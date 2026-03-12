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
    """Consumes stream-json events and detects when Claude asks a question."""

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
            content_blocks = event.get("message", {}).get("content") or event.get("content") or []
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
            sid = event.get("session_id")
            if isinstance(sid, str) and sid:
                self.claude_session_id = sid
            result_text = event.get("result", "")
            if isinstance(result_text, str) and result_text:
                self.accumulated_text += result_text
                pr_match = _PR_NUMBER_PATTERN.search(result_text)
                if pr_match:
                    self.pr_number = int(pr_match.group(1))

    def detected_question(self) -> bool:
        """Return True if the stream ended with an unanswered question."""
        if not self._stop_reason_seen:
            return False
        if self.last_stop_reason is not None:
            return False
        if self.pr_number is not None:
            return False
        return bool(_INTERROGATIVE_PATTERNS.search(self.accumulated_text))

    def get_question(self) -> DetectedQuestion | None:
        """Extract the detected question, or None if no question was detected."""
        if not self.detected_question():
            return None

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
