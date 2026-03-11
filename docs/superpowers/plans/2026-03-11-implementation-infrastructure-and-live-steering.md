# Implementation Infrastructure & Live Steering — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add worktree-based isolation, PR enforcement, webhook cleanup, live session streaming, and human steering via Claude Code hooks — integrated with the NEXUS brain.

**Architecture:** Five subsystems layered bottom-up: WorktreeManager (git isolation) → SteeringManager + hooks (directive queues) → WebSocketManager (live streaming) → Live Session UI (browser) → NEXUS brain integration (cognitive loop). Each layer has a clean async interface; higher layers depend only on the interface below.

**Tech Stack:** Python 3.13, FastAPI, WebSockets, asyncio queues, Claude Code HTTP hooks, SQLAlchemy async + PostgreSQL, tiktoken, structlog

**Spec:** `docs/superpowers/specs/2026-03-11-implementation-infrastructure-and-live-steering-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/claudedev/engines/worktree_manager.py` | Git worktree lifecycle (create, cleanup, list) |
| `src/claudedev/engines/steering_manager.py` | Per-session directive queues + hook response logic |
| `src/claudedev/engines/websocket_manager.py` | WebSocket subscriber management + broadcast |
| `src/claudedev/api/__init__.py` | API subpackage marker |
| `src/claudedev/api/hooks.py` | Hook HTTP endpoints (post-tool-use, stop, pre-tool-use) |
| `src/claudedev/ui/live_session.py` | Live session HTML page + FastAPI router |
| `tests/test_worktree_manager.py` | WorktreeManager unit tests |
| `tests/test_steering_manager.py` | SteeringManager unit tests |
| `tests/test_websocket_manager.py` | WebSocketManager unit tests |
| `tests/test_hooks_api.py` | Hook endpoint integration tests |
| `tests/test_live_session.py` | Live session page tests |
| `tests/brain/test_observation.py` | Observation model tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/claudedev/core/state.py` | Add `worktree_path` column to TrackedIssue |
| `src/claudedev/engines/team_engine.py` | Integrate worktree creation + PR enforcement fallback |
| `src/claudedev/github/webhook_server.py` | Add PR merge/close cleanup handlers, mount hook + WS routers |
| `src/claudedev/integrations/claude_sdk.py` | Add `session_id` param for WebSocket broadcasting |
| `src/claudedev/brain/models.py` | Add `Observation` model |
| `src/claudedev/brain/memory/working.py` | Add steering slot to `_ORDERED_SLOTS` |
| `src/claudedev/brain/cortex.py` | Implement `_observe()` with steering + prediction error |

---

## Chunk 1: Foundation — Observation Model, WorktreeManager & DB Schema

### Task 1: Observation Model

**Files:**
- Modify: `src/claudedev/brain/models.py:131`
- Create: `tests/brain/test_observation.py`

- [ ] **Step 1: Write failing tests for Observation model**

```python
# tests/brain/test_observation.py
"""Tests for the Observation model."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from claudedev.brain.models import Observation


class TestObservation:
    def test_minimal_creation(self) -> None:
        obs = Observation(
            task_id="abc123",
            predicted_outcome="success",
            actual_outcome="success",
            prediction_error=0.1,
            predicted_confidence=0.8,
            actual_confidence=0.7,
            error_category="confidence_gap",
        )
        assert obs.task_id == "abc123"
        assert obs.prediction_error == 0.1

    def test_auto_generated_id(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.id
        assert len(obs.id) == 32

    def test_unique_ids(self) -> None:
        kwargs = dict(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        o1 = Observation(**kwargs)
        o2 = Observation(**kwargs)
        assert o1.id != o2.id

    def test_timestamp_utc(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.timestamp.tzinfo is not None
        assert obs.timestamp.tzinfo == UTC

    def test_episode_id_optional(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.episode_id is None

    def test_episode_id_set(self) -> None:
        obs = Observation(
            task_id="t",
            episode_id="ep1",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.episode_id == "ep1"

    def test_prediction_error_bounds_zero(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=0.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.prediction_error == 0.0

    def test_prediction_error_bounds_one(self) -> None:
        obs = Observation(
            task_id="t",
            predicted_outcome="p",
            actual_outcome="a",
            prediction_error=1.0,
            predicted_confidence=0.5,
            actual_confidence=0.5,
            error_category="unknown",
        )
        assert obs.prediction_error == 1.0

    def test_prediction_error_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=1.1,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category="unknown",
            )

    def test_prediction_error_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=-0.1,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category="unknown",
            )

    def test_all_error_categories(self) -> None:
        for cat in ("success_mismatch", "confidence_gap", "outcome_divergence", "unknown"):
            obs = Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=0.5,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category=cat,
            )
            assert obs.error_category == cat

    def test_invalid_error_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Observation(
                task_id="t",
                predicted_outcome="p",
                actual_outcome="a",
                prediction_error=0.5,
                predicted_confidence=0.5,
                actual_confidence=0.5,
                error_category="invalid_cat",
            )

    def test_confidence_bounds(self) -> None:
        for field in ("predicted_confidence", "actual_confidence"):
            with pytest.raises(ValidationError):
                Observation(
                    task_id="t",
                    predicted_outcome="p",
                    actual_outcome="a",
                    prediction_error=0.0,
                    error_category="unknown",
                    **{field: 1.1},
                )
            with pytest.raises(ValidationError):
                Observation(
                    task_id="t",
                    predicted_outcome="p",
                    actual_outcome="a",
                    prediction_error=0.0,
                    error_category="unknown",
                    **{field: -0.1},
                )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/brain/test_observation.py -v 2>&1 | head -30`
Expected: FAIL with `ImportError: cannot import name 'Observation' from 'claudedev.brain.models'`

- [ ] **Step 3: Implement Observation model**

Add after the `EpisodicMemory` class (line ~132) in `src/claudedev/brain/models.py`:

```python
class Observation(BaseModel):
    """A prediction error observation from the _observe() cognitive step."""

    id: str = Field(default_factory=_uuid)
    task_id: str
    episode_id: str | None = None
    predicted_outcome: str
    actual_outcome: str
    prediction_error: float = Field(ge=0.0, le=1.0)
    predicted_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    actual_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    error_category: Literal["success_mismatch", "confidence_gap", "outcome_divergence", "unknown"]
    timestamp: datetime = Field(default_factory=_now)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/brain/test_observation.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite + linting**

Run: `cd /Users/iworldafric/claudedev && ruff check src/claudedev/brain/models.py tests/brain/test_observation.py && python -m pytest tests/brain/ -v --tb=short`
Expected: ruff clean, all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/brain/models.py tests/brain/test_observation.py
git commit -m "feat(brain): add Observation model for prediction error tracking"
```

---

### Task 2: WorktreeManager Module

**Files:**
- Create: `src/claudedev/engines/worktree_manager.py`
- Create: `tests/test_worktree_manager.py`

- [ ] **Step 1: Write failing tests for WorktreeManager**

```python
# tests/test_worktree_manager.py
"""Tests for WorktreeManager — git worktree lifecycle management."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from claudedev.engines.worktree_manager import WorktreeError, WorktreeInfo, WorktreeManager


