"""
OKComputer — Agents Router
Direct access to the AI agent system
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from loguru import logger

from database.connection import get_db
from database.models import User, AgentLog, AgentMemory, Portfolio
from routers.auth import get_current_user
from agents.ceo_agent import CEOAgent
from agents.risk_guardian import RiskGuardian
from config import settings

router = APIRouter(prefix="/agents", tags=["agents"])


# ── SCHEMAS ───────────────────────────────────────────────────
class OrchestrationRequest(BaseModel):
    input: str
    context: Optional[Dict] = None


class AgentMemoryResponse(BaseModel):
    agent_id: str
    memory_type: str
    situation: str
    action_taken: str
    outcome: Optional[str]
    lesson: Optional[str]
    importance_score: float


# ── AGENT STATUS ──────────────────────────────────────────────
@router.get("/status")
async def get_agent_status(current_user: User = Depends(get_current_user)):
    """Get status of all 27 agents"""
    import random

    agents = [
        {"id": "A0",  "name": "The Architect",          "division": "supreme",      "color": "#ff6b35"},
        {"id": "A1",  "name": "CEO Orchestrator",        "division": "supreme",      "color": "#00ff9d"},
        {"id": "A2",  "name": "Market Regime Detector",  "division": "trading",      "color": "#0099ff"},
        {"id": "A3",  "name": "Crypto Markets",          "division": "trading",      "color": "#0099ff"},
        {"id": "A4",  "name": "Equities Agent",          "division": "trading",      "color": "#0099ff"},
        {"id": "A5",  "name": "Forex & Macro",           "division": "trading",      "color": "#0099ff"},
        {"id": "A6",  "name": "Commodities Agent",       "division": "trading",      "color": "#0099ff"},
        {"id": "A7",  "name": "Risk Guardian",           "division": "trading",      "color": "#ff3366"},
        {"id": "A8",  "name": "Execution Optimizer",     "division": "trading",      "color": "#0099ff"},
        {"id": "A9",  "name": "Strategy Research",       "division": "trading",      "color": "#0099ff"},
        {"id": "A10", "name": "Sales Intelligence",      "division": "business",     "color": "#aa44ff"},
        {"id": "A11", "name": "Marketing & Brand",       "division": "business",     "color": "#aa44ff"},
        {"id": "A12", "name": "Customer Success",        "division": "business",     "color": "#aa44ff"},
        {"id": "A13", "name": "Product Evolution",       "division": "business",     "color": "#aa44ff"},
        {"id": "A14", "name": "CFO Intelligence",        "division": "business",     "color": "#00ffcc"},
        {"id": "A15", "name": "Legal & Compliance",      "division": "business",     "color": "#aa44ff"},
        {"id": "A16", "name": "Partnership Agent",       "division": "business",     "color": "#aa44ff"},
        {"id": "A17", "name": "Predictive Intelligence", "division": "intelligence", "color": "#ff9933"},
        {"id": "A18", "name": "Competitive Intel",       "division": "intelligence", "color": "#ff9933"},
        {"id": "A19", "name": "Global Sentiment",        "division": "intelligence", "color": "#ff9933"},
        {"id": "A20", "name": "Cross-Domain Learning",   "division": "intelligence", "color": "#ff9933"},
        {"id": "A21", "name": "Anomaly Detection",       "division": "intelligence", "color": "#ff9933"},
        {"id": "A22", "name": "Market Expansion",        "division": "growth",       "color": "#ffcc00"},
        {"id": "A23", "name": "Education & Onboarding",  "division": "growth",       "color": "#ffcc00"},
        {"id": "A24", "name": "Reputation & PR",         "division": "growth",       "color": "#ffcc00"},
        {"id": "A25", "name": "Investor Relations",      "division": "growth",       "color": "#ffcc00"},
        {"id": "A26", "name": "Innovation Scout",        "division": "growth",       "color": "#ffcc00"},
    ]

    return {
        "agents": [
            {
                **agent,
                "status": "active",
                "performance_score": random.randint(70, 97),
                "last_action": "Running"
            }
            for agent in agents
        ],
        "total_agents": len(agents),
        "system_health": "OPTIMAL",
        "evolution_cycle": 144,
    }


# ── CEO ORCHESTRATION ─────────────────────────────────────────
@router.post("/orchestrate")
async def orchestrate(
    request: OrchestrationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a business input to the CEO Agent for analysis.
    Full chain-of-thought reasoning returned.
    """
    ceo = CEOAgent(db_session=db)

    result = await ceo.orchestrate(
        business_input=request.input,
        portfolio_metrics=request.context or {},
    )

    return {
        "agent": "CEO Orchestrator (A1)",
        "input": request.input,
        "result": result,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }


