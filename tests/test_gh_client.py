"""Tests for the GitHub CLI wrapper (GHClient)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from claudedev.github.gh_client import GHClient, GHClientError


@pytest.fixture
def gh_client() -> GHClient:
    return GHClient()


def _make_process_mock(stdout: str = "", stderr: str = "", returncode: int = 0) -> AsyncMock:
    """Create a mock for asyncio.create_subprocess_exec return value."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    proc.returncode = returncode
    return proc


class TestGHClientRunGh:
    async def test_run_gh_success(self, gh_client: GHClient) -> None:
        proc = _make_process_mock(stdout="output text")
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await gh_client._run_gh(["auth", "status"])
        assert result == "output text"

    async def test_run_gh_failure_raises(self, gh_client: GHClient) -> None:
        proc = _make_process_mock(stderr="not found", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(GHClientError) as exc_info:
                await gh_client._run_gh(["issue", "view", "999"])
            assert "not found" in str(exc_info.value)
            assert exc_info.value.returncode == 1

    async def test_run_gh_check_false_no_raise(self, gh_client: GHClient) -> None:
        proc = _make_process_mock(stderr="some warning", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await gh_client._run_gh(["auth", "status"], check=False)
        assert result == ""

    async def test_run_gh_with_input_data(self, gh_client: GHClient) -> None:
        proc = _make_process_mock(stdout='{"id": 1}')
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            await gh_client._run_gh(["api", "endpoint"], input_data='{"key":"val"}')
        proc.communicate.assert_awaited_once()
        call_kwargs = proc.communicate.call_args
        assert call_kwargs[1]["input"] == b'{"key":"val"}'


class TestCreateIssue:
    async def test_create_issue_calls_gh(self, gh_client: GHClient) -> None:
        issue_url = "https://github.com/owner/repo/issues/5"
        issue_data = {
            "number": 5,
            "title": "Test issue",
            "body": "body",
            "state": "open",
            "user": {"login": "user", "id": 1},
            "labels": [],
            "assignees": [],
        }

        call_count = 0

        async def mock_run_gh(args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # create issue returns URL
                return issue_url
            else:
                # get_issue returns JSON
                return json.dumps(issue_data)

        gh_client._run_gh = AsyncMock(side_effect=mock_run_gh)

        result = await gh_client.create_issue("owner/repo", "Test issue", "body")
        assert result.number == 5
        assert result.title == "Test issue"

    async def test_create_issue_with_labels_and_assignees(self, gh_client: GHClient) -> None:
        issue_data = {
            "number": 6,
            "title": "Labeled",
            "state": "open",
            "user": {"login": "u", "id": 1},
            "labels": [{"id": 1, "name": "bug", "color": "red"}],
            "assignees": [],
        }

        calls = []

        async def mock_run(args, **kwargs):
            calls.append(args)
            if "create" in args:
                return "https://github.com/o/r/issues/6"
            return json.dumps(issue_data)

        gh_client._run_gh = AsyncMock(side_effect=mock_run)

        await gh_client.create_issue("o/r", "Labeled", labels=["bug"], assignees=["user1"])
        create_args = calls[0]
        assert "--label" in create_args
        assert "bug" in create_args
        assert "--assignee" in create_args
        assert "user1" in create_args


class TestUpdateIssue:
    async def test_update_issue_basic(self, gh_client: GHClient) -> None:
        gh_client._run_gh = AsyncMock(return_value="")
        await gh_client.update_issue("o/r", 1, title="New Title")
        call_args = gh_client._run_gh.call_args_list[0][0][0]
        assert "edit" in call_args
        assert "--title" in call_args
        assert "New Title" in call_args

    async def test_update_issue_close(self, gh_client: GHClient) -> None:
        gh_client._run_gh = AsyncMock(return_value="")
        await gh_client.update_issue("o/r", 1, state="closed")
        assert gh_client._run_gh.call_count == 2
        close_args = gh_client._run_gh.call_args_list[1][0][0]
        assert "close" in close_args

    async def test_update_issue_reopen(self, gh_client: GHClient) -> None:
        gh_client._run_gh = AsyncMock(return_value="")
        await gh_client.update_issue("o/r", 1, state="open")
        reopen_args = gh_client._run_gh.call_args_list[1][0][0]
        assert "reopen" in reopen_args


class TestParsePaginatedJson:
    def test_empty_string_returns_empty(self) -> None:
        from claudedev.github.gh_client import _parse_paginated_json

        assert _parse_paginated_json("") == []

    def test_whitespace_only_returns_empty(self) -> None:
        from claudedev.github.gh_client import _parse_paginated_json

        assert _parse_paginated_json("   \n  ") == []

    def test_single_page(self) -> None:
        from claudedev.github.gh_client import _parse_paginated_json

        raw = json.dumps([{"id": 1}, {"id": 2}])
        result = _parse_paginated_json(raw)
        assert result == [{"id": 1}, {"id": 2}]

    def test_two_pages_concatenated(self) -> None:
        from claudedev.github.gh_client import _parse_paginated_json

        page1 = json.dumps([{"id": 1}, {"id": 2}])
        page2 = json.dumps([{"id": 3}])
        result = _parse_paginated_json(page1 + page2)
        assert len(result) == 3
        assert result[2]["id"] == 3

    def test_pages_separated_by_whitespace(self) -> None:
        from claudedev.github.gh_client import _parse_paginated_json

        page1 = json.dumps([{"id": 1}])
        page2 = json.dumps([{"id": 2}])
        result = _parse_paginated_json(page1 + "\n" + page2)
        assert len(result) == 2

    def test_three_pages(self) -> None:
        from claudedev.github.gh_client import _parse_paginated_json

        pages = [json.dumps([{"id": i}]) for i in range(3)]
        result = _parse_paginated_json("".join(pages))
        assert len(result) == 3

    def test_invalid_json_stops_gracefully(self) -> None:
        from claudedev.github.gh_client import _parse_paginated_json

        raw = json.dumps([{"id": 1}]) + "garbage"
        result = _parse_paginated_json(raw)
        assert len(result) == 1

    def test_error_object_returns_empty(self) -> None:
        """A JSON object (e.g., rate limit error) returns empty list."""
        from claudedev.github.gh_client import _parse_paginated_json

        raw = (
            '{"message": "API rate limit exceeded", "documentation_url": "https://docs.github.com"}'
        )
        result = _parse_paginated_json(raw)
        assert result == []


class TestListIssues:
    async def test_list_issues_parses_json(self, gh_client: GHClient) -> None:
        issues_json = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Issue 1",
                    "state": "open",
                    "user": {"login": "u", "id": 1},
                    "labels": [],
                    "assignees": [],
                },
                {
                    "number": 2,
                    "title": "Issue 2",
                    "state": "open",
                    "user": {"login": "u", "id": 1},
                    "labels": [],
                    "assignees": [],
                },
            ]
        )
        gh_client._run_gh = AsyncMock(return_value=issues_json)

        result = await gh_client.list_issues("o/r")
        assert len(result) == 2
        assert result[0].number == 1
        assert result[1].title == "Issue 2"

    async def test_list_issues_uses_paginate_flag(self, gh_client: GHClient) -> None:
        """list_issues must pass --paginate to the gh CLI."""
        gh_client._run_gh = AsyncMock(return_value=json.dumps([]))
        await gh_client.list_issues("o/r")
        args_passed: list[str] = gh_client._run_gh.call_args[0][0]
        assert "--paginate" in args_passed

    async def test_list_issues_filters_prs(self, gh_client: GHClient) -> None:
        """Items with a 'pull_request' key must be excluded from results."""
        mixed = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Real issue",
                    "state": "open",
                    "user": {"login": "u", "id": 1},
                    "labels": [],
                    "assignees": [],
                },
                {
                    "number": 2,
                    "title": "A PR pretending to be an issue",
                    "state": "open",
                    "user": {"login": "u", "id": 1},
                    "labels": [],
                    "assignees": [],
                    "pull_request": {"url": "https://github.com/o/r/pull/2"},
                },
            ]
        )
        gh_client._run_gh = AsyncMock(return_value=mixed)
        result = await gh_client.list_issues("o/r")
        assert len(result) == 1
        assert result[0].number == 1

    async def test_list_issues_multipage(self, gh_client: GHClient) -> None:
        """list_issues correctly handles --paginate multi-array output."""
        page1 = json.dumps(
            [
                {
                    "number": i,
                    "title": f"Issue {i}",
                    "state": "open",
                    "user": {"login": "u", "id": 1},
                    "labels": [],
                    "assignees": [],
                }
                for i in range(1, 101)
            ]
        )
        page2 = json.dumps(
            [
                {
                    "number": i,
                    "title": f"Issue {i}",
                    "state": "open",
                    "user": {"login": "u", "id": 1},
                    "labels": [],
                    "assignees": [],
                }
                for i in range(101, 148)
            ]
        )
        gh_client._run_gh = AsyncMock(return_value=page1 + page2)
        result = await gh_client.list_issues("o/r")
        assert len(result) == 147

    async def test_list_issues_no_limit_param(self, gh_client: GHClient) -> None:
        """list_issues must not pass a limit kwarg — signature changed."""
        import inspect

        sig = inspect.signature(GHClient.list_issues)
        assert "limit" not in sig.parameters

    async def test_list_issues_with_labels(self, gh_client: GHClient) -> None:
        gh_client._run_gh = AsyncMock(return_value=json.dumps([]))
        await gh_client.list_issues("o/r", labels=["bug", "enhancement"])
        args_passed: list[str] = gh_client._run_gh.call_args[0][0]
        assert "labels=bug,enhancement" in args_passed