@pytest.fixture
def wt_manager() -> WorktreeManager:
    return WorktreeManager()


class TestWorktreeInfo:
    def test_creation(self, tmp_path: Path) -> None:
        info = WorktreeInfo(
            path=tmp_path / ".claudedev" / "worktrees" / "issue-42",
            branch="claudedev/issue-42",
            issue_number=42,
        )
        assert info.issue_number == 42
        assert info.branch == "claudedev/issue-42"

    def test_str_representation(self, tmp_path: Path) -> None:
        info = WorktreeInfo(
            path=tmp_path / ".claudedev" / "worktrees" / "issue-1",
            branch="claudedev/issue-1",
            issue_number=1,
        )
        assert "issue-1" in str(info)


class TestGetWorktreePath:
    def test_returns_path_format(self, wt_manager: WorktreeManager) -> None:
        result = wt_manager.get_worktree_path(Path("/repo"), 42)
        assert result == Path("/repo/.claudedev/worktrees/issue-42")

    def test_different_issue_numbers(self, wt_manager: WorktreeManager) -> None:
        p1 = wt_manager.get_worktree_path(Path("/repo"), 1)
        p2 = wt_manager.get_worktree_path(Path("/repo"), 99)
        assert p1 != p2

    def test_different_repos(self, wt_manager: WorktreeManager) -> None:
        p1 = wt_manager.get_worktree_path(Path("/repo-a"), 42)
        p2 = wt_manager.get_worktree_path(Path("/repo-b"), 42)
        assert p1 != p2


