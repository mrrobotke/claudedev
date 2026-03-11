"""Tests for NEXUS brain domain models."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from claudedev.brain.models import (
    Context,
    EpisodicMemory,
    MemoryNode,
    Skill,
    Strategy,
    Task,
    TaskResult,
)

# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class TestTask:
    def test_minimal_creation(self) -> None:
        task = Task(description="fix the login bug")
        assert task.description == "fix the login bug"

    def test_auto_generated_id(self) -> None:
        task = Task(description="some task")
        assert task.id
        assert isinstance(task.id, str)
        assert len(task.id) == 32  # uuid4().hex is 32 hex chars

    def test_unique_ids(self) -> None:
        t1 = Task(description="task one")
        t2 = Task(description="task two")
        assert t1.id != t2.id

    def test_created_at_is_utc(self) -> None:
        task = Task(description="something")
        assert task.created_at.tzinfo is not None
        assert task.created_at.tzinfo == UTC

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError, match="description"):
            Task(description="")

    def test_whitespace_description_rejected(self) -> None:
        with pytest.raises(ValidationError, match="description"):
            Task(description="   ")

    def test_explicit_id_accepted(self) -> None:
        task = Task(id="custom123", description="task")
        assert task.id == "custom123"


# ---------------------------------------------------------------------------
# TaskResult
# ---------------------------------------------------------------------------


class TestTaskResult:
    def test_successful_result(self) -> None:
        result = TaskResult(
            task_id="abc123",
            success=True,
            output="Implementation complete",
        )
        assert result.task_id == "abc123"
        assert result.success is True
        assert result.output == "Implementation complete"

    def test_failed_result_with_error(self) -> None:
        result = TaskResult(
            task_id="xyz",
            success=False,
            output="",
            error="timeout exceeded",
        )
        assert result.success is False
        assert result.error == "timeout exceeded"

    def test_default_files_changed_empty(self) -> None:
        result = TaskResult(task_id="t", success=True, output="ok")
        assert result.files_changed == []

    def test_default_tools_used_empty(self) -> None:
        result = TaskResult(task_id="t", success=True, output="ok")
        assert result.tools_used == []

    def test_default_error_is_none(self) -> None:
        result = TaskResult(task_id="t", success=True, output="ok")
        assert result.error is None

    def test_default_duration_ms_is_zero(self) -> None:
        result = TaskResult(task_id="t", success=True, output="ok")
        assert result.duration_ms == 0.0

    def test_default_confidence_is_zero(self) -> None:
        result = TaskResult(task_id="t", success=True, output="ok")
        assert result.confidence == 0.0

    def test_files_changed_populated(self) -> None:
        result = TaskResult(
            task_id="t",
            success=True,
            output="done",
            files_changed=["src/foo.py", "src/bar.py"],
        )
        assert len(result.files_changed) == 2

    def test_tools_used_populated(self) -> None:
        result = TaskResult(
            task_id="t",
            success=True,
            output="done",
            tools_used=["read_file", "write_file"],
        )
        assert result.tools_used == ["read_file", "write_file"]

    def test_full_result(self) -> None:
        result = TaskResult(
            task_id="fulltest",
            success=True,
            output="All done",
            files_changed=["a.py"],
            tools_used=["grep"],
            error=None,
            duration_ms=123.45,
            confidence=0.95,
        )
        assert result.duration_ms == 123.45
        assert result.confidence == 0.95

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskResult(task_id="t", success=True, output="ok", confidence=1.1)

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskResult(task_id="t", success=True, output="ok", confidence=-0.1)

    def test_confidence_at_one_accepted(self) -> None:
        result = TaskResult(task_id="t", success=True, output="ok", confidence=1.0)
        assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class TestSkill:
    def test_minimal_creation(self) -> None:
        skill = Skill(
            name="add_tests",
            description="Adds pytest tests",
            procedure="1. Read file\n2. Write tests",
            task_signature="add_tests(module: str) -> None",
        )
        assert skill.name == "add_tests"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="name"):
            Skill(
                name="",
                description="desc",
                procedure="proc",
                task_signature="sig",
            )

    def test_whitespace_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="name"):
            Skill(
                name="   ",
                description="desc",
                procedure="proc",
                task_signature="sig",
            )

    def test_default_preconditions_empty(self) -> None:
        skill = Skill(
            name="skill",
            description="d",
            procedure="p",
            task_signature="s",
        )
        assert skill.preconditions == []

    def test_default_reliability(self) -> None:
        skill = Skill(
            name="skill",
            description="d",
            procedure="p",
            task_signature="s",
        )
        assert skill.reliability == 0.5

    def test_created_at_utc(self) -> None:
        skill = Skill(
            name="skill",
            description="d",
            procedure="p",
            task_signature="s",
        )
        assert skill.created_at.tzinfo is not None

    def test_custom_reliability(self) -> None:
        skill = Skill(
            name="skill",
            description="d",
            procedure="p",
            task_signature="s",
            reliability=0.95,
        )
        assert skill.reliability == 0.95

    def test_reliability_bounds_zero(self) -> None:
        skill = Skill(
            name="s",
            description="d",
            procedure="p",
            task_signature="t",
            reliability=0.0,
        )
        assert skill.reliability == 0.0

    def test_reliability_bounds_one(self) -> None:
        skill = Skill(
            name="s",
            description="d",
            procedure="p",
            task_signature="t",
            reliability=1.0,
        )
        assert skill.reliability == 1.0

    def test_reliability_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Skill(
                name="s",
                description="d",
                procedure="p",
                task_signature="t",
                reliability=1.1,
            )

    def test_reliability_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Skill(
                name="s",
                description="d",
                procedure="p",
                task_signature="t",
                reliability=-0.1,
            )

    def test_preconditions_populated(self) -> None:
        skill = Skill(
            name="s",
            description="d",
            procedure="p",
            task_signature="t",
            preconditions=["file exists", "tests pass"],
        )
        assert len(skill.preconditions) == 2


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


def _make_skill() -> Skill:
    return Skill(
        name="deploy",
        description="Deploy the service",
        procedure="1. Build\n2. Push",
        task_signature="deploy(env: str) -> None",
    )


class TestStrategy:
    def test_system1_mode_with_skill(self) -> None:
        skill = _make_skill()
        strategy = Strategy(
            mode="system1",
            confidence=0.9,
            skill=skill,
            reason="Known pattern",
        )
        assert strategy.mode == "system1"
        assert strategy.skill is not None
        assert strategy.skill.name == "deploy"

    def test_delegate_mode_without_skill(self) -> None:
        strategy = Strategy(
            mode="delegate",
            confidence=0.4,
            skill=None,
            reason="Novel task",
        )
        assert strategy.mode == "delegate"
        assert strategy.skill is None

    def test_default_skill_is_none(self) -> None:
        strategy = Strategy(mode="delegate", confidence=0.5, reason="r")
        assert strategy.skill is None

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Strategy(mode="auto", confidence=0.5, reason="r")

    def test_confidence_zero(self) -> None:
        strategy = Strategy(mode="delegate", confidence=0.0, reason="r")
        assert strategy.confidence == 0.0

    def test_confidence_one(self) -> None:
        strategy = Strategy(mode="delegate", confidence=1.0, reason="r")
        assert strategy.confidence == 1.0

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Strategy(mode="delegate", confidence=-0.1, reason="r")

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Strategy(mode="delegate", confidence=1.1, reason="r")

    def test_reason_stored(self) -> None:
        strategy = Strategy(mode="delegate", confidence=0.3, reason="complex reasoning here")
        assert strategy.reason == "complex reasoning here"

    def test_system1_without_skill_rejected(self) -> None:
        with pytest.raises(ValidationError, match="system1 mode requires a skill"):
            Strategy(mode="system1", confidence=0.9, reason="pattern match")

    def test_delegate_without_skill_accepted(self) -> None:
        strategy = Strategy(mode="delegate", confidence=0.3, reason="novel")
        assert strategy.skill is None


# ---------------------------------------------------------------------------
# MemoryNode
# ---------------------------------------------------------------------------


class TestMemoryNode:
    def test_minimal_creation(self) -> None:
        node = MemoryNode(
            content="User prefers async patterns",
            source="conversation",
            memory_type="semantic",
        )
        assert node.content == "User prefers async patterns"
        assert node.source == "conversation"

    def test_auto_generated_id(self) -> None:
        node = MemoryNode(
            content="some content",
            source="src",
            memory_type="episodic",
        )
        assert node.id
        assert len(node.id) == 32

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError, match="content"):
            MemoryNode(content="", source="src", memory_type="semantic")

    def test_whitespace_content_rejected(self) -> None:
        with pytest.raises(ValidationError, match="content"):
            MemoryNode(content="  ", source="src", memory_type="semantic")

    def test_default_consolidated_false(self) -> None:
        node = MemoryNode(content="c", source="s", memory_type="procedural")
        assert node.consolidated is False

    def test_default_importance(self) -> None:
        node = MemoryNode(content="c", source="s", memory_type="episodic")
        assert node.importance == 0.5

    def test_timestamp_utc(self) -> None:
        node = MemoryNode(content="c", source="s", memory_type="semantic")
        assert node.timestamp.tzinfo is not None

    def test_all_memory_types(self) -> None:
        for mtype in ("episodic", "semantic", "procedural"):
            node = MemoryNode(content="c", source="s", memory_type=mtype)
            assert node.memory_type == mtype

    def test_invalid_memory_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryNode(
                content="c",
                source="s",
                memory_type="working",
            )

    def test_consolidated_can_be_set_true(self) -> None:
        node = MemoryNode(
            content="c",
            source="s",
            memory_type="episodic",
            consolidated=True,
        )
        assert node.consolidated is True

    def test_importance_bounds(self) -> None:
        n0 = MemoryNode(content="c", source="s", memory_type="episodic", importance=0.0)
        n1 = MemoryNode(content="c", source="s", memory_type="episodic", importance=1.0)
        assert n0.importance == 0.0
        assert n1.importance == 1.0

    def test_importance_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryNode(content="c", source="s", memory_type="episodic", importance=1.1)

    def test_importance_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryNode(content="c", source="s", memory_type="episodic", importance=-0.1)


# ---------------------------------------------------------------------------
# EpisodicMemory
# ---------------------------------------------------------------------------


class TestEpisodicMemory:
    def test_minimal_creation(self) -> None:
        em = EpisodicMemory(
            task="implement login",
            approach="used JWT tokens",
            outcome="success",
        )
        assert em.task == "implement login"
        assert em.approach == "used JWT tokens"
        assert em.outcome == "success"

    def test_auto_generated_id(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o")
        assert em.id
        assert len(em.id) == 32

    def test_default_tools_used_empty(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o")
        assert em.tools_used == []

    def test_default_files_modified_empty(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o")
        assert em.files_modified == []

    def test_default_error_messages_empty(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o")
        assert em.error_messages == []

    def test_default_confidence(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o")
        assert em.confidence == 0.5

    def test_default_consolidated_false(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o")
        assert em.consolidated is False

    def test_timestamp_utc(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o")
        assert em.timestamp.tzinfo is not None

    def test_full_creation_all_fields(self) -> None:
        em = EpisodicMemory(
            task="deploy service",
            approach="blue-green deployment",
            outcome="deployed successfully",
            tools_used=["kubectl", "helm"],
            files_modified=["k8s/deployment.yaml"],
            error_messages=["warning: deprecated API"],
            confidence=0.92,
            consolidated=True,
        )
        assert em.tools_used == ["kubectl", "helm"]
        assert em.files_modified == ["k8s/deployment.yaml"]
        assert em.error_messages == ["warning: deprecated API"]
        assert em.confidence == 0.92
        assert em.consolidated is True

    def test_confidence_bounds_zero(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o", confidence=0.0)
        assert em.confidence == 0.0

    def test_confidence_bounds_one(self) -> None:
        em = EpisodicMemory(task="t", approach="a", outcome="o", confidence=1.0)
        assert em.confidence == 1.0

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EpisodicMemory(task="t", approach="a", outcome="o", confidence=1.1)

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EpisodicMemory(task="t", approach="a", outcome="o", confidence=-0.1)

    def test_unique_ids(self) -> None:
        e1 = EpisodicMemory(task="t", approach="a", outcome="o")
        e2 = EpisodicMemory(task="t", approach="a", outcome="o")
        assert e1.id != e2.id


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class TestContext:
    def test_minimal_creation(self) -> None:
        ctx = Context(content="some context")
        assert ctx.content == "some context"

    def test_default_token_count_zero(self) -> None:
        ctx = Context(content="c")
        assert ctx.token_count == 0

    def test_default_slots_empty(self) -> None:
        ctx = Context(content="c")
        assert ctx.slots == []

    def test_negative_token_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Context(content="c", token_count=-1)

    def test_full_creation(self) -> None:
        ctx = Context(content="ctx", token_count=100, slots=["system_prompt", "task_context"])
        assert ctx.token_count == 100
        assert len(ctx.slots) == 2
