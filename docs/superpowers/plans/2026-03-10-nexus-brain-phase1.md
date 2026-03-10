# NEXUS Brain Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the NEXUS brain's cognitive foundation — 6 modules that enable the Perceive->Recall->Decide->Act->Observe->Remember loop.

**Architecture:** Dependency-ordered build: shared config+models first, then parallel memory+bridge, then decision engine, then cortex orchestrator, finally integration tests+benchmarks. Each module is async, fully typed, Pydantic v2, structlog-instrumented.

**Tech Stack:** Python 3.13, Pydantic v2, anthropic SDK, aiosqlite, tiktoken, structlog, pytest+pytest-asyncio

---

## Chunk 1: Foundation (Config + Models + Dependencies)

### Task 1: Add tiktoken dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add tiktoken to dependencies**

Add to `[tool.poetry.dependencies]`:
```toml
tiktoken = ">=0.9.0"
```

- [ ] **Step 2: Install**

Run: `poetry lock --no-update && poetry install`

- [ ] **Step 3: Verify import works**

Run: `python -c "import tiktoken; print(tiktoken.encoding_for_model('claude-sonnet-4-20250514'))"`
Expected: encoding object returned without error

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "deps: add tiktoken for accurate token counting"
```

---

### Task 2: Create brain package and BrainConfig

**Files:**
- Create: `src/claudedev/brain/__init__.py`
- Create: `src/claudedev/brain/config.py`
- Create: `tests/brain/__init__.py`
- Create: `tests/brain/test_config.py`

- [ ] **Step 1: Create brain package init**

```python
# src/claudedev/brain/__init__.py
"""NEXUS Brain — cognitive architecture for autonomous development."""
```

- [ ] **Step 2: Create tests/brain package init**

```python
# tests/brain/__init__.py
```

- [ ] **Step 3: Write failing tests for BrainConfig**

```python
# tests/brain/test_config.py
"""Tests for BrainConfig — the brain's immutable configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from claudedev.brain.config import BrainConfig


class TestBrainConfigDefaults:
    """Verify default values are sensible."""

    def test_minimal_construction(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        assert config.project_path == "/tmp/test"
        assert config.max_working_memory_tokens == 180_000
        assert config.claude_model == "claude-sonnet-4-20250514"
        assert config.system1_confidence_threshold == 0.85
        assert config.max_retries == 3
        assert config.log_level == "INFO"

    def test_memory_dir_default(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        assert "/.claudedev/memory" in config.memory_dir

    def test_embedding_model_default(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        assert config.embedding_model == "nomic-embed-text-v2"

    def test_ollama_url_default(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        assert config.ollama_base_url == "http://localhost:11434"


class TestBrainConfigFrozen:
    """BrainConfig must be immutable after construction."""

    def test_cannot_set_attribute(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        with pytest.raises(ValidationError):
            config.project_path = "/other"  # type: ignore[misc]

    def test_cannot_delete_attribute(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        with pytest.raises(ValidationError):
            del config.project_path  # type: ignore[misc]


class TestBrainConfigValidation:
    """Field validators catch invalid input."""

    def test_empty_project_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="project_path"):
            BrainConfig(project_path="")

    def test_whitespace_project_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="project_path"):
            BrainConfig(project_path="   ")

    def test_tokens_below_minimum_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp", max_working_memory_tokens=500)

    def test_tokens_above_maximum_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp", max_working_memory_tokens=1_000_000)

    def test_tokens_at_minimum_boundary(self) -> None:
        config = BrainConfig(project_path="/tmp", max_working_memory_tokens=1000)
        assert config.max_working_memory_tokens == 1000

    def test_tokens_at_maximum_boundary(self) -> None:
        config = BrainConfig(project_path="/tmp", max_working_memory_tokens=500_000)
        assert config.max_working_memory_tokens == 500_000

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp", system1_confidence_threshold=-0.1)

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp", system1_confidence_threshold=1.1)

    def test_confidence_at_zero(self) -> None:
        config = BrainConfig(project_path="/tmp", system1_confidence_threshold=0.0)
        assert config.system1_confidence_threshold == 0.0

    def test_confidence_at_one(self) -> None:
        config = BrainConfig(project_path="/tmp", system1_confidence_threshold=1.0)
        assert config.system1_confidence_threshold == 1.0

    def test_negative_retries_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp", max_retries=-1)

    def test_zero_retries_accepted(self) -> None:
        config = BrainConfig(project_path="/tmp", max_retries=0)
        assert config.max_retries == 0

    def test_invalid_log_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrainConfig(project_path="/tmp", log_level="TRACE")

    def test_valid_log_levels(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            config = BrainConfig(project_path="/tmp", log_level=level)
            assert config.log_level == level

    def test_memory_dir_tilde_expanded(self) -> None:
        config = BrainConfig(project_path="/tmp", memory_dir="~/brain_mem")
        assert "~" not in config.memory_dir
        assert config.memory_dir.startswith("/")


class TestBrainConfigSerialization:
    """Config should round-trip through dict."""

    def test_model_dump(self) -> None:
        config = BrainConfig(project_path="/tmp/test")
        data = config.model_dump()
        assert isinstance(data, dict)
        assert data["project_path"] == "/tmp/test"

    def test_from_dict(self) -> None:
        data = {"project_path": "/tmp/test", "max_retries": 5}
        config = BrainConfig(**data)
        assert config.max_retries == 5
```

- [ ] **Step 4: Run tests — verify they fail**

Run: `python -m pytest tests/brain/test_config.py -v`
Expected: ImportError — `claudedev.brain.config` does not exist yet

- [ ] **Step 5: Implement BrainConfig**

```python
# src/claudedev/brain/config.py
"""Brain configuration — immutable settings for all NEXUS subsystems."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BrainConfig(BaseModel):
    """Immutable configuration for the NEXUS brain.

    All brain subsystems receive this at construction time.
    Frozen after creation — any mutation raises ValidationError.
    """

    model_config = ConfigDict(frozen=True)

    project_path: str = Field(
        ...,
        description="Absolute path to the project root",
    )
    memory_dir: str = Field(
        default="~/.claudedev/memory",
        description="Directory for persistent memory storage",
    )
    max_working_memory_tokens: int = Field(
        default=180_000,
        ge=1000,
        le=500_000,
        description="Maximum tokens in working memory",
    )
    embedding_model: str = Field(
        default="nomic-embed-text-v2",
        description="Ollama embedding model name",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL",
    )
    claude_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model ID for brain operations",
    )
    system1_confidence_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for System 1 execution",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts for failed operations",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging verbosity level",
    )

    @field_validator("project_path")
    @classmethod
    def project_path_must_be_nonempty(cls, v: str) -> str:
        if not v.strip():
            msg = "project_path must not be empty or whitespace"
            raise ValueError(msg)
        return v

    @field_validator("memory_dir")
    @classmethod
    def expand_memory_dir(cls, v: str) -> str:
        return str(Path(v).expanduser())
```

- [ ] **Step 6: Run tests — verify they pass**

Run: `python -m pytest tests/brain/test_config.py -v`
Expected: All pass

- [ ] **Step 7: Lint and type check**

Run: `ruff check src/claudedev/brain/config.py tests/brain/test_config.py && python -m mypy src/claudedev/brain/config.py --strict`

- [ ] **Step 8: Commit**

```bash
git add src/claudedev/brain/__init__.py src/claudedev/brain/config.py tests/brain/__init__.py tests/brain/test_config.py
git commit -m "feat(brain): add BrainConfig with frozen Pydantic model and validators

Issue #1 — foundation config for all brain subsystems.
Validates project_path, token bounds, confidence range, log levels.
Immutable after construction."
```

---

### Task 3: Create shared domain models

**Files:**
- Create: `src/claudedev/brain/models.py`
- Create: `tests/brain/test_models.py`

- [ ] **Step 1: Write failing tests for domain models**

```python
# tests/brain/test_models.py
"""Tests for shared brain domain models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claudedev.brain.models import (
    EpisodicMemory,
    MemoryNode,
    Observation,
    Skill,
    Strategy,
    Task,
    TaskResult,
)


class TestTask:
    def test_creation_with_defaults(self) -> None:
        task = Task(description="Fix the login bug")
        assert task.description == "Fix the login bug"
        assert task.id is not None
        assert task.task_type == "general"
        assert task.domain == "unknown"
        assert isinstance(task.created_at, datetime)

    def test_id_auto_generated(self) -> None:
        t1 = Task(description="a")
        t2 = Task(description="b")
        assert t1.id != t2.id

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Task(description="")

    def test_context_tags_default_empty(self) -> None:
        task = Task(description="test")
        assert task.context_tags == []

    def test_custom_fields(self) -> None:
        task = Task(
            description="Refactor auth",
            task_type="refactor",
            domain="auth",
            context_tags=["security", "urgent"],
        )
        assert task.task_type == "refactor"
        assert task.domain == "auth"
        assert "security" in task.context_tags


class TestTaskResult:
    def test_successful_result(self) -> None:
        result = TaskResult(
            task_id="abc-123",
            success=True,
            output="Done",
            duration_ms=150.0,
        )
        assert result.success is True
        assert result.error is None
        assert result.files_changed == []

    def test_failed_result_with_error(self) -> None:
        result = TaskResult(
            task_id="abc-123",
            success=False,
            output="",
            error="Syntax error in main.py",
            duration_ms=50.0,
        )
        assert result.success is False
        assert result.error == "Syntax error in main.py"

    def test_with_files_and_tools(self) -> None:
        result = TaskResult(
            task_id="abc-123",
            success=True,
            output="ok",
            files_changed=["src/main.py", "tests/test_main.py"],
            tools_used=["Edit", "Bash"],
            duration_ms=200.0,
        )
        assert len(result.files_changed) == 2
        assert "Edit" in result.tools_used


class TestStrategy:
    def test_system1_strategy(self) -> None:
        skill = Skill(
            name="fix-import",
            description="Fix missing imports",
            procedure="Add import statement",
            task_signature="fix_import",
        )
        strategy = Strategy(
            mode="system1",
            confidence=0.92,
            skill=skill,
            reason="Matched fix-import skill",
        )
        assert strategy.mode == "system1"
        assert strategy.skill is not None

    def test_delegate_strategy(self) -> None:
        strategy = Strategy(
            mode="delegate",
            confidence=0.4,
            reason="No matching skill",
        )
        assert strategy.mode == "delegate"
        assert strategy.skill is None

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Strategy(mode="system99", confidence=0.5, reason="bad")


class TestMemoryNode:
    def test_creation(self) -> None:
        node = MemoryNode(
            content="User prefers snake_case",
            source="observation",
            importance=0.8,
            memory_type="semantic",
        )
        assert node.content == "User prefers snake_case"
        assert node.consolidated is False

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryNode(content="", source="x", importance=0.5, memory_type="episodic")


class TestEpisodicMemory:
    def test_creation(self) -> None:
        ep = EpisodicMemory(
            task="Fix login",
            approach="Added redirect check",
            outcome="success",
        )
        assert ep.id is not None
        assert ep.consolidated is False
        assert ep.tools_used == []
        assert ep.confidence == 0.5

    def test_full_creation(self) -> None:
        ep = EpisodicMemory(
            task="Fix login",
            approach="Added redirect",
            outcome="success",
            tools_used=["Edit", "Bash"],
            files_modified=["auth.py"],
            error_messages=[],
            confidence=0.95,
        )
        assert ep.confidence == 0.95
        assert len(ep.tools_used) == 2


class TestSkill:
    def test_creation(self) -> None:
        skill = Skill(
            name="add-test",
            description="Add unit test for function",
            procedure="1. Read function. 2. Write test. 3. Run.",
            task_signature="add_test",
        )
        assert skill.reliability == 0.5
        assert skill.preconditions == []

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Skill(name="", description="x", procedure="y", task_signature="z")


class TestObservation:
    def test_creation(self) -> None:
        obs = Observation(source="file_watcher", content="main.py changed")
        assert obs.prediction_error is None
        assert isinstance(obs.timestamp, datetime)
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `python -m pytest tests/brain/test_models.py -v`

- [ ] **Step 3: Implement shared models**

```python
# src/claudedev/brain/models.py
"""Shared domain models for the NEXUS brain.