class TestCreateWorktree:
    async def test_creates_worktree_directory(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            info = await wt_manager.create_worktree(tmp_path, 42, "main")

        assert info.issue_number == 42
        assert info.branch == "claudedev/issue-42"
        assert "issue-42" in str(info.path)

    async def test_idempotent_if_exists(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        info = await wt_manager.create_worktree(tmp_path, 42, "main")
        assert info.path == wt_dir

    async def test_git_failure_raises_worktree_error(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 128
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"fatal: not a git repository")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(WorktreeError, match="not a git repository"):
                await wt_manager.create_worktree(tmp_path, 42, "main")

    async def test_creates_claudedev_directory(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await wt_manager.create_worktree(tmp_path, 42, "main")

        assert (tmp_path / ".claudedev" / "worktrees").is_dir()


class TestCleanupWorktree:
    async def test_cleanup_nonexistent_returns_false(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        result = await wt_manager.cleanup_worktree(tmp_path, 42)
        assert result is False

    async def test_cleanup_existing_worktree(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await wt_manager.cleanup_worktree(tmp_path, 42)

        assert result is True


class TestListWorktrees:
    async def test_empty_repo(self, wt_manager: WorktreeManager, tmp_path: Path) -> None:
        result = await wt_manager.list_worktrees(tmp_path)
        assert result == []

    async def test_lists_existing_worktrees(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_base = tmp_path / ".claudedev" / "worktrees"
        (wt_base / "issue-1").mkdir(parents=True)
        (wt_base / "issue-5").mkdir(parents=True)

        result = await wt_manager.list_worktrees(tmp_path)
        assert len(result) == 2
        issue_numbers = {wt.issue_number for wt in result}
        assert issue_numbers == {1, 5}

    async def test_ignores_non_issue_dirs(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_base = tmp_path / ".claudedev" / "worktrees"
        (wt_base / "issue-1").mkdir(parents=True)
        (wt_base / "random-dir").mkdir(parents=True)

        result = await wt_manager.list_worktrees(tmp_path)
        assert len(result) == 1


class TestWriteHookConfig:
    async def test_writes_settings_json(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        await wt_manager.write_hook_config(wt_dir, "sess-123", 42)

        settings_path = wt_dir / ".claude" / "settings.json"
        assert settings_path.exists()

        config = json.loads(settings_path.read_text())
        assert "hooks" in config
        assert "PostToolUse" in config["hooks"]

        post_hook = config["hooks"]["PostToolUse"][0]
        assert post_hook["headers"]["X-Session-Id"] == "sess-123"
        assert post_hook["headers"]["X-Issue-Number"] == "42"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_worktree_manager.py -v 2>&1 | head -10`
Expected: FAIL with `ModuleNotFoundError: No module named 'claudedev.engines.worktree_manager'`

- [ ] **Step 3: Implement WorktreeManager**

```python
# src/claudedev/engines/worktree_manager.py
"""Git worktree lifecycle management for isolated issue implementations."""

from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class WorktreeError(Exception):
    """Raised when a git worktree operation fails."""


@dataclass
class WorktreeInfo:
    """Metadata about an active worktree."""

    path: Path
    branch: str
    issue_number: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __str__(self) -> str:
        return f"Worktree(issue-{self.issue_number}, branch={self.branch})"


_HOOK_CONFIG_TEMPLATE: dict[str, object] = {
    "hooks": {
        "PostToolUse": [
            {
                "type": "http",
                "url": "http://127.0.0.1:8787/api/hooks/post-tool-use",
                "headers": {"X-Session-Id": "", "X-Issue-Number": ""},
                "timeout": 5000,
            }
        ],
        "Stop": [
            {
                "type": "http",
                "url": "http://127.0.0.1:8787/api/hooks/stop",
                "headers": {"X-Session-Id": "", "X-Issue-Number": ""},
                "timeout": 10000,
            }
        ],
        "PreToolUse": [
            {
                "type": "http",
                "url": "http://127.0.0.1:8787/api/hooks/pre-tool-use",
                "headers": {"X-Session-Id": "", "X-Issue-Number": ""},
                "timeout": 5000,
            }
        ],
    }
}


class WorktreeManager:
    """Manages git worktree lifecycle for isolated issue implementations."""

    def get_worktree_path(self, repo_path: Path, issue_number: int) -> Path:
        """Return the expected worktree path for an issue."""
        return repo_path / ".claudedev" / "worktrees" / f"issue-{issue_number}"

    async def create_worktree(
        self,
        repo_path: Path,
        issue_number: int,
        base_branch: str,
    ) -> WorktreeInfo:
        """Create a git worktree for the given issue. Idempotent."""
        wt_path = self.get_worktree_path(repo_path, issue_number)
        branch = f"claudedev/issue-{issue_number}"

        if wt_path.is_dir():
            logger.info("worktree_exists", issue=issue_number, path=str(wt_path))
            return WorktreeInfo(path=wt_path, branch=branch, issue_number=issue_number)

        wt_path.parent.mkdir(parents=True, exist_ok=True)
        await self._ensure_gitignore(repo_path)
        await self._run_git(
            repo_path, "worktree", "add", str(wt_path), "-b", branch, base_branch,
        )

        logger.info("worktree_created", issue=issue_number, path=str(wt_path), branch=branch)
        return WorktreeInfo(path=wt_path, branch=branch, issue_number=issue_number)

    async def cleanup_worktree(self, repo_path: Path, issue_number: int) -> bool:
        """Remove a worktree and its local branch. Returns False if not found."""
        wt_path = self.get_worktree_path(repo_path, issue_number)
        branch = f"claudedev/issue-{issue_number}"

        if not wt_path.is_dir():
            return False

        try:
            await self._run_git(repo_path, "worktree", "remove", str(wt_path), "--force")
        except WorktreeError:
            logger.warning("worktree_remove_failed", issue=issue_number, path=str(wt_path))
            return False

        try:
            await self._run_git(repo_path, "branch", "-D", branch)
        except WorktreeError:
            logger.debug("branch_delete_skipped", branch=branch)

        logger.info("worktree_cleaned", issue=issue_number)
        return True

    async def list_worktrees(self, repo_path: Path) -> list[WorktreeInfo]:
        """List all ClaudeDev worktrees for a repo."""
        wt_base = repo_path / ".claudedev" / "worktrees"
        if not wt_base.is_dir():
            return []

        results: list[WorktreeInfo] = []
        for child in sorted(wt_base.iterdir()):
            if not child.is_dir():
                continue
            match = re.match(r"^issue-(\d+)$", child.name)
            if match:
                issue_num = int(match.group(1))
                results.append(
                    WorktreeInfo(
                        path=child,
                        branch=f"claudedev/issue-{issue_num}",
                        issue_number=issue_num,
                    )
                )
        return results

    async def write_hook_config(
        self, worktree_path: Path, session_id: str, issue_number: int,
    ) -> None:
        """Write .claude/settings.json inside the worktree with hook configuration."""
        config = copy.deepcopy(_HOOK_CONFIG_TEMPLATE)
        hooks = config["hooks"]
        assert isinstance(hooks, dict)

        for hook_list in hooks.values():
            assert isinstance(hook_list, list)
            for hook in hook_list:
                assert isinstance(hook, dict)
                headers = hook["headers"]
                assert isinstance(headers, dict)
                headers["X-Session-Id"] = session_id
                headers["X-Issue-Number"] = str(issue_number)

        claude_dir = worktree_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps(config, indent=2))
        logger.info("hook_config_written", worktree=str(worktree_path), session_id=session_id)

    async def _ensure_gitignore(self, repo_path: Path) -> None:
        """Add .claudedev/ to .gitignore if not already present."""
        gitignore = repo_path / ".gitignore"
        pattern = ".claudedev/"
        if gitignore.exists():
            content = gitignore.read_text()
            if pattern in content:
                return
            gitignore.write_text(content.rstrip() + f"\n{pattern}\n")
        else:
            gitignore.write_text(f"{pattern}\n")

    async def _run_git(self, cwd: Path, *args: str) -> str:
        """Run a git command and return stdout. Raises WorktreeError on failure."""
        process = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise WorktreeError(error_msg)
        return stdout.decode("utf-8", errors="replace").strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_worktree_manager.py -v`
Expected: ALL PASS

- [ ] **Step 5: Lint check**

Run: `cd /Users/iworldafric/claudedev && ruff check src/claudedev/engines/worktree_manager.py tests/test_worktree_manager.py`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/engines/worktree_manager.py tests/test_worktree_manager.py
git commit -m "feat(engines): add WorktreeManager for isolated issue implementations"
```

---

### Task 3: TrackedIssue.worktree_path DB Column

**Files:**
- Modify: `src/claudedev/core/state.py:157`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_state.py`:

```python
async def test_tracked_issue_worktree_path(db_session) -> None:
    from claudedev.core.state import Project, ProjectType, Repo, RepoDomain, TrackedIssue

    project = Project(name="wt-test", type=ProjectType.POLYREPO)
    db_session.add(project)
    await db_session.flush()
    repo = Repo(
        project_id=project.id, domain=RepoDomain.BACKEND,
        local_path="/tmp/test", github_owner="test", github_repo="repo",
    )
    db_session.add(repo)
    await db_session.flush()
    issue = TrackedIssue(
        repo_id=repo.id, github_issue_number=99,
        worktree_path="/tmp/test/.claudedev/worktrees/issue-99",
    )
    db_session.add(issue)
    await db_session.flush()
    assert issue.worktree_path == "/tmp/test/.claudedev/worktrees/issue-99"


async def test_tracked_issue_worktree_path_default_none(db_session) -> None:
    from claudedev.core.state import Project, ProjectType, Repo, RepoDomain, TrackedIssue

    project = Project(name="wt-test2", type=ProjectType.POLYREPO)
    db_session.add(project)
    await db_session.flush()
    repo = Repo(
        project_id=project.id, domain=RepoDomain.BACKEND,
        local_path="/tmp/test2", github_owner="test2", github_repo="repo2",
    )
    db_session.add(repo)
    await db_session.flush()
    issue = TrackedIssue(repo_id=repo.id, github_issue_number=100)
    db_session.add(issue)
    await db_session.flush()
    assert issue.worktree_path is None
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_state.py::test_tracked_issue_worktree_path -v 2>&1 | tail -10`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'worktree_path'`

- [ ] **Step 3: Add worktree_path column to TrackedIssue**

In `src/claudedev/core/state.py`, add after the `pr_number` field (line ~157):

```python
    worktree_path: Mapped[str | None] = mapped_column(String(500), default=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_state.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/core/state.py tests/test_state.py
git commit -m "feat(state): add worktree_path column to TrackedIssue"
```

---

## Chunk 2: PR Enforcement & Webhook Cleanup

### Task 4: PR Enforcement in TeamEngine

**Files:**
- Modify: `src/claudedev/engines/team_engine.py:127-287`
- Modify: `tests/test_team_engine.py`
- Possibly modify: `src/claudedev/github/gh_client.py`

- [ ] **Step 1: Write tests for worktree integration and PR enforcement**

Add to `tests/test_team_engine.py`:

```python
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from claudedev.engines.team_engine import TeamEngine


class TestWorktreeIntegration:
    async def test_worktree_path_format(self) -> None:
        from claudedev.engines.worktree_manager import WorktreeManager
        wt = WorktreeManager()
        path = wt.get_worktree_path(Path("/repo"), 42)
        assert ".claudedev/worktrees/issue-42" in str(path)


class TestPREnforcement:
    async def test_extract_pr_number_from_metadata(self) -> None:
        text = "Implementation done\nPR_NUMBER: 15\nBRANCH: claudedev/issue-42"
        result = TeamEngine._extract_pr_number(text)
        assert result == 15

    async def test_extract_pr_number_from_url(self) -> None:
        text = "Created https://github.com/owner/repo/pull/23"
        result = TeamEngine._extract_pr_number(text)
        assert result == 23

    async def test_extract_pr_number_none(self) -> None:
        text = "Done with implementation, no PR created."
        result = TeamEngine._extract_pr_number(text)
        assert result is None
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_team_engine.py -v --tb=short`

- [ ] **Step 3: Modify TeamEngine.run_implementation() for worktree + PR enforcement**

In `src/claudedev/engines/team_engine.py`:

Add import at top:
```python
from claudedev.engines.worktree_manager import WorktreeManager
```

Before the `try:` block in `run_implementation()` (after line ~221), add:
```python
        # Create worktree for isolated implementation
        wt_manager = WorktreeManager()
        wt_info = await wt_manager.create_worktree(
            Path(repo.local_path), tracked.github_issue_number, repo.default_branch,
        )
        tracked.worktree_path = str(wt_info.path)
        await session.flush()

        # Write hook configuration for steering
        await wt_manager.write_hook_config(
            wt_info.path, str(agent_session.id), tracked.github_issue_number,
        )
        working_dir = str(wt_info.path)
```

Update the prompt format to use `working_dir` and the `run_query()` call to use `cwd=working_dir`.

Replace the `else: tracked.status = IssueStatus.DONE` block (~line 254) with:
```python
            if pr_number is None:
                try:
                    pr_number = await self.gh_client.create_pr(
                        repo_full_name,
                        title=f"fix: resolve #{tracked.github_issue_number} - {gh_issue.title[:60]}",
                        body=f"Resolves #{tracked.github_issue_number}\n\n*Created by ClaudeDev*",
                        head=f"claudedev/issue-{tracked.github_issue_number}",
                        base=repo.default_branch,
                    )
                    log.info("auto_pr_created", pr_number=pr_number)
                except Exception as pr_err:
                    log.warning("auto_pr_failed", error=str(pr_err))

            if pr_number is not None:
                tracked.pr_number = pr_number
                tracked.status = IssueStatus.IN_REVIEW
            else:
                tracked.status = IssueStatus.DONE
                log.warning("no_pr_created", issue=tracked.github_issue_number)
```

- [ ] **Step 4: Add `create_pr` to GHClient if missing**

Check if `src/claudedev/github/gh_client.py` has `create_pr`. If not, add:

```python
    async def create_pr(
        self, repo_full_name: str, title: str, body: str, head: str, base: str,
    ) -> int:
        """Create a pull request via gh CLI. Returns the PR number."""
        result = await self._run_gh(
            "pr", "create", "--repo", repo_full_name,
            "--title", title, "--body", body, "--head", head, "--base", base,
            "--json", "number",
        )
        import json
        data = json.loads(result)
        return int(data["number"])
```

- [ ] **Step 5: Run tests and lint**

Run: `cd /Users/iworldafric/claudedev && ruff check src/claudedev/engines/team_engine.py && python -m pytest tests/test_team_engine.py -v --tb=short`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/engines/team_engine.py src/claudedev/github/gh_client.py tests/test_team_engine.py
git commit -m "feat(engines): integrate worktree creation and PR enforcement in TeamEngine"
```

---

### Task 5: Webhook-Driven Worktree Cleanup

**Files:**
- Modify: `src/claudedev/github/webhook_server.py`
- Create: `tests/test_webhook_cleanup.py`

- [ ] **Step 1: Write tests for cleanup handler**

```python
# tests/test_webhook_cleanup.py
"""Tests for webhook-driven worktree cleanup on PR merge/close."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from claudedev.core.state import (
    IssueStatus, PRStatus, Project, ProjectType, Repo, RepoDomain,
    TrackedIssue, TrackedPR, close_db, get_session_factory, init_db,
)
from claudedev.github.webhook_server import create_webhook_app


@pytest.fixture
async def cleanup_db():
    await init_db("sqlite+aiosqlite:///:memory:")
    yield
    await close_db()


class TestWorktreeCleanupLogic:
    async def test_pr_close_clears_worktree_path(self, cleanup_db) -> None:
        """When a tracked PR is closed, its issue's worktree_path should be cleared."""
        factory = get_session_factory()
        async with factory() as session:
            project = Project(name="test", type=ProjectType.POLYREPO)
            session.add(project)
            await session.flush()
            repo = Repo(
                project_id=project.id, domain=RepoDomain.BACKEND,
                local_path="/tmp/repo", github_owner="test", github_repo="repo",
            )
            session.add(repo)
            await session.flush()
            issue = TrackedIssue(
                repo_id=repo.id, github_issue_number=42,
                status=IssueStatus.IN_REVIEW,
                worktree_path="/tmp/repo/.claudedev/worktrees/issue-42",
            )
            session.add(issue)
            await session.flush()
            pr = TrackedPR(
                issue_id=issue.id, repo_id=repo.id,
                pr_number=10, status=PRStatus.OPEN,
            )
            session.add(pr)
            await session.commit()

            # Verify setup
            assert issue.worktree_path is not None
            assert pr.status == PRStatus.OPEN
```

- [ ] **Step 2: Add `_handle_pr_close` to webhook_server.py**

In `src/claudedev/github/webhook_server.py`, inside `create_webhook_app()`, add the cleanup handler:

```python
    async def _handle_pr_close(pr_number: int, repo_full: str, merged: bool) -> None:
        """Handle PR close/merge — cleanup worktree if applicable."""
        from claudedev.engines.worktree_manager import WorktreeManager

        async with get_session() as session:
            result = await session.execute(
                select(TrackedPR)
                .options(selectinload(TrackedPR.issue))
                .where(TrackedPR.pr_number == pr_number)
            )
            tracked_pr = result.scalar_one_or_none()
            if not tracked_pr or not tracked_pr.issue:
                return

            tracked_pr.status = PRStatus.MERGED if merged else PRStatus.CLOSED
            issue = tracked_pr.issue

            if issue.worktree_path:
                from pathlib import Path
                wt_path = Path(issue.worktree_path)
                repo_path = wt_path.parent.parent.parent
                wt = WorktreeManager()
                cleaned = await wt.cleanup_worktree(repo_path, issue.github_issue_number)
                if cleaned:
                    issue.worktree_path = None
                    logger.info(
                        "worktree_cleaned_on_pr_close",
                        pr=pr_number, issue=issue.github_issue_number, merged=merged,
                    )

            await session.commit()
```

Add the call in the existing `handle_webhook` for PR events:

```python
        if x_github_event == "pull_request" and payload.get("action") == "closed":
            pr_data = payload.get("pull_request", {})
            merged = pr_data.get("merged", False)
            pr_num = pr_data.get("number")
            repo_full = payload.get("repository", {}).get("full_name", "")
            if pr_num and repo_full:
                await _handle_pr_close(int(pr_num), repo_full, merged)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_webhook_cleanup.py tests/test_webhook_server.py -v --tb=short`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/claudedev/github/webhook_server.py tests/test_webhook_cleanup.py
git commit -m "feat(webhook): add worktree cleanup on PR merge/close"
```

---

## Chunk 3: Steering Infrastructure

### Task 6: SteeringManager Module

**Files:**
- Create: `src/claudedev/engines/steering_manager.py`
- Create: `tests/test_steering_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_steering_manager.py
"""Tests for SteeringManager — per-session directive queues."""

from __future__ import annotations

import pytest

from claudedev.engines.steering_manager import (
    DirectiveType, SteeringDirective, SteeringManager,
)


@pytest.fixture
def sm() -> SteeringManager:
    return SteeringManager()


class TestSessionLifecycle:
    async def test_register_and_unregister(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        assert sm.is_session_active("s1")
        sm.unregister_session("s1")
        assert not sm.is_session_active("s1")

    async def test_unregister_nonexistent_is_safe(self, sm: SteeringManager) -> None:
        sm.unregister_session("nonexistent")

    async def test_register_idempotent(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        sm.register_session("s1")
        assert sm.is_session_active("s1")


class TestDirectiveQueue:
    async def test_enqueue_and_get(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Use Redis", DirectiveType.PIVOT)
        directive = await sm.get_pending_directive("s1")
        assert directive is not None
        assert directive.message == "Use Redis"
        assert directive.directive_type == DirectiveType.PIVOT

    async def test_get_empty_returns_none(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        directive = await sm.get_pending_directive("s1")
        assert directive is None

    async def test_fifo_ordering(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "first", DirectiveType.INFORM)
        await sm.enqueue_message("s1", "second", DirectiveType.CONSTRAIN)
        d1 = await sm.get_pending_directive("s1")
        d2 = await sm.get_pending_directive("s1")
        assert d1 is not None and d1.message == "first"
        assert d2 is not None and d2.message == "second"

    async def test_enqueue_unregistered_raises(self, sm: SteeringManager) -> None:
        with pytest.raises(KeyError):
            await sm.enqueue_message("bad", "msg", DirectiveType.INFORM)

    async def test_get_unregistered_returns_none(self, sm: SteeringManager) -> None:
        result = await sm.get_pending_directive("bad")
        assert result is None


class TestHookHandlers:
    async def test_post_tool_use_no_directive(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        result = await sm.handle_post_tool_use("s1", {"tool": "Read"})
        assert result == {}

    async def test_post_tool_use_with_directive(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Switch to Redis", DirectiveType.PIVOT)
        result = await sm.handle_post_tool_use("s1", {"tool": "Read"})
        assert "additionalContext" in result
        assert "Switch to Redis" in result["additionalContext"]

    async def test_stop_no_directive_approves(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        result = await sm.handle_stop("s1", {})
        assert result.get("decision") == "approve"

    async def test_stop_with_abort_approves(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Stop now", DirectiveType.ABORT)
        result = await sm.handle_stop("s1", {})
        assert result.get("decision") == "approve"

    async def test_stop_with_pivot_blocks(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Try different approach", DirectiveType.PIVOT)
        result = await sm.handle_stop("s1", {})
        assert result.get("decision") == "block"
        assert "Try different approach" in result.get("reason", "")

    async def test_pre_tool_use_no_abort(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        result = await sm.handle_pre_tool_use("s1", {"tool": "Edit"})
        assert result == {}

    async def test_pre_tool_use_with_abort(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "Abort", DirectiveType.ABORT)
        result = await sm.handle_pre_tool_use("s1", {"tool": "Edit"})
        assert "permissionDecision" in result
        assert result["permissionDecision"] == "deny"


class TestActivityTracking:
    async def test_hook_invocation_logged(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.handle_post_tool_use("s1", {"tool": "Read"})
        activity = sm.get_session_activity("s1")
        assert len(activity) >= 1
        assert activity[0].event_type == "tool_use"

    async def test_steering_delivery_logged(self, sm: SteeringManager) -> None:
        sm.register_session("s1")
        await sm.enqueue_message("s1", "test", DirectiveType.INFORM)
        await sm.handle_post_tool_use("s1", {"tool": "Read"})
        activity = sm.get_session_activity("s1")
        types = [a.event_type for a in activity]
        assert "steering_sent" in types

    async def test_activity_empty_for_unknown_session(self, sm: SteeringManager) -> None:
        result = sm.get_session_activity("unknown")
        assert result == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_steering_manager.py -v 2>&1 | head -10`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement SteeringManager**

```python
# src/claudedev/engines/steering_manager.py
"""Per-session directive queues and hook response logic for human steering."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class DirectiveType(StrEnum):
    PIVOT = "pivot"
    CONSTRAIN = "constrain"
    INFORM = "inform"
    ABORT = "abort"


class SteeringDirective(BaseModel):
    """A human steering message for an active implementation session."""

    session_id: str
    message: str
    directive_type: DirectiveType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False


class ActivityEvent(BaseModel):
    """A recorded hook invocation or steering event."""

    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    tool_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SteeringManager:
    """Manages per-session steering message queues and hook responses."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[SteeringDirective]] = {}
        self._activity: dict[str, list[ActivityEvent]] = {}
        self._stop_hook_active: dict[str, bool] = {}

    def register_session(self, session_id: str) -> None:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
            self._activity[session_id] = []
            self._stop_hook_active[session_id] = False

    def unregister_session(self, session_id: str) -> None:
        self._queues.pop(session_id, None)
        self._activity.pop(session_id, None)
        self._stop_hook_active.pop(session_id, None)

    def is_session_active(self, session_id: str) -> bool:
        return session_id in self._queues

    async def enqueue_message(
        self, session_id: str, message: str, directive_type: DirectiveType,
    ) -> None:
        if session_id not in self._queues:
            raise KeyError(f"Session {session_id} not registered")
        directive = SteeringDirective(
            session_id=session_id, message=message, directive_type=directive_type,
        )
        await self._queues[session_id].put(directive)

    async def get_pending_directive(self, session_id: str) -> SteeringDirective | None:
        queue = self._queues.get(session_id)
        if queue is None:
            return None
        try:
            return queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def handle_post_tool_use(
        self, session_id: str, hook_payload: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name = hook_payload.get("tool", "unknown")
        self._log_activity(session_id, "tool_use", tool_name=tool_name)

        directive = await self.get_pending_directive(session_id)
        if directive is None:
            return {}

        directive.acknowledged = True
        self._log_activity(
            session_id, "steering_sent",
            details={"message": directive.message, "type": directive.directive_type.value},
        )
        context = (
            f"[CLAUDEDEV STEERING - {directive.directive_type.value.upper()}]\n"
            f"From the project owner: {directive.message}\n"
            f"You MUST acknowledge this directive and adjust your approach accordingly."
        )
        return {"additionalContext": context}

    async def handle_stop(
        self, session_id: str, hook_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self._stop_hook_active.get(session_id, False):
            self._stop_hook_active[session_id] = False
            return {"decision": "approve"}

        directive = await self.get_pending_directive(session_id)
        if directive is None:
            return {"decision": "approve"}

        if directive.directive_type == DirectiveType.ABORT:
            self._log_activity(session_id, "abort")
            return {"decision": "approve"}

        self._stop_hook_active[session_id] = True
        self._log_activity(
            session_id, "steering_sent",
            details={"message": directive.message, "type": directive.directive_type.value},
        )
        reason = (
            f"[CLAUDEDEV STEERING - {directive.directive_type.value.upper()}]\n"
            f"From the project owner: {directive.message}\n"
            f"Continue working and adjust your approach accordingly."
        )
        return {"decision": "block", "reason": reason}

    async def handle_pre_tool_use(
        self, session_id: str, hook_payload: dict[str, Any],
    ) -> dict[str, Any]:
        queue = self._queues.get(session_id)
        if queue is None:
            return {}
        try:
            directive = queue.get_nowait()
        except asyncio.QueueEmpty:
            return {}

        if directive.directive_type == DirectiveType.ABORT:
            self._log_activity(session_id, "abort")
            return {
                "permissionDecision": "deny",
                "reason": "Implementation aborted by project owner",
            }
        # Not abort — put it back
        await queue.put(directive)
        return {}

    def get_session_activity(self, session_id: str) -> list[ActivityEvent]:
        return self._activity.get(session_id, [])

    def _log_activity(
        self, session_id: str, event_type: str,
        tool_name: str | None = None, details: dict[str, Any] | None = None,
    ) -> None:
        if session_id not in self._activity:
            return
        event = ActivityEvent(
            session_id=session_id, event_type=event_type,
            tool_name=tool_name, details=details or {},
        )
        self._activity[session_id].append(event)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_steering_manager.py -v`
Expected: ALL PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/claudedev/engines/steering_manager.py tests/test_steering_manager.py
git add src/claudedev/engines/steering_manager.py tests/test_steering_manager.py
git commit -m "feat(engines): add SteeringManager for per-session directive queues"
```

---

### Task 7: Hook API Endpoints

**Files:**
- Create: `src/claudedev/api/__init__.py`
- Create: `src/claudedev/api/hooks.py`
- Create: `tests/test_hooks_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hooks_api.py
"""Tests for hook API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from claudedev.api.hooks import create_hooks_router
from claudedev.engines.steering_manager import DirectiveType, SteeringManager


@pytest.fixture
def steering() -> SteeringManager:
    sm = SteeringManager()
    sm.register_session("test-session")
    return sm


@pytest.fixture
async def hooks_client(steering: SteeringManager):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(create_hooks_router(steering))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPostToolUseEndpoint:
    async def test_no_directive_returns_empty(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/post-tool-use",
            json={"tool": "Read"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_with_directive_returns_context(
        self, hooks_client: AsyncClient, steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Use JWT", DirectiveType.PIVOT)
        resp = await hooks_client.post(
            "/api/hooks/post-tool-use",
            json={"tool": "Read"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "additionalContext" in data
        assert "Use JWT" in data["additionalContext"]


class TestStopEndpoint:
    async def test_no_directive_approves(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/stop", json={},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approve"

    async def test_pivot_blocks(
        self, hooks_client: AsyncClient, steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Change approach", DirectiveType.PIVOT)
        resp = await hooks_client.post(
            "/api/hooks/stop", json={},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        data = resp.json()
        assert data["decision"] == "block"


class TestPreToolUseEndpoint:
    async def test_no_abort_allows(self, hooks_client: AsyncClient) -> None:
        resp = await hooks_client.post(
            "/api/hooks/pre-tool-use", json={"tool": "Edit"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_abort_denies(
        self, hooks_client: AsyncClient, steering: SteeringManager,
    ) -> None:
        await steering.enqueue_message("test-session", "Stop", DirectiveType.ABORT)
        resp = await hooks_client.post(
            "/api/hooks/pre-tool-use", json={"tool": "Edit"},
            headers={"X-Session-Id": "test-session", "X-Issue-Number": "42"},
        )
        data = resp.json()
        assert data["permissionDecision"] == "deny"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_hooks_api.py -v 2>&1 | head -10`
Expected: FAIL with `ModuleNotFoundError: No module named 'claudedev.api'`

- [ ] **Step 3: Create api package and hooks router**

```python
# src/claudedev/api/__init__.py
"""API endpoints for ClaudeDev."""
```

```python
# src/claudedev/api/hooks.py
"""Hook API endpoints for Claude Code steering integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from claudedev.engines.steering_manager import SteeringManager

logger = structlog.get_logger(__name__)


def create_hooks_router(steering: SteeringManager) -> APIRouter:
    """Create a FastAPI router with hook endpoints."""
    router = APIRouter(prefix="/api/hooks", tags=["hooks"])

    @router.post("/post-tool-use")
    async def post_tool_use(
        request: Request,
        x_session_id: str = Header(""),
        x_issue_number: str = Header(""),
    ) -> JSONResponse:
        body = await request.json()
        result = await steering.handle_post_tool_use(x_session_id, body)
        return JSONResponse(result)

    @router.post("/stop")
    async def stop(
        request: Request,
        x_session_id: str = Header(""),
        x_issue_number: str = Header(""),
    ) -> JSONResponse:
        body = await request.json()
        result = await steering.handle_stop(x_session_id, body)
        return JSONResponse(result)

    @router.post("/pre-tool-use")
    async def pre_tool_use(
        request: Request,
        x_session_id: str = Header(""),
        x_issue_number: str = Header(""),
    ) -> JSONResponse:
        body = await request.json()
        result = await steering.handle_pre_tool_use(x_session_id, body)
        return JSONResponse(result)

    return router
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_hooks_api.py -v`
Expected: ALL PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/claudedev/api/__init__.py src/claudedev/api/hooks.py tests/test_hooks_api.py
git add src/claudedev/api/__init__.py src/claudedev/api/hooks.py tests/test_hooks_api.py
git commit -m "feat(api): add hook endpoints for PostToolUse, Stop, PreToolUse"
```

---

## Chunk 4: Live Session Streaming

### Task 8: WebSocketManager Module

**Files:**
- Create: `src/claudedev/engines/websocket_manager.py`
- Create: `tests/test_websocket_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_websocket_manager.py
"""Tests for WebSocketManager — session output broadcasting."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from claudedev.engines.websocket_manager import WebSocketManager


@pytest.fixture
def ws_manager() -> WebSocketManager:
    return WebSocketManager()


def make_mock_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestSubscription:
    async def test_register_subscriber(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        assert ws_manager.get_subscriber_count("s1") == 1

    async def test_unregister_subscriber(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.unregister_subscriber("s1", ws)
        assert ws_manager.get_subscriber_count("s1") == 0

    async def test_multiple_subscribers(self, ws_manager: WebSocketManager) -> None:
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws1)
        await ws_manager.register_subscriber("s1", ws2)
        assert ws_manager.get_subscriber_count("s1") == 2

    async def test_count_unknown_session(self, ws_manager: WebSocketManager) -> None:
        assert ws_manager.get_subscriber_count("unknown") == 0


class TestBroadcast:
    async def test_broadcast_output(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.broadcast_output("s1", "Hello world")
        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["type"] == "output"
        assert msg["data"] == "Hello world"

    async def test_broadcast_to_multiple(self, ws_manager: WebSocketManager) -> None:
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await ws_manager.register_subscriber("s1", ws1)
        await ws_manager.register_subscriber("s1", ws2)
        await ws_manager.broadcast_output("s1", "test")
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    async def test_broadcast_no_subscribers(self, ws_manager: WebSocketManager) -> None:
        await ws_manager.broadcast_output("none", "test")

    async def test_dead_subscriber_removed(self, ws_manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        ws.send_text.side_effect = Exception("Connection closed")
        await ws_manager.register_subscriber("s1", ws)
        await ws_manager.broadcast_output("s1", "test")
        assert ws_manager.get_subscriber_count("s1") == 0


class TestOutputBuffer:
    async def test_buffer_stores_lines(self, ws_manager: WebSocketManager) -> None:
        await ws_manager.broadcast_output("s1", "line 1")
        await ws_manager.broadcast_output("s1", "line 2")
        buffer = ws_manager.get_output_buffer("s1")
        assert len(buffer) == 2

    async def test_buffer_max_size(self, ws_manager: WebSocketManager) -> None:
        for i in range(150):
            await ws_manager.broadcast_output("s1", f"line {i}")
        buffer = ws_manager.get_output_buffer("s1")
        assert len(buffer) == 100

    async def test_empty_buffer(self, ws_manager: WebSocketManager) -> None:
        buffer = ws_manager.get_output_buffer("unknown")
        assert buffer == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_websocket_manager.py -v 2>&1 | head -10`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement WebSocketManager**

```python
# src/claudedev/engines/websocket_manager.py
"""WebSocket subscriber management and broadcast for live session streaming."""

from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_MAX_BUFFER_SIZE = 100


class WebSocketManager:
    """Manages WebSocket connections and broadcasts session output."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[Any]] = {}
        self._output_buffers: dict[str, deque[str]] = {}

    async def register_subscriber(self, session_id: str, ws: Any) -> None:
        if session_id not in self._subscribers:
            self._subscribers[session_id] = set()
        self._subscribers[session_id].add(ws)

    async def unregister_subscriber(self, session_id: str, ws: Any) -> None:
        subs = self._subscribers.get(session_id)
        if subs:
            subs.discard(ws)

    def get_subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, set()))

    async def broadcast_output(self, session_id: str, line: str) -> None:
        if session_id not in self._output_buffers:
            self._output_buffers[session_id] = deque(maxlen=_MAX_BUFFER_SIZE)
        self._output_buffers[session_id].append(line)

        subs = self._subscribers.get(session_id)
        if not subs:
            return

        msg = json.dumps({
            "type": "output", "data": line,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        dead: list[Any] = []
        for ws in subs:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            subs.discard(ws)

    async def broadcast_activity(
        self, session_id: str, event_type: str, data: dict[str, Any],
    ) -> None:
        subs = self._subscribers.get(session_id)
        if not subs:
            return
        msg = json.dumps({
            "type": "activity", "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        dead: list[Any] = []
        for ws in subs:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            subs.discard(ws)

    def get_output_buffer(self, session_id: str) -> list[str]:
        buf = self._output_buffers.get(session_id)
        return list(buf) if buf else []
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/test_websocket_manager.py -v`
Expected: ALL PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/claudedev/engines/websocket_manager.py tests/test_websocket_manager.py
git add src/claudedev/engines/websocket_manager.py tests/test_websocket_manager.py
git commit -m "feat(engines): add WebSocketManager for live session broadcasting"
```

---

### Task 9: Live Session Page + WebSocket Endpoints + Router Mounting

**Files:**
- Create: `src/claudedev/ui/live_session.py`
- Create: `tests/test_live_session.py`
- Modify: `src/claudedev/github/webhook_server.py`
- Modify: `src/claudedev/integrations/claude_sdk.py`

- [ ] **Step 1: Create live session page**

Create `src/claudedev/ui/live_session.py` with:
- `LIVE_SESSION_HTML` constant: three-panel layout (terminal + tool activity + steering input)
- `create_live_session_router(ws_manager, steering)` function returning an APIRouter with:
  - `GET /session/{session_id}/live` — serves HTML page
  - `WS /ws/session/{session_id}/stream` — output streaming
  - `WS /ws/session/{session_id}/steer` — bidirectional steering

See the design spec Section 3.4 for the HTML layout. The page uses two WebSocket connections from JavaScript and includes a terminal output panel, tool activity sidebar, and steering input with directive type buttons.

- [ ] **Step 2: Write tests**

```python
# tests/test_live_session.py
"""Tests for live session page."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from claudedev.engines.steering_manager import SteeringManager
from claudedev.engines.websocket_manager import WebSocketManager
from claudedev.ui.live_session import create_live_session_router


class TestLiveSessionPage:
    async def test_serves_html(self) -> None:
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(create_live_session_router(WebSocketManager(), SteeringManager()))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/session/test-123/live")
            assert resp.status_code == 200
            assert "Live Session" in resp.text
```

- [ ] **Step 3: Mount all routers in webhook_server.py**

In `src/claudedev/github/webhook_server.py`, at the end of `create_webhook_app()` before `return app`:

```python
    from claudedev.engines.steering_manager import SteeringManager
    from claudedev.engines.websocket_manager import WebSocketManager
    from claudedev.api.hooks import create_hooks_router
    from claudedev.ui.live_session import create_live_session_router

    app.state.steering_manager = SteeringManager()
    app.state.ws_manager = WebSocketManager()
    app.include_router(create_hooks_router(app.state.steering_manager))
    app.include_router(create_live_session_router(app.state.ws_manager, app.state.steering_manager))
```

- [ ] **Step 4: Add WebSocket broadcasting to claude_sdk.py**

In `src/claudedev/integrations/claude_sdk.py`, add `session_id` and `ws_manager` optional params to `run_query()` and `_run_query_cli()`. After `yield decoded` in the readline loop, add:

```python
            if session_id and ws_manager:
                await ws_manager.broadcast_output(session_id, decoded.rstrip())
```

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20`
Expected: All tests pass

- [ ] **Step 6: Lint and commit**

```bash
ruff check src/claudedev/ui/live_session.py src/claudedev/github/webhook_server.py src/claudedev/integrations/claude_sdk.py tests/test_live_session.py
git add src/claudedev/ui/live_session.py src/claudedev/github/webhook_server.py src/claudedev/integrations/claude_sdk.py tests/test_live_session.py
git commit -m "feat(ui): add live session page with WebSocket streaming and steering"
```

---

## Chunk 5: NEXUS Brain Integration

### Task 10: Steering Slot in Working Memory

**Files:**
- Modify: `src/claudedev/brain/memory/working.py:38-44`
- Modify: `tests/brain/test_working_memory.py`

- [ ] **Step 1: Write failing test**

Add to `tests/brain/test_working_memory.py`:

```python
class TestSteeringSlot:
    async def test_steering_slot_in_ordered_slots(self) -> None:
        from claudedev.brain.memory.working import _ORDERED_SLOTS
        assert "steering" in _ORDERED_SLOTS
        rm_idx = _ORDERED_SLOTS.index("recalled_memories")
        st_idx = _ORDERED_SLOTS.index("steering")
        hi_idx = _ORDERED_SLOTS.index("history")
        assert rm_idx < st_idx < hi_idx

    async def test_steering_slot_in_context_assembly(self) -> None:
        from claudedev.brain.memory.working import SlotPriority, WorkingMemory
        wm = WorkingMemory()
        await wm.add_slot("system_prompt", "sys", SlotPriority.CRITICAL)
        await wm.add_slot("steering", "steer msg", SlotPriority.HIGH)
        await wm.add_slot("history", "hist", SlotPriority.LOW)
        ctx = await wm.get_context()
        assert ctx.index("steer msg") < ctx.index("hist")
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd /Users/iworldafric/claudedev && python -m pytest "tests/brain/test_working_memory.py::TestSteeringSlot" -v`
Expected: FAIL

- [ ] **Step 3: Add steering to _ORDERED_SLOTS**

In `src/claudedev/brain/memory/working.py`, update line 38-44:

```python
_ORDERED_SLOTS: tuple[str, ...] = (
    "system_prompt",
    "task_context",
    "code_context",
    "recalled_memories",
    "steering",
    "history",
)
```

Update the docstring to include "steering" in the slot order description.

- [ ] **Step 4: Run tests**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/brain/test_working_memory.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/claudedev/brain/memory/working.py tests/brain/test_working_memory.py
git commit -m "feat(brain): add steering slot to working memory ordered slots"
```

---

### Task 11: Cortex._observe() Enhancement

**Files:**
- Modify: `src/claudedev/brain/cortex.py:227-240`
- Modify: `tests/brain/test_cortex.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/brain/test_cortex.py`:

```python
class TestObserve:
    async def test_observe_no_prior_memory(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge,
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        task = Task(description="brand new unique task xyz123")
        result = TaskResult(
            task_id=task.id, success=True, output="done", confidence=0.8,
        )
        observed = await cortex._observe(task, result)
        assert observed.confidence == 0.8
        await cortex.shutdown()

    async def test_observe_success_mismatch_penalizes(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge,
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        from claudedev.brain.models import EpisodicMemory
        await cortex.episodic.store(EpisodicMemory(
            task="fix auth bug", approach="patched validation",
            outcome="success", confidence=0.9,
        ))
        task = Task(description="fix auth bug")
        result = TaskResult(
            task_id=task.id, success=False, output="failed",
            error="timeout", confidence=0.9,
        )
        observed = await cortex._observe(task, result)
        assert observed.confidence < 0.9
        await cortex.shutdown()

    async def test_observe_matching_prediction_unchanged(
        self, brain_config: BrainConfig, mock_bridge: ClaudeBridge,
    ) -> None:
        cortex = await Cortex.create(brain_config, mock_bridge)
        from claudedev.brain.models import EpisodicMemory
        await cortex.episodic.store(EpisodicMemory(
            task="run tests", approach="pytest",
            outcome="success", confidence=0.85,
        ))
        task = Task(description="run tests")
        result = TaskResult(
            task_id=task.id, success=True, output="pass", confidence=0.85,
        )
        observed = await cortex._observe(task, result)
        assert observed.confidence == 0.85
        await cortex.shutdown()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd /Users/iworldafric/claudedev && python -m pytest "tests/brain/test_cortex.py::TestObserve" -v`
Expected: Some tests FAIL (current _observe passes through without prediction error logic)

- [ ] **Step 3: Implement enhanced _observe()**

Replace `_observe()` in `src/claudedev/brain/cortex.py` (lines 227-240):

```python
    async def _observe(self, task: Task, result: TaskResult) -> TaskResult:
        """Compute prediction error by comparing actual result with recalled episodes."""
        predictions = await self.episodic.search(task.description, limit=3)

        prediction_error: float | None = None
        if predictions:
            prior = predictions[0]
            actual_success = result.success
            predicted_success = "success" in prior.outcome.lower()

            if actual_success != predicted_success:
                error_value = 1.0
                category = "success_mismatch"
            else:
                error_value = abs(result.confidence - prior.confidence)
                category = "confidence_gap" if error_value > 0.2 else "outcome_divergence"

            prediction_error = min(error_value, 1.0)

            if error_value > 0.3:
                logger.warning(
                    "high_prediction_error",
                    task_id=task.id, error=f"{error_value:.2f}", category=category,
                )

            if error_value > 0.5:
                result = TaskResult(
                    task_id=result.task_id, success=result.success,
                    output=result.output, tools_used=result.tools_used,
                    files_changed=result.files_changed, error=result.error,
                    confidence=max(0.0, result.confidence - 0.1),
                    duration_ms=result.duration_ms,
                )

        logger.info(
            "observe",
            task_id=task.id, success=result.success,
            tools_count=len(result.tools_used),
            files_count=len(result.files_changed),
            has_prediction_error=prediction_error is not None,
            prediction_error=prediction_error,
        )
        return result
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/iworldafric/claudedev && python -m pytest tests/brain/test_cortex.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite + quality gates**

Run: `cd /Users/iworldafric/claudedev && ruff check src/claudedev/brain/cortex.py && python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20`
Expected: ruff clean, all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/claudedev/brain/cortex.py tests/brain/test_cortex.py
git commit -m "feat(brain): implement prediction error computation in cortex._observe()"
```

---

## Final Quality Gate

- [ ] **Full linting:** `cd /Users/iworldafric/claudedev && ruff check src/ tests/`
- [ ] **Type checking:** `cd /Users/iworldafric/claudedev && mypy src/claudedev/ --strict 2>&1 | tail -10`
- [ ] **Full test suite:** `cd /Users/iworldafric/claudedev && python -m pytest tests/ -v --tb=short`
- [ ] **Coverage:** `cd /Users/iworldafric/claudedev && python -m pytest tests/ --cov=claudedev --cov-report=term-missing 2>&1 | tail -30`

---

## Summary

| Chunk | Tasks | New Files | Modified Files | Est. Tests |
|-------|-------|-----------|----------------|------------|
| 1. Foundation | 1-3 | 3 | 2 | ~30 |
| 2. PR & Cleanup | 4-5 | 1 | 3 | ~10 |
| 3. Steering | 6-7 | 3 | 0 | ~25 |
| 4. Live Streaming | 8-9 | 3 | 2 | ~15 |
| 5. NEXUS Brain | 10-11 | 1 | 2 | ~8 |
| **Total** | **11** | **11** | **9** | **~88** |
