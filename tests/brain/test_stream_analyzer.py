"""Tests for StreamAnalyzer -- real-time question detection from stream-json."""

from __future__ import annotations

import json

from claudedev.brain.autoresponder.stream_analyzer import StreamAnalyzer


def _make_assistant_event(text: str) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": text}]},
        }
    )


def _make_tool_use_event(name: str = "Read") -> str:
    return json.dumps({"type": "tool_use", "name": name})


def _make_result_line(stop_reason: str | None = None, result: str = "") -> str:
    event: dict[str, object] = {"type": "result", "result": result}
    if stop_reason is not None:
        event["stop_reason"] = stop_reason
    return json.dumps(event)


class TestFeedAccumulation:
    def test_accumulates_assistant_text(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Hello "))
        sa.feed(_make_assistant_event("world"))
        assert sa.accumulated_text == "Hello world"

    def test_tracks_tool_use(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_tool_use_event("Read"))
        assert sa.has_tool_use is True

    def test_extracts_pr_number(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Done!\n\nPR_NUMBER: 42\nBRANCH: claudedev/issue-42"))
        assert sa.pr_number == 42

    def test_captures_stop_reason(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_result_line(stop_reason="end_turn"))
        assert sa.last_stop_reason == "end_turn"

    def test_null_stop_reason(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_result_line(stop_reason=None))
        assert sa.last_stop_reason is None

    def test_ignores_invalid_json(self) -> None:
        sa = StreamAnalyzer()
        sa.feed("not json at all")
        assert sa.accumulated_text == ""

    def test_ignores_empty_lines(self) -> None:
        sa = StreamAnalyzer()
        sa.feed("")
        sa.feed("   ")
        assert sa.accumulated_text == ""


class TestQuestionDetection:
    def test_detects_question_with_null_stop_reason(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Which approach should I use?"))
        sa.feed(_make_result_line(stop_reason=None))
        assert sa.detected_question() is True

    def test_no_question_with_end_turn(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Which approach should I use?"))
        sa.feed(_make_result_line(stop_reason="end_turn"))
        assert sa.detected_question() is False

    def test_no_question_with_pr_number(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Which approach?\n\nPR_NUMBER: 42"))
        sa.feed(_make_result_line(stop_reason=None))
        assert sa.detected_question() is False

    def test_no_question_without_interrogative(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("I have completed the implementation."))
        sa.feed(_make_result_line(stop_reason=None))
        assert sa.detected_question() is False

    def test_detects_interrogative_patterns(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Would you like me to proceed?"))
        sa.feed(_make_result_line(stop_reason=None))
        assert sa.detected_question() is True

    def test_detects_do_you_want(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Do you want me to use Redis?"))
        sa.feed(_make_result_line(stop_reason=None))
        assert sa.detected_question() is True

    def test_missing_stop_reason_key_treated_as_null(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Which approach?"))
        sa.feed(json.dumps({"type": "result", "result": ""}))
        assert sa.detected_question() is True


class TestGetQuestion:
    def test_returns_detected_question(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Some context.\n\nWhich approach should I use?"))
        sa.feed(_make_result_line(stop_reason=None))
        q = sa.get_question()
        assert q is not None
        assert "Which approach" in q.question_text
        assert "Some context" in q.full_context

    def test_returns_none_when_no_question(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("All done."))
        sa.feed(_make_result_line(stop_reason="end_turn"))
        assert sa.get_question() is None


class TestResetForResume:
    def test_clears_text_but_preserves_session_id(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Question?"))
        sa.feed(_make_result_line(stop_reason=None))
        sa.reset_for_resume()
        assert sa.accumulated_text == ""
        assert sa.last_stop_reason is None
        assert sa.has_tool_use is False

    def test_question_not_detected_after_reset(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_assistant_event("Question?"))
        sa.feed(_make_result_line(stop_reason=None))
        sa.reset_for_resume()
        assert sa.detected_question() is False


class TestClaudeSessionIdExtraction:
    def test_extracts_session_id_from_result(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(
            json.dumps(
                {
                    "type": "result",
                    "result": "",
                    "session_id": "abc-123-def",
                }
            )
        )
        assert sa.claude_session_id == "abc-123-def"

    def test_none_when_no_session_id(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_result_line(stop_reason="end_turn"))
        assert sa.claude_session_id is None
