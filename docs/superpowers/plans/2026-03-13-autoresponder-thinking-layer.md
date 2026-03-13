# AutoResponder + Thinking Layer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Claude Code stops mid-implementation to ask a question, detect it in real-time via stream analysis, think autonomously using Opus 4.6, and resume the session with a decisive answer — no human in the loop.

**Architecture:** Four new modules in `src/claudedev/brain/autoresponder/`: StreamAnalyzer consumes stream-json events and detects questions; QuestionClassifier assigns type + risk; AutoResponder calls Opus 4.6 via ClaudeBridge for a decisive answer; DecisionLogger records to episodic memory + dashboard + structlog. The TeamEngine gains an outer retry loop: stream, detect, think, resume, continue (max 5 loops).

**Tech Stack:** Python 3.13, async throughout, Pydantic v2 models, Anthropic API (Opus 4.6 via ClaudeBridge), aiosqlite (episodic store), structlog, pytest + pytest-asyncio

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/claudedev/brain/autoresponder/__init__.py` | Create | Package exports: StreamAnalyzer, AutoResponder, QuestionClassifier, DecisionLogger |
| `src/claudedev/brain/autoresponder/stream_analyzer.py` | Create | Real-time question detection from stream-json events |
| `src/claudedev/brain/autoresponder/question_classifier.py` | Create | Question type classification + risk scoring |
| `src/claudedev/brain/autoresponder/auto_responder.py` | Create | Opus 4.6 thinking via ClaudeBridge, context assembly |
| `src/claudedev/brain/autoresponder/decision_logger.py` | Create | Log decisions to episodic store + WebSocket + structlog |
| `src/claudedev/brain/config.py` | Modify | Add thinking_model, max_auto_responses, auto_respond_enabled, max_thinking_tokens |
| `src/claudedev/integrations/claude_sdk.py` | Modify | Add resume_session() method |
| `src/claudedev/engines/team_engine.py` | Modify | Wire auto-respond loop around streaming |
| `tests/brain/test_stream_analyzer.py` | Create | StreamAnalyzer unit tests |
| `tests/brain/test_question_classifier.py` | Create | QuestionClassifier parametric tests |
| `tests/brain/test_auto_responder.py` | Create | AutoResponder unit tests (mocked ClaudeBridge) |
| `tests/brain/test_decision_logger.py` | Create | DecisionLogger unit tests |
| `tests/test_resume_session.py` | Create | resume_session CLI integration tests |

---

## Chunk 1: BrainConfig Extension + QuestionClassifier

### Task 1: Extend BrainConfig with AutoResponder fields

**Files:**
- Modify: `src/claudedev/brain/config.py:11-75`
- Test: `tests/brain/test_config.py` (existing)

- [ ] **Step 1: Write the failing tests**

Add to `tests/brain/test_config.py`:

```python
class TestAutoResponderConfig:
    def test_default_thinking_model(self) -> None:
        cfg = BrainConfig(project_path="/tmp/test")
        assert cfg.thinking_model == "claude-opus-4-6"

    def test_default_max_auto_responses(self) -> None:
        cfg = BrainConfig(project_path="/tmp/test")
        assert cfg.max_auto_responses == 5

    def test_default_auto_respond_enabled(self) -> None:
        cfg = BrainConfig(project_path="/tmp/test")
        assert cfg.auto_respond_enabled is True

    def test_default_max_thinking_tokens(self) -> None:
        cfg = BrainConfig(project_path="/tmp/test")
        assert cfg.max_thinking_tokens == 50_000

    def test_max_auto_responses_bounds(self) -> None:
        cfg = BrainConfig(project_path="/tmp/test", max_auto_responses=0)
        assert cfg.max_auto_responses == 0

        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp/test", max_auto_responses=-1)

        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp/test", max_auto_responses=21)

    def test_max_thinking_tokens_bounds(self) -> None:
        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp/test", max_thinking_tokens=999)

        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp/test", max_thinking_tokens=200_001)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/brain/test_config.py::TestAutoResponderConfig -v`
Expected: FAIL -- attributes don't exist yet

- [ ] **Step 3: Add the four new fields to BrainConfig**

In `src/claudedev/brain/config.py`, add after `log_level` field (line 61):

```python
    thinking_model: str = Field(
        default="claude-opus-4-6",
        description="Model ID for autonomous thinking (AutoResponder)",
    )
    max_auto_responses: int = Field(
        default=5,
        ge=0,
        le=20,
        description="Maximum auto-response loops per session (prevents infinite loops)",
    )
    auto_respond_enabled: bool = Field(
        default=True,
        description="Whether the AutoResponder is active",
    )
    max_thinking_tokens: int = Field(
        default=50_000,
        ge=1000,
        le=200_000,
        description="Maximum tokens for each AutoResponder thinking call",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/brain/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/claudedev/brain/config.py tests/brain/test_config.py
git commit -m "feat(brain): add AutoResponder config fields to BrainConfig"
```

---

### Task 2: QuestionClassifier -- question type + risk scoring