All brain subsystems import from here. Models are Pydantic v2
with sensible defaults and strict validation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Task(BaseModel):
    """A unit of work for the brain to process."""

    id: str = Field(default_factory=_uuid)
    description: str
    task_type: str = Field(default="general")
    domain: str = Field(default="unknown")
    context_tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)

    @field_validator("description")
    @classmethod
    def description_nonempty(cls, v: str) -> str:
        if not v.strip():
            msg = "description must not be empty"
            raise ValueError(msg)
        return v


class TaskResult(BaseModel):
    """Outcome of a brain cognitive cycle."""

    task_id: str
    success: bool
    output: str
    files_changed: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0.0
    confidence: float = 0.0


class Skill(BaseModel):
    """A reusable procedure in procedural memory."""

    name: str
    description: str
    procedure: str
    task_signature: str
    preconditions: list[str] = Field(default_factory=list)
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_now)

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, v: str) -> str:
        if not v.strip():
            msg = "name must not be empty"
            raise ValueError(msg)
        return v


class Strategy(BaseModel):
    """Decision engine output — how to execute a task."""

    mode: Literal["system1", "delegate"]
    confidence: float = Field(ge=0.0, le=1.0)
    skill: Skill | None = None
    reason: str


class MemoryNode(BaseModel):
    """A single unit of memory across any tier."""

    id: str = Field(default_factory=_uuid)
    content: str
    source: str
    timestamp: datetime = Field(default_factory=_now)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    memory_type: Literal["episodic", "semantic", "procedural"]
    consolidated: bool = False

    @field_validator("content")
    @classmethod
    def content_nonempty(cls, v: str) -> str:
        if not v.strip():
            msg = "content must not be empty"
            raise ValueError(msg)
        return v


class EpisodicMemory(BaseModel):
    """A single episodic memory — one task attempt and its outcome."""

    id: str = Field(default_factory=_uuid)
    task: str
    approach: str
    outcome: str
    tools_used: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=_now)
    consolidated: bool = False


class Observation(BaseModel):
    """A raw observation from the environment."""

    source: str
    content: str
    timestamp: datetime = Field(default_factory=_now)
    prediction_error: float | None = None
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `python -m pytest tests/brain/test_models.py -v`

- [ ] **Step 5: Lint and type check**

Run: `ruff check src/claudedev/brain/models.py tests/brain/test_models.py && python -m mypy src/claudedev/brain/models.py --strict`

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/brain/models.py tests/brain/test_models.py
git commit -m "feat(brain): add shared domain models for brain subsystems

Task, TaskResult, Strategy, Skill, MemoryNode, EpisodicMemory,
Observation. All Pydantic v2 with validators. Issue #1."
```

---

## Chunk 2: Working Memory Manager (Issue #2)

### Task 4: Implement WorkingMemory with token-budgeted slots

**Files:**
- Create: `src/claudedev/brain/memory/__init__.py`
- Create: `src/claudedev/brain/memory/working.py`
- Create: `tests/brain/test_working_memory.py`

- [ ] **Step 1: Create memory package init**

```python
# src/claudedev/brain/memory/__init__.py
"""Memory subsystems for the NEXUS brain."""
```

- [ ] **Step 2: Write failing tests for WorkingMemory**

```python
# tests/brain/test_working_memory.py
"""Tests for WorkingMemory — token-budgeted context window management."""

from __future__ import annotations

import asyncio

import pytest

from claudedev.brain.memory.working import SlotPriority, WorkingMemory


@pytest.fixture
def memory() -> WorkingMemory:
    return WorkingMemory(max_tokens=1000)


@pytest.fixture
def small_memory() -> WorkingMemory:
    return WorkingMemory(max_tokens=100)


class TestSlotManagement:
    async def test_add_and_retrieve_slot(self, memory: WorkingMemory) -> None:
        await memory.add_slot("task_context", "Fix the login bug", SlotPriority.CRITICAL)
        info = await memory.slot_info()
        assert "task_context" in info
        assert info["task_context"].content == "Fix the login bug"

    async def test_remove_slot(self, memory: WorkingMemory) -> None:
        await memory.add_slot("temp", "temporary data", SlotPriority.LOW)
        await memory.remove_slot("temp")
        info = await memory.slot_info()
        assert "temp" not in info

    async def test_remove_nonexistent_slot_is_noop(self, memory: WorkingMemory) -> None:
        await memory.remove_slot("ghost")  # should not raise

    async def test_update_slot(self, memory: WorkingMemory) -> None:
        await memory.add_slot("history", "old content", SlotPriority.NORMAL)
        await memory.update_slot("history", "new content")
        info = await memory.slot_info()
        assert info["history"].content == "new content"

    async def test_update_nonexistent_raises(self, memory: WorkingMemory) -> None:
        with pytest.raises(KeyError):
            await memory.update_slot("ghost", "content")

    async def test_add_duplicate_slot_overwrites(self, memory: WorkingMemory) -> None:
        await memory.add_slot("ctx", "v1", SlotPriority.NORMAL)
        await memory.add_slot("ctx", "v2", SlotPriority.HIGH)
        info = await memory.slot_info()
        assert info["ctx"].content == "v2"
        assert info["ctx"].priority == SlotPriority.HIGH


class TestTokenCounting:
    async def test_empty_memory_zero_tokens(self, memory: WorkingMemory) -> None:
        assert await memory.token_count() == 0

    async def test_token_count_increases_with_content(self, memory: WorkingMemory) -> None:
        await memory.add_slot("a", "hello world", SlotPriority.NORMAL)
        count = await memory.token_count()
        assert count > 0

    async def test_available_tokens(self, memory: WorkingMemory) -> None:
        await memory.add_slot("a", "hello", SlotPriority.NORMAL)
        available = await memory.available_tokens()
        total = await memory.token_count()
        assert available == 1000 - total

    async def test_token_count_decreases_on_remove(self, memory: WorkingMemory) -> None:
        await memory.add_slot("a", "hello world test", SlotPriority.NORMAL)
        count_before = await memory.token_count()
        await memory.remove_slot("a")
        count_after = await memory.token_count()
        assert count_after < count_before


class TestContextAssembly:
    async def test_get_context_empty(self, memory: WorkingMemory) -> None:
        ctx = await memory.get_context()
        assert ctx == ""

    async def test_get_context_single_slot(self, memory: WorkingMemory) -> None:
        await memory.add_slot("task_context", "Fix bug", SlotPriority.CRITICAL)
        ctx = await memory.get_context()
        assert "Fix bug" in ctx

    async def test_get_context_multiple_slots(self, memory: WorkingMemory) -> None:
        await memory.add_slot("system_prompt", "You are helpful", SlotPriority.CRITICAL)
        await memory.add_slot("task_context", "Fix the bug", SlotPriority.CRITICAL)
        await memory.add_slot("history", "Previous: tested login", SlotPriority.NORMAL)
        ctx = await memory.get_context()
        assert "You are helpful" in ctx
        assert "Fix the bug" in ctx
        assert "Previous: tested login" in ctx


