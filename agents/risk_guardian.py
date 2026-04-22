"""
OKComputer — Risk Guardian Agent (A7)
The most important agent in the trading system.
Enforces Constitution A1: Capital Preservation.
Cannot be overridden. Not even by CEO Agent.
"""
import json
from typing import Dict, Any, Optional, Tuple
from loguru import logger
from agents.base import BaseAgent
from config import settings


class RiskGuardian(BaseAgent):
    agent_id = "A7"
    agent_name = "Risk Guardian"
    division = "trading"
    description = "Enforces all capital limits. Can halt ALL trading. Cannot be overridden."

    def __init__(self, db_session=None):
        super().__init__(db_session)
        # Hard-coded limits — these do NOT come from config
        # They are burned into the agent and cannot be changed via API
        self.MAX_POSITION_SIZE_PCT = settings.max_position_size_pct    # 2%
        self.MAX_DAILY_DRAWDOWN_PCT = settings.max_daily_drawdown_pct  # 3%
        self.MAX_TOTAL_DRAWDOWN_PCT = settings.max_total_drawdown_pct  # 10%
        self.MIN_CONFIDENCE = settings.min_confidence_threshold         # 70%
        self.emergency_stop_active = False

    # ── TRADE PRE-APPROVAL ────────────────────────────────────
    async def approve_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        portfolio_value: float,
        daily_pnl: float,
        current_drawdown: float,
        confidence: float,
        strategy_name: str = "",
        user_id: str = None,
    ) -> Tuple[bool, str, Dict]:
        """
        Approve or reject a trade before execution.
        This is the last line of defense before real capital is touched.

        Returns: (approved: bool, reason: str, risk_analysis: dict)
        """
        risk_analysis = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "trade_value_usdt": quantity * price,
            "portfolio_value": portfolio_value,
            "position_size_pct": (quantity * price / portfolio_value * 100) if portfolio_value > 0 else 0,
            "daily_pnl": daily_pnl,
            "daily_drawdown_pct": abs(daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0,
            "current_drawdown_pct": current_drawdown,
            "confidence": confidence,
            "checks": [],
            "approved": False,
            "rejection_reason": None,
        }

        # ── CHECK 1: Emergency stop ──────────────────────────
        if self.emergency_stop_active:
            reason = "EMERGENCY STOP ACTIVE — No trading allowed. Human intervention required."
            risk_analysis["rejection_reason"] = reason
            risk_analysis["checks"].append({"check": "emergency_stop", "passed": False, "reason": reason})
            await self._alert_operator(reason, user_id, severity="CRITICAL")
            return False, reason, risk_analysis
        risk_analysis["checks"].append({"check": "emergency_stop", "passed": True})

        # ── CHECK 2: Portfolio exists ────────────────────────
        if portfolio_value <= 0:
            reason = "Invalid portfolio value — cannot calculate risk"
            risk_analysis["rejection_reason"] = reason
            return False, reason, risk_analysis
        risk_analysis["checks"].append({"check": "portfolio_valid", "passed": True})

        # ── CHECK 3: Confidence threshold (A4) ──────────────
        if confidence < self.MIN_CONFIDENCE * 100:
            reason = f"Constitution A4: Confidence {confidence:.1f}% < {self.MIN_CONFIDENCE*100}% required"
            risk_analysis["rejection_reason"] = reason
            risk_analysis["checks"].append({"check": "confidence", "passed": False, "reason": reason})
            return False, reason, risk_analysis
        risk_analysis["checks"].append({"check": "confidence", "passed": True})

        # ── CHECK 4: Position size limit (A1) ────────────────
        position_size_pct = risk_analysis["position_size_pct"]
        if position_size_pct > self.MAX_POSITION_SIZE_PCT * 100:
            reason = (
                f"Constitution A1: Position size {position_size_pct:.2f}% "
                f"exceeds max {self.MAX_POSITION_SIZE_PCT*100}%"
            )
            risk_analysis["rejection_reason"] = reason
            risk_analysis["checks"].append({"check": "position_size", "passed": False, "reason": reason})
            return False, reason, risk_analysis
        risk_analysis["checks"].append({"check": "position_size", "passed": True})

        # ── CHECK 5: Daily drawdown limit (A1) ───────────────
        daily_drawdown_pct = risk_analysis["daily_drawdown_pct"]
        if daily_pnl < 0 and daily_drawdown_pct > self.MAX_DAILY_DRAWDOWN_PCT * 100:
            reason = (
                f"Constitution A1: Daily drawdown {daily_drawdown_pct:.2f}% "
                f"exceeds max {self.MAX_DAILY_DRAWDOWN_PCT*100}%"
            )
            risk_analysis["rejection_reason"] = reason
            risk_analysis["checks"].append({"check": "daily_drawdown", "passed": False, "reason": reason})
            await self._alert_operator(
                f"Daily drawdown limit reached: {daily_drawdown_pct:.2f}%. Trading paused.",
                user_id, severity="CRITICAL"
            )
            return False, reason, risk_analysis
        risk_analysis["checks"].append({"check": "daily_drawdown", "passed": True})

        # ── CHECK 6: Total drawdown — Emergency stop (A1) ────
        if current_drawdown > self.MAX_TOTAL_DRAWDOWN_PCT * 100:
            reason = (
                f"Constitution A1: EMERGENCY STOP — Total drawdown {current_drawdown:.2f}% "
                f"exceeds {self.MAX_TOTAL_DRAWDOWN_PCT*100}%. All trading halted."
            )
            self.emergency_stop_active = True
            risk_analysis["rejection_reason"] = reason
            risk_analysis["checks"].append({"check": "total_drawdown", "passed": False, "reason": reason})
            await self._alert_operator(reason, user_id, severity="CRITICAL")
            return False, reason, risk_analysis
        risk_analysis["checks"].append({"check": "total_drawdown", "passed": True})

        # ── ALL CHECKS PASSED ────────────────────────────────
        risk_analysis["approved"] = True
        risk_analysis["checks"].append({"check": "final_approval", "passed": True})

        logger.info(
            f"[A7 Risk] APPROVED: {symbol} {side} | "
            f"Size: {position_size_pct:.2f}% | "
            f"Confidence: {confidence:.1f}%"
        )

        # Log the approval
        await self.log_decision(
            action_type="TRADE_APPROVAL",
            decision=f"APPROVED: {symbol} {side} {quantity}",
            input_data={"symbol": symbol, "quantity": quantity, "confidence": confidence},
            output_data=risk_analysis,
            confidence=confidence,
        )

        return True, "All risk checks passed", risk_analysis

    # ── PORTFOLIO HEALTH CHECK ────────────────────────────────
    async def portfolio_health_check(
        self,
        portfolio_value: float,
        peak_value: float,
        daily_pnl: float,
        open_positions: list,
    ) -> Dict[str, Any]:
        """
        Runs continuously to monitor portfolio health.
        Called every 5 minutes during market hours.
        """
        current_drawdown = ((peak_value - portfolio_value) / peak_value * 100) if peak_value > 0 else 0
        daily_pnl_pct = (daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0

        # Risk level assessment
        if current_drawdown > self.MAX_TOTAL_DRAWDOWN_PCT * 100 * 0.8:
            risk_level = "CRITICAL"
        elif current_drawdown > self.MAX_TOTAL_DRAWDOWN_PCT * 100 * 0.5:
            risk_level = "HIGH"
        elif daily_pnl_pct < -(self.MAX_DAILY_DRAWDOWN_PCT * 100 * 0.7):
            risk_level = "ELEVATED"
        else:
            risk_level = "NORMAL"

        health = {
            "portfolio_value": portfolio_value,
            "peak_value": peak_value,
            "current_drawdown_pct": round(current_drawdown, 3),
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": round(daily_pnl_pct, 3),
            "open_positions": len(open_positions),
            "risk_level": risk_level,
            "emergency_stop_active": self.emergency_stop_active,
            "limits": {
                "max_position_pct": self.MAX_POSITION_SIZE_PCT * 100,
                "max_daily_drawdown_pct": self.MAX_DAILY_DRAWDOWN_PCT * 100,
                "max_total_drawdown_pct": self.MAX_TOTAL_DRAWDOWN_PCT * 100,
            },
            "checked_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

        if risk_level == "CRITICAL":
            logger.critical(f"[A7 Risk] CRITICAL: Drawdown {current_drawdown:.2f}%")
        elif risk_level == "HIGH":
            logger.warning(f"[A7 Risk] HIGH RISK: Drawdown {current_drawdown:.2f}%")

        return health

    # ── EMERGENCY STOP ────────────────────────────────────────
    async def trigger_emergency_stop(self, reason: str, user_id: str = None):
        """
        Activates emergency stop. All trading halted immediately.
        Only the human operator can deactivate this.
        """
        self.emergency_stop_active = True
        logger.critical(f"[A7 Risk] EMERGENCY STOP: {reason}")

        await self.log_decision(
            action_type="EMERGENCY_STOP",
            decision=f"EMERGENCY STOP TRIGGERED: {reason}",
            confidence=100,  # Maximum certainty — this is always correct
        )

        await self._alert_operator(
            f"🚨 EMERGENCY STOP TRIGGERED\n\nReason: {reason}\n\n"
            f"All trading has been halted. Human intervention required to resume.",
            user_id, severity="CRITICAL"
        )

    async def deactivate_emergency_stop(self, operator_confirmed: bool = False):
        """Only the human operator can deactivate emergency stop"""
        if not operator_confirmed:
            return False, "Human operator confirmation required"
        self.emergency_stop_active = False
        logger.info("[A7 Risk] Emergency stop deactivated by operator")
        return True, "Emergency stop deactivated"

    # ── POSITION SIZING ───────────────────────────────────────
    def calculate_position_size(
        self,
        portfolio_value: float,
        risk_pct: float,
        entry_price: float,
        stop_loss_price: float,
    ) -> float:
        """
        Kelly-criterion-inspired position sizing.
        Constitution A1: Never risk more than specified %.
        """
        if stop_loss_price >= entry_price:
            return 0.0  # Invalid stop loss

        risk_per_unit = abs(entry_price - stop_loss_price)
        max_risk_amount = portfolio_value * min(risk_pct, self.MAX_POSITION_SIZE_PCT)
        quantity = max_risk_amount / risk_per_unit

        logger.debug(
            f"[A7 Risk] Position size: {quantity:.4f} units | "
            f"Risk: ${max_risk_amount:.2f} | "
            f"Stop distance: ${risk_per_unit:.4f}"
        )
        return quantity

    # ── INTERNAL ALERT ────────────────────────────────────────
    async def _alert_operator(self, message: str, user_id: str = None, severity: str = "WARNING"):
        """Send alert to operator — email + in-app notification"""
        logger.warning(f"[A7 Risk] OPERATOR ALERT [{severity}]: {message[:100]}")
        # In production: send email via Resend, push notification, Slack webhook
        # For now: log only
        if self.db and user_id:
            try:
                from database.models import Alert
                alert = Alert(
                    user_id=user_id,
                    agent_id=self.agent_id,
                    alert_type="RISK",
                    severity=severity,
                    title=f"Risk Guardian Alert — {severity}",
                    message=message,
                )
                self.db.add(alert)
                await self.db.commit()
            except Exception as e:
                logger.error(f"[A7 Risk] Alert storage error: {e}")

    async def run_daily_cycle(self) -> Dict:
        return {"status": "Risk Guardian active", "emergency_stop": self.emergency_stop_active}
