# ClaudeDev Research Document

**Date:** 2026-03-09
**Purpose:** Feature inventory of Claude Code, competitor analysis of OpenClaw, and gap analysis for ClaudeDev.

---

## Part 1: Claude Code Feature Inventory

### 1.1 Hooks System

**Description:** Shell scripts that fire at specific lifecycle events during a Claude Code session. Hooks run as external processes with zero context cost unless they return output.

**Hook Types:**
- **PreToolUse** - Fires before a tool is executed. Can block operations (exit code 2). Used for protecting sensitive files, logging commands.
- **PostToolUse** - Fires after a tool completes. Used for auto-formatting, auto-CI (lint + type check + tests after every edit).
- **UserPromptSubmit** - Fires when the user submits a prompt. Used for detecting complex tasks (Ralph Loop activation), injecting dual-agent workflow instructions.
- **Stop** - Fires when Claude attempts to stop. Can block completion if quality gates haven't passed.
- **SessionStart** - Fires at session initialization. Used for auto-activating tools like Serena.

**Current User Setup (from `~/.claude/hooks/`):**
- `auto-ci.sh` - Runs ruff + mypy + pytest (Python) or eslint + tsc + pnpm test (TS) after every edit
- `auto-format.sh` - Auto-formats with ruff (Python) or prettier (TS/JS/JSON) after edits
- `ralph-detector.sh` - Detects complex prompts (>100 words) and activates autonomous Ralph Loop
- `quality-gate-stop.sh` - Blocks session stop if lint/type/test failures exist
- `protect-sensitive.sh` - Blocks edits to production env files and .git directory
- `log-commands.sh` - Logs all bash commands to audit trail
- `serena-init.sh` - Auto-activates Serena MCP server at session start
- `dual-agent-detect.sh` - Detects code change tasks and injects dual-agent review instructions
- `detect-project-type.sh` - Utility to detect Python/TS/JS/React Native project types

**ClaudeDev Integration Status:** ❌ Not used
**Priority:** HIGH - Hooks enable automated CI, quality gates, and safety guardrails without consuming context tokens.

---

### 1.2 Custom Agents (Subagents)

**Description:** Markdown files in `~/.claude/agents/` that define specialized agent personas with restricted tool access, custom models, and focused instructions. Subagents load fresh, isolated context - they don't inherit conversation history.

**Current User Setup (from `~/.claude/agents/`):**
- `code-writer.md` - Implementation agent with Write/Edit/Bash access, Sonnet model
- `code-reviewer.md` - Review agent with Read/Grep/Glob only (no write access), Sonnet model
- `test-writer.md` - Test generation agent with full tool access, Sonnet model

**Agent Definition Format:**
```yaml
---
name: agent-name
description: What the agent does
model: sonnet  # or opus, haiku
allowed-tools: Read, Write, Edit, Bash
disallowed-tools: Write, Edit  # for read-only agents
---
# Instructions in markdown
```

**ClaudeDev Integration Status:** ⚠️ Partial - ClaudeDev uses team agents but not the `.claude/agents/` format
**Priority:** HIGH - Custom agents with tool restrictions enable safe delegation patterns.

---

### 1.3 Plugins Ecosystem

**Description:** Lightweight packages that extend Claude Code with custom slash commands, subagents, MCP servers, hooks, and LSP servers. Installed via `/plugin` command. Over 9,000 plugins available as of February 2026. Two marketplaces: `claude-plugins-official` and `claude-code-plugins`.

**Current User Installed Plugins (27 total):**

