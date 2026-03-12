# AutoResponder + Thinking Layer Design

## Goal

When Claude Code stops mid-implementation to ask a question (approach choice, confirmation, missing info), ClaudeDev detects this in real-time via stream analysis, thinks autonomously using Opus 4.6, and resumes the session with a decisive answer. No human in the loop. Full autonomy with guardrails.

## Context

- Issue #251 demonstrated the problem: Claude invoked the brainstorming skill, asked "which approach?", and waited for input that never came in `-p` mode
- This is the precursor to full Product Owner mode (Issue #14, Phase 3)
- Maps to the `AutoResponder` class and `Session Resume` method from V02_AI_BRAIN_ARCHITECTURE.md

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Thinking model | Opus 4.6 (Anthropic API) | Maximum reasoning quality, same subscription |
| Local models | Ollama for embeddings only | 16GB Mac limits local model viability for reasoning |
| Response method | Session resume (`--resume`) | Zero wasted work, Claude picks up where it left off |
| Autonomy level | Full autonomy with guardrails | Answers everything, logs all decisions, flags high-risk |
| Context for decisions | Issue + codebase + episodic memory | Full NEXUS integration, wires Phase 1 episodic store |
| Detection method | Stream analysis (real-time) | Detect `stop_reason: null` during stream-json output |

## Architecture

### Component Diagram

```
team_engine.py (streaming loop)
    │
    ├── StreamAnalyzer ← consumes stream-json events
    │       │
    │       └── QUESTION DETECTED (stop_reason: null, no PR, interrogative output)
    │               │
    │               ├── QuestionClassifier → type + risk score
    │               │
    │               ├── AutoResponder → Opus 4.6 via ClaudeBridge
    │               │       │
    │               │       ├── Issue context (body, enhancement, comments)
    │               │       ├── Codebase context (key files, max 50K tokens)
    │               │       └── Episodic memory (past decisions, top 3 relevant)
    │               │
    │               ├── DecisionLogger → episodic store + dashboard WebSocket + structlog
    │               │
    │               └── claude --resume <session_id> -p "<answer>"
    │                       │
    │                       └── Continue streaming (loop up to 5 times)
    │
    └── Normal completion → PR extraction, status update
```

### Detection Flow

```
Claude -p (stream-json)              ClaudeDev AutoResponder
─────────────────────────────────    ───────────────────────
│ streaming events...              │
│ {"type":"assistant","message":…} │──→ StreamAnalyzer accumulates
│ {"type":"tool_use","tool":…}     │──→ StreamAnalyzer tracks tool use
│ {"type":"result","stop_reason":  │
│   null}                          │──→ QUESTION DETECTED
│                                  │
│ [process exits]                  │    QuestionClassifier → type + risk
│                                  │    AutoResponder → Opus 4.6 thinks
│                                  │    DecisionLogger → log + broadcast
│                                  │
│ claude --resume <id> -p "answer" │←── Resume with decision
│ streaming events...              │──→ StreamAnalyzer continues
│ {"type":"result","stop_reason":  │
│   "end_turn"}                    │──→ NORMAL COMPLETION
```

## Components

### 1. StreamAnalyzer (`brain/autoresponder/stream_analyzer.py`)

Consumes stream-json events in real-time. Maintains state:

- `accumulated_text: str` — all assistant text blocks concatenated
- `last_stop_reason: str | None` — from the most recent result event
- `has_tool_use: bool` — whether any tool_use events were seen
- `has_commits: bool` — whether git commit activity was detected
- `pr_number: int | None` — extracted PR number if found

Detection heuristics (all must be true for question detection):
1. Result event has `stop_reason` of `null`, empty, or missing
2. No `PR_NUMBER:` metadata line in accumulated text
3. Last assistant text contains interrogative patterns (ends with `?`, contains "would you", "should I", "which approach", "do you want", etc.)

Returns `DetectedQuestion` dataclass:
- `question_text: str` — the extracted question
- `full_context: str` — all accumulated assistant output
- `claude_session_id: str` — for resume

### 2. AutoResponder (`brain/autoresponder/auto_responder.py`)

Receives `DetectedQuestion`, assembles context, calls Opus 4.6 via `ClaudeBridge`.

Context assembly (capped at 50K tokens total):
- Issue body + enhancement analysis (~5K tokens)
- Relevant codebase files (architecture docs, files mentioned in issue) (~30K tokens)
- Episodic memory recall: top 3 past decisions matching issue keywords (~5K tokens)
- Claude's question + accumulated context (~10K tokens)

Opus prompt template:
```
You are the autonomous Product Owner for ClaudeDev. A Claude Code session
implementing GitHub issue #{number} has stopped with a question.

ISSUE: {title} — {body}
ENHANCEMENT: {enhancement_analysis}
CODEBASE CONTEXT: {relevant_files_summary}
PAST DECISIONS: {episodic_memories}

Claude's question: "{extracted_question}"
Question type: {classification}

Respond with a clear, decisive answer. Do NOT ask follow-up questions.
Choose the approach that best fits:
- Project conventions and existing patterns
- The issue requirements
- Past decisions that worked

Format:
DECISION: <your answer in 1-3 sentences>
REASONING: <why, in 1-2 sentences>
RISK: <1-10>
```

Returns `AutoResponse`:
- `answer: str` — the decision text to send via resume
- `reasoning: str` — why this decision was made
- `risk_score: int` — 1-10
- `decision_type: QuestionType` — from classifier
- `thinking_tokens: int` — tokens used for this decision
- `thinking_duration_ms: float` — latency

### 3. QuestionClassifier (`brain/autoresponder/question_classifier.py`)

Classifies detected questions by type and risk. Lightweight — uses pattern matching first, falls back to Opus for ambiguous cases.

Question types (from V02 architecture `AutoResponder`):
- `confirmation` — "Should I proceed?" (risk: 2-4)
- `choice` — "Approach A or B?" (risk: 4-7)
- `missing_info` — "What should the function name be?" (risk: 3-5)
- `permission` — "Can I modify this file?" (risk: 2-3)
- `scope_expansion` — "Should I also refactor X?" (risk: 7-9)
- `architecture` — "Which database/pattern/library?" (risk: 6-8)

Risk scoring:
- Base risk from question type
- +1 if question mentions "delete", "remove", "drop", "migration"
- +1 if question mentions files outside the issue scope
- +2 if question involves adding new dependencies

### 4. DecisionLogger (`brain/autoresponder/decision_logger.py`)

Writes every auto-decision to three destinations:

1. **Episodic memory** — `EpisodicStore.store()` with task_type="auto_decision", recording question, answer, risk, and outcome (updated later when session completes)
2. **Dashboard WebSocket** — new events: `auto_response_thinking`, `auto_response_decision`, `auto_response_resumed`
3. **structlog** — structured log with all decision fields for audit trail

High-risk decisions (risk 7+) get a special flag that appears in:
- The PR description (auto-appended section: "Autonomous Decisions Made")
- The dashboard issue detail page (amber highlight)

## Integration Changes

### BrainConfig (`brain/config.py`) — New Fields

```python
thinking_model: str = "claude-opus-4-6"
max_auto_responses: int = 5
auto_respond_enabled: bool = True
max_thinking_tokens: int = 50_000
```

### ClaudeSDKClient (`integrations/claude_sdk.py`) — New Method

```python
async def resume_session(
    self, session_id: str, prompt: str, cwd: str,
    output_format: str = "stream-json", **kwargs
) -> AsyncIterator[str]:
    """Resume a Claude Code session with a follow-up prompt."""
    cmd = [claude_path, "--resume", session_id, "-p", prompt,
           "--output-format", output_format]
    if output_format == "stream-json":
        cmd.append("--verbose")
    # ... same subprocess streaming logic as _run_query_cli
```

### TeamEngine (`engines/team_engine.py`) — Auto-Respond Loop

The `run_implementation` method gains an outer loop:

```python
stream_analyzer = StreamAnalyzer()
auto_responder = AutoResponder(brain_config, claude_bridge, episodic_store)
decision_logger = DecisionLogger(episodic_store, ws_manager)

for attempt in range(brain_config.max_auto_responses + 1):
    async for chunk in claude_client.run_query(...):  # or resume_session
        stream_analyzer.feed(chunk)
        # ... existing streaming + WebSocket broadcast logic

    if not stream_analyzer.detected_question():
        break  # Normal completion

    question = stream_analyzer.get_question()
    classification = QuestionClassifier.classify(question)
    response = await auto_responder.respond(question, tracked, session, classification)
    decision_logger.log(response)

    # Reset analyzer for next stream, keep accumulated context
    stream_analyzer.reset_for_resume()
    claude_session_id = stream_analyzer.claude_session_id
    # Next iteration will use resume_session instead of run_query
```

### Episodic Memory Wiring

The existing `brain/memory/episodic.py` (Phase 1, already implemented) provides:
- `store(episode)` — save a decision
- `search(query, limit)` — keyword recall
- `get_recent(limit)` — recent episodes

AutoResponder calls `episodic_store.search(issue_keywords + question_text, limit=3)` to pull relevant past decisions before thinking.

## Dashboard Visibility

New WebSocket events for the live session page:
- `auto_response_thinking` — brain is analyzing (shows spinner in terminal sidebar)
- `auto_response_decision` — brain decided (shows decision card with risk badge)
- `auto_response_resumed` — session resumed (terminal continues streaming)

Decision audit section on issue detail page:
- List of all auto-decisions made during the session
- Each shows: question, decision, risk score (color-coded), reasoning
- High-risk (7+) decisions highlighted amber

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/claudedev/brain/autoresponder/__init__.py` | Create | Package exports |
| `src/claudedev/brain/autoresponder/stream_analyzer.py` | Create | Real-time question detection |
| `src/claudedev/brain/autoresponder/auto_responder.py` | Create | Opus 4.6 thinking + answers |
| `src/claudedev/brain/autoresponder/question_classifier.py` | Create | Question type + risk scoring |
| `src/claudedev/brain/autoresponder/decision_logger.py` | Create | Episodic + dashboard + structlog |
| `src/claudedev/brain/config.py` | Modify | Add thinking_model, max_auto_responses, etc. |
| `src/claudedev/integrations/claude_sdk.py` | Modify | Add resume_session() method |
| `src/claudedev/engines/team_engine.py` | Modify | Wire auto-respond loop |
| `tests/brain/test_stream_analyzer.py` | Create | Detection logic tests |
| `tests/brain/test_auto_responder.py` | Create | Thinking + response tests |
| `tests/brain/test_question_classifier.py` | Create | Classification tests |
| `tests/brain/test_decision_logger.py` | Create | Logging tests |
| `tests/test_resume_session.py` | Create | Resume CLI integration tests |

## Testing Strategy

- Unit tests for each component with mocked dependencies
- StreamAnalyzer: feed real stream-json from Session 41 (issue #251) and verify question detection
- AutoResponder: mock ClaudeBridge, verify prompt assembly and response parsing
- QuestionClassifier: parametric tests for each question type
- Integration test: mock the full loop (stream → detect → think → resume → complete)
- Edge cases: no question detected, max retries hit, Opus API failure, empty resume output

## Success Criteria

- Issue #251 (or similar) runs to completion without human intervention
- All auto-decisions visible in dashboard with risk scores
- High-risk decisions flagged in PR description
- Max 5 auto-response loops per session (prevents infinite loops)
- Episodic memory stores decisions for future recall
- All tests pass, ruff clean, mypy clean