**Files:**
- Create: `src/claudedev/brain/autoresponder/__init__.py`
- Create: `src/claudedev/brain/autoresponder/question_classifier.py`
- Create: `tests/brain/test_question_classifier.py`

- [ ] **Step 1: Create the package init**

Create `src/claudedev/brain/autoresponder/__init__.py`:

```python
"""AutoResponder -- autonomous thinking layer for unattended Claude Code sessions."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/brain/test_question_classifier.py`:

```python
"""Tests for QuestionClassifier -- question type + risk scoring."""

from __future__ import annotations

import pytest

from claudedev.brain.autoresponder.question_classifier import (
    QuestionClassifier,
    QuestionType,
)


class TestQuestionType:
    def test_all_types_defined(self) -> None:
        expected = {"confirmation", "choice", "missing_info", "permission",
                    "scope_expansion", "architecture", "unknown"}
        assert {t.value for t in QuestionType} == expected


class TestClassifyConfirmation:
    @pytest.mark.parametrize("text", [
        "Should I proceed with the implementation?",
        "Shall I continue?",
        "Should I go ahead and create the PR?",
    ])
    def test_confirmation_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.CONFIRMATION

    def test_confirmation_risk_range(self) -> None:
        result = QuestionClassifier.classify("Should I proceed?")
        assert 2 <= result.risk_score <= 4


class TestClassifyChoice:
    @pytest.mark.parametrize("text", [
        "Should I use approach A or approach B?",
        "Which approach would you prefer?",
        "Option 1: SQLite, Option 2: PostgreSQL. Which one?",
    ])
    def test_choice_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.CHOICE

    def test_choice_risk_range(self) -> None:
        result = QuestionClassifier.classify("Approach A or B?")
        assert 4 <= result.risk_score <= 7


class TestClassifyMissingInfo:
    @pytest.mark.parametrize("text", [
        "What should the function name be?",
        "What is the expected return type?",
        "What database table should this use?",
    ])
    def test_missing_info_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.MISSING_INFO


class TestClassifyPermission:
    @pytest.mark.parametrize("text", [
        "Can I modify this file?",
        "Is it okay to change the API contract?",
        "May I update the migration?",
    ])
    def test_permission_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.PERMISSION

    def test_permission_risk_range(self) -> None:
        result = QuestionClassifier.classify("Can I modify this file?")
        assert 2 <= result.risk_score <= 3


class TestClassifyScopeExpansion:
    @pytest.mark.parametrize("text", [
        "Should I also refactor the helper functions?",
        "Would you like me to also add logging?",
        "Should I also fix the related tests?",
    ])
    def test_scope_expansion_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.SCOPE_EXPANSION

    def test_scope_expansion_risk_range(self) -> None:
        result = QuestionClassifier.classify("Should I also refactor?")
        assert 7 <= result.risk_score <= 9


class TestClassifyArchitecture:
    @pytest.mark.parametrize("text", [
        "Which database should I use for this?",
        "Should I use the repository pattern or direct queries?",
        "Which library should I use for HTTP requests?",
    ])
    def test_architecture_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.ARCHITECTURE


class TestRiskModifiers:
    def test_delete_keyword_adds_risk(self) -> None:
        base = QuestionClassifier.classify("Should I proceed?")
        modified = QuestionClassifier.classify("Should I proceed and delete the old files?")
        assert modified.risk_score >= base.risk_score + 1

    def test_dependency_keyword_adds_risk(self) -> None:
        base = QuestionClassifier.classify("Which approach?")
        modified = QuestionClassifier.classify("Should I add a new dependency for this?")
        assert modified.risk_score >= base.risk_score + 1

    def test_risk_capped_at_10(self) -> None:
        result = QuestionClassifier.classify(
            "Should I also refactor, delete the migration, and add a new dependency?"
        )
        assert result.risk_score <= 10


class TestUnknownFallback:
    def test_non_question_returns_unknown(self) -> None:
        result = QuestionClassifier.classify("I have completed the implementation.")
        assert result.question_type == QuestionType.UNKNOWN
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/brain/test_question_classifier.py -v`
Expected: FAIL -- module doesn't exist

- [ ] **Step 4: Implement QuestionClassifier**

Create `src/claudedev/brain/autoresponder/question_classifier.py`:

