# Claude Code Deep Technical Research Report

**Date**: 2026-03-09
**Researcher**: ClaudeDev Technical Research
**Sources**: GitHub repositories (anthropics/claude-code, anthropics/claude-agent-sdk-demos, anthropics/claude-plugins-official), Official documentation (code.claude.com, platform.claude.com)

---

## Table of Contents

1. [Agent Architecture](#1-claude-code-agent-architecture)
2. [Hooks System](#2-hooks-system-deep-dive)
3. [MCP Architecture](#3-mcp-model-context-protocol-architecture)
4. [Agent SDK / Swarm Mode](#4-agent-sdk--swarm-mode)
5. [Skills System](#5-skills-system)
6. [Programmatic Control](#6-programmatic-control)
7. [Context Management](#7-context-management)
8. [API Direct Access](#8-api-direct-access)
9. [Plugin System](#9-plugin-system)
10. [Agent Teams](#10-agent-teams-experimental)
11. [Key Capabilities Matrix](#11-key-capabilities-matrix)

---

## 1. Claude Code Agent Architecture

### 1.1 Overview

Claude Code is an agentic coding tool built on Anthropic's Claude models. It operates as an autonomous agent loop in the terminal, IDE (VS Code, JetBrains), desktop app, or web browser. The core engine is the same across all surfaces -- CLAUDE.md files, settings, and MCP servers work identically everywhere.

### 1.2 The Agentic Loop

The agent loop follows a cycle:

```
SessionStart
  -> User submits prompt (UserPromptSubmit hook fires)
    -> Claude processes prompt
      -> Claude decides on tool use
        -> PreToolUse hook fires (can block/modify)
          -> PermissionRequest hook fires (if permission needed)
            -> Tool executes
              -> PostToolUse hook fires (or PostToolUseFailure)
                -> Claude observes result
                  -> Claude decides: more tools needed or respond
                    -> If more tools: loop back to tool decision
                    -> If done: Stop hook fires
                      -> Response delivered to user
                        -> Wait for next prompt or SessionEnd
```

Key aspects:
- **Tool decision**: Claude autonomously decides which tool to use based on the task, available tools, and context
- **Multi-step execution**: The loop continues until Claude determines the task is complete or hits a turn limit
- **Hook interception points**: Every stage can be intercepted by hooks for validation, logging, or modification
- **Auto-compaction**: When context reaches ~95% capacity, automatic compaction triggers (configurable via `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`)

### 1.3 Built-in Tools

Claude Code provides these internal tools:

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| **Read** | Read file contents | `file_path`, `offset`, `limit` |
| **Write** | Create/overwrite files | `file_path`, `content` |
| **Edit** | String replacement in files | `file_path`, `old_string`, `new_string`, `replace_all` |
| **Bash** | Execute shell commands | `command`, `description`, `timeout`, `run_in_background` |
| **Glob** | Find files by pattern | `pattern`, `path` |
| **Grep** | Search file contents (regex) | `pattern`, `path`, `glob`, `output_mode`, `-i`, `multiline` |
| **WebFetch** | Fetch and process web content | `url`, `prompt` |
| **WebSearch** | Search the web | `query`, `allowed_domains`, `blocked_domains` |
| **Agent** | Spawn subagents (formerly Task) | `prompt`, `description`, `subagent_type`, `model` |
| **AskUserQuestion** | Ask user clarifying questions | Multiple choice options |
| **Skill** | Invoke a skill/command | Skill name and arguments |
| **NotebookEdit** | Edit Jupyter notebook cells | Cell operations |
| **MCPSearch** | Dynamic tool discovery for MCP | Search query |

### 1.4 Session Management

- **Session ID**: Each session gets a unique UUID, accessible via `--session-id` flag
- **Session persistence**: Sessions are saved to disk by default (`~/.claude/projects/{project}/{sessionId}/`)
- **Resume**: `claude -c` (continue most recent) or `claude -r <session-id>` (resume specific)
- **Fork**: `--fork-session` creates a new session ID when resuming
- **No persistence**: `--no-session-persistence` disables disk saving (print mode only)
- **PR linking**: Sessions auto-link to PRs when created via `gh pr create`, resumable with `--from-pr`

### 1.5 Context Window Handling

- Claude reads CLAUDE.md files at session start
- Auto-compaction triggers at ~95% capacity (configurable)
- CLAUDE.md files fully survive compaction -- they are re-read from disk
- Conversation-only context is lost during compaction
- `PreCompact` hook fires before compaction (matcher: `manual` or `auto`)
- Subagent transcripts are stored separately and unaffected by main conversation compaction

---

## 2. Hooks System (Deep Dive)

### 2.1 Hook Types

There are **four types** of hook handlers:

| Type | Description | Delivery |
|------|-------------|----------|
| `command` | Shell command | JSON via stdin, results via exit code + stdout |
| `http` | HTTP POST endpoint | JSON body, results via response body |
| `prompt` | LLM single-turn evaluation | Yes/no decision as JSON |
| `agent` | Subagent with tools (Read, Grep, Glob) | Decision after analysis |

### 2.2 Complete Hook Events Reference

#### SessionStart
- **When**: Session begins or resumes
- **Matcher values**: `startup`, `resume`, `clear`, `compact`
- **Can block**: No
- **Special**: stdout is added as context for Claude; access to `CLAUDE_ENV_FILE` for persisting env vars
- **Input fields**: `source`, `model`, optionally `agent_type`
- **Decision control**: `additionalContext` field in `hookSpecificOutput`

#### InstructionsLoaded
- **When**: CLAUDE.md or `.claude/rules/*.md` loaded into context
- **Matcher**: Not supported (fires on every load)
- **Can block**: No
- **Input fields**: `file_path`, `memory_type`, `load_reason`, `globs`, `trigger_file_path`, `parent_file_path`
- **Use case**: Audit logging, compliance tracking

#### UserPromptSubmit
- **When**: User submits a prompt, before Claude processes it
- **Matcher**: Not supported
- **Can block**: Yes (exit 2 or `decision: "block"`)
- **Input fields**: `prompt`
- **Decision control**: `decision: "block"`, `reason`, `additionalContext`
- **Use case**: Prompt validation, context injection, prompt filtering

#### PreToolUse
- **When**: Before tool call executes
- **Matcher**: Tool name (`Bash`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `Agent`, `WebFetch`, `WebSearch`, `mcp__*`)
- **Can block**: Yes
- **Input fields**: `tool_name`, `tool_input`, `tool_use_id`
- **Decision control via `hookSpecificOutput`**:
  - `permissionDecision`: `"allow"` | `"deny"` | `"ask"`
  - `permissionDecisionReason`: string
  - `updatedInput`: modify tool parameters before execution
  - `additionalContext`: inject context for Claude

#### PermissionRequest
- **When**: Permission dialog about to be shown
- **Matcher**: Tool name
- **Can block**: Yes
- **Input fields**: `tool_name`, `tool_input`, `permission_suggestions`
- **Decision control via `hookSpecificOutput`**:
  - `decision.behavior`: `"allow"` | `"deny"`
  - `decision.updatedInput`: modify tool input
  - `decision.updatedPermissions`: apply "always allow" rules
  - `decision.message`: reason for deny
  - `decision.interrupt`: stop Claude on deny

#### PostToolUse
- **When**: After tool call succeeds
- **Matcher**: Tool name
- **Can block**: No (tool already ran)
- **Input fields**: `tool_name`, `tool_input`, `tool_use_id`, `tool_result`
- **Decision control**: `decision: "block"`, `reason` (shown to Claude as error)

#### PostToolUseFailure
- **When**: After tool call fails
- **Matcher**: Tool name
- **Can block**: No
- **Input fields**: `tool_name`, `tool_input`, `tool_use_id`, `tool_error`

#### Stop
- **When**: Claude finishes responding
- **Matcher**: Not supported
- **Can block**: Yes (exit 2 prevents stopping, continues conversation)
- **Decision control**: `decision: "block"`, `reason`
- **Critical use case**: Autonomous loops (ralph-wiggum pattern)

#### SubagentStart
- **When**: Subagent spawned
- **Matcher**: Agent type (`Bash`, `Explore`, `Plan`, custom names)
- **Can block**: No

#### SubagentStop
- **When**: Subagent finishes
- **Matcher**: Agent type
- **Can block**: Yes (exit 2 prevents stopping)

#### TeammateIdle
- **When**: Agent team teammate about to go idle
- **Matcher**: Not supported
- **Can block**: Yes (exit 2 keeps teammate working)

#### TaskCompleted
- **When**: Task being marked as completed
- **Matcher**: Not supported
- **Can block**: Yes (exit 2 prevents completion)

#### Notification
- **When**: Claude Code sends a notification
- **Matcher**: `permission_prompt`, `idle_prompt`, `auth_success`, `elicitation_dialog`
- **Can block**: No

#### ConfigChange
- **When**: Configuration file changes during session
- **Matcher**: `user_settings`, `project_settings`, `local_settings`, `policy_settings`, `skills`
- **Can block**: Yes (except `policy_settings`)

#### PreCompact
- **When**: Before context compaction
- **Matcher**: `manual`, `auto`
- **Can block**: No

#### WorktreeCreate
- **When**: Worktree being created
- **Matcher**: Not supported
- **Can block**: Yes (non-zero exit fails creation)
- **Output**: Hook prints absolute path to created worktree

#### WorktreeRemove
- **When**: Worktree being removed
- **Matcher**: Not supported
- **Can block**: No

#### SessionEnd
- **When**: Session terminates
- **Matcher**: `clear`, `logout`, `prompt_input_exit`, `bypass_permissions_disabled`, `other`
- **Can block**: No

### 2.3 Common Input Fields (All Events)

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/path/to/project",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "agent_id": "optional-subagent-id",
  "agent_type": "optional-agent-type"
}
```

### 2.4 Exit Code Semantics

| Exit Code | Meaning | Behavior |
|-----------|---------|----------|
| **0** | Success | Parse stdout for JSON output; proceed |
| **2** | Blocking error | Block action; stderr fed to Claude as error |
| **Other** | Non-blocking error | stderr shown in verbose mode; continue |

### 2.5 JSON Output Fields

```json
{
  "continue": true,
  "stopReason": "string shown to user when continue=false",
  "suppressOutput": false,
  "systemMessage": "warning shown to user",
  "decision": "block",
  "reason": "explanation",
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny|ask",
    "permissionDecisionReason": "string",
    "updatedInput": {},
    "additionalContext": "string"
  }
}
```

### 2.6 Hook Configuration Locations

| Location | Scope | Shareable |
|----------|-------|-----------|
| `~/.claude/settings.json` | All projects | No |
| `.claude/settings.json` | Single project | Yes (commit to repo) |
| `.claude/settings.local.json` | Single project | No (gitignored) |
| Managed policy settings | Organization-wide | Yes (admin-controlled) |
| Plugin `hooks/hooks.json` | When plugin enabled | Yes |
| Skill/agent frontmatter | While component active | Yes |

### 2.7 Critical Hook Patterns for Autonomous Operation

#### Auto-Continue (Ralph Loop Pattern)
```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/check-if-done.sh"
          }
        ]
      }
    ]
  }
}
```
The script exits with code 2 to prevent stopping (continues conversation), or exits 0 to allow stopping.

#### Auto-Approve Permissions (PermissionRequest)
```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/auto-approve.sh"
          }
        ]
      }
    ]
  }
}
```
Script returns `{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}` to auto-approve.

#### Tool Input Modification
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "updatedInput": {
      "command": "npm run lint -- --fix"
    }
  }
}
```

