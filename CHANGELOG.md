# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-09

### Added

- **Core Pipeline**: End-to-end autonomous development workflow
  - GitHub webhook integration for issues, PRs, and comments
  - Automatic issue enhancement with codebase investigation and root cause analysis
  - Playwright-based validation of reported behaviors (with credential support)
  - Tier classification (1-4) based on issue complexity
  - Team-based implementation via Claude Agent SDK
  - Multi-reviewer code review pipeline

- **Issue Context Intelligence**
  - Fetch latest issue comments for up-to-date context
  - Issue timeline analysis (close/reopen events, PR references, cross-references)
  - Context injection into both enhancement and implementation prompts

- **Credential Management**
  - Auto-discovery of test credentials from `.env` / `.env.local` files
  - Manual credential management via CLI and dashboard
  - Secure credential masking in API responses and UI
  - Path validation to prevent directory traversal attacks

- **Web Dashboard**
  - Real-time project and issues monitoring
  - Session management with terminate/cancel actions
  - Credential viewer and editor modal
  - Configurable issues filter (open/all) with persistent settings
  - Built with Tailwind CSS, served inline via FastAPI

- **CLI**
  - Project management (`project add`, `project list`)
  - Daemon control (`daemon start`, `daemon stop`)
  - Issue operations (`issue enhance`, `issue sync`)
  - Credential operations (`cred discover`, `cred set`)
  - Dashboard launcher

- **Integrations**
  - Claude Code CLI integration for AI operations
  - Anthropic API key support as fallback
  - Cloudflare Tunnel for webhook ingress
  - iTerm2 pane management for session visualization
  - macOS menubar app via rumps

- **Reliability**
  - Webhook retry queue with exponential backoff
  - Bidirectional issue sync (forward + reverse polling)
  - Session termination correctly reverts linked issue status
  - Stale session cleanup with issue status recovery
  - Structured logging with structlog

- **Quality**
  - 181 tests passing
  - ruff linting with zero warnings
  - mypy strict mode with zero errors
  - Input validation on all API endpoints
  - Path traversal prevention for credential discovery

### Security

- Server-side credential masking (no client-side re-masking)
- Sensitive directory blocking for credential discovery
- Credential key format validation (uppercase alphanumeric + underscore)
- `SECRET_KEY` pattern exclusion to prevent false positives

[0.1.0]: https://github.com/mrrobotke/claudedev/releases/tag/v0.1.0
