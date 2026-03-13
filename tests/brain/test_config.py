"""Tests for BrainConfig — immutable brain configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from claudedev.brain.config import BrainConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def minimal_config(**overrides: object) -> BrainConfig:
    """Return a BrainConfig with only the required field, plus any overrides."""
    kwargs: dict[str, object] = {"project_path": "/tmp/myproject"}
    kwargs.update(overrides)
    return BrainConfig(**kwargs)


# ---------------------------------------------------------------------------
# Construction with defaults
# ---------------------------------------------------------------------------


class TestBrainConfigDefaults:
    def test_minimal_construction(self) -> None:
        from pathlib import Path

        cfg = minimal_config()
        assert cfg.project_path == str(Path("/tmp/myproject").resolve())

    def test_default_max_working_memory_tokens(self) -> None:
        cfg = minimal_config()
        assert cfg.max_working_memory_tokens == 180_000

    def test_default_embedding_model(self) -> None:
        cfg = minimal_config()
        assert cfg.embedding_model == "nomic-embed-text-v2"

    def test_default_ollama_base_url(self) -> None:
        cfg = minimal_config()
        assert cfg.ollama_base_url == "http://localhost:11434"

    def test_default_claude_model(self) -> None:
        cfg = minimal_config()
        assert cfg.claude_model == "claude-sonnet-4-20250514"

    def test_default_system1_confidence_threshold(self) -> None:
        cfg = minimal_config()
        assert cfg.system1_confidence_threshold == 0.85

    def test_default_max_retries(self) -> None:
        cfg = minimal_config()
        assert cfg.max_retries == 3

    def test_default_log_level(self) -> None:
        cfg = minimal_config()
        assert cfg.log_level == "INFO"

    def test_default_memory_dir_expands_tilde(self) -> None:
        cfg = minimal_config()
        home = str(Path("~").expanduser())
        assert cfg.memory_dir.startswith(home)
        assert "~" not in cfg.memory_dir


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------


class TestBrainConfigFrozen:
    def test_cannot_set_attribute(self) -> None:
        cfg = minimal_config()
        with pytest.raises((ValidationError, TypeError)):
            cfg.project_path = "/other"  # type: ignore[misc]

    def test_cannot_delete_attribute(self) -> None:
        cfg = minimal_config()
        with pytest.raises((ValidationError, TypeError, AttributeError)):
            del cfg.project_path

    def test_frozen_after_construction(self) -> None:
        cfg = minimal_config()
        # Verify the model_config declares frozen=True
        assert cfg.model_config.get("frozen") is True


# ---------------------------------------------------------------------------
# project_path validator
# ---------------------------------------------------------------------------


class TestProjectPathValidator:
    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError, match="project_path"):
            BrainConfig(project_path="")

    def test_whitespace_only_rejected(self) -> None:
        with pytest.raises(ValidationError, match="project_path"):
            BrainConfig(project_path="   ")

    def test_tab_only_rejected(self) -> None:
        with pytest.raises(ValidationError, match="project_path"):
            BrainConfig(project_path="\t")

    def test_newline_only_rejected(self) -> None:
        with pytest.raises(ValidationError, match="project_path"):
            BrainConfig(project_path="\n")

    def test_valid_path_accepted(self) -> None:
        from pathlib import Path

        cfg = BrainConfig(project_path="/home/user/myproject")
        assert cfg.project_path == str(Path("/home/user/myproject").resolve())

    def test_relative_path_accepted(self) -> None:
        cfg = BrainConfig(project_path="./my/project")
        # resolve() converts relative paths to absolute
        assert cfg.project_path.startswith("/")
        assert cfg.project_path.endswith("my/project")


# ---------------------------------------------------------------------------
# memory_dir tilde expansion
# ---------------------------------------------------------------------------


class TestMemoryDirExpansion:
    def test_tilde_expanded(self) -> None:
        cfg = minimal_config(memory_dir="~/.claudedev/memory")
        expected = str(Path("~/.claudedev/memory").expanduser())
        assert cfg.memory_dir == expected

    def test_no_tilde_unchanged(self) -> None:
        cfg = minimal_config(memory_dir="/absolute/path/memory")
        assert cfg.memory_dir == "/absolute/path/memory"

    def test_tilde_with_subdirs(self) -> None:
        cfg = minimal_config(memory_dir="~/some/deep/path")
        assert "~" not in cfg.memory_dir
        assert cfg.memory_dir.endswith("/some/deep/path")

    def test_memory_dir_resolves_symlinks(self, tmp_path: Path) -> None:
        cfg = BrainConfig(project_path=str(tmp_path), memory_dir="~/.claudedev/memory")
        # Should be resolved (no relative components, expanded)
        assert "~" not in cfg.memory_dir
        assert Path(cfg.memory_dir).is_absolute()


# ---------------------------------------------------------------------------
# max_working_memory_tokens bounds
# ---------------------------------------------------------------------------


class TestMaxWorkingMemoryTokensBounds:
    def test_minimum_valid_value(self) -> None:
        cfg = minimal_config(max_working_memory_tokens=1000)
        assert cfg.max_working_memory_tokens == 1000

    def test_maximum_valid_value(self) -> None:
        cfg = minimal_config(max_working_memory_tokens=500_000)
        assert cfg.max_working_memory_tokens == 500_000

    def test_middle_value(self) -> None:
        cfg = minimal_config(max_working_memory_tokens=100_000)
        assert cfg.max_working_memory_tokens == 100_000

    def test_below_minimum_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_working_memory_tokens=999)

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_working_memory_tokens=0)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_working_memory_tokens=-1)

    def test_above_maximum_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_working_memory_tokens=500_001)

    def test_boundary_999_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_working_memory_tokens=999)

    def test_boundary_1000_accepted(self) -> None:
        cfg = minimal_config(max_working_memory_tokens=1000)
        assert cfg.max_working_memory_tokens == 1000

    def test_boundary_500000_accepted(self) -> None:
        cfg = minimal_config(max_working_memory_tokens=500_000)
        assert cfg.max_working_memory_tokens == 500_000

    def test_boundary_500001_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_working_memory_tokens=500_001)


# ---------------------------------------------------------------------------
# system1_confidence_threshold bounds
# ---------------------------------------------------------------------------


class TestSystem1ConfidenceThresholdBounds:
    def test_zero_accepted(self) -> None:
        cfg = minimal_config(system1_confidence_threshold=0.0)
        assert cfg.system1_confidence_threshold == 0.0

    def test_one_accepted(self) -> None:
        cfg = minimal_config(system1_confidence_threshold=1.0)
        assert cfg.system1_confidence_threshold == 1.0

    def test_midpoint_accepted(self) -> None:
        cfg = minimal_config(system1_confidence_threshold=0.5)
        assert cfg.system1_confidence_threshold == 0.5

    def test_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(system1_confidence_threshold=-0.1)

    def test_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(system1_confidence_threshold=1.1)

    def test_large_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(system1_confidence_threshold=-100.0)


# ---------------------------------------------------------------------------
# max_retries bounds
# ---------------------------------------------------------------------------


class TestMaxRetriesBounds:
    def test_zero_retries_accepted(self) -> None:
        cfg = minimal_config(max_retries=0)
        assert cfg.max_retries == 0

    def test_positive_retries_accepted(self) -> None:
        cfg = minimal_config(max_retries=10)
        assert cfg.max_retries == 10

    def test_negative_retries_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_retries=-1)

    def test_large_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(max_retries=-999)


# ---------------------------------------------------------------------------
# log_level validation
# ---------------------------------------------------------------------------


class TestLogLevelValidation:
    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
    def test_valid_log_levels(self, level: str) -> None:
        cfg = minimal_config(log_level=level)
        assert cfg.log_level == level

    def test_invalid_log_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(log_level="TRACE")

    def test_lowercase_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(log_level="info")

    def test_mixed_case_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(log_level="Info")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            minimal_config(log_level="")

    def test_critical_rejected(self) -> None:
        # CRITICAL is not in the Literal type
        with pytest.raises(ValidationError):
            minimal_config(log_level="CRITICAL")


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestBrainConfigSerialization:
    def test_model_dump_returns_dict(self) -> None:
        from pathlib import Path

        cfg = minimal_config()
        data = cfg.model_dump()
        assert isinstance(data, dict)
        assert data["project_path"] == str(Path("/tmp/myproject").resolve())

    def test_model_dump_contains_all_fields(self) -> None:
        cfg = minimal_config()
        data = cfg.model_dump()
        expected_keys = {
            "project_path",
            "memory_dir",
            "max_working_memory_tokens",
            "embedding_model",
            "ollama_base_url",
            "claude_model",
            "system1_confidence_threshold",
            "max_retries",
            "log_level",
        }
        assert expected_keys.issubset(data.keys())

    def test_round_trip_from_dict(self) -> None:
        original = minimal_config(
            project_path="/srv/project",
            max_working_memory_tokens=50_000,
            log_level="DEBUG",
            max_retries=5,
            system1_confidence_threshold=0.75,
        )
        data = original.model_dump()
        restored = BrainConfig(**data)
        assert restored == original

    def test_round_trip_preserves_expanded_memory_dir(self) -> None:
        original = minimal_config(memory_dir="~/.claudedev/memory")
        data = original.model_dump()
        restored = BrainConfig(**data)
        assert restored.memory_dir == original.memory_dir
        assert "~" not in restored.memory_dir

    def test_model_dump_all_custom_values(self) -> None:
        cfg = minimal_config(
            project_path="/custom/project",
            memory_dir="/absolute/memory",
            max_working_memory_tokens=200_000,
            embedding_model="custom-model",
            ollama_base_url="http://remote:11434",
            claude_model="claude-opus-4",
            system1_confidence_threshold=0.9,
            max_retries=7,
            log_level="WARNING",
        )
        data = cfg.model_dump()
        assert data["project_path"] == "/custom/project"
        assert data["memory_dir"] == "/absolute/memory"
        assert data["max_working_memory_tokens"] == 200_000
        assert data["embedding_model"] == "custom-model"
        assert data["ollama_base_url"] == "http://remote:11434"
        assert data["claude_model"] == "claude-opus-4"
        assert data["system1_confidence_threshold"] == 0.9
        assert data["max_retries"] == 7
        assert data["log_level"] == "WARNING"


# ---------------------------------------------------------------------------
# AutoResponder config fields
# ---------------------------------------------------------------------------


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
