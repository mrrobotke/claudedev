# ClaudeDev Masterplan: The Autonomous Coding Platform for Claude Code

**Version**: 1.0 | **Date**: 2026-03-09 | **Status**: Strategic Blueprint

---

## Executive Summary

ClaudeDev is an autonomous development orchestrator built specifically for Claude Code users. This masterplan charts the path from its current v0.1.0 state (a functional daemon with issue-to-PR pipeline) to becoming the definitive autonomous coding platform purpose-built around Anthropic's Claude ecosystem.

**Key strategic differentiator**: While OpenClaw is a general-purpose autonomous AI agent framework (messaging, browser, emails, calendars), ClaudeDev is laser-focused on software development automation. This specialization is our moat.

---

## Part 1: Competitive Landscape

### OpenClaw: What They Do Well

OpenClaw (247K+ GitHub stars) is an open-source autonomous AI agent that operates via messaging platforms. Its strengths:

| Capability | How OpenClaw Does It | ClaudeDev Gap |
|-----------|---------------------|---------------|
| Heartbeat daemon | 30-min autonomous polling, reads HEARTBEAT.md, decides actions | We poll but lack autonomous decision-making |
| Multi-model support | Claude, GPT-4, Gemini, DeepSeek via BYOK | We are Claude-only |
| File-based config | SOUL.md, AGENTS.md, TOOLS.md, MEMORY.md | We use TOML config (less flexible) |
| Memory system | Daily memory files + curated MEMORY.md | We have SQLite but no persistent AI memory |
| Skill marketplace | ClawHub with 100+ community skills | No marketplace |
| Multi-channel I/O | 20+ messaging platforms | GitHub webhooks only |
| MCP tool integration | 134+ MCP tools in production deployments | Not using MCP at all |

### OpenClaw: Where They Are Weak (Our Advantage)

| Area | OpenClaw Weakness | ClaudeDev Advantage |
|------|------------------|---------------------|
| Code specialization | General-purpose agent, coding is one capability | Purpose-built for software development |
| Code quality | No built-in review pipeline | 8-reviewer quality pipeline (security, performance, types, tests) |
| Team orchestration | Single-agent + multi-agent via AGENTS.md | Tiered teams with architect, implementers, reviewers |
| Issue understanding | Basic task execution | Deep codebase investigation + Playwright validation |
| PR lifecycle | Manual or basic script | Full PR creation, review, iteration, merge |
| Type safety | Node.js, loosely typed | Python 3.13, mypy strict, Pydantic v2 |
| Cost control | Per-session caps only | Per-issue, per-project, per-day budget hierarchy |
| Security posture | CVE history (CVE-2026-25253) | Path validation, credential masking, auth guards |

### Claude Code: Features We Must Leverage

| Feature | Claude Code Status | ClaudeDev Usage | Priority |
|---------|-------------------|-----------------|----------|
| Hooks (PreToolUse, PostToolUse, Stop) | Mature, 7 event types | Not integrated | CRITICAL |
| Agent Teams / Swarms | Research preview | Not using (we build our own teams) | HIGH |
| MCP Servers | 50+ available, lazy loading | Not using | HIGH |
| Skills (.claude/skills/) | Auto-activated by context | Not using | HIGH |
| Slash Commands | .claude/commands/ | Not using | MEDIUM |
| Custom Agents (.claude/agents/) | Markdown-defined | Have 3, not integrated with ClaudeDev | MEDIUM |
| Plugins | Community marketplace | Not using | MEDIUM |
| CLAUDE.md hierarchy | Enterprise, user, project, directory | User-level only | MEDIUM |
| Worktree isolation | Git worktree per agent | Not using | HIGH |
| Plan Mode | Built-in approval flow | Not using | LOW |

---

## Part 2: Architecture Vision

### Current Architecture (v0.1.0)

```
GitHub -> Webhook -> FastAPI -> Orchestrator -> Claude CLI -> Agent SDK
                       |
                   Dashboard
                   Menubar
                   CLI
```

Problem: ClaudeDev runs ALONGSIDE Claude Code but does not deeply integrate WITH it.

### Target Architecture (v1.0)

The target architecture has three layers:

**Layer 1 - ClaudeDev Brain (AI Layer)**:
- Issue Thinker: pre-analyzes before sending to Claude Code
- Code Planner: architects before implementation
- Decision Engine: decides when to enhance, implement, or skip
- All powered by Anthropic API (Sonnet for thinking, Opus for complex decisions)