#### Environment Variable Persistence (SessionStart)
```bash
#!/bin/bash
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo 'export MY_VAR=value' >> "$CLAUDE_ENV_FILE"
fi
```

### 2.8 Async Hooks

Command hooks support `"async": true` to run in the background without blocking. The hook fires and Claude Code continues immediately.

### 2.9 Prompt-Based and Agent-Based Hooks

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "prompt",
            "prompt": "A bash command is about to be executed: $ARGUMENTS. Is this safe? Return JSON with decision.",
            "model": "haiku",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Agent hooks (`type: "agent"`) spawn a full subagent with tools (Read, Grep, Glob) to verify conditions.

---

## 3. MCP (Model Context Protocol) Architecture

### 3.1 Overview

MCP is an open standard for connecting AI tools to external data sources. Claude Code supports three transport types:

| Transport | Protocol | Use Case |
|-----------|----------|----------|
| **HTTP** (recommended) | Streamable HTTP POST | Cloud services, remote APIs |
| **SSE** (deprecated) | Server-Sent Events | Legacy remote servers |
| **stdio** | Standard I/O | Local processes, custom scripts |

### 3.2 Server Registration

```bash
# HTTP server
claude mcp add --transport http <name> <url>

# SSE server
claude mcp add --transport sse <name> <url>

# stdio server
claude mcp add --transport stdio --env KEY=value <name> -- <command> [args...]

# From JSON config
claude mcp add-json <name> '<json>'

# Import from Claude Desktop
claude mcp add-from-claude-desktop

# Management
claude mcp list
claude mcp get <name>
claude mcp remove <name>
```

