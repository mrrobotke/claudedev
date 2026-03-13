# Implementation Infrastructure & Live Steering Design

> **For agentic workers:** This is the specification document. Use `superpowers:writing-plans` to create the implementation plan.

**Goal:** Add worktree-based isolation, PR enforcement, webhook-driven cleanup, live session streaming, and human steering via Claude Code hooks — all integrated with the NEXUS brain architecture.

**Architecture:** Five interconnected subsystems that transform ClaudeDev from a fire-and-forget executor into an observable, steerable autonomous development platform. The hook-based steering system feeds into NEXUS working memory, making the brain natively aware of human directives.

**Tech Stack:** Python 3.13, FastAPI, WebSockets, Claude Code hooks (HTTP), asyncio queues, SQLAlchemy async + PostgreSQL, structlog

---

## Section 1: Worktree Management, PR Enforcement & Webhook Cleanup

### 1.1 WorktreeManager Module

**File:** `src/claudedev/engines/worktree_manager.py`

Manages git worktree lifecycle for isolated issue implementations.

```
WorktreeManager
├── create_worktree(repo_path, issue_number, base_branch) -> WorktreeInfo
├── cleanup_worktree(repo_path, issue_number) -> bool
├── get_worktree_path(repo_path, issue_number) -> Path | None
├── list_worktrees(repo_path) -> list[WorktreeInfo]
└── cleanup_merged_worktrees(repo_path) -> int
```

**Worktree Layout:**
```
{repo_path}/
└── .claudedev/
    └── worktrees/
        ├── issue-42/    ← git worktree on branch claudedev/issue-42
        ├── issue-87/    ← git worktree on branch claudedev/issue-87
        └── issue-103/   ← git worktree on branch claudedev/issue-103
```

