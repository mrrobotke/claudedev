"""Tests for claudedev.utils.paths.escape_path_for_claude."""

import pytest

from claudedev.utils.paths import escape_path_for_claude


class TestEscapePathForClaude:
    """Verify escape_path_for_claude matches Claude Code's directory naming."""

    def test_simple_path(self) -> None:
        """Plain path with no dots."""
        assert escape_path_for_claude("/Users/alice/myproject") == "-Users-alice-myproject"

    def test_path_with_leading_dot_segment(self) -> None:
        """.claudedev segment: dot is removed, slash becomes dash → double dash."""
        assert (
            escape_path_for_claude("/Users/alice/repo/.claudedev/worktrees/issue-1")
            == "-Users-alice-repo--claudedev-worktrees-issue-1"
        )

    def test_dot_claude_directory(self) -> None:
        """~/.claude path — the canonical case that was broken."""
        assert escape_path_for_claude("/Users/iworldafric/.claude") == "-Users-iworldafric--claude"

    def test_dotfile_segment(self) -> None:
        """.git and other dotfiles."""
        assert escape_path_for_claude("/home/bob/repo/.git") == "-home-bob-repo--git"

    def test_version_dots_in_name(self) -> None:
        """Dots inside segment names (version strings) are also removed."""
        assert (
            escape_path_for_claude("/Users/alice/pkg-v3.5.46/src")
            == "-Users-alice-pkg-v3-5-46-src"
        )

    def test_multiple_dot_segments(self) -> None:
        """Multiple dot-prefixed segments in the same path."""
        assert (
            escape_path_for_claude("/Users/alice/.config/.myapp")
            == "-Users-alice--config--myapp"
        )

    def test_real_worktree_path(self) -> None:
        """Exact example from the bug report."""
        path = "/Users/iworldafric/Ignixxion/CEMEA/cemea-backend/.claudedev/worktrees/issue-252"
        expected = "-Users-iworldafric-Ignixxion-CEMEA-cemea-backend--claudedev-worktrees-issue-252"
        assert escape_path_for_claude(path) == expected

    def test_path_without_dots(self) -> None:
        """Path with no dots at all is unchanged except slashes."""
        assert escape_path_for_claude("/a/b/c") == "-a-b-c"

    def test_root_path(self) -> None:
        """Edge case: root '/' alone."""
        assert escape_path_for_claude("/") == "-"

    def test_empty_string(self) -> None:
        """Edge case: empty string."""
        assert escape_path_for_claude("") == ""

    def test_existing_dash_in_segment(self) -> None:
        """Dashes already in segment names are preserved (not doubled)."""
        result = escape_path_for_claude("/Users/alice/cemea-backend/worktrees/issue-252")
        assert result == "-Users-alice-cemea-backend-worktrees-issue-252"

    def test_dot_only_segment(self) -> None:
        """A segment that is just a dot (e.g. '/foo/./bar') — dot is replaced with dash."""
        # /foo/./bar → -foo-.-bar → -foo---bar (slash→dash, dot→dash)
        assert escape_path_for_claude("/foo/./bar") == "-foo---bar"