**Layer 2 - Claude Code Integration Layer**:
- Hooks: event-driven automation
- MCP: tool exposure for bidirectional communication
- Skills: auto-activated expertise
- Agent Teams: native swarm orchestration
- Commands, Plugins, Worktrees, Plan Mode

**Layer 3 - Input/Output Layer**:
- GitHub Webhooks, Dashboard, CLI, Menubar
- Future: Slack, Discord, Email

### The Three Pillars

#### Pillar 1: AI Brain (NEW - The Differentiator)

ClaudeDev should have its own AI layer that thinks BEFORE delegating to Claude Code. This is not a replacement for Claude Code; it is a pre-processing intelligence that makes Claude Code more effective.

Currently, ClaudeDev dumps the issue body into a prompt and lets Claude Code figure everything out. OpenClaw's success shows that autonomous agents need decision-making capability.

The AI Brain should:
1. Analyze issues before enhancement - decide IF an issue needs enhancement, what priority it deserves, and what investigation strategy to use
2. Plan implementations before team spawning - generate an architecture plan, identify affected files, estimate complexity BEFORE creating a Claude Code session
3. Learn from outcomes - track which approaches worked, which reviews found real issues, which implementations succeeded, and use this to improve future decisions

**Model strategy**:
- Use Anthropic API directly (Claude Sonnet 4 for fast thinking, Claude Opus 4 for complex planning)
- Support user's Claude Code subscription (uses `claude -p` CLI for heavy sessions)
- Also support adding Anthropic API key directly for the Brain layer
- Brain operations are lightweight (analysis, planning) - most cost is still in Claude Code implementation

#### Pillar 2: Claude Code Deep Integration

Transform from "uses Claude Code" to "IS a Claude Code extension":
1. Become an MCP Server - expose ClaudeDev capabilities as MCP tools
2. Register as a Plugin - distribute through Claude Code's plugin system
3. Provide Skills - auto-activated expertise for issue analysis, PR review, team management
4. Use Hooks - intercept lifecycle events for quality gates, auto-review, security scanning
5. Use Worktrees - each implementation agent gets its own isolated git worktree

#### Pillar 3: Developer Experience

The UI/UX layer:
1. Dashboard 2.0 - real-time agent visualization, cost tracking, pipeline view
2. CLI 2.0 - interactive TUI with live status
3. Notifications - Slack, Discord, email integration
4. Observability - structured logging, metrics, tracing

---

## Part 3: Implementation Roadmap

### v0.2.0 - "The Brain" (Target: April 2026)

Theme: Add the AI thinking layer and memory system.

#### 3.1. Issue Thinker Module

Pre-analyzes issues before sending to Claude Code enhancement. Uses Anthropic API to:
- Decide priority (P0-P4)
- Estimate complexity (simple/medium/complex/epic)
- Generate investigation strategy
- Detect skip-worthy issues (spam, duplicates, incomplete)
- Find related past issues from memory

Model: Claude Sonnet 4 via Anthropic API (fast, cheap, good for analysis)

#### 3.2. Code Planner Module

Generates architecture plans before implementation begins. Uses Anthropic API to:
- Predict affected files
- Plan step-by-step implementation strategy
- Identify risk areas
- Define test strategy
- May upgrade/downgrade the enhancement tier

Model: Claude Opus 4 via Anthropic API (complex reasoning needed)

#### 3.3. Memory System

File-based persistent memory inspired by OpenClaw but structured for code:

```
~/.claudedev/memory/
  projects/{project}/
    architecture.md        # Auto-generated codebase summary
    patterns.md           # Detected coding patterns
    past_issues.jsonl     # Issue to outcome history
    review_patterns.md    # Common review findings
  global/
    tech_stack_knowledge.md
    common_bugs.md
  decisions/
    {date}-{topic}.md     # Architecture decisions made
```

Features: persists knowledge across sessions, learns from past cycles, feeds context to Brain modules, auto-prunes to manage token costs.

#### 3.4. Auth Mode: Dual Support

Support both Claude Code CLI and direct API key:
- Brain operations use Anthropic API directly (small, fast calls)
- Implementation sessions use Claude Code CLI (heavy, multi-turn)
- Users can provide their own API key for Brain layer OR rely on Claude Code subscription
- Budget tracking covers both Brain API calls and Claude Code session costs

### v0.3.0 - "Claude Code Native" (Target: May 2026)

Theme: Deep integration with Claude Code's extension system.

#### 3.5. ClaudeDev as MCP Server

Expose capabilities as MCP tools:
- `claudedev_list_issues` - list tracked issues with status
- `claudedev_enhance_issue` - trigger enhancement pipeline
- `claudedev_get_issue_context` - get full context (comments, timeline)
- `claudedev_spawn_team` - start implementation
- `claudedev_check_session` - check session status
- `claudedev_get_review_findings` - get review results
- `claudedev_dashboard_url` - open dashboard