```python
"""Question classification and risk scoring for detected questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class QuestionType(StrEnum):
    CONFIRMATION = "confirmation"
    CHOICE = "choice"
    MISSING_INFO = "missing_info"
    PERMISSION = "permission"
    SCOPE_EXPANSION = "scope_expansion"
    ARCHITECTURE = "architecture"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassificationResult:
    """Result of classifying a detected question."""

    question_type: QuestionType
    risk_score: int  # 1-10


# Pattern tuples: (compiled regex, question type, base risk)
_PATTERNS: list[tuple[re.Pattern[str], QuestionType, int]] = [
    # Scope expansion -- must come before confirmation ("should I also")
    (re.compile(r"\bshould I also\b|\bwould you like me to also\b", re.I),
     QuestionType.SCOPE_EXPANSION, 7),
    # Architecture -- database, pattern, library choices
    (re.compile(r"\bwhich (database|pattern|library|framework)\b|\brepository pattern\b", re.I),
     QuestionType.ARCHITECTURE, 6),
    # Choice -- "A or B", "which approach", "option 1"
    (re.compile(
        r"\bapproach [A-Z]\b|\bor\b.+\?\s*$|\bwhich (approach|option|one)\b|\boption \d\b",
        re.I,
    ), QuestionType.CHOICE, 4),
    # Permission -- "can I", "may I", "is it okay"
    (re.compile(r"\bcan I\b|\bmay I\b|\bis it (okay|ok) to\b", re.I),
     QuestionType.PERMISSION, 2),
    # Missing info -- "what should", "what is the"
    (re.compile(r"\bwhat (should|is the|are the|would)\b", re.I),
     QuestionType.MISSING_INFO, 3),
    # Confirmation -- "should I proceed", "shall I continue"
    (re.compile(r"\bshould I (proceed|continue|go ahead|create|start)\b|\bshall I\b", re.I),
     QuestionType.CONFIRMATION, 2),
]

_RISK_KEYWORDS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(delete|remove|drop|migration)\b", re.I), 1),
    (re.compile(r"\boutside\b.+\bscope\b|\bother file", re.I), 1),
    (re.compile(r"\b(add|new|install)\b.+\bdependenc", re.I), 2),
]


class QuestionClassifier:
    """Classifies detected questions by type and risk. Stateless, all static."""

    @staticmethod
    def classify(question_text: str) -> ClassificationResult:
        """Classify a question string into a type with a risk score.

        Uses pattern matching. Returns UNKNOWN for non-questions.
        """
        question_type = QuestionType.UNKNOWN
        base_risk = 1

        for pattern, qtype, risk in _PATTERNS:
            if pattern.search(question_text):
                question_type = qtype
                base_risk = risk
                break

        # Apply risk modifiers
        modifier = 0
        for kw_pattern, delta in _RISK_KEYWORDS:
            if kw_pattern.search(question_text):
                modifier += delta

        final_risk = min(base_risk + modifier, 10)
        return ClassificationResult(question_type=question_type, risk_score=final_risk)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/brain/test_question_classifier.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run ruff + mypy**

Run: `ruff check src/claudedev/brain/autoresponder/ tests/brain/test_question_classifier.py && mypy src/claudedev/brain/autoresponder/`
Expected: Clean

- [ ] **Step 7: Commit**

```bash
git add src/claudedev/brain/autoresponder/ tests/brain/test_question_classifier.py
git commit -m "feat(brain): add QuestionClassifier with type + risk scoring"
```

---

## Chunk 2: StreamAnalyzer

### Task 3: StreamAnalyzer -- real-time question detection from stream-json

**Files:**
- Create: `src/claudedev/brain/autoresponder/stream_analyzer.py`
- Create: `tests/brain/test_stream_analyzer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/brain/test_stream_analyzer.py`:

```python
"""Tests for StreamAnalyzer -- real-time question detection from stream-json."""

from __future__ import annotations

import json

import pytest

from claudedev.brain.autoresponder.stream_analyzer import StreamAnalyzer


