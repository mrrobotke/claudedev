"""Phase 1 integration tests — full brain loop end-to-end.

These tests verify all Phase 1 components work together as a cohesive system.
This is the Phase 1 graduation gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from claudedev.brain.cortex import Cortex
from claudedev.brain.integration.claude_bridge import ClaudeResult
from claudedev.brain.models import Skill, Task

if TYPE_CHECKING:
    from claudedev.brain.config import BrainConfig
    from claudedev.brain.integration.claude_bridge import ClaudeBridge


@pytest.fixture
def successful_bridge(brain_config: BrainConfig) -> ClaudeBridge:
    """Bridge that returns varied successful responses."""
    from claudedev.brain.integration.claude_bridge import ClaudeBridge as _ClaudeBridge

    bridge = _ClaudeBridge.__new__(_ClaudeBridge)
    bridge._model = brain_config.claude_model
    bridge._max_retries = brain_config.max_retries

    call_count = 0

    async def mock_execute(**kwargs: object) -> ClaudeResult:
        nonlocal call_count
        call_count += 1
        return ClaudeResult(
            content=f"Completed task #{call_count}.",
            input_tokens=80 + call_count * 10,
            output_tokens=40 + call_count * 5,
            stop_reason="end_turn",
            tool_use_history=["Edit"] if call_count % 2 == 0 else [],
            success=True,
            duration_ms=100.0 + call_count * 10,
        )

    bridge.execute_task = AsyncMock(side_effect=mock_execute)  # type: ignore[method-assign]
    return bridge


class TestFullCognitiveLoop:
    """End-to-end: task in -> perceive -> recall -> decide -> act -> remember -> result out."""

    async def test_task_produces_result(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Fix the login redirect bug")
        result = await cortex.run(task)

        assert result.task_id == task.id
        assert result.success is True
        assert result.output != ""
        assert result.duration_ms > 0
        await cortex.shutdown()

    async def test_episodic_memory_stored_after_task(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Add pagination to user list")
        await cortex.run(task)

        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        assert "pagination" in episodes[0].task.lower()
        await cortex.shutdown()

    async def test_decision_logged(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Test decision logging")
        await cortex.run(task)

        logs = cortex._decision.get_decision_log()
        assert len(logs) == 1
        assert logs[0].task_id == task.id
        assert logs[0].mode in ("system1", "delegate")
        await cortex.shutdown()


class TestMultiTaskSequence:
    """Run multiple tasks and verify memory accumulates."""

    async def test_three_tasks_all_stored(
        self, brain_config: BrainConfig, successful_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, successful_bridge)

        tasks = [
            Task(description="Fix authentication timeout"),
            Task(description="Add password reset flow"),
            Task(description="Fix authentication session expiry"),
        ]

        results = []
        for task in tasks:
            result = await cortex.run(task)
            results.append(result)

        assert all(r.success for r in results)
        episodes = await cortex.episodic.get_recent(limit=10)
        assert len(episodes) == 3
        await cortex.shutdown()

    async def test_recall_finds_related_past_tasks(
        self, brain_config: BrainConfig, successful_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, successful_bridge)

        await cortex.run(Task(description="Fix authentication timeout"))
        await cortex.run(Task(description="Fix authentication session"))

        episodes = await cortex.episodic.search("authentication")
        assert len(episodes) == 2
        await cortex.shutdown()

    async def test_five_tasks_sequential(
        self, brain_config: BrainConfig, successful_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, successful_bridge)

        for i in range(5):
            result = await cortex.run(Task(description=f"Sequential task {i}"))
            assert result.success is True

        assert await cortex.episodic.count() == 5
        assert len(cortex._decision.get_decision_log()) == 5
        await cortex.shutdown()


class TestWorkingMemoryBudget:
    """Verify context assembly respects token budget."""

    async def test_context_within_budget(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.run(Task(description="Test working memory budget"))

        tokens = await cortex.working.token_count()
        assert tokens <= brain_config.max_working_memory_tokens
        await cortex.shutdown()

    async def test_context_contains_task_description(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.run(Task(description="Unique test string XYZ123"))

        context = await cortex.working.get_context()
        assert "Unique test string XYZ123" in context
        await cortex.shutdown()


class TestErrorRecovery:
    """Brain must never crash, even when subsystems fail."""

    async def test_bridge_exception_returns_failed_result(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        mock_bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("API down")
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        result = await cortex.run(Task(description="This will fail"))
        assert result.success is False
        assert result.error is not None
        assert "API down" in result.error
        await cortex.shutdown()

    async def test_bridge_failure_result_propagated(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        mock_bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
            return_value=ClaudeResult(
                content="",
                input_tokens=0,
                output_tokens=0,
                stop_reason="",
                tool_use_history=[],
                success=False,
                error="Syntax error",
                duration_ms=50.0,
            )
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        result = await cortex.run(Task(description="Failing task"))
        assert result.success is False
        await cortex.shutdown()

    async def test_failed_task_still_stored_in_memory(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        mock_bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
            return_value=ClaudeResult(
                content="",
                input_tokens=0,
                output_tokens=0,
                stop_reason="",
                tool_use_history=[],
                success=False,
                error="Compilation error",
                duration_ms=50.0,
            )
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.run(Task(description="Store even failures"))
        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        assert "failed" in episodes[0].outcome
        await cortex.shutdown()


class TestSystem1WithRegisteredSkill:
    """Verify System 1 path when a matching skill is registered."""

    async def test_system1_execution_with_skill(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)

        skill = Skill(
            name="fix-import",
            description="Fix missing imports in Python files",
            procedure="1. Find the missing import. 2. Add it.",
            task_signature="fix_import",
            reliability=0.95,
        )
        cortex._decision.register_skill(skill)

        result = await cortex.run(Task(description="Fix import error in module"))
        assert result.success is True

        logs = cortex._decision.get_decision_log()
        assert len(logs) == 1
        await cortex.shutdown()
