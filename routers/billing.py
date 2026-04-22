"""
OKComputer — Stripe Payments Router
Subscription management, webhooks, billing portal
Plans: Starter $99 | Growth $299 | Enterprise $999+
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from loguru import logger

from database.connection import get_db
from database.models import User, UserPlan, UserStatus, Subscription
from routers.auth import get_current_user
from config import settings

router = APIRouter(prefix="/billing", tags=["billing"])

try:
    import stripe
    stripe.api_key = settings.stripe_secret_key
    STRIPE_AVAILABLE = bool(settings.stripe_secret_key)
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("Stripe not installed. Billing disabled.")

# ── PLAN CONFIG ───────────────────────────────────────────────
PLANS = {
    "starter": {
        "name": "Starter",
        "price_cents": 9900,       # $99/mo
        "price_id": settings.stripe_price_starter,
        "features": [
            "1 trading bot",
            "5 trading pairs",
            "Paper trading only",
            "CEO Agent briefing",
            "Basic risk management",
            "Email support",
        ],
        "limits": {
            "bots": 1,
            "pairs": 5,
            "live_trading": False,
        }
    },
    "growth": {
        "name": "Growth",
        "price_cents": 29900,      # $299/mo
        "price_id": settings.stripe_price_growth,
        "features": [
            "5 trading bots",
            "50 trading pairs",
            "Live trading enabled",
            "All 27 AI agents",
            "Full The Architect suite",
            "Red-team + Evolution",
            "Priority support",
        ],
        "limits": {
            "bots": 5,
            "pairs": 50,
            "live_trading": True,
        }
    },
    "enterprise": {
        "name": "Enterprise",
        "price_cents": 99900,      # $999/mo
        "price_id": settings.stripe_price_enterprise,
        "features": [
            "Unlimited bots",
            "All asset classes",
            "Custom strategy deployment",
            "White-label option",
            "Dedicated infrastructure",
            "Custom AI agent training",
            "Direct founder access",
        ],
        "limits": {
            "bots": -1,  # unlimited
            "pairs": -1,
            "live_trading": True,
        }
    }
}

# ── SCHEMAS ───────────────────────────────────────────────────
class CreateCheckoutRequest(BaseModel):
    plan: str
    success_url: str = "https://okcomputer.ai/dashboard?upgraded=true"
    cancel_url: str = "https://okcomputer.ai/pricing"


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool = False
    amount_cents: int


# ── ENDPOINTS ─────────────────────────────────────────────────
@router.get("/plans")
async def get_plans():
    """Get all available subscription plans — no auth required"""
    return {
        "plans": [
            {
                "id": plan_id,
                "name": plan["name"],
                "price_monthly": plan["price_cents"] / 100,
                "price_display": f"${plan['price_cents']//100}/mo",
                "features": plan["features"],
                "limits": plan["limits"],
                "popular": plan_id == "growth",
            }
            for plan_id, plan in PLANS.items()
        ],
        "trial": "30 days free — no credit card required",
    }


@router.post("/checkout")
async def create_checkout_session(
    request: CreateCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a Stripe Checkout session for plan upgrade"""
    if not STRIPE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Billing not configured")

    plan = PLANS.get(request.plan)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {request.plan}")

    if not plan["price_id"]:
        raise HTTPException(status_code=503, detail="Plan price not configured in Stripe")

    try:
        # Get or create Stripe customer
        if current_user.stripe_customer_id:
            customer_id = current_user.stripe_customer_id
        else:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=current_user.full_name,
                metadata={"user_id": current_user.id, "app": "okcomputer"},
            )
            current_user.stripe_customer_id = customer.id
            await db.commit()
            customer_id = customer.id

        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": plan["price_id"], "quantity": 1}],
            mode="subscription",
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata={"user_id": current_user.id, "plan": request.plan},
            subscription_data={
                "metadata": {"user_id": current_user.id, "plan": request.plan},
                "trial_period_days": 0 if current_user.plan != UserPlan.STARTER else None,
            },
        )

        logger.info(f"Checkout session created for {current_user.email}: {request.plan}")
        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/subscription")
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current subscription status"""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == current_user.id)
        .order_by(Subscription.created_at.desc())
    )
    sub = result.scalar_one_or_none()

    plan_config = PLANS.get(current_user.plan, PLANS["starter"])

    return {
        "plan": current_user.plan,
        "status": current_user.status,
        "plan_name": plan_config["name"],
        "features": plan_config["features"],
        "limits": plan_config["limits"],
        "trial_ends_at": current_user.trial_ends_at.isoformat() if current_user.trial_ends_at else None,
        "subscription": {
            "status": sub.status if sub else "trial",
            "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
            "amount_display": f"${sub.amount_cents//100}/mo" if sub else "Free trial",
        } if sub else None,
    }


@router.post("/portal")
async def create_billing_portal(
    current_user: User = Depends(get_current_user),
):
    """Create Stripe billing portal session for managing subscription"""
    if not STRIPE_AVAILABLE or not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription found")

    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url="https://okcomputer.ai/dashboard",
        )
        return {"portal_url": session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Stripe webhook handler.
    Handles subscription lifecycle events.
    """
    if not STRIPE_AVAILABLE:
        return JSONResponse({"status": "billing_disabled"})

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle events
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Stripe webhook: {event_type}")

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, db)

    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, db)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_cancelled(data, db)

    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data, db)

    return {"status": "processed", "event": event_type}