class TestPruning:
    async def test_prune_removes_low_priority_first(self, small_memory: WorkingMemory) -> None:
        # Fill memory over budget
        await small_memory.add_slot("system_prompt", "You are an AI", SlotPriority.CRITICAL)
        await small_memory.add_slot("history", "x " * 50, SlotPriority.LOW)
        await small_memory.add_slot("recalled", "y " * 50, SlotPriority.NORMAL)

        pruned = await small_memory.prune_to_budget()
        info = await small_memory.slot_info()

        # Critical slot must survive
        assert "system_prompt" in info
        # Something was pruned
        assert len(pruned) > 0

    async def test_critical_slots_never_pruned(self, small_memory: WorkingMemory) -> None:
        await small_memory.add_slot("system_prompt", "a " * 80, SlotPriority.CRITICAL)
        await small_memory.add_slot("task_context", "b " * 80, SlotPriority.CRITICAL)
        pruned = await small_memory.prune_to_budget()
        info = await small_memory.slot_info()
        assert "system_prompt" in info
        assert "task_context" in info

    async def test_prune_when_under_budget_is_noop(self, memory: WorkingMemory) -> None:
        await memory.add_slot("small", "hi", SlotPriority.NORMAL)
        pruned = await memory.prune_to_budget()
        assert pruned == []

    async def test_prune_empty_memory(self, memory: WorkingMemory) -> None:
        pruned = await memory.prune_to_budget()
        assert pruned == []


class TestEdgeCases:
    async def test_empty_content_slot(self, memory: WorkingMemory) -> None:
        await memory.add_slot("empty", "", SlotPriority.LOW)
        assert await memory.token_count() == 0

    async def test_large_content(self, memory: WorkingMemory) -> None:
        large = "word " * 5000
        await memory.add_slot("big", large, SlotPriority.NORMAL)
        count = await memory.token_count()
        assert count > 0

    async def test_special_characters(self, memory: WorkingMemory) -> None:
        await memory.add_slot("special", "def foo():\n    return '✨'\n", SlotPriority.NORMAL)
        ctx = await memory.get_context()
        assert "✨" in ctx

    async def test_concurrent_operations(self, memory: WorkingMemory) -> None:
        async def add_slot(n: int) -> None:
            await memory.add_slot(f"slot_{n}", f"content {n}", SlotPriority.NORMAL)

        await asyncio.gather(*[add_slot(i) for i in range(10)])
        info = await memory.slot_info()
        assert len(info) == 10
```

- [ ] **Step 3: Run tests — verify they fail**

Run: `python -m pytest tests/brain/test_working_memory.py -v`

- [ ] **Step 4: Implement WorkingMemory**

```python
# src/claudedev/brain/memory/working.py
"""Working memory — token-budgeted context window management.

The brain's RAM. Manages named slots with priorities, tracks token
usage, and prunes low-priority content when approaching budget limits.
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

import tiktoken

if TYPE_CHECKING:
    pass


class SlotPriority(enum.IntEnum):
    """Priority levels for working memory slots.

    Higher values = higher priority = pruned last.
    """

    LOW = 10
    NORMAL = 50
    HIGH = 80
    CRITICAL = 100


@dataclass
class SlotInfo:
    """Metadata about a working memory slot."""

    content: str
    priority: SlotPriority
    token_count: int


class WorkingMemory:
    """Token-budgeted context window with named, prioritized slots.

    Thread-safe for async operations via asyncio.Lock.
    Token counting uses tiktoken (cl100k_base) for accuracy.
    """

    # Slot assembly order — defines output ordering in get_context()
    _SLOT_ORDER = [
        "system_prompt",
        "task_context",
        "code_context",
        "recalled_memories",
        "history",
    ]

    def __init__(self, max_tokens: int = 180_000) -> None:
        self._max_tokens = max_tokens
        self._slots: dict[str, tuple[str, SlotPriority]] = {}
        self._lock = asyncio.Lock()
        self._encoder = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoder.encode(text))

    async def add_slot(self, name: str, content: str, priority: SlotPriority) -> None:
        """Add or replace a named memory slot."""
        async with self._lock:
            self._slots[name] = (content, priority)

    async def remove_slot(self, name: str) -> None:
        """Remove a slot by name. No-op if it doesn't exist."""
        async with self._lock:
            self._slots.pop(name, None)

    async def update_slot(self, name: str, content: str) -> None:
        """Update content of an existing slot. Raises KeyError if missing."""
        async with self._lock:
            if name not in self._slots:
                raise KeyError(name)
            _, priority = self._slots[name]
            self._slots[name] = (content, priority)

    async def get_context(self) -> str:
        """Assemble all slots into a single context string.

        Slots are ordered: known slots first (in _SLOT_ORDER),
        then any custom slots alphabetically.
        """
        async with self._lock:
            if not self._slots:
                return ""

            ordered_names: list[str] = []
            for name in self._SLOT_ORDER:
                if name in self._slots:
                    ordered_names.append(name)
            for name in sorted(self._slots):
                if name not in ordered_names:
                    ordered_names.append(name)

            parts = []
            for name in ordered_names:
                content, _ = self._slots[name]
                if content:
                    parts.append(content)
            return "\n\n".join(parts)

    async def token_count(self) -> int:
        """Total tokens across all slots."""
        async with self._lock:
            total = 0
            for content, _ in self._slots.values():
                total += self._count_tokens(content)
            return total

    async def available_tokens(self) -> int:
        """Tokens remaining before hitting the budget."""
        used = await self.token_count()
        return max(0, self._max_tokens - used)

    async def slot_info(self) -> dict[str, SlotInfo]:
        """Snapshot of all slots with metadata."""
        async with self._lock:
            result: dict[str, SlotInfo] = {}
            for name, (content, priority) in self._slots.items():
                result[name] = SlotInfo(
                    content=content,
                    priority=priority,
                    token_count=self._count_tokens(content),
                )
            return result

    async def prune_to_budget(self) -> list[str]:
        """Remove lowest-priority non-critical slots until within budget.

        Returns names of pruned slots.
        """
        async with self._lock:
            total = sum(self._count_tokens(c) for c, _ in self._slots.values())
            if total <= self._max_tokens:
                return []

            # Sort by priority ascending (lowest first), then by token count descending
            candidates = [
                (name, content, priority)
                for name, (content, priority) in self._slots.items()
                if priority < SlotPriority.CRITICAL
            ]
            candidates.sort(key=lambda x: (x[2], -self._count_tokens(x[1])))

            pruned: list[str] = []
            for name, content, _ in candidates:
                if total <= self._max_tokens:
                    break
                total -= self._count_tokens(content)
                del self._slots[name]
                pruned.append(name)

            return pruned
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `python -m pytest tests/brain/test_working_memory.py -v`

- [ ] **Step 6: Lint and type check**

Run: `ruff check src/claudedev/brain/memory/ tests/brain/test_working_memory.py && python -m mypy src/claudedev/brain/memory/ --strict`

- [ ] **Step 7: Commit**

```bash
git add src/claudedev/brain/memory/__init__.py src/claudedev/brain/memory/working.py tests/brain/test_working_memory.py
git commit -m "feat(brain): add WorkingMemory with token-budgeted slots

Issue #2 — tiktoken-based counting, priority pruning, asyncio-safe.
Critical slots (system_prompt, task_context) survive all pruning."
```

---

## Chunk 3: Episodic Memory Store (Issue #3)

### Task 5: Implement EpisodicStore with async SQLite