def _make_assistant_event(text: str) -> str:
    return json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    })


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
        # Result event without stop_reason key at all
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
        sa.feed(json.dumps({
            "type": "result",
            "result": "",
            "session_id": "abc-123-def",
        }))
        assert sa.claude_session_id == "abc-123-def"

    def test_none_when_no_session_id(self) -> None:
        sa = StreamAnalyzer()
        sa.feed(_make_result_line(stop_reason="end_turn"))
        assert sa.claude_session_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/brain/test_stream_analyzer.py -v`
Expected: FAIL -- module doesn't exist

- [ ] **Step 3: Implement StreamAnalyzer**

Create `src/claudedev/brain/autoresponder/stream_analyzer.py`:

```python
"""Real-time question detection from Claude Code stream-json output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

_PR_NUMBER_PATTERN = re.compile(r"PR_NUMBER:\s*(\d+)")
_INTERROGATIVE_PATTERNS = re.compile(
    r"\?\s*$|"
    r"\bwould you\b|\bshould I\b|\bwhich approach\b|"
    r"\bdo you want\b|\bdo you prefer\b|\bcan I\b|"
    r"\bwhat should\b|\bshall I\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class DetectedQuestion:
    """A question detected in a Claude Code stream."""

    question_text: str
    full_context: str
    claude_session_id: str | None = None


@dataclass
class StreamAnalyzer:
    """Consumes stream-json events and detects when Claude asks a question.

    Feed each raw JSON line via ``feed()``. After the stream ends, check
    ``detected_question()`` and ``get_question()``.
    """

    accumulated_text: str = ""
    last_stop_reason: str | None = field(default=None, repr=False)
    has_tool_use: bool = False
    has_commits: bool = False
    pr_number: int | None = None
    claude_session_id: str | None = None
    _stop_reason_seen: bool = field(default=False, repr=False)

    def feed(self, raw_line: str) -> None:
        """Process a single stream-json line."""
        stripped = raw_line.strip()
        if not stripped:
            return

        try:
            event = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return

        if not isinstance(event, dict):
            return

        event_type = event.get("type", "")

        if event_type == "assistant":
            content_blocks = (
                event.get("message", {}).get("content")
                or event.get("content")
                or []
            )
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    self.accumulated_text += text
                    pr_match = _PR_NUMBER_PATTERN.search(text)
                    if pr_match:
                        self.pr_number = int(pr_match.group(1))

        elif event_type == "tool_use":
            self.has_tool_use = True

        elif event_type == "result":
            self._stop_reason_seen = True
            stop = event.get("stop_reason")
            self.last_stop_reason = stop if isinstance(stop, str) else None
            # Extract session_id if present
            sid = event.get("session_id")
            if isinstance(sid, str) and sid:
                self.claude_session_id = sid
            # Accumulate result text
            result_text = event.get("result", "")
            if isinstance(result_text, str) and result_text:
                self.accumulated_text += result_text
                pr_match = _PR_NUMBER_PATTERN.search(result_text)
                if pr_match:
                    self.pr_number = int(pr_match.group(1))

    def detected_question(self) -> bool:
        """Return True if the stream ended with an unanswered question.

        All three conditions must hold:
        1. stop_reason is None/missing (not "end_turn")
        2. No PR_NUMBER metadata found
        3. Accumulated text contains interrogative patterns
        """
        if not self._stop_reason_seen:
            return False
        if self.last_stop_reason is not None:
            return False
        if self.pr_number is not None:
            return False
        if not _INTERROGATIVE_PATTERNS.search(self.accumulated_text):
            return False
        return True

    def get_question(self) -> DetectedQuestion | None:
        """Extract the detected question, or None if no question was detected."""
        if not self.detected_question():
            return None

        # Extract the last question from accumulated text
        lines = self.accumulated_text.strip().split("\n")
        question_lines: list[str] = []
        for line in reversed(lines):
            question_lines.insert(0, line)
            if line.strip().endswith("?"):
                break

        question_text = "\n".join(question_lines).strip()
        if not question_text:
            question_text = lines[-1].strip() if lines else ""

        return DetectedQuestion(
            question_text=question_text,
            full_context=self.accumulated_text,
            claude_session_id=self.claude_session_id,
        )

    def reset_for_resume(self) -> None:
        """Clear text state for the next streaming round while keeping session ID."""
        sid = self.claude_session_id
        self.accumulated_text = ""
        self.last_stop_reason = None
        self.has_tool_use = False
        self.has_commits = False
        self.pr_number = None
        self._stop_reason_seen = False
        self.claude_session_id = sid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/brain/test_stream_analyzer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check src/claudedev/brain/autoresponder/stream_analyzer.py tests/brain/test_stream_analyzer.py && mypy src/claudedev/brain/autoresponder/stream_analyzer.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/brain/autoresponder/stream_analyzer.py tests/brain/test_stream_analyzer.py
git commit -m "feat(brain): add StreamAnalyzer for real-time question detection"
```

---

## Chunk 3: AutoResponder + DecisionLogger

### Task 4: AutoResponder -- Opus 4.6 thinking via ClaudeBridge

**Files:**
- Create: `src/claudedev/brain/autoresponder/auto_responder.py`
- Create: `tests/brain/test_auto_responder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/brain/test_auto_responder.py`:

```python
"""Tests for AutoResponder -- Opus 4.6 thinking + autonomous answers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from claudedev.brain.autoresponder.auto_responder import AutoResponse, AutoResponder
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
    async def test_respond_calls_bridge_with_thinking_model(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(return_value=_make_claude_result(
            "DECISION: Use approach A\nREASONING: Better fit\nRISK: 5"
        ))
        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])

        responder = AutoResponder(config, bridge, episodic)
        question = _make_question()
        classification = _make_classification()

        issue_context = {"number": 42, "title": "Add feature", "body": "Details"}
        response = await responder.respond(question, issue_context, classification)

        assert response.answer is not None
        assert len(response.answer) > 0
        bridge.execute_task.assert_awaited_once()

    async def test_respond_parses_decision_format(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(return_value=_make_claude_result(
            "DECISION: Use Redis for caching\nREASONING: Existing infra\nRISK: 3"
        ))
        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])

        responder = AutoResponder(config, bridge, episodic)
        response = await responder.respond(
            _make_question(), {"number": 1, "title": "T", "body": "B"},
            _make_classification(),
        )

        assert "Redis" in response.answer
        assert "Existing infra" in response.reasoning

    async def test_respond_handles_bridge_failure(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(return_value=_make_claude_result(
            "", success=False,
        ))
        episodic = AsyncMock()
        episodic.search = AsyncMock(return_value=[])

        responder = AutoResponder(config, bridge, episodic)
        response = await responder.respond(
            _make_question(), {"number": 1, "title": "T", "body": "B"},
            _make_classification(),
        )

        # Should return a safe fallback answer, not crash
        assert response.answer is not None
        assert response.risk_score == 10  # Maximum risk for fallback

    async def test_respond_queries_episodic_memory(self) -> None:
        config = _make_config()
        bridge = MagicMock()
        bridge._model = config.claude_model
        bridge.execute_task = AsyncMock(return_value=_make_claude_result(
            "DECISION: Yes\nREASONING: Past success\nRISK: 2"
        ))
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
        bridge.execute_task = AsyncMock(return_value=_make_claude_result(
            "DECISION: Yes\nREASONING: Fine\nRISK: 2"
        ))

        responder = AutoResponder(config, bridge, episodic_store=None)
        response = await responder.respond(
            _make_question(),
            {"number": 1, "title": "T", "body": "B"},
            _make_classification(),
        )
        assert response.answer is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/brain/test_auto_responder.py -v`
Expected: FAIL -- module doesn't exist

- [ ] **Step 3: Implement AutoResponder**

Create `src/claudedev/brain/autoresponder/auto_responder.py`:

```python
"""AutoResponder -- calls Opus 4.6 to autonomously answer Claude Code questions."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from claudedev.brain.autoresponder.question_classifier import (
    ClassificationResult,
    QuestionType,
)
from claudedev.brain.autoresponder.stream_analyzer import DetectedQuestion

if TYPE_CHECKING:
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

        # Assemble episodic memory context
        past_decisions = ""
        if self._episodic:
            try:
                keywords = f"{issue_context.get('title', '')} {question.question_text}"
                episodes = await self._episodic.search(keywords, limit=3)
                if episodes:
                    parts = []
                    for ep in episodes:
                        parts.append(
                            f"- Task: {ep.task}\n"
                            f"  Approach: {ep.approach}\n"
                            f"  Outcome: {ep.outcome}"
                        )
                    past_decisions = "\n".join(parts)
            except Exception:
                logger.warning("episodic_search_failed", exc_info=True)

        # Build the task prompt
        task_prompt = (
            f"ISSUE: #{issue_context.get('number', '?')} "
            f"-- {issue_context.get('title', 'Unknown')}\n"
            f"BODY: {str(issue_context.get('body', ''))[:3000]}\n"
        )
        if past_decisions:
            task_prompt += f"\nPAST DECISIONS:\n{past_decisions}\n"
        task_prompt += (
            f"\nClaude's question: \"{question.question_text}\"\n"
            f"Question type: {classification.question_type.value}\n"
            f"Full context:\n{question.full_context[-5000:]}\n"
        )

        # Store original model, swap to thinking model
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
            logger.error(
                "auto_responder_bridge_failed",
                error=result.error,
            )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/brain/test_auto_responder.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check src/claudedev/brain/autoresponder/auto_responder.py tests/brain/test_auto_responder.py && mypy src/claudedev/brain/autoresponder/auto_responder.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/brain/autoresponder/auto_responder.py tests/brain/test_auto_responder.py
git commit -m "feat(brain): add AutoResponder for Opus 4.6 autonomous thinking"
```

---

### Task 5: DecisionLogger -- episodic + dashboard + structlog

**Files:**
- Create: `src/claudedev/brain/autoresponder/decision_logger.py`
- Create: `tests/brain/test_decision_logger.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/brain/test_decision_logger.py`:

```python
"""Tests for DecisionLogger -- episodic + dashboard + structlog logging."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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
        # Should not raise
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

        # Should broadcast decision event
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

        # Should not propagate
        await dl.log(
            question=_make_question(),
            response=_make_response(),
            issue_number=42,
            session_id="sess-1",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/brain/test_decision_logger.py -v`
Expected: FAIL -- module doesn't exist

- [ ] **Step 3: Implement DecisionLogger**

Create `src/claudedev/brain/autoresponder/decision_logger.py`:

```python
"""DecisionLogger -- records auto-decisions to episodic memory, dashboard, and structlog."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from claudedev.brain.autoresponder.auto_responder import AutoResponse
from claudedev.brain.autoresponder.stream_analyzer import DetectedQuestion
from claudedev.brain.models import EpisodicMemory

if TYPE_CHECKING:
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
                    task=(
                        f"auto_decision:issue-{issue_number}"
                        f":{response.decision_type.value}"
                    ),
                    approach=(
                        f"Q: {question.question_text[:500]}\n"
                        f"A: {response.answer[:500]}"
                    ),
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
                            response.thinking_duration_ms, 1,
                        ),
                    },
                )
            except Exception:
                logger.warning("decision_logger_ws_failed", exc_info=True)

        return episode_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/brain/test_decision_logger.py -v`
Expected: ALL PASS

- [ ] **Step 5: Update package __init__.py with all exports**

Update `src/claudedev/brain/autoresponder/__init__.py`:

```python
"""AutoResponder -- autonomous thinking layer for unattended Claude Code sessions."""

from claudedev.brain.autoresponder.auto_responder import AutoResponse, AutoResponder
from claudedev.brain.autoresponder.decision_logger import DecisionLogger
from claudedev.brain.autoresponder.question_classifier import (
    ClassificationResult,
    QuestionClassifier,
    QuestionType,
)
from claudedev.brain.autoresponder.stream_analyzer import DetectedQuestion, StreamAnalyzer

__all__ = [
    "AutoResponse",
    "AutoResponder",
    "ClassificationResult",
    "DecisionLogger",
    "DetectedQuestion",
    "QuestionClassifier",
    "QuestionType",
    "StreamAnalyzer",
]
```

- [ ] **Step 6: Run ruff + mypy on all autoresponder modules**

Run: `ruff check src/claudedev/brain/autoresponder/ tests/brain/test_decision_logger.py && mypy src/claudedev/brain/autoresponder/`
Expected: Clean

- [ ] **Step 7: Commit**

```bash
git add src/claudedev/brain/autoresponder/ tests/brain/test_decision_logger.py
git commit -m "feat(brain): add DecisionLogger + complete autoresponder package"
```

---

## Chunk 4: resume_session + TeamEngine Integration

### Task 6: Add resume_session() to ClaudeSDKClient

**Files:**
- Modify: `src/claudedev/integrations/claude_sdk.py` (add method after `_run_query_cli`, around line 248)
- Create: `tests/test_resume_session.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resume_session.py`:

```python
"""Tests for ClaudeSDKClient.resume_session -- session resume via CLI."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudedev.auth import AuthManager, AuthMode
from claudedev.integrations.claude_sdk import ClaudeSDKClient


@pytest.fixture
def cli_client() -> ClaudeSDKClient:
    auth = MagicMock(spec=AuthManager)
    auth.get_auth_mode.return_value = AuthMode.CLI
    auth.claude_code_path = "/usr/bin/claude"
    return ClaudeSDKClient(auth)


class TestResumeSession:
    async def test_builds_correct_command(self, cli_client: ClaudeSDKClient) -> None:
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[
            b'{"type":"result","stop_reason":"end_turn","result":"Done"}\n',
            b"",
        ])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc,
        ) as mock_exec:
            chunks = []
            async for chunk in cli_client.resume_session(
                session_id="sess-abc-123",
                prompt="Use approach A",
                cwd="/tmp/worktree",
            ):
                chunks.append(chunk)

            call_args = mock_exec.call_args[0]
            assert "--resume" in call_args
            assert "sess-abc-123" in call_args
            assert "-p" in call_args
            assert "Use approach A" in call_args

    async def test_streams_output(self, cli_client: ClaudeSDKClient) -> None:
        lines = [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"OK"}]}}\n',
            b'{"type":"result","stop_reason":"end_turn","result":"Done"}\n',
            b"",
        ]
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=lines)
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in cli_client.resume_session(
                session_id="sess-123",
                prompt="Continue",
                cwd="/tmp",
            ):
                chunks.append(chunk)

        assert len(chunks) == 2  # Two non-empty lines

    async def test_uses_stream_json_format(self, cli_client: ClaudeSDKClient) -> None:
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[b"", b""])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc,
        ) as mock_exec:
            async for _ in cli_client.resume_session("s", "p", "/tmp"):
                pass

            call_args = mock_exec.call_args[0]
            assert "--output-format" in call_args
            assert "stream-json" in call_args
            assert "--verbose" in call_args
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resume_session.py -v`
Expected: FAIL -- method doesn't exist

- [ ] **Step 3: Implement resume_session() in ClaudeSDKClient**

Add after `_run_query_cli` method (around line 248) in `src/claudedev/integrations/claude_sdk.py`:

```python
    async def resume_session(
        self,
        session_id: str,
        prompt: str,
        cwd: str,
        output_format: str = "stream-json",
        *,
        ws_session_id: str | None = None,
        ws_manager: WebSocketManager | None = None,
    ) -> AsyncIterator[str]:
        """Resume a Claude Code session with a follow-up prompt.

        Uses ``claude --resume <session_id> -p <prompt>`` to continue a
        previously started session.

        Args:
            session_id: The Claude Code session ID to resume.
            prompt: The follow-up prompt (the auto-responder's answer).
            cwd: Working directory for the resumed session.
            output_format: Output format (default: stream-json).
            ws_session_id: Optional session ID for WebSocket broadcast.
            ws_manager: Optional WebSocketManager for live output.

        Yields:
            Raw stream-json lines from the resumed session.
        """
        log = logger.bind(mode="cli", resume_session_id=session_id)
        claude_path = self._auth.claude_code_path

        cmd = [
            claude_path, "--resume", session_id, "-p", prompt,
            "--output-format", output_format,
        ]
        if output_format == "stream-json":
            cmd.append("--verbose")

        log.debug("cli_resume_start", cwd=cwd)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        async with self._semaphore:
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )

                if process.stdout is None:
                    return

                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    yield decoded
                    if (
                        ws_session_id
                        and ws_manager
                        and output_format == "stream-json"
                    ):
                        await self._broadcast_stream_json(
                            ws_manager, ws_session_id, decoded,
                        )

                await process.wait()

                if process.returncode != 0 and process.stderr:
                    stderr_output = await process.stderr.read()
                    error_text = stderr_output.decode(
                        "utf-8", errors="replace",
                    ).strip()
                    if error_text:
                        log.warning("cli_resume_stderr", stderr=error_text)

            except (OSError, asyncio.CancelledError) as exc:
                log.error("cli_resume_error", error=str(exc))
                raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_resume_session.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check src/claudedev/integrations/claude_sdk.py tests/test_resume_session.py && mypy src/claudedev/integrations/claude_sdk.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/integrations/claude_sdk.py tests/test_resume_session.py
