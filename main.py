"""
OKComputer — Main Application Entry Point
FastAPI backend with all routers mounted
"""
import os
os.makedirs("logs", exist_ok=True)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import sys
import time

from config import settings
from database.connection import init_db, close_db

# ── LOGGING ───────────────────────────────────────────────────
import os
os.makedirs("logs", exist_ok=True)
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
    level="DEBUG" if settings.debug else "INFO",
    colorize=True,
)
logger.add("logs/okcomputer.log", rotation="1 day", retention="30 days", level="INFO")


# ── LIFESPAN ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("=" * 60)
    logger.info("   OKComputer v1.0 — Starting up")
    logger.info("=" * 60)
    logger.info(f"   Environment: {settings.app_env}")
    logger.info(f"   Paper Trading: {settings.paper_trading_mode}")
    logger.info(f"   AI Model: {settings.anthropic_model}")

    # Initialize database
    await init_db()
    logger.info("   Constitutional Core: ARMED (7 articles)")
    logger.info("   27 Agents: STANDING BY")
    logger.info("=" * 60)

    yield  # App runs here

    # Shutdown
    await close_db()
    logger.info("OKComputer shutting down. All positions safe.")


# ── APP ───────────────────────────────────────────────────────
app = FastAPI(
    title="OKComputer API",
    description="Autonomous AI Trading & Business Intelligence System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)


# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REQUEST TIMING ────────────────────────────────────────────
@app.middleware("http")
async def add_timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    response.headers["X-Response-Time"] = f"{duration:.1f}ms"
    return response


# ── GLOBAL ERROR HANDLER ──────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc) if settings.debug else "Contact support"}
    )


# ── ROUTERS ───────────────────────────────────────────────────
from routers.auth import router as auth_router
from routers.trading import router as trading_router
from routers.agents import router as agents_router

app.include_router(auth_router)
app.include_router(trading_router)
app.include_router(agents_router)


# ── HEALTH & ROOT ─────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "system": "OKComputer",
        "version": "1.0.0",
        "status": "operational",
        "agents": 27,
        "constitution": "7 articles active",
        "paper_trading": settings.paper_trading_mode,
        "documentation": "/docs",
    }


@app.get("/health")
async def health():
    """Railway health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "environment": settings.app_env,
    }


@app.get("/constitution")
async def constitution():
    """Public endpoint — The OKComputer Constitution"""
    from agents.base import CONSTITUTION
    return {"constitution": CONSTITUTION, "immutable": True}


# ── RUN ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        workers=1 if settings.debug else 4,
    )