**Files:**
- Create: `src/claudedev/brain/memory/episodic.py`
- Create: `tests/brain/test_episodic.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/brain/test_episodic.py
"""Tests for EpisodicStore — autobiographical task memory."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from claudedev.brain.memory.episodic import EpisodicStore
from claudedev.brain.models import EpisodicMemory


@pytest.fixture
async def store(tmp_path) -> EpisodicStore:
    db_path = str(tmp_path / "test_episodic.db")
    s = EpisodicStore(db_path=db_path)
    await s.initialize()
    yield s
    await s.close()


def _make_episode(**kwargs) -> EpisodicMemory:
    defaults = {
        "task": "Fix login bug",
        "approach": "Added redirect check",
        "outcome": "success",
    }
    defaults.update(kwargs)
    return EpisodicMemory(**defaults)


class TestStoreCRUD:
    async def test_store_and_retrieve(self, store: EpisodicStore) -> None:
        ep = _make_episode()
        stored_id = await store.store(ep)
        assert stored_id == ep.id

        retrieved = await store.get_by_id(stored_id)
        assert retrieved is not None
        assert retrieved.task == "Fix login bug"
        assert retrieved.approach == "Added redirect check"
        assert retrieved.outcome == "success"

    async def test_store_preserves_all_fields(self, store: EpisodicStore) -> None:
        ep = _make_episode(
            tools_used=["Edit", "Bash"],
            files_modified=["auth.py", "tests/test_auth.py"],
            error_messages=["TypeError: missing arg"],
            confidence=0.92,
        )
        await store.store(ep)
        retrieved = await store.get_by_id(ep.id)
        assert retrieved is not None
        assert retrieved.tools_used == ["Edit", "Bash"]
        assert retrieved.files_modified == ["auth.py", "tests/test_auth.py"]
        assert retrieved.error_messages == ["TypeError: missing arg"]
        assert retrieved.confidence == 0.92

    async def test_get_nonexistent_returns_none(self, store: EpisodicStore) -> None:
        result = await store.get_by_id("nonexistent-id")
        assert result is None

    async def test_update_episode(self, store: EpisodicStore) -> None:
        ep = _make_episode(consolidated=False)
        await store.store(ep)
        ep_updated = ep.model_copy(update={"consolidated": True})
        await store.update(ep_updated)
        retrieved = await store.get_by_id(ep.id)
        assert retrieved is not None
        assert retrieved.consolidated is True

    async def test_count(self, store: EpisodicStore) -> None:
        assert await store.count() == 0
        await store.store(_make_episode())
        assert await store.count() == 1
        await store.store(_make_episode())
        assert await store.count() == 2


class TestSearch:
    async def test_keyword_search(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(task="Fix login redirect bug"))
        await store.store(_make_episode(task="Add user profile page"))
        await store.store(_make_episode(task="Fix payment gateway timeout"))

        results = await store.search("login", limit=10)
        assert len(results) == 1
        assert results[0].task == "Fix login redirect bug"

    async def test_search_in_approach(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(approach="Used SQLAlchemy ORM"))
        results = await store.search("SQLAlchemy")
        assert len(results) == 1

    async def test_search_in_outcome(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(outcome="failed: timeout error"))
        results = await store.search("timeout")
        assert len(results) == 1

    async def test_search_no_results(self, store: EpisodicStore) -> None:
        await store.store(_make_episode())
        results = await store.search("quantum computing")
        assert results == []

    async def test_search_empty_store(self, store: EpisodicStore) -> None:
        results = await store.search("anything")
        assert results == []

    async def test_search_limit(self, store: EpisodicStore) -> None:
        for i in range(10):
            await store.store(_make_episode(task=f"Login task {i}"))
        results = await store.search("Login", limit=3)
        assert len(results) == 3

    async def test_search_case_insensitive(self, store: EpisodicStore) -> None:
        await store.store(_make_episode(task="Fix LOGIN Bug"))
        results = await store.search("login")
        assert len(results) == 1


class TestRecency:
    async def test_get_recent_ordering(self, store: EpisodicStore) -> None:
        for i in range(5):
            await store.store(_make_episode(task=f"Task {i}"))
        results = await store.get_recent(limit=3)
        assert len(results) == 3

    async def test_get_recent_limit(self, store: EpisodicStore) -> None:
        for i in range(10):
            await store.store(_make_episode(task=f"Task {i}"))
        results = await store.get_recent(limit=5)
        assert len(results) == 5

    async def test_get_recent_empty_store(self, store: EpisodicStore) -> None:
        results = await store.get_recent()
        assert results == []


class TestConsolidation:
    async def test_get_unconsolidated(self, store: EpisodicStore) -> None:
        ep1 = _make_episode(consolidated=False)
        ep2 = _make_episode(consolidated=True)
        ep3 = _make_episode(consolidated=False)
        await store.store(ep1)
        await store.store(ep2)
        await store.store(ep3)
        results = await store.get_unconsolidated(limit=10)
        assert len(results) == 2
        assert all(not r.consolidated for r in results)

    async def test_get_unconsolidated_limit(self, store: EpisodicStore) -> None:
        for _ in range(10):
            await store.store(_make_episode(consolidated=False))
        results = await store.get_unconsolidated(limit=3)
        assert len(results) == 3


class TestEdgeCases:
    async def test_special_characters_in_task(self, store: EpisodicStore) -> None:
        ep = _make_episode(task="Fix O'Brien's \"quoted\" code & <html>")
        await store.store(ep)
        retrieved = await store.get_by_id(ep.id)
        assert retrieved is not None
        assert retrieved.task == "Fix O'Brien's \"quoted\" code & <html>"

    async def test_unicode_content(self, store: EpisodicStore) -> None:
        ep = _make_episode(task="Исправить баг с логином 🐛")
        await store.store(ep)
        retrieved = await store.get_by_id(ep.id)
        assert retrieved is not None
        assert "🐛" in retrieved.task

    async def test_large_content(self, store: EpisodicStore) -> None:
        big = "x" * 100_000
        ep = _make_episode(task=big)
        await store.store(ep)
        retrieved = await store.get_by_id(ep.id)
        assert retrieved is not None
        assert len(retrieved.task) == 100_000

    async def test_empty_lists_stored_correctly(self, store: EpisodicStore) -> None:
        ep = _make_episode(tools_used=[], files_modified=[], error_messages=[])
        await store.store(ep)
        retrieved = await store.get_by_id(ep.id)
        assert retrieved is not None
        assert retrieved.tools_used == []

    async def test_concurrent_writes(self, store: EpisodicStore) -> None:
        async def write(n: int) -> str:
            ep = _make_episode(task=f"Concurrent task {n}")
            return await store.store(ep)

        ids = await asyncio.gather(*[write(i) for i in range(20)])
        assert len(set(ids)) == 20
        assert await store.count() == 20

    async def test_sql_injection_safe(self, store: EpisodicStore) -> None:
        ep = _make_episode(task="'; DROP TABLE episodes; --")
        await store.store(ep)
        assert await store.count() == 1
        results = await store.search("DROP TABLE")
        assert len(results) == 1
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `python -m pytest tests/brain/test_episodic.py -v`

- [ ] **Step 3: Implement EpisodicStore**

```python
# src/claudedev/brain/memory/episodic.py
"""Episodic memory store — the brain's autobiographical memory.

Stores temporal task records: what was attempted, what approach was used,
what happened, and what was learned. Uses async SQLite with WAL mode.

Phase 1: keyword search via LIKE.
Phase 2: vector similarity via LanceDB (upgrade path preserved).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite
import structlog

from claudedev.brain.models import EpisodicMemory

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    approach TEXT NOT NULL,
    outcome TEXT NOT NULL,
    tools_used TEXT NOT NULL DEFAULT '[]',
    files_modified TEXT NOT NULL DEFAULT '[]',
    error_messages TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    timestamp TEXT NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_consolidated ON episodes(consolidated);
"""


class EpisodicStore:
    """Async SQLite store for episodic memories.

    Uses WAL mode for concurrent read/write safety.
    Parameterized queries throughout — no SQL injection possible.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create database and tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("episodic_store_initialized", path=str(self._db_path))

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "EpisodicStore not initialized. Call initialize() first."
            raise RuntimeError(msg)
        return self._db

    async def store(self, episode: EpisodicMemory) -> str:
        """Store an episode. Returns its ID."""
        db = self._ensure_db()
        await db.execute(
            """INSERT INTO episodes
               (id, task, approach, outcome, tools_used, files_modified,
                error_messages, confidence, timestamp, consolidated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                episode.id,
                episode.task,
                episode.approach,
                episode.outcome,
                json.dumps(episode.tools_used),
                json.dumps(episode.files_modified),
                json.dumps(episode.error_messages),
                episode.confidence,
                episode.timestamp.isoformat(),
                int(episode.consolidated),
            ),
        )
        await db.commit()
        logger.debug("episode_stored", episode_id=episode.id, task=episode.task[:50])
        return episode.id

    async def get_by_id(self, episode_id: str) -> EpisodicMemory | None:
        """Retrieve a single episode by ID."""
        db = self._ensure_db()
        cursor = await db.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_episode(row)

    async def search(self, query: str, limit: int = 20) -> list[EpisodicMemory]:
        """Keyword search across task, approach, and outcome fields.

        Case-insensitive LIKE matching. Phase 2 replaces with vector search.
        """
        db = self._ensure_db()
        pattern = f"%{query}%"
        cursor = await db.execute(
            """SELECT * FROM episodes
               WHERE task LIKE ? COLLATE NOCASE
                  OR approach LIKE ? COLLATE NOCASE
                  OR outcome LIKE ? COLLATE NOCASE
               ORDER BY timestamp DESC
               LIMIT ?""",
            (pattern, pattern, pattern, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_episode(row) for row in rows]

    async def get_recent(self, limit: int = 10) -> list[EpisodicMemory]:
        """Retrieve most recent episodes."""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_episode(row) for row in rows]

    async def get_unconsolidated(self, limit: int = 100) -> list[EpisodicMemory]:
        """Retrieve episodes not yet consolidated into higher-order memory."""
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT * FROM episodes WHERE consolidated = 0 ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_episode(row) for row in rows]

    async def update(self, episode: EpisodicMemory) -> None:
        """Update an existing episode."""
        db = self._ensure_db()
        await db.execute(
            """UPDATE episodes SET
               task = ?, approach = ?, outcome = ?, tools_used = ?,
               files_modified = ?, error_messages = ?, confidence = ?,
               timestamp = ?, consolidated = ?
               WHERE id = ?""",
            (
                episode.task,
                episode.approach,
                episode.outcome,
                json.dumps(episode.tools_used),
                json.dumps(episode.files_modified),
                json.dumps(episode.error_messages),
                episode.confidence,
                episode.timestamp.isoformat(),
                int(episode.consolidated),
                episode.id,
            ),
        )
        await db.commit()

    async def count(self) -> int:
        """Total number of stored episodes."""
        db = self._ensure_db()
        cursor = await db.execute("SELECT COUNT(*) FROM episodes")
        row = await cursor.fetchone()
        return row[0] if row else 0

    @staticmethod
    def _row_to_episode(row: tuple) -> EpisodicMemory:  # type: ignore[type-arg]
        return EpisodicMemory(
            id=row[0],
            task=row[1],
            approach=row[2],
            outcome=row[3],
            tools_used=json.loads(row[4]),
            files_modified=json.loads(row[5]),
            error_messages=json.loads(row[6]),
            confidence=row[7],
            timestamp=row[8],
            consolidated=bool(row[9]),
        )
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `python -m pytest tests/brain/test_episodic.py -v`

- [ ] **Step 5: Lint and type check**

Run: `ruff check src/claudedev/brain/memory/episodic.py tests/brain/test_episodic.py && python -m mypy src/claudedev/brain/memory/episodic.py --strict`

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/brain/memory/episodic.py tests/brain/test_episodic.py
git commit -m "feat(brain): add EpisodicStore with async SQLite and keyword search

