# src/claudedev/engines/worktree_manager.py
"""Git worktree lifecycle management for isolated issue implementations."""

from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

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
            repo_path,
            "worktree",
            "add",
            str(wt_path),
            "-b",
            branch,
            base_branch,
        )

        logger.info("worktree_created", issue=issue_number, path=str(wt_path), branch=branch)
        return WorktreeInfo(path=wt_path, branch=branch, issue_number=issue_number)

    async def cleanup_worktree(self, repo_path: Path, issue_number: int) -> bool:
        """Remove a worktree and its local branch. Returns False if not found or dirty."""
        wt_path = self.get_worktree_path(repo_path, issue_number)
        branch = f"claudedev/issue-{issue_number}"

        if not wt_path.is_dir():
            return False

        # Safety check: refuse to clean dirty worktrees
        if await self._is_worktree_dirty(wt_path):
            logger.warning(
                "worktree_cleanup_skipped_dirty",
                issue=issue_number,
                path=str(wt_path),
            )
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

    async def cleanup_merged_worktrees(self, repo_path: Path) -> int:
        """Remove all worktrees whose branches have been merged. Returns count cleaned."""
        worktrees = await self.list_worktrees(repo_path)
        if not worktrees:
            return 0

        try:
            merged_output = await self._run_git(repo_path, "branch", "--merged")
        except WorktreeError:
            return 0

        merged_branches = {b.strip() for b in merged_output.splitlines()}
        cleaned = 0

        for wt in worktrees:
            if wt.branch in merged_branches and await self.cleanup_worktree(
                repo_path, wt.issue_number
            ):
                cleaned += 1

        logger.info("cleanup_merged_worktrees", total=len(worktrees), cleaned=cleaned)
        return cleaned

    async def _is_worktree_dirty(self, wt_path: Path) -> bool:
        """Check if a worktree has uncommitted changes."""
        try:
            output = await self._run_git(wt_path, "status", "--porcelain")
            return bool(output.strip())
        except WorktreeError:
            return True  # Assume dirty if we can't check

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
        self,
        worktree_path: Path,
        session_id: str,
        issue_number: int,
    ) -> None:
        """Write .claude/settings.json inside the worktree with hook configuration."""
        config = copy.deepcopy(_HOOK_CONFIG_TEMPLATE)
        hooks = config["hooks"]
        if not isinstance(hooks, dict):
            raise TypeError(f"Expected hooks to be a dict, got {type(hooks).__name__}")

        for hook_list in hooks.values():
            if not isinstance(hook_list, list):
                raise TypeError(f"Expected hook_list to be a list, got {type(hook_list).__name__}")
            for hook in hook_list:
                if not isinstance(hook, dict):
                    raise TypeError(f"Expected hook to be a dict, got {type(hook).__name__}")
                headers = hook["headers"]
                if not isinstance(headers, dict):
                    raise TypeError(f"Expected headers to be a dict, got {type(headers).__name__}")
                headers["X-Session-Id"] = session_id
                headers["X-Issue-Number"] = str(issue_number)

        claude_dir = worktree_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        settings_path = claude_dir / "settings.json"
        content = json.dumps(config, indent=2)
        await asyncio.to_thread(settings_path.write_text, content)
        logger.info("hook_config_written", worktree=str(worktree_path), session_id=session_id)

    async def _ensure_gitignore(self, repo_path: Path) -> None:
        """Add .claudedev/ to .gitignore if not already present."""
        gitignore = repo_path / ".gitignore"
        pattern = ".claudedev/"
        if gitignore.exists():
            content = await asyncio.to_thread(gitignore.read_text)
            if pattern in content:
                return
            await asyncio.to_thread(gitignore.write_text, content.rstrip() + f"\n{pattern}\n")
        else:
            await asyncio.to_thread(gitignore.write_text, f"{pattern}\n")

    async def _run_git(self, cwd: Path, *args: str) -> str:
        """Run a git command and return stdout. Raises WorktreeError on failure."""
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise WorktreeError(error_msg)
        return stdout.decode("utf-8", errors="replace").strip()
