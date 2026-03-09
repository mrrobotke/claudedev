"""iTerm2 Python API wrapper for visual session management.

Provides tab/pane creation, command execution, and output monitoring
using the iTerm2 Python API.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TerminalPane:
    """Represents an iTerm2 pane with its session ID and metadata."""

    session_id: str
    name: str
    working_dir: str = ""
    is_active: bool = True


@dataclass
class TerminalTab:
    """Represents an iTerm2 tab containing one or more panes."""

    tab_id: str
    name: str
    panes: list[TerminalPane] = field(default_factory=list)


class ITerm2Manager:
    """Manages iTerm2 sessions for visual Claude Agent SDK session monitoring.

    Creates dedicated tabs and panes for each agent session so developers
    can observe agent activity in real time.
    """

    def __init__(self) -> None:
        self._connection: object = None
        self._tabs: dict[str, TerminalTab] = {}
        self._connected = False

    async def connect(self) -> bool:
        """Establish connection to the iTerm2 application."""
        try:
            import iterm2

            self._connection = await iterm2.Connection.async_create()
            self._connected = True
            logger.info("iterm2_connected")
            return True
        except ImportError:
            logger.warning("iterm2_not_installed")
            return False
        except Exception:
            logger.exception("iterm2_connection_failed")
            return False

    async def create_session_tab(
        self,
        session_name: str,
        working_dir: str,
        pane_names: list[str] | None = None,
    ) -> TerminalTab | None:
        """Create a new iTerm2 tab for an agent session with optional split panes."""
        if not self._connected or self._connection is None:
            logger.warning("iterm2_not_connected")
            return None

        try:
            import iterm2

            app = await iterm2.async_get_app(self._connection)
            if app is None:
                return None

            window = app.current_terminal_window
            if window is None:
                window = await iterm2.Window.async_create(self._connection)
                if window is None:
                    return None

            tab = await window.async_create_tab()
            current_session = tab.current_session
            if current_session is None:
                return None

            await current_session.async_set_name(session_name)

            main_pane = TerminalPane(
                session_id=current_session.session_id,
                name=session_name,
                working_dir=working_dir,
            )
            terminal_tab = TerminalTab(
                tab_id=tab.tab_id,
                name=session_name,
                panes=[main_pane],
            )

            if pane_names:
                for pane_name in pane_names:
                    split_session = await current_session.async_split_pane(vertical=True)
                    if split_session:
                        await split_session.async_set_name(pane_name)
                        terminal_tab.panes.append(
                            TerminalPane(
                                session_id=split_session.session_id,
                                name=pane_name,
                                working_dir=working_dir,
                            )
                        )

            self._tabs[session_name] = terminal_tab
            logger.info("iterm2_tab_created", tab=session_name, panes=len(terminal_tab.panes))
            return terminal_tab

        except Exception:
            logger.exception("iterm2_create_tab_failed", session=session_name)
            return None

    async def send_command(
        self,
        session_name: str,
        command: str,
        pane_index: int = 0,
    ) -> bool:
        """Send a command to a specific pane in a session tab."""
        if not self._connected or self._connection is None:
            return False

        tab = self._tabs.get(session_name)
        if tab is None or pane_index >= len(tab.panes):
            return False

        try:
            import iterm2

            app = await iterm2.async_get_app(self._connection)
            if app is None:
                return False

            pane = tab.panes[pane_index]
            session = app.get_session_by_id(pane.session_id)
            if session is None:
                return False

            await session.async_send_text(command + "\n")
            return True

        except Exception:
            logger.exception("iterm2_send_failed", session=session_name)
            return False

    async def get_pane_output(
        self,
        session_name: str,
        pane_index: int = 0,
        line_count: int = 50,
    ) -> str:
        """Read recent output from a specific pane."""
        if not self._connected or self._connection is None:
            return ""

        tab = self._tabs.get(session_name)
        if tab is None or pane_index >= len(tab.panes):
            return ""

        try:
            import iterm2

            app = await iterm2.async_get_app(self._connection)
            if app is None:
                return ""

            pane = tab.panes[pane_index]
            session = app.get_session_by_id(pane.session_id)
            if session is None:
                return ""

            contents = await session.async_get_screen_contents()
            lines: list[str] = []
            for i in range(contents.number_of_lines):
                line = contents.line(i)
                lines.append(line.string)

            return "\n".join(lines[-line_count:])

        except Exception:
            logger.exception("iterm2_read_failed", session=session_name)
            return ""

    async def close_tab(self, session_name: str) -> bool:
        """Close an iTerm2 tab and all its panes."""
        if not self._connected or self._connection is None:
            return False

        tab = self._tabs.pop(session_name, None)
        if tab is None:
            return False

        try:
            import iterm2

            app = await iterm2.async_get_app(self._connection)
            if app is None:
                return False

            for pane in tab.panes:
                session = app.get_session_by_id(pane.session_id)
                if session:
                    await session.async_close()
                pane.is_active = False

            logger.info("iterm2_tab_closed", session=session_name)
            return True

        except Exception:
            logger.exception("iterm2_close_failed", session=session_name)
            return False

    async def disconnect(self) -> None:
        """Close all tabs and disconnect from iTerm2."""
        for name in list(self._tabs.keys()):
            await self.close_tab(name)
        self._connected = False
        self._connection = None
        logger.info("iterm2_disconnected")

    @property
    def active_tabs(self) -> list[str]:
        """Return names of all active session tabs."""
        return list(self._tabs.keys())