Issue #3 — WAL mode, parameterized queries, case-insensitive search.
Supports CRUD, recency queries, unconsolidated filtering."
```

---

## Chunk 4: Claude Code Bridge (Issue #4)

### Task 6: Implement ClaudeBridge and Session

**Files:**
- Create: `src/claudedev/brain/integration/__init__.py`
- Create: `src/claudedev/brain/integration/claude_bridge.py`
- Create: `src/claudedev/brain/integration/session.py`
- Create: `tests/brain/test_claude_bridge.py`
- Create: `tests/brain/test_session.py`

- [ ] **Step 1: Create integration package init**

```python
# src/claudedev/brain/integration/__init__.py
"""Integration layer — bridges between the NEXUS brain and external services."""
```

- [ ] **Step 2: Write failing tests for ClaudeBridge**

```python
# tests/brain/test_claude_bridge.py
"""Tests for ClaudeBridge — Anthropic SDK wrapper for brain-to-Claude communication."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.integration.claude_bridge import ClaudeBridge, ClaudeResult


@pytest.fixture
def config() -> BrainConfig:
    return BrainConfig(project_path="/tmp/test")


@pytest.fixture
def mock_anthropic():
    with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock:
        client = MagicMock()
        mock.Anthropic.return_value = client

        # Default successful response
        response = MagicMock()
        response.content = [MagicMock(type="text", text="Task completed successfully.")]
        response.usage = MagicMock(input_tokens=100, output_tokens=50)
        response.stop_reason = "end_turn"
        response.model = "claude-sonnet-4-20250514"
        client.messages.create.return_value = response

        yield client


class TestBridgeConstruction:
    def test_creates_with_config(self, config: BrainConfig, mock_anthropic: Any) -> None:
        bridge = ClaudeBridge(config)
        assert bridge is not None

    def test_uses_model_from_config(self, mock_anthropic: Any) -> None:
        config = BrainConfig(project_path="/tmp", claude_model="claude-opus-4-20250514")
        bridge = ClaudeBridge(config)
        assert bridge._model == "claude-opus-4-20250514"


class TestExecuteTask:
    async def test_basic_execution(self, config: BrainConfig, mock_anthropic: Any) -> None:
        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(
            task="Fix the bug",
            system_prompt="You are helpful",
        )
        assert isinstance(result, ClaudeResult)
        assert result.success is True
        assert "Task completed" in result.content
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    async def test_system_prompt_passed(self, config: BrainConfig, mock_anthropic: Any) -> None:
        bridge = ClaudeBridge(config)
        await bridge.execute_task(task="test", system_prompt="Be precise")
        call_kwargs = mock_anthropic.messages.create.call_args
        assert "Be precise" in str(call_kwargs)

    async def test_result_includes_duration(self, config: BrainConfig, mock_anthropic: Any) -> None:
        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(task="test", system_prompt="x")
        assert result.duration_ms >= 0

    async def test_tool_use_extraction(self, config: BrainConfig, mock_anthropic: Any) -> None:
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "Edit"
        tool_block.input = {"path": "main.py"}

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Done"

        response = MagicMock()
        response.content = [tool_block, text_block]
        response.usage = MagicMock(input_tokens=50, output_tokens=30)
        response.stop_reason = "end_turn"
        mock_anthropic.messages.create.return_value = response

        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(task="edit file", system_prompt="x")
        assert "Edit" in result.tool_use_history

    async def test_max_turns_passed(self, config: BrainConfig, mock_anthropic: Any) -> None:
        bridge = ClaudeBridge(config)
        await bridge.execute_task(task="test", system_prompt="x", max_turns=5)
        call_kwargs = mock_anthropic.messages.create.call_args
        assert call_kwargs.kwargs.get("max_tokens") is not None


class TestErrorHandling:
    async def test_api_error_returns_failed_result(
        self, config: BrainConfig, mock_anthropic: Any
    ) -> None:
        import anthropic as anthropic_module

        mock_anthropic.messages.create.side_effect = anthropic_module.APIError(
            message="Bad request",
            request=MagicMock(),
            body=None,
        )
        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(task="test", system_prompt="x")
        assert result.success is False
        assert result.error is not None

    async def test_timeout_returns_failed_result(
        self, config: BrainConfig, mock_anthropic: Any
    ) -> None:
        import anthropic as anthropic_module

        mock_anthropic.messages.create.side_effect = anthropic_module.APITimeoutError(
            request=MagicMock(),
        )
        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(task="test", system_prompt="x")
        assert result.success is False
        assert "timeout" in (result.error or "").lower()

    async def test_rate_limit_retries(self, config: BrainConfig, mock_anthropic: Any) -> None:
        import anthropic as anthropic_module

        response_ok = MagicMock()
        response_ok.content = [MagicMock(type="text", text="ok")]
        response_ok.usage = MagicMock(input_tokens=10, output_tokens=5)
        response_ok.stop_reason = "end_turn"

        mock_anthropic.messages.create.side_effect = [
            anthropic_module.RateLimitError(
                message="Rate limited",
                response=MagicMock(status_code=429),
                body=None,
            ),
            response_ok,
        ]
        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(task="test", system_prompt="x")
        assert result.success is True
        assert mock_anthropic.messages.create.call_count == 2


class TestEdgeCases:
    async def test_empty_response_content(self, config: BrainConfig, mock_anthropic: Any) -> None:
        response = MagicMock()
        response.content = []
        response.usage = MagicMock(input_tokens=10, output_tokens=0)
        response.stop_reason = "end_turn"
        mock_anthropic.messages.create.return_value = response

        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(task="test", system_prompt="x")
        assert result.content == ""

    async def test_very_long_task(self, config: BrainConfig, mock_anthropic: Any) -> None:
        bridge = ClaudeBridge(config)
        result = await bridge.execute_task(task="x" * 100_000, system_prompt="x")
        assert result is not None
```

- [ ] **Step 3: Write failing tests for Session**

```python
# tests/brain/test_session.py
"""Tests for Session — conversation lifecycle management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from claudedev.brain.integration.session import Session, SessionManager


class TestSession:
    def test_creation(self) -> None:
        session = Session.create()
        assert session.id is not None
        assert session.conversation_history == []
        assert isinstance(session.created_at, datetime)

    def test_add_turn(self) -> None:
        session = Session.create()
        session.add_turn("user", "Fix the bug")
        session.add_turn("assistant", "I'll fix it now")
        assert len(session.conversation_history) == 2
        assert session.conversation_history[0]["role"] == "user"

    def test_get_history(self) -> None:
        session = Session.create()
        session.add_turn("user", "hello")
        history = session.get_history()
        assert len(history) == 1

    def test_is_expired_false(self) -> None:
        session = Session.create()
        assert not session.is_expired(ttl_minutes=30)

    def test_is_expired_true(self) -> None:
        session = Session.create()
        session.last_active = datetime.now(UTC) - timedelta(minutes=60)
        assert session.is_expired(ttl_minutes=30)

    def test_last_active_updated_on_turn(self) -> None:
        session = Session.create()
        before = session.last_active
        session.add_turn("user", "test")
        assert session.last_active >= before


class TestSessionManager:
    def test_create_session(self) -> None:
        mgr = SessionManager()
        session = mgr.create_session()
        assert session.id in mgr._sessions

    def test_get_session(self) -> None:
        mgr = SessionManager()
        session = mgr.create_session()
        retrieved = mgr.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id

    def test_get_nonexistent_returns_none(self) -> None:
        mgr = SessionManager()
        assert mgr.get_session("ghost") is None

    def test_cleanup_expired(self) -> None:
        mgr = SessionManager()
        s1 = mgr.create_session()
        s2 = mgr.create_session()
        s1.last_active = datetime.now(UTC) - timedelta(hours=2)
        removed = mgr.cleanup_expired(ttl_minutes=30)
        assert removed == 1
        assert mgr.get_session(s1.id) is None
        assert mgr.get_session(s2.id) is not None

    def test_list_sessions(self) -> None:
        mgr = SessionManager()
        mgr.create_session()
        mgr.create_session()
        assert len(mgr.list_sessions()) == 2
```

- [ ] **Step 4: Run tests — verify they fail**

Run: `python -m pytest tests/brain/test_claude_bridge.py tests/brain/test_session.py -v`

- [ ] **Step 5: Implement ClaudeBridge**

```python
# src/claudedev/brain/integration/claude_bridge.py
"""Claude Code bridge — the brain's primary effector.

Wraps anthropic.Anthropic() to send brain-curated context to Claude
and receive structured results. Handles retries, rate limits,
and error recovery.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import anthropic
import structlog
from pydantic import BaseModel, Field

from claudedev.brain.config import BrainConfig

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class ClaudeResult(BaseModel):
    """Structured result from a Claude API call."""

    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    tool_use_history: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None


class ClaudeBridge:
    """Bridge between the NEXUS brain and Claude via Anthropic SDK.

    Handles request construction, error recovery, and result parsing.
    """

    _BASE_BACKOFF_S = 1.0
    _MAX_BACKOFF_S = 30.0

    def __init__(self, config: BrainConfig) -> None:
        self._client = anthropic.Anthropic()
        self._model = config.claude_model
        self._max_retries = config.max_retries

    async def execute_task(
        self,
        task: str,
        system_prompt: str,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
    ) -> ClaudeResult:
        """Execute a task through Claude with brain-enriched context.

        Retries on rate limits with exponential backoff + jitter.
        Returns ClaudeResult with success=False on unrecoverable errors.
        """
        log = logger.bind(model=self._model, task_preview=task[:80])
        start = time.perf_counter()

        messages: list[dict[str, str]] = [{"role": "user", "content": task}]

        for attempt in range(1 + self._max_retries):
            try:
                response = await asyncio.to_thread(
                    self._client.messages.create,
                    model=self._model,
                    max_tokens=16384,
                    system=system_prompt,
                    messages=messages,
                )
                elapsed = (time.perf_counter() - start) * 1000
                return self._parse_response(response, elapsed)

            except anthropic.RateLimitError:
                if attempt < self._max_retries:
                    backoff = min(
                        self._BASE_BACKOFF_S * (2**attempt),
                        self._MAX_BACKOFF_S,
                    )
                    log.warning("rate_limited", attempt=attempt, backoff_s=backoff)
                    await asyncio.sleep(backoff)
                    continue
                elapsed = (time.perf_counter() - start) * 1000
                return ClaudeResult(
                    success=False,
                    error="Rate limited after max retries",
                    duration_ms=elapsed,
                )

            except anthropic.APITimeoutError:
                elapsed = (time.perf_counter() - start) * 1000
                log.error("api_timeout")
                return ClaudeResult(
                    success=False,
                    error="API timeout",
                    duration_ms=elapsed,
                )

            except anthropic.APIError as exc:
                elapsed = (time.perf_counter() - start) * 1000
                log.error("api_error", error=str(exc))
                return ClaudeResult(
                    success=False,
                    error=str(exc),
                    duration_ms=elapsed,
                )

        elapsed = (time.perf_counter() - start) * 1000
        return ClaudeResult(success=False, error="Exhausted retries", duration_ms=elapsed)

    def _parse_response(self, response: Any, elapsed_ms: float) -> ClaudeResult:
        """Extract structured data from Anthropic response."""
        content_parts: list[str] = []
        tool_names: list[str] = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_names.append(block.name)

        return ClaudeResult(
            content="\n".join(content_parts),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
            tool_use_history=tool_names,
            duration_ms=elapsed_ms,
            success=True,
        )
```

- [ ] **Step 6: Implement Session**

```python
# src/claudedev/brain/integration/session.py
"""Session management for multi-turn brain interactions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)