| Plugin | Source | Purpose |
|--------|--------|---------|
| agent-sdk-dev | Both | Agent SDK development tools |
| code-review | Both | Code review workflows |
| feature-dev | Both | Feature development workflows |
| frontend-design | Both | Frontend design tools |
| hookify | Both | Hook generation/management |
| ralph-wiggum | claude-code-plugins | Autonomous loop personality |
| ralph-loop | claude-plugins-official | Ralph autonomous loop engine |
| github | claude-plugins-official | GitHub integration |
| supabase | claude-plugins-official | Supabase database integration |
| commit-commands | Both | Git commit workflows |
| pr-review-toolkit | Both | PR review sub-agents |
| playwright | claude-plugins-official | Browser automation |
| sentry | claude-plugins-official | Error tracking |
| greptile | claude-plugins-official | AI code search |
| vercel | claude-plugins-official | Deployment platform |
| stripe | claude-plugins-official | Payment integration |
| pyright-lsp | claude-plugins-official | Python LSP |
| typescript-lsp | claude-plugins-official | TypeScript LSP |
| serena | claude-plugins-official | Semantic code analysis MCP |
| swift-lsp | claude-plugins-official | Swift LSP |
| security-guidance | Both | Security best practices |
| claude-code-setup | claude-plugins-official | Setup wizard |
| superpowers | claude-plugins-official | Enhanced capabilities |

**ClaudeDev Integration Status:** ❌ Not used
**Priority:** HIGH - Plugin ecosystem provides pre-built capabilities (PR review, security audit, etc.)

---

### 1.4 MCP (Model Context Protocol) Servers

**Description:** MCP connects Claude Code to external services through a standardized protocol. Servers provide tools, resources, and prompts. Claude Code supports MCP Tool Search for lazy loading - reduces context usage by up to 95%.

**Key MCP Features:**
- **Tool Search / Lazy Loading** - Loads tool definitions on-demand instead of upfront. When >10K tokens of tool descriptions exist, a lightweight search index is used instead. Context drops from ~77K to ~8.7K tokens.
- **Multiple Server Support** - Run many MCP servers simultaneously
- **Server Types** - stdio (local process), SSE (remote HTTP), streamable HTTP

**Currently Active MCP:** Serena (semantic code analysis), Playwright (browser automation), Claude in Chrome (browser control)

**ClaudeDev Integration Status:** ⚠️ Partial - ClaudeDev uses Serena MCP but doesn't leverage Tool Search or the broader MCP ecosystem
**Priority:** HIGH - MCP is the extension mechanism for integrating with external tools and services.

---

### 1.5 Skills System

**Description:** SKILL.md files that extend Claude's knowledge and capabilities. Skills are organized in directories under `~/.claude/skills/`. The skill name becomes a `/slash-command`. Slash commands were merged into the skills system in v2.1.3.

**Skill Format:**
```yaml
---
name: skill-name
description: What the skill does
allowed-tools: Tool1, Tool2  # optional restrictions
---
# Instructions in markdown
```

**Current User Skills (from `~/.claude/skills/`):**
- `db-migration` - Alembic migration workflow
- `fastapi` - FastAPI development patterns and conventions
- `react-native` - React Native + Expo development patterns
- `tdd` - Test-driven development workflow
- `ui-test` - Playwright UI testing with credential handling

**Built-in Skills:**
- `/batch` - Orchestrates large-scale parallel changes across codebase (5-30 independent units in separate git worktrees)

**ClaudeDev Integration Status:** ⚠️ Partial - ClaudeDev has project-specific patterns in CLAUDE.md but doesn't use the skills format
**Priority:** MEDIUM - Skills provide reusable, modular knowledge that can be shared.

---

### 1.6 Agent Teams (Swarm Mode)

**Description:** Experimental feature that orchestrates teams of Claude Code sessions working together. One session acts as team lead, coordinating work and assigning tasks. Teammates work independently in their own context windows and communicate directly.

**Key Components:**
- **TeammateTool** - Core orchestration layer with 13 operations for managing agents
- **TaskCreate / TaskUpdate / TaskList** - Task management system with dependencies
- **SendMessage** - Inter-agent messaging (direct and broadcast)
- **Shutdown protocol** - Graceful team shutdown with confirmation