**Implementation Details:**
- Uses `asyncio.create_subprocess_exec` for git commands (non-blocking)
- Branch naming: `claudedev/issue-{N}` (created from repo's default branch)
- Worktree path: `{repo_path}/.claudedev/worktrees/issue-{N}/`
- Creates `.claudedev/` directory if not exists, adds to `.gitignore` if not already there
- Validates repo path exists and is a git repo before operations
- Returns `WorktreeInfo` dataclass: `path`, `branch`, `issue_number`, `created_at`

**Error Handling:**
- If worktree already exists for issue, return existing path (idempotent)
- If branch already exists remotely, fetch and use it
- If git command fails, raise `WorktreeError` with stderr details
- Cleanup is safe: `git worktree remove --force` + `git branch -D` (local only)

### 1.2 PR Enforcement in TeamEngine

**File:** `src/claudedev/engines/team_engine.py` (modify existing)

Current gap: If Claude doesn't create a PR, the issue is silently marked DONE. Fix:

**After Claude execution completes:**
1. Extract PR number from Claude's output (existing `_extract_pr_number()`)
2. If no PR found, check GitHub API for open PRs on branch `claudedev/issue-{N}`
3. If still no PR, **create one automatically** via `gh pr create` or GitHub API:
   - Title: `fix: resolve issue #{N} - {issue_title_first_60_chars}`
   - Body: Auto-generated from Claude's session summary
   - Base: repo's default branch
   - Head: `claudedev/issue-{N}`
   - Labels: `claudedev`, `automated`
4. If PR creation also fails (e.g., no commits on branch), mark issue as `FAILED` not `DONE`
5. Store `pr_number` on TrackedIssue and create TrackedPR record

**Integration with WorktreeManager:**
- Before spawning Claude, call `WorktreeManager.create_worktree()`
- Pass worktree path as `cwd` to Claude subprocess
- Claude operates entirely within the worktree (isolated from main branch)

### 1.3 Database Schema Addition

**Table:** `tracked_issues` — add column:
```sql
worktree_path VARCHAR(500) DEFAULT NULL
```

**Model update in `state.py`:**
```python
class TrackedIssue(Base):
    # ... existing fields ...
    worktree_path: Mapped[str | None] = mapped_column(String(500), default=None)
```

### 1.4 Webhook-Driven Worktree Cleanup

**File:** `src/claudedev/github/webhook_server.py` (modify existing)

On `pull_request` webhook events with `action` in (`merged`, `closed`):
1. Match PR to TrackedPR by `pr_number` + `repo_id`
2. Look up associated TrackedIssue
3. If `worktree_path` is set, call `WorktreeManager.cleanup_worktree()`
4. Clear `worktree_path` on the TrackedIssue record
5. Log cleanup result

On `issues` webhook events with `action` == `closed`:
1. Match to TrackedIssue
2. If issue has a worktree and no open PR, clean up the worktree
3. If issue has an open PR, leave worktree (PR merge will clean it up)

**Safety:** Never clean up a worktree that has uncommitted changes. Check `git status` first and warn in logs if dirty.

---

## Section 2: Hook-Based Steering Architecture

### 2.1 Per-Worktree Hook Configuration

When `WorktreeManager.create_worktree()` runs, it writes a `.claude/settings.json` inside the worktree:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "type": "http",
        "url": "http://127.0.0.1:8787/api/hooks/post-tool-use",
        "headers": {
          "X-Session-Id": "{{SESSION_ID}}",
          "X-Issue-Number": "{{ISSUE_NUMBER}}"
        },
        "timeout": 5000
      }
    ],
    "Stop": [
      {
        "type": "http",
        "url": "http://127.0.0.1:8787/api/hooks/stop",
        "headers": {
          "X-Session-Id": "{{SESSION_ID}}",
          "X-Issue-Number": "{{ISSUE_NUMBER}}"
        },
        "timeout": 10000
      }
    ],
    "PreToolUse": [
      {
        "type": "http",
        "url": "http://127.0.0.1:8787/api/hooks/pre-tool-use",
        "headers": {
          "X-Session-Id": "{{SESSION_ID}}",
          "X-Issue-Number": "{{ISSUE_NUMBER}}"
        },
        "timeout": 5000
      }
    ]
  }
}
```

**Template substitution:** `WorktreeManager` replaces `{{SESSION_ID}}` and `{{ISSUE_NUMBER}}` with actual values at creation time.

### 2.2 SteeringManager

**File:** `src/claudedev/engines/steering_manager.py`

Manages per-session steering message queues and hook response logic.

```
SteeringManager
├── register_session(session_id: str) -> None
├── unregister_session(session_id: str) -> None
├── enqueue_message(session_id: str, message: str, directive_type: str) -> None
├── get_pending_directive(session_id: str) -> SteeringDirective | None
├── handle_post_tool_use(session_id: str, hook_payload: dict) -> dict
├── handle_stop(session_id: str, hook_payload: dict) -> dict
├── handle_pre_tool_use(session_id: str, hook_payload: dict) -> dict
└── get_session_activity(session_id: str) -> list[ActivityEvent]
```

**SteeringDirective model:**
```python
class DirectiveType(StrEnum):
    PIVOT = "pivot"        # Change approach entirely
    CONSTRAIN = "constrain"  # Add a rule/constraint
    INFORM = "inform"      # Provide additional context
    ABORT = "abort"        # Stop implementation

class SteeringDirective(BaseModel):
    session_id: str
    message: str
    directive_type: DirectiveType
    timestamp: datetime
    acknowledged: bool = False