class Session:
    """A conversation session with lifecycle tracking."""

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.conversation_history: list[dict[str, str]] = []
        self.created_at = datetime.now(UTC)
        self.last_active = datetime.now(UTC)

    @classmethod
    def create(cls) -> Session:
        """Create a new session with a unique ID."""
        session_id = f"brain-{uuid.uuid4().hex[:12]}"
        logger.debug("session_created", session_id=session_id)
        return cls(session_id)

    def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn and update last_active."""
        self.conversation_history.append({"role": role, "content": content})
        self.last_active = datetime.now(UTC)

    def get_history(self) -> list[dict[str, str]]:
        """Return a copy of the conversation history."""
        return list(self.conversation_history)

    def is_expired(self, ttl_minutes: int = 30) -> bool:
        """Check if the session has expired based on inactivity."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
        return self.last_active < cutoff


class SessionManager:
    """Manages active brain sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> Session:
        """Create and register a new session."""
        session = Session.create()
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        """List all active sessions."""
        return list(self._sessions.values())

    def cleanup_expired(self, ttl_minutes: int = 30) -> int:
        """Remove expired sessions. Returns count removed."""
        expired = [
            sid for sid, s in self._sessions.items() if s.is_expired(ttl_minutes)
        ]
        for sid in expired:
            del self._sessions[sid]
            logger.debug("session_expired", session_id=sid)
        return len(expired)
```

- [ ] **Step 7: Run tests — verify they pass**

Run: `python -m pytest tests/brain/test_claude_bridge.py tests/brain/test_session.py -v`

- [ ] **Step 8: Lint and type check**

Run: `ruff check src/claudedev/brain/integration/ tests/brain/test_claude_bridge.py tests/brain/test_session.py && python -m mypy src/claudedev/brain/integration/ --strict`

- [ ] **Step 9: Commit**

```bash
git add src/claudedev/brain/integration/ tests/brain/test_claude_bridge.py tests/brain/test_session.py
git commit -m "feat(brain): add ClaudeBridge and Session for Claude API integration

Issue #4 — Anthropic SDK wrapper with retry logic, rate limit handling,
tool use extraction. Session manager with TTL-based expiry."
```

---

## Chunk 5: Decision Engine (Issue #5)

### Task 7: Implement DecisionEngine with System 1

**Files:**
- Create: `src/claudedev/brain/decision/__init__.py`
- Create: `src/claudedev/brain/decision/engine.py`
- Create: `tests/brain/test_decision_engine.py`

- [ ] **Step 1: Create decision package init**

```python
# src/claudedev/brain/decision/__init__.py
"""Decision engine — cognitive mode selection for the NEXUS brain."""
```

- [ ] **Step 2: Write failing tests**

```python
# tests/brain/test_decision_engine.py
"""Tests for DecisionEngine — System 1 fast decisions + delegate fallback."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.decision.engine import DecisionEngine, DecisionLog
from claudedev.brain.models import MemoryNode, Skill, Task


@pytest.fixture
def config() -> BrainConfig:
    return BrainConfig(project_path="/tmp/test", system1_confidence_threshold=0.85)


@pytest.fixture
def engine(config: BrainConfig) -> DecisionEngine:
    return DecisionEngine(config)


def _make_skill(name: str = "fix-import", reliability: float = 0.9) -> Skill:
    return Skill(
        name=name,
        description=f"Skill: {name}",
        procedure=f"Do {name}",
        task_signature=name.replace("-", "_"),
        reliability=reliability,
    )


def _make_memory(content: str, memory_type: str = "procedural") -> MemoryNode:
    return MemoryNode(
        content=content,
        source="test",
        importance=0.8,
        memory_type=memory_type,
    )


class TestSystem1Routing:
    async def test_matches_skill_above_threshold(self, engine: DecisionEngine) -> None:
        task = Task(description="Fix missing import in auth.py")
        skill = _make_skill("fix-import", reliability=0.92)
        engine.register_skill(skill)

        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "system1"
        assert strategy.confidence >= 0.85
        assert strategy.skill is not None
        assert strategy.skill.name == "fix-import"

    async def test_rejects_skill_below_threshold(self, engine: DecisionEngine) -> None:
        task = Task(description="Fix missing import")
        skill = _make_skill("fix-import", reliability=0.60)
        engine.register_skill(skill)

        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "delegate"

    async def test_boundary_at_threshold(self, engine: DecisionEngine) -> None:
        task = Task(description="Fix import")
        skill = _make_skill("fix-import", reliability=0.85)
        engine.register_skill(skill)

        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "system1"

    async def test_just_below_threshold(self, engine: DecisionEngine) -> None:
        task = Task(description="Fix import")
        skill = _make_skill("fix-import", reliability=0.84)
        engine.register_skill(skill)

        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "delegate"


class TestDelegation:
    async def test_empty_skills_delegates(self, engine: DecisionEngine) -> None:
        task = Task(description="Build a new feature")
        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "delegate"
        assert strategy.skill is None
        assert "no matching skill" in strategy.reason.lower()

    async def test_no_matching_skill_delegates(self, engine: DecisionEngine) -> None:
        task = Task(description="Deploy to production")
        engine.register_skill(_make_skill("fix-import", reliability=0.95))
        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "delegate"


class TestAmbiguousMatch:
    async def test_highest_reliability_wins(self, engine: DecisionEngine) -> None:
        task = Task(description="Fix the import error")
        engine.register_skill(_make_skill("fix-import-v1", reliability=0.88))
        engine.register_skill(_make_skill("fix-import-v2", reliability=0.95))

        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "system1"
        assert strategy.skill is not None
        assert strategy.skill.name == "fix-import-v2"


class TestDecisionLogging:
    async def test_decisions_are_logged(self, engine: DecisionEngine) -> None:
        task = Task(description="Fix something")
        await engine.decide(task, context="", memories=[])
        logs = engine.get_decision_log()
        assert len(logs) == 1
        assert isinstance(logs[0], DecisionLog)
        assert logs[0].task_id == task.id

    async def test_log_captures_mode_and_confidence(self, engine: DecisionEngine) -> None:
        skill = _make_skill("test-skill", reliability=0.92)
        engine.register_skill(skill)
        task = Task(description="Test skill match")
        await engine.decide(task, context="", memories=[])
        log_entry = engine.get_decision_log()[0]
        assert log_entry.mode == "system1"
        assert log_entry.confidence >= 0.85

    async def test_multiple_decisions_logged(self, engine: DecisionEngine) -> None:
        for i in range(5):
            task = Task(description=f"Task {i}")
            await engine.decide(task, context="", memories=[])
        assert len(engine.get_decision_log()) == 5


class TestEdgeCases:
    async def test_empty_context_and_memories(self, engine: DecisionEngine) -> None:
        task = Task(description="Anything")
        strategy = await engine.decide(task, context="", memories=[])
        assert strategy is not None

    async def test_custom_threshold(self) -> None:
        config = BrainConfig(project_path="/tmp", system1_confidence_threshold=0.5)
        engine = DecisionEngine(config)
        skill = _make_skill("easy-skill", reliability=0.55)
        engine.register_skill(skill)
        task = Task(description="Easy skill match")
        strategy = await engine.decide(task, context="", memories=[])
        assert strategy.mode == "system1"