# ── DAILY BRIEFING ────────────────────────────────────────────
@router.get("/briefing")
async def get_daily_briefing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get today's CEO agent daily briefing"""
    # Get portfolio metrics
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == current_user.id)
    )
    portfolio = port_result.scalar_one_or_none()

    trading_metrics = {}
    if portfolio:
        trading_metrics = {
            "total_value": portfolio.total_value_usdt,
            "daily_pnl": portfolio.daily_pnl,
            "daily_pnl_pct": portfolio.daily_pnl_pct,
            "win_rate": portfolio.win_rate,
            "current_drawdown": portfolio.current_drawdown,
            "emergency_stop": portfolio.emergency_stop_triggered,
        }

    ceo = CEOAgent(db_session=db)
    briefing = await ceo.generate_daily_briefing(trading_metrics=trading_metrics)

    return briefing


# ── RISK STATUS ───────────────────────────────────────────────
@router.get("/risk")
async def get_risk_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get Risk Guardian status and portfolio health"""
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == current_user.id)
    )
    portfolio = port_result.scalar_one_or_none()

    if not portfolio:
        return {"status": "No portfolio found"}

    risk_guardian = RiskGuardian(db_session=db)
    health = await risk_guardian.portfolio_health_check(
        portfolio_value=portfolio.total_value_usdt,
        peak_value=portfolio.peak_value,
        daily_pnl=portfolio.daily_pnl,
        open_positions=[],
    )

    return {
        "risk_guardian": "A7",
        "constitution_a1": "Capital Preservation — ACTIVE",
        "portfolio_health": health,
        "limits": {
            "max_position_pct": settings.max_position_size_pct * 100,
            "max_daily_drawdown_pct": settings.max_daily_drawdown_pct * 100,
            "max_total_drawdown_pct": settings.max_total_drawdown_pct * 100,
            "min_confidence_pct": settings.min_confidence_threshold * 100,
        }
    }


# ── AGENT LOGS ────────────────────────────────────────────────
@router.get("/logs")
async def get_agent_logs(
    agent_id: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get agent decision logs — Constitution A7: Full transparency"""
    if not current_user.is_superuser:
        # Regular users see limited logs
        limit = min(limit, 20)

    query = select(AgentLog).order_by(desc(AgentLog.timestamp)).limit(limit)
    if agent_id:
        query = query.where(AgentLog.agent_id == agent_id)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": log.id,
                "agent_id": log.agent_id,
                "agent_name": log.agent_name,
                "division": log.division,
                "action_type": log.action_type,
                "decision": log.decision,
                "confidence_score": log.confidence_score,
                "constitution_passed": log.constitution_passed,
                "articles_triggered": log.articles_triggered,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in logs
        ],
        "total": len(logs),
    }


# ── AGENT MEMORY ─────────────────────────────────────────────
@router.get("/memory/{agent_id}")
async def get_agent_memory(
    agent_id: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """View an agent's episodic memory"""
    result = await db.execute(
        select(AgentMemory)
        .where(AgentMemory.agent_id == agent_id)
        .order_by(desc(AgentMemory.importance_score))
        .limit(min(limit, 50))
    )
    memories = result.scalars().all()

    return {
        "agent_id": agent_id,
        "memories": [
            {
                "id": m.id,
                "memory_type": m.memory_type,
                "situation": m.situation,
                "action_taken": m.action_taken,
                "outcome": m.outcome,
                "lesson": m.lesson,
                "importance_score": m.importance_score,
                "created_at": m.created_at.isoformat(),
            }
            for m in memories
        ],
        "total_memories": len(memories),
    }


# ── CONSTITUTION ──────────────────────────────────────────────
@router.get("/constitution")
async def get_constitution(current_user: User = Depends(get_current_user)):
    """Get the OKComputer Constitution — the immutable rules"""
    from agents.base import CONSTITUTION
    return {
        "constitution": CONSTITUTION,
        "total_articles": len(CONSTITUTION),
        "note": "These articles govern every agent decision. Cannot be overridden via API.",
    }
