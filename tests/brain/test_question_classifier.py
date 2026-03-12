"""Tests for QuestionClassifier -- question type + risk scoring."""

from __future__ import annotations

import pytest

from claudedev.brain.autoresponder.question_classifier import (
    QuestionClassifier,
    QuestionType,
)


class TestQuestionType:
    def test_all_types_defined(self) -> None:
        expected = {
            "confirmation",
            "choice",
            "missing_info",
            "permission",
            "scope_expansion",
            "architecture",
            "unknown",
        }
        assert {t.value for t in QuestionType} == expected


class TestClassifyConfirmation:
    @pytest.mark.parametrize(
        "text",
        [
            "Should I proceed with the implementation?",
            "Shall I continue?",
            "Should I go ahead and create the PR?",
        ],
    )
    def test_confirmation_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.CONFIRMATION

    def test_confirmation_risk_range(self) -> None:
        result = QuestionClassifier.classify("Should I proceed?")
        assert 2 <= result.risk_score <= 4


class TestClassifyChoice:
    @pytest.mark.parametrize(
        "text",
        [
            "Should I use approach A or approach B?",
            "Which approach would you prefer?",
            "Option 1: SQLite, Option 2: PostgreSQL. Which one?",
        ],
    )
    def test_choice_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.CHOICE

    def test_choice_risk_range(self) -> None:
        result = QuestionClassifier.classify("Approach A or B?")
        assert 4 <= result.risk_score <= 7


class TestClassifyMissingInfo:
    @pytest.mark.parametrize(
        "text",
        [
            "What should the function name be?",
            "What is the expected return type?",
            "What database table should this use?",
        ],
    )
    def test_missing_info_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.MISSING_INFO


class TestClassifyPermission:
    @pytest.mark.parametrize(
        "text",
        [
            "Can I modify this file?",
            "Is it okay to change the API contract?",
            "May I update the migration?",
        ],
    )
    def test_permission_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.PERMISSION

    def test_permission_risk_range(self) -> None:
        result = QuestionClassifier.classify("Can I modify this file?")
        assert 2 <= result.risk_score <= 3


class TestClassifyScopeExpansion:
    @pytest.mark.parametrize(
        "text",
        [
            "Should I also refactor the helper functions?",
            "Would you like me to also add logging?",
            "Should I also fix the related tests?",
        ],
    )
    def test_scope_expansion_detected(self, text: str) -> None:
        result = QuestionClassifier.classify(text)
        assert result.question_type == QuestionType.SCOPE_EXPANSION

    def test_scope_expansion_risk_range(self) -> None:
        result = QuestionClassifier.classify("Should I also refactor?")
        assert 7 <= result.risk_score <= 9


class TestClassifyArchitecture:
    @pytest.mark.parametrize(
        "text",
        [
            "Which database should I use for this?",
            "Should I use the repository pattern or direct queries?",
            "Which library should I use for HTTP requests?",
        ],
    )
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
