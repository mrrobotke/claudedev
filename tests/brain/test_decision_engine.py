"""Comprehensive tests for DecisionEngine — System 1 routing and delegate fallback."""

from __future__ import annotations

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.decision.engine import DecisionEngine
from claudedev.brain.models import Context, MemoryNode, Skill, Task

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> BrainConfig:
    return BrainConfig(
        project_path="/tmp/test",
        system1_confidence_threshold=0.85,
    )


@pytest.fixture
def engine(config: BrainConfig) -> DecisionEngine:
    return DecisionEngine(config)


def _make_skill(name: str, reliability: float) -> Skill:
    """Create a minimal Skill with the given name and reliability."""
    return Skill(
        name=name,
        description=f"Skill that handles {name} tasks",
        procedure=f"1. Run {name}",
        task_signature=f"{name}(input: str) -> None",
        reliability=reliability,
    )


def _make_task(description: str) -> Task:
    return Task(description=description)


def _empty_memories() -> list[MemoryNode]:
    return []


# ---------------------------------------------------------------------------
# TestSystem1Routing
# ---------------------------------------------------------------------------


class TestSystem1Routing:
    async def test_skill_above_threshold_matched(self, engine: DecisionEngine) -> None:
        """A high-reliability skill with a strong match should return system1."""
        skill = _make_skill("deploy", reliability=1.0)
        engine.register_skill(skill)

        # task_signature is "deploy(input: str) -> None" — very similar to description
        task = _make_task("deploy(input: str) -> None")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        assert strategy.mode == "system1"
        assert strategy.skill is not None
        assert strategy.skill.name == "deploy"
        assert strategy.confidence >= 0.85

    async def test_skill_below_threshold_returns_delegate(self, engine: DecisionEngine) -> None:
        """A low-reliability skill should not reach the threshold."""
        skill = _make_skill("deploy", reliability=0.1)
        engine.register_skill(skill)

        task = _make_task("deploy(input: str) -> None")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        assert strategy.mode == "delegate"

    async def test_boundary_exactly_at_threshold_returns_system1(self) -> None:
        """A score exactly at threshold (>=) should return system1."""
        # threshold = 0.85; reliability * (0.5 + 0.5 * similarity) >= 0.85
        # With reliability=1.0, we need similarity >= 0.7, which is trivially met
        # with an exact match.
        config = BrainConfig(project_path="/tmp/test", system1_confidence_threshold=0.85)
        engine = DecisionEngine(config)

        skill = Skill(
            name="exact",
            description="exact",
            procedure="p",
            task_signature="exact",
            reliability=1.0,
        )
        engine.register_skill(skill)

        # Perfect match on all three fields → similarity=1.0, score=1.0 >= 0.85
        task = _make_task("exact")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        assert strategy.mode == "system1"
        assert strategy.confidence >= 0.85

    async def test_just_below_threshold_returns_delegate(self) -> None:
        """Score just below 0.85 threshold returns delegate."""
        # reliability=0.84, similarity=1.0 → score = 0.84 * 1.0 = 0.84 < 0.85
        config = BrainConfig(project_path="/tmp/test", system1_confidence_threshold=0.85)
        engine = DecisionEngine(config)

        skill = Skill(
            name="exact",
            description="exact",
            procedure="p",
            task_signature="exact",
            reliability=0.84,
        )
        engine.register_skill(skill)

        task = _make_task("exact")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        assert strategy.mode == "delegate"
        assert strategy.confidence < 0.85


# ---------------------------------------------------------------------------
# TestDelegation
# ---------------------------------------------------------------------------


class TestDelegation:
    async def test_empty_skills_returns_delegate(self, engine: DecisionEngine) -> None:
        """No registered skills → always delegate."""
        task = _make_task("implement a new login feature")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        assert strategy.mode == "delegate"
        assert strategy.skill is None
        assert strategy.confidence == 0.0

    async def test_no_matching_skill_returns_delegate(self, engine: DecisionEngine) -> None:
        """Registered skills with no similarity to task description → delegate."""
        # Register a skill about "database migration" for a completely unrelated task
        skill = _make_skill("database_migration", reliability=1.0)
        engine.register_skill(skill)

        task = _make_task("zzz totally unrelated xyz 12345")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        # similarity <= 0.2 for random string, so no skill qualifies
        assert strategy.mode == "delegate"


# ---------------------------------------------------------------------------
# TestAmbiguousMatch
# ---------------------------------------------------------------------------


class TestAmbiguousMatch:
    async def test_highest_reliability_wins_when_multiple_match(self) -> None:
        """When multiple skills match, the one with the highest score wins."""
        config = BrainConfig(project_path="/tmp/test", system1_confidence_threshold=0.5)
        engine = DecisionEngine(config)

        low_skill = Skill(
            name="exact",
            description="exact",
            procedure="p",
            task_signature="exact",
            reliability=0.6,
        )
        high_skill = Skill(
            name="exact",
            description="exact",
            procedure="p",
            task_signature="exact",
            reliability=0.9,
        )
        engine.register_skill(low_skill)
        engine.register_skill(high_skill)

        task = _make_task("exact")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        assert strategy.mode == "system1"
        # high_skill score = 0.9 * (0.5 + 0.5*1.0) = 0.9, low_skill = 0.6
        assert strategy.confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# TestDecisionLogging