class TestInstallWebhook:
    async def test_install_webhook_sends_correct_payload(self, gh_client: GHClient) -> None:
        webhook_response = json.dumps(
            {
                "id": 42,
                "name": "web",
                "active": True,
                "events": ["issues", "pull_request"],
                "config": {"url": "https://example.com/webhook"},
            }
        )
        gh_client._run_gh = AsyncMock(return_value=webhook_response)

        result = await gh_client.install_webhook("o/r", "https://example.com/webhook", "secret123")
        assert result.id == 42
        assert result.active is True

        call_args = gh_client._run_gh.call_args
        assert call_args[1]["input_data"] is not None
        sent_payload = json.loads(call_args[1]["input_data"])
        assert sent_payload["config"]["url"] == "https://example.com/webhook"
        assert sent_payload["config"]["secret"] == "secret123"

    async def test_install_webhook_custom_events(self, gh_client: GHClient) -> None:
        webhook_response = json.dumps(
            {
                "id": 43,
                "name": "web",
                "active": True,
                "events": ["push"],
                "config": {},
            }
        )
        gh_client._run_gh = AsyncMock(return_value=webhook_response)

        await gh_client.install_webhook("o/r", "https://x.com/hook", "s", events=["push"])
        sent = json.loads(gh_client._run_gh.call_args[1]["input_data"])
        assert sent["events"] == ["push"]


