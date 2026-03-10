# ClaudeDev

[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-181%20passing-brightgreen.svg)](#)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-orange.svg)](https://claude.ai/code)
[![Code Style: ruff](https://img.shields.io/badge/code%20style-ruff-black.svg)](https://github.com/astral-sh/ruff)

**The autonomous coding companion built for Claude Code users.**

ClaudeDev listens to your GitHub repositories, understands your issues at a deep level, and deploys full implementation teams — automatically. From webhook to merged PR, with zero manual intervention.

---

## Table of Contents

- [What is ClaudeDev?](#what-is-claudedev)
- [How It Works](#how-it-works)
- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Architecture](#architecture)
- [CLI Reference](#cli-reference)
- [Web Dashboard](#web-dashboard)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## What is ClaudeDev?

ClaudeDev is a daemon-based autonomous development orchestrator that transforms GitHub issues into merged pull requests — without you lifting a finger. It was built from the ground up to work alongside [Claude Code](https://claude.ai/code), leveraging the Claude Agent SDK to spawn structured teams of specialized agents for implementation, review, and validation.

When a new issue lands in your repository, ClaudeDev doesn't just acknowledge it. It explores your codebase, identifies the root cause, validates its understanding using Playwright-based browser automation, and rewrites the issue body with a professional technical analysis. It then classifies the issue by complexity, spawns the right team for the job, implements the fix across your codebase, and opens a PR with a full review cycle already complete.

Think of ClaudeDev as a tireless senior engineer on your team — one that monitors your repos 24/7, never skips code review, and always writes typed, linted, tested code. It is not a code generation tool. It is an orchestration layer that makes Claude Code autonomous.

---

## How It Works

```
GitHub Issue Created
        │
        ▼
┌─────────────────────┐
│   Webhook Ingress   │  ← Cloudflare Tunnel routes to local daemon
│  (FastAPI server)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Issue Enhancement  │  ← Explores repo, identifies root cause,
│     Pipeline        │    validates via Playwright, rewrites issue body
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Tier Classification│  ← Tier 1 (bugfix) → Tier 4 (cross-domain feature)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Team Spawning     │  ← Architect + Implementers + 8 specialized reviewers
│  (Agent SDK teams)  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Implementation    │  ← Parallel file-owned implementation
│   + Review Cycle    │    Security, quality, type, performance, test reviews
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   PR Creation       │  ← Quality gates: ruff + mypy + pytest
│   + Quality Gates   │
└────────┬────────────┘
         │
         ▼
     PR Ready for Merge
```

---

## Features

### Core Pipeline

- **Webhook Integration** — Listens for GitHub issue, PR, and comment events with HMAC-verified payloads
- **Automatic Issue Enhancement** — Deep-dives into your repo, rewrites issues with root cause analysis, reproduction steps, and implementation recommendations
- **Tier Classification** — Routes issues to the right team size (Tier 1: minimal bugfix → Tier 4: full cross-domain feature)
- **Implementation Teams** — Spawns architect + implementers + up to 8 specialized reviewers using the Claude Agent SDK
- **Multi-Reviewer Pipeline** — Parallel reviews for security (OWASP), code quality, test coverage, performance, type safety, atomic design, error handling, and simplicity
- **PR Lifecycle Management** — Creates PRs, runs review cycles, iterates on findings, enforces quality gates before marking ready

### Dashboard & Monitoring

- **Web Dashboard** — Real-time monitoring of tracked repositories, active agent sessions, issue queue, and PR status
- **macOS Menubar App** — Native menubar indicator with quick-access controls via rumps
- **Structured Logging** — structlog-based JSON logging with configurable levels and log rotation
- **Cost Tracking** — Per-issue, per-project-daily, and global daily spend budgets with hard limits
- **macOS Notifications** — Native notifications for issue enhancement, implementation complete, PR ready, and errors

### Intelligence Features

- **Credential Discovery** — Automatically finds test credentials in `.env` files for Playwright-based validation
- **Issue Context Enrichment** — Fetches issue comments and timeline events to build full context before analysis
- **Configurable Issue Filters** — Display open or all issues from the dashboard and CLI
- **iTerm2 Session Management** — Visually color-codes agent sessions in iTerm2 panes per project

### Developer Experience

- **Dual Auth Modes** — Works with a Claude Code CLI subscription (`claude -p`) or a direct `ANTHROPIC_API_KEY`
- **Cloudflare Tunnel** — Zero-config webhook ingress without port forwarding or static IPs
- **Interactive Onboarding** — Rich terminal wizard to configure your first project
- **LaunchAgent Support** — macOS plist for auto-start on login
- **Poetry-managed** — Clean dependency management with locked versions

---

## Quick Start

### Prerequisites

| Requirement | Version | Install |
|---|---|---|
| macOS | 13+ | — |
| Python | 3.13+ | `brew install python@3.13` |
| Poetry | latest | [install.python-poetry.org](https://install.python-poetry.org) |
| Claude Code CLI | latest | [claude.ai/code](https://claude.ai/code) |
| GitHub CLI | latest | `brew install gh` |
| cloudflared | latest | `brew install cloudflared` |
| iTerm2 | latest | [iterm2.com](https://iterm2.com) (optional) |

> **Note:** Claude Code CLI is recommended. Without it, set `ANTHROPIC_API_KEY` for direct API access.

### Installation

```bash
# Clone the repository
git clone https://github.com/mrrobotke/claudedev.git
cd claudedev

# Run the installer (checks prerequisites, installs deps, creates config)
bash scripts/install.sh
```

The installer will:
1. Verify all prerequisites are installed
2. Create `~/.claudedev/` directory structure
3. Install Python dependencies with Poetry
4. Copy the example config to `~/.claudedev/config.toml`
5. Install the macOS LaunchAgent for auto-start
6. Initialize the PostgreSQL database

### Manual Installation

```bash
git clone https://github.com/mrrobotke/claudedev.git
cd claudedev

# Install dependencies
poetry install

# Create config directory and copy example config
mkdir -p ~/.claudedev
cp config/settings.example.toml ~/.claudedev/config.toml

# Authenticate GitHub CLI
gh auth login

# Start the daemon
poetry run claudedev daemon start
```

### Configuration

Edit `~/.claudedev/config.toml` with your settings:

```toml
[auth]
mode = "auto"  # "cli" for Claude Code, "api_key" for direct API

[server]
port = 8787
host = "127.0.0.1"

[tunnel]
enabled = true
```

### Running

```bash
# Add your first GitHub project
claudedev project add

# Start the daemon (webhook server + scheduler)
claudedev daemon start

# Open the web dashboard
claudedev dashboard
```

GitHub will send webhooks to your Cloudflare Tunnel URL. ClaudeDev handles the rest.

---

## Configuration Reference

All configuration lives in `~/.claudedev/config.toml`. The full reference:

### `[auth]`

| Key | Default | Description |
|---|---|---|
| `mode` | `"auto"` | Auth mode: `"auto"`, `"cli"` (Claude Code), or `"api_key"` |
| `anthropic_api_key` | — | API key (prefer `ANTHROPIC_API_KEY` env var or keychain) |
| `claude_code_path` | auto | Path to `claude` binary if not in `$PATH` |

### `[server]`

| Key | Default | Description |
|---|---|---|
| `port` | `8787` | Webhook server and dashboard port |
| `host` | `"127.0.0.1"` | Bind address |

### `[tunnel]`

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable Cloudflare Tunnel for webhook ingress |
| `hostname` | — | Custom hostname (requires Cloudflare DNS setup) |

### `[budget]`

| Key | Default | Description |
|---|---|---|
| `max_per_issue` | `2.00` | Max API spend per issue (USD) |
| `max_per_project_daily` | `20.00` | Max daily spend per project (USD) |
| `max_total_daily` | `50.00` | Max total daily spend across all projects (USD) |

### `[logging]`

| Key | Default | Description |
|---|---|---|
| `level` | `"INFO"` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `dir` | `"~/.claudedev/logs"` | Log file directory |

### `[iterm2]`

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable iTerm2 visual session management |
| `color_coding` | `true` | Color-code iTerm2 panes by project |

### `[notifications]`

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable macOS notifications |
| `on_enhancement` | `true` | Notify when issue enhancement completes |
| `on_implementation` | `true` | Notify when implementation completes |
| `on_pr_ready` | `true` | Notify when PR is ready for merge |
| `on_error` | `true` | Notify on errors |

### Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Direct API key (used when `auth.mode = "api_key"`) |
| `GITHUB_WEBHOOK_SECRET` | HMAC secret for verifying GitHub webhook payloads |
| `CLAUDEDEV_CONFIG` | Override config file path (default: `~/.claudedev/config.toml`) |

---

## Architecture

```
src/claudedev/
├── __init__.py              # Version and app name
├── auth.py                  # Auth mode detection (CLI vs API key)
├── cli.py                   # Typer CLI application
├── config.py                # Pydantic settings + TOML config loader
│
├── core/
│   ├── credentials.py       # Test credential discovery (.env parsing)
│   ├── discovery.py         # Project auto-discovery
│   ├── orchestrator.py      # Webhook event dispatcher + retry queue
│   ├── scheduler.py         # APScheduler (polling, cleanup, health checks)
│   └── state.py             # SQLAlchemy models: Repo, TrackedIssue, AgentSession
│
├── engines/
│   ├── issue_engine.py      # Issue enhancement pipeline
│   ├── team_engine.py       # Implementation team spawning (Tier 1–4)
│   ├── pr_engine.py         # PR creation and lifecycle management
│   └── review_engine.py     # Parallel multi-reviewer orchestration
│
├── github/
│   ├── gh_client.py         # Async GitHub CLI wrapper
│   ├── models.py            # Pydantic models for GitHub API + webhooks
│   └── webhook_server.py    # FastAPI webhook server + dashboard REST API
│
├── integrations/
│   ├── claude_sdk.py        # Claude Agent SDK client (CLI + API modes)
│   ├── iterm2_manager.py    # iTerm2 pane and tab management
│   └── tunnel_manager.py    # Cloudflare Tunnel lifecycle
│
├── ui/
│   ├── dashboard.py         # Web dashboard (FastAPI router + Tailwind CSS)
│   ├── menubar.py           # macOS menubar app (rumps)
│   └── onboarding.py        # Interactive onboarding wizard (Rich)
│
└── utils/
    ├── logging.py           # structlog configuration
    └── security.py          # HMAC verification, webhook secrets, keychain
```

### Data Flow

```
GitHub Webhook
    → HMAC verification (security.py)
    → FastAPI endpoint (webhook_server.py)
    → Event dispatcher (orchestrator.py)
    → Issue engine or PR engine
    → Claude Agent SDK (claude_sdk.py)
    → gh CLI (gh_client.py)
    → State updates (state.py → PostgreSQL)
    → Dashboard refresh (webhook_server.py)
```

**State store**: PostgreSQL via asyncpg + SQLAlchemy async. Three primary models:
- `Repo` — Tracked repository with config and webhook URL
- `TrackedIssue` — Issue state through the enhancement/implementation pipeline
- `AgentSession` — Active agent team sessions with cost tracking

---

## CLI Reference

All commands are available via `claudedev` (or `poetry run claudedev` in development).

### Daemon

| Command | Description |
|---|---|
| `claudedev daemon start` | Start the webhook server, scheduler, tunnel, and menubar |
| `claudedev daemon stop` | Stop the running daemon |
| `claudedev daemon status` | Show daemon status and active sessions |

### Projects

| Command | Description |
|---|---|
| `claudedev project add` | Add a GitHub repository to monitor (interactive) |
| `claudedev project list` | List all tracked projects |
| `claudedev project show <repo_id>` | Show detailed project info and stats |
| `claudedev project remove <repo_id>` | Remove a project from monitoring |

### Issues

| Command | Description |
|---|---|
| `claudedev issue list [--filter open\|all]` | List tracked issues |
| `claudedev issue enhance <repo> <number>` | Manually trigger issue enhancement |
| `claudedev issue implement <repo> <number>` | Manually trigger implementation |
| `claudedev issue sync <repo_id>` | Sync issues from GitHub |

### Pull Requests

| Command | Description |
|---|---|
| `claudedev pr list` | List tracked pull requests |
| `claudedev pr review <repo> <number>` | Trigger PR review pipeline |

### Credentials

| Command | Description |
|---|---|
| `claudedev cred discover <repo_id>` | Auto-discover test credentials from .env files |
| `claudedev cred set <repo_id> <key> <value>` | Manually set a test credential |

### Configuration

| Command | Description |
|---|---|
| `claudedev config show` | Display current configuration |
| `claudedev config set <key> <value>` | Update a config value |
| `claudedev dashboard` | Open the web dashboard in your browser |

---

## Web Dashboard

The web dashboard is served at `http://localhost:8787` (or your configured port) when the daemon is running.

**Dashboard features:**

- **Repository Overview** — Status, webhook URL, active session count per repo
- **Issue Queue** — Tracked issues with pipeline stage, tier classification, and enhancement status. Toggle between open and all issues.
- **Active Sessions** — Live view of running agent teams with session type, start time, and cost
- **PR Status** — Open PRs with review state and quality gate results
- **Cost Summary** — Per-project and global spend against configured budgets
- **System Health** — Daemon uptime, scheduler status, tunnel connectivity

Open the dashboard via:

```bash
claudedev dashboard
```

Or navigate directly to `http://localhost:8787` in any browser.

---

## Contributing

Contributions are welcome. Please read this section before opening a PR.

### Getting Started

1. **Fork** the repository and clone your fork
2. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
3. **Install dependencies**:
   ```bash
   poetry install
   ```
4. **Make your changes** following the coding standards below
5. **Run quality gates** — all must pass before submitting:
   ```bash
   ruff check .
   mypy . --strict
   pytest
   ```
6. **Commit** with a clear, descriptive message
7. **Push** your branch and open a pull request against `main`

### Coding Standards

**Python**
- Python 3.13+ with type hints on **all** function parameters and return types
- Pydantic v2 for all data models with proper field validation
- `async def` for all I/O operations (database, HTTP, subprocess)
- ruff for linting with `line-length = 100`
- mypy in strict mode — zero type errors
- 90%+ test coverage target on new code
- Conventional commits preferred: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`

**Testing**
- pytest + pytest-asyncio for all tests
- Unit tests for business logic, integration tests for API endpoints
- Use `pytest.mark.asyncio` (or `asyncio_mode = "auto"` in config) for async tests
- No shared mutable state between tests
- Mock external services (GitHub API, Claude API) in unit tests

**Project Conventions**
- Repository pattern for database access (see `core/state.py`)
- Structured logging via `structlog` — no bare `print()` or `logging.basicConfig()`
- Errors are raised, not silently swallowed
- All secrets via environment variables or macOS Keychain — never hardcoded

### Branch Naming

| Prefix | Use for |
|---|---|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `refactor/` | Code refactoring without behavior change |
| `docs/` | Documentation only |
| `test/` | Test additions or fixes |
| `chore/` | Dependency updates, tooling, CI |

### Pull Request Requirements

- **Title**: Short and descriptive (under 72 characters)
- **Description**: What changed, why, and how to test it
- **Tests**: New or updated tests for all changed logic
- **Quality gates**: All ruff, mypy, and pytest checks pass
- **No secrets**: Confirm no API keys, tokens, or credentials in the diff
- **One concern per PR**: Avoid mixing features and refactors

### Reporting Issues

Use [GitHub Issues](https://github.com/mrrobotke/claudedev/issues) to report bugs or request features. For bugs, include:
- macOS version
- Python version (`python3 --version`)
- ClaudeDev version (`claudedev --version`)
- Relevant log output from `~/.claudedev/logs/`
- Steps to reproduce

### Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be respectful and constructive.

---

## Roadmap

### v0.1.0 — Current

- [x] GitHub webhook integration (issues, PRs, comments)
- [x] Automatic issue enhancement with root cause analysis
- [x] Tier 1–4 team classification and spawning
- [x] 8-reviewer parallel code review pipeline
- [x] PR lifecycle management with quality gates
- [x] Web dashboard with real-time monitoring
- [x] macOS menubar app
- [x] Cloudflare Tunnel webhook ingress
- [x] Test credential auto-discovery
- [x] Cost tracking and budgeting
- [x] iTerm2 session management
- [x] Dual auth: Claude Code CLI + direct API key

### v0.2.0 — Planned

- [ ] AI planning layer with pre-implementation codebase analysis
- [ ] Multi-repository context sharing across projects
- [ ] Webhook retry queue with exponential backoff persistence
- [ ] GitHub Actions integration for CI-triggered workflows
- [ ] Dashboard authentication and multi-user support

### v0.3.0 — Planned

- [ ] Multi-model support with cost-based routing
- [ ] Token and cost optimization with smart context trimming
- [ ] Plugin system for custom review agents
- [ ] Slack and Linear integrations
- [ ] Configurable enhancement templates per repository

### v1.0.0 — Target

- [ ] Production-ready with 95%+ test coverage
- [ ] Full documentation and API reference
- [ ] Docker support for non-macOS environments
- [ ] Performance benchmarks and SLA targets
- [ ] Stable public API for extensions

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgments

- **[Claude Code](https://claude.ai/code)** by Anthropic — the CLI that makes autonomous coding possible
- **[Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk)** — the multi-agent orchestration layer that powers ClaudeDev's implementation teams
- **[FastAPI](https://fastapi.tiangolo.com)** — the async web framework powering the webhook server and dashboard
- **[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)** — zero-config secure webhook ingress