### 3.3 MCP Scopes

| Scope | Storage | Shared |
|-------|---------|--------|
| **local** (default) | `~/.claude.json` under project path | No |
| **project** | `.mcp.json` in project root | Yes (version control) |
| **user** | `~/.claude.json` globally | No (all projects) |

Precedence: local > project > user

### 3.4 `.mcp.json` Configuration Format

```json
{
  "mcpServers": {
    "server-name": {
      "command": "/path/to/server",
      "args": ["--port", "8080"],
      "env": {
        "API_KEY": "${API_KEY}",
        "BASE_URL": "${BASE_URL:-https://default.com}"
      }
    }
  }
}
```

Environment variable expansion supported:
- `${VAR}` -- expand variable
- `${VAR:-default}` -- expand with default

Expansion locations: `command`, `args`, `env`, `url`, `headers`

### 3.5 MCP Tool Naming Convention

MCP tools follow: `mcp__<server>__<tool>`

Examples:
- `mcp__memory__create_entities`
- `mcp__github__search_repositories`
- `mcp__filesystem__read_file`

### 3.6 MCP Resources

MCP servers expose resources accessible via `@` mentions:
```
@github:issue://123
@docs:file://api/authentication
@postgres:schema://users
```

### 3.7 MCP Prompts as Commands

MCP server prompts become available as slash commands:
```
/mcp__github__list_prs
/mcp__github__pr_review 456
```

### 3.8 MCP Tool Search

When MCP tools exceed 10% of context window, Claude Code auto-enables tool search:
- Tools are deferred (not preloaded)
- Claude uses MCPSearch tool to discover relevant tools on-demand
- Configurable via `ENABLE_TOOL_SEARCH`: `auto` (default), `auto:<N>`, `true`, `false`

### 3.9 MCP Output Limits

