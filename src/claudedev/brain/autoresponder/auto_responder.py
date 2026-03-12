"""AutoResponder -- calls Opus 4.6 to autonomously answer Claude Code questions."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from claudedev.brain.autoresponder.question_classifier import (
        ClassificationResult,
        QuestionType,
    )
    from claudedev.brain.autoresponder.stream_analyzer import DetectedQuestion
    from claudedev.brain.config import BrainConfig
    from claudedev.brain.integration.claude_bridge import ClaudeBridge
    from claudedev.brain.memory.episodic import EpisodicStore

logger = structlog.get_logger(__name__)

_DECISION_RE = re.compile(r"DECISION:\s*(.+?)(?:\n|$)", re.DOTALL)
_REASONING_RE = re.compile(r"REASONING:\s*(.+?)(?:\n|$)", re.DOTALL)
_RISK_RE = re.compile(r"RISK:\s*(\d+)")

_SYSTEM_PROMPT = (
    "You are the autonomous Product Owner for ClaudeDev. A Claude Code session "
    "implementing a GitHub issue has stopped with a question.\n\n"
    "Respond with a clear, decisive answer. Do NOT ask follow-up questions.\n"
    "Choose the approach that best fits:\n"
    "- Project conventions and existing patterns\n"
    "- The issue requirements\n"
    "- Past decisions that worked\n\n"
    "Format:\n"
    "DECISION: <your answer in 1-3 sentences>\n"
    "REASONING: <why, in 1-2 sentences>\n"
    "RISK: <1-10>"
)


@dataclass(frozen=True)
class AutoResponse:
    """The result of autonomous thinking."""

    answer: str
    reasoning: str
    risk_score: int
    decision_type: QuestionType
    thinking_tokens: int
    thinking_duration_ms: float


class AutoResponder:
    """Receives a DetectedQuestion, assembles context, calls Opus 4.6."""

    def __init__(
        self,
        config: BrainConfig,
        claude_bridge: ClaudeBridge,
        episodic_store: EpisodicStore | None = None,
    ) -> None:
        self._config = config
        self._bridge = claude_bridge
        self._episodic = episodic_store

    async def respond(
        self,
        question: DetectedQuestion,
        issue_context: dict[str, Any],
        classification: ClassificationResult,
    ) -> AutoResponse:
        """Think about the question and produce a decisive answer."""
        start = time.perf_counter()

        past_decisions = ""
        if self._episodic:
            try:
                keywords = f"{issue_context.get('title', '')} {question.question_text}"
                episodes = await self._episodic.search(keywords, limit=3)
                if episodes:
                    parts = []
                    for ep in episodes:
                        parts.append(
                            f"- Task: {ep.task}\n  Approach: {ep.approach}\n  Outcome: {ep.outcome}"
                        )
                    past_decisions = "\n".join(parts)
            except Exception:
                logger.warning("episodic_search_failed", exc_info=True)

        task_prompt = (
            f"ISSUE: #{issue_context.get('number', '?')} "
            f"-- {issue_context.get('title', 'Unknown')}\n"
            f"BODY: {str(issue_context.get('body', ''))[:3000]}\n"
        )
        if past_decisions:
            task_prompt += f"\nPAST DECISIONS:\n{past_decisions}\n"
        task_prompt += (
            f'\nClaude\'s question: "{question.question_text}"\n'
            f"Question type: {classification.question_type.value}\n"
            f"Full context:\n{question.full_context[-5000:]}\n"
        )

        original_model = self._bridge._model
        self._bridge._model = self._config.thinking_model
        try:
            result = await self._bridge.execute_task(
                task=task_prompt,
                system_prompt=_SYSTEM_PROMPT,
            )
        finally:
            self._bridge._model = original_model

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        if not result.success:
            logger.error("auto_responder_bridge_failed", error=result.error)
            return AutoResponse(
                answer="Proceed with the most conservative approach.",
                reasoning="AutoResponder thinking failed -- defaulting to safe option.",
                risk_score=10,
                decision_type=classification.question_type,
                thinking_tokens=0,
                thinking_duration_ms=elapsed_ms,
            )

        return self._parse_response(
            result.content,
            result.output_tokens,
            elapsed_ms,
            classification,
        )

    def _parse_response(
        self,
        content: str,
        output_tokens: int,
        duration_ms: float,
        classification: ClassificationResult,
    ) -> AutoResponse:
        """Parse the DECISION/REASONING/RISK format from the thinking model."""
        decision_match = _DECISION_RE.search(content)
        reasoning_match = _REASONING_RE.search(content)
        risk_match = _RISK_RE.search(content)

        answer = decision_match.group(1).strip() if decision_match else content.strip()
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        risk = int(risk_match.group(1)) if risk_match else classification.risk_score
        risk = max(1, min(risk, 10))

        return AutoResponse(
            answer=answer,
            reasoning=reasoning,
            risk_score=risk,
            decision_type=classification.question_type,
            thinking_tokens=output_tokens,
            thinking_duration_ms=duration_ms,
        )