```

**Queue Mechanics:**
- Each session gets an `asyncio.Queue[SteeringDirective]` on registration
- `enqueue_message()` puts a directive on the queue (called by WebSocket handler)
- `get_pending_directive()` does a non-blocking `get_nowait()` — returns `None` if empty
- Multiple messages queue up and are delivered one-per-hook-cycle (FIFO)

### 2.3 Hook API Endpoints

**File:** `src/claudedev/github/webhook_server.py` (or new `src/claudedev/api/hooks.py`)

#### POST `/api/hooks/post-tool-use`

Called by Claude Code after every tool use (~50-200 times per implementation).

**Request:** Claude Code hook payload (tool name, result summary, session context)
**Response logic:**
1. Read `X-Session-Id` from headers
2. Call `SteeringManager.get_pending_directive(session_id)`
3. If directive exists:
   - For `PIVOT`/`CONSTRAIN`/`INFORM`: Return `{"additionalContext": "<formatted directive>"}`
   - The `additionalContext` becomes a system message in Claude's next turn
4. If no directive: Return `{}` (no-op, minimal latency)

**additionalContext format:**
```
[CLAUDEDEV STEERING - {directive_type.upper()}]
From the project owner: {message}
You MUST acknowledge this directive and adjust your approach accordingly.
```

#### POST `/api/hooks/stop`

Called when Claude finishes its current task or conversation turn.

**Response logic:**
1. Check for pending directives
2. If `ABORT` directive: Return `{"decision": "approve"}` (let Claude stop)
3. If `PIVOT`/`CONSTRAIN` directive: Return `{"decision": "block", "reason": "<directive>"}` — this restarts Claude with the directive as its new instruction
4. If no directive: Return `{"decision": "approve"}`

**Loop prevention:** Track `stop_hook_active` flag per session. If the Stop hook fires and `stop_hook_active` is already true, always approve to prevent infinite block loops.

#### POST `/api/hooks/pre-tool-use`

Called before Claude executes a tool. Used for safety guardrails.

**Response logic:**
1. Check if an `ABORT` directive is pending
2. If abort: Return `{"permissionDecision": "deny", "reason": "Implementation aborted by project owner"}` for destructive tools
3. Otherwise: Return `{}` (allow all tools)

### 2.4 Activity Tracking

Every hook invocation is logged as an `ActivityEvent`:

```python
class ActivityEvent(BaseModel):
    session_id: str
    timestamp: datetime
    event_type: str  # "tool_use", "steering_sent", "steering_ack", "stop", "abort"
    tool_name: str | None = None
    details: dict = {}