class TestUpdateWebhook:
    async def test_update_webhook_sends_correct_payload(self, gh_client: GHClient) -> None:
        webhook_response = json.dumps(
            {
                "id": 42,
                "name": "web",
                "active": True,
                "events": ["issues", "pull_request"],
                "config": {"url": "https://new.example.com/webhook"},
            }
        )
        gh_client._run_gh = AsyncMock(return_value=webhook_response)

        result = await gh_client.update_webhook(
            "o/r", 42, "https://new.example.com/webhook", secret="newsecret"
        )
        assert result.id == 42
        assert result.active is True

        call_args = gh_client._run_gh.call_args
        args_list: list[str] = call_args[0][0]
        assert "PATCH" in args_list
        assert "repos/o/r/hooks/42" in args_list

        sent_payload = json.loads(call_args[1]["input_data"])
        assert sent_payload["config"]["url"] == "https://new.example.com/webhook"
        assert sent_payload["config"]["secret"] == "newsecret"

    async def test_update_webhook_without_secret(self, gh_client: GHClient) -> None:
        webhook_response = json.dumps(
            {
                "id": 7,
                "name": "web",
                "active": True,
                "events": ["push"],
                "config": {"url": "https://x.example.com/hook"},
            }
        )
        gh_client._run_gh = AsyncMock(return_value=webhook_response)

        result = await gh_client.update_webhook("owner/repo", 7, "https://x.example.com/hook")
        assert result.id == 7

        sent_payload = json.loads(gh_client._run_gh.call_args[1]["input_data"])
        assert "secret" not in sent_payload["config"]

    async def test_update_webhook_propagates_gh_error(self, gh_client: GHClient) -> None:
        from claudedev.github.gh_client import GHClientError

        gh_client._run_gh = AsyncMock(
            side_effect=GHClientError("not found", stderr="Not Found", returncode=404)
        )
        with pytest.raises(GHClientError):
            await gh_client.update_webhook("o/r", 999, "https://x.com/hook")


class TestAuthStatus:
    async def test_auth_status_logged_in(self, gh_client: GHClient) -> None:
        output = (
            "github.com\n"
            "  Logged in to github.com account testuser (keyring)\n"
            "  Git operations for github.com configured to use ssh protocol."
        )
        gh_client._run_gh = AsyncMock(return_value=output)
        status = await gh_client.auth_status()
        assert status.logged_in is True
        assert status.username == "testuser"

    async def test_auth_status_not_logged_in(self, gh_client: GHClient) -> None:
        gh_client._run_gh = AsyncMock(return_value="You are not logged in")
        status = await gh_client.auth_status()
        assert status.logged_in is False

    async def test_auth_status_exception_returns_false(self, gh_client: GHClient) -> None:
        gh_client._run_gh = AsyncMock(side_effect=Exception("network error"))
        status = await gh_client.auth_status()
        assert status.logged_in is False


class TestCommandFailure:
    async def test_command_failure_error_message(self, gh_client: GHClient) -> None:
        proc = _make_process_mock(stderr="permission denied", returncode=128)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(GHClientError) as exc_info:
                await gh_client._run_gh(["repo", "view"])
            assert exc_info.value.stderr == "permission denied"
            assert exc_info.value.returncode == 128
