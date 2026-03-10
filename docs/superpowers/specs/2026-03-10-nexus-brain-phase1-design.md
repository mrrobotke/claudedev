# NEXUS Brain Phase 1: Foundation Design Spec

**Date**: 2026-03-10
**Status**: Approved (self-approved, I own this)
**Milestone**: v0.2.0-phase1-foundation
**Issues**: #1, #2, #3, #4, #5, #6

---

## Architecture

The NEXUS brain is a cognitive loop: **Perceive -> Recall -> Decide -> Act -> Observe -> Remember**.

Phase 1 builds the foundational substrate: configuration, working memory, episodic memory, Claude Code bridge, System 1 decision engine, and the Cortex orchestrator that ties them together.

### Module Dependency Graph

```
brain/config.py (BrainConfig)
brain/models.py (Task, TaskResult, Strategy, MemoryNode, EpisodicMemory)
    │
    ├── brain/memory/working.py (WorkingMemory)
    │       │
    │       └── brain/memory/episodic.py (EpisodicStore)
    │               │
    │               └── brain/decision/engine.py (DecisionEngine)
    │
    ├── brain/integration/claude_bridge.py (ClaudeBridge)
    │       │
    │       └── brain/integration/session.py (Session)
    │
    └── brain/cortex.py (Cortex - orchestrates all above)
```

### File Structure

```
src/claudedev/brain/
├── __init__.py
├── config.py            # BrainConfig frozen Pydantic model
├── cortex.py            # Cortex: main cognitive loop
├── models.py            # Shared domain models
├── memory/
│   ├── __init__.py      # MemoryStore protocol
│   ├── working.py       # WorkingMemory (slot-based, token-budgeted)
│   └── episodic.py      # EpisodicStore (async SQLite, keyword search)
├── decision/
│   ├── __init__.py
│   └── engine.py        # DecisionEngine (System 1 + delegate fallback)
└── integration/
    ├── __init__.py
    ├── claude_bridge.py # ClaudeBridge (Anthropic SDK wrapper)
    └── session.py       # Session management

tests/brain/
├── __init__.py
├── conftest.py          # Brain-specific fixtures
├── test_config.py
├── test_cortex.py
├── test_models.py
├── test_working_memory.py
├── test_episodic.py
├── test_claude_bridge.py
├── test_session.py
├── test_decision_engine.py
├── integration/
│   ├── __init__.py
│   └── test_phase1_integration.py
└── benchmarks/
    ├── __init__.py
    └── bench_brain_loop.py
```

---

## Module Specifications

### 1. BrainConfig (`config.py`)

Frozen Pydantic v2 model. All brain subsystems receive this at construction.

Fields:
- `project_path: str` — validated: must be non-empty
- `memory_dir: str = "~/.claudedev/memory"` — expanded via validator
- `max_working_memory_tokens: int = 180_000` — validated: 1000..500_000
- `embedding_model: str = "nomic-embed-text-v2"`
- `ollama_base_url: str = "http://localhost:11434"` — validated: URL format
- `claude_model: str = "claude-sonnet-4-20250514"`
- `system1_confidence_threshold: float = 0.85` — validated: 0.0..1.0
- `max_retries: int = 3` — validated: >= 0
- `log_level: str = "INFO"` — validated: must be valid log level

### 2. Shared Models (`models.py`)

- `Task` — id (UUID), description, type, domain, context_tags, created_at
- `TaskResult` — task_id, success, output, files_changed, tools_used, error, duration_ms, confidence
- `Strategy` — mode (system1|delegate), confidence, skill (optional), reason
- `MemoryNode` — id, content, source, timestamp, importance, memory_type, consolidated
- `Observation` — source, content, timestamp, prediction_error (optional)
- `Skill` — name, description, procedure, preconditions, reliability, task_signature, created_at

### 3. WorkingMemory (`memory/working.py`)

Token-budgeted context window manager with named slots.

- Slots: `task_context`, `code_context`, `history`, `recalled_memories`, `system_prompt`
- Critical slots (never pruned): `task_context`, `system_prompt`
- Token counting via tiktoken (cl100k_base encoding, cross-validated)
- Pruning strategy: lowest-priority non-critical slots removed first, then oldest content within slots
- Thread-safe: asyncio.Lock for mutations

