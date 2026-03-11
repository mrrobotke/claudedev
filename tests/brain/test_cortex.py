"""Tests for Cortex — the main brain orchestrator."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from claudedev.brain.cortex import Cortex
from claudedev.brain.integration.claude_bridge import ClaudeResult
from claudedev.brain.models import Skill, Task, TaskResult

if TYPE_CHECKING:
    from pathlib import Path

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
        self, tmp_path: Path, mock_bridge: ClaudeBridge
    ) -> None:
        from claudedev.brain.config import BrainConfig

        low_threshold_config = BrainConfig(
            project_path=str(tmp_path),
            memory_dir=str(tmp_path / "memory"),
            system1_confidence_threshold=0.3,
        )
        cortex = await Cortex.create(low_threshold_config, mock_bridge)
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

    async def test_delegate_mode_sends_task_description_as_prompt(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """In delegate mode (no matching skill), the raw task description is the prompt."""
        cortex = await Cortex.create(brain_config, mock_bridge)
        execute_mock: AsyncMock = mock_bridge.execute_task  # type: ignore[assignment]
        task = Task(description="No skill matches this unusual request")
        await cortex.run(task)
        call_task = execute_mock.call_args.kwargs["task"]
        assert call_task == task.description
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

    async def test_recalled_memories_are_bracketed(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.run(Task(description="Fix authentication session timeout error"))
        await cortex.run(Task(description="Fix authentication session"))
        slot = await cortex.working.slot_info("recalled_memories")
        assert "<recalled_memories>" in slot.content
        assert "</recalled_memories>" in slot.content
        assert "reference only" in slot.content.lower()
        await cortex.shutdown()

    async def test_system1_skill_procedure_is_bracketed(
        self, tmp_path: Path, mock_bridge: ClaudeBridge
    ) -> None:
        from claudedev.brain.config import BrainConfig

        low_threshold_config = BrainConfig(
            project_path=str(tmp_path),
            memory_dir=str(tmp_path / "memory"),
            system1_confidence_threshold=0.3,
        )
        cortex = await Cortex.create(low_threshold_config, mock_bridge)
        skill = Skill(
            name="auth-fix",
            description="Fix authentication issues",
            procedure="Step 1: Check token expiry.",
            task_signature="Fix authentication timeout",
            reliability=1.0,
        )
        cortex._decision.register_skill(skill)
        execute_mock: AsyncMock = mock_bridge.execute_task  # type: ignore[assignment]
        task = Task(description="Fix authentication timeout")
        await cortex.run(task)
        call_task = execute_mock.call_args.kwargs["task"]
        assert "<procedure>" in call_task
        assert "</procedure>" in call_task
        await cortex.shutdown()

    async def test_error_truncated_to_208_chars_in_episodic_outcome(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """Errors > 200 chars are truncated to 200 in stored episodic outcome."""
        long_error = "E" * 300
        mock_bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
            return_value=ClaudeResult(
                content="",
                input_tokens=0,
                output_tokens=0,
                stop_reason="",
                tool_use_history=[],
                success=False,
                error=long_error,
                duration_ms=10.0,
            )
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Task with long error")
        await cortex.run(task)
        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        # "failed: " (8 chars) + 200 chars = 208 max
        assert len(episodes[0].outcome) <= 208
        assert episodes[0].outcome.startswith("failed: ")
        assert "E" * 200 in episodes[0].outcome
        await cortex.shutdown()

    async def test_create_propagates_init_failure(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """If EpisodicStore.initialize() raises, Cortex.create() propagates the error."""
        from claudedev.brain.memory.episodic import EpisodicStore

        with patch.object(EpisodicStore, "initialize", new_callable=AsyncMock) as mock_init:
            mock_init.side_effect = OSError("disk full")
            with pytest.raises(OSError, match="disk full"):
                await Cortex.create(brain_config, mock_bridge)

    async def test_recalled_memories_included_in_system_prompt(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """After _recall(), the re-captured context must include recalled_memories."""
        cortex = await Cortex.create(brain_config, mock_bridge)
        # Store a prior episode so recall finds something
        await cortex.run(Task(description="Fix authentication session timeout error"))
        execute_mock: AsyncMock = mock_bridge.execute_task  # type: ignore[assignment]
        await cortex.run(Task(description="Fix authentication session"))
        # The system_prompt passed to Claude must contain the recalled_memories
        call_system_prompt = execute_mock.call_args.kwargs["system_prompt"]
        assert "<recalled_memories>" in call_system_prompt
        await cortex.shutdown()

    async def test_shutdown_handles_close_error(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        cortex.episodic.close = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("DB close failed")
        )
        await cortex.shutdown()  # should not raise

    async def test_run_after_shutdown_returns_error(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.shutdown()
        task = Task(description="Should not execute")
        result = await cortex.run(task)
        assert result.success is False
        assert result.error is not None
        assert "shut down" in result.error.lower()

    async def test_error_with_angle_brackets_sanitized_in_episodic_outcome(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """Errors containing angle brackets are sanitized before storing in episodic memory."""
        mock_bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
            return_value=ClaudeResult(
                content="",
                input_tokens=0,
                output_tokens=0,
                stop_reason="",
                tool_use_history=[],
                success=False,
                error="<script>alert('xss')</script>",
                duration_ms=10.0,
            )
        )
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Task with XSS error")
        await cortex.run(task)
        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        assert "<script>" not in episodes[0].outcome
        assert "&lt;script&gt;" in episodes[0].outcome
        await cortex.shutdown()

    async def test_perceive_sanitizes_task_description(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """_perceive() must sanitize task.description to prevent prompt injection."""
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="<script>alert('xss')</script>")
        await cortex.run(task)
        context = await cortex.working.get_context()
        assert "<script>" not in context
        assert "&lt;script&gt;" in context
        await cortex.shutdown()


class TestCortexObserveStep:
    async def test_observe_returns_result_unchanged(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """Phase 1 _observe() is a pass-through — result should be unchanged."""
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Test observe pass-through")
        result = await cortex.run(task)
        assert result.success is True
        assert result.output != ""
        await cortex.shutdown()

    async def test_observe_is_called_during_cycle(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """Verify _observe() is invoked as part of the cognitive cycle."""
        cortex = await Cortex.create(brain_config, mock_bridge)
        observe_called = False
        original_observe = cortex._observe

        async def tracking_observe(
            task: Task, result: TaskResult, recalled_episodes: list | None = None
        ) -> TaskResult:
            nonlocal observe_called
            observe_called = True
            return await original_observe(task, result, recalled_episodes=recalled_episodes or [])

        cortex._observe = tracking_observe  # type: ignore[method-assign]
        await cortex.run(Task(description="Track observe call"))
        assert observe_called is True
        await cortex.shutdown()

    async def test_observe_exception_propagates_to_error_result(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        """If _observe() raises, the cognitive cycle returns a failed TaskResult."""
        cortex = await Cortex.create(brain_config, mock_bridge)

        async def failing_observe(
            task: Task, result: TaskResult, recalled_episodes: list | None = None
        ) -> TaskResult:
            msg = "Observation failed"
            raise RuntimeError(msg)

        cortex._observe = failing_observe  # type: ignore[method-assign]
        result = await cortex.run(Task(description="Observe will fail"))
        assert result.success is False
        assert "Observation failed" in (result.error or "")
        await cortex.shutdown()


class TestSanitizeXml:
    def test_escapes_script_tags(self) -> None:
        from claudedev.utils.sanitize import sanitize_xml

        assert (
            sanitize_xml("<script>alert('xss')</script>")
            == "&lt;script&gt;alert('xss')&lt;/script&gt;"
        )

    def test_escapes_system_tags(self) -> None:
        from claudedev.utils.sanitize import sanitize_xml

        assert sanitize_xml("<system>override</system>") == "&lt;system&gt;override&lt;/system&gt;"

    def test_escapes_nested_tags(self) -> None:
        from claudedev.utils.sanitize import sanitize_xml

        assert sanitize_xml("<a><b><c>") == "&lt;a&gt;&lt;b&gt;&lt;c&gt;"

    def test_no_tags_unchanged(self) -> None:
        from claudedev.utils.sanitize import sanitize_xml

        assert sanitize_xml("no tags here") == "no tags here"

    def test_empty_string(self) -> None:
        from claudedev.utils.sanitize import sanitize_xml

        assert sanitize_xml("") == ""

    def test_already_escaped_passes_through_unchanged(self) -> None:
        from claudedev.utils.sanitize import sanitize_xml

        # &lt; contains no < or >, so it stays unchanged
        assert sanitize_xml("&lt;script&gt;") == "&lt;script&gt;"

    def test_mixed_angle_brackets(self) -> None:
        from claudedev.utils.sanitize import sanitize_xml

        assert sanitize_xml("a < b > c") == "a &lt; b &gt; c"


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


class TestObserve:
    async def test_observe_no_prior_memory(
        self,
        brain_config: BrainConfig,
        mock_bridge: ClaudeBridge,
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="brand new unique task xyz123")
        result = TaskResult(
            task_id=task.id,
            success=True,
            output="done",
            confidence=0.8,
        )
        observed = await cortex._observe(task, result, recalled_episodes=[])
        assert observed.confidence == 0.8
        await cortex.shutdown()

    async def test_observe_success_mismatch_penalizes(
        self,
        brain_config: BrainConfig,
        mock_bridge: ClaudeBridge,
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        from claudedev.brain.models import EpisodicMemory

        episode = EpisodicMemory(
            task="fix auth bug",
            approach="patched validation",
            outcome="success",
            confidence=0.9,
        )
        await cortex.episodic.store(episode)
        task = Task(description="fix auth bug")
        result = TaskResult(
            task_id=task.id,
            success=False,
            output="failed",
            error="timeout",
            confidence=0.9,
        )
        recalled = await cortex.episodic.search(task.description, limit=3)
        observed = await cortex._observe(task, result, recalled_episodes=recalled)
        assert observed.confidence < 0.9
        await cortex.shutdown()

    async def test_observe_matching_prediction_unchanged(
        self,
        brain_config: BrainConfig,
        mock_bridge: ClaudeBridge,
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        from claudedev.brain.models import EpisodicMemory

        episode = EpisodicMemory(
            task="run tests",
            approach="pytest",
            outcome="success",
            confidence=0.85,
        )
        await cortex.episodic.store(episode)
        task = Task(description="run tests")
        result = TaskResult(
            task_id=task.id,
            success=True,
            output="pass",
            confidence=0.85,
        )
        recalled = await cortex.episodic.search(task.description, limit=3)
        observed = await cortex._observe(task, result, recalled_episodes=recalled)
        assert observed.confidence == 0.85
        await cortex.shutdown()

    async def test_observe_with_steering_slot(
        self,
        brain_config: BrainConfig,
        mock_bridge: ClaudeBridge,
    ) -> None:
        """When steering slot has content, _observe() should detect it."""
        cortex = await Cortex.create(brain_config, mock_bridge)
        from claudedev.brain.memory.working import SlotPriority

        await cortex.working.add_slot(
            "steering",
            "[CLAUDEDEV STEERING - PIVOT]\nFrom the project owner: Use Redis\nAdjust accordingly.",
            SlotPriority.HIGH,
        )
        task = Task(description="implement caching")
        result = TaskResult(
            task_id=task.id,
            success=True,
            output="done",
            confidence=0.8,
        )
        observed = await cortex._observe(task, result, recalled_episodes=[])
        # Result should pass through (steering doesn't modify confidence)
        assert observed.confidence == 0.8
        await cortex.shutdown()
