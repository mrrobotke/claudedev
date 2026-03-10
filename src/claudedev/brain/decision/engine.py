"""Decision engine — System 1 fast pattern matching and delegate fallback."""

from __future__ import annotations

import difflib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from claudedev.brain.models import MemoryNode, Skill, Strategy, Task

if TYPE_CHECKING:
    from claudedev.brain.config import BrainConfig

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class DecisionLog(BaseModel):
    """Record of a single routing decision made by the DecisionEngine."""

    task_id: str
    task_description: str
    mode: str
    confidence: float
    skill_name: str | None
    reason: str
    timestamp: datetime = Field(default_factory=_now)


class DecisionEngine:
    """Routes tasks to System 1 (fast pattern match) or delegate execution.

    System 1 fires when a registered skill's reliability-weighted similarity
    score meets or exceeds ``config.system1_confidence_threshold``.  All
    other tasks fall through to delegate mode.

    Args:
        config: Immutable brain configuration.
    """

    def __init__(self, config: BrainConfig) -> None:
        self._threshold: float = config.system1_confidence_threshold
        self._skills: list[Skill] = []
        self._decision_log: list[DecisionLog] = []

    # ------------------------------------------------------------------
    # Skill registration
    # ------------------------------------------------------------------

    def register_skill(self, skill: Skill) -> None:
        """Register a skill for System 1 pattern matching.

        Args:
            skill: The Skill to add to the matching pool.
        """
        self._skills.append(skill)
        logger.info(
            "skill_registered",
            skill_name=skill.name,
            reliability=skill.reliability,
            total_skills=len(self._skills),
        )

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    async def decide(
        self,
        task: Task,
        context: str,
        memories: list[MemoryNode],
    ) -> Strategy:
        """Select the execution strategy for *task*.

        Computes a reliability-weighted similarity score for each registered
        skill.  If the best score is at or above the threshold, returns a
        ``system1`` strategy with the matched skill; otherwise returns a
        ``delegate`` strategy.

        Args:
            task: The work item to route.
            context: Free-text context string (not used for matching but
                included for future extension).
            memories: Recalled memory nodes (not used for matching but
                included for future extension).

        Returns:
            A :class:`~claudedev.brain.models.Strategy` instance.
        """
        description_lower = task.description.lower()

        best_skill: Skill | None = None
        best_score: float = 0.0

        for skill in self._skills:
            sig_sim = difflib.SequenceMatcher(
                None, description_lower, skill.task_signature.lower()
            ).ratio()
            desc_sim = difflib.SequenceMatcher(
                None, description_lower, skill.description.lower()
            ).ratio()
            name_sim = difflib.SequenceMatcher(
                None, description_lower, skill.name.lower()
            ).ratio()

            similarity = max(sig_sim, desc_sim, name_sim)

            if similarity > 0.2:
                score = skill.reliability * (0.5 + 0.5 * similarity)
                if score > best_score:
                    best_score = score
                    best_skill = skill

        if best_skill is not None and best_score >= self._threshold:
            strategy = Strategy(
                mode="system1",
                confidence=best_score,
                skill=best_skill,
                reason=(
                    f"Skill '{best_skill.name}' matched with score {best_score:.3f} "
                    f"(threshold {self._threshold:.3f})"
                ),
            )
        else:
            strategy = Strategy(
                mode="delegate",
                confidence=best_score,
                skill=None,
                reason=(
                    "No skill met the confidence threshold "
                    f"(best={best_score:.3f}, threshold={self._threshold:.3f})"
                ),
            )

        self._decision_log.append(
            DecisionLog(
                task_id=task.id,
                task_description=task.description,
                mode=strategy.mode,
                confidence=strategy.confidence,
                skill_name=best_skill.name if best_skill is not None else None,
                reason=strategy.reason,
            )
        )

        logger.info(
            "decision_made",
            task_id=task.id,
            mode=strategy.mode,
            confidence=strategy.confidence,
            skill=strategy.skill.name if strategy.skill is not None else None,
        )

        return strategy

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_decision_log(self) -> list[DecisionLog]:
        """Return a shallow copy of the decision log.

        Returns:
            List of all :class:`DecisionLog` entries recorded so far.
        """
        return list(self._decision_log)