Methods:
- `add_slot(name, content, priority)` → None
- `remove_slot(name)` → None
- `update_slot(name, content)` → None
- `get_context()` → str (assembled from all slots)
- `token_count()` → int
- `prune_to_budget()` → list[str] (names of pruned slots)
- `available_tokens()` → int
- `slot_info()` → dict[str, SlotInfo]

### 4. EpisodicStore (`memory/episodic.py`)

Async SQLite store for autobiographical task memories.

Schema:
```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    approach TEXT NOT NULL,
    outcome TEXT NOT NULL,
    tools_used TEXT DEFAULT '[]',       -- JSON array
    files_modified TEXT DEFAULT '[]',   -- JSON array
    error_messages TEXT DEFAULT '[]',   -- JSON array
    confidence REAL DEFAULT 0.5,
    timestamp TEXT NOT NULL,            -- ISO 8601
    consolidated INTEGER DEFAULT 0
);
CREATE INDEX idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX idx_episodes_consolidated ON episodes(consolidated);
```

Methods:
- `store(episode)` → str (UUID)
- `search(query, limit=20)` → list[EpisodicMemory] (keyword search via LIKE)
- `get_recent(limit=10)` → list[EpisodicMemory]
- `get_by_id(id)` → EpisodicMemory | None
- `get_unconsolidated(limit=100)` → list[EpisodicMemory]
- `update(episode)` → None
- `count()` → int

WAL mode enabled. Connection pool with proper lifecycle management.

### 5. ClaudeBridge (`integration/claude_bridge.py`)

Wraps `anthropic.Anthropic()` for brain-to-Claude communication.

- `execute_task(task, system_prompt, allowed_tools, max_turns)` → ClaudeResult
- `ClaudeResult`: content, usage (input/output tokens), stop_reason, tool_use_history, duration_ms
- Error handling: 400 (bad request), 401 (auth), 403 (forbidden), 429 (rate limit with exp backoff + jitter), 500 (server error with retry), timeout, context overflow (truncate + retry)
- Streaming support via async generator
- System prompt injection merges brain context with base prompt

### 6. Session (`integration/session.py`)

Session lifecycle for multi-turn interactions.

- `Session`: id, bridge_ref, conversation_history, created_at, last_active
- `create()` → Session
- `resume(session_id)` → Session
- `add_turn(role, content)` → None
- `get_history()` → list[dict]
- `is_expired(ttl_minutes)` → bool

### 7. DecisionEngine (`decision/engine.py`)

System 1 (fast) + delegate (fallback) decision making.

- `decide(task, context, memories)` → Strategy
- System 1: scan procedural memories for matching skills above confidence threshold
- Delegate: when no skill matches or confidence < threshold, hand off entirely to Claude
- Decision logging: every decision recorded with mode, confidence, skill, reason, timestamp
- Ambiguous match resolution: highest reliability wins

### 8. Cortex (`cortex.py`)

The brain. Orchestrates the full cognitive cycle.

```python
async def run(self, task: Task) -> TaskResult:
    context = await self.perceive(task)      # Build working memory context
    memories = await self.recall(task)        # Search episodic memory
    strategy = await self.decide(task, context, memories)  # System 1 or delegate
    result = await self.act(strategy)         # Execute via Claude bridge
    await self.remember(task, result)         # Store episode
    return result
```

- Structured logging at every step
- Never crashes — always returns TaskResult (success=False on error)
- Latency target: <100ms excluding Claude API call

---

## Dependencies to Add

```toml
tiktoken = ">=0.9.0"   # Token counting (cross-validated accuracy)
```

---

## Quality Requirements

- ruff check . — zero warnings
- mypy --strict — zero errors
- pytest — all pass
- Coverage: >80% overall, >85% for bridge/decision, >90% for memory
- No commit signatures
- Python Zen: every principle enforced
- Edge cases: empty, null, boundary, concurrent, special chars, oversized
- Security: no secrets, validate boundaries, no injection
