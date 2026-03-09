# OpenHands (OpenClaw) Deep Technical Analysis
## Competitive Intelligence Report -- March 9, 2026

**Repo**: https://github.com/All-Hands-AI/OpenHands (redirects to github.com/OpenHands/OpenHands)
**Stars**: 68,808 | **Forks**: 8,605 | **Primary Language**: Python
**V1 SDK**: https://github.com/OpenHands/software-agent-sdk (564 stars)
**Topics**: agent, artificial-intelligence, llm, chatgpt, claude-ai, cli, developer-tools

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [SOUL.md Equivalent -- Core Prompt System](#3-soul-equivalent--core-prompt-system)
4. [Memory System](#4-memory-system)
5. [Agent Architecture](#5-agent-architecture)
6. [Brain / Reasoning System](#6-brain--reasoning-system)
7. [Integration Architecture](#7-integration-architecture)
8. [V0 to V1 Migration](#8-v0-to-v1-migration)
9. [Weaknesses and Gaps](#9-weaknesses-and-gaps)
10. [Competitive Opportunities](#10-competitive-opportunities)

---

## 1. Executive Summary

OpenHands is the most popular open-source AI coding agent (69K stars). It is in the midst of a
major architecture migration from V0 (monolithic Python codebase) to V1 (modular SDK-based
architecture). The V0 code is tagged as legacy and scheduled for removal April 1, 2026. The V1
replacement is the `software-agent-sdk` repo with a clean modular structure.

**Key Findings**:

- **No SOUL.md**: OpenHands does not have a single "soul" file. Its personality is distributed
  across multiple Jinja2 prompt templates with role-specific content.
- **Memory is Event-Stream-Based**: No vector stores, no embeddings. Memory is purely sequential
  event history with condenser strategies for compression.
- **Single Primary Agent**: The CodeAct agent dominates. Other agents (BrowsingAgent, ReadonlyAgent)
  are secondary/delegated.
- **Microagent System**: Keyword-triggered expertise injection via markdown files -- their version
  of specialized knowledge.
- **Stuck Detection**: Sophisticated loop detection (5 scenarios) but reactive, not proactive.
- **No Planning Engine**: No tree-of-thought, no strategic planning beyond a task tracker tool.
  Planning is entirely LLM-driven through prompt instructions.

---

## 2. Architecture Overview

```
+-----------------------------------------------------------------------+
|                         OpenHands V0 Architecture                      |
+-----------------------------------------------------------------------+
|                                                                       |
|  +-------------+     +------------------+     +-------------------+   |
|  | User Input  |---->| Agent Controller |---->| CodeAct Agent     |   |
|  | (CLI/Web)   |     | (State Machine)  |     | (Primary Agent)   |   |
|  +-------------+     +------------------+     +-------------------+   |
|                             |                        |                |
|                             v                        v                |
|                    +------------------+     +-------------------+     |
|                    | State / History  |     | LLM (via LiteLLM) |     |
|                    | (Event Stream)   |     | (Multi-provider)  |     |
|                    +------------------+     +-------------------+     |
|                             |                        |                |
|                             v                        v                |
|                    +------------------+     +-------------------+     |
|                    | Memory System    |     | Tool System       |     |
|                    | (Condensers)     |     | (Function Calls)  |     |
|                    +------------------+     +-------------------+     |
|                             |                        |                |
|                             v                        v                |
|                    +------------------+     +-------------------+     |
|                    | Microagent       |     | Runtime           |     |
|                    | System           |     | (Docker/Local/K8s)|     |
|                    +------------------+     +-------------------+     |
|                                                                       |
+-----------------------------------------------------------------------+

+-----------------------------------------------------------------------+
|                         OpenHands V1 Architecture                      |
+-----------------------------------------------------------------------+
|                                                                       |
|  openhands-sdk       openhands-tools      openhands-agent-server      |
|  +-------------+     +---------------+    +---------------------+     |
|  | Agent Core  |     | Terminal      |    | REST API Server     |     |
|  | Context     |     | File Editor   |    | WebSocket Handler   |     |
|  | Conversation|     | Browser Use   |    | Conversation Router |     |
|  | Event System|     | Glob/Grep     |    | Skills Service      |     |
|  | Condenser   |     | Apply Patch   |    | Desktop Service     |     |
|  | LLM Layer   |     | Task Tracker  |    | Git Router          |     |
|  | Security    |     | Planning File |    | Terminal Service     |     |
|  | Subagent    |     | Delegate      |    | VSCode Service      |     |
|  | Skills      |     | Gemini Tools  |    | Pub/Sub             |     |
|  | Plugins     |     | Tom Consult   |    | Webhook Subscriber  |     |
|  | Critic      |     | Presets       |    | Hooks               |     |
|  +-------------+     +---------------+    +---------------------+     |
|                                                                       |
|  openhands-workspace                                                  |
|  +---------------------+                                              |
|  | Docker Workspace    |                                              |
|  | Cloud Workspace     |                                              |
|  | API Remote          |                                              |
|  | Apptainer           |                                              |
|  +---------------------+                                              |
+-----------------------------------------------------------------------+
```

### Core Module Structure (V0 - `/openhands/`)

| Module | Purpose |
|--------|---------|
| `agenthub/` | Agent implementations (CodeAct, Browsing, Readonly, LOC, VisualBrowsing, Dummy) |
| `controller/` | Agent controller, state machine, stuck detector |
| `core/` | Config, logging, main loop, message handling |
| `memory/` | Condenser system, conversation memory, event views |
| `microagent/` | Keyword-triggered knowledge injection |
| `events/` | Event system (actions, observations, serialization, stream) |
| `llm/` | LLM abstraction via LiteLLM, function call conversion |
| `runtime/` | Sandbox execution (Docker, local, browser) |
| `security/` | Security analyzers (LLM-based, Invariant) |
| `critic/` | Output evaluation (AgentFinishedCritic) |
| `resolver/` | GitHub issue resolver pipeline |
| `mcp/` | Model Context Protocol client |
| `server/` | V0 web server (being replaced by app_server) |
| `app_server/` | V1 application server |
| `storage/` | File stores (local, S3, Google Cloud) |

---

## 3. SOUL.md Equivalent -- Core Prompt System

OpenHands does **not** have a SOUL.md file. Instead, its "soul" is distributed across multiple
Jinja2 templates in `openhands/agenthub/codeact_agent/prompts/`. There are four system prompt
variants that can be selected via configuration:

### 3.1 Primary System Prompt (`system_prompt.j2`)

**File**: `openhands/agenthub/codeact_agent/prompts/system_prompt.j2`

This is the main personality document. Key sections:

```
<ROLE>
Your primary role is to assist users by executing commands, modifying code,
and solving technical problems effectively. You should be thorough, methodical,
and prioritize quality over speed.
</ROLE>

<EFFICIENCY>
...combine multiple actions into a single action...
</EFFICIENCY>

<FILE_SYSTEM_GUIDELINES>
...NEVER create multiple versions of the same file...
</FILE_SYSTEM_GUIDELINES>

<CODE_QUALITY>
...Write clean, efficient code with minimal comments...
</CODE_QUALITY>

<VERSION_CONTROL>
...Exercise caution with git operations...
</VERSION_CONTROL>

<PULL_REQUESTS>
...create only ONE per session/issue...
</PULL_REQUESTS>

<PROBLEM_SOLVING_WORKFLOW>
1. EXPLORATION
2. ANALYSIS
3. TESTING
4. IMPLEMENTATION
5. VERIFICATION
</PROBLEM_SOLVING_WORKFLOW>

<SECURITY>
...Only use GITHUB_TOKEN and other credentials in ways the user has explicitly requested...
</SECURITY>

<SECURITY_RISK_ASSESSMENT>
{% include 'security_risk_assessment.j2' %}
</SECURITY_RISK_ASSESSMENT>

<ENVIRONMENT_SETUP>
...install missing dependencies automatically...
</ENVIRONMENT_SETUP>

<TROUBLESHOOTING>
...Step back and reflect on 5-7 different possible sources of the problem...
</TROUBLESHOOTING>

<DOCUMENTATION>
...Include explanations in conversation responses rather than creating files...
</DOCUMENTATION>

<PROCESS_MANAGEMENT>
...Do NOT use general keywords with commands like pkill...
</PROCESS_MANAGEMENT>
```

**Analysis**: The prompt is structured, practical, and focused on safe code operations. It
emphasizes a 5-step problem-solving workflow (Explore -> Analyze -> Test -> Implement -> Verify)
but gives no strategic planning guidance. The troubleshooting section is notable -- it tells the
agent to "step back and reflect on 5-7 different possible sources" when stuck.

### 3.2 Tech Philosophy Variant (`system_prompt_tech_philosophy.j2`)

**File**: `openhands/agenthub/codeact_agent/prompts/system_prompt_tech_philosophy.j2`

This extends the base prompt with a Linus Torvalds-inspired engineering philosophy:

```
{% include "system_prompt.j2" %}

<TECHNICAL_PHILOSOPHY>
Adopt the engineering mindset of Linus Torvalds...

1. "Good Taste" -- My First Principle
2. "Never break userspace" -- My Iron Law
3. Pragmatism -- My Belief
4. Obsession with Simplicity -- My Standard

# Requirement Confirmation Process
## 0. Premise Thinking -- Linus's Three Questions
1. Is this a real problem or an imagined one?
2. Is there a simpler way?
3. What will it break?

## 2. Linus-Style Problem Decomposition
### First Layer: Data Structure Analysis
### Second Layer: Special Case Identification
### Third Layer: Complexity Review
### Fourth Layer: Breaking Change Analysis
### Fifth Layer: Practicality Verification
</TECHNICAL_PHILOSOPHY>
```

**Analysis**: This is a sophisticated persona overlay. It adds a structured 5-layer analysis
framework that forces the agent to think about data structures before code, identify special
cases, review complexity, analyze breaking changes, and validate practicality. This is more
structured than any other open-source agent's reasoning framework.

### 3.3 Interactive Variant (`system_prompt_interactive.j2`)

Extends base with rules for handling ambiguous instructions, confirming requirements, and
checking existing solutions before implementing.

### 3.4 Long Horizon Variant (`system_prompt_long_horizon.j2`)

Extends base with the **task_tracker** tool for complex multi-step tasks. Includes persistence
across condensation events via `<TASK_TRACKING_PERSISTENCE>` section.

### 3.5 How Prompts Are Loaded

The `PromptManager` class (`openhands/utils/prompt.py`) loads Jinja2 templates from the agent's
prompt directory. The system prompt filename is configurable via `AgentConfig.resolved_system_prompt_filename`.
Workspace context (repo info, runtime info, microagent knowledge) is injected via the
`additional_info.j2` template at runtime.

```
PromptManager
  |-- system_template (system_prompt*.j2)
  |-- user_template (user_prompt.j2)
  |-- additional_info_template (additional_info.j2)  --> repo/runtime context
  |-- microagent_info_template (microagent_info.j2)  --> triggered knowledge
```

### 3.6 Security Risk Assessment

Embedded via `{% include 'security_risk_assessment.j2' %}`. Defines three risk levels:
- **LOW**: Read-only actions
- **MEDIUM**: Project-scoped edits
- **HIGH**: System-level or data exfiltration operations

Every tool call can include a `security_risk` parameter assessed by the LLM.

---

## 4. Memory System

### 4.1 Architecture Overview

OpenHands' memory is entirely **event-stream-based**. There are NO vector stores, NO embeddings,
NO semantic search, NO persistent long-term memory across sessions. Everything is sequential
event processing.

```
Event Stream Architecture:
+------------------------------------------------------------------+
|                                                                  |
|  EventStream (per conversation)                                  |
|  +----------------------------------------------------------+   |
|  | Event 1: MessageAction (user)                             |   |
|  | Event 2: RecallAction (workspace context)                 |   |
|  | Event 3: RecallObservation (repo info + microagents)      |   |
|  | Event 4: CmdRunAction (bash command)                      |   |
|  | Event 5: CmdOutputObservation (command result)            |   |
|  | Event 6: FileEditAction (code change)                     |   |
|  | Event 7: FileEditObservation (edit result)                |   |
|  | ...                                                       |   |
|  +----------------------------------------------------------+   |
|                         |                                        |
|                         v                                        |
|  Condenser System (manages context window)                       |
|  +----------------------------------------------------------+   |
|  | View.from_events() --> filters forgotten events           |   |
|  | Condenser.condensed_history() --> View or Condensation     |   |
|  +----------------------------------------------------------+   |
|                         |                                        |
|                         v                                        |
|  ConversationMemory (converts events to LLM messages)            |
|  +----------------------------------------------------------+   |
|  | process_events() --> list[Message]                         |   |
|  | apply_prompt_caching() --> cache optimization              |   |
|  +----------------------------------------------------------+   |
|                                                                  |
+------------------------------------------------------------------+
```

### 4.2 The Memory Class (`openhands/memory/memory.py`)

The `Memory` class subscribes to the EventStream and handles two types of recall:

1. **WORKSPACE_CONTEXT** recall (first user message):
   - Repository info (name, directory, branch)
   - Runtime info (hosts, ports, date, secrets)
   - Repo-level microagent instructions (always active)
   - Keyword-triggered microagent knowledge

2. **KNOWLEDGE** recall (triggered by keywords in messages):
   - Searches all knowledge microagents for trigger keyword matches
   - Returns matched microagent content as `MicroagentKnowledge`

Microagent sources (loaded at startup):
- **Global**: `skills/` directory (public microagents shipped with OpenHands)
- **User**: `~/.openhands/microagents/` (user's personal microagents)
- **Workspace**: `.openhands/microagents/` in the cloned repo

### 4.3 Condenser System (Context Window Management)

This is the most architecturally interesting part of OpenHands' memory system. The condenser
system manages the context window by compressing/forgetting old events.

**File**: `openhands/memory/condenser/condenser.py`

The abstract `Condenser` class provides:

```python
class Condenser(ABC):
    def condensed_history(self, state: State) -> View | Condensation:
        """Returns either a View (ready for LLM) or a Condensation (needs another step)."""

class RollingCondenser(Condenser, ABC):
    def should_condense(self, view: View) -> bool: ...
    def get_condensation(self, view: View) -> Condensation: ...
```

**Available Condenser Implementations**:

| Condenser | Strategy | LLM Required? |
|-----------|----------|---------------|
| `NoOpCondenser` | Keep everything, no compression | No |
| `ObservationMaskingCondenser` | Mask old observation content, keep structure | No |
| `RecentEventsCondenser` | Keep only N most recent events | No |
| `AmortizedForgettingCondenser` | Forget middle events, keep head + tail | No |
| `LLMSummarizingCondenser` | LLM generates text summary of forgotten events | Yes |
| `StructuredSummaryCondenser` | LLM generates structured summary via function calling | Yes |
| `LLMAttentionCondenser` | LLM scores events by relevance, drops low-scoring ones | Yes |
| `BrowserOutputCondenser` | Specifically compresses browser output | No |
| `CondenserPipeline` | Chain multiple condensers sequentially | Depends |

### 4.4 LLM Summarizing Condenser (Deep Dive)

**File**: `openhands/memory/condenser/impl/llm_summarizing_condenser.py`

When history exceeds `max_size`, this condenser:
1. Keeps the first `keep_first` events (head)
2. Keeps the last `target_size - keep_first - 1` events (tail)
3. Asks an LLM to summarize all middle events
4. Replaces the middle with an `AgentCondensationObservation` containing the summary

The summarization prompt tracks:
- `USER_CONTEXT`: user requirements and goals
- `TASK_TRACKING`: active tasks with IDs and statuses
- `COMPLETED` / `PENDING`: task progress
- `CODE_STATE`: file paths, function signatures, data structures
- `TESTS`: failing cases, error messages
- `CHANGES`: code edits
- `DEPS`: dependencies
- `VERSION_CONTROL_STATUS`: branch, PR status, commit history

### 4.5 Structured Summary Condenser (Deep Dive)

**File**: `openhands/memory/condenser/impl/structured_summary_condenser.py`

Uses function calling to produce a structured `StateSummary` Pydantic model with fields:
- `user_context`, `completed_tasks`, `pending_tasks`, `current_state`
- `files_modified`, `function_changes`, `data_structures`
- `tests_written`, `tests_passing`, `failing_tests`, `error_messages`
- `branch_created`, `branch_name`, `commits_made`, `pr_created`, `pr_status`
- `dependencies`, `other_relevant_context`

This is more reliable than free-form summarization because it uses constrained output via
tool calling.

### 4.6 View System

**File**: `openhands/memory/view.py`

The `View` class represents the filtered event history after condensation:
- `View.from_events(events)` processes `CondensationAction` events to determine which events
  are forgotten and where summaries should be inserted
- Tracks `forgotten_event_ids` to exclude condensed events
- Handles `unhandled_condensation_request` for agent-initiated condensation

### 4.7 Memory Limitations

1. **No cross-session memory**: Each conversation starts fresh. No learning from past sessions.
2. **No semantic search**: Cannot find relevant past context by meaning, only by sequential position.
3. **No embedding store**: No vector database, no similarity-based retrieval.
4. **Microagents are static**: Keyword-triggered, not learned or adapted.
5. **Condensation is lossy**: Summarization inevitably loses details.

---

## 5. Agent Architecture

### 5.1 Agent Hierarchy

```
Agent (base class)
  |
  +-- CodeActAgent (primary - "the brain")
  |     Tools: bash, think, finish, browser, ipython, str_replace_editor,
  |            llm_based_edit, task_tracker, condensation_request
  |
  +-- BrowsingAgent (web browsing specialist)
  |
  +-- ReadonlyAgent (read-only analysis)
  |
  +-- LOCAgent (lines-of-code focused)
  |
  +-- VisualBrowsingAgent (visual web interaction)
  |
  +-- DummyAgent (testing)
```

### 5.2 CodeActAgent -- The Primary Agent

**File**: `openhands/agenthub/codeact_agent/codeact_agent.py`

The CodeAct agent implements the core action loop:

```python
class CodeActAgent(Agent):
    VERSION = '2.2'

    def step(self, state: State) -> Action:
        # 1. Check for pending actions from previous multi-action response
        if self.pending_actions:
            return self.pending_actions.popleft()

        # 2. Check for /exit command
        if latest_user_message == '/exit':
            return AgentFinishAction()

        # 3. Run condenser on history
        match self.condenser.condensed_history(state):
            case View(events=events):
                condensed_history = events    # ready for LLM
            case Condensation(action=condensation_action):
                return condensation_action     # need another step

        # 4. Build messages from condensed history
        messages = self._get_messages(condensed_history, initial_user_message, ...)

        # 5. Call LLM with tools
        response = self.llm.completion(messages=messages, tools=tools)

        # 6. Convert response to actions
        actions = self.response_to_actions(response)
        return self.pending_actions.popleft()
```

**Key Design Decisions**:
- Uses **function calling** exclusively (not text parsing)
- Supports **multi-action responses** (queue of pending actions)
- Condenser integration is seamless -- if condensation is needed, it returns a
  `CondensationAction` instead of a normal action
- The initial user message is always preserved separately

### 5.3 Tool System

Each tool is defined as a `ChatCompletionToolParam` (LiteLLM format):

| Tool | Description |
|------|-------------|
| `cmd_run` | Execute bash commands with optional timeout |
| `think` | Log reasoning without side effects |
| `finish` | Signal task completion |
| `ipython` | Execute Python code in Jupyter |
| `str_replace_editor` | File editing via search/replace |
| `llm_based_edit` | AI-powered file editing |
| `browser` | Web browsing interaction |
| `task_tracker` | Structured task management (plan mode) |
| `condensation_request` | Agent can request history condensation |

The **Think Tool** is particularly interesting:

```python
_THINK_DESCRIPTION = """Use the tool to think about something. It will not
obtain new information or make any changes to the repository, but just log
the thought. Use it when complex reasoning or brainstorming is needed.

Common use cases:
1. When exploring a repository and discovering the source of a bug, call
   this tool to brainstorm several unique ways of fixing the bug...
2. After receiving test results, use this tool to brainstorm ways to fix...
3. When planning a complex refactoring, use this tool to outline approaches...
4. When designing a new feature, think through architecture decisions...
5. When debugging a complex issue, organize your thoughts and hypotheses."""
```

### 5.4 Agent Controller

**File**: `openhands/controller/agent_controller.py` (1392 lines, Legacy V0)

The controller manages the agent lifecycle via a state machine:

```
AgentState Flow:
INIT --> LOADING --> RUNNING --> STOPPED/FINISHED/ERROR
                       |
                       +--> PAUSED --> RUNNING
                       +--> AWAITING_USER_INPUT --> RUNNING
                       +--> AWAITING_USER_CONFIRMATION --> RUNNING
```

Key responsibilities:
1. **Step Loop**: Repeatedly calls `agent.step(state)` until terminal state
2. **Error Handling**: Catches LLM errors (context window exceeded, rate limits, malformed responses)
3. **Stuck Detection**: Runs `StuckDetector` after each step
4. **Security Analysis**: Optionally runs actions through a security analyzer
5. **History Truncation**: Falls back to truncating history if context window is exceeded
6. **Agent Delegation**: Supports spawning sub-agents (BrowsingAgent)
7. **Iteration Limits**: Enforces max_iterations to prevent runaway agents

### 5.5 Stuck Detector

**File**: `openhands/controller/stuck.py`

Detects 5 types of stuck loops:

1. **Repeating Action-Observation**: Same action produces same observation 4 times
2. **Repeating Action-Error**: Same action produces error 3 times
3. **Monologue**: Agent sends identical messages to itself 3 times
4. **Action-Observation Pattern**: Alternating A-B pattern repeats 3 times in 6 steps
5. **Context Window Error Loop**: 10+ consecutive condensation events with nothing between them

When stuck is detected, the controller injects a `LoopDetectionObservation` into the event
stream, giving the agent explicit feedback about the loop type and where it started.

### 5.6 Critic System

**File**: `openhands/critic/base.py`, `openhands/critic/finish_critic.py`

Simple rule-based evaluation:
- `BaseCritic`: Abstract base with `evaluate(events, git_patch) -> CriticResult(score, message)`
- `AgentFinishedCritic`: Checks if agent actually finished (score 1) or not (score 0);
  also checks if git patch is empty (score 0)

The V1 SDK has a `critic_mixin.py` suggesting critics are becoming more integrated.

---

## 6. Brain / Reasoning System

### 6.1 No Dedicated Reasoning Engine

OpenHands has **no dedicated reasoning module**. All reasoning is LLM-driven through:
1. The system prompt's problem-solving workflow
2. The `think` tool for explicit reasoning
3. The tech philosophy variant's 5-layer analysis framework
4. The task tracker for structured planning

### 6.2 Decision-Making Flow

```
User Message
    |
    v
Memory.recall(WORKSPACE_CONTEXT)  --> inject repo/runtime/microagent context
    |
    v
Condenser.condensed_history()     --> compress history if needed
    |
    v
ConversationMemory.process_events() --> convert to LLM messages
    |
    v
LLM.completion(messages, tools)   --> THE BRAIN (external LLM)
    |
    v
response_to_actions()             --> parse function calls to Actions
    |
    v
AgentController validates         --> security check, stuck detection
    |
    v
Runtime executes Action           --> Docker/local sandbox
    |
    v
Observation added to EventStream  --> loop back to agent
```

### 6.3 How the Agent Decides Without Human Input

In **headless mode** (no human in the loop), the agent:
1. Receives the initial task via `MessageAction`
2. Loops through `step()` calls until `AgentFinishAction` or max iterations
3. Uses the `think` tool for internal reasoning
4. Uses the `task_tracker` for structured planning (in long-horizon mode)
5. The stuck detector breaks infinite loops
6. The condenser manages context window automatically

There is no tree-of-thought, no Monte Carlo search, no self-evaluation beyond the simple
critic. The agent relies entirely on the LLM's built-in reasoning capabilities.

### 6.4 How Ambiguity is Handled

In **interactive mode** (`system_prompt_interactive.j2`):
- Agent explores the codebase before implementing
- Reads project documentation first
- Asks for clarification when unsure
- Validates file existence before operations
- Explains technical decisions

In **headless mode**: The agent must make all decisions autonomously, guided only by the
system prompt's problem-solving workflow.

### 6.5 Task Tracker (Planning Tool)

**File**: `openhands/agenthub/codeact_agent/tools/task_tracker.py`

A structured task management tool with two commands:
- `view`: Show current task list
- `plan`: Create or update task list with structured items (id, title, status, notes)

Status values: `todo`, `in_progress`, `done`

This is used in the `system_prompt_long_horizon.j2` variant and includes persistence across
condensation events via a special `<TASK_TRACKING_PERSISTENCE>` section.

---

## 7. Integration Architecture

### 7.1 LLM Integration

OpenHands uses **LiteLLM** as a universal LLM abstraction layer, supporting:
- OpenAI (GPT-4, GPT-5, o1, o3, o4)
- Anthropic (Claude)
- AWS Bedrock
- Google Vertex AI / Gemini
- Mistral
- Ollama (local models)
- Any LiteLLM-compatible provider

Key LLM features:
- **Function calling**: Primary interaction mode (with fallback to text for non-supporting models)
- **Prompt caching**: Supported for Anthropic models
- **Token metrics**: Tracks input/output/cache tokens and costs
- **Retry logic**: Exponential backoff with configurable retries
- **Model routing**: Experimental multimodal router for switching between models
- **Reasoning effort**: Support for o-series models' reasoning_effort parameter

### 7.2 Model Context Protocol (MCP)

**Files**: `openhands/mcp/client.py`, `openhands/mcp/tool.py`

OpenHands supports MCP for external tool integration:
- SSE (Server-Sent Events) transport
- SHTTP (Streamable HTTP) transport
- Stdio transport (direct process communication)
- MCP tools from microagents (repo-level `.openhands/microagents/` can define MCP tools)

MCP tool calls are handled as `MCPAction` events and returned as `MCPObservation` events.

### 7.3 Runtime / Sandbox

```
Runtime Architecture:
+------------------------------------------+
|  Runtime (base class)                    |
|  +------------------------------------+  |
|  | DockerRuntime (primary)            |  |
|  | LocalRuntime (development)         |  |
|  | KubernetesRuntime (cloud)          |  |
|  | E2BRuntime (third-party sandbox)   |  |
|  | ModalRuntime (serverless)          |  |
|  +------------------------------------+  |
|                                          |
|  Action Execution Server (REST API)      |
|  +------------------------------------+  |
|  | Bash session (tmux-based)          |  |
|  | Jupyter kernel                     |  |
|  | Browser (BrowserGym/Playwright)    |  |
|  | File operations                    |  |
|  +------------------------------------+  |
+------------------------------------------+
```

### 7.4 Microagent System (Skills)

**File**: `openhands/microagent/microagent.py`

Three types of microagents:

1. **KnowledgeMicroagent**: Triggered by keywords in user/agent messages
   - Example: `github.md` triggers on "github" or "git" keywords
   - Provides specialized instructions for that domain

2. **RepoMicroagent**: Always loaded for the current repository
   - Stored in `.openhands/microagents/` in the repo
   - Loaded unconditionally into context

3. **TaskMicroagent**: Invoked via slash commands (e.g., `/code-review`)
   - Has input parameters
   - Defines complete workflows

Microagent loading also handles third-party formats:
- `.cursorrules` files (mapped to RepoMicroagent)
- `agents.md` / `agent.md` files (mapped to RepoMicroagent)
- `.openhands_instructions` (legacy format)

### 7.5 Event-Driven Architecture

The entire system is built around the `EventStream`:

```python
class EventStream(EventStore):
    """Thread-safe event publishing and subscribing system."""

    subscribers: {
        'agent_controller': callback,
        'server': callback,
        'runtime': callback,
        'memory': callback,
    }

    def add_event(event, source):
        # Persists to FileStore (local/S3/GCS)
        # Notifies all subscribers in their own thread pools
```

Event types:
- **Actions**: CmdRunAction, FileEditAction, BrowseInteractiveAction, IPythonRunCellAction,
  MessageAction, AgentFinishAction, AgentThinkAction, MCPAction, TaskTrackingAction, etc.
- **Observations**: CmdOutputObservation, FileEditObservation, BrowserOutputObservation,
  ErrorObservation, RecallObservation, AgentCondensationObservation, etc.

### 7.6 Enterprise Integrations

The `enterprise/` directory adds:
- **Authentication**: Keycloak SSO, OAuth flows
- **Git providers**: GitHub, GitLab, Bitbucket, Bitbucket Data Center, Jira, Jira DC, Linear
- **Communication**: Slack integration (resolver, notifications)
- **Billing**: Stripe subscription management
- **Storage**: PostgreSQL (asyncpg), Redis
- **Observability**: PostHog, custom telemetry framework

### 7.7 Issue Resolver

**File**: `openhands/resolver/issue_resolver.py`

A specialized pipeline for automatically resolving GitHub issues:
1. Fetches issue details from GitHub API
2. Constructs a specialized prompt with issue context
3. Runs the agent in headless mode
4. Sends a pull request with the fix

This is integrated with GitHub Actions workflows for automated PR review and issue resolution.

---

## 8. V0 to V1 Migration

### 8.1 Current State

All V0 files are marked with:
```python
# IMPORTANT: LEGACY V0 CODE - Deprecated since version 1.0.0,
# scheduled for removal April 1, 2026
```

### 8.2 V1 SDK Structure (`software-agent-sdk`)

The V1 SDK is a clean, modular monorepo with four packages:

```
software-agent-sdk/
  |-- openhands-sdk/         (core SDK: agent, context, conversation, event, etc.)
  |-- openhands-tools/       (tool implementations: terminal, file_editor, browser, etc.)
  |-- openhands-agent-server/ (REST API server with WebSocket support)
  |-- openhands-workspace/   (workspace management: Docker, Cloud, API)
```

**V1 SDK features not in V0**:
- `apply_patch` tool (Git-style patch application)
- `browser_use` tool (enhanced browser interaction)
- `gemini` specific tools
- `planning_file_editor` (plan-aware file editing)
- `tom_consult` tool (Theory of Mind consultation)
- `delegate` tool (structured sub-agent delegation)
- `preset` system (tool presets for different LLMs -- e.g., GPT5 apply_patch)
- Agent communication protocol (ACP) support
- Configurable security policies
- Browser session recording
- LLM streaming support
- Iterative refinement examples
- LLM profile store
- LLM fallback chains

### 8.3 V1 Agent Philosophy (AGENTS.md)

The V1 SDK's AGENTS.md adopts a softer, more collaborative tone compared to V0:
- "Collaborative software engineering partner" instead of "helpful AI assistant"
- Inspired by open-source engineering principles (unnamed, vs V0's explicit Linus Torvalds reference)
- 4 principles: Simplicity/Clarity, Backward Compatibility, Pragmatic Problem-Solving,
  Maintainable Architecture
- Constructive, collaborative, clear, respectful communication style

---

## 9. Weaknesses and Gaps

### 9.1 No True Long-Term Memory

- No cross-session learning
- No vector store for semantic retrieval
- No memory of past interactions or patterns
- Each conversation starts completely fresh
- Microagents are static, not adaptive

### 9.2 No Strategic Planning Engine

- All planning is LLM-driven with no structured search
- No tree-of-thought or Monte Carlo tree search
- No plan verification or plan comparison
- The task_tracker is a simple list, not a dependency graph
- No parallel execution planning

### 9.3 Weak Self-Evaluation

- The critic system is minimal (just checks if agent finished and if patch is non-empty)
- No intermediate quality checks during execution
- No automatic testing of generated code
- No comparison of multiple solution approaches

### 9.4 Context Window Dependency

- Entirely dependent on LLM context window for "working memory"
- Condenser strategies are lossy -- they inevitably lose important details
- No mechanism to retrieve previously condensed information
- Issue #13257 acknowledges duplication between Plan.md and task_tracker

### 9.5 Stuck Detection is Reactive

- Only detects loops after they happen (3-4 repetitions required)
- No proactive prevention of common failure patterns
- No pattern learning from past stuck scenarios
- Context window error loops need 10 events to detect

### 9.6 Single-Agent Focus

- Primarily designed around a single CodeAct agent
- Agent delegation (to BrowsingAgent) is basic
- No multi-agent coordination or team-based problem solving
- Issue #13030 requests GUI support for sub-agent delegation
- V1 SDK adds delegation and subagent support but it's early stage

### 9.7 Generic Design (Not Coding-Focused Enough)

- The agent is designed as a general-purpose assistant that happens to code
- No code-specific understanding (AST analysis, type checking, test coverage)
- No repository-aware intelligence (understanding project structure, patterns)
- No language-specific strategies (different approaches for Python vs TypeScript)
- Relies on external tools (ruff, mypy, eslint) without understanding their output

### 9.8 Open Issues Revealing Pain Points

From active bug reports:
- **#13311**: Database write failures and timeout handling issues
- **#13282**: Infinite scroll bugs in conversation history
- **#13280**: Chat messages lost during WebSocket disconnection
- **#13156**: PS1 metadata parsing fails with complex stdout
- **#13182**: Slash menu displays repeating/wrong entries
- **#13079**: base_url accepts wrong paths, causing cryptic errors
- **#13125**: API-triggered conversations lack proper titles

From enhancement requests:
- **#13275**: Automations (scheduled/event-driven conversations) -- not yet implemented
- **#13271**: STDIO MCP scalability issues
- **#13233**: Need for specialized search sub-agent (WarpGrep)
- **#13203**: Request for QEMU microVM runtime (Docker alternative)
- **#13113**: Messaging interface for remote execution/confirmation
- **#13088**: LLM subscription support for SDK

### 9.9 Migration Fragility

- V0 and V1 coexist, creating complexity
- V0 removal deadline is April 1, 2026 (imminent)
- Enterprise features depend on V0 patterns
- Many files are tagged as legacy but still actively used

---

## 10. Competitive Opportunities

Based on OpenHands' weaknesses, here are areas where a coding-focused alternative could excel:

### 10.1 Memory Architecture Advantages

| OpenHands | Opportunity |
|-----------|-------------|
| No cross-session memory | Persistent project memory with learning |
| No semantic search | Vector-based retrieval of relevant past context |
| Static microagents | Adaptive skill learning from success/failure |
| Lossy condensation | Hierarchical memory with importance scoring |

### 10.2 Planning Engine Advantages

| OpenHands | Opportunity |
|-----------|-------------|
| LLM-only planning | Structured planning with dependency graphs |
| Simple task list | Multi-agent orchestration with parallel execution |
| No plan verification | Automated plan validation before execution |
| No backtracking | Plan revision when intermediate steps fail |

### 10.3 Code Intelligence Advantages

| OpenHands | Opportunity |
|-----------|-------------|
| Generic text processing | AST-aware code understanding |
| No type awareness | Integrated type checking during editing |
| External linter calls | Real-time lint integration with understanding |
| No test awareness | Test-driven development with coverage tracking |
| Language-agnostic | Language-specific strategies and patterns |

### 10.4 Self-Evaluation Advantages

| OpenHands | Opportunity |
|-----------|-------------|
| Basic finish check | Multi-dimensional quality scoring |
| No intermediate checks | Progressive quality gates |
| No solution comparison | A/B testing of approaches |
| Reactive stuck detection | Proactive failure prevention with pattern learning |

### 10.5 Architecture Advantages

| OpenHands | Opportunity |
|-----------|-------------|
| Single agent focus | Team-based orchestration (Tech Lead model) |
| Simple delegation | Hierarchical domain leads with sub-teams |
| Generic tools | Coding-specific tool ecosystem |
| Event-stream only | Event sourcing + knowledge graph |

---

## Appendix A: Key File Paths

| File | Purpose |
|------|---------|
| `openhands/agenthub/codeact_agent/prompts/system_prompt.j2` | Primary system prompt (SOUL equivalent) |
| `openhands/agenthub/codeact_agent/prompts/system_prompt_tech_philosophy.j2` | Linus Torvalds philosophy overlay |
| `openhands/agenthub/codeact_agent/prompts/system_prompt_interactive.j2` | Interactive mode prompt |
| `openhands/agenthub/codeact_agent/prompts/system_prompt_long_horizon.j2` | Long-horizon task management |
| `openhands/agenthub/codeact_agent/codeact_agent.py` | Main agent implementation |
| `openhands/agenthub/codeact_agent/function_calling.py` | LLM response to action conversion |
| `openhands/agenthub/codeact_agent/tools/think.py` | Reasoning tool |
| `openhands/agenthub/codeact_agent/tools/task_tracker.py` | Planning tool |
| `openhands/controller/agent_controller.py` | Agent lifecycle/state machine |
| `openhands/controller/stuck.py` | Loop detection (5 scenarios) |
| `openhands/memory/memory.py` | Memory class (microagent + context recall) |
| `openhands/memory/conversation_memory.py` | Event-to-message conversion |
| `openhands/memory/condenser/condenser.py` | Condenser base classes |
| `openhands/memory/condenser/impl/llm_summarizing_condenser.py` | LLM-based summarization |
| `openhands/memory/condenser/impl/structured_summary_condenser.py` | Structured summary via function calling |
| `openhands/memory/condenser/impl/amortized_forgetting_condenser.py` | Smart forgetting strategy |
| `openhands/memory/condenser/impl/pipeline.py` | Condenser chaining |
| `openhands/memory/view.py` | Filtered event view |
| `openhands/microagent/microagent.py` | Microagent loading and matching |
| `openhands/events/stream.py` | Event stream (pub/sub) |
| `openhands/llm/llm.py` | LLM abstraction via LiteLLM |
| `openhands/critic/base.py` | Critic evaluation framework |
| `openhands/core/loop.py` | Main agent loop |
| `openhands/utils/prompt.py` | Prompt template management |
| `config.template.toml` | Full configuration reference |
| `AGENTS.md` | Repository-level agent instructions |
| `skills/` | Global microagents (github, docker, npm, etc.) |

## Appendix B: Dependency Stack

- **Python**: 3.12-3.13
- **LLM**: LiteLLM (multi-provider)
- **Web**: FastAPI + Starlette + python-socketio
- **Template**: Jinja2
- **Sandbox**: Docker + libtmux + Playwright
- **Storage**: Local filesystem / S3 / Google Cloud
- **Database**: SQLAlchemy + asyncpg + Redis (enterprise)
- **MCP**: fastmcp >= 2.12.4, mcp >= 1.25
- **Browser**: BrowserGym + Playwright
- **Jupyter**: jupyter-kernel-gateway
- **Auth**: Keycloak + JWT (enterprise)
- **Billing**: Stripe (enterprise)

## Appendix C: Configuration System

OpenHands uses a TOML-based configuration with these main sections:
- `[core]`: workspace paths, max iterations, runtime type, default agent
- `[llm]`: model, API key, base URL, token limits, retry settings, caching
- `[agent]`: tool toggles (browsing, editor, jupyter, cmd, think, finish)
- `[sandbox]`: Docker settings, timeouts, GPU support, volumes
- `[security]`: confirmation mode, security analyzer type
- `[condenser]`: condenser type and strategy-specific settings
- `[mcp]`: MCP server configurations (SSE, SHTTP, stdio)
- `[model_routing]`: experimental model switching
- `[kubernetes]`: K8s-specific runtime settings

---

*Report generated: March 9, 2026*
*Data sources: GitHub API, raw file content, issue tracker, PR history*
