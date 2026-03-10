"""Cortex — the NEXUS brain orchestrator.

Implements the core cognitive cycle:
    Perceive -> Recall -> Decide -> Act -> Observe -> Remember

Never crashes. Always returns a TaskResult.
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

import structlog

from claudedev.brain.decision.engine import DecisionEngine
from claudedev.brain.memory.episodic import EpisodicStore
from claudedev.brain.memory.working import SlotPriority, WorkingMemory
from claudedev.brain.models import EpisodicMemory, MemoryNode, Strategy, Task, TaskResult

if TYPE_CHECKING:
    from claudedev.brain.config import BrainConfig
    from claudedev.brain.integration.claude_bridge import ClaudeBridge

logger = structlog.get_logger(__name__)


class Cortex:
    """The NEXUS brain — central cognitive loop.

    Use ``Cortex.create()`` for construction (async initialisation required).
    """

    def __init__(
        self,
        config: BrainConfig,
        bridge: ClaudeBridge,
        working: WorkingMemory,
        episodic: EpisodicStore,
        decision: DecisionEngine,
    ) -> None:
        self._config = config
        self._bridge = bridge
        self.working = working
        self.episodic = episodic
        self._decision = decision

    @classmethod
    async def create(cls, config: BrainConfig, bridge: ClaudeBridge) -> Cortex:
        """Async factory — initialises all subsystems."""
        working = WorkingMemory(max_tokens=config.max_working_memory_tokens)

        project_hash = hashlib.sha256(config.project_path.encode()).hexdigest()[:12]
        episodic = EpisodicStore(db_path=f"{config.memory_dir}/{project_hash}/episodic.db")
        await episodic.initialize()

        decision = DecisionEngine(config)

        logger.info(
            "cortex_initialized",
            project=config.project_path,
            model=config.claude_model,
        )
        return cls(config, bridge, working, episodic, decision)

    async def run(self, task: Task) -> TaskResult:
        """Execute the full cognitive cycle for a task.

        Never raises — returns TaskResult with success=False on errors.
        """
        log = logger.bind(task_id=task.id, task=task.description[:60])
        start = time.perf_counter()

        try:
            log.info("perceive_start")
            context = await self._perceive(task)

            log.info("recall_start")
            memories = await self._recall(task)

            log.info("decide_start")
            strategy = await self._decision.decide(task, context, memories)

            log.info("act_start", mode=strategy.mode)
            result = await self._act(task, strategy, context)

            log.info("remember_start")
            await self._remember(task, result, strategy)

            elapsed_ms = (time.perf_counter() - start) * 1000
            result.duration_ms = elapsed_ms
            log.info(
                "cognitive_cycle_complete",
                success=result.success,
                ms=f"{elapsed_ms:.1f}",
            )
            return result

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log.error("cognitive_cycle_failed", error=str(exc))
            return TaskResult(
                task_id=task.id,
                success=False,
                output="",
                error=str(exc),
                duration_ms=elapsed_ms,
            )

    async def _perceive(self, task: Task) -> str:
        """Build working memory context for the current task."""
        await self.working.add_slot(
            "system_prompt",
            "You are the NEXUS brain, an autonomous coding assistant.",
            SlotPriority.CRITICAL,
        )
        await self.working.add_slot(
            "task_context",
            f"Current task: {task.description}",
            SlotPriority.CRITICAL,
        )
        return await self.working.get_context()

    async def _recall(self, task: Task) -> list[MemoryNode]:
        """Search episodic memory for relevant past experiences."""
        episodes = await self.episodic.search(task.description, limit=5)
        if episodes:
            recall_text = "\n".join(f"- [{e.outcome}] {e.task}: {e.approach}" for e in episodes)
            await self.working.add_slot(
                "recalled_memories",
                recall_text,
                SlotPriority.NORMAL,
            )
        return []

    async def _act(self, task: Task, strategy: Strategy, context: str) -> TaskResult:
        """Execute the chosen strategy via the Claude bridge."""
        if strategy.mode == "system1" and strategy.skill is not None:
            prompt = (
                f"Execute this procedure:\n{strategy.skill.procedure}\n\n"
                f"For task: {task.description}"
            )
        else:
            prompt = task.description

        result = await self._bridge.execute_task(
            task=prompt,
            system_prompt=context,
        )

        return TaskResult(
            task_id=task.id,
            success=result.success,
            output=result.content,
            tools_used=result.tool_use_history,
            error=result.error,
            confidence=strategy.confidence,
        )

    async def _remember(self, task: Task, result: TaskResult, strategy: Strategy) -> None:
        """Store the task outcome as an episodic memory."""
        episode = EpisodicMemory(
            task=task.description,
            approach=f"{strategy.mode}: {strategy.reason}",
            outcome=("success" if result.success else f"failed: {result.error or 'unknown'}"),
            tools_used=result.tools_used,
            files_modified=result.files_changed,
            confidence=strategy.confidence,
        )
        await self.episodic.store(episode)

    async def shutdown(self) -> None:
        """Release resources held by the brain."""
        await self.episodic.close()
        logger.info("cortex_shutdown")