```

- [ ] **Step 3: Run tests — verify they fail**

Run: `python -m pytest tests/brain/test_decision_engine.py -v`

- [ ] **Step 4: Implement DecisionEngine**

```python
# src/claudedev/brain/decision/engine.py
"""Decision engine — System 1 fast decisions with delegate fallback.

System 1: pattern-match against registered skills. If a skill's
reliability meets the confidence threshold, use it directly.
Delegate: hand the task entirely to Claude Code via the bridge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from claudedev.brain.config import BrainConfig
from claudedev.brain.models import MemoryNode, Skill, Strategy, Task

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class DecisionLog(BaseModel):
    """Record of a single decision for calibration."""

    task_id: str
    task_description: str
    mode: str
    confidence: float
    skill_name: str | None = None
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionEngine:
    """Phase 1 decision engine: System 1 + delegate.

    Matches tasks against registered skills by comparing task descriptions
    to skill signatures and descriptions. Highest-reliability match above
    the confidence threshold triggers System 1 execution.
    """

    def __init__(self, config: BrainConfig) -> None:
        self._threshold = config.system1_confidence_threshold
        self._skills: list[Skill] = []
        self._decision_log: list[DecisionLog] = []

    def register_skill(self, skill: Skill) -> None:
        """Register a skill for System 1 matching."""
        self._skills.append(skill)
        logger.debug("skill_registered", name=skill.name, reliability=skill.reliability)

    async def decide(
        self,
        task: Task,
        context: str,
        memories: list[MemoryNode],
    ) -> Strategy:
        """Choose execution strategy for a task.

        Returns System 1 strategy if a matching skill exists above threshold,
        otherwise delegates to Claude Code.
        """
        log = logger.bind(task_id=task.id, task=task.description[:60])

        best_skill, best_score = self._find_best_skill(task)

        if best_skill is not None and best_score >= self._threshold:
            strategy = Strategy(
                mode="system1",
                confidence=best_score,
                skill=best_skill,
                reason=f"Matched skill '{best_skill.name}' with confidence {best_score:.2f}",
            )
            log.info("decision_system1", skill=best_skill.name, confidence=best_score)
        else:
            reason = (
                f"No matching skill above threshold {self._threshold}"
                if best_skill is None
                else f"Best skill '{best_skill.name}' at {best_score:.2f} below threshold {self._threshold}"
            )
            strategy = Strategy(
                mode="delegate",
                confidence=best_score if best_skill else 0.0,
                reason=reason,
            )
            log.info("decision_delegate", reason=reason)

        self._log_decision(task, strategy)
        return strategy

    def _find_best_skill(self, task: Task) -> tuple[Skill | None, float]:
        """Find the highest-reliability matching skill."""
        if not self._skills:
            return None, 0.0

        best: Skill | None = None
        best_score = 0.0
        task_lower = task.description.lower()

        for skill in self._skills:
            # Match based on signature and description similarity
            sig_match = SequenceMatcher(
                None, task_lower, skill.task_signature.lower()
            ).ratio()
            desc_match = SequenceMatcher(
                None, task_lower, skill.description.lower()
            ).ratio()
            name_match = SequenceMatcher(
                None, task_lower, skill.name.lower()
            ).ratio()

            similarity = max(sig_match, desc_match, name_match)

            # Only consider skills with some relevance
            if similarity > 0.2:
                score = skill.reliability * (0.5 + 0.5 * similarity)
                if score > best_score:
                    best_score = score
                    best = skill

        return best, best_score

    def _log_decision(self, task: Task, strategy: Strategy) -> None:
        """Record decision for future calibration."""
        entry = DecisionLog(
            task_id=task.id,
            task_description=task.description,
            mode=strategy.mode,
            confidence=strategy.confidence,
            skill_name=strategy.skill.name if strategy.skill else None,
            reason=strategy.reason,
        )
        self._decision_log.append(entry)

    def get_decision_log(self) -> list[DecisionLog]:
        """Return all recorded decisions."""
        return list(self._decision_log)
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `python -m pytest tests/brain/test_decision_engine.py -v`

- [ ] **Step 6: Lint and type check**

Run: `ruff check src/claudedev/brain/decision/ tests/brain/test_decision_engine.py && python -m mypy src/claudedev/brain/decision/ --strict`

- [ ] **Step 7: Commit**

```bash
git add src/claudedev/brain/decision/ tests/brain/test_decision_engine.py
git commit -m "feat(brain): add DecisionEngine with System 1 mode and delegation

Issue #5 — pattern matching against skills via SequenceMatcher,
configurable confidence threshold, full decision logging."
```

---

## Chunk 6: Cortex Orchestrator (Issue #1 — final assembly)

### Task 8: Implement Cortex (main brain loop)

**Files:**
- Create: `src/claudedev/brain/cortex.py`
- Create: `tests/brain/test_cortex.py`
- Create: `tests/brain/conftest.py`

- [ ] **Step 1: Create brain test fixtures**

```python
# tests/brain/conftest.py
"""Shared fixtures for brain tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.integration.claude_bridge import ClaudeBridge, ClaudeResult

if TYPE_CHECKING:
    pass


@pytest.fixture
def brain_config(tmp_path) -> BrainConfig:
    return BrainConfig(
        project_path=str(tmp_path),
        memory_dir=str(tmp_path / "memory"),
    )


@pytest.fixture
def mock_bridge(brain_config: BrainConfig) -> ClaudeBridge:
    bridge = ClaudeBridge.__new__(ClaudeBridge)
    bridge._model = brain_config.claude_model
    bridge._max_retries = brain_config.max_retries
    bridge.execute_task = AsyncMock(
        return_value=ClaudeResult(
            content="Task completed successfully.",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
            success=True,
            duration_ms=150.0,
        )
    )
    return bridge
```

- [ ] **Step 2: Write failing tests for Cortex**

```python
# tests/brain/test_cortex.py
"""Tests for Cortex — the main brain orchestrator."""

from __future__ import annotations

import time

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.cortex import Cortex
from claudedev.brain.integration.claude_bridge import ClaudeBridge, ClaudeResult
from claudedev.brain.models import Task, TaskResult


