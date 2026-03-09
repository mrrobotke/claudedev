"""Tests for Pydantic model validation (GitHub webhook payloads)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from claudedev.github.models import (
    AuthStatus,
    CommentEvent,
    GitHubIssue,
    GitHubLabel,
    GitHubPR,
    GitHubUser,
    IssueEvent,
    PingEvent,
    PREvent,
    PRRef,
    WebhookInfo,
)


class TestGitHubUser:
    def test_parse_minimal(self) -> None:
        user = GitHubUser(login="octocat", id=1)
        assert user.login == "octocat"
        assert user.id == 1
        assert user.avatar_url == ""
        assert user.html_url == ""

    def test_parse_full(self) -> None:
        user = GitHubUser(
            login="octocat",
            id=1,
            avatar_url="https://avatars.githubusercontent.com/u/1",
            html_url="https://github.com/octocat",
        )
        assert user.html_url == "https://github.com/octocat"


class TestGitHubIssue:
    def test_parse_basic_issue(self) -> None:
        issue = GitHubIssue(
            number=42,
            title="Bug: login broken",
            body="Steps to reproduce...",
            state="open",
        )
        assert issue.number == 42
        assert issue.title == "Bug: login broken"
        assert issue.state == "open"
        assert issue.labels == []
        assert issue.is_pull_request is False

    def test_issue_is_pull_request(self) -> None:
        issue = GitHubIssue(
            number=10,
            title="PR as issue",
            pull_request={"url": "https://api.github.com/repos/o/r/pulls/10"},
        )
        assert issue.is_pull_request is True

    def test_issue_with_labels(self) -> None:
        issue = GitHubIssue(
            number=1,
            title="Labeled",
            labels=[
                GitHubLabel(id=1, name="bug", color="d73a4a"),
                GitHubLabel(id=2, name="enhancement", color="a2eeef"),
            ],
        )
        assert len(issue.labels) == 2
        assert issue.labels[0].name == "bug"


class TestGitHubPR:
    def test_parse_pr(self) -> None:
        pr = GitHubPR(
            number=10,
            title="Fix redirect",
            state="open",
            head=PRRef(ref="feature-branch", sha="abc123"),
            base=PRRef(ref="main", sha="def456"),
        )
        assert pr.number == 10
        assert pr.head.ref == "feature-branch"
        assert pr.base.ref == "main"
        assert pr.draft is False

    def test_draft_pr(self) -> None:
        pr = GitHubPR(
            number=11,
            title="WIP",
            head=PRRef(ref="wip", sha="111"),
            base=PRRef(ref="main", sha="222"),
            draft=True,
        )
        assert pr.draft is True


class TestIssueEventParsing:
    def test_parse_real_payload(self, issue_event_payload: dict[str, Any]) -> None:
        event = IssueEvent.model_validate(issue_event_payload)
        assert event.action == "opened"
        assert event.issue.number == 42
        assert event.issue.title == "Fix login redirect"
        assert event.repository.full_name == "test/repo"
        assert event.sender.login == "testuser"

    def test_issue_event_with_label(self) -> None:
        payload = {
            "action": "labeled",
            "issue": {
                "number": 5,
                "title": "Add feature",
                "state": "open",
                "user": {"login": "u", "id": 1},
                "labels": [{"id": 1, "name": "enhancement", "color": "aaa"}],
                "assignees": [],
            },
            "label": {"id": 1, "name": "enhancement", "color": "aaa"},
            "repository": {
                "id": 1,
                "name": "r",
                "full_name": "o/r",
                "owner": {"login": "o", "id": 1},
            },
            "sender": {"login": "u", "id": 1},
        }
        event = IssueEvent.model_validate(payload)
        assert event.label is not None
        assert event.label.name == "enhancement"


class TestPREventParsing:
    def test_parse_real_payload(self, pr_event_payload: dict[str, Any]) -> None:
        event = PREvent.model_validate(pr_event_payload)
        assert event.action == "opened"
        assert event.pull_request.number == 10
        assert event.pull_request.head.ref == "claudedev/issue-42"
        assert event.pull_request.base.ref == "main"
        assert event.repository.full_name == "test/repo"
        assert event.number == 10


class TestCommentEventParsing:
    def test_parse_real_payload(self, comment_event_payload: dict[str, Any]) -> None:
        event = CommentEvent.model_validate(comment_event_payload)
        assert event.action == "created"
        assert event.comment.id == 777
        assert event.comment.body == "/implement"
        assert event.issue is not None
        assert event.issue.number == 42
        assert event.repository.full_name == "test/repo"

    def test_comment_event_without_issue(self) -> None:
        """PR review comment may not have issue field."""
        payload = {
            "action": "created",
            "comment": {
                "id": 888,
                "body": "LGTM",
                "user": {"login": "reviewer", "id": 2},
            },
            "repository": {
                "id": 1,
                "name": "r",
                "full_name": "o/r",
                "owner": {"login": "o", "id": 1},
            },
            "sender": {"login": "reviewer", "id": 2},
        }
        event = CommentEvent.model_validate(payload)
        assert event.issue is None
        assert event.pull_request is None


class TestPingEventParsing:
    def test_parse_ping(self) -> None:
        payload = {
            "zen": "Anything added dilutes everything else.",
            "hook_id": 12345,
            "repository": {
                "id": 1,
                "name": "r",
                "full_name": "o/r",
                "owner": {"login": "o", "id": 1},
            },
        }
        event = PingEvent.model_validate(payload)
        assert event.zen == "Anything added dilutes everything else."
        assert event.hook_id == 12345
        assert event.repository is not None

    def test_parse_ping_minimal(self) -> None:
        event = PingEvent.model_validate({})
        assert event.zen == ""
        assert event.hook_id == 0
        assert event.repository is None


class TestInvalidPayloads:
    def test_issue_event_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            IssueEvent.model_validate({"action": "opened"})

    def test_pr_event_missing_pull_request(self) -> None:
        with pytest.raises(ValidationError):
            PREvent.model_validate(
                {
                    "action": "opened",
                    "repository": {
                        "id": 1,
                        "name": "r",
                        "full_name": "o/r",
                        "owner": {"login": "o", "id": 1},
                    },
                    "sender": {"login": "u", "id": 1},
                }
            )

    def test_user_missing_login(self) -> None:
        with pytest.raises(ValidationError):
            GitHubUser(id=1)  # type: ignore[call-arg]

    def test_user_missing_id(self) -> None:
        with pytest.raises(ValidationError):
            GitHubUser(login="test")  # type: ignore[call-arg]


class TestNestedModelParsing:
    def test_deeply_nested_issue_event(self) -> None:
        payload = {
            "action": "opened",
            "issue": {
                "number": 100,
                "title": "Nested test",
                "state": "open",
                "user": {
                    "login": "deep-user",
                    "id": 999,
                    "avatar_url": "https://avatars.example.com/999",
                    "html_url": "https://github.com/deep-user",
                },
                "labels": [
                    {
                        "id": 10,
                        "name": "bug",
                        "color": "d73a4a",
                        "description": "Something isn't working",
                    },
                    {"id": 20, "name": "priority:high", "color": "ff0000", "description": None},
                ],
                "assignees": [
                    {"login": "assignee1", "id": 111},
                    {"login": "assignee2", "id": 222},
                ],
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-16T14:00:00Z",
            },
            "repository": {
                "id": 5000,
                "name": "deep-repo",
                "full_name": "org/deep-repo",
                "private": True,
                "default_branch": "develop",
                "owner": {
                    "login": "org",
                    "id": 500,
                    "avatar_url": "https://avatars.example.com/org",
                },
            },
            "sender": {"login": "deep-user", "id": 999},
        }
        event = IssueEvent.model_validate(payload)

        assert event.issue.user is not None
        assert event.issue.user.login == "deep-user"
        assert event.issue.user.avatar_url == "https://avatars.example.com/999"
        assert len(event.issue.labels) == 2
        assert event.issue.labels[1].name == "priority:high"
        assert event.issue.labels[1].description is None
        assert len(event.issue.assignees) == 2
        assert event.issue.assignees[0].login == "assignee1"
        assert event.repository.private is True
        assert event.repository.default_branch == "develop"
        assert event.issue.created_at is not None


class TestAuthStatusModel:
    def test_default_values(self) -> None:
        status = AuthStatus()
        assert status.logged_in is False
        assert status.username == ""
        assert status.scopes == []

    def test_logged_in(self) -> None:
        status = AuthStatus(logged_in=True, username="user1")
        assert status.logged_in is True
        assert status.username == "user1"


class TestWebhookInfoModel:
    def test_parse_webhook_info(self) -> None:
        info = WebhookInfo(
            id=42,
            name="web",
            active=True,
            events=["issues", "pull_request"],
            config={"url": "https://example.com/hook"},
        )
        assert info.id == 42
        assert info.events == ["issues", "pull_request"]

    def test_default_values(self) -> None:
        info = WebhookInfo(id=1)
        assert info.name == "web"
        assert info.active is True
        assert info.events == []
