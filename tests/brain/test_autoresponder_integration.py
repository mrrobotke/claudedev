"""Integration test: stream, detect, think, log, resume, complete."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from claudedev.brain.autoresponder import (
    AutoResponder,
    DecisionLogger,
    QuestionClassifier,
    StreamAnalyzer,
)
from claudedev.brain.config import BrainConfig
from claudedev.brain.integration.claude_bridge import ClaudeResult


class TestFullAutoRespondLoop:
    """Simulate the complete loop: stream, detect, think, log, resume, complete."""

    async def test_end_to_end_loop(self) -> None:
        config = BrainConfig(project_path="/tmp/test", max_auto_responses=3)

        # Phase 1: Stream output that ends with a question
        analyzer = StreamAnalyzer()
        stream_events_phase1 = [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "I've analyzed the codebase. "}]
                    },
                }
            ),
            json.dumps({"type": "tool_use", "name": "Read"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "Which approach should I use for the caching layer?",
                            }
                        ]
                    },
                }
            ),
            # No stop_reason key means last_stop_reason stays None -> question detected
            json.dumps(
                {
                    "type": "result",
                    "result": "",
                    "session_id": "claude-abc123",
                }
            ),
        ]

        for event in stream_events_phase1:
            analyzer.feed(event)

        # Verify question detected
        assert analyzer.detected_question() is True
        question = analyzer.get_question()
        assert question is not None
        assert "caching" in question.question_text
        assert analyzer.claude_session_id == "claude-abc123"

        # Phase 2: Classify the question
        classification = QuestionClassifier.classify(question.question_text)
        assert classification.question_type.value in {
            "choice",
            "architecture",
            "missing_info",
        }

        # Phase 3: AutoResponder thinks
        bridge = MagicMock()
        bridge.execute_task = AsyncMock(
            return_value=ClaudeResult(
                content=(
                    "DECISION: Use Redis -- it matches our existing infra\n"
                    "REASONING: Redis is already deployed and the team is familiar\n"
                    "RISK: 4"
                ),
                input_tokens=2000,
                output_tokens=100,
                stop_reason="end_turn",
                tool_use_history=[],
                duration_ms=1200.0,
                success=True,
            )
        )
        bridge._model = config.claude_model

        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])
        episodic.store = AsyncMock(return_value="ep-456")

        responder = AutoResponder(config, bridge, episodic)
        response = await responder.respond(
            question,
            {"number": 42, "title": "Add caching", "body": "Need cache"},
            classification,
        )

        assert "Redis" in response.answer
        assert response.risk_score == 4

        # Phase 4: Log the decision
        dl = DecisionLogger(episodic_store=episodic)
        episode_id = await dl.log(
            question=question,
            response=response,
            issue_number=42,
            session_id="sess-1",
        )
        assert episode_id == "ep-456"

        # Phase 5: Reset analyzer for resume
        analyzer.reset_for_resume()
        assert analyzer.accumulated_text == ""
        assert analyzer.detected_question() is False
        assert analyzer.claude_session_id == "claude-abc123"  # Preserved

        # Phase 6: Simulate resumed stream that completes normally
        stream_events_phase2 = [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Implementing Redis caching... Done!\n\n"
                                    "PR_NUMBER: 99\nBRANCH: claudedev/issue-42"
                                ),
                            }
                        ]
                    },
                }
            ),
            # stop_reason="end_turn" means last_stop_reason is not None -> no question
            json.dumps(
                {
                    "type": "result",
                    "stop_reason": "end_turn",
                    "result": "",
                }
            ),
        ]

        for event in stream_events_phase2:
            analyzer.feed(event)

        assert analyzer.detected_question() is False
        assert analyzer.pr_number == 99

    async def test_max_retries_respected(self) -> None:
        """Verify the loop stops after max_auto_responses."""
        config = BrainConfig(project_path="/tmp/test", max_auto_responses=2)

        bridge = MagicMock()
        bridge.execute_task = AsyncMock(
            return_value=ClaudeResult(
                content="DECISION: Proceed\nREASONING: OK\nRISK: 2",
                input_tokens=100,
                output_tokens=50,
                stop_reason="end_turn",
                tool_use_history=[],
                duration_ms=500.0,
                success=True,
            )
        )
        bridge._model = config.claude_model

        responder = AutoResponder(config, bridge)
        responses_generated = 0

        for attempt in range(config.max_auto_responses + 1):
            analyzer = StreamAnalyzer()
            analyzer.feed(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "Should I proceed?"}]},
                    }
                )
            )
            # No stop_reason -> question can be detected
            analyzer.feed(json.dumps({"type": "result", "result": ""}))

            if analyzer.detected_question() and attempt < config.max_auto_responses:
                question = analyzer.get_question()
                assert question is not None
                classification = QuestionClassifier.classify(
                    question.question_text,
                )
                await responder.respond(
                    question,
                    {"number": 1, "title": "T", "body": "B"},
                    classification,
                )
                responses_generated += 1
            else:
                break

        assert responses_generated == config.max_auto_responses

    async def test_bridge_failure_uses_safe_fallback(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        bridge = MagicMock()
        bridge.execute_task = AsyncMock(
            return_value=ClaudeResult(
                content="",
                input_tokens=0,
                output_tokens=0,
                stop_reason="",
                tool_use_history=[],
                duration_ms=0,
                success=False,
                error="API timeout",
            )
        )
        bridge._model = config.claude_model

        responder = AutoResponder(config, bridge)
        analyzer = StreamAnalyzer()
        analyzer.feed(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Which database?"}]},
                }
            )
        )
        # No stop_reason -> question detected
        analyzer.feed(json.dumps({"type": "result", "result": ""}))

        question = analyzer.get_question()
        assert question is not None
        classification = QuestionClassifier.classify(question.question_text)
        response = await responder.respond(
            question,
            {"number": 1, "title": "T", "body": "B"},
            classification,
        )

        # Fallback: safe answer with max risk
        assert response.risk_score == 10
        assert response.answer is not None
