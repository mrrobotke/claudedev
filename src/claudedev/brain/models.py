"""Shared domain models for the NEXUS brain.

All brain subsystems import from here. Models are Pydantic v2
with sensible defaults and strict validation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Task(BaseModel):
    """A unit of work for the brain to process."""

    id: str = Field(default_factory=_uuid)
    description: str
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
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Context(BaseModel):
    """Assembled working memory context passed to the decision engine."""

    content: str
    token_count: int = Field(default=0, ge=0)
    slots: list[str] = Field(
        default_factory=list, description="Working memory slot names (populated in Phase 2)"
    )


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

    @model_validator(mode="after")
    def _system1_requires_skill(self) -> Strategy:
        if self.mode == "system1" and self.skill is None:
            msg = "system1 mode requires a skill"
            raise ValueError(msg)
        return self


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
