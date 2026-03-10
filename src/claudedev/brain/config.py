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
        validate_default=True,
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
        return str(Path(v).expanduser().resolve())

    @field_validator("memory_dir")
    @classmethod
    def expand_memory_dir(cls, v: str) -> str:
        return str(Path(v).expanduser().resolve())