```

These events feed the live session view's tool activity panel.

---

## Section 3: Live Session Streaming & Web Interface

### 3.1 WebSocketManager

**File:** `src/claudedev/engines/websocket_manager.py`

Manages WebSocket connections for live session output streaming.

```
WebSocketManager
├── register_subscriber(session_id: str, ws: WebSocket) -> None
├── unregister_subscriber(session_id: str, ws: WebSocket) -> None
├── broadcast_output(session_id: str, line: str) -> None
├── broadcast_activity(session_id: str, event: ActivityEvent) -> None
├── broadcast_steering_ack(session_id: str, directive: SteeringDirective) -> None
└── get_subscriber_count(session_id: str) -> int
```

**Design:**
- Per-session subscriber sets: `dict[str, set[WebSocket]]`
- `broadcast_*` methods iterate subscribers and send JSON messages
- Dead connections detected on send failure, auto-removed from set
- Thread-safe via `asyncio.Lock` per session

**Message Types (JSON over WebSocket):**
```json
{"type": "output", "data": "line of Claude's stdout", "timestamp": "..."}
{"type": "activity", "data": {"tool": "Read", "file": "src/foo.py"}, "timestamp": "..."}
{"type": "steering_ack", "data": {"message": "...", "directive_type": "pivot"}, "timestamp": "..."}
{"type": "session_end", "data": {"status": "completed", "summary": "..."}, "timestamp": "..."}
```

### 3.2 WebSocket Endpoints

#### WS `/ws/session/{session_id}/stream`

Read-only stream of session output and activity.

**On connect:** Add to `WebSocketManager` subscribers. Send buffered recent output (last 100 lines) for late joiners.
**On message:** Ignore (read-only endpoint).
**On disconnect:** Remove from subscribers.

#### WS `/ws/session/{session_id}/steer`

Bidirectional endpoint for sending steering messages and receiving acknowledgments.

**On connect:** Validate session exists and is active.
**On message (from client):**
```json
{"message": "Switch to using Redis instead of in-memory cache", "directive_type": "pivot"}
```
Parse and call `SteeringManager.enqueue_message()`.

**On message (to client):** Steering acknowledgment when Claude processes the directive.

### 3.3 stdout Capture Enhancement

**File:** `src/claudedev/integrations/claude_sdk.py` (modify existing)

Current `_run_query_cli()` reads stdout line-by-line. Enhance:

1. Accept optional `session_id` parameter
2. After reading each line, call `WebSocketManager.broadcast_output(session_id, line)` if session_id provided
3. Buffer last 100 lines in a per-session ring buffer for late WebSocket joiners
4. Parse tool-use markers from Claude's output to generate `ActivityEvent` objects

**Tool detection heuristic:** Claude Code outputs structured markers like `⏵ Read file.py` or `⏵ Edit src/main.py`. Parse these for tool name and target, broadcast as activity events.

### 3.4 Live Session Page

**File:** `src/claudedev/ui/live_session.py`

A dedicated HTML page served at `/session/{session_id}/live`.

**Three-Panel Layout:**

```
┌──────────────────────────────────────────────────────┐
│  Live Session: Issue #42 — claudedev/issue-42        │
│  Status: ● Running   Duration: 12m 34s              │
├────────────────────────────┬─────────────────────────┤
│                            │  Tool Activity           │
│  Terminal Output           │  ├─ Read src/auth.py     │
│  (scrolling, monospace)    │  ├─ Edit src/auth.py     │
│                            │  ├─ Bash: pytest         │
│  > Reading src/auth.py...  │  ├─ Read src/models.py   │
│  > Analyzing auth flow...  │  └─ Write src/jwt.py     │
│  > Writing tests...        │                          │
│                            │─────────────────────────│
│                            │  Steering                │
│                            │  ┌─────────────────────┐│
│                            │  │ Type message...     ▸││
│                            │  └─────────────────────┘│
│                            │  [pivot][constrain]      │
│                            │  [inform][abort]         │
│                            │                          │
│                            │  History:                │
│                            │  ✓ "Use JWT not sessions"│
│                            │    (pivot, 3m ago)       │
└────────────────────────────┴─────────────────────────┘
```

**Implementation:**
- Self-contained HTML template (inline CSS + JS, same pattern as existing dashboard)
- Connects to both WebSocket endpoints on load
- Terminal panel: auto-scrolling `<pre>` with ANSI color support via a lightweight JS parser
- Tool activity panel: timestamped list, auto-scrolling, color-coded by tool type
- Steering panel: text input + directive type buttons, history of sent directives with acknowledgment status
- Session status: polling `/api/session/{session_id}/status` every 5s for duration and status updates

**Navigation:**
- Linked from dashboard's issue detail modal (new "Watch Live" button when session is active)
- Direct URL: `/session/{session_id}/live`
- Returns to dashboard when session ends (with summary)

---

## Section 4: NEXUS Brain Integration

### 4.1 Working Memory Steering Slot

**File:** `src/claudedev/brain/memory/working.py` (modify existing)

Add a dedicated steering slot to the slot-based working memory system:

```python
STEERING_SLOT = "steering_directive"
STEERING_PRIORITY = Priority.HIGH  # 80 — above task context, below system constraints
```

**Slot behavior:**
- Written by `SteeringManager` when a directive arrives during a cognitive cycle
- Read by `Cortex._assemble_context()` and included in the next prompt
- **Consumed after one cycle** — the slot is cleared after the cortex processes it
- This ensures steering is ephemeral: it influences the current decision without permanently polluting the context window

**Content format:**
```python
SteeringSlotContent(BaseModel):
    session_id: str
    message: str
    directive_type: DirectiveType  # pivot, constrain, inform, abort
    timestamp: datetime
    source: str = "human"  # For future: could be "metacognitive" or "automated"
```

### 4.2 Cortex `_observe()` Enhancement

**File:** `src/claudedev/brain/cortex.py` (modify existing)

The `_observe()` method is currently a Phase 1 stub. Enhance it to process steering:

```python
async def _observe(self, task: Task) -> Observation:
    """Phase 2 enhancement: Check for steering directives."""
    steering = await self.working_memory.get_slot(STEERING_SLOT)

    if steering is None:
        return Observation(has_steering=False)

    directive = SteeringSlotContent.model_validate_json(steering.content)

    return Observation(
        has_steering=True,
        directive_type=directive.directive_type,
        directive_message=directive.message,
    )
