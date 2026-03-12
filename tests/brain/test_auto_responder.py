"""Tests for AutoResponder -- Opus 4.6 thinking + autonomous answers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from claudedev.brain.autoresponder.auto_responder import AutoResponder, AutoResponse
from claudedev.brain.autoresponder.question_classifier import (
    ClassificationResult,
    QuestionType,
)
from claudedev.brain.autoresponder.stream_analyzer import DetectedQuestion
from claudedev.brain.config import BrainConfig
from claudedev.brain.integration.claude_bridge import ClaudeResult


def _make_config() -> BrainConfig:
    return BrainConfig(project_path="/tmp/test")


def _make_question(text: str = "Which approach?") -> DetectedQuestion:
    return DetectedQuestion(
        question_text=text,
        full_context=f"Some context.\n\n{text}",
    )


def _make_classification(
    qtype: QuestionType = QuestionType.CHOICE,
    risk: int = 5,
) -> ClassificationResult:
    return ClassificationResult(question_type=qtype, risk_score=risk)


def _make_claude_result(content: str, success: bool = True) -> ClaudeResult:
    return ClaudeResult(
        content=content,
        input_tokens=1000,
        output_tokens=500,
        stop_reason="end_turn",
        tool_use_history=[],
        duration_ms=1500.0,
        success=success,
    )


class TestAutoResponseModel:
    def test_auto_response_fields(self) -> None:
        r = AutoResponse(
            answer="Use approach A",
            reasoning="Better fits project patterns",
            risk_score=5,
            decision_type=QuestionType.CHOICE,
            thinking_tokens=500,
            thinking_duration_ms=1500.0,
        )
        assert r.answer == "Use approach A"
        assert r.risk_score == 5


class TestAutoResponder:
    async def test_respond_calls_bridge(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(
            return_value=_make_claude_result(
                "DECISION: Use approach A\nREASONING: Better fit\nRISK: 5"
            )
        )
        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])

        responder = AutoResponder(config, bridge, episodic)
        response = await responder.respond(
            _make_question(),
            {"number": 42, "title": "Add feature", "body": "Details"},
            _make_classification(),
        )

        assert response.answer is not None
        assert len(response.answer) > 0
        bridge.execute_task.assert_awaited_once()

    async def test_respond_parses_decision_format(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(
            return_value=_make_claude_result(
                "DECISION: Use Redis for caching\nREASONING: Existing infra\nRISK: 3"
            )
        )
        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])

        responder = AutoResponder(config, bridge, episodic)
        response = await responder.respond(
            _make_question(),
            {"number": 1, "title": "T", "body": "B"},
            _make_classification(),
        )

        assert "Redis" in response.answer
        assert "Existing infra" in response.reasoning

    async def test_respond_handles_bridge_failure(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(return_value=_make_claude_result("", success=False))
        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])

        responder = AutoResponder(config, bridge, episodic)
        response = await responder.respond(
            _make_question(),
            {"number": 1, "title": "T", "body": "B"},
            _make_classification(),
        )

        assert response.answer is not None
        assert response.risk_score == 10

    async def test_respond_queries_episodic_memory(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(
            return_value=_make_claude_result("DECISION: Yes\nREASONING: Past success\nRISK: 2")
        )
        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])

        responder = AutoResponder(config, bridge, episodic)
        await responder.respond(
            _make_question("Should I proceed?"),
            {"number": 42, "title": "Feature", "body": "Details"},
            _make_classification(QuestionType.CONFIRMATION, 2),
        )

        episodic.search.assert_awaited_once()

    async def test_respond_without_episodic_store(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(
            return_value=_make_claude_result("DECISION: Yes\nREASONING: Fine\nRISK: 2")
        )

        responder = AutoResponder(config, bridge, episodic_store=None)
        response = await responder.respond(
            _make_question(),
            {"number": 1, "title": "T", "body": "B"},
            _make_classification(),
        )
        assert response.answer is not None