- Warning at 10,000 tokens
- Default max: 25,000 tokens
- Override: `MAX_MCP_OUTPUT_TOKENS=50000`

### 3.10 OAuth Support

Claude Code supports OAuth 2.0 for remote MCP servers:
- Dynamic client registration
- Pre-configured credentials (`--client-id`, `--client-secret`)
- Fixed callback port (`--callback-port`)
- Metadata URL override (`authServerMetadataUrl`)

### 3.11 Dynamic Tool Updates

MCP servers can send `list_changed` notifications. Claude Code auto-refreshes available capabilities.

### 3.12 Claude Code as MCP Server

```bash
claude mcp serve
```

Exposes Claude Code's tools (View, Edit, LS, etc.) as an MCP server for other applications.

### 3.13 Managed MCP Configuration

**Option 1: Exclusive control** (`managed-mcp.json`):
- macOS: `/Library/Application Support/ClaudeCode/managed-mcp.json`
- Linux: `/etc/claude-code/managed-mcp.json`
- Windows: `C:\Program Files\ClaudeCode\managed-mcp.json`

**Option 2: Policy-based** (allowlists/denylists in managed settings):
```json
{
  "allowedMcpServers": [
    { "serverName": "github" },
    { "serverCommand": ["npx", "-y", "approved-package"] },
    { "serverUrl": "https://mcp.company.com/*" }
  ],
  "deniedMcpServers": [
    { "serverName": "dangerous-server" }
  ]
}
```

---

## 4. Agent SDK / Swarm Mode

### 4.1 SDK Overview

The Claude Agent SDK (formerly Claude Code SDK) provides programmatic access to Claude Code's tools and agent loop. Available in Python and TypeScript.

```bash
# Install
pip install claude-agent-sdk       # Python
npm install @anthropic-ai/claude-agent-sdk  # TypeScript
```

### 4.2 Core API: `query()`

**Python:**
```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash"],
            permission_mode="acceptEdits",
        ),
    ):
        if hasattr(message, "result"):
            print(message.result)

asyncio.run(main())
```

**TypeScript:**
```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Find and fix the bug in auth.py",
  options: {
    allowedTools: ["Read", "Edit", "Bash"],
    permissionMode: "acceptEdits",
  }
})) {
  if ("result" in message) console.log(message.result);
}
```

### 4.3 ClaudeAgentOptions (Key Fields)

| Field | Description |
|-------|-------------|
| `allowed_tools` / `allowedTools` | Tools pre-approved for use |
| `permission_mode` / `permissionMode` | `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan` |
| `resume` | Session ID to resume |
| `model` | Model to use (sonnet, opus, haiku) |
| `max_turns` / `maxTurns` | Limit agentic turns |
| `max_budget_usd` / `maxBudgetUsd` | Budget limit |
| `system_prompt` / `systemPrompt` | Replace or append system prompt |
| `append_system_prompt` / `appendSystemPrompt` | Append to default prompt |
| `mcp_servers` / `mcpServers` | MCP server configurations |
| `agents` | Subagent definitions |
| `hooks` | Lifecycle hooks (callback functions) |
| `setting_sources` / `settingSources` | Which settings to load (`["project"]`) |
| `plugins` | Plugin configurations |
| `json_schema` / `jsonSchema` | Structured output schema |

### 4.4 Subagent Definitions in SDK

```python
from claude_agent_sdk import AgentDefinition

agents={
    "code-reviewer": AgentDefinition(
        description="Expert code reviewer.",
        prompt="Analyze code quality and suggest improvements.",
        tools=["Read", "Glob", "Grep"],
        model="sonnet",
    )
}
```

### 4.5 Hooks in SDK (Callback Functions)

```python
from claude_agent_sdk import HookMatcher

async def log_file_change(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "unknown")
    # Custom logic
    return {}  # or return decision

hooks={
    "PostToolUse": [
        HookMatcher(matcher="Edit|Write", hooks=[log_file_change])
    ]
}
```

### 4.6 Session Management in SDK

```python
# Capture session ID
async for message in query(prompt="Read auth module", options=opts):
    if hasattr(message, "subtype") and message.subtype == "init":
        session_id = message.session_id

# Resume with full context
async for message in query(
    prompt="Now find all callers",
    options=ClaudeAgentOptions(resume=session_id),
):
    pass
```

### 4.7 Streaming Message Types

Messages from `query()` include:
- `type: "system"`, `subtype: "init"` -- session initialization with `session_id`
- `type: "system"`, `subtype: "compact_boundary"` -- compaction event
- Messages with `result` field -- final agent result
- Messages with `parent_tool_use_id` -- from within subagent context

---

## 5. Skills System

### 5.1 Skill File Format

Skills are Markdown files with YAML frontmatter stored in:

| Location | Scope |
|----------|-------|
| `~/.claude/skills/<name>/SKILL.md` | Personal (all projects) |
| `.claude/skills/<name>/SKILL.md` | Project |
| `<plugin>/skills/<name>/SKILL.md` | Plugin |
| Enterprise managed settings | Organization-wide |

Legacy `.claude/commands/<name>.md` format still works and creates the same `/name` command.

