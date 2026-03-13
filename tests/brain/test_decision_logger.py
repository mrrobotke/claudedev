"""Tests for DecisionLogger -- episodic + dashboard + structlog logging."""

from __future__ import annotations

from unittest.mock import AsyncMock

from claudedev.brain.autoresponder.auto_responder import AutoResponse
from claudedev.brain.autoresponder.decision_logger import DecisionLogger
from claudedev.brain.autoresponder.question_classifier import QuestionType
from claudedev.brain.autoresponder.stream_analyzer import DetectedQuestion


def _make_response(risk: int = 5) -> AutoResponse:
    return AutoResponse(
        answer="Use approach A",
        reasoning="Better fit",
        risk_score=risk,
        decision_type=QuestionType.CHOICE,
        thinking_tokens=500,
        thinking_duration_ms=1500.0,
    )


def _make_question(text: str = "Which approach?") -> DetectedQuestion:
    return DetectedQuestion(
        question_text=text,
        full_context=f"Context\n\n{text}",
    )


class TestDecisionLogger:
    async def test_logs_to_episodic_store(self) -> None:
        episodic = AsyncMock()
        episodic.store = AsyncMock(return_value="ep-123")
        dl = DecisionLogger(episodic_store=episodic)

        await dl.log(
            question=_make_question(),
            response=_make_response(),
            issue_number=42,
            session_id="sess-1",
        )

        episodic.store.assert_awaited_once()
        stored_episode = episodic.store.call_args[0][0]
        assert "approach A" in stored_episode.approach
        assert stored_episode.task.startswith("auto_decision")

    async def test_logs_without_episodic_store(self) -> None:
        dl = DecisionLogger(episodic_store=None)
        await dl.log(
            question=_make_question(),
            response=_make_response(),
            issue_number=42,
            session_id="sess-1",
        )

    async def test_broadcasts_to_ws_manager(self) -> None:
        ws = AsyncMock()
        ws.broadcast_activity = AsyncMock()
        dl = DecisionLogger(ws_manager=ws)

        await dl.log(
            question=_make_question(),
            response=_make_response(),
            issue_number=42,
            session_id="sess-1",
        )

        assert ws.broadcast_activity.await_count >= 1

    async def test_high_risk_flagged(self) -> None:
        episodic = AsyncMock()
        episodic.store = AsyncMock(return_value="ep-123")
        dl = DecisionLogger(episodic_store=episodic)

        await dl.log(
            question=_make_question(),
            response=_make_response(risk=8),
            issue_number=42,
            session_id="sess-1",
        )

        stored = episodic.store.call_args[0][0]
        assert "HIGH_RISK" in stored.outcome or stored.confidence < 0.5

    async def test_episodic_store_failure_does_not_raise(self) -> None:
        episodic = AsyncMock()
        episodic.store = AsyncMock(side_effect=RuntimeError("DB error"))
        dl = DecisionLogger(episodic_store=episodic)

        await dl.log(
            question=_make_question(),
            response=_make_response(),
            issue_number=42,
            session_id="sess-1",
        )