This enables users to interact with ClaudeDev FROM within Claude Code sessions.

#### 3.6. ClaudeDev Skills

Auto-activated skills in .claude/skills/:
- claudedev-issue-analysis: "When analyzing a GitHub issue, use this approach..."
- claudedev-pr-review: "When reviewing a PR, check these categories..."
- claudedev-test-strategy: "When writing tests, cover these patterns..."
- claudedev-security-check: "When touching auth code, verify these..."

Skills auto-activate when Claude Code detects relevant context.

#### 3.7. ClaudeDev Hooks

Register hooks that fire during Claude Code sessions:
- PostToolUse (Write/Edit): Run auto-CI after file edits
- Stop: Verify quality gates before stopping
- PreToolUse (Bash + git push): Run full review before pushing

#### 3.8. Worktree Isolation for Agents

Each implementation agent operates in its own git worktree:
- Parallel implementation without file conflicts
- Each agent's changes are isolated until merge
- Easy rollback if an agent's work is rejected

### v0.4.0 - "Intelligence" (Target: June 2026)

Theme: Learning, optimization, and advanced decision-making.

#### 3.9. Decision Engine

Autonomous decision-making based on project history:
- Should we auto-implement? (considers complexity vs past success rate, budget, failure rate)
- Which reviewers to spawn? (dynamic selection based on changed file types)
- When to escalate? (detect repeated failures and alert humans)

#### 3.10. Cost Optimization Engine

Smart model selection and token management:
- Tier 1 bugfixes use Sonnet (fast, cheap)
- Tier 2 features use Sonnet for impl, Opus for architect
- Tier 3+ complex use Opus throughout
- Review tasks use Haiku for simple, Sonnet for complex
- Pre-implementation cost estimates with user approval

#### 3.11. Multi-Model Support

While Claude is primary, support model selection for cost optimization:
- Brain layer: configurable model per task type
- Implementation: Claude Code CLI
- Review: lighter models for routine checks
- Optional fallback for availability

### v0.5.0 - "Plugin Ecosystem" (Target: July 2026)

Theme: Distribute ClaudeDev as a Claude Code plugin.

#### 3.12. ClaudeDev Plugin

Package everything as a distributable plugin with commands, skills, hooks, and agents.

#### 3.13. Skill Marketplace

Community-contributed skills specific to code development:
- Language-specific (Python, TypeScript, Rust, Go)
- Framework skills (FastAPI, Next.js, Django, Rails)
- Review skills (OWASP, performance, accessibility)
- Testing skills (TDD, property-based, mutation testing)

### v1.0.0 - "Production Ready" (Target: September 2026)

Theme: Enterprise features, stability, comprehensive testing.

#### 3.14. Enterprise Features
- Multi-user support with role-based access
- Audit logging for compliance
- SSO integration
- Team budgets and cost allocation
- Self-hosted deployment guide (Docker)

#### 3.15. Reliability
- 95%+ test coverage
- Chaos testing (GitHub down? Claude down?)
- Graceful degradation
- Health monitoring and alerting

#### 3.16. Performance
- Benchmarked issue-to-PR pipeline times
- Optimized token usage (caching, summary compression)
- Parallel pipeline (enhance issue A while implementing issue B)

---

## Part 4: Key Design Principles

### 4.1. "Coding Only" Focus

Unlike OpenClaw (messaging, emails, calendars), ClaudeDev does ONE thing: turn GitHub issues into merged PRs. Every feature must serve this pipeline. If it does not make the issue-to-PR flow better, it does not belong.

### 4.2. Claude-Native, Claude-First

Built FOR Claude Code, WITH Claude Code, ON Anthropic's Claude:
- Use Claude Code's native features (hooks, skills, MCP, agents) rather than reinventing
- Use Anthropic API for the Brain layer
- Support Claude Code subscriptions AND API keys
- Extend Claude Code, don't compete with it

### 4.3. AI-Assisted, Human-Controlled

The Brain layer makes decisions, but humans approve:
- Auto-enhance: default ON (can be turned off per project)
- Auto-implement: default OFF (requires human approval)
- Budget limits: hard caps that the AI cannot override
- Dashboard shows AI reasoning for every decision

### 4.4. Quality Over Speed

OpenClaw moves fast and has had security incidents. ClaudeDev moves methodically:
- 8 specialized reviewers catch issues before production
- Quality gates block completion until all checks pass
- mypy strict + ruff + full test coverage
- Security-first design

