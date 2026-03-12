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
    (
        re.compile(r"\bshould I also\b|\bwould you like me to also\b", re.I),
        QuestionType.SCOPE_EXPANSION,
        7,
    ),
    # Architecture -- database, pattern, library choices
    (
        re.compile(r"\bwhich (database|pattern|library|framework)\b|\brepository pattern\b", re.I),
        QuestionType.ARCHITECTURE,
        6,
    ),
    # Choice -- "A or B", "which approach", "option 1"
    (
        re.compile(
            r"\bapproach [A-Z]\b|\bor\b.+\?\s*$|\bwhich (approach|option|one)\b|\boption \d\b",
            re.I,
        ),
        QuestionType.CHOICE,
        4,
    ),
    # Permission -- "can I", "may I", "is it okay"
    (re.compile(r"\bcan I\b|\bmay I\b|\bis it (okay|ok) to\b", re.I), QuestionType.PERMISSION, 2),
    # Missing info -- "what should", "what is the", "what <noun>"
    (re.compile(r"\bwhat\b", re.I), QuestionType.MISSING_INFO, 3),
    # Confirmation -- "should I proceed", "shall I continue"
    (
        re.compile(r"\bshould I (proceed|continue|go ahead|create|start|add)\b|\bshall I\b", re.I),
        QuestionType.CONFIRMATION,
        2,
    ),
]

_RISK_KEYWORDS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(delete|remove|drop|migration)\b", re.I), 1),
    (re.compile(r"\boutside\b.+\bscope\b|\bother file", re.I), 1),
    (re.compile(r"\b(add|new|install)\b.+\bdependenc", re.I), 3),
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