git commit -m "feat(sdk): add resume_session() for auto-responder session continuation"
```

---

### Task 7: Wire auto-respond loop into TeamEngine

**Files:**
- Modify: `src/claudedev/engines/team_engine.py:1-374`

This is the integration task. The `run_implementation` method gains an outer loop:
stream, detect question, classify, think, log, resume.

- [ ] **Step 1: Add imports to team_engine.py**

At the top of `src/claudedev/engines/team_engine.py`, add:

```python
from claudedev.brain.autoresponder import (
    AutoResponder,
    DecisionLogger,
    QuestionClassifier,
    StreamAnalyzer,
)
from claudedev.brain.config import BrainConfig
```

Also add to the `if TYPE_CHECKING` block:

```python
    from claudedev.brain.integration.claude_bridge import ClaudeBridge
    from claudedev.brain.memory.episodic import EpisodicStore
```

- [ ] **Step 2: Add brain_config, claude_bridge, episodic_store params to TeamEngine.__init__**

Modify `TeamEngine.__init__` to accept optional brain dependencies:

```python
    def __init__(
        self,
        settings: Settings,
        gh_client: GHClient,
        claude_client: ClaudeSDKClient,
        ws_manager: WebSocketManager | None = None,
        steering_manager: SteeringManager | None = None,
        hook_secret: str = "",
        brain_config: BrainConfig | None = None,
        claude_bridge: ClaudeBridge | None = None,
        episodic_store: EpisodicStore | None = None,
    ) -> None:
        self.settings = settings
        self.gh_client = gh_client
        self.claude_client = claude_client
        self.ws_manager = ws_manager
        self.steering_manager = steering_manager
        self.hook_secret = hook_secret
        self._brain_config = brain_config
        self._claude_bridge = claude_bridge
        self._episodic_store = episodic_store