### 5.2 Skill Directory Structure

```
my-skill/
  SKILL.md           # Required: main instructions
  template.md        # Optional: templates
  examples/
    sample.md        # Optional: examples
  scripts/
    validate.sh      # Optional: executable scripts
```

### 5.3 Complete Frontmatter Reference

```yaml
---
name: my-skill                    # Unique identifier (lowercase, hyphens)
description: What this does       # Used by Claude for auto-invocation
argument-hint: [issue-number]     # Autocomplete hint
disable-model-invocation: true    # Only user can invoke
user-invocable: false             # Only Claude can invoke
allowed-tools: Read, Grep, Glob   # Tool restrictions
model: sonnet                     # Model override
context: fork                     # Run in forked subagent
agent: Explore                    # Subagent type for fork
hooks:                            # Scoped lifecycle hooks
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/check.sh"
---
```

### 5.4 String Substitutions

| Variable | Description |
|----------|-------------|
| `$ARGUMENTS` | All arguments passed to skill |
| `$ARGUMENTS[N]` or `$N` | Specific argument by index |
| `${CLAUDE_SESSION_ID}` | Current session ID |
| `${CLAUDE_SKILL_DIR}` | Skill directory path |

### 5.5 Dynamic Context Injection

The `` !`command` `` syntax runs shell commands before skill content is sent to Claude:

```yaml
---
name: pr-summary
---
PR diff: !`gh pr diff`
PR comments: !`gh pr view --comments`
```

### 5.6 Invocation Control Matrix

| Setting | User can invoke | Claude can invoke |
|---------|----------------|-------------------|
| Default | Yes | Yes |
| `disable-model-invocation: true` | Yes | No |
| `user-invocable: false` | No | Yes |

### 5.7 Bundled Skills

- `/simplify` -- Code reuse, quality, efficiency review (3 parallel agents)
- `/batch <instruction>` -- Large-scale parallel changes across codebase (worktree-based)
- `/debug [description]` -- Session debug log analysis
- `/loop [interval] <prompt>` -- Recurring prompt on schedule
- `/claude-api` -- Claude API reference material

### 5.8 Skill Context Budget

- Default: 2% of context window (fallback 16,000 chars)
- Override: `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable
- Only descriptions loaded at startup; full content loads on invocation

---

## 6. Programmatic Control

### 6.1 CLI Flags (Complete Reference)

**Core Execution:**
```bash
claude -p "query"                          # Print mode (non-interactive)
claude -c                                  # Continue most recent session
claude -r <session-id> "query"             # Resume specific session
claude --model sonnet                      # Model selection
claude --max-turns 3                       # Limit agentic turns
claude --max-budget-usd 5.00              # Budget limit
```

**Output Control:**
```bash
--output-format text|json|stream-json     # Output format
--input-format text|stream-json           # Input format
--json-schema '{...}'                     # Structured output
--include-partial-messages                # Streaming partials
--verbose                                 # Full turn output
```

**Prompt Control:**
```bash
--system-prompt "..."                     # Replace system prompt
--system-prompt-file ./prompt.txt         # Replace from file
--append-system-prompt "..."              # Append to default
--append-system-prompt-file ./extra.txt   # Append from file
```

**Tool and Permission Control:**
```bash
--allowedTools "Bash,Read,Edit"           # Auto-approve tools
--disallowedTools "WebSearch"             # Remove tools
--tools "Bash,Edit,Read"                  # Restrict available tools
--permission-mode plan|acceptEdits|dontAsk|bypassPermissions
--dangerously-skip-permissions            # Skip all permissions
--permission-prompt-tool mcp_tool         # MCP tool for permissions
```

**Agent/Subagent Control:**
```bash
--agent my-custom-agent                   # Use specific agent
--agents '{"name":{"description":"...","prompt":"..."}}'  # Dynamic agents
--teammate-mode auto|in-process|tmux      # Agent team display
```

**MCP Control:**
```bash
--mcp-config ./mcp.json                   # Load MCP servers
--strict-mcp-config                       # Only use specified MCP
```

**Session Control:**
```bash
--session-id "uuid"                       # Specific session UUID
--fork-session                            # Fork when resuming
--no-session-persistence                  # Don't save to disk
--from-pr 123                             # Resume from PR
```

**Other:**
```bash
--add-dir ../other-project                # Additional directories
--worktree feature-name                   # Git worktree isolation
--chrome                                  # Chrome integration
--plugin-dir ./my-plugins                 # Load plugins
--debug "api,hooks"                       # Debug categories
--init / --init-only                      # Initialization hooks
--maintenance                             # Maintenance hooks
--remote "task description"               # Web session
--teleport                                # Teleport web session
--settings ./settings.json                # Additional settings
--setting-sources user,project            # Setting source filter
--betas interleaved-thinking              # API beta features
--fallback-model sonnet                   # Fallback on overload
```

### 6.2 Non-Interactive (Headless) Patterns

**Basic query:**
```bash
claude -p "What does auth.py do?"
```

**Structured JSON output:**
```bash
claude -p "Summarize" --output-format json | jq -r '.result'
```

**Schema-validated output:**
```bash
claude -p "Extract functions" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}}}'
```

**Streaming tokens:**
```bash
claude -p "Write poem" --output-format stream-json --verbose --include-partial-messages | \
  jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

