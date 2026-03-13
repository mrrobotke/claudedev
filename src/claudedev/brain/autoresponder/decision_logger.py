"""DecisionLogger -- records auto-decisions to episodic memory, dashboard, and structlog."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from claudedev.brain.models import EpisodicMemory

if TYPE_CHECKING:
    from claudedev.brain.autoresponder.auto_responder import AutoResponse
    from claudedev.brain.autoresponder.stream_analyzer import DetectedQuestion
    from claudedev.brain.memory.episodic import EpisodicStore
    from claudedev.engines.websocket_manager import WebSocketManager

logger = structlog.get_logger(__name__)

_HIGH_RISK_THRESHOLD = 7


class DecisionLogger:
    """Writes auto-decisions to three destinations: episodic memory, dashboard, structlog."""

    def __init__(
        self,
        episodic_store: EpisodicStore | None = None,
        ws_manager: WebSocketManager | None = None,
    ) -> None:
        self._episodic = episodic_store
        self._ws = ws_manager

    async def log(
        self,
        question: DetectedQuestion,
        response: AutoResponse,
        issue_number: int,
        session_id: str,
    ) -> str | None:
        """Log an auto-decision. Returns the episodic memory ID if stored."""
        is_high_risk = response.risk_score >= _HIGH_RISK_THRESHOLD

        # 1. structlog -- always
        logger.info(
            "auto_decision",
            issue_number=issue_number,
            session_id=session_id,
            question_type=response.decision_type.value,
            risk_score=response.risk_score,
            high_risk=is_high_risk,
            answer=response.answer[:200],
            reasoning=response.reasoning[:200],
            thinking_tokens=response.thinking_tokens,
            thinking_duration_ms=round(response.thinking_duration_ms, 1),
        )

        # 2. Episodic memory
        episode_id: str | None = None
        if self._episodic:
            try:
                outcome = response.answer
                if is_high_risk:
                    outcome = f"[HIGH_RISK] {outcome}"

                episode = EpisodicMemory(
                    task=(f"auto_decision:issue-{issue_number}:{response.decision_type.value}"),
                    approach=(f"Q: {question.question_text[:500]}\nA: {response.answer[:500]}"),
                    outcome=outcome,
                    tools_used=["AutoResponder", "ClaudeBridge"],
                    confidence=max(0.1, 1.0 - (response.risk_score / 10.0)),
                )
                episode_id = await self._episodic.store(episode)
            except Exception:
                logger.warning("decision_logger_episodic_failed", exc_info=True)

        # 3. Dashboard WebSocket
        if self._ws:
            try:
                await self._ws.broadcast_activity(
                    session_id,
                    "auto_response_decision",
                    {
                        "question": question.question_text[:200],
                        "answer": response.answer[:200],
                        "reasoning": response.reasoning[:200],
                        "risk_score": response.risk_score,
                        "high_risk": is_high_risk,
                        "question_type": response.decision_type.value,
                        "thinking_tokens": response.thinking_tokens,
                        "thinking_duration_ms": round(
                            response.thinking_duration_ms,
                            1,
                        ),
                    },
                )
            except Exception:
                logger.warning("decision_logger_ws_failed", exc_info=True)

        return episode_id
