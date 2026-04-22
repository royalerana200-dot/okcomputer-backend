"""
OKComputer — Sales Intelligence Agent (A10)
100 qualified leads/day. Hyper-personalized outreach.
Learns from every conversion and rejection.
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger
from agents.base import BaseAgent


SALES_SYSTEM = """You are the Sales Intelligence Agent (A10) of OKComputer.

Your mission: Find traders and small funds who need autonomous trading intelligence.
You operate with strict ethical standards — Constitution A3 (Customer First) governs everything.
You never overpromise. You never mislead. You sell only what genuinely helps the customer.

You are expert in:
- Identifying high-quality leads from trader profiles
- Writing personalized outreach that resonates
- Understanding trader pain points deeply
- Qualifying leads by their likelihood to convert and benefit

Always respond with valid JSON."""


class SalesAgent(BaseAgent):
    agent_id = "A10"
    agent_name = "Sales Intelligence"
    division = "business"
    description = "100 qualified leads/day. Hyper-personalized outreach. Learns from rejections."

    async def score_lead(self, lead_profile: Dict) -> Dict[str, Any]:
        """
        Score a lead 0-100 based on fit and conversion probability.
        Only pursue leads scoring 70+.
        """
        prompt = f"""{SALES_SYSTEM}

Score this potential OKComputer customer:

Lead Profile:
{json.dumps(lead_profile, indent=2)}

OKComputer is: An autonomous AI trading agent SaaS. Plans from $99-$999/mo.
Best customers: Active crypto/stock traders, small funds, algorithmic trading enthusiasts.

Respond ONLY with valid JSON:
{{
  "score": 85,
  "tier": "HOT|WARM|COLD|DISQUALIFIED",
  "reasoning": "2-sentence explanation of score",
  "pain_points": ["Specific pain this person likely has", "Another pain point"],
  "best_angle": "The single most compelling angle for this specific person",
  "estimated_ltv": 2400,
  "disqualification_reason": null
}}"""

        raw = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        result_text = raw.content[0].text
        result = json.loads(result_text.replace("```json", "").replace("```", "").strip())

        await self.log_decision(
            action_type="LEAD_SCORING",
            decision=f"Score: {result['score']} | Tier: {result['tier']}",
            input_data=lead_profile,
            output_data=result,
            confidence=result["score"],
        )

        return result

    async def write_outreach(
        self,
        lead_profile: Dict,
        score_result: Dict,
        channel: str = "email",
    ) -> Dict[str, Any]:
        """
        Write hyper-personalized outreach message.
        Constitution A3: Only send if it genuinely helps the recipient.
        """
        # Constitution check — don't spam low-quality leads
        if score_result.get("score", 0) < 70:
            return {
                "approved": False,
                "reason": "Lead score below 70 — Constitution A3: not worth their time",
            }

        prompt = f"""{SALES_SYSTEM}

Write a {channel} outreach message for this lead.

Lead Profile: {json.dumps(lead_profile, indent=2)}
Lead Score: {score_result.get('score')} | Tier: {score_result.get('tier')}
Their Pain Points: {score_result.get('pain_points', [])}
Best Angle: {score_result.get('best_angle', '')}

OKComputer Value Prop:
- Autonomous AI trading agent — works 24/7 without you
- 27 AI agents managing trading, risk, and business
- Constitutional AI — capital preservation is non-negotiable
- Starts with paper trading — zero risk to learn
- Plans from $99/month

RULES:
- NO generic templates. Every word must feel written for THIS person.
- Maximum 4 sentences for cold outreach
- Lead with their pain, not our product
- Include ONE specific, credible claim
- End with a soft, low-commitment CTA
- Constitution A2: Do not exaggerate results or make guarantees

Respond with valid JSON:
{{
  "subject": "Email subject line (email only)",
  "message": "The full outreach message",
  "cta": "The specific call to action",
  "follow_up_day": 3,
  "personalization_hooks": ["What made this message specific to this person"]
}}"""

        raw = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        result = json.loads(raw.content[0].text.replace("```json", "").replace("```", "").strip())
        result["approved"] = True
        result["lead_score"] = score_result.get("score")

        await self.log_decision(
            action_type="OUTREACH_WRITTEN",
            decision=f"Outreach for {lead_profile.get('name', 'Unknown')} via {channel}",
            output_data=result,
            confidence=score_result.get("score"),
        )

        return result

    async def analyze_rejection(self, outreach_sent: str, rejection_response: str) -> Dict:
        """
        Learn from every rejection.
        Constitution A5: Never stop improving.
        """
        prompt = f"""{SALES_SYSTEM}

Analyze this rejection and extract learnings for future outreach.

Outreach we sent:
{outreach_sent}

Their response (rejection):
{rejection_response}

Respond with valid JSON:
{{
  "rejection_type": "NOT_INTERESTED|WRONG_TIMING|PRICE_OBJECTION|TRUST_ISSUE|COMPETITOR|NO_RESPONSE",
  "root_cause": "Why they really said no",
  "outreach_weakness": "What was weak about our message",
  "lesson": "Specific change to make in future outreach",
  "objection_handler": "How to address this objection if it comes up again",
  "reachout_in_days": 30
}}"""

        raw = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        result = json.loads(raw.content[0].text.replace("```json", "").replace("```", "").strip())

        # Store as episodic memory for future improvement
        await self.store_memory(
            situation=f"Rejection after outreach: {outreach_sent[:200]}",
            action_taken="Sent outreach message",
            outcome=f"Rejection: {rejection_response[:200]}",
            lesson=result.get("lesson"),
            memory_type="episodic",
            importance=0.8,  # Rejections are high-value learning
            tags=["rejection", result.get("rejection_type", "unknown")],
        )

        return result

    async def generate_daily_targets(self, target_count: int = 20) -> Dict[str, Any]:
        """
        Generate daily lead targeting strategy.
        Called by CEO Agent during daily cycle.
        """
        # Retrieve past learnings
        memories = await self.retrieve_memories("lead generation and outreach strategy", limit=10)
        learning_context = "\n".join([
            f"- {m['lesson']}" for m in memories if m.get("lesson")
        ]) or "No specific learnings yet — building baseline."

        prompt = f"""{SALES_SYSTEM}

Generate today's lead targeting strategy for OKComputer.

Target: {target_count} qualified leads today
Past learnings from memory:
{learning_context}

Best performing channels historically: Twitter/X trader communities, 
Reddit r/algotrading r/CryptoTechnology, LinkedIn quant finance groups,
Discord trading servers.

Respond with valid JSON:
{{
  "daily_target": {target_count},
  "channel_breakdown": {{
    "twitter_x": 8,
    "linkedin": 5,
    "reddit": 4,
    "discord": 3
  }},
  "target_profiles": [
    {{"profile": "Description of ideal target", "why": "Why they're a fit", "channel": "best channel"}},
    {{"profile": "Another profile", "why": "Why", "channel": "channel"}}
  ],
  "outreach_theme_today": "The unifying angle for today's outreach",
  "avoid_today": "What to avoid based on past learnings",
  "expected_responses": 3,
  "expected_conversions": 0.5
}}"""

        raw = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}]
        )
        result = json.loads(raw.content[0].text.replace("```json", "").replace("```", "").strip())
        logger.info(f"[A10 Sales] Daily targets: {result.get('daily_target')} leads | Theme: {result.get('outreach_theme_today', '')[:60]}")
        return result

    async def run_daily_cycle(self) -> Dict:
        targets = await self.generate_daily_targets()
        return {"status": "Sales cycle complete", "targets": targets}
