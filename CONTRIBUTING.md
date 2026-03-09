# Contributing to ClaudeDev

Thank you for your interest in contributing to ClaudeDev! This document provides guidelines and standards for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)
- [Architecture Decisions](#architecture-decisions)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you are expected to uphold this code. Report unacceptable behavior to the maintainers.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/claudedev.git
   cd claudedev
   ```
3. **Add upstream** remote:
   ```bash
   git remote add upstream https://github.com/mrrobotke/claudedev.git
   ```
4. **Create a branch** for your changes:
   ```bash
   git checkout -b feat/my-feature
   ```

## Development Setup

### Prerequisites

- **macOS** (required for menubar and iTerm2 features)
- **Python 3.13+** (required)
- **Poetry** for dependency management
- **Claude Code** CLI (recommended)
- **GitHub CLI** (`gh`) for GitHub operations
- **cloudflared** for webhook tunneling

### Installation

```bash
# Install dependencies
poetry install

# Or use the install script
./scripts/install.sh

# Verify setup
poetry run pytest
poetry run ruff check .
poetry run mypy . --strict
```

### Configuration

```bash
# Copy example config
cp config/settings.example.toml ~/.claudedev/config.toml

# Edit to your preferences
$EDITOR ~/.claudedev/config.toml
```

## Making Changes

### Branch Naming Convention

Use descriptive branch names with the appropriate prefix:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feat/` | New feature | `feat/multi-model-support` |
| `fix/` | Bug fix | `fix/webhook-retry-race` |
| `refactor/` | Code refactoring | `refactor/orchestrator-state` |
| `docs/` | Documentation | `docs/api-reference` |
| `test/` | Test additions | `test/scheduler-edge-cases` |
| `perf/` | Performance improvement | `perf/query-optimization` |
| `chore/` | Maintenance | `chore/update-dependencies` |

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `chore`, `ci`

**Examples**:
```
feat(engine): add issue comment context to enhancement pipeline
fix(webhook): prevent silent failures on dispatch errors
refactor(state): extract session management into dedicated module
docs(readme): add architecture diagram
test(credentials): add path traversal prevention tests
```

## Coding Standards

### Python Style

- **Python 3.13+** — use modern syntax (type unions with `|`, match statements, etc.)
- **Type hints** on ALL functions — no exceptions
- **Pydantic v2** for all data models with proper validators
- **async/await** for all I/O operations
- **ruff** for linting — config in `pyproject.toml` (line-length=100)
- **mypy strict** mode — must pass with zero errors
- **structlog** for logging — structured JSON with bound context

### Code Patterns

```python
# Good: Typed, async, Pydantic v2
async def list_issue_comments(
    self, repo: str, number: int, *, limit: int = 20
) -> list[GitHubComment]:
    """List comments on an issue, newest first."""
    output = await self._run_gh([...])
    data = json.loads(output)
    return [GitHubComment.model_validate(item) for item in data]

# Bad: Untyped, sync, dict
def get_comments(self, repo, number):
    result = subprocess.run([...])
    return json.loads(result.stdout)
```

### Architecture Rules

1. **Repository pattern** for database access — models in `core/state.py`
2. **Engine pattern** for business logic — each engine owns one domain
3. **GH Client** wraps all GitHub CLI operations — never call `gh` directly
4. **Config** through Pydantic Settings — never hardcode values
5. **Structured logging** — always use `structlog.get_logger(__name__)`
6. **Error handling** — never swallow exceptions; log and propagate

### File Organization

- New models → `core/state.py` or `github/models.py`
- New GitHub API calls → `github/gh_client.py`
- New business logic → `engines/` (create new engine if new domain)
- New API endpoints → `github/webhook_server.py`
- New CLI commands → `cli.py`
- New integrations → `integrations/`
- New UI components → `ui/`

## Testing

### Running Tests

```bash
# Full test suite
poetry run pytest

# With coverage
poetry run pytest --cov=claudedev --cov-report=html

# Specific test file
poetry run pytest tests/test_issue_engine.py

# Verbose with short traceback
poetry run pytest -x --tb=short -v
```

### Writing Tests

- Place tests in `tests/` mirroring the source structure
- Use `pytest-asyncio` for async tests (auto mode enabled)
- Use `conftest.py` fixtures for shared setup (DB sessions, mocks)
- Mock external services (GitHub API, Claude CLI) — never make real API calls
- Test edge cases: empty inputs, error responses, boundary values
- **Target**: 90%+ coverage on new code

### Quality Gates

All of these must pass before a PR can be merged:

```bash
# Lint — zero warnings
poetry run ruff check .

# Type check — zero errors
poetry run mypy . --strict

# Tests — all passing
poetry run pytest
```

## Pull Request Process

### Before Submitting

1. **Sync with upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```
2. **Run all quality gates** (lint, types, tests)
3. **Self-review your diff** — read it as a reviewer would

### PR Requirements

- **Title**: Clear, concise description (under 70 characters)
- **Description**: Include:
  - What changed and why
  - How to test it
  - Screenshots for UI changes
- **Scope**: One logical change per PR — don't bundle unrelated changes
- **Tests**: New code must have tests; modified code must maintain coverage
- **Quality gates**: All passing (enforced by CI)

### Review Process

1. At least **one maintainer approval** required
2. All CI checks must pass
3. Reviewer feedback must be addressed (resolved or discussed)
4. Squash merge to main (maintainer handles this)

### PR Size Guidelines

| Size | Files Changed | Expectation |
|------|--------------|-------------|
| Small | 1-3 | Quick review, same day |
| Medium | 4-10 | 1-2 day review |
| Large | 10+ | Consider splitting; discuss first |

## Issue Guidelines

### Bug Reports

Include:
- ClaudeDev version (`claudedev --version`)
- Python version
- macOS version
- Steps to reproduce
- Expected vs actual behavior
- Logs (from `~/.claudedev/logs/`)

### Feature Requests

Include:
- Problem description (what are you trying to do?)
- Proposed solution
- Alternatives considered
- Impact on existing features

### Enhancement Ideas

Open a discussion first for large changes. We prefer to align on approach before implementation to avoid wasted effort.

## Architecture Decisions

For significant architectural changes, we use lightweight Architecture Decision Records (ADRs):

1. Open an issue describing the proposed change
2. Label it `architecture`
3. Include: context, decision, consequences, alternatives
4. Get maintainer feedback before implementing

This ensures major changes are discussed and documented before code is written.

---

Questions? Open a [Discussion](https://github.com/mrrobotke/claudedev/discussions) or reach out to the maintainers.

Thank you for contributing to ClaudeDev!