**Pipe input:**
```bash
cat logs.txt | claude -p "Explain these errors"
git diff main --name-only | claude -p "Review these files"
tail -f app.log | claude -p "Alert on anomalies"
```

**Continue conversations:**
```bash
session_id=$(claude -p "Start review" --output-format json | jq -r '.session_id')
claude -p "Continue review" --resume "$session_id"
```

### 6.3 Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | API key |
| `CLAUDE_CODE_USE_BEDROCK=1` | Use AWS Bedrock |
| `CLAUDE_CODE_USE_VERTEX=1` | Use Google Vertex AI |
| `CLAUDE_CODE_USE_FOUNDRY=1` | Use Azure AI Foundry |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | Compaction threshold (e.g., `50`) |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` | Disable background subagents |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY` | Disable auto memory |
| `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` | Load CLAUDE.md from --add-dir |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Enable agent teams |
| `ENABLE_TOOL_SEARCH` | MCP tool search: auto, true, false |
| `MAX_MCP_OUTPUT_TOKENS` | MCP output token limit |
| `MCP_TIMEOUT` | MCP server startup timeout (ms) |
| `SLASH_COMMAND_TOOL_CHAR_BUDGET` | Skill description budget |
| `ENABLE_CLAUDEAI_MCP_SERVERS` | Enable claude.ai MCP servers |
| `CLAUDE_CODE_REMOTE` | Set to "true" in remote environments |

---

## 7. Context Management

### 7.1 CLAUDE.md File Hierarchy

| Scope | Location | Priority |
|-------|----------|----------|
| Managed policy | `/Library/Application Support/ClaudeCode/CLAUDE.md` | Highest |
| Project | `./CLAUDE.md` or `./.claude/CLAUDE.md` | High |
| User | `~/.claude/CLAUDE.md` | Medium |
| Local | `./CLAUDE.local.md` | Medium (personal) |

Loading behavior:
- Files in ancestor directories: loaded at startup
- Files in subdirectories: loaded on-demand when Claude reads files there
- Files in `--add-dir`: only with `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`

### 7.2 Rules System (`.claude/rules/`)

```
.claude/rules/
  code-style.md     # Always loaded
  testing.md         # Always loaded
  api-rules.md       # Path-scoped (loaded when matching files accessed)
```

**Path-scoped rules:**
```yaml
---
paths:
  - "src/api/**/*.ts"
  - "src/**/*.{ts,tsx}"
---
Rules that only apply when working with matching files...
```

User-level rules: `~/.claude/rules/` (loaded before project rules)

### 7.3 Import System

CLAUDE.md files support `@path/to/import` syntax:
```markdown
See @README for overview.
Follow @docs/git-instructions.md for workflow.
Personal: @~/.claude/my-project-instructions.md
```

Max import depth: 5 hops

### 7.4 Auto Memory

- Storage: `~/.claude/projects/<project>/memory/`
- Entry point: `MEMORY.md` (first 200 lines loaded per session)
- Topic files: `debugging.md`, `api-conventions.md`, etc. (loaded on demand)
- Toggle: `autoMemoryEnabled` in settings or `/memory` command
- Environment: `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`
- Scope: per git repository (all worktrees share same memory)
- Subagents can have their own memory (`user`, `project`, `local` scopes)

### 7.5 Context Compaction

- Auto-triggers at ~95% capacity (configurable via `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`)
- CLAUDE.md files re-read fresh from disk after compaction
- Conversation-only context is summarized/compressed
- `/compact` for manual compaction
- `PreCompact` hook fires before compaction
- Subagent transcripts unaffected by main compaction

### 7.6 Exclude Patterns

```json
{
  "claudeMdExcludes": [
    "**/monorepo/CLAUDE.md",
    "/home/user/monorepo/other-team/.claude/rules/**"
  ]
}
```

---

## 8. API Direct Access

### 8.1 Model Aliases

| Alias | Model ID | Notes |
|-------|----------|-------|
| `sonnet` | `claude-sonnet-4-6` | Default for most tasks |
| `opus` | `claude-opus-4-6` | Most capable |
| `haiku` | (latest haiku) | Fast, cheap, used for Explore agent |

### 8.2 Authentication Methods

| Method | Configuration |
|--------|--------------|
| Anthropic API | `ANTHROPIC_API_KEY` |
| AWS Bedrock | `CLAUDE_CODE_USE_BEDROCK=1` + AWS credentials |
| Google Vertex AI | `CLAUDE_CODE_USE_VERTEX=1` + GCP credentials |
| Azure AI Foundry | `CLAUDE_CODE_USE_FOUNDRY=1` + Azure credentials |
| Claude.ai subscription | OAuth login via `claude auth login` |

### 8.3 API Features Available

