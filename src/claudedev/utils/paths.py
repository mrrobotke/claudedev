"""Path utilities for Claude Code integration."""


def escape_path_for_claude(path: str) -> str:
    """Escape an absolute filesystem path to match Claude Code's project directory naming.

    Claude Code stores project session files under ``~/.claude/projects/`` using a
    deterministic escaping of the project path:

    1. Replace every ``/`` with ``-``.
    2. Replace every ``.`` with ``-``.

    This means a leading dot (e.g. ``.claudedev``) produces a double dash because the
    preceding slash was already converted to a dash::

        /Users/alice/myproject       → -Users-alice-myproject
        /Users/alice/.claudedev      → -Users-alice--claudedev
        /home/bob/proj-v3.5.1        → -home-bob-proj-v3-5-1

    Args:
        path: Absolute filesystem path (e.g. from ``os.getcwd()`` or a repo root).

    Returns:
        The escaped string that matches the corresponding ``~/.claude/projects/``
        subdirectory name.
    """
    return path.replace("/", "-").replace(".", "-")
