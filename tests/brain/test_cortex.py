"""Tests for Cortex — the main brain orchestrator."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from claudedev.brain.cortex import Cortex
from claudedev.brain.integration.claude_bridge import ClaudeResult
from claudedev.brain.models import Skill, Task, TaskResult

if TYPE_CHECKING:
    from claudedev.brain.config import BrainConfig
    from claudedev.brain.integration.claude_bridge import ClaudeBridge


class TestCortexCognitiveLoop:
    """End-to-end cognitive cycle: perceive -> recall -> decide -> act -> remember."""

    async def test_run_returns_task_result(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Fix the login bug")
        result = await cortex.run(task)
        assert isinstance(result, TaskResult)
        assert result.task_id == task.id
        await cortex.shutdown()

    async def test_successful_task(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Add unit test for auth module")
        result = await cortex.run(task)
        assert result.success is True
        assert result.output != ""
        await cortex.shutdown()

    async def test_stores_episodic_memory(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Refactor database layer")
        await cortex.run(task)
        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        assert "Refactor database" in episodes[0].task
        await cortex.shutdown()

    async def test_multiple_tasks_build_memory(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        for i in range(3):
            task = Task(description=f"Task number {i}")
            await cortex.run(task)
        episodes = await cortex.episodic.get_recent(limit=10)
        assert len(episodes) == 3
        await cortex.shutdown()

    async def test_never_crashes_on_bridge_exception(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        mock_bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("Unexpected explosion")
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="This will fail internally")
        result = await cortex.run(task)
        assert result.success is False
        assert result.error is not None
        await cortex.shutdown()

    async def test_never_crashes_on_bridge_failure_result(
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
                error="Syntax error in main.py",
                duration_ms=50.0,
            )
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Failing task")
        result = await cortex.run(task)
        assert result.success is False
        await cortex.shutdown()

    async def test_result_includes_duration(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Quick task")
        result = await cortex.run(task)
        assert result.duration_ms > 0
        await cortex.shutdown()

    async def test_decision_is_logged(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Test decision logging")
        await cortex.run(task)
        logs = cortex._decision.get_decision_log()
        assert len(logs) == 1
        assert logs[0].task_id == task.id
        await cortex.shutdown()

    async def test_recall_finds_related_past_tasks(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.run(Task(description="Fix authentication timeout"))
        await cortex.run(Task(description="Fix authentication session"))
        episodes = await cortex.episodic.search("authentication")
        assert len(episodes) == 2
        await cortex.shutdown()

    async def test_working_memory_within_budget(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Test working memory budget")
        await cortex.run(task)
        tokens = await cortex.working.token_count()
        assert tokens <= brain_config.max_working_memory_tokens
        await cortex.shutdown()

    async def test_recall_populates_working_memory_slot(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        # First task — stored in episodic memory with task text containing "Fix authentication"
        await cortex.run(Task(description="Fix authentication session timeout error"))
        # Second task description is a substring of the first task's stored text,
        # so the LIKE search in _recall finds the first episode and populates the slot.
        await cortex.run(Task(description="Fix authentication session"))
        slot = await cortex.working.slot_info("recalled_memories")
        assert "authentication" in slot.content.lower()
        await cortex.shutdown()

    async def test_system1_uses_skill_procedure_in_prompt(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        cortex._decision._threshold = 0.3
        skill = Skill(
            name="auth-fix",
            description="Fix authentication issues",
            procedure="Step 1: Check token expiry. Step 2: Refresh session.",
            task_signature="Fix authentication timeout",
            reliability=1.0,
        )
        cortex._decision.register_skill(skill)
        execute_mock: AsyncMock = mock_bridge.execute_task  # type: ignore[assignment]
        task = Task(description="Fix authentication timeout")
        await cortex.run(task)
        assert skill.procedure in execute_mock.call_args.kwargs["task"]
        await cortex.shutdown()

    async def test_remember_failure_does_not_invalidate_result(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        cortex.episodic.store = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("DB write failed")
        )
        task = Task(description="Fix authentication timeout")
        result = await cortex.run(task)
        assert result.success is True
        await cortex.shutdown()

    async def test_failed_result_without_error_uses_unknown_outcome(
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
                error=None,
                duration_ms=50.0,
            )
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Failing task no error")
        await cortex.run(task)
        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        assert episodes[0].outcome == "failed: unknown"
        await cortex.shutdown()

    async def test_shutdown_handles_close_error(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        cortex.episodic.close = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("DB close failed")
        )
        await cortex.shutdown()  # should not raise


class TestCortexLatency:
    async def test_loop_latency_under_100ms(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Latency test task")
        start = time.perf_counter()
        await cortex.run(task)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"Brain loop took {elapsed_ms:.1f}ms (budget: 100ms)"
        await cortex.shutdown()


class TestCortexCleanup:
    async def test_shutdown_is_safe(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.run(Task(description="test"))
        await cortex.shutdown()

    async def test_double_shutdown_is_safe(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.shutdown()
        await cortex.shutdown()
