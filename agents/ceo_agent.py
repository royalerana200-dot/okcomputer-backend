"""
OKComputer — CEO Orchestrator Agent (A1)
Master decision intelligence. Coordinates all other agents.
Produces daily operator briefing.
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger
from agents.base import BaseAgent, CONSTITUTION_TEXT


CEO_SYSTEM_PROMPT = """You are the CEO Orchestrator Agent (A1) of OKComputer — an autonomous AI trading and SaaS business system.

Your responsibilities:
1. Coordinate all 26 other agents
2. Set daily priorities based on business metrics
3. Resolve conflicts between agents
4. Make high-level strategic decisions
5. Produce daily operator briefing

You operate under strict Constitutional AI principles. You reason step by step before every decision.
You always cite your confidence level. You NEVER act when confidence < 70%.

Respond ONLY with valid JSON in the exact format requested."""


class CEOAgent(BaseAgent):
    agent_id = "A1"
    agent_name = "CEO Orchestrator"
    division = "supreme"
    description = "Coordinates all 26 agents. Sets daily priorities. Produces operator briefing."

    async def orchestrate(
        self,
        business_input: str,
        portfolio_metrics: Dict = None,
        agent_reports: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Main CEO decision loop.
        Takes a business situation, reasons through it, returns decision.
        """
        # Step 1: Retrieve relevant memories
        memories = await self.retrieve_memories(business_input, limit=5)
        memory_context = ""
        if memories:
            memory_context = "\n\nRelevant past experiences:\n" + "\n".join([
                f"- Situation: {m['situation'][:100]} | Outcome: {m['outcome']}" 
                for m in memories if m.get('outcome')
            ])

        # Step 2: Build context
        context = f"""Business situation requiring CEO analysis:
{business_input}

Portfolio metrics: {json.dumps(portfolio_metrics or {}, indent=2)}
Active agent reports: {len(agent_reports or [])} reports received
{memory_context}

OKComputer Constitution:
{CONSTITUTION_TEXT}
"""

        # Step 3: Reason through the situation
        prompt = f"""{CEO_SYSTEM_PROMPT}

Analyze this business situation with full chain-of-thought reasoning.

Situation:
{context}

Respond with this exact JSON structure:
{{
  "observation": "What is happening here — 2 sentences",
  "interpretation": "What this means for the business — 2 sentences",
  "options": [
    {{"option": "Option 1", "pros": "advantages", "cons": "risks"}},
    {{"option": "Option 2", "pros": "advantages", "cons": "risks"}}
  ],
  "constitution_check": {{
    "articles_triggered": ["A3", "A7"],
    "verdict": "PASS",
    "reason": "Why this is constitutional"
  }},
  "confidence": 85,
  "decision": "The clear action to take",
  "reasoning": "Full explanation — 3 sentences",
  "agents_to_notify": ["A3", "A10", "A12"],
  "expected_outcome": "What we expect to happen",
  "operator_escalation": false,
  "escalation_reason": null
}}"""

        try:
            import anthropic
            from config import settings
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text
            result = json.loads(raw.replace("```json", "").replace("```", "").strip())

            confidence = result.get("confidence", 0)

            # Constitution A4: Confidence gate
            if not self.confidence_gate(confidence):
                result["decision"] = "HOLD — confidence below threshold. Gathering more information."
                result["operator_escalation"] = True
                result["escalation_reason"] = f"Confidence {confidence}% < 70% threshold (Constitution A4)"

            # Constitution check
            if result.get("constitution_check", {}).get("verdict") == "BLOCK":
                result["decision"] = "BLOCKED — Constitutional violation detected."
                result["operator_escalation"] = True

            # Log the decision
            await self.log_decision(
                action_type="ORCHESTRATION",
                decision=result.get("decision", ""),
                reasoning=result.get("reasoning", ""),
                input_data={"situation": business_input[:500]},
                output_data=result,
                confidence=confidence,
                constitution_result=result.get("constitution_check"),
            )

            # Store memory
            await self.store_memory(
                situation=business_input[:300],
                action_taken=result.get("decision", ""),
                importance=0.7 if result.get("operator_escalation") else 0.5,
                tags=["orchestration", "ceo_decision"]
            )

            logger.info(
                f"[A1 CEO] Decision: {result['decision'][:80]}... "
                f"| Confidence: {confidence}% | Verdict: {result.get('constitution_check', {}).get('verdict')}"
            )

            return result

        except Exception as e:
            logger.error(f"[A1 CEO] Orchestration error: {e}")
            return {
                "observation": "CEO agent encountered an error",
                "decision": "HOLD — system error. Human review required.",
                "confidence": 0,
                "operator_escalation": True,
                "escalation_reason": str(e),
                "agents_to_notify": [],
            }

    async def generate_daily_briefing(
        self,
        trading_metrics: Dict = None,
        business_metrics: Dict = None,
        agent_performance: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Produces the daily 1-page operator briefing.
        This is the one report you read every morning.
        """
        prompt = f"""{CEO_SYSTEM_PROMPT}

Generate the daily operator briefing for OKComputer.

Data:
Trading metrics: {json.dumps(trading_metrics or {}, indent=2)}
Business metrics: {json.dumps(business_metrics or {}, indent=2)}
Agent performance: {json.dumps(agent_performance or [], indent=2)}

Produce a concise, honest, actionable briefing. Respond with this JSON:
{{
  "date": "{datetime.utcnow().strftime('%Y-%m-%d')}",
  "headline": "One sentence capturing the most important thing today",
  "trading": {{
    "portfolio_pnl_today": "string",
    "trades_executed": 0,
    "win_rate": "string",
    "risk_status": "ALL CLEAR | CAUTION | ALERT"
  }},
  "business": {{
    "mrr": "string",
    "new_customers": 0,
    "churned": 0,
    "pipeline_value": "string"
  }},
  "top_risk": "The single biggest risk right now",
  "top_opportunity": "The single biggest opportunity",
  "decisions_needed": [
    "Any decision that requires the operator today"
  ],
  "agent_alerts": [
    {{"agent": "Name", "issue": "What needs attention"}}
  ],
  "constitution_health": "OPTIMAL | GOOD | REVIEW NEEDED",
  "system_intelligence_score": 87
}}"""

        try:
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text
            result = json.loads(raw.replace("```json", "").replace("```", "").strip())

            logger.info(f"[A1 CEO] Daily briefing generated: {result.get('headline', '')[:80]}")
            return result

        except Exception as e:
            logger.error(f"[A1 CEO] Daily briefing error: {e}")
            return {"error": str(e), "date": datetime.utcnow().strftime('%Y-%m-%d')}

    async def run_daily_cycle(self) -> Dict:
        """Called by scheduler every morning at 07:00 UTC"""
        logger.info("[A1 CEO] Starting daily cycle...")

        briefing = await self.generate_daily_briefing(
            trading_metrics={"status": "active", "paper_trading": True},
            business_metrics={"status": "growing"},
        )

        await self.log_decision(
            action_type="DAILY_BRIEFING",
            decision=briefing.get("headline", "Briefing generated"),
            output_data=briefing,
            confidence=90,
        )

        return briefing
