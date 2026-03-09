"""Async wrapper around the gh CLI for GitHub operations.

Uses asyncio.create_subprocess_exec (not shell) for safe process execution.
"""

from __future__ import annotations

import asyncio
import json

import structlog

from claudedev.github.models import (
    AuthStatus,
    GitHubComment,
    GitHubIssue,
    GitHubPR,
    IssueTimelineEvent,
    WebhookInfo,
)

logger = structlog.get_logger(__name__)


class GHClientError(Exception):
    """Error from gh CLI."""

    def __init__(self, message: str, stderr: str = "", returncode: int = 1) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class GHClient:
    """Async wrapper around the gh CLI for all GitHub API operations.

    All methods use asyncio.create_subprocess_exec (no shell) and parse
    JSON responses into typed Pydantic models.
    """

    def __init__(self, default_host: str = "github.com") -> None:
        self.default_host = default_host

    async def _run_gh(
        self,
        args: list[str],
        input_data: str | None = None,
        check: bool = True,
    ) -> str:
        """Run a gh CLI command safely via subprocess_exec and return stdout."""
        cmd = ["gh", *args]
        log = logger.bind(cmd=" ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate(
            input=input_data.encode() if input_data else None,
        )
        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()

        if check and proc.returncode != 0:
            log.error("gh_cli_error", stderr=stderr, returncode=proc.returncode)
            raise GHClientError(
                f"gh command failed: {stderr}",
                stderr=stderr,
                returncode=proc.returncode or 1,
            )

        return stdout

    # --- Authentication ---

    async def auth_status(self) -> AuthStatus:
        """Check current gh authentication status."""
        try:
            output = await self._run_gh(["auth", "status"], check=False)
            logged_in = "Logged in" in output
            username = ""
            for line in output.splitlines():
                if "account" in line.lower():
                    parts = line.strip().split()
                    for i, part in enumerate(parts):
                        if part.lower() == "account" and i + 1 < len(parts):
                            username = parts[i + 1].strip("()")
                            break
            return AuthStatus(logged_in=logged_in, username=username)
        except Exception:
            return AuthStatus(logged_in=False)

    # --- Issues ---

    async def get_issue(self, repo: str, number: int) -> GitHubIssue:
        """Get a single issue by number."""
        output = await self._run_gh(["api", f"repos/{repo}/issues/{number}"])
        data = json.loads(output)
        return GitHubIssue.model_validate(data)

    async def create_issue(
        self,
        repo: str,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> GitHubIssue:
        """Create a new issue."""
        args = ["issue", "create", "-R", repo, "--title", title, "--body", body]
        if labels:
            for label in labels:
                args.extend(["--label", label])
        if assignees:
            for assignee in assignees:
                args.extend(["--assignee", assignee])
        output = await self._run_gh(args)
        number = int(output.strip().split("/")[-1])
        return await self.get_issue(repo, number)

    async def update_issue(
        self,
        repo: str,
        number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> None:
        """Update an existing issue."""
        args = ["issue", "edit", str(number), "-R", repo]
        if title:
            args.extend(["--title", title])
        if body:
            args.extend(["--body", body])
        if labels:
            args.extend(["--add-label", ",".join(labels)])
        await self._run_gh(args)

        if state and state in ("open", "closed"):
            state_cmd = "reopen" if state == "open" else "close"
            await self._run_gh(["issue", state_cmd, str(number), "-R", repo])

    async def comment_on_issue(self, repo: str, number: int, body: str) -> None:
        """Add a comment to an issue."""
        await self._run_gh(["issue", "comment", str(number), "-R", repo, "--body", body])

    async def list_issues(
        self,
        repo: str,
        state: str = "open",
        limit: int = 30,
        labels: list[str] | None = None,
    ) -> list[GitHubIssue]:
        """List issues for a repository."""
        output = await self._run_gh(
            [
                "api",
                f"repos/{repo}/issues",
                "-X",
                "GET",
                "-f",
                f"state={state}",
                "-f",
                f"per_page={limit}",
            ]
        )
        data = json.loads(output)
        return [GitHubIssue.model_validate(item) for item in data]

    async def list_issue_comments(
        self, repo: str, number: int, *, limit: int = 20
    ) -> list[GitHubComment]:
        """List comments on an issue, newest first."""
        output = await self._run_gh([
            "api", f"repos/{repo}/issues/{number}/comments",
            "--method", "GET",
            "-f", f"per_page={limit}",
            "-f", "sort=created",
            "-f", "direction=desc",
        ])
        data = json.loads(output)
        return [GitHubComment.model_validate(item) for item in data]

    async def list_issue_timeline(
        self, repo: str, number: int, *, limit: int = 50
    ) -> list[IssueTimelineEvent]:
        """List issue timeline events (close, reopen, PR references, etc.)."""
        output = await self._run_gh([
            "api", f"repos/{repo}/issues/{number}/timeline",
            "--method", "GET",
            "-f", f"per_page={limit}",
            "-H", "Accept: application/vnd.github.mockingbird-preview+json",
        ])
        data = json.loads(output)
        # Timeline API returns mixed event types; filter to relevant ones
        relevant_events = {"closed", "reopened", "cross-referenced", "referenced", "renamed", "labeled"}
        events = []
        for item in data:
            if isinstance(item, dict) and item.get("event") in relevant_events:
                events.append(IssueTimelineEvent.model_validate(item))
        return events

    async def get_issue_full_context(
        self, repo: str, number: int
    ) -> tuple[GitHubIssue, list[GitHubComment], list[IssueTimelineEvent]]:
        """Fetch issue, comments, and timeline in parallel-friendly fashion."""
        issue = await self.get_issue(repo, number)
        comments = await self.list_issue_comments(repo, number, limit=10)
        timeline = await self.list_issue_timeline(repo, number, limit=30)
        return issue, comments, timeline

    # --- Pull Requests ---

    async def get_pr(self, repo: str, number: int) -> GitHubPR:
        """Get a single pull request by number."""
        output = await self._run_gh(["api", f"repos/{repo}/pulls/{number}"])
        data = json.loads(output)
        return GitHubPR.model_validate(data)

    async def create_pr(
        self,
        repo: str,
        title: str,
        body: str = "",
        head: str = "",
        base: str = "main",
        draft: bool = False,
    ) -> GitHubPR:
        """Create a new pull request."""
        args = [
            "pr",
            "create",
            "-R",
            repo,
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
        ]
        if head:
            args.extend(["--head", head])
        if draft:
            args.append("--draft")
        output = await self._run_gh(args)
        number = int(output.strip().split("/")[-1])
        return await self.get_pr(repo, number)

    async def review_pr(
        self,
        repo: str,
        number: int,
        body: str = "",
        event: str = "COMMENT",
    ) -> None:
        """Submit a review on a pull request."""
        event_flag_map = {
            "APPROVE": "--approve",
            "REQUEST_CHANGES": "--request-changes",
            "COMMENT": "--comment",
        }
        flag = event_flag_map.get(event, "--comment")
        args = ["pr", "review", str(number), "-R", repo, flag]
        if body:
            args.extend(["--body", body])
        await self._run_gh(args)

    async def merge_pr(
        self,
        repo: str,
        number: int,
        method: str = "squash",
        delete_branch: bool = True,
    ) -> None:
        """Merge a pull request."""
        args = ["pr", "merge", str(number), "-R", repo, f"--{method}"]
        if delete_branch:
            args.append("--delete-branch")
        await self._run_gh(args)

    async def list_prs(
        self,
        repo: str,
        state: str = "open",
        limit: int = 30,
    ) -> list[GitHubPR]:
        """List pull requests for a repository."""
        output = await self._run_gh(
            [
                "api",
                f"repos/{repo}/pulls",
                "-X",
                "GET",
                "-f",
                f"state={state}",
                "-f",
                f"per_page={limit}",
            ]
        )
        data = json.loads(output)
        return [GitHubPR.model_validate(item) for item in data]

    async def get_pr_diff(self, repo: str, number: int) -> str:
        """Get the diff for a pull request."""
        return await self._run_gh(["pr", "diff", str(number), "-R", repo])

    # --- Webhooks ---

    async def install_webhook(
        self,
        repo: str,
        url: str,
        secret: str,
        events: list[str] | None = None,
    ) -> WebhookInfo:
        """Install a webhook on a repository."""
        webhook_events = events or ["issues", "pull_request", "issue_comment"]
        payload: dict[str, str | bool | list[str] | dict[str, str]] = {
            "name": "web",
            "active": True,
            "events": webhook_events,
            "config": {
                "url": url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }
        output = await self._run_gh(
            ["api", f"repos/{repo}/hooks", "-X", "POST", "--input", "-"],
            input_data=json.dumps(payload),
        )
        data = json.loads(output)
        return WebhookInfo.model_validate(data)

    async def update_webhook(
        self,
        repo: str,
        hook_id: int,
        url: str,
        secret: str | None = None,
    ) -> WebhookInfo:
        """Update an existing webhook's URL (and optionally secret)."""
        config: dict[str, str] = {
            "url": url,
            "content_type": "json",
        }
        if secret:
            config["secret"] = secret
        payload: dict[str, str | dict[str, str]] = {"config": config}
        output = await self._run_gh(
            ["api", f"repos/{repo}/hooks/{hook_id}", "-X", "PATCH", "--input", "-"],
            input_data=json.dumps(payload),
        )
        data = json.loads(output)
        return WebhookInfo.model_validate(data)

    async def list_webhooks(self, repo: str) -> list[WebhookInfo]:
        """List webhooks for a repository."""
        output = await self._run_gh(["api", f"repos/{repo}/hooks"])
        data = json.loads(output)
        return [WebhookInfo.model_validate(item) for item in data]

    async def delete_webhook(self, repo: str, hook_id: int) -> None:
        """Delete a webhook from a repository."""
        await self._run_gh(["api", f"repos/{repo}/hooks/{hook_id}", "-X", "DELETE"])
