"""SQLAlchemy async models and session factory for ClaudeDev state persistence."""

from __future__ import annotations

import tomllib
from datetime import datetime
from enum import StrEnum
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

import structlog
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from sqlalchemy.types import TypeEngine

type JsonBlob = dict[str, Any]  # SQLAlchemy JSON columns require Any for untyped data


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    type_annotation_map: ClassVar[dict[type, TypeEngine[Any]]] = {
        dict[str, Any]: JSON().with_variant(JSONB(), "postgresql"),
        datetime: DateTime(timezone=True),
    }


# --- Enums ---


class ProjectType(StrEnum):
    POLYREPO = "polyrepo"
    MONOREPO = "monorepo"


class RepoDomain(StrEnum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    MOBILE = "mobile"
    SHARED = "shared"


class IssueStatus(StrEnum):
    NEW = "new"
    ENHANCING = "enhancing"
    ENHANCED = "enhanced"
    TRIAGED = "triaged"
    IMPLEMENTING = "implementing"
    IN_REVIEW = "in_review"
    FIXING = "fixing"
    DONE = "done"
    FAILED = "failed"
    CLOSED = "closed"


class PRStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    REVIEWING = "reviewing"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    MERGED = "merged"
    CLOSED = "closed"


class SessionType(StrEnum):
    ENHANCEMENT = "enhancement"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"


class SessionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IssueTier(StrEnum):
    TIER_1 = "1"
    TIER_2 = "2"
    TIER_3 = "3"
    TIER_4 = "4"


# --- Models ---


class Project(Base):
    """A tracked project (polyrepo or monorepo)."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    type: Mapped[ProjectType] = mapped_column(String(20))
    config: Mapped[JsonBlob] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    repos: Mapped[list[Repo]] = relationship(back_populates="project", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project(name={self.name!r}, type={self.type!r})>"


class Repo(Base):
    """A git repository belonging to a project."""

    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    domain: Mapped[RepoDomain] = mapped_column(String(20))
    local_path: Mapped[str] = mapped_column(String(500))
    github_owner: Mapped[str] = mapped_column(String(255))
    github_repo: Mapped[str] = mapped_column(String(255))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    webhook_id: Mapped[int | None] = mapped_column(default=None)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), default=None)
    tech_stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    test_credentials: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="repos")
    tracked_issues: Mapped[list[TrackedIssue]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )
    tracked_prs: Mapped[list[TrackedPR]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.github_owner}/{self.github_repo}"

    def __repr__(self) -> str:
        return f"<Repo(full_name={self.full_name!r}, domain={self.domain!r})>"


class TrackedIssue(Base):
    """A GitHub issue being tracked by ClaudeDev."""

    __tablename__ = "tracked_issues"
    __table_args__ = (
        UniqueConstraint("repo_id", "github_issue_number", name="uq_tracked_issues_repo_issue"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    github_issue_number: Mapped[int] = mapped_column(index=True)
    status: Mapped[IssueStatus] = mapped_column(String(20), default=IssueStatus.NEW)
    tier: Mapped[IssueTier | None] = mapped_column(String(1), default=None)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="SET NULL"), default=None
    )
    enhanced_at: Mapped[datetime | None] = mapped_column(default=None)
    implementation_started_at: Mapped[datetime | None] = mapped_column(default=None)
    pr_number: Mapped[int | None] = mapped_column(default=None)
    worktree_path: Mapped[str | None] = mapped_column(String(500), default=None)
    issue_metadata: Mapped[JsonBlob] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    repo: Mapped[Repo] = relationship(back_populates="tracked_issues")
    tracked_prs: Mapped[list[TrackedPR]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )
    agent_sessions: Mapped[list[AgentSession]] = relationship(
        back_populates="issue", foreign_keys="AgentSession.issue_id"
    )

    def __repr__(self) -> str:
        return f"<TrackedIssue(#{self.github_issue_number}, status={self.status!r})>"


class TrackedPR(Base):
    """A pull request being tracked by ClaudeDev."""

    __tablename__ = "tracked_prs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracked_issues.id", ondelete="SET NULL"), default=None
    )
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    pr_number: Mapped[int] = mapped_column(index=True)
    status: Mapped[PRStatus] = mapped_column(String(25), default=PRStatus.DRAFT)
    review_iteration: Mapped[int] = mapped_column(default=0)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="SET NULL"), default=None
    )
    findings: Mapped[JsonBlob] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    issue: Mapped[TrackedIssue | None] = relationship(back_populates="tracked_prs")
    repo: Mapped[Repo] = relationship(back_populates="tracked_prs")

    def __repr__(self) -> str:
        return f"<TrackedPR(#{self.pr_number}, status={self.status!r})>"


class AgentSession(Base):
    """A Claude Agent SDK session record."""

    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracked_issues.id", ondelete="SET NULL"), default=None
    )
    session_type: Mapped[SessionType] = mapped_column(String(20))
    claude_session_id: Mapped[str | None] = mapped_column(String(255), default=None)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[SessionStatus] = mapped_column(String(20), default=SessionStatus.RUNNING)
    summary: Mapped[str | None] = mapped_column(default=None)

    issue: Mapped[TrackedIssue | None] = relationship(
        back_populates="agent_sessions", foreign_keys=[issue_id]
    )

    def __repr__(self) -> str:
        return f"<AgentSession(type={self.session_type!r}, status={self.status!r})>"


# --- Database Engine and Session ---

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(db_url: str) -> None:
    """Initialize the database engine and create all tables."""
    global _engine, _session_factory
    is_sqlite = db_url.startswith("sqlite")

    if is_sqlite:
        _engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"timeout": 30},
        )
    else:
        _engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if is_sqlite:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory. Raises if init_db has not been called."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


def get_session() -> AsyncSession:
    """Create and return a new async session."""
    factory = get_session_factory()
    return factory()


async def close_db() -> None:
    """Close the database engine and release connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


# --- Config Sync ---

logger = structlog.get_logger(__name__)


async def sync_projects_from_config(projects_dir: Path) -> int:
    """Sync project configurations from TOML files into the database.

    Reads all project.toml files under projects_dir and creates/updates
    corresponding Project and Repo records. Returns the number of
    projects synced.
    """
    if not projects_dir.exists():
        return 0

    synced = 0
    async with get_session() as session:
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            config_path = project_dir / "project.toml"
            if not config_path.exists():
                continue

            with open(config_path, "rb") as f:
                config = tomllib.load(f)

            project_data = config.get("project", {})
            if not isinstance(project_data, dict):
                continue
            project_name: str = project_data.get("name", "")
            project_type_raw: str = project_data.get("type", "polyrepo")

            if not project_name:
                logger.warning("sync_skip_no_name", config_path=str(config_path))
                continue

            # Resolve project type; default to POLYREPO for unknown values.
            try:
                project_type = ProjectType(project_type_raw)
            except ValueError:
                project_type = ProjectType.POLYREPO

            # Upsert project record.
            result = await session.execute(select(Project).where(Project.name == project_name))
            project = result.scalar_one_or_none()

            if project is None:
                project = Project(
                    name=project_name,
                    type=project_type,
                    config={},
                )
                session.add(project)
                await session.flush()  # Obtain project.id before FK inserts.
                logger.info("sync_project_created", project=project_name)
            else:
                project.type = project_type

            # Build lookup of existing repos for this project.
            existing_result = await session.execute(
                select(Repo).where(Repo.project_id == project.id)
            )
            existing_repos: dict[str, Repo] = {
                f"{r.github_owner}/{r.github_repo}": r for r in existing_result.scalars().all()
            }

            repos_conf = config.get("repos", [])
            if not isinstance(repos_conf, list):
                repos_conf = []

            for repo_conf in repos_conf:
                if not isinstance(repo_conf, dict):
                    continue

                owner: str = repo_conf.get("github_owner", "")
                repo_name: str = repo_conf.get("github_repo", "")
                if not owner or not repo_name:
                    logger.warning(
                        "sync_skip_repo_no_owner_or_name",
                        project=project_name,
                        owner=owner,
                        repo=repo_name,
                    )
                    continue

                full_name = f"{owner}/{repo_name}"
                domain_raw: str = repo_conf.get("domain", "shared")
                try:
                    domain = RepoDomain(domain_raw)
                except ValueError:
                    domain = RepoDomain.SHARED

                tech_stack: list[str] = repo_conf.get("tech_stack", [])
                if not isinstance(tech_stack, list):
                    tech_stack = []

                if full_name in existing_repos:
                    existing = existing_repos[full_name]
                    existing.domain = domain
                    existing.local_path = repo_conf.get("local_path", "")
                    existing.default_branch = repo_conf.get("default_branch", "main")
                    existing.webhook_id = repo_conf.get("webhook_id")
                    existing.webhook_secret = repo_conf.get("webhook_secret")
                    existing.tech_stack = tech_stack
                    logger.debug("sync_repo_updated", repo=full_name)
                else:
                    repo = Repo(
                        project_id=project.id,
                        domain=domain,
                        local_path=repo_conf.get("local_path", ""),
                        github_owner=owner,
                        github_repo=repo_name,
                        default_branch=repo_conf.get("default_branch", "main"),
                        webhook_id=repo_conf.get("webhook_id"),
                        webhook_secret=repo_conf.get("webhook_secret"),
                        tech_stack=tech_stack,
                    )
                    session.add(repo)
                    logger.info("sync_repo_created", repo=full_name)

            await session.commit()
            synced += 1

    return synced