- **Extended thinking**: Include "ultrathink" in skill content or use `--betas interleaved-thinking`
- **Structured outputs**: `--json-schema` for schema-validated JSON responses
- **Streaming**: `--output-format stream-json` for real-time token delivery
- **Budget control**: `--max-budget-usd` and `--max-turns` for cost management

### 8.4 Permission Modes

| Mode | Behavior |
|------|----------|
| `default` | Standard permission checking |
| `plan` | Read-only exploration |
| `acceptEdits` | Auto-accept file edits |
| `dontAsk` | Auto-deny prompts (allowed tools still work) |
| `bypassPermissions` | Skip all permission checks |

---

## 9. Plugin System

### 9.1 Plugin Structure

```
plugin-name/
  .claude-plugin/
    plugin.json          # Plugin metadata
  commands/              # Slash commands
  agents/                # Specialized agents
  skills/                # Skills
  hooks/
    hooks.json           # Event handlers
  .mcp.json              # MCP server configuration
  README.md
```

### 9.2 plugin.json Format

```json
{
  "name": "my-plugin",
  "description": "Plugin description",
  "mcpServers": {
    "plugin-api": {
      "command": "${CLAUDE_PLUGIN_ROOT}/servers/api-server",
      "args": ["--port", "8080"]
    }
  }
}
```

### 9.3 Plugin Environment Variables

- `${CLAUDE_PLUGIN_ROOT}` -- Plugin root directory
- `$CLAUDE_PROJECT_DIR` -- Project root directory

### 9.4 Official Plugins (from anthropics/claude-code repo)

| Plugin | Key Components |
|--------|---------------|
| **agent-sdk-dev** | `/new-sdk-app` command, SDK verification agents |
| **code-review** | `/code-review` with 5 parallel Sonnet agents |
| **commit-commands** | `/commit`, `/commit-push-pr`, `/clean_gone` |
| **feature-dev** | 7-phase workflow with `code-explorer`, `code-architect`, `code-reviewer` agents |
| **frontend-design** | Auto-invoked skill for bold frontend design |
| **hookify** | `/hookify` to create custom hooks from patterns |
| **plugin-dev** | `/plugin-dev:create-plugin` with 7 expert skills |
| **pr-review-toolkit** | 6 specialized review agents |
| **ralph-wiggum** | `/ralph-loop` autonomous iteration |
| **security-guidance** | PreToolUse hook monitoring 9 security patterns |
| **explanatory-output-style** | SessionStart hook for educational context |
| **learning-output-style** | SessionStart hook for interactive learning |

### 9.5 Plugin Marketplace

The `anthropics/claude-code` repo includes a `.claude-plugin/marketplace.json` serving as an official marketplace. Plugins from `anthropics/claude-plugins-official` provide additional official plugins.

---

## 10. Agent Teams (Experimental)

### 10.1 Enabling

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### 10.2 Architecture

| Component | Role |
|-----------|------|
| **Team lead** | Main session that creates team, spawns teammates, coordinates |
| **Teammates** | Independent Claude Code instances with own context windows |
| **Task list** | Shared list with states: pending, in_progress, completed |
| **Mailbox** | Direct messaging between any agents |

Storage:
- Team config: `~/.claude/teams/{team-name}/config.json`
- Task list: `~/.claude/tasks/{team-name}/`

### 10.3 Display Modes

| Mode | Description |
|------|-------------|
| `in-process` | All in main terminal, Shift+Down to cycle |
| `tmux` | Split panes, one per teammate |
| `auto` (default) | Split if in tmux, otherwise in-process |

### 10.4 Key Capabilities

- **Shared task list**: Tasks with dependencies, auto-unblock on completion
- **Self-claiming**: Teammates pick up unassigned tasks
- **File locking**: Prevents race conditions on task claiming
- **Direct messaging**: `message` (one-to-one) and `broadcast` (all teammates)
- **Plan approval**: Teammates can work in read-only plan mode until lead approves
- **Automatic idle notifications**: Lead notified when teammates finish
- **Quality gates**: `TeammateIdle` and `TaskCompleted` hooks for enforcement

### 10.5 Subagents vs Agent Teams

| Aspect | Subagents | Agent Teams |
|--------|-----------|-------------|
| Context | Own window, results return to caller | Fully independent |
| Communication | Report back to main agent only | Direct peer messaging |
| Coordination | Main agent manages all | Shared task list, self-coordination |
| Nesting | Cannot spawn sub-subagents | Cannot spawn sub-teams |
| Token cost | Lower (results summarized) | Higher (each is full instance) |
| Best for | Focused tasks | Complex collaborative work |

### 10.6 Limitations

- No session resumption with in-process teammates
- One team per session
- No nested teams
- Lead is fixed (cannot transfer)
- Permissions set at spawn for all teammates

---

## 11. Key Capabilities Matrix

### What ClaudeDev Can Leverage

