"""Pydantic models for GitHub webhook payloads and API responses."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Common models ---


class GitHubUser(BaseModel):
    """GitHub user as returned by the API."""

    login: str
    id: int
    avatar_url: str = ""
    html_url: str = ""


class GitHubRepository(BaseModel):
    """Repository metadata from webhook payloads."""

    id: int
    name: str
    full_name: str
    private: bool = False
    html_url: str = ""
    default_branch: str = "main"
    owner: GitHubUser


class GitHubLabel(BaseModel):
    """Issue/PR label."""

    id: int
    name: str
    color: str = ""
    description: str | None = None


# --- Issue models ---


class GitHubIssue(BaseModel):
    """GitHub issue from webhook payload or API response."""

    number: int
    title: str
    body: str | None = None
    state: str = "open"
    html_url: str = ""
    user: GitHubUser | None = None
    labels: list[GitHubLabel] = Field(default_factory=list)
    assignees: list[GitHubUser] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pull_request: dict[str, str] | None = None

    @property
    def is_pull_request(self) -> bool:
        return self.pull_request is not None


# --- PR models ---


class PRRef(BaseModel):
    """Branch reference for a PR head or base."""

    ref: str
    sha: str
    label: str = ""


class GitHubPR(BaseModel):
    """GitHub pull request from webhook payload or API response."""

    number: int
    title: str
    body: str | None = None
    state: str = "open"
    html_url: str = ""
    user: GitHubUser | None = None
    head: PRRef
    base: PRRef
    draft: bool = False
    mergeable: bool | None = None
    labels: list[GitHubLabel] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- Comment model ---


class GitHubComment(BaseModel):
    """Issue or PR comment."""

    id: int
    body: str
    user: GitHubUser
    html_url: str = ""
    created_at: datetime | None = None


# --- Timeline model ---


class IssueTimelineEvent(BaseModel):
    """GitHub issue timeline event from the timeline API."""

    event: str  # "closed", "reopened", "cross-referenced", "referenced", "labeled", "renamed", etc.
    created_at: datetime | None = None
    actor: GitHubUser | None = None
    # For "closed" events: the commit/PR that closed it
    commit_id: str | None = None
    commit_url: str | None = None
    # For "cross-referenced" events: the source issue/PR
    source: dict[str, Any] | None = None
    # For "renamed" events
    rename: dict[str, str] | None = None
    # For "labeled"/"unlabeled" events
    label: GitHubLabel | None = None


# --- Webhook event models ---


class IssueEvent(BaseModel):
    """Webhook payload for issue events."""

    action: str
    issue: GitHubIssue
    repository: GitHubRepository
    sender: GitHubUser
    label: GitHubLabel | None = None


class PREvent(BaseModel):
    """Webhook payload for pull_request events."""

    action: str
    pull_request: GitHubPR
    repository: GitHubRepository
    sender: GitHubUser
    number: int = 0


class CommentEvent(BaseModel):
    """Webhook payload for issue_comment and pull_request_review_comment events."""

    action: str
    comment: GitHubComment
    issue: GitHubIssue | None = None
    pull_request: GitHubPR | None = None
    repository: GitHubRepository
    sender: GitHubUser


class PingEvent(BaseModel):
    """Webhook payload for the ping event (sent on webhook creation)."""

    zen: str = ""
    hook_id: int = 0
    repository: GitHubRepository | None = None


WebhookEvent = IssueEvent | PREvent | CommentEvent | PingEvent


# --- gh CLI response models ---


class AuthStatus(BaseModel):
    """Output of gh auth status."""

    logged_in: bool = False
    username: str = ""
    scopes: list[str] = Field(default_factory=list)
    token_source: str = ""


class WebhookInfo(BaseModel):
    """Information about an installed webhook."""

    id: int
    name: str = "web"
    active: bool = True
    events: list[str] = Field(default_factory=list)
    config: dict[str, str] = Field(default_factory=dict)


class PRReviewRequest(BaseModel):
    """Parameters for submitting a PR review."""

    body: str
    event: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"] = "COMMENT"
