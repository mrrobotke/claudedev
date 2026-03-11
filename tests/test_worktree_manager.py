# tests/test_worktree_manager.py
"""Tests for WorktreeManager — git worktree lifecycle management."""

from __future__ import annotations

import json
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

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(WorktreeError, match="not a git repository"),
        ):
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

    async def test_cleanup_existing_clean_worktree(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        call_count = 0

        async def mock_exec(*args: object, **kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            proc.returncode = 0
            if call_count == 1:  # git status --porcelain (clean)
                proc.communicate = AsyncMock(return_value=(b"", b""))
            else:  # git worktree remove / git branch -D
                proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await wt_manager.cleanup_worktree(tmp_path, 42)

        assert result is True

class TestCleanupWorktreeFailurePaths:
    async def test_cleanup_worktree_remove_failure(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        """cleanup_worktree returns False when git worktree remove fails."""
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        call_count = 0

        async def mock_exec(*args: object, **kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            if call_count == 1:  # git status --porcelain (clean)
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"", b""))
            else:  # git worktree remove — fail
                proc.returncode = 128
                proc.communicate = AsyncMock(
                    return_value=(b"", b"fatal: worktree remove failed")
                )
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await wt_manager.cleanup_worktree(tmp_path, 42)

        assert result is False

    async def test_cleanup_worktree_branch_delete_failure(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        """cleanup_worktree succeeds even when git branch -D fails."""
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        call_count = 0

        async def mock_exec(*args: object, **kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            if call_count == 1:  # git status --porcelain (clean)
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"", b""))
            elif call_count == 2:  # git worktree remove — succeed
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"", b""))
            else:  # git branch -D — fail (best-effort, should not affect result)
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(b"", b"error: branch not found")
                )
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
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


class TestDirtyWorktreeCheck:
    async def test_cleanup_dirty_worktree_returns_false(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        """Dirty worktrees (uncommitted changes) must not be cleaned up."""
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        # git status returns non-empty (dirty)
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b" M src/file.py\n", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await wt_manager.cleanup_worktree(tmp_path, 42)

        assert result is False

    async def test_cleanup_clean_worktree_succeeds(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_dir = tmp_path / ".claudedev" / "worktrees" / "issue-42"
        wt_dir.mkdir(parents=True)

        call_count = 0

        async def mock_exec(*args: object, **kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            proc.returncode = 0
            if call_count == 1:  # git status --porcelain (clean)
                proc.communicate = AsyncMock(return_value=(b"", b""))
            else:  # git worktree remove / git branch -D
                proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await wt_manager.cleanup_worktree(tmp_path, 42)

        assert result is True


class TestCleanupMergedWorktrees:
    async def test_no_worktrees_returns_zero(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        result = await wt_manager.cleanup_merged_worktrees(tmp_path)
        assert result == 0

    async def test_cleans_merged_branches(
        self, wt_manager: WorktreeManager, tmp_path: Path
    ) -> None:
        wt_base = tmp_path / ".claudedev" / "worktrees"
        (wt_base / "issue-1").mkdir(parents=True)
        (wt_base / "issue-2").mkdir(parents=True)

        call_count = 0

        async def mock_exec(*args: object, **kwargs: object) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            proc.returncode = 0
            if "branch" in args and "--merged" in args:
                # Both branches are merged
                proc.communicate = AsyncMock(
                    return_value=(b"  claudedev/issue-1\n  claudedev/issue-2\n", b"")
                )
            elif "status" in args and "--porcelain" in args:
                proc.communicate = AsyncMock(return_value=(b"", b""))  # clean
            else:
                proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await wt_manager.cleanup_merged_worktrees(tmp_path)

        assert result == 2


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