class TestCortexCognitiveLoop:
    async def test_run_returns_task_result(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge, tmp_path
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Fix the login bug")
        result = await cortex.run(task)
        assert isinstance(result, TaskResult)
        assert result.task_id == task.id

    async def test_successful_task(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Add unit test for auth module")
        result = await cortex.run(task)
        assert result.success is True
        assert result.output != ""

    async def test_stores_episodic_memory(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Refactor database layer")
        await cortex.run(task)
        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        assert "Refactor database" in episodes[0].task

    async def test_multiple_tasks_build_memory(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        for i in range(3):
            task = Task(description=f"Task number {i}")
            await cortex.run(task)
        episodes = await cortex.episodic.get_recent(limit=10)
        assert len(episodes) == 3

    async def test_never_crashes(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        mock_bridge.execute_task.side_effect = RuntimeError("Unexpected explosion")
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="This will fail internally")
        result = await cortex.run(task)
        assert result.success is False
        assert result.error is not None

    async def test_result_includes_duration(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Quick task")
        result = await cortex.run(task)
        assert result.duration_ms > 0


class TestCortexLatency:
    async def test_loop_latency_under_100ms(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="Latency test task")
        start = time.perf_counter()
        await cortex.run(task)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # The 100ms budget is for brain logic only (mock bridge is ~0ms)
        assert elapsed_ms < 100, f"Brain loop took {elapsed_ms:.1f}ms (budget: 100ms)"


class TestCortexCleanup:
    async def test_shutdown(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        await cortex.run(Task(description="test"))
        await cortex.shutdown()
        # Should not raise
```

- [ ] **Step 3: Run tests — verify they fail**

Run: `python -m pytest tests/brain/test_cortex.py -v`

- [ ] **Step 4: Implement Cortex**

```python
# src/claudedev/brain/cortex.py
"""Cortex — the NEXUS brain orchestrator.

Implements the core cognitive cycle:
    Perceive -> Recall -> Decide -> Act -> Observe -> Remember

Never crashes. Always returns a TaskResult.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from claudedev.brain.config import BrainConfig
from claudedev.brain.decision.engine import DecisionEngine
from claudedev.brain.memory.episodic import EpisodicStore
from claudedev.brain.memory.working import SlotPriority, WorkingMemory
from claudedev.brain.models import EpisodicMemory, Strategy, Task, TaskResult

if TYPE_CHECKING:
    from claudedev.brain.integration.claude_bridge import ClaudeBridge

logger = structlog.get_logger(__name__)


class Cortex:
    """The NEXUS brain — central cognitive loop.

    Use Cortex.create() to construct (async initialization required).
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
        """Async factory — initializes all subsystems."""
        working = WorkingMemory(max_tokens=config.max_working_memory_tokens)
        episodic = EpisodicStore(
            db_path=f"{config.memory_dir}/{_project_hash(config.project_path)}/episodic.db"
        )
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
            # 1. Perceive — build working memory context
            log.info("perceive_start")
            context = await self._perceive(task)

            # 2. Recall — search episodic memory
            log.info("recall_start")
            memories = await self._recall(task)

            # 3. Decide — choose execution strategy
            log.info("decide_start")
            strategy = await self._decision.decide(task, context, memories)

            # 4. Act — execute via Claude bridge
            log.info("act_start", mode=strategy.mode)
            result = await self._act(task, strategy, context)

            # 5. Remember — store episode
            log.info("remember_start")
            await self._remember(task, result, strategy)

            elapsed_ms = (time.perf_counter() - start) * 1000
            result.duration_ms = elapsed_ms
            log.info("cognitive_cycle_complete", success=result.success, ms=f"{elapsed_ms:.1f}")
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
        """Build working memory context for the task."""
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

    async def _recall(self, task: Task) -> list:
        """Search episodic memory for relevant past experiences."""
        episodes = await self.episodic.search(task.description, limit=5)
        if episodes:
            recall_text = "\n".join(
                f"- [{e.outcome}] {e.task}: {e.approach}" for e in episodes
            )
            await self.working.add_slot(
                "recalled_memories", recall_text, SlotPriority.NORMAL
            )
        return []

    async def _act(self, task: Task, strategy: Strategy, context: str) -> TaskResult:
        """Execute the chosen strategy."""
        if strategy.mode == "system1" and strategy.skill is not None:
            # System 1: use skill procedure as the prompt
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
            outcome="success" if result.success else f"failed: {result.error or 'unknown'}",
            tools_used=result.tools_used,
            files_modified=result.files_changed,
            confidence=strategy.confidence,
        )
        await self.episodic.store(episode)

    async def shutdown(self) -> None:
        """Clean up resources."""
        await self.episodic.close()
        logger.info("cortex_shutdown")


def _project_hash(path: str) -> str:
    """Short hash of project path for directory naming."""
    import hashlib

    return hashlib.sha256(path.encode()).hexdigest()[:12]
```

- [ ] **Step 5: Run tests — verify they pass**

Run: `python -m pytest tests/brain/test_cortex.py -v`

- [ ] **Step 6: Lint and type check**

Run: `ruff check src/claudedev/brain/cortex.py tests/brain/test_cortex.py tests/brain/conftest.py && python -m mypy src/claudedev/brain/cortex.py --strict`

- [ ] **Step 7: Commit**

```bash
git add src/claudedev/brain/cortex.py tests/brain/conftest.py tests/brain/test_cortex.py
git commit -m "feat(brain): add Cortex orchestrator with full cognitive loop

Issue #1 — Perceive->Recall->Decide->Act->Remember cycle.
Never crashes, structured logging at every step, <100ms target."
```

---

## Chunk 7: Integration Tests & Quality Gates (Issue #6)

### Task 9: Phase 1 integration tests

**Files:**
- Create: `tests/brain/integration/__init__.py`
- Create: `tests/brain/integration/test_phase1_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/brain/integration/__init__.py
```

```python
# tests/brain/integration/test_phase1_integration.py
"""Phase 1 integration tests — full brain loop end-to-end.

These tests verify all Phase 1 components work together as a cohesive system.
This is the Phase 1 graduation gate.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.cortex import Cortex
from claudedev.brain.integration.claude_bridge import ClaudeBridge, ClaudeResult
from claudedev.brain.models import Task


@pytest.fixture
def config(tmp_path) -> BrainConfig:
    return BrainConfig(
        project_path=str(tmp_path),
        memory_dir=str(tmp_path / "memory"),
    )


@pytest.fixture
def mock_bridge(config: BrainConfig) -> ClaudeBridge:
    bridge = ClaudeBridge.__new__(ClaudeBridge)
    bridge._model = config.claude_model
    bridge._max_retries = config.max_retries
    bridge.execute_task = AsyncMock(
        return_value=ClaudeResult(
            content="Fixed the issue.",
            input_tokens=80,
            output_tokens=40,
            stop_reason="end_turn",
            success=True,
            duration_ms=100.0,
        )
    )
    return bridge


class TestFullCognitiveLoop:
    """End-to-end: task in -> perceive -> recall -> decide -> act -> remember -> result out."""

    async def test_task_produces_result(self, config: BrainConfig, mock_bridge: ClaudeBridge) -> None:
        cortex = await Cortex.create(config, mock_bridge)
        task = Task(description="Fix the login redirect bug")
        result = await cortex.run(task)

        assert result.task_id == task.id
        assert result.success is True
        assert result.output == "Fixed the issue."
        assert result.duration_ms > 0
        await cortex.shutdown()

    async def test_episodic_memory_stored_after_task(
        self, config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(config, mock_bridge)
        task = Task(description="Add pagination to user list")
        await cortex.run(task)

        episodes = await cortex.episodic.get_recent(limit=1)
        assert len(episodes) == 1
        assert "pagination" in episodes[0].task.lower()
        await cortex.shutdown()

    async def test_decision_logged(self, config: BrainConfig, mock_bridge: ClaudeBridge) -> None:
        cortex = await Cortex.create(config, mock_bridge)
        task = Task(description="Test decision logging")
        await cortex.run(task)

        logs = cortex._decision.get_decision_log()
        assert len(logs) == 1
        assert logs[0].task_id == task.id
        await cortex.shutdown()


class TestMultiTaskSequence:
    """Run multiple tasks and verify memory improves recall."""

    async def test_three_tasks_all_stored(
        self, config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(config, mock_bridge)

        tasks = [
            Task(description="Fix authentication timeout"),
            Task(description="Add password reset flow"),
            Task(description="Fix authentication session expiry"),
        ]

        results = []
        for task in tasks:
            result = await cortex.run(task)
            results.append(result)

        # All should succeed
        assert all(r.success for r in results)

        # All should be stored
        episodes = await cortex.episodic.get_recent(limit=10)
        assert len(episodes) == 3
        await cortex.shutdown()

    async def test_recall_finds_related_past_tasks(
        self, config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(config, mock_bridge)

        # First task about auth
        await cortex.run(Task(description="Fix authentication timeout"))

        # Second related task — should recall the first
        await cortex.run(Task(description="Fix authentication session"))

        # The second task's working memory should have recalled memories
        # (We verify by checking the episodic store has both)
        episodes = await cortex.episodic.search("authentication")
        assert len(episodes) == 2
        await cortex.shutdown()


class TestWorkingMemoryBudget:
    """Verify context assembly respects token budget."""

    async def test_context_within_budget(
        self, config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(config, mock_bridge)
        task = Task(description="Test working memory budget")
        await cortex.run(task)

        tokens = await cortex.working.token_count()
        assert tokens <= config.max_working_memory_tokens
        await cortex.shutdown()


class TestErrorRecovery:
    """Brain should never crash, even when subsystems fail."""

    async def test_bridge_failure_returns_failed_result(
        self, config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        mock_bridge.execute_task = AsyncMock(side_effect=RuntimeError("API down"))
        cortex = await Cortex.create(config, mock_bridge)
        task = Task(description="This will fail")
        result = await cortex.run(task)
        assert result.success is False
        assert result.error is not None
        await cortex.shutdown()

    async def test_bridge_returns_failed_result(
        self, config: BrainConfig, mock_bridge: ClaudeBridge
    ) -> None:
        mock_bridge.execute_task = AsyncMock(
            return_value=ClaudeResult(
                content="", success=False, error="Syntax error", duration_ms=50.0
            )
        )
        cortex = await Cortex.create(config, mock_bridge)
        task = Task(description="Failing task")
        result = await cortex.run(task)
        assert result.success is False
        await cortex.shutdown()
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/brain/integration/ -v`

- [ ] **Step 3: Commit**

```bash
git add tests/brain/integration/
git commit -m "test(brain): add Phase 1 integration tests for full cognitive loop

Issue #6 — end-to-end tests: task lifecycle, multi-task sequences,
working memory budget, error recovery. Phase 1 graduation gate."
```

### Task 10: Benchmarks

**Files:**
- Create: `tests/brain/benchmarks/__init__.py`
- Create: `tests/brain/benchmarks/bench_brain_loop.py`

- [ ] **Step 1: Write benchmarks**

```python
# tests/brain/benchmarks/__init__.py
```

```python
# tests/brain/benchmarks/bench_brain_loop.py
"""Phase 1 benchmarks — latency and throughput measurements."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.cortex import Cortex
from claudedev.brain.integration.claude_bridge import ClaudeBridge, ClaudeResult
from claudedev.brain.memory.episodic import EpisodicStore
from claudedev.brain.memory.working import SlotPriority, WorkingMemory
from claudedev.brain.models import EpisodicMemory, Task


@pytest.fixture
def config(tmp_path) -> BrainConfig:
    return BrainConfig(project_path=str(tmp_path), memory_dir=str(tmp_path / "mem"))


@pytest.fixture
def mock_bridge(config: BrainConfig) -> ClaudeBridge:
    bridge = ClaudeBridge.__new__(ClaudeBridge)
    bridge._model = config.claude_model
    bridge._max_retries = 0
    bridge.execute_task = AsyncMock(
        return_value=ClaudeResult(
            content="ok", success=True, input_tokens=10, output_tokens=5,
            stop_reason="end_turn", duration_ms=1.0,
        )
    )
    return bridge


class TestBrainLoopLatency:
    async def test_latency_under_100ms(self, config: BrainConfig, mock_bridge: ClaudeBridge) -> None:
        cortex = await Cortex.create(config, mock_bridge)
        task = Task(description="Latency benchmark task")

        times = []
        for _ in range(10):
            start = time.perf_counter()
            await cortex.run(task)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        p95 = sorted(times)[int(len(times) * 0.95)]

        print(f"\nBrain loop latency: avg={avg:.1f}ms, p95={p95:.1f}ms")
        assert avg < 100, f"Average latency {avg:.1f}ms exceeds 100ms budget"
        await cortex.shutdown()


class TestEpisodicWriteThroughput:
    async def test_write_throughput_over_100_per_sec(self, tmp_path) -> None:
        store = EpisodicStore(db_path=str(tmp_path / "bench.db"))
        await store.initialize()

        episodes = [
            EpisodicMemory(
                task=f"Benchmark task {i}",
                approach=f"Approach {i}",
                outcome="success",
            )
            for i in range(200)
        ]

        start = time.perf_counter()
        for ep in episodes:
            await store.store(ep)
        elapsed = time.perf_counter() - start

        throughput = len(episodes) / elapsed
        print(f"\nEpisodic write throughput: {throughput:.0f} episodes/sec")
        assert throughput > 100, f"Throughput {throughput:.0f}/s below 100/s target"
        await store.close()


class TestTokenCountingAccuracy:
    async def test_100_percent_accuracy_vs_tiktoken(self) -> None:
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")
        memory = WorkingMemory(max_tokens=100_000)

        test_texts = [
            "Hello, world!",
            "def foo():\n    return 42\n",
            "The quick brown fox jumps over the lazy dog.",
            "import asyncio\nasync def main():\n    await asyncio.sleep(1)\n",
            "",
            "a",
            "🎉" * 100,
            "SELECT * FROM users WHERE id = ? AND status = 'active';",
        ]

        for text in test_texts:
            expected = len(encoder.encode(text))
            await memory.add_slot("test", text, SlotPriority.NORMAL)
            actual = await memory.token_count()
            await memory.remove_slot("test")
            assert actual == expected, (
                f"Token count mismatch for '{text[:30]}...': "
                f"expected={expected}, actual={actual}"
            )
```

- [ ] **Step 2: Run benchmarks**

Run: `python -m pytest tests/brain/benchmarks/ -v -s`

- [ ] **Step 3: Commit**

```bash
git add tests/brain/benchmarks/
git commit -m "test(brain): add Phase 1 benchmarks for latency and throughput

Issue #6 — brain loop <100ms, episodic writes >100/sec,
token counting 100% accuracy vs tiktoken."
```

### Task 11: Final quality gates

- [ ] **Step 1: Run full lint**

Run: `ruff check src/claudedev/brain/ tests/brain/`

- [ ] **Step 2: Run full type check**

Run: `python -m mypy src/claudedev/brain/ --strict`

- [ ] **Step 3: Run all brain tests with coverage**

Run: `python -m pytest tests/brain/ -v --cov=claudedev.brain --cov-report=term-missing`

- [ ] **Step 4: Verify coverage >80%**

Check output for coverage percentage. Target: >80% overall, >85% for bridge/decision, >90% for memory.

- [ ] **Step 5: Run full project test suite**

Run: `python -m pytest tests/ -v`
Expected: All existing tests + all new brain tests pass

- [ ] **Step 6: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(brain): address quality gate findings from Phase 1 review"
```