```

- [ ] **Step 3: Wrap streaming in auto-respond loop**

In `run_implementation`, replace the current streaming block (lines 267-301) with an outer loop.
After streaming completes, check if a question was detected. If yes, think and resume.
Max `brain_config.max_auto_responses` loops.

The new streaming block structure:

```python
            implementation_text = ""
            use_stream_json = self.ws_manager is not None
            output_format = "stream-json" if use_stream_json else "text"

            # Auto-respond setup
            stream_analyzer = StreamAnalyzer() if use_stream_json else None
            auto_responder = None
            decision_logger = None
            max_loops = 1  # Default: no auto-response

            if (
                self._brain_config
                and self._brain_config.auto_respond_enabled
                and self._claude_bridge
                and use_stream_json
            ):
                auto_responder = AutoResponder(
                    self._brain_config,
                    self._claude_bridge,
                    self._episodic_store,
                )
                decision_logger = DecisionLogger(
                    episodic_store=self._episodic_store,
                    ws_manager=self.ws_manager,
                )
                max_loops = self._brain_config.max_auto_responses + 1

            claude_session_id: str | None = None
            is_resume = False
            resume_prompt = ""

            for attempt in range(max_loops):
                if is_resume and claude_session_id:
                    stream_source = self.claude_client.resume_session(
                        session_id=claude_session_id,
                        prompt=resume_prompt,
                        cwd=working_dir,
                        ws_session_id=stream_session_id,
                        ws_manager=self.ws_manager,
                    )
                else:
                    stream_source = self.claude_client.run_query(
                        prompt,
                        cwd=working_dir,
                        max_turns=30,
                        output_format=output_format,
                        session_id=stream_session_id,
                        ws_manager=self.ws_manager,
                    )

                async for chunk in stream_source:
                    if use_stream_json:
                        stripped = chunk.strip()
                        if not stripped:
                            continue
                        if stream_analyzer:
                            stream_analyzer.feed(stripped)
                        try:
                            event = json.loads(stripped)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        event_type = event.get("type", "")
                        if event_type == "assistant":
                            content_blocks = (
                                event.get("message", {}).get("content")
                                or event.get("content")
                                or []
                            )
                            for block in content_blocks:
                                if (
                                    isinstance(block, dict)
                                    and block.get("type") == "text"
                                ):
                                    implementation_text += block.get("text", "")
                        elif event_type == "result":
                            result = event.get("result", "")
                            if isinstance(result, str):
                                implementation_text += result
                    else:
                        implementation_text += chunk

                # Check for detected question
                if (
                    stream_analyzer
                    and stream_analyzer.detected_question()
                    and auto_responder
                    and attempt < max_loops - 1
                ):
                    question = stream_analyzer.get_question()
                    if question:
                        log.info(
                            "auto_response_question_detected",
                            question=question.question_text[:200],
                            attempt=attempt,
                        )

                        if self.ws_manager:
                            await self.ws_manager.broadcast_activity(
                                stream_session_id,
                                "auto_response_thinking",
                                {"question": question.question_text[:200]},
                            )

                        classification = QuestionClassifier.classify(
                            question.question_text,
                        )
                        issue_context = {
                            "number": tracked.github_issue_number,
                            "title": gh_issue.title,
                            "body": gh_issue.body or "",
                        }
                        response = await auto_responder.respond(
                            question, issue_context, classification,
                        )

                        if decision_logger:
                            await decision_logger.log(
                                question=question,
                                response=response,
                                issue_number=tracked.github_issue_number,
                                session_id=stream_session_id,
                            )

                        # Prepare for resume
                        claude_session_id = (
                            stream_analyzer.claude_session_id
                            or self._find_claude_session_id(
                                working_dir, agent_session.started_at,
                            )
                        )
                        resume_prompt = response.answer
                        stream_analyzer.reset_for_resume()
                        is_resume = True

                        if self.ws_manager:
                            await self.ws_manager.broadcast_activity(
                                stream_session_id,
                                "auto_response_resumed",
                                {
                                    "answer": response.answer[:200],
                                    "risk_score": response.risk_score,
                                },
                            )

                        continue  # Next loop iteration will resume

                break  # Normal completion -- exit the loop
