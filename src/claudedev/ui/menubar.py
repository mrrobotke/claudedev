"""macOS menubar app using rumps for quick status and actions."""

from __future__ import annotations

import contextlib

import structlog

logger = structlog.get_logger(__name__)


class ClaudeDevMenubar:
    """macOS menubar application for ClaudeDev status and quick actions.

    Shows daemon status, tunnel URL, recent events, and provides
    quick access to common operations.

    Threading model
    ---------------
    macOS AppKit (NSStatusBar, NSWindow) **must** be created and run on the
    main thread.  Call ``run_on_main_thread()`` from the main thread after
    launching the async event loop in a background thread.  ``start()`` only
    initialises the rumps application object; it does **not** start the run
    loop.
    """

    def __init__(self, dashboard_port: int = 8787) -> None:
        self._app: object = None
        self._status: str = "stopped"
        self._tunnel_url: str = ""
        self._recent_events: list[dict[str, str]] = []
        self._dashboard_port = dashboard_port

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise the menubar app object (does NOT start the run loop).

        Kept for the caller to set up the app before handing control to
        ``run_on_main_thread()``.  Safe to call from any thread, but
        ``run_on_main_thread()`` **must** subsequently be called from the
        main thread.
        """
        try:
            import rumps

            self._app = rumps.App(
                "ClaudeDev",
                title="CD",
                icon=None,
                quit_button=None,
            )
            self._build_menu()
            logger.info("menubar_initialized")
        except ImportError:
            logger.warning("rumps_not_installed")
        except Exception:
            logger.exception("menubar_init_failed")

    def run_on_main_thread(self) -> None:
        """Run the menubar app on the calling (main) thread — blocks until quit.

        macOS AppKit requires NSStatusBar and NSWindow to be created and
        driven on the main thread.  This method **must** be called from the
        main thread; it blocks until the user quits or the app exits.

        If *rumps* is not available the method falls back to
        ``threading.Event.wait()`` so the daemon process stays alive.
        """
        if self._app is None:
            # rumps not available — keep the main thread alive until
            # interrupted (e.g. SIGTERM from ``daemon stop``).
            import threading

            _exit_event = threading.Event()
            with contextlib.suppress(KeyboardInterrupt):
                _exit_event.wait()
            return

        try:
            self._app.run()  # type: ignore[attr-defined]
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("menubar_stopped")

    def stop(self) -> None:
        """Signal the menubar app to quit (can be called from any thread)."""
        if self._app is not None:
            with contextlib.suppress(Exception):
                import rumps

                rumps.quit_application()
        self._app = None
        logger.info("menubar_stopped")

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        """Build the menubar menu items."""
        import rumps

        if self._app is None:
            return

        status_item = rumps.MenuItem(f"Status: {self._status}")
        status_item.set_callback(None)

        tunnel_item = rumps.MenuItem(f"Tunnel: {self._tunnel_url or 'Not running'}")
        tunnel_item.set_callback(None)

        separator = rumps.separator

        dashboard_item = rumps.MenuItem("Open Dashboard", callback=self._open_dashboard)
        logs_item = rumps.MenuItem("View Logs", callback=self._open_logs)

        projects_menu = rumps.MenuItem("Projects")
        projects_menu.add(rumps.MenuItem("No projects configured"))

        recent_menu = rumps.MenuItem("Recent Events")
        if self._recent_events:
            for event in self._recent_events[-5:]:
                item = rumps.MenuItem(
                    f"[{event.get('type', '?')}] {event.get('summary', 'Unknown')}"
                )
                recent_menu.add(item)
        else:
            recent_menu.add(rumps.MenuItem("No recent events"))

        pause_item = rumps.MenuItem("Pause Processing", callback=self._toggle_pause)
        quit_item = rumps.MenuItem("Quit ClaudeDev", callback=self._quit)

        self._app.menu = [  # type: ignore[attr-defined]
            status_item,
            tunnel_item,
            separator,
            dashboard_item,
            logs_item,
            separator,
            projects_menu,
            recent_menu,
            separator,
            pause_item,
            quit_item,
        ]

    # ------------------------------------------------------------------
    # State updates (can be called from any thread)
    # ------------------------------------------------------------------

    def update_status(self, status: str) -> None:
        """Update the displayed daemon status."""
        self._status = status
        if self._app is not None:
            self._app.title = "CD" if status == "running" else "CD!"  # type: ignore[attr-defined]
        self._rebuild_menu()

    def update_tunnel_url(self, url: str) -> None:
        """Update the displayed tunnel URL."""
        self._tunnel_url = url
        self._rebuild_menu()

    def add_event(self, event_type: str, summary: str) -> None:
        """Add a recent event to the menu."""
        self._recent_events.append({"type": event_type, "summary": summary})
        if len(self._recent_events) > 20:
            self._recent_events = self._recent_events[-20:]
        self._rebuild_menu()

    def notify(self, title: str, message: str) -> None:
        """Show a macOS notification."""
        try:
            import rumps

            rumps.notification(
                title=title,
                subtitle="ClaudeDev",
                message=message,
            )
        except Exception:
            logger.debug("notification_failed", title=title)

    def _rebuild_menu(self) -> None:
        """Rebuild the menu to reflect updated state."""
        with contextlib.suppress(Exception):
            self._build_menu()

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def _open_dashboard(self, _sender: object = None) -> None:
        """Open the web dashboard in the default browser."""
        import webbrowser

        webbrowser.open(f"http://localhost:{self._dashboard_port}/dashboard")

    def _open_logs(self, _sender: object = None) -> None:
        """Open the log directory in Finder."""
        import subprocess

        from claudedev.config import LOG_DIR

        subprocess.Popen(["open", str(LOG_DIR)])

    def _toggle_pause(self, sender: object = None) -> None:
        """Toggle processing pause state."""
        if sender is not None:
            import rumps

            if isinstance(sender, rumps.MenuItem):
                sender.state = not sender.state

    def _quit(self, _sender: object = None) -> None:
        """Quit the menubar app."""
        import rumps

        rumps.quit_application()