### 4.5. Cost Transparency

Every API call is tracked, every session is budgeted:
- Per-issue, per-project, per-day budgets
- Brain layer costs tracked separately from implementation costs
- Pre-implementation cost estimates with user approval
- Monthly cost reports in dashboard

---

## Part 5: Immediate Next Steps (Post v0.1.0)

### Sprint 1 (Week 1-2): Foundation

1. Add Anthropic API client (`src/claudedev/brain/client.py`)
   - Dual auth: API key OR Claude Code token discovery
   - Model selection by task type
   - Token counting and cost tracking

2. Implement IssueThinker (`src/claudedev/brain/thinker.py`)
   - Pre-analysis prompt engineering
   - Priority scoring (P0-P4)
   - Skip detection (spam, duplicates, incomplete)

3. Add memory system (`src/claudedev/brain/memory.py`)
   - File-based persistent memory
   - Past issue to outcome tracking
   - Codebase architecture summaries

### Sprint 2 (Week 3-4): Integration

4. Implement MCP server mode (`src/claudedev/mcp/server.py`)
   - Expose core capabilities as MCP tools
   - Register in Claude Code settings

5. Create ClaudeDev skills (`.claude/skills/claudedev-*/`)
   - Issue analysis skill
   - PR review skill
   - Security check skill

6. Add worktree isolation (`src/claudedev/core/worktree.py`)
   - Per-agent worktree creation
   - Automatic cleanup on completion

### Sprint 3 (Week 5-6): Polish

7. Code Planner module (`src/claudedev/brain/planner.py`)
   - Architecture plan generation
   - File impact prediction
   - Cost estimation

8. Hook installer (`src/claudedev/hooks/installer.py`)
   - Auto-install ClaudeDev hooks in Claude Code projects
   - Quality gate hooks
   - Auto-CI hooks

9. Dashboard 2.0
   - AI decision explanations
   - Cost breakdown charts
   - Memory viewer

---

## Part 6: Target File Structure (v0.5.0)

```
src/claudedev/
  brain/                     # NEW - AI thinking layer
    __init__.py
    client.py               # Anthropic API client (dual auth)
    thinker.py              # Issue pre-analysis
    planner.py              # Implementation planning
    decision.py             # Autonomous decision engine
    memory.py               # Persistent memory system
    cost.py                 # Cost optimization
  core/
    credentials.py
    discovery.py
    orchestrator.py
    scheduler.py
    state.py
    worktree.py             # NEW - Git worktree management
  engines/
    issue_engine.py         # Enhanced with Brain integration
    team_engine.py          # Enhanced with worktree + cost opt
    pr_engine.py
    review_engine.py
  github/
    gh_client.py
    models.py
    webhook_server.py
  hooks/                     # NEW - Claude Code hook integration
    __init__.py
    installer.py            # Install hooks in Claude Code settings
    auto_ci.py              # Post-edit quality checks
    quality_gate.py         # Stop hook verification
  integrations/
    claude_sdk.py
    iterm2_manager.py
    tunnel_manager.py
  mcp/                       # NEW - MCP server mode
    __init__.py
    server.py               # ClaudeDev as MCP server
  ui/
    dashboard.py            # Enhanced with Brain insights
    menubar.py
    onboarding.py
  utils/
    logging.py
    security.py
```

---

## Part 7: Success Metrics

| Metric | v0.1.0 (Current) | v0.5.0 Target | v1.0.0 Target |
|--------|------------------|---------------|---------------|
| GitHub stars | 0 | 1,000 | 10,000 |
| Test count | 181 | 400 | 700 |
| Test coverage | ~70% | 85% | 95% |
| Avg issue-to-PR time | N/A (manual) | 15 min (Tier 1) | 5 min (Tier 1) |
| Models supported | Claude only | Claude + cost opt | Claude + fallback |
| MCP tools exposed | 0 | 7 | 15 |
| Skills available | 0 | 5 | 20+ |
| Memory recall accuracy | N/A | 70% | 90% |
| Monthly cost per project | Untracked | $50-200 | $30-150 (optimized) |

---

## Positioning Statement

ClaudeDev is the autonomous coding platform for Claude Code. While OpenClaw turns AI into a general-purpose autonomous agent, ClaudeDev focuses exclusively on software development: transforming GitHub issues into production-ready pull requests with deep codebase understanding, multi-reviewer quality pipelines, and an AI brain that learns from every implementation. Built for Claude Code, by Claude Code users.

---

*This masterplan is a living document. Update as the landscape evolves.*