**Activation:** Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json (currently enabled in user's setup).

**Current User Protocol:** Extensive 4-tier orchestration protocol defined in CLAUDE.md:
- Tier 1: 4 agents (1 implementer + 3 reviewers)
- Tier 2: 6-8 agents (1-2 implementers + architect + 4-5 reviewers)
- Tier 3: 10-12 agents (2-3 implementers + architect + 6-8 reviewers)
- Tier 4: Cross-domain with backend/frontend leads managing sub-teams (~19 agents)

**Limitations:** Adds coordination overhead, uses significantly more tokens, works best for independent parallel tasks.

**ClaudeDev Integration Status:** ❌ Not used (ClaudeDev doesn't orchestrate multi-agent teams)
**Priority:** HIGH - Multi-agent teams enable parallel work, specialized reviewers, and quality gates.

---

### 1.7 Worktree Isolation

**Description:** The `--worktree` (`-w`) flag starts Claude in an isolated git worktree, allowing changes in a separate branch without affecting the working directory. Especially powerful combined with `background: true` for agents.

**Use Cases:**
- Parallel feature development
- `/batch` command uses worktrees for each parallel unit
- Scheduled tasks can use worktrees to prevent interference
- Safe experimentation without affecting main branch

**ClaudeDev Integration Status:** ❌ Not used
**Priority:** MEDIUM - Useful for parallel development and safe experimentation.

---

### 1.8 Plan Mode

**Description:** A mode (activated with Shift+Tab twice) that forces architectural thinking before implementation. Claude produces a plan that can be reviewed and approved before any code changes.

**Benefits:**
- Dramatically improves output quality
- Prevents premature implementation
- Enables plan-then-execute workflow
- Agents can be spawned in plan mode (`plan_mode_required`)

**ClaudeDev Integration Status:** ⚠️ Partial - ClaudeDev's architect agents use plan mode, but it's not a general workflow
**Priority:** MEDIUM - Good for complex tasks requiring upfront design.

---

### 1.9 IDE Integrations

**Description:** Claude Code integrates with VS Code and JetBrains IDEs.

**VS Code Extension:**
- Native graphical chat panel
- Checkpoint-based undo (revert to any point in conversation)
- @-mention file references with line ranges
- Review and edit plans before accepting
- Auto-accept edits mode
- Parallel conversations in separate tabs
- Diff viewer for proposed changes

**JetBrains Plugin:**
- Runs Claude Code CLI inside IDE terminal
- Opens proposed changes in IDE diff viewer
- Supports all JetBrains IDEs (IntelliJ, PyCharm, WebStorm, etc.)
- Remote development support

**ClaudeDev Integration Status:** ❌ Not used (ClaudeDev is terminal-based)
**Priority:** LOW for ClaudeDev (different product category), but worth noting for UX inspiration.

---

### 1.10 Scheduled Tasks

**Description:** Desktop scheduled tasks automate recurring work. Tasks run locally with fresh sessions at chosen times, with full access to files, MCP servers, skills, connectors, and plugins.

**Features:**
- Cron-based scheduling (local timezone)
- Worktree toggle for isolation
- SKILL.md format for task definitions
- Manual or automated triggers

**ClaudeDev Integration Status:** ❌ Not used
**Priority:** MEDIUM - Enables automated maintenance, monitoring, and routine tasks.

---

### 1.11 Settings and Configuration

**Description:** Multi-level configuration system.

**Configuration Files:**
- `~/.claude/settings.json` - Global user settings (permissions, hooks, plugins, env vars)
- `~/.claude/settings.local.json` - Local overrides (not committed)
- `.claude/CLAUDE.md` - Project-level instructions (per-repo)
- `~/.claude/CLAUDE.md` - Global user instructions

**Key Settings:**
- `permissions.allow` - Whitelisted tool patterns
- `permissions.defaultMode` - Permission mode (bypassPermissions, normal, etc.)
- `hooks` - Hook configurations with matchers
- `enabledPlugins` - Active plugin list
- `env` - Environment variables (e.g., experimental features)
- `effortLevel` - Model effort level (high/medium/low)
- `skipDangerousModePermissionPrompt` - Skip safety prompts

**ClaudeDev Integration Status:** ⚠️ Partial - ClaudeDev reads CLAUDE.md but doesn't use the full settings system
**Priority:** MEDIUM - Configuration system enables customization and safety controls.

---

### 1.12 Preview Tool (Claude Preview)

**Description:** Built-in dev server management and browser preview tool.

**Features:**
- `preview_start/stop/list` - Dev server lifecycle management via `.claude/launch.json`
- `preview_screenshot` - Take screenshots of running app
- `preview_snapshot` - Accessibility tree for text/structure verification
- `preview_inspect` - DOM inspection with computed styles
- `preview_click/fill/eval` - Interact with the running app
- `preview_network` - Monitor network requests
- `preview_console_logs` - Read browser console
- `preview_resize` - Test responsive layouts (mobile/tablet/desktop presets)

**ClaudeDev Integration Status:** ❌ Not used
**Priority:** MEDIUM - Enables visual testing and UI development without external tools.

---

## Part 2: OpenClaw Analysis

### 2.1 What is OpenClaw?

OpenClaw (formerly Moltbot, then Clawdbot) is an open-source, self-hosted personal AI agent created by PSPDFKit founder Peter Steinberger. It runs as a long-lived Node.js process (the "Gateway") on your machine and connects LLMs to your local system and messaging apps.

**Core Identity:** A personal AI assistant, not primarily a coding tool. It automates workflows across messaging, email, calendar, browser, shell, and files.

### 2.2 Architecture

**Gateway Architecture:**
- Single long-lived Node.js process called the "Gateway"
- Binds to port 18789 by default
- Serves Control UI and WebChat interface
- Manages: channel connections, session state, agent loop, model calls, tool execution, memory persistence
- No separate services to manage

**Key Architectural Components:**
- **Skills** - SKILL.md files with YAML frontmatter (similar to Claude Code skills)
- **Memory** - Persistent markdown files stored on local disk
- **Channels** - 20+ messaging platform integrations (WhatsApp, Telegram, Slack, Discord, etc.)
- **Heartbeat** - Configurable interval (default 30min) where agent reads HEARTBEAT.md checklist
- **Lobster** - Workflow engine for deterministic multi-agent pipelines

### 2.3 Features

| Feature | Description |
|---------|-------------|
| Multi-channel messaging | 20+ platforms (WhatsApp, Slack, Telegram, Discord, etc.) |
| Skills ecosystem | 565+ community skills via ClawHub registry |
| Persistent memory | Markdown files on local disk |
| Browser automation | CDP-based browser control |
| Shell command execution | Direct system access |
| Email/Calendar | Automation of productivity workflows |
| Proactive automation | Heartbeat system, cron jobs, scheduled tasks |
| Multi-model support | Anthropic, OpenAI, local models, and others |
| File operations | Read, write, search local filesystem |
| GitHub integration | PR creation, issue management, repo automation |
| Lobster workflow engine | Deterministic multi-agent pipelines |
| ClawHub skill registry | Community skill sharing marketplace |

### 2.4 Community and Adoption Metrics

| Metric | Value |
|--------|-------|
| GitHub Stars | ~250,000 (surpassed React in ~60 days) |
| GitHub Forks | 45,141 |
| Contributors | 1,000+ shipping code weekly |
| Community Skills | 565+ |
| Codebase Size | 430,000+ lines of code |
| Dependencies | 70+ |
| Time to 200K stars | ~60 days |
| Repository Count | 22 repos in the org |

### 2.5 Pricing/Licensing

- **Software License:** MIT (100% free, open-source)
- **Infrastructure Cost:** $6-13/month (basic personal), $25-50/month (small business), $50-100/month (teams), $100+/month (heavy automation)
- **AI API Cost:** Depends on model choice and usage volume
- **Hidden Cost:** 2-4 hours/month operational maintenance

### 2.6 Feature Comparison: OpenClaw vs ClaudeDev

| Feature | OpenClaw | ClaudeDev |
|---------|----------|-----------|
| **Primary Focus** | Personal AI assistant (multi-purpose) | Autonomous coding tool |
| **Architecture** | Single Node.js Gateway process | Python CLI + Claude Code integration |
| **AI Models** | Multi-model (Anthropic, OpenAI, local) | Claude only (via Claude Code) |
| **Code Generation** | Via skills/community plugins | Core competency |
| **Code Review** | Via community skills | Built-in multi-reviewer pipeline |
| **Multi-Agent** | Lobster workflow engine | Claude Code Agent Teams |
| **Messaging** | 20+ platforms native | None |
| **Memory** | Persistent markdown files | Via Serena memory |
| **Scheduling** | Heartbeat + cron | Not implemented |
| **Browser Automation** | CDP-based | Via Playwright plugin |
| **IDE Integration** | None (messaging-first) | Terminal + potential IDE |
| **Quality Gates** | Manual/skill-based | Automated hooks (lint, type, test) |
| **Skill Sharing** | ClawHub marketplace (565+ skills) | Not implemented |
| **Security Model** | Broad system access (criticized) | Sandboxed + permission system |
| **License** | MIT | Proprietary/TBD |
| **Community** | 250K stars, 1000+ contributors | Early stage |
| **Issue-to-PR Pipeline** | Community skill available | Core planned feature |
| **Multi-repo Support** | Via skills | Via Agent Teams Tier 4 |
| **Type Safety** | Not a focus | Core requirement (mypy, tsc) |
| **Test Generation** | Via skills | Built-in test-writer agent |

### 2.7 OpenClaw Strengths (What We Should Learn From)

1. **Massive community adoption** - 250K GitHub stars demonstrates product-market fit for autonomous AI agents
2. **Skill ecosystem** - 565+ community skills with ClawHub registry makes it extensible by anyone
3. **Multi-channel presence** - Being where users already are (WhatsApp, Slack, etc.) vs requiring terminal access
4. **Proactive automation** - Heartbeat system enables the agent to act without being prompted
5. **Multi-model support** - Not locked to a single AI provider
6. **Issue-to-PR pipeline** - Community has built automated TODO/FIXME scanning and PR generation
7. **Open-source virality** - MIT license enabled explosive growth
8. **Gateway architecture** - Always-on daemon means persistent context and state

### 2.8 OpenClaw Weaknesses (Our Competitive Advantages)

1. **Security concerns** - 430K lines of code with 70+ dependencies and unrestricted system access. Called "lethal trifecta" by Palo Alto Networks
2. **Not coding-focused** - It's a generalist assistant; coding is just one of many skills
3. **No built-in quality gates** - No automated lint/type/test enforcement
4. **No type safety enforcement** - No mypy/tsc integration in the core
5. **No structured code review** - No specialized reviewer roles (security, performance, etc.)
6. **No IDE integration** - Messaging-first means no VS Code/JetBrains presence
7. **High operational overhead** - 2-4 hours/month maintenance, complex setup
8. **Token-heavy** - No context optimization like MCP Tool Search
9. **No sandboxing** - Full system access by default vs Claude Code's permission model
10. **Dependency risk** - 70+ dependencies means larger attack surface and maintenance burden

---

## Part 3: Gap Analysis

### 3.1 What ClaudeDev Is Missing vs Claude Code Features

| Gap | Description | Priority | Effort |
|-----|-------------|----------|--------|
| **Hooks integration** | ClaudeDev doesn't leverage Claude Code's hook system for automated CI, quality gates, or safety guardrails | HIGH | MEDIUM |
| **Plugin ecosystem** | ClaudeDev doesn't use or contribute to the 9,000+ plugin ecosystem | HIGH | HIGH |
| **Agent Teams orchestration** | While CLAUDE.md defines the protocol, ClaudeDev itself doesn't implement team management | HIGH | HIGH |
| **MCP Tool Search** | ClaudeDev doesn't leverage lazy loading for context optimization | HIGH | LOW |
| **Skills system** | ClaudeDev's knowledge is in CLAUDE.md rather than modular, shareable skills | MEDIUM | MEDIUM |
| **Worktree isolation** | ClaudeDev doesn't use worktrees for parallel safe development | MEDIUM | LOW |
| **Scheduled tasks** | No automated recurring task support | MEDIUM | MEDIUM |
| **Preview tool** | No visual testing or UI preview capability | MEDIUM | LOW |
| **Custom agent format** | ClaudeDev doesn't use `.claude/agents/` format for agent definitions | MEDIUM | LOW |
| **IDE integration** | ClaudeDev is terminal-only, no VS Code/JetBrains presence | LOW | HIGH |

### 3.2 What ClaudeDev Is Missing vs OpenClaw

| Gap | Description | Priority | Effort |
|-----|-------------|----------|--------|
| **Issue-to-PR pipeline** | Automated scanning of issues/TODOs and PR generation | HIGH | HIGH |
| **Skill sharing marketplace** | No way to share or discover community-built capabilities | HIGH | HIGH |
| **Proactive automation** | No heartbeat/cron system for autonomous actions | MEDIUM | MEDIUM |
| **Multi-model support** | Locked to Claude; no fallback or routing to other models | MEDIUM | HIGH |
| **Community skills** | No equivalent to ClawHub's 565+ community contributions | MEDIUM | HIGH |
| **Messaging integration** | No way to receive tasks via Slack/Discord/etc | LOW | MEDIUM |
| **Always-on daemon** | ClaudeDev runs on-demand, not as a persistent service | LOW | HIGH |

### 3.3 Prioritized Improvement Roadmap

#### Phase 1: Quick Wins (LOW effort, HIGH impact)
1. **Leverage MCP Tool Search** - Enable lazy loading for MCP tools to save context
2. **Adopt worktree isolation** - Use `--worktree` for parallel agent work
3. **Formalize agent definitions** - Convert team roles to `.claude/agents/` format
4. **Use Preview tool** - Integrate Claude Preview for UI development tasks

#### Phase 2: Core Infrastructure (MEDIUM effort, HIGH impact)
5. **Hook-driven quality gates** - Build on existing hooks for automated CI/CD
6. **Skills modularization** - Break CLAUDE.md into modular skills
7. **Scheduled task support** - Add cron-based automation for routine tasks
8. **Proactive heartbeat** - Implement autonomous monitoring and action

#### Phase 3: Ecosystem (HIGH effort, HIGH impact)
9. **Plugin integration** - Leverage existing plugin ecosystem for ClaudeDev workflows
10. **Issue-to-PR pipeline** - Build automated issue scanning and implementation pipeline
11. **Skill sharing** - Create mechanism for sharing ClaudeDev skills/configurations
12. **Agent Teams native support** - Make team orchestration a first-class ClaudeDev feature

#### Phase 4: Differentiation (HIGH effort, MEDIUM impact)
13. **Multi-model routing** - Support fallback models for cost optimization
14. **IDE integration** - Build VS Code extension for ClaudeDev
15. **Messaging integration** - Accept tasks from Slack/Discord
16. **Community marketplace** - Build a ClaudeDev skill/config marketplace

---

## Summary

**ClaudeDev's Core Strength:** Deep integration with Claude Code's ecosystem (hooks, MCP, plugins, agent teams) for structured, quality-gated software development. The multi-reviewer architecture (security, performance, type safety, etc.) is unique.

**OpenClaw's Core Strength:** Massive community, multi-channel presence, and general-purpose automation. It's a personal assistant that happens to code, not a coding tool.

**Strategic Recommendation:** ClaudeDev should double down on being the best *coding-specific* autonomous agent by:
1. Fully leveraging Claude Code's native features (hooks, plugins, MCP, teams)
2. Building the issue-to-PR pipeline as a core differentiator
3. Creating a skill/config sharing mechanism for the coding community
4. Maintaining the quality-gate-enforced workflow as a key advantage over OpenClaw's security-criticized approach