```

**Cognitive cycle adjustment based on directive type:**
- `PIVOT`: Skip current `_decide()` output. Re-enter decision phase with the pivot as a new constraint.
- `CONSTRAIN`: Inject the constraint into the next `_act()` call's system prompt. Continue current plan.
- `INFORM`: Append to episodic context as additional information. Continue current plan.
- `ABORT`: Raise `SteeringAbort` exception to cleanly terminate the cognitive cycle.

### 4.3 Episodic Memory for Steering Events

**File:** `src/claudedev/brain/memory/episodic.py` (modify existing)

Every steering interaction becomes an episodic memory for future learning:

```python
EpisodicMemory(
    task=f"Steering: {directive_type} on issue #{issue_number}",
    approach=f"User directed: {message_summary}",
    outcome="applied" | "acknowledged" | "rejected_incompatible",
    tools_used=["steering_hook"],
    confidence=1.0,  # Human directives are ground truth
)
```

**Learning pathway (future phases):**
- Over time, accumulated steering episodes enable pattern detection
- Example: "When implementing auth features, user frequently steers toward JWT over sessions"
- Future: Decision engine can preemptively adopt preferred patterns (episodic → semantic consolidation)
- This is the NEXUS Dreaming timescale's consolidation pathway

### 4.4 Observation Model Addition

**File:** `src/claudedev/brain/models.py` (modify existing)

```python
class Observation(BaseModel):
    """Result of the _observe() phase — perception of current state."""

    has_steering: bool = False
    directive_type: DirectiveType | None = None
    directive_message: str | None = None
    environment_signals: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)
```

### 4.5 Predictive Coding Hooks (Future-Ready)

The design leaves integration points for Phase 2's predictive coding loop:

- **Prediction**: Before each cognitive cycle, cortex predicts whether steering will occur (based on task complexity, issue type, historical steering frequency)
- **Prediction Error**: If steering arrives when none was predicted (or vice versa), the error signal adjusts future predictions
- **Metacognitive Signal**: High steering frequency on a task type signals the brain to request human input proactively on similar future tasks

These are NOT implemented now but the data structures and slot architecture support them without modification.

---

## Data Flow Summary

```
User types steering message in live session page
    │
    ▼
WebSocket /ws/session/{id}/steer
    │
    ▼
SteeringManager.enqueue_message()
    │ (asyncio.Queue per session)
    ▼
Next PostToolUse hook fires (within ~seconds)
    │
    ▼
/api/hooks/post-tool-use reads queue
    │
    ├── Returns {additionalContext: "..."}
    │   to Claude Code
    │
    ├── Broadcasts steering_ack via WebSocket
    │   to live session page
    │
    └── Writes to NEXUS working memory
        steering_directive slot
            │
            ▼
        Cortex._observe() reads slot
            │
            ▼
        Cognitive cycle adjusts behavior
            │
            ▼
        EpisodicMemory records the event
```

## Cross-Cutting Concerns

### Error Resilience
- Hook endpoints MUST respond within timeout (5s for PostToolUse, 10s for Stop)
- If SteeringManager is unavailable, hooks return `{}` (no-op) — never block Claude
- WebSocket disconnections are handled gracefully with auto-reconnect on client side
- Worktree operations are idempotent and safe to retry

### Observability
- All hook invocations logged via structlog with session_id, tool_name, latency
- Steering events logged at INFO level with directive content
- WebSocket connection counts tracked for monitoring
- Worktree lifecycle events logged (create, cleanup, error)

### Security
- Hook endpoints validate `X-Session-Id` header against registered sessions
- WebSocket endpoints validate session existence before accepting connection
- Steering messages are sanitized (max length, no injection of system prompt markers)
- Worktree cleanup validates ownership before removing

### Performance
- PostToolUse hook response target: <50ms (critical path — fires after every tool)
- WebSocket broadcast is fire-and-forget (non-blocking)
- Activity events buffered and batched for WebSocket delivery
- Worktree operations are async subprocess calls (non-blocking)
