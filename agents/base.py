"""
OKComputer — Base Agent
All 27 agents inherit from this class.
Implements: Constitutional checks · Chain-of-Thought · Memory · Logging
"""
import anthropic
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger
from config import settings


CONSTITUTION = [
    {"id": "A1", "title": "Capital Preservation",  "rule": "Never risk more than the system can recover from. Survival is always prioritized over profit.", "weight": 10},
    {"id": "A2", "title": "Honest Reporting",       "rule": "Always report true performance. Never hide losses or inflate returns.", "weight": 9},
    {"id": "A3", "title": "Customer First",         "rule": "Every decision evaluated through: does this genuinely help our customer?", "weight": 9},
    {"id": "A4", "title": "Epistemic Humility",     "rule": "If confidence is below 70%, do not act. Uncertainty is information, not weakness.", "weight": 8},
    {"id": "A5", "title": "Continuous Improvement", "rule": "Never accept current performance as good enough.", "weight": 7},
    {"id": "A6", "title": "Regulatory Respect",     "rule": "No profit is worth a legal or ethical violation. Compliance is non-negotiable.", "weight": 10},
    {"id": "A7", "title": "Transparency",           "rule": "Every decision must be explainable in plain English. No black-box actions.", "weight": 9},
]

CONSTITUTION_TEXT = "\n".join(
    [f"{c['id']} ({c['title']}, weight:{c['weight']}): {c['rule']}" for c in CONSTITUTION]
)


