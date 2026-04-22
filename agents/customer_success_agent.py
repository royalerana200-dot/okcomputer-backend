"""
OKComputer — Customer Success Agent (A12)
Predicts churn 30 days early. Proactive intervention.
Constitution A3: Customer First — always.
"""
import json
from typing import Dict, Any, List, Optional
from loguru import logger
from agents.base import BaseAgent


CS_SYSTEM = """You are the Customer Success Agent (A12) of OKComputer.

Your mission: Keep every customer successful, engaged, and growing.
You predict churn before it happens and intervene proactively.
You track every signal that indicates a customer is at risk or thriving.

Constitution A3 (Customer First) is your primary directive:
Every action must genuinely help the customer — not just retain them for revenue.
If a customer should cancel, help them do it gracefully. The long-term brand matters more.

Respond only with valid JSON."""


class CustomerSuccessAgent(BaseAgent):
    agent_id = "A12"
    agent_name = "Customer Success"
    division = "business"
    description = "Predicts churn 30 days early. Proactive intervention. NPS monitoring."

    # Behavioral signals that indicate churn risk
    CHURN_SIGNALS = {
        "no_login_7_days": 25,       # Points added to churn risk
        "no_login_14_days": 45,
        "bot_paused_14_days": 30,
        "support_ticket_unresolved": 20,
        "onboarding_incomplete": 35,
        "day_12_spike": 20,          # Historical data shows day 12/47 are peak churn
        "day_47_spike": 25,
        "negative_pnl_streak": 40,
        "downgrade_inquiry": 60,
    }

    async def calculate_churn_risk(self, customer_data: Dict) -> Dict[str, Any]:
        """
        Calculate churn risk score 0-100.
        Score > 60: Intervention required immediately.
        Score > 40: Monitoring required.
        Score < 40: Healthy.
        """
        risk_score = 0
        triggered_signals = []

        days_since_login = customer_data.get("days_since_login", 0)
        if days_since_login >= 14:
            risk_score += self.CHURN_SIGNALS["no_login_14_days"]
            triggered_signals.append(f"No login for {days_since_login} days")
        elif days_since_login >= 7:
            risk_score += self.CHURN_SIGNALS["no_login_7_days"]
            triggered_signals.append(f"No login for {days_since_login} days")

        days_since_active = customer_data.get("days_bot_paused", 0)
        if days_since_active >= 14:
            risk_score += self.CHURN_SIGNALS["bot_paused_14_days"]
            triggered_signals.append("Bot paused for 14+ days")

        if not customer_data.get("onboarding_complete", True):
            risk_score += self.CHURN_SIGNALS["onboarding_incomplete"]
            triggered_signals.append("Onboarding not completed")

        if customer_data.get("unresolved_tickets", 0) > 0:
            risk_score += self.CHURN_SIGNALS["support_ticket_unresolved"]
            triggered_signals.append("Unresolved support ticket")

        days_subscribed = customer_data.get("days_subscribed", 0)
        if 10 <= days_subscribed <= 14:
            risk_score += self.CHURN_SIGNALS["day_12_spike"]
            triggered_signals.append("Day 12 churn window active")
        elif 44 <= days_subscribed <= 50:
            risk_score += self.CHURN_SIGNALS["day_47_spike"]
            triggered_signals.append("Day 47 churn window active")

        consecutive_loss_days = customer_data.get("consecutive_loss_days", 0)
        if consecutive_loss_days >= 3:
            risk_score += self.CHURN_SIGNALS["negative_pnl_streak"]
            triggered_signals.append(f"{consecutive_loss_days} consecutive losing days")

        if customer_data.get("downgrade_inquiry", False):
            risk_score += self.CHURN_SIGNALS["downgrade_inquiry"]
            triggered_signals.append("Customer inquired about downgrade")

        risk_score = min(100, risk_score)
        risk_level = "CRITICAL" if risk_score > 70 else "HIGH" if risk_score > 50 else "ELEVATED" if risk_score > 30 else "LOW"

        return {
            "customer_id": customer_data.get("user_id"),
            "customer_name": customer_data.get("full_name"),
            "churn_risk_score": risk_score,
            "risk_level": risk_level,
            "triggered_signals": triggered_signals,
            "intervention_required": risk_score > 50,
            "days_subscribed": days_subscribed,
        }

    async def generate_intervention(self, customer_data: Dict, churn_risk: Dict) -> Dict[str, Any]:
        """
        Generate personalized retention intervention.
        Constitution A3: The intervention must genuinely help them.
        """
        if not churn_risk.get("intervention_required"):
            return {"intervention": "none", "reason": "Risk level acceptable"}

        prompt = f"""{CS_SYSTEM}

Generate a retention intervention for this at-risk customer.

Customer Data:
{json.dumps(customer_data, indent=2)}

Churn Risk Assessment:
{json.dumps(churn_risk, indent=2)}

Design an intervention that:
1. Addresses their specific signals (not generic)
2. Genuinely helps them get more value from OKComputer
3. Does NOT feel manipulative or desperate
4. Constitution A3: If they should cancel, help them — the brand matters more

Respond with valid JSON:
{{
  "intervention_type": "PERSONAL_OUTREACH|FEATURE_EDUCATION|STRATEGY_REVIEW|CONCESSION|ESCALATION",
  "message": "The personalized message to send",
  "tone": "Empathetic and helpful — not salesy",
  "specific_value": "One specific thing we can offer that addresses their exact pain",
  "offer": null,
  "send_via": ["email"],
  "send_timing": "immediately|in_2_hours|tomorrow_morning",
  "escalate_to_human": false,
  "if_no_response_in_days": 3,
  "constitution_check": "Does this genuinely help the customer?"
}}"""

        raw = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}]
        )
        result = json.loads(raw.content[0].text.replace("```json", "").replace("```", "").strip())

        await self.log_decision(
            action_type="CHURN_INTERVENTION",
            decision=f"Intervention: {result.get('intervention_type')} for {customer_data.get('full_name')}",
            input_data=churn_risk,
            output_data=result,
            confidence=churn_risk.get("churn_risk_score"),
        )

        await self.store_memory(
            situation=f"Churn risk {churn_risk['churn_risk_score']}% — signals: {', '.join(churn_risk['triggered_signals'][:2])}",
            action_taken=f"Sent {result.get('intervention_type')} intervention",
            importance=0.85,
            tags=["churn_intervention", churn_risk["risk_level"].lower()],
        )

        return result

    async def generate_success_tips(self, customer_data: Dict) -> Dict[str, Any]:
        """
        Generate personalized tips for healthy customers.
        Proactive value delivery — not just reactive retention.
        """
        prompt = f"""{CS_SYSTEM}

Generate personalized success tips for this OKComputer customer.
They are HEALTHY (low churn risk) — focus on helping them get MORE value.

Customer Data:
{json.dumps(customer_data, indent=2)}

Respond with valid JSON:
{{
  "weekly_insight": "One specific insight based on their trading data this week",
  "feature_spotlight": "One underused feature they'd benefit from",
  "strategy_tip": "One specific trading strategy optimization for their style",
  "benchmark": "How their performance compares to similar users (anonymized)",
  "next_milestone": "What they should aim for next week"
}}"""

        raw = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(raw.content[0].text.replace("```json", "").replace("```", "").strip())

    async def run_daily_cycle(self) -> Dict:
        """
        Daily scan: calculate churn risk for all active customers.
        In production: pulls from database and runs for every user.
        """
        logger.info("[A12 Customer Success] Running daily churn risk scan...")

        # Placeholder — in production iterates over all users
        return {
            "status": "Daily cycle complete",
            "scanned": 0,
            "at_risk": 0,
            "interventions_queued": 0,
        }