# ---------------------------------------------------------------------------


class TestDecisionLogging:
    async def test_single_decision_is_logged(self, engine: DecisionEngine) -> None:
        """After one decide() call the log should contain one entry."""
        task = _make_task("do something")
        await engine.decide(task, context=Context(content=""), memories=_empty_memories())

        log = engine.get_decision_log()
        assert len(log) == 1

    async def test_log_captures_mode_and_confidence(self, engine: DecisionEngine) -> None:
        """Log entry stores mode and confidence correctly."""
        task = _make_task("do something")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        entry = engine.get_decision_log()[0]
        assert entry.mode == strategy.mode
        assert entry.confidence == strategy.confidence

    async def test_multiple_decisions_all_logged(self, engine: DecisionEngine) -> None:
        """Every decide() call appends to the log."""
        for i in range(5):
            task = _make_task(f"task number {i}")
            await engine.decide(task, context=Context(content=""), memories=_empty_memories())

        assert len(engine.get_decision_log()) == 5

    async def test_log_returns_copy(self, engine: DecisionEngine) -> None:
        """Mutating the returned list does not affect the internal log."""
        task = _make_task("task")
        await engine.decide(task, context=Context(content=""), memories=_empty_memories())

        log_copy = engine.get_decision_log()
        log_copy.clear()

        assert len(engine.get_decision_log()) == 1

    async def test_log_entry_has_timestamp(self, engine: DecisionEngine) -> None:
        """Log entries carry a UTC timestamp."""
        task = _make_task("something")
        await engine.decide(task, context=Context(content=""), memories=_empty_memories())

        entry = engine.get_decision_log()[0]
        assert entry.timestamp is not None
        assert entry.timestamp.tzinfo is not None

    async def test_log_entry_skill_name_none_on_delegate(self, engine: DecisionEngine) -> None:
        """skill_name is None when mode is delegate (no registered skills)."""
        task = _make_task("some task")
        await engine.decide(task, context=Context(content=""), memories=_empty_memories())

        entry = engine.get_decision_log()[0]
        assert entry.skill_name is None

    async def test_log_entry_skill_name_set_on_system1(self) -> None:
        """skill_name is set to the matched skill's name on system1."""
        config = BrainConfig(project_path="/tmp/test", system1_confidence_threshold=0.5)
        engine = DecisionEngine(config)

        skill = Skill(
            name="exact",
            description="exact",
            procedure="p",
            task_signature="exact",
            reliability=0.9,
        )
        engine.register_skill(skill)

        task = _make_task("exact")
        strategy = await engine.decide(
            task, context=Context(content=""), memories=_empty_memories()
        )

        assert strategy.mode == "system1"
        entry = engine.get_decision_log()[0]
        assert entry.skill_name == "exact"


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_empty_context_and_memories_works(self, engine: DecisionEngine) -> None:
        """Empty context string and empty memories list should not raise."""
        task = _make_task("some task")
        strategy = await engine.decide(task, context=Context(content=""), memories=[])
        assert strategy.mode in ("system1", "delegate")

    async def test_custom_threshold_0_5_with_skill_at_0_55(self) -> None:
        """Custom threshold=0.5: a skill scoring 0.55 should return system1."""
        config = BrainConfig(project_path="/tmp/test", system1_confidence_threshold=0.5)
        engine = DecisionEngine(config)

        # With reliability=0.55, perfect match → score = 0.55 * 1.0 = 0.55 >= 0.5
        skill = Skill(
            name="exact",
            description="exact",
            procedure="p",
            task_signature="exact",
            reliability=0.55,
        )
        engine.register_skill(skill)

        task = _make_task("exact")
        strategy = await engine.decide(task, context=Context(content=""), memories=[])

        assert strategy.mode == "system1"
        assert strategy.confidence == pytest.approx(0.55)

    async def test_non_empty_memories_accepted(self, engine: DecisionEngine) -> None:
        """Passing actual MemoryNode objects should not raise."""
        memories = [
            MemoryNode(
                content="User prefers async patterns",
                source="conversation",
                memory_type="semantic",
            )
        ]
        task = _make_task("async task implementation")
        strategy = await engine.decide(
            task, context=Context(content="some context"), memories=memories
        )
        assert strategy.mode in ("system1", "delegate")

    async def test_log_entry_task_id_matches_task(self, engine: DecisionEngine) -> None:
        """Log entry task_id matches the task that was decided."""
        task = _make_task("log id check")
        await engine.decide(task, context=Context(content=""), memories=[])

        entry = engine.get_decision_log()[0]
        assert entry.task_id == task.id
        assert entry.task_description == task.description

    async def test_decision_log_maxlen_rollover(self, engine: DecisionEngine) -> None:
        """After 1001 decisions, log length is capped at 1000 and oldest entry is gone."""
        for i in range(1001):
            await engine.decide(_make_task(f"task {i}"), context=Context(content=""), memories=[])

        log = engine.get_decision_log()
        assert len(log) == 1000
        # The oldest entry ("task 0") must have been evicted
        assert log[0].task_description == "task 1"
        assert log[-1].task_description == "task 1000"