```

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `pytest tests/ -v --tb=short -x`
Expected: ALL PASS (existing TeamEngine tests still work because new params are optional)

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check src/claudedev/engines/team_engine.py && mypy src/claudedev/engines/team_engine.py`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/engines/team_engine.py
git commit -m "feat(engine): wire auto-respond loop into TeamEngine streaming"
```

---

## Chunk 5: Integration Test + Final Quality Gates

### Task 8: Integration test -- full auto-respond loop

**Files:**
- Create: `tests/brain/test_autoresponder_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/brain/test_autoresponder_integration.py`:

```python
"""Integration test: stream, detect, think, resume, complete."""

from __future__ import annotations

import json

from unittest.mock import AsyncMock, MagicMock

import pytest

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
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "I've analyzed the codebase. "}
            ]}}),
            json.dumps({"type": "tool_use", "name": "Read"}),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Which approach should I use for the caching layer?"}
            ]}}),
            json.dumps({
                "type": "result", "result": "", "session_id": "claude-abc123",
            }),
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
            "choice", "architecture", "missing_info",
        }

        # Phase 3: AutoResponder thinks
        bridge = MagicMock()
        bridge.execute_task = AsyncMock(return_value=ClaudeResult(
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
        ))
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
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": (
                    "Implementing Redis caching... Done!\n\n"
                    "PR_NUMBER: 99\nBRANCH: claudedev/issue-42"
                )}
            ]}}),
            json.dumps({
                "type": "result", "stop_reason": "end_turn", "result": "",
            }),
        ]

        for event in stream_events_phase2:
            analyzer.feed(event)

        assert analyzer.detected_question() is False
        assert analyzer.pr_number == 99

    async def test_max_retries_respected(self) -> None:
        """Verify the loop stops after max_auto_responses."""
        config = BrainConfig(project_path="/tmp/test", max_auto_responses=2)

        bridge = MagicMock()
        bridge.execute_task = AsyncMock(return_value=ClaudeResult(
            content="DECISION: Proceed\nREASONING: OK\nRISK: 2",
            input_tokens=100, output_tokens=50,
            stop_reason="end_turn", tool_use_history=[],
            duration_ms=500.0, success=True,
        ))
        bridge._model = config.claude_model

        responder = AutoResponder(config, bridge)
        responses_generated = 0

        for attempt in range(config.max_auto_responses + 1):
            analyzer = StreamAnalyzer()
            analyzer.feed(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Should I proceed?"}
            ]}}))
            analyzer.feed(json.dumps({"type": "result", "result": ""}))

            if (
                analyzer.detected_question()
                and attempt < config.max_auto_responses
            ):
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
        bridge.execute_task = AsyncMock(return_value=ClaudeResult(
            content="", input_tokens=0, output_tokens=0,
            stop_reason="", tool_use_history=[],
            duration_ms=0, success=False, error="API timeout",
        ))
        bridge._model = config.claude_model

        responder = AutoResponder(config, bridge)
        analyzer = StreamAnalyzer()
        analyzer.feed(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Which database?"}
        ]}}))
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
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/brain/test_autoresponder_integration.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Run full quality gates**

Run: `ruff check . && mypy src/claudedev/brain/autoresponder/ src/claudedev/integrations/claude_sdk.py src/claudedev/engines/team_engine.py src/claudedev/brain/config.py`
Expected: Clean

- [ ] **Step 5: Commit**

```bash
git add tests/brain/test_autoresponder_integration.py
git commit -m "test(brain): add integration test for full auto-respond loop"
```

---

### Task 9: Final quality sweep and cleanup

- [ ] **Step 1: Run full test suite with coverage**

Run: `pytest tests/ -v --tb=short --cov=claudedev.brain.autoresponder --cov-report=term-missing`
Expected: >85% coverage on autoresponder package

- [ ] **Step 2: Verify all ruff + mypy clean**

Run: `ruff check . && mypy src/`
Expected: Clean

- [ ] **Step 3: Final commit with any cleanup**

```bash
git add -A
git commit -m "chore: final quality pass on autoresponder module"
```