# ── WEBHOOK HANDLERS ──────────────────────────────────────────
async def _handle_checkout_completed(session_data: dict, db: AsyncSession):
    """Activate subscription after successful checkout"""
    user_id = session_data.get("metadata", {}).get("user_id")
    plan_id = session_data.get("metadata", {}).get("plan")

    if not user_id or not plan_id:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    plan_map = {"starter": UserPlan.STARTER, "growth": UserPlan.GROWTH, "enterprise": UserPlan.ENTERPRISE}
    user.plan = plan_map.get(plan_id, UserPlan.STARTER)
    user.status = UserStatus.ACTIVE
    user.stripe_subscription_id = session_data.get("subscription")

    # Enable live trading for Growth+ plans
    if plan_id in ["growth", "enterprise"]:
        user.paper_trading = False

    # Record subscription
    plan_config = PLANS.get(plan_id, PLANS["starter"])
    sub = Subscription(
        user_id=user_id,
        plan=user.plan,
        status="active",
        stripe_subscription_id=session_data.get("subscription"),
        amount_cents=plan_config["price_cents"],
    )
    db.add(sub)
    await db.commit()
    logger.info(f"Subscription activated: {user.email} → {plan_id}")


async def _handle_subscription_updated(sub_data: dict, db: AsyncSession):
    """Update subscription when plan changes"""
    user_id = sub_data.get("metadata", {}).get("user_id")
    if not user_id:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    status = sub_data.get("status")
    if status == "active":
        user.status = UserStatus.ACTIVE
    elif status == "past_due":
        user.status = UserStatus.SUSPENDED

    await db.commit()


async def _handle_subscription_cancelled(sub_data: dict, db: AsyncSession):
    """Handle subscription cancellation"""
    user_id = sub_data.get("metadata", {}).get("user_id")
    if not user_id:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    user.status = UserStatus.CANCELLED
    user.plan = UserPlan.STARTER
    user.paper_trading = True  # Back to paper trading
    await db.commit()
    logger.info(f"Subscription cancelled: {user.email}")


async def _handle_payment_failed(invoice_data: dict, db: AsyncSession):
    """Handle failed payment — send alert"""
    customer_id = invoice_data.get("customer")
    logger.warning(f"Payment failed for customer: {customer_id}")
    # In production: send email via Resend
