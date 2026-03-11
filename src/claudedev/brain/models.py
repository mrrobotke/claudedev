"""Shared domain models for the NEXUS brain.

All brain subsystems import from here. Models are Pydantic v2
with sensible defaults and strict validation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Type aliases for Observation field types — importable for use in local variables
ErrorCategory = Literal["success_mismatch", "confidence_gap", "outcome_divergence", "unknown"]
ObservationDirectiveType = Literal["pivot", "constrain", "inform", "abort", "unknown"]


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
    slots: list[str] = Field(default_factory=list, description="Working memory slot names")


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
    content: str = Field(max_length=10000)
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
    task: str = Field(max_length=5000)
    approach: str = Field(max_length=5000)
    outcome: str = Field(max_length=5000)
    tools_used: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=_now)
    consolidated: bool = False


class Observation(BaseModel):
    """Result of the _observe() phase — prediction error computation and steering awareness.

    Combines prediction error tracking (comparing recalled episodes against actual outcomes)
    with steering directive awareness (checking for human directives in working memory).
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_uuid)
    task_id: str
    episode_id: str | None = None
    # Prediction error fields
    predicted_outcome: str
    actual_outcome: str
    prediction_error: float = Field(ge=0.0, le=1.0)
    predicted_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    actual_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    error_category: ErrorCategory
    # Steering awareness fields (per spec Section 4.4)
    has_steering: bool = False
    directive_type: ObservationDirectiveType | None = None
    directive_message: str | None = Field(default=None, max_length=2000)
    environment_signals: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)

    @field_validator("predicted_outcome", "actual_outcome")
    @classmethod
    def _nonempty_strings(cls, v: str) -> str:
        if not v.strip():
            msg = "predicted_outcome and actual_outcome must not be empty"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _steering_requires_directive_type(self) -> Observation:
        if self.has_steering and self.directive_type is None:
            msg = "directive_type is required when has_steering is True"
            raise ValueError(msg)
        return self
