"""Shared fixtures for brain tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.integration.claude_bridge import ClaudeBridge, ClaudeResult

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def brain_config(tmp_path: Path) -> BrainConfig:
    """BrainConfig pointing at a temporary directory."""
    return BrainConfig(
        project_path=str(tmp_path),
        memory_dir=str(tmp_path / "memory"),
    )


@pytest.fixture
def mock_bridge(brain_config: BrainConfig) -> ClaudeBridge:
    """ClaudeBridge with a mocked execute_task that returns success."""
    bridge = ClaudeBridge.__new__(ClaudeBridge)
    bridge._model = brain_config.claude_model
    bridge._max_retries = brain_config.max_retries
    bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
        return_value=ClaudeResult(
            content="Task completed successfully.",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
            tool_use_history=[],
            success=True,
            duration_ms=150.0,
        )
    )
    return bridge