| Capability | Mechanism | Priority |
|------------|-----------|----------|
| **Autonomous operation** | Stop hook (exit 2 to continue), PermissionRequest hook (auto-approve) | Critical |
| **Tool interception** | PreToolUse hooks with `updatedInput` to modify tool calls | Critical |
| **Context injection** | SessionStart hooks, UserPromptSubmit additionalContext | High |
| **Multi-agent orchestration** | Agent SDK `query()` with subagent definitions | Critical |
| **Parallel execution** | Agent teams with shared task list and messaging | High |
| **Structured output** | `--json-schema` with `--output-format json` | High |
| **Session persistence** | Resume/continue with session IDs | High |
| **Dynamic tool loading** | MCP servers added programmatically | High |
| **Custom tools** | MCP stdio servers with any language | High |
| **Cost control** | `--max-budget-usd`, `--max-turns` | Medium |
| **Permission automation** | PermissionRequest hooks, `--dangerously-skip-permissions` | High |
| **Environment setup** | SessionStart with `CLAUDE_ENV_FILE` | Medium |
| **Quality enforcement** | PostToolUse hooks, TaskCompleted hooks | Medium |
| **Skill packaging** | SKILL.md with frontmatter, context: fork | Medium |
| **Plugin distribution** | plugin.json with commands, agents, skills, hooks, MCP | Medium |
| **Memory persistence** | Auto memory in `~/.claude/projects/` | Medium |
| **Streaming control** | `--output-format stream-json --include-partial-messages` | Medium |
| **Model routing** | `--model`, subagent `model` field, skill `model` field | Medium |

### Architecture Patterns for Autonomous AI Brain

1. **Orchestrator Pattern**: Main agent uses Agent SDK `query()` to spawn specialized sub-agents, each with focused tools and prompts
2. **Pipeline Pattern**: Chain multiple `query()` calls with session resume for multi-step workflows
3. **Swarm Pattern**: Agent teams with 3-5 teammates, shared task list, quality gate hooks
4. **Gate Pattern**: PreToolUse + PostToolUse hooks for validation, Stop hooks for completion criteria
5. **Memory Pattern**: CLAUDE.md for rules, auto-memory for learnings, skills for reusable workflows
6. **MCP Bridge Pattern**: Custom MCP stdio server wrapping external APIs for seamless tool integration

---

## Appendix A: Settings File Hierarchy

| File | Location | Scope |
|------|----------|-------|
| Managed policy | System directories | Organization (highest priority) |
| `~/.claude/settings.json` | Home | User (all projects) |
| `.claude/settings.json` | Project | Project (shared) |
| `.claude/settings.local.json` | Project | Project (personal, gitignored) |

Settings merge across layers. Higher priority wins for conflicts.

### Key Settings Fields

```json
{
  "permissions": {
    "allow": ["Read", "Glob", "Grep"],
    "ask": ["Bash"],
    "deny": ["Agent(Explore)"],
    "disableBypassPermissionsMode": "disable"
  },
  "allowManagedPermissionRulesOnly": true,
  "allowManagedHooksOnly": true,
  "strictKnownMarketplaces": [],
  "autoMemoryEnabled": true,
  "claudeMdExcludes": [],
  "teammateMode": "in-process",
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "hooks": { ... },
  "sandbox": {
    "autoAllowBashIfSandboxed": false,
    "network": {
      "allowedDomains": [],
      "allowLocalBinding": false
    }
  }
}
```

## Appendix B: GitHub Repositories Reference

| Repository | Purpose |
|-----------|---------|
| `anthropics/claude-code` | Main Claude Code repo with plugins, examples, settings |
| `anthropics/claude-agent-sdk-demos` | SDK demo projects (email agent, research agent, etc.) |
| `anthropics/claude-plugins-official` | Official plugin directory |
| `anthropics/claude-code-action` | GitHub Actions integration |
| `anthropics/claude-code-security-review` | Security review GitHub Action |
| `anthropics/claude-code-monitoring-guide` | Monitoring guide |
| `anthropics/claude-cookbooks` | General Claude usage patterns and recipes |
| `anthropics/courses` | Educational courses on Claude |

## Appendix C: Subagent Configuration Reference

### Built-in Subagents

| Agent | Model | Tools | Purpose |
|-------|-------|-------|---------|
| **Explore** | Haiku | Read-only | Codebase search/analysis (fast) |
| **Plan** | Inherited | Read-only | Plan mode research |
| **general-purpose** | Inherited | All | Complex multi-step tasks |
| **Bash** | Inherited | Bash | Terminal commands in separate context |

### Custom Subagent File Format

```yaml
---
name: code-reviewer
description: Expert code review specialist
tools: Read, Grep, Glob, Bash
disallowedTools: Write, Edit
model: sonnet
permissionMode: default
maxTurns: 50
skills:
  - api-conventions
  - error-handling
mcpServers:
  - slack
  - name: custom-server
    command: ./server.py
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./validate.sh"
memory: user
background: false
isolation: worktree
---

You are a senior code reviewer. When invoked, analyze code quality...
```

### Subagent Scope Precedence

| Location | Priority |
|----------|----------|
| `--agents` CLI flag | 1 (highest) |
| `.claude/agents/` | 2 |
| `~/.claude/agents/` | 3 |
| Plugin `agents/` | 4 (lowest) |

---

*End of Research Report*
