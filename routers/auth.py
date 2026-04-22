"""
OKComputer — Authentication Router
JWT-based auth with refresh tokens
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from loguru import logger

from database.connection import get_db
from database.models import User, UserPlan, UserStatus, Portfolio
from config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── SCHEMAS ───────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    plan: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    plan: str
    status: str
    paper_trading: bool
    kyc_verified: bool
    created_at: datetime


# ── HELPERS ───────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + expires_delta
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_tokens(user_id: str, email: str) -> dict:
    access_token = create_token(
        {"sub": user_id, "email": email, "type": "access"},
        timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    refresh_token = create_token(
        {"sub": user_id, "email": email, "type": "refresh"},
        timedelta(days=settings.jwt_refresh_token_expire_days)
    )
    return {"access_token": access_token, "refresh_token": refresh_token}


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """FastAPI dependency — validates JWT and returns current user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if not user_id or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(status_code=403, detail="Account suspended")

    return user


# ── ROUTES ────────────────────────────────────────────────────
@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user — 30-day free trial"""

    # Check email unique
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user
    user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
        plan=UserPlan.STARTER,
        status=UserStatus.TRIAL,
        trial_ends_at=datetime.utcnow() + timedelta(days=30),
        paper_trading=True,  # Always start in paper mode
    )
    db.add(user)
    await db.flush()  # Get the user.id

    # Create empty portfolio
    portfolio = Portfolio(user_id=user.id, peak_value=10000.0)  # $10k paper start
    db.add(portfolio)
    await db.commit()

    tokens = create_tokens(user.id, user.email)
    logger.info(f"New user registered: {user.email}")

    return LoginResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user_id=user.id,
        email=user.email,
        plan=user.plan,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password"""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # Update last login
    user.last_login_at = datetime.utcnow()
    await db.commit()

    tokens = create_tokens(user.id, user.email)
    logger.info(f"User login: {user.email}")

    return LoginResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user_id=user.id,
        email=user.email,
        plan=user.plan,
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(request: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token"""
    try:
        payload = jwt.decode(
            request.refresh_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        token_type = payload.get("type")
        if not user_id or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tokens = create_tokens(user.id, user.email)
    return LoginResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user_id=user.id,
        email=user.email,
        plan=user.plan,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        plan=current_user.plan,
        status=current_user.status,
        paper_trading=current_user.paper_trading,
        kyc_verified=current_user.kyc_verified,
        created_at=current_user.created_at,
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout — client should delete tokens"""
    return {"message": "Logged out successfully"}
