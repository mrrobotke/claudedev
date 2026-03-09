"""Tests for SQLAlchemy async models and database queries."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import pytest
import tomli_w
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from claudedev.core.state import (
    AgentSession,
    IssueStatus,
    IssueTier,
    Project,
    ProjectType,
    PRStatus,
    Repo,
    RepoDomain,
    SessionStatus,
    SessionType,
    TrackedIssue,
    TrackedPR,
    sync_projects_from_config,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TestProjectCRUD:
    async def test_create_project(self, db_session: AsyncSession) -> None:
        project = Project(name="my-project", type=ProjectType.POLYREPO)
        db_session.add(project)
        await db_session.flush()

        result = await db_session.execute(select(Project).where(Project.name == "my-project"))
        fetched = result.scalar_one()
        assert fetched.id is not None
        assert fetched.name == "my-project"
        assert fetched.type == ProjectType.POLYREPO
        assert fetched.created_at is not None

    async def test_create_project_unique_name(self, db_session: AsyncSession) -> None:
        p1 = Project(name="unique-proj", type=ProjectType.MONOREPO)
        db_session.add(p1)
        await db_session.flush()

        p2 = Project(name="unique-proj", type=ProjectType.POLYREPO)
        db_session.add(p2)
        with pytest.raises(Exception, match=""):  # IntegrityError
            await db_session.flush()

    async def test_project_monorepo_type(self, db_session: AsyncSession) -> None:
        project = Project(name="mono", type=ProjectType.MONOREPO)
        db_session.add(project)
        await db_session.flush()

        result = await db_session.execute(select(Project).where(Project.name == "mono"))
        assert result.scalar_one().type == ProjectType.MONOREPO


class TestRepoCRUD:
    async def test_create_repo(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo).where(Repo.github_owner == "test"))
        repo = result.scalar_one()
        assert repo.github_repo == "repo"
        assert repo.domain == RepoDomain.BACKEND
        assert repo.default_branch == "main"

    async def test_repo_full_name(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()
        assert repo.full_name == "test/repo"

    async def test_repo_project_relationship(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo).options(selectinload(Repo.project)))
        repo = result.scalar_one()
        assert repo.project is not None
        assert repo.project.name == "test-project"


class TestTrackedIssueCRUD:
    async def test_create_tracked_issue(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=42,
        )
        seeded_db.add(issue)
        await seeded_db.flush()

        result = await seeded_db.execute(
            select(TrackedIssue).where(TrackedIssue.github_issue_number == 42)
        )
        fetched = result.scalar_one()
        assert fetched.id is not None
        assert fetched.status == IssueStatus.NEW
        assert fetched.tier is None
        assert fetched.created_at is not None

    async def test_update_issue_status(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=43,
        )
        seeded_db.add(issue)
        await seeded_db.flush()

        assert issue.status == IssueStatus.NEW
        issue.status = IssueStatus.ENHANCING
        await seeded_db.flush()

        result = await seeded_db.execute(select(TrackedIssue).where(TrackedIssue.id == issue.id))
        assert result.scalar_one().status == IssueStatus.ENHANCING

        issue.status = IssueStatus.ENHANCED
        issue.tier = IssueTier.TIER_2
        await seeded_db.flush()

        result = await seeded_db.execute(select(TrackedIssue).where(TrackedIssue.id == issue.id))
        fetched = result.scalar_one()
        assert fetched.status == IssueStatus.ENHANCED
        assert fetched.tier == "2"

    async def test_issue_repo_relationship(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=44)
        seeded_db.add(issue)
        await seeded_db.flush()

        result = await seeded_db.execute(select(TrackedIssue).where(TrackedIssue.id == issue.id))
        fetched = result.scalar_one()
        assert fetched.repo is not None
        assert fetched.repo.full_name == "test/repo"


class TestTrackedPRCRUD:
    async def test_create_tracked_pr(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        pr = TrackedPR(
            repo_id=repo.id,
            pr_number=10,
        )
        seeded_db.add(pr)
        await seeded_db.flush()

        result = await seeded_db.execute(select(TrackedPR).where(TrackedPR.pr_number == 10))
        fetched = result.scalar_one()
        assert fetched.id is not None
        assert fetched.status == PRStatus.DRAFT
        assert fetched.review_iteration == 0

    async def test_pr_issue_relationship(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=45)
        seeded_db.add(issue)
        await seeded_db.flush()

        pr = TrackedPR(
            repo_id=repo.id,
            pr_number=11,
            issue_id=issue.id,
        )
        seeded_db.add(pr)
        await seeded_db.flush()

        result = await seeded_db.execute(select(TrackedPR).where(TrackedPR.id == pr.id))
        fetched = result.scalar_one()
        assert fetched.issue is not None
        assert fetched.issue.github_issue_number == 45

    async def test_pr_status_transitions(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        pr = TrackedPR(repo_id=repo.id, pr_number=12)
        seeded_db.add(pr)
        await seeded_db.flush()

        for status in [PRStatus.OPEN, PRStatus.REVIEWING, PRStatus.APPROVED, PRStatus.MERGED]:
            pr.status = status
            await seeded_db.flush()
            result = await seeded_db.execute(select(TrackedPR).where(TrackedPR.id == pr.id))
            assert result.scalar_one().status == status


class TestAgentSessionCRUD:
    async def test_create_agent_session(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=50)
        seeded_db.add(issue)
        await seeded_db.flush()

        agent_session = AgentSession(
            issue_id=issue.id,
            session_type=SessionType.ENHANCEMENT,
        )
        seeded_db.add(agent_session)
        await seeded_db.flush()

        result = await seeded_db.execute(
            select(AgentSession).where(AgentSession.id == agent_session.id)
        )
        fetched = result.scalar_one()
        assert fetched.session_type == SessionType.ENHANCEMENT
        assert fetched.status == SessionStatus.RUNNING
        assert fetched.cost_usd == 0.0
        assert fetched.started_at is not None
        assert fetched.ended_at is None

    async def test_session_cost_tracking(self, seeded_db: AsyncSession) -> None:
        agent_session = AgentSession(
            session_type=SessionType.IMPLEMENTATION,
            cost_usd=1.50,
            status=SessionStatus.COMPLETED,
            summary="Implemented feature X",
        )
        seeded_db.add(agent_session)
        await seeded_db.flush()

        result = await seeded_db.execute(
            select(AgentSession).where(AgentSession.id == agent_session.id)
        )
        fetched = result.scalar_one()
        assert fetched.cost_usd == 1.50
        assert fetched.status == SessionStatus.COMPLETED
        assert fetched.summary == "Implemented feature X"

    async def test_session_issue_relationship(self, seeded_db: AsyncSession) -> None:
        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=51)
        seeded_db.add(issue)
        await seeded_db.flush()

        session1 = AgentSession(
            issue_id=issue.id,
            session_type=SessionType.ENHANCEMENT,
            status=SessionStatus.COMPLETED,
        )
        session2 = AgentSession(
            issue_id=issue.id,
            session_type=SessionType.IMPLEMENTATION,
            status=SessionStatus.RUNNING,
        )
        seeded_db.add_all([session1, session2])
        await seeded_db.flush()

        result = await seeded_db.execute(
            select(TrackedIssue)
            .where(TrackedIssue.id == issue.id)
            .options(selectinload(TrackedIssue.agent_sessions))
        )
        fetched = result.scalar_one()
        assert len(fetched.agent_sessions) == 2


def _write_project_toml(project_dir: Path, config: dict[str, object]) -> None:
    """Write a project.toml file using tomli_w."""
    with open(project_dir / "project.toml", "wb") as f:
        tomli_w.dump(config, f)


class TestSyncProjectsFromConfig:
    """Tests for sync_projects_from_config()."""

    async def test_sync_creates_project_and_repo(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """Syncing from a valid TOML file creates Project and Repo records."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        _write_project_toml(
            project_dir,
            {
                "project": {"name": "test-project", "type": "polyrepo"},
                "repos": [
                    {
                        "domain": "backend",
                        "local_path": "/tmp/backend",
                        "github_owner": "octocat",
                        "github_repo": "backend",
                        "default_branch": "main",
                        "tech_stack": ["python", "fastapi"],
                        "webhook_id": 123,
                        "webhook_secret": "s3cr3t",
                    },
                ],
            },
        )

        count = await sync_projects_from_config(tmp_path)
        assert count == 1

        result = await db_session.execute(select(Project))
        project = result.scalar_one()
        assert project.name == "test-project"
        assert project.type == ProjectType.POLYREPO

        result = await db_session.execute(select(Repo))
        repo = result.scalar_one()
        assert repo.github_owner == "octocat"
        assert repo.github_repo == "backend"
        assert repo.domain == RepoDomain.BACKEND
        assert repo.default_branch == "main"
        assert repo.tech_stack == ["python", "fastapi"]
        assert repo.webhook_id == 123
        assert repo.webhook_secret == "s3cr3t"

    async def test_sync_is_idempotent(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Running sync twice does not create duplicate Project or Repo records."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        _write_project_toml(
            project_dir,
            {
                "project": {"name": "my-project", "type": "polyrepo"},
                "repos": [
                    {
                        "domain": "shared",
                        "local_path": "/tmp/x",
                        "github_owner": "o",
                        "github_repo": "r",
                        "default_branch": "main",
                        "tech_stack": [],
                    }
                ],
            },
        )

        await sync_projects_from_config(tmp_path)
        count = await sync_projects_from_config(tmp_path)
        assert count == 1

        result = await db_session.execute(select(Project))
        projects = result.scalars().all()
        assert len(projects) == 1

        result = await db_session.execute(select(Repo))
        repos = result.scalars().all()
        assert len(repos) == 1

    async def test_sync_updates_existing_repo(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """A second sync with changed values updates the existing Repo record."""
        project_dir = tmp_path / "update-project"
        project_dir.mkdir()
        base_config: dict[str, object] = {
            "project": {"name": "update-project", "type": "polyrepo"},
            "repos": [
                {
                    "domain": "backend",
                    "local_path": "/old/path",
                    "github_owner": "owner",
                    "github_repo": "myrepo",
                    "default_branch": "main",
                    "tech_stack": ["python"],
                }
            ],
        }
        _write_project_toml(project_dir, base_config)
        await sync_projects_from_config(tmp_path)

        # Update the config on disk.
        updated_config: dict[str, object] = {
            "project": {"name": "update-project", "type": "polyrepo"},
            "repos": [
                {
                    "domain": "frontend",
                    "local_path": "/new/path",
                    "github_owner": "owner",
                    "github_repo": "myrepo",
                    "default_branch": "develop",
                    "tech_stack": ["typescript", "react"],
                }
            ],
        }
        _write_project_toml(project_dir, updated_config)
        await sync_projects_from_config(tmp_path)

        result = await db_session.execute(select(Repo).where(Repo.github_repo == "myrepo"))
        repo = result.scalar_one()
        assert repo.domain == RepoDomain.FRONTEND
        assert repo.local_path == "/new/path"
        assert repo.default_branch == "develop"
        assert repo.tech_stack == ["typescript", "react"]

    async def test_sync_multiple_projects(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Multiple project dirs are each synced and counted."""
        for proj_name in ("proj-a", "proj-b", "proj-c"):
            d = tmp_path / proj_name
            d.mkdir()
            _write_project_toml(
                d,
                {
                    "project": {"name": proj_name, "type": "polyrepo"},
                    "repos": [],
                },
            )

        count = await sync_projects_from_config(tmp_path)
        assert count == 3

        result = await db_session.execute(select(Project))
        assert len(result.scalars().all()) == 3

    async def test_sync_skips_dir_without_toml(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """Directories that lack a project.toml are silently skipped."""
        (tmp_path / "no-config").mkdir()

        count = await sync_projects_from_config(tmp_path)
        assert count == 0

        result = await db_session.execute(select(Project))
        assert result.scalars().all() == []

    async def test_sync_returns_zero_for_nonexistent_dir(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """A projects_dir that does not exist returns 0 without raising."""
        missing = tmp_path / "does-not-exist"
        count = await sync_projects_from_config(missing)
        assert count == 0

    async def test_sync_skips_repo_missing_owner(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """A repo entry without github_owner is skipped; the project is still synced."""
        project_dir = tmp_path / "partial-project"
        project_dir.mkdir()
        _write_project_toml(
            project_dir,
            {
                "project": {"name": "partial-project", "type": "polyrepo"},
                "repos": [
                    {
                        "domain": "backend",
                        "local_path": "/tmp/x",
                        "github_owner": "",  # missing
                        "github_repo": "myrepo",
                        "default_branch": "main",
                        "tech_stack": [],
                    }
                ],
            },
        )

        count = await sync_projects_from_config(tmp_path)
        assert count == 1  # project counted even though repo was skipped

        result = await db_session.execute(select(Repo))
        assert result.scalars().all() == []
