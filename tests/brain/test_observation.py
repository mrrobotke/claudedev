# tests/brain/test_observation.py
"""Tests for the Observation model."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from claudedev.brain.models import Observation


class TestObservation:
    def test_minimal_creation(self) -> None:
        obs = Observation(
            task_id="abc123",
            predicted_outcome="success",
            actual_outcome="success",
            prediction_error=0.1,
            predicted_confidence=0.8,
            actual_confidence=0.7,
            error_category="confidence_gap",
        )
        assert obs.task_id == "abc123"
        assert obs.prediction_error == 0.1

    def test_auto_generated_id(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.id
        assert len(obs.id) == 32

    def test_unique_ids(self) -> None:
        kwargs = dict(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        o1 = Observation(**kwargs)
        o2 = Observation(**kwargs)
        assert o1.id != o2.id

    def test_timestamp_utc(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.timestamp.tzinfo is not None
        assert obs.timestamp.tzinfo == UTC

    def test_episode_id_optional(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.episode_id is None

    def test_episode_id_set(self) -> None:
        obs = Observation(
            task_id="t",
            episode_id="ep1",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.episode_id == "ep1"

    def test_prediction_error_bounds_zero(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.prediction_error == 0.0

    def test_prediction_error_bounds_one(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=1.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.prediction_error == 1.0

    def test_prediction_error_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=1.1,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category="unknown",
            )

    def test_prediction_error_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=-0.1,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category="unknown",
            )

    def test_all_error_categories(self) -> None:
        for cat in ("success_mismatch", "confidence_gap", "outcome_divergence", "unknown"):
            obs = Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=0.5,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category=cat,
            )
            assert obs.error_category == cat

    def test_invalid_error_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=0.5,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category="invalid_cat",
            )

    def test_confidence_bounds(self) -> None:
        for field in ("predicted_confidence", "actual_confidence"):
            with pytest.raises(ValidationError):
                Observation(
                    task_id="t",
                    predicted_outcome="p",
                    actual_outcome="a",
                    prediction_error=0.0,
                    error_category="unknown",
                    **{field: 1.1},
                )
            with pytest.raises(ValidationError):
                Observation(
                    task_id="t",
                    predicted_outcome="p",
                    actual_outcome="a",
                    prediction_error=0.0,
                    error_category="unknown",
                    **{field: -0.1},
                )

    def test_steering_fields_default_false(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.has_steering is False
        assert obs.directive_type is None
        assert obs.directive_message is None
        assert obs.environment_signals == {}

    def test_steering_fields_set(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
            has_steering=True,
            directive_type="pivot",
            directive_message="Use Redis instead",
            environment_signals={"session_active": True},
        )
        assert obs.has_steering is True
        assert obs.directive_type == "pivot"
        assert obs.directive_message == "Use Redis instead"
        assert obs.environment_signals == {"session_active": True}