class BaseAgent:
    """
    Foundation for all OKComputer agents.
    Implements the 4 intelligence layers:
    - Memory Layer: retrieves relevant past experiences
    - Reasoning Layer: Claude-powered chain-of-thought
    - Action Layer: executes decisions
    - Learning Layer: records outcomes for improvement
    """

    agent_id: str = "BASE"
    agent_name: str = "Base Agent"
    division: str = "system"
    description: str = "Base agent class"

    def __init__(self, db_session=None):
        self.db = db_session
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.memory_cache: List[Dict] = []
        self.performance_score: float = 80.0
        self.last_action_at: Optional[datetime] = None

    # ── CONSTITUTION CHECK ────────────────────────────────────
    async def constitution_check(
        self,
        proposed_action: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """
        Check proposed action against all 7 constitutional articles.
        Returns verdict: PASS | CAUTION | BLOCK
        """
        prompt = f"""You are the OKComputer Constitutional Validator.

Constitution:
{CONSTITUTION_TEXT}

Proposed Action by {self.agent_name}:
{proposed_action}

Context:
{context}

Evaluate this action against all 7 articles. Respond ONLY with valid JSON:
{{
  "verdict": "PASS",
  "articles_triggered": ["A1", "A4"],
  "blocking_article": null,
  "confidence": 87,
  "reasoning": "Why this passes or fails the constitution",
  "modifications_required": "Any required changes to make this action compliant"
}}

Verdicts:
- PASS: Action is constitutional. Proceed.
- CAUTION: Action has risk. Proceed with modifications.
- BLOCK: Action violates constitution. Do not proceed."""

        try:
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text
            result = json.loads(raw.replace("```json", "").replace("```", "").strip())

            # Log constitution check
            logger.info(
                f"[{self.agent_id}] Constitution check: {result['verdict']} "
                f"| Articles: {result.get('articles_triggered', [])}"
            )

            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Constitution check error: {e}")
            # Safe default — caution on error
            return {
                "verdict": "CAUTION",
                "articles_triggered": ["A4"],
                "blocking_article": None,
                "confidence": 50,
                "reasoning": f"Constitution check failed due to error: {e}. Proceeding with caution.",
                "modifications_required": "Manual review recommended."
            }

    # ── CHAIN OF THOUGHT ──────────────────────────────────────
    async def reason(
        self,
        situation: str,
        system_prompt: str,
        max_tokens: int = 1200
    ) -> Dict[str, Any]:
        """
        Core reasoning using Claude with chain-of-thought.
        Returns structured decision with full reasoning chain.
        """
        enhanced_prompt = f"""{system_prompt}

You are {self.agent_name} ({self.agent_id}), operating in the {self.division} division of OKComputer.
Your role: {self.description}

OKComputer Constitution (you must comply with all articles):
{CONSTITUTION_TEXT}

CRITICAL RULES:
1. Always reason step-by-step before deciding
2. State your confidence level (0-100%)
3. If confidence < 70%, do not act — flag for review
4. Every decision must be explainable in plain English (A7)
5. Check constitutional compliance before any action

Current situation:
{situation}

Respond with structured JSON including:
- observation: what is happening
- interpretation: what it means
- options: 2-3 possible actions
- constitution_check: which articles are relevant
- confidence: your confidence score (0-100)
- decision: the chosen action
- reasoning: why you chose this
- expected_outcome: what you predict will happen
"""

        try:
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": enhanced_prompt}]
            )
            raw = response.content[0].text

            # Try to parse as JSON, fall back to text
            try:
                result = json.loads(raw.replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                result = {
                    "observation": "Reasoning complete",
                    "decision": raw,
                    "confidence": 75,
                    "reasoning": raw,
                    "expected_outcome": "Outcome pending"
                }

            self.last_action_at = datetime.utcnow()
            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Reasoning error: {e}")
            return {
                "observation": "Reasoning failed",
                "decision": "HOLD — reasoning error",
                "confidence": 0,
                "reasoning": str(e),
                "expected_outcome": "Unknown"
            }

    # ── CONFIDENCE GATE ───────────────────────────────────────
    def confidence_gate(self, confidence: float, threshold: float = None) -> bool:
        """
        Constitution A4: Epistemic Humility
        If confidence < threshold, do NOT act.
        """
        threshold = threshold or (settings.min_confidence_threshold * 100)
        if confidence < threshold:
            logger.warning(
                f"[{self.agent_id}] Confidence gate: {confidence:.1f}% < {threshold}%. "
                f"Action blocked — Constitution A4."
            )
            return False
        return True

    # ── MEMORY RETRIEVAL ──────────────────────────────────────
    async def retrieve_memories(
        self,
        situation: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Retrieve relevant episodic memories before acting.
        This is the key to the self-learning system.
        """
        if not self.db:
            return []

        try:
            from database.models import AgentMemory
            from sqlalchemy import select

            # Simple text search — in production use vector similarity
            result = await self.db.execute(
                select(AgentMemory)
                .where(AgentMemory.agent_id == self.agent_id)
                .order_by(AgentMemory.importance_score.desc())
                .limit(limit)
            )
            memories = result.scalars().all()

            return [
                {
                    "situation": m.situation,
                    "action_taken": m.action_taken,
                    "outcome": m.outcome,
                    "lesson": m.lesson,
                    "confidence": m.confidence,
                }
                for m in memories
            ]
        except Exception as e:
            logger.error(f"[{self.agent_id}] Memory retrieval error: {e}")
            return []

    # ── STORE MEMORY ──────────────────────────────────────────
    async def store_memory(
        self,
        situation: str,
        action_taken: str,
        outcome: str = None,
        lesson: str = None,
        memory_type: str = "episodic",
        confidence: float = None,
        importance: float = 0.5,
        tags: List[str] = None
    ):
        """Store a new episodic memory for future learning"""
        if not self.db:
            return

        try:
            from database.models import AgentMemory
            memory = AgentMemory(
                agent_id=self.agent_id,
                memory_type=memory_type,
                situation=situation,
                action_taken=action_taken,
                outcome=outcome,
                lesson=lesson,
                confidence=confidence,
                importance_score=importance,
                tags=tags or [],
            )
            self.db.add(memory)
            await self.db.commit()
        except Exception as e:
            logger.error(f"[{self.agent_id}] Memory store error: {e}")

    # ── LOG DECISION ──────────────────────────────────────────
    async def log_decision(
        self,
        action_type: str,
        decision: str,
        reasoning: str = None,
        input_data: Dict = None,
        output_data: Dict = None,
        confidence: float = None,
        constitution_result: Dict = None,
    ):
        """Constitution A7: Log every decision with full reasoning"""
        if not self.db:
            logger.info(f"[{self.agent_id}] {action_type}: {decision[:100]}")
            return

        try:
            from database.models import AgentLog
            log = AgentLog(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                division=self.division,
                action_type=action_type,
                decision=decision,
                input_data=input_data or {},
                output_data=output_data or {},
                confidence_score=confidence,
                constitution_check=constitution_result,
                constitution_passed=constitution_result.get("verdict") != "BLOCK" if constitution_result else True,
                articles_triggered=constitution_result.get("articles_triggered", []) if constitution_result else [],
            )
            self.db.add(log)
            await self.db.commit()
        except Exception as e:
            logger.error(f"[{self.agent_id}] Log decision error: {e}")

    # ── DAILY CYCLE ───────────────────────────────────────────
    async def run_daily_cycle(self) -> Dict:
        """
        Override this in each agent subclass.
        This is called by the scheduler every day.
        """
        raise NotImplementedError(
            f"{self.agent_name} must implement run_daily_cycle()"
        )

    # ── STATUS ───────────────────────────────────────────────
    def get_status(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "division": self.division,
            "performance_score": self.performance_score,
            "last_action_at": self.last_action_at.isoformat() if self.last_action_at else None,
            "status": "active",
        }
