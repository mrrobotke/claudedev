# Research Report: State-of-the-Art AI Agent Brain Architectures

**Date**: March 9, 2026
**Purpose**: Comprehensive research into cognitive architectures, memory systems, decision engines, and self-improving patterns for building an autonomous coding AI.

---

## Table of Contents

1. [Cognitive Architecture Patterns](#1-cognitive-architecture-patterns)
2. [Memory Systems for AI Agents](#2-memory-systems-for-ai-agents)
3. [Autonomous Decision Engines](#3-autonomous-decision-engines)
4. [Code-Specific AI Patterns](#4-code-specific-ai-patterns)
5. [Self-Improving Systems](#5-self-improving-systems)
6. [Local-First AI Architecture](#6-local-first-ai-architecture)
7. [Recommended Architecture for Our System](#7-recommended-architecture-for-our-system)

---

## 1. Cognitive Architecture Patterns

### 1.1 CoALA (Cognitive Architectures for Language Agents)

**How it works**: CoALA is a foundational framework that organizes language agents along three dimensions: information storage (working memory + long-term memory subdivided into episodic, semantic, and procedural), action space (internal actions like reasoning/retrieval and external actions like tool use), and a decision-making loop with planning and execution stages. Each decision cycle has two stages: Planning (the agent applies reasoning and retrieval to propose and evaluate candidate actions) and Execution (the selected action modifies internal memory or the external world).

**Pros**:
- Provides a universal blueprint applicable to any LLM-based agent
- Clean separation of concerns between memory types
- Maps directly to well-understood cognitive science models
- Extensible: new memory types or action types can be added modularly

**Cons**:
- Framework-level abstraction; does not prescribe specific implementations
- No built-in mechanism for learning or self-improvement
- Memory management policies (when to consolidate, what to forget) are left undefined

**Relevance**: HIGH. CoALA should serve as the conceptual backbone of our system. Every component we build maps to a CoALA concept: working memory = current context window, episodic memory = past task logs, semantic memory = codebase knowledge graph, procedural memory = learned coding patterns and strategies.

**Implementation complexity**: MEDIUM. The framework itself is straightforward. Complexity lies in implementing each memory type effectively.

**Key reference**: [Cognitive Architectures for Language Agents (arXiv:2309.02427)](https://arxiv.org/abs/2309.02427)

---

### 1.2 ReAct (Reasoning + Acting)

**How it works**: ReAct interleaves reasoning traces (chain-of-thought) with task-specific actions in a loop. The agent formulates a Thought about its current state and what to do next, takes an Action (e.g., tool call, file read, code edit), observes the result, and repeats. This grounds reasoning in real-world observations rather than pure hallucination.

**Pros**:
- Simple and intuitive loop (Thought -> Action -> Observation)
- Well-proven pattern; most production agents (including Claude) use variants
- Grounding in observations dramatically reduces hallucination
- Easy to implement and debug (traces are human-readable)

**Cons**:
- Linear execution path: does not explore alternatives
- No built-in self-correction: if the first approach fails, recovery depends entirely on the LLM's in-context reasoning
- Can get stuck in loops without explicit mechanisms to break out
- Single trajectory: no backtracking

**Relevance**: HIGH. ReAct is the minimum viable cognitive loop. Our system should use ReAct as the base execution pattern for individual task steps, but layer more advanced patterns (Reflexion, LATS) on top for complex multi-step work.

**Implementation complexity**: LOW. This is a straightforward prompt pattern + tool-calling loop.

**Key reference**: [ReAct: Synergizing Reasoning and Acting (arXiv:2210.03629)](https://arxiv.org/abs/2210.03629)

---

### 1.3 Reflexion

**How it works**: Reflexion extends ReAct by adding a self-evaluation stage after each task attempt. After completing (or failing) a task, the agent reflects on what went wrong, generates verbal feedback (a "reflection"), and stores this reflection in episodic memory. On the next attempt, the agent retrieves relevant reflections to avoid repeating mistakes. The cycle is: Act -> Evaluate -> Reflect -> Store -> Retry with reflection context.

**Pros**:
- Enables genuine learning across attempts without parameter updates
- Verbal reflections are interpretable and debuggable
- Memory of failures prevents infinite retry loops
- Can be layered on top of ReAct with minimal architectural change

**Cons**:
- Requires clear success/failure signals (test results, linting output, etc.)
- Reflection quality depends on the LLM's self-evaluation capability
- Memory can accumulate stale or contradictory reflections over time
- Multiple retries consume significant compute/tokens

**Relevance**: CRITICAL. For a coding AI, Reflexion is essential. We have natural success signals: test pass/fail, lint output, type errors, build success. The agent should reflect after every failed attempt, store the lesson, and apply it. This is how the system "learns" from mistakes without fine-tuning.

**Implementation complexity**: LOW-MEDIUM. Requires: (1) a reflection prompt template, (2) episodic memory store for reflections, (3) retrieval mechanism to inject relevant past reflections into context.

**Key reference**: [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)

---

### 1.4 LATS (Language Agent Tree Search)

**How it works**: LATS unifies reasoning, acting, and planning using Monte Carlo Tree Search (MCTS). Instead of following a single action trajectory (ReAct), LATS explores multiple possible action paths as a tree. At each step, the agent: (1) Selects a node to expand using UCB (Upper Confidence Bound), (2) Expands by generating multiple candidate actions, (3) Evaluates each candidate using an LLM-based value function, (4) Backpropagates the evaluation scores up the tree. This enables the agent to explore alternatives, backtrack from dead ends, and select the most promising path.

**Pros**:
- Dramatically higher accuracy on complex tasks vs. linear approaches
- Natural backtracking when approaches fail
- LLM-based value function can estimate likelihood of success
- Combines the best of tree search (exploration) with LLM reasoning (evaluation)

**Cons**:
- Substantial computational overhead: each tree expansion requires multiple LLM calls
- Latency increases significantly (5-20x slower than ReAct)
- Expensive in token usage for deep trees
- Diminishing returns for simple, well-defined tasks

**Relevance**: HIGH for complex tasks. LATS should be activated selectively for high-stakes, ambiguous tasks (large refactors, architecture decisions, debugging complex issues) where the cost of exploration is justified. For routine coding tasks (simple feature implementation, bug fixes with clear reproduction), ReAct + Reflexion is sufficient.

**Implementation complexity**: HIGH. Requires: (1) tree data structure with node state management, (2) LLM-based value function for node evaluation, (3) UCB selection policy, (4) state snapshot/restore capability for backtracking, (5) budget management to cap exploration depth.

**Key reference**: [Language Agent Tree Search (arXiv:2310.04406)](https://arxiv.org/abs/2310.04406)

---

### 1.5 Graph of Thought (GoT) and ThoughtSculpt

**How it works**: GoT extends Tree of Thought by allowing thoughts to form an arbitrary directed graph rather than a tree. Thoughts can merge, branch, and form cycles. ThoughtSculpt specifically incorporates iterative self-revision capabilities within this graph framework, using MCTS to navigate the search space. This enables the agent to combine partial solutions from different reasoning paths.

**Pros**:
- Can represent complex reasoning with interdependencies
- Enables merging of partial solutions from different branches
- More flexible than tree-based approaches for problems with shared sub-solutions
- ThoughtSculpt's self-revision improves solution quality iteratively

**Cons**:
- Even more computationally expensive than LATS
- Graph management complexity is significant
- Harder to debug and interpret than linear or tree approaches
- Risk of combinatorial explosion without aggressive pruning

**Relevance**: MEDIUM. For most coding tasks, tree search (LATS) provides sufficient exploration. GoT becomes relevant for architecture-level decisions where multiple subsystems interact and partial designs need to be combined. Consider as a future enhancement rather than a v1 requirement.

**Implementation complexity**: VERY HIGH.

**Key reference**: [Graph of Thoughts: Solving Elaborate Problems with Large Language Models](https://arxiv.org/abs/2308.09687)

---

### 1.6 Recommended Cognitive Architecture

**Adaptive Multi-Strategy Architecture**: Our system should implement a tiered cognitive strategy that selects the appropriate reasoning pattern based on task complexity:

| Task Complexity | Strategy | When to Use |
|----------------|----------|-------------|
| Trivial | Direct action (no explicit reasoning) | Single-line fixes, config changes |
| Simple | ReAct | Clear requirement, single-file change |
| Moderate | ReAct + Reflexion | Multi-file feature, debugging |
| Complex | LATS with Reflexion | Architecture decisions, large refactors |
| Ambiguous | LATS + GoT (future) | Cross-system design, unclear requirements |

The **complexity classifier** (a lightweight local model or heuristic) routes tasks to the appropriate strategy. This is critical: using LATS for a typo fix wastes resources; using ReAct for a complex refactor risks poor outcomes.

---

## 2. Memory Systems for AI Agents

### 2.1 Memory Type Taxonomy

Based on CoALA and the latest research (including the ICLR 2026 MemAgents workshop proposals and the "Memory in the Age of AI Agents" survey), AI agent memory should be organized into four primary types:

#### Working Memory (Short-Term / In-Context)
**What it holds**: Current task context, active file contents, recent tool outputs, current reasoning chain.
**Implementation**: The LLM's context window itself. Managed via careful prompt construction and context window management.
**Capacity**: Limited by model context window (128K-1M tokens in 2025-2026).
**Eviction policy**: Least-recently-used with priority retention for: (1) current task description, (2) active file contents, (3) recent tool outputs, (4) system instructions.

#### Episodic Memory (Experience Records)
**What it holds**: Records of past task attempts, including: task description, actions taken, outcomes (success/failure), reflections on what worked/failed, environmental context (repo state, branch, etc.).
**Implementation**: Structured JSON records stored in a local database (SQLite or LanceDB), indexed by task similarity via embeddings.
**Retention**: Permanent for failed attempts (lessons learned). Summarized/consolidated for successful attempts after a cooldown period.
**Retrieval**: Semantic similarity search using task description embeddings + metadata filters (same repo, similar file types, similar error patterns).

#### Semantic Memory (Knowledge Base)
**What it holds**: Facts about the codebase and domain: architecture patterns used, API contracts, coding conventions, dependency graph, team preferences, project-specific terminology.
**Implementation**: A hybrid knowledge graph + vector store (following Cognee's architecture). Entities and relationships stored in a graph database (Kuzu or Neo4j), with vector embeddings for semantic search.
**Update policy**: Continuously updated as the agent explores the codebase. Periodically consolidated to merge redundant facts and resolve contradictions.

#### Procedural Memory (Skills and Strategies)
**What it holds**: Learned procedures for common tasks: "how to add a new API endpoint in this project", "how to write tests following this project's patterns", "how to handle database migrations".
**Implementation**: Templated action sequences stored as structured documents, indexed by task type. Each procedure includes: preconditions, step sequence, expected outcomes, common pitfalls.
**Learning**: Extracted from successful task completions. When the agent completes a novel task type successfully, it generates a procedure template and stores it.

---

### 2.2 MemGPT / Letta Architecture

**How it works**: MemGPT (now the Letta framework) implements an OS-inspired memory hierarchy for LLM agents. It creates three tiers of memory:

1. **Core Memory (In-Context)**: Information the agent actively manages within its context window. Split into blocks (e.g., "user info", "project context") that the agent can read/write.
2. **Recall Memory (Conversation History)**: Full conversation history stored externally. The agent can search and retrieve past messages.
3. **Archival Memory (Knowledge Store)**: Explicitly stored knowledge in an external database. The agent can insert, search, and retrieve arbitrary text.

The agent itself decides when to move information between tiers -- it can "page in" archival memories when needed and "page out" context that is no longer immediately relevant, similar to virtual memory in operating systems.

**Pros**:
- Breaks the context window barrier: effectively infinite memory
- Agent has explicit control over its own memory (reads/writes)
- Clean separation between tiers with well-defined interfaces
- Production-proven (Letta framework, adopted by enterprises)

**Cons**:
- Memory management actions consume tokens and add latency
- Agent must learn when to page-in vs page-out (meta-skill)
- Risk of losing important context if paging decisions are poor
- Sleep-time consolidation adds background processing complexity

**Relevance**: CRITICAL. The MemGPT paradigm is essential for our system. A coding AI that only uses the context window will fail on any task requiring understanding of more than ~50 files. We need the ability to page codebase knowledge in and out of context dynamically.

**Key innovation to adopt**: Letta's "sleep-time memory consolidation" -- asynchronous memory refinement during idle periods. After a task completes, the agent can consolidate what it learned, update its knowledge graph, and refine its procedural memories without blocking the user.

**Implementation complexity**: MEDIUM-HIGH. The core tier system is straightforward. The challenge is building good memory management policies (when to page in/out, what to consolidate).

**Key reference**: [Letta Documentation](https://docs.letta.com/concepts/memgpt/), [MemGPT Paper](https://arxiv.org/abs/2310.08560)

---

### 2.3 Mem0: Production-Scale Memory

**How it works**: Mem0 provides a scalable memory architecture with two variants. The base version uses a vector store with memory extraction, deduplication, and consolidation modules. Mem0g (graph variant) stores memories as directed labeled graphs with entities as nodes and relationships as edges.

The key pipeline: Conversation Input -> Memory Extraction (identifies salient facts) -> Conflict Resolution (checks for contradictions with existing memories) -> Consolidation (merges with existing related memories) -> Storage (vector + optional graph).

**Performance**: 91% lower p95 latency vs. naive RAG approaches, 90%+ token cost savings, 26% improvement in response quality over OpenAI's memory.

**Pros**:
- Production-proven at scale
- Graph variant captures relational structure
- Built-in conflict resolution and deduplication
- Available as Python and JavaScript SDKs

**Cons**:
- Cloud-hosted in the default configuration (privacy concern)
- Graph variant adds complexity and storage overhead
- Memory extraction quality depends on the underlying LLM
- No built-in procedural memory concept

**Relevance**: HIGH. Mem0's memory extraction and consolidation pipeline is directly applicable. We should adopt its patterns for: extracting key facts from coding sessions, deduplicating knowledge, and resolving contradictions when code changes.

**Implementation complexity**: MEDIUM. The open-source version can be self-hosted. Graph variant adds complexity but is worthwhile for codebase relationship mapping.

**Key reference**: [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory (arXiv:2504.19413)](https://arxiv.org/abs/2504.19413)

---

### 2.4 Cognee: Graph-Vector Hybrid Memory Engine

**How it works**: Cognee unifies three storage layers into a single memory engine:
- **Graph store** (Kuzu by default): entities, relationships, structural traversal
- **Vector store** (LanceDB by default): embeddings, semantic similarity search
- **Relational store** (SQLite by default): documents, chunks, provenance tracking

The system ships 14 retrieval modes from classic RAG to chain-of-thought graph traversal. A key innovation is "graph-aware embeddings" that fuse semantic vectors with graph signals (hierarchy, time, entity types) to improve ranking precision.

**Self-improving memory**: Cognee's memory auto-optimization uses rated responses to aggregate weights on graph edges used to answer questions. Those weights guide future ranking, so relevance improves with real usage.

**Pros**:
- Unified interface over graph + vector + relational storage
- Graph-aware embeddings are a significant retrieval improvement
- Self-improving retrieval quality through usage feedback
- Open-source with production adoption (70+ companies)
- Flexible backend choices (can swap Neo4j, Qdrant, PostgreSQL, etc.)

**Cons**:
- Relatively new project; API may still evolve
- Graph construction from raw text can be noisy
- Requires careful schema design for code-specific entities
- Heavier infrastructure than pure vector store approaches

**Relevance**: CRITICAL. Cognee's architecture is the best fit for our codebase memory layer. Code has inherent graph structure (call graphs, import dependencies, type hierarchies) that pure vector stores lose. The unified graph-vector approach lets us store both structural relationships AND semantic meaning.

**Implementation complexity**: MEDIUM. Cognee has a Python SDK. The main work is designing our code-specific entity schema and ingestion pipeline.

**Key reference**: [Cognee GitHub](https://github.com/topoteretes/cognee), [Cognee Architecture Blog](https://www.cognee.ai/blog/fundamentals/how-cognee-builds-ai-memory)

---

### 2.5 Memory Consolidation Strategies

The latest research identifies three consolidation strategies essential for long-lived agents:

#### Extraction
Convert raw experiences (conversation logs, tool outputs) into structured facts. For coding: "This project uses FastAPI with Pydantic v2" or "The auth module has a circular dependency with the user module".

#### Consolidation
Merge related facts, resolve contradictions, and update confidence scores. For coding: when the agent discovers a new pattern that contradicts a previously stored one, the newer observation takes priority but the old one is retained with lower confidence.

#### Forgetting
Remove or downweight outdated information. For coding: when a file is refactored, invalidate all cached facts about the old structure. When a convention changes, update procedural memories accordingly.

**Implementation pattern**: Run consolidation during "sleep time" (between tasks) or triggered by specific events (file changes detected, test results received, PR merged).

---

### 2.6 Knowledge Graphs for Codebases

**How it works**: Recent work (notably GitNexus, published February 2026) demonstrates indexing entire repositories into knowledge graphs that map dependencies, call chains, clusters, and execution flows. The graph is then exposed through Graph RAG for agent consumption.

**Key entities for a code knowledge graph**:
- Files (with metadata: language, size, last modified)
- Functions/Methods (with signatures, complexity, test coverage)
- Classes/Types (with hierarchies, interfaces)
- Modules/Packages (with dependency relationships)
- Tests (linked to the code they cover)
- API Endpoints (with request/response shapes)
- Configuration values (with where they are used)
- Patterns (singleton, repository, factory, etc. detected in code)

**Key relationships**:
- IMPORTS, CALLS, INHERITS, IMPLEMENTS
- TESTS (which test covers which function)
- DEPENDS_ON (runtime dependencies)
- CONFIGURED_BY (config -> code relationship)
- SIMILAR_TO (semantically similar functions across the codebase)

**Relevance**: CRITICAL. This is how we build the agent's "mental model" of a codebase. Rather than re-reading files each time, the agent queries the knowledge graph for relevant context.

**Key references**: [Knowledge Graph Based Repository-Level Code Generation (arXiv:2505.14394)](https://arxiv.org/abs/2505.14394), [GitNexus](https://topaiproduct.com/2026/02/22/gitnexus-turns-your-codebase-into-a-knowledge-graph-and-your-ai-agent-will-thank-you/)

---

## 3. Autonomous Decision Engines

### 3.1 Autonomous Decision-Making Framework

For our coding AI to operate without human input, it needs a structured decision framework. Based on the research, the following architecture emerges:

#### Decision Pipeline

```
Input (Task/Issue/Bug Report)
    |
    v
[1. UNDERSTAND] -- Parse intent, extract requirements, identify ambiguity
    |
    v
[2. CONTEXTUALIZE] -- Retrieve relevant codebase knowledge, past experiences
    |
    v
[3. PLAN] -- Generate candidate approaches (1-3 depending on complexity)
    |
    v
[4. EVALUATE] -- Score each approach on: risk, effort, reversibility, confidence
    |
    v
[5. DECIDE] -- Select approach based on scoring + risk tolerance
    |
    v
[6. EXECUTE] -- Implement with ReAct loop, monitoring for deviations
    |
    v
[7. VERIFY] -- Run tests, lint, type check, compare with expected outcome
    |
    v
[8. REFLECT] -- Log outcome, update memories, adjust confidence calibration
```

#### Ambiguity Resolution Strategy

When the agent encounters ambiguity, it should NOT ask the user. Instead, it should:

1. **Check precedent**: Search episodic memory for similar past decisions
2. **Apply conventions**: Check semantic memory for project conventions
3. **Use conservative defaults**: When genuinely uncertain, choose the approach that is:
   - Most reversible (easiest to undo)
   - Most consistent with existing patterns
   - Least likely to break existing functionality
4. **Document assumptions**: Clearly state what was assumed and why in commit messages or PR descriptions
5. **Flag for review**: Mark decisions with low confidence for human review (but don't block on it)

---

### 3.2 Risk-Aware Decision Engine

The agent needs a risk scoring system:

| Factor | Low Risk (0-3) | Medium Risk (4-6) | High Risk (7-10) |
|--------|---------------|-------------------|-------------------|
| Scope | Single file, local change | Multi-file, single module | Cross-module, architectural |
| Reversibility | Easy git revert | Requires migration rollback | Data loss possible |
| Test coverage | >80% coverage exists | 40-80% coverage | <40% or no tests |
| Confidence | Strong precedent | Some precedent | Novel situation |
| Impact | Internal/dev only | Affects other modules | User-facing / production |

**Risk-based strategy selection**:
- Risk score 0-3: Execute directly, verify with tests
- Risk score 4-6: Generate plan, self-review before execution, run full test suite
- Risk score 7-10: Generate multiple candidate plans, use LATS for exploration, create detailed rollback plan, flag for human review

---

### 3.3 Product Owner Decision Patterns

For the agent to act autonomously as a "Product Owner," it needs decision heuristics for common tradeoff scenarios:

**Scope decisions**: When a task could be interpreted narrowly or broadly, default to the narrower interpretation. Ship the minimal viable change and note potential extensions.

**Quality vs. speed**: Default to quality. A coding AI that ships buggy code loses trust faster than one that takes longer. Always: lint clean, type clean, tests passing.

**Refactoring scope**: When fixing a bug, resist the urge to refactor surrounding code unless the refactoring is necessary for the fix. Scope creep is the enemy of autonomous reliability.

**Backward compatibility**: When changing interfaces, default to backward compatibility. Add new, deprecate old. Never remove without explicit instruction.

**Dependency decisions**: Prefer using existing project dependencies over adding new ones. If a new dependency is truly needed, prefer well-maintained, widely-adopted packages with minimal transitive dependencies.

---

### 3.4 Self-Correction Mechanisms

Based on the research, three layers of self-correction are needed:

#### Immediate self-correction (within a task)
- After each action, check: did the action succeed? Did it move toward the goal?
- If a test fails after a code change, immediately analyze the failure and adjust
- If a tool call returns an error, parse the error and retry with corrected parameters
- Budget: up to 3 retries per action before escalating to a different approach

#### Task-level self-correction (Reflexion)
- After completing a task attempt, evaluate: did tests pass? Is the code clean? Does it meet the requirement?
- If the attempt failed, generate a reflection: what went wrong, what should be tried differently
- Store the reflection and retry with the reflection context
- Budget: up to 3 full task attempts before flagging as blocked

#### Strategic self-correction (cross-task learning)
- After multiple tasks, review: are my approaches working? Am I making the same mistakes repeatedly?
- Periodically review episodic memory for patterns: "I keep failing at X type of task because of Y"
- Update procedural memory with improved strategies
- Adjust confidence calibration based on actual success rates

---

## 4. Code-Specific AI Patterns

### 4.1 How Leading AI Coding Tools Work

#### Cursor Architecture
- **Agent mode** with iterative tool calling (Thought -> Tool -> Observation loop)
- **Cursor 2.0** supports up to 8 parallel agents in isolated environments
- **Background Agents** run in cloud-hosted Ubuntu VMs with internet access
- **Key insight**: Parallelism at the agent level, not just the tool level

#### Windsurf / Cascade Engine
- **Graph-based reasoning** that maps the entire codebase's logic and dependencies
- **"Flow" state**: Persistent context where the AI understands architectural intent, not just the current file
- **SWE-grep models** for fast context retrieval (10x faster than traditional agentic search, using 8 parallel tool calls per turn across 4 turns)
- **Key insight**: Codebase-level understanding via graph-based reasoning is essential

#### Devin Architecture
- **Plan-first approach**: Creates an explicit plan before coding, continuously updates progress
- **Multi-tool**: Terminal, browser, visual capabilities, automated frontend testing
- **SWE-1.5 model**: Emphasizes reasoning depth over raw speed, designed for complex multi-file projects
- **Key insight**: Explicit planning with progress tracking prevents drift

#### SWE-Agent / OpenHands
- **OpenHands SDK**: Stateless, event-sourced architecture with deterministic replay
- **Agentless approach**: Three-phase pipeline: localization -> repair -> validation (no iterative agent loop)
- **Moatless Tools**: Uses MCTS with custom reward functions for patch exploration
- **Key insight**: For well-defined bug fixes, a structured pipeline can outperform open-ended agent loops

**Key references**: [OpenHands Platform (arXiv:2407.16741)](https://arxiv.org/abs/2407.16741), [Windsurf Cascade Engine](https://windsurf.com/compare/windsurf-vs-cursor)

---

### 4.2 AST-Based Code Understanding

**How it works**: Rather than treating code as raw text, parse it into Abstract Syntax Trees (ASTs) to understand structure. AutoCodeRover pioneered this approach, combining LLMs with AST-based code search to achieve strong SWE-bench results.

**AST-based capabilities**:
- **Symbol extraction**: Functions, classes, methods, variables with their signatures and types
- **Call graph construction**: Who calls whom, transitive dependencies
- **Impact analysis**: Given a code change, which other files/functions are affected
- **Pattern detection**: Identify design patterns (repository, factory, singleton) and anti-patterns
- **Complexity analysis**: Cyclomatic complexity, nesting depth, function length

**Implementation**: Use tree-sitter (multi-language AST parser) for parsing. Build a symbol index that maps every symbol to its location, type, and relationships. Update incrementally on file changes.

**Relevance**: CRITICAL. AST understanding is non-negotiable for a production coding AI. Raw text search is insufficient for understanding code structure, navigating large codebases, and making safe edits.

**Implementation complexity**: MEDIUM. Tree-sitter is mature and supports 100+ languages. The main work is building the symbol index and keeping it updated.

---

### 4.3 Repository-Level Understanding ("Mental Model")

A coding AI needs a layered understanding of any repository:

**Layer 1: Structure** (computed once, updated on file changes)
- Directory tree and file organization
- Module/package boundaries
- Build system configuration (package.json, pyproject.toml, Cargo.toml)
- CI/CD configuration

**Layer 2: Architecture** (computed once, refined over time)
- Design patterns in use
- Dependency graph (internal modules + external packages)
- Entry points (main files, API routes, CLI commands)
- Configuration sources and environment variables

**Layer 3: Conventions** (learned from observation)
- Naming conventions (camelCase vs snake_case, file naming patterns)
- Import organization style
- Test file placement and naming
- Error handling patterns
- Logging patterns

**Layer 4: Domain** (accumulated from task context)
- Business domain terminology
- User types and roles
- Data flow (where data enters, transforms, and exits)
- Critical paths (auth, payments, data persistence)

**Implementation**: Layers 1-2 are computed by analyzing the codebase structure and stored in the knowledge graph. Layer 3 is learned from code analysis and stored in procedural memory. Layer 4 accumulates from task descriptions and code comments, stored in semantic memory.

---

### 4.4 Technical Debt Detection

**How it works**: AI-powered technical debt detection goes beyond linting. Modern approaches use ML models to:
- Predict defect-prone code based on complexity metrics and change history
- Identify "hotspots" (files that change frequently AND have high complexity)
- Detect Self-Admitted Technical Debt (SATD) in code comments
- Estimate remediation cost by correlating complexity with historical fix effort

**Key platforms**: CodeScene (predictive analysis, hotspot visualization), DeepCode/Snyk (semantic ML-based analysis)

**Practical implementation for our system**:
- Track a "code health score" per file: complexity + test coverage + change frequency + SATD count
- When working on a file, report its health score and suggest improvements if score is below threshold
- Maintain a "debt register" in semantic memory: known issues, their severity, and estimated fix effort
- When autonomously prioritizing work, factor in debt reduction opportunities adjacent to the current task

**Relevance**: MEDIUM-HIGH. A coding AI that understands technical debt can make better decisions about when to refactor vs. when to ship quickly.

**Implementation complexity**: MEDIUM. Code health scoring can use static analysis tools (tree-sitter metrics + test coverage tools). The ML-based prediction is a future enhancement.

**Key reference**: [CodeScene](https://codescene.com/)

---

## 5. Self-Improving Systems

### 5.1 Outcome-Based Learning

**How it works**: After each task, record the outcome and link it to the approach taken. Over time, patterns emerge: "approach X works for task type Y" or "approach A fails when condition B is present."

**Implementation pipeline**:

```
Task Completion
    |
    v
Record Outcome:
  - Task type (bug fix, feature, refactor, test)
  - Approach taken (which files changed, which tools used, which strategy)
  - Outcome signals:
    * Did tests pass? (binary)
    * Did lint/typecheck pass? (binary)
    * Was the PR approved? (if applicable)
    * Was the solution reverted? (if applicable)
    * Time to completion
    * Number of retries needed
    |
    v
Pattern Extraction (periodic, during "sleep time"):
  - Group outcomes by task type
  - Identify high-success vs low-success approaches
  - Update procedural memory with refined strategies
  - Update confidence calibration per task type
```

**Relevance**: CRITICAL. This is the core mechanism for the agent to improve over time. Without outcome tracking, the agent makes the same mistakes repeatedly.

**Implementation complexity**: LOW-MEDIUM. Recording outcomes is straightforward. Pattern extraction requires periodic analysis (can be a scheduled background task).

---

### 5.2 Self-Challenge and Self-Play (SAGE Framework)

**How it works**: The SAGE (Skill Augmented GRPO for self-Evolution) framework and Self-Challenging Agents (NeurIPS 2025) use a dual-role approach: the LLM plays both "challenger" (creates new tasks in "Code-as-Task" format with test code providing scalar rewards) and "executor" (solves the tasks). Successfully solved tasks become training data.

For our system (without fine-tuning), the adaptation is:
- The agent generates "practice problems" based on the codebase (e.g., "write a new endpoint following the project's patterns", "refactor this function to reduce complexity")
- It solves these problems and evaluates solutions against test suites
- Successful solutions are stored as procedural memory examples
- This builds a library of "skills" specific to each project

**Relevance**: MEDIUM-HIGH. This is a longer-term investment but enables rapid project-specific skill acquisition. When the agent first encounters a new project, it can "practice" before taking on real tasks.

**Implementation complexity**: HIGH. Requires: task generation, solution evaluation, skill extraction, skill library management.

**Key reference**: [Self-Improving AI Agents through Self-Play (arXiv:2512.02731)](https://arxiv.org/abs/2512.02731), [SAGE: Reinforcement Learning for Self-Improving Agent with Skill Library](https://huggingface.co/papers/2512.17102)

---

### 5.3 Preference Learning from Code Review

**How it works**: When a human reviews the agent's code (approves, requests changes, or provides comments), extract preferences and store them:

- **Style preferences**: "Reviewer prefers early returns over nested if-else"
- **Architecture preferences**: "Team prefers dependency injection over global singletons"
- **Naming preferences**: "This project uses `handle_` prefix for event handlers"
- **Quality thresholds**: "Tests must cover error paths, not just happy paths"

**Implementation**: After each review cycle:
1. Parse review comments for actionable preferences
2. Store preferences in semantic memory with confidence scores
3. Before generating code, retrieve relevant preferences and inject into prompt
4. Track whether code following the preference was accepted (reinforcement signal)

**DPO (Direct Preference Optimization) adaptation**: Without fine-tuning the base model, we can implement a lightweight DPO-like system at the prompt level: maintain a preference database that biases generation toward accepted patterns and away from rejected ones.

**Relevance**: HIGH. This is how the agent adapts to team/project-specific standards over time.

**Implementation complexity**: MEDIUM. Preference extraction from natural language reviews is the main challenge (can use the LLM itself for this). Storage and retrieval are straightforward.

---

### 5.4 Confidence Calibration

**How it works**: The agent should maintain calibrated confidence estimates for its outputs. Calibration means: when the agent says it is 80% confident, it should be correct ~80% of the time.

**Implementation**:
1. **Per-task confidence tracking**: Before executing, the agent estimates confidence (0-1). After outcome, compare estimated vs. actual success.
2. **Calibration curve**: Periodically compute calibration curve across recent tasks. If the agent is systematically overconfident, apply a deflation factor.
3. **Domain-specific calibration**: Track confidence separately per domain (backend, frontend, database, testing). The agent may be well-calibrated for Python but overconfident for TypeScript.
4. **Action gating**: Use calibrated confidence to gate actions:
   - High confidence (>0.8): Execute autonomously
   - Medium confidence (0.5-0.8): Execute but flag for review
   - Low confidence (<0.5): Generate plan only, request human input

**Relevance**: HIGH. Confidence calibration is what separates a reliable autonomous agent from a dangerous one. The agent must know what it does not know.

**Key reference**: [Towards a Science of AI Agent Reliability (arXiv:2602.16666)](https://arxiv.org/abs/2602.16666), [ICML 2025 calibration research](https://www.instabase.com/blog/ai-insights-from-icml-2025-part-2-reinforcement-learning-agent-evaluation-and-confidence)

---

### 5.5 Metacognitive Learning

**How it works**: Recent ICML 2025 position paper argues that truly self-improving agents need "intrinsic metacognitive learning" -- the ability to evaluate, reflect on, and adapt their own learning processes. This goes beyond learning from task outcomes to learning about how to learn.

For our system, this means:
- **Strategy meta-evaluation**: "My Reflexion approach works well for test failures but poorly for type errors. I should try a different reflection template for type issues."
- **Memory meta-evaluation**: "I keep retrieving irrelevant codebase facts. My semantic memory retrieval threshold needs adjustment."
- **Tool meta-evaluation**: "I tend to read entire files when I only need a function. I should use symbol-level tools more."

**Implementation**: Periodic meta-reviews (triggered by configurable interval or performance degradation):
1. Sample recent task outcomes
2. Analyze patterns in failures
3. Identify systematic issues in the agent's strategy, memory, or tool usage
4. Generate meta-reflections and store them at a higher priority than regular reflections
5. Update agent configuration or prompt templates based on meta-findings

**Relevance**: HIGH. This is the mechanism for long-term improvement beyond simple outcome tracking.

**Implementation complexity**: HIGH. Requires introspection capabilities and the ability to modify the agent's own behavior programmatically.

**Key reference**: [Position: Truly Self-Improving Agents Require Intrinsic Metacognitive Learning (ICML 2025)](https://openreview.net/forum?id=4KhDd0Ozqe)

---

## 6. Local-First AI Architecture

### 6.1 Local Embedding Models

For a coding AI that handles sensitive codebases, local embeddings are essential. The 2025-2026 landscape:

| Model | Dimensions | Speed (ms/1K tokens) | Quality (MTEB) | Size | Best For |
|-------|-----------|---------------------|-----------------|------|----------|
| **nomic-embed-text-v2** | 768 | ~25 | Top-tier | ~550MB | Highest accuracy, MoE architecture, multilingual |
| **all-MiniLM-L6-v2** | 384 | ~15 | Good | ~80MB | Speed-critical, real-time search |
| **BGE-M3** | 1024 | ~35 | Top-tier | ~1.2GB | Dense+sparse+multi-vector retrieval |
| **EmbeddingGemma** | 768 | ~20 | Top-tier | ~1.2GB | On-device, best for its size class |
| **mxbai-embed-large** | 1024 | ~30 | Very good | ~670MB | Good balance of size and quality |

**Recommendation**: Use **nomic-embed-text-v2** as the primary embedding model. It achieves top-tier accuracy with a Mixture-of-Experts architecture that keeps inference efficient. Fall back to **all-MiniLM-L6-v2** for latency-sensitive operations (real-time autocomplete, instant search). Both can run fully offline via Ollama.

**Key reference**: [Best Open-Source Embedding Models Benchmarked](https://supermemory.ai/blog/best-open-source-embedding-models-benchmarked-and-ranked/), [BentoML Guide to Open-Source Embedding Models](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)

---

### 6.2 Local Vector Stores

| Store | Type | Best For | Persistence | Language |
|-------|------|----------|-------------|----------|
| **LanceDB** | Embedded | Local-first, columnar, disk-based | Native | Python/Rust |
| **ChromaDB** | Embedded/Client-Server | Easy setup, metadata filtering | SQLite backend | Python |
| **FAISS** | Library | Raw speed, GPU acceleration | Manual | Python/C++ |
| **SQLite-VSS** | Extension | Minimal dependencies, embedded | SQLite file | Any |
| **Qdrant** | Client-Server | Production scale, rich filtering | Native | Rust |

**Recommendation**: Use **LanceDB** as the primary vector store. It is embedded (no separate server), disk-based (handles large codebases without running out of RAM), columnar (efficient for metadata-rich vectors), and has native persistence. For the simplest possible setup, **ChromaDB** is a viable alternative with a gentler learning curve.

---

### 6.3 Local Lightweight Classification Models

For task routing, complexity estimation, and intent classification, use small local models rather than sending everything to a cloud LLM:

**Options**:
- **Ollama + small LLMs** (Phi-3, Gemma-2 2B, Llama-3 3B): Run locally for classification, routing, and simple reasoning. 2-4GB RAM.
- **ONNX Runtime + fine-tuned classifiers**: For specific classification tasks (task complexity, file relevance), a fine-tuned BERT or DistilBERT model running via ONNX is faster and more reliable than prompting a general LLM.
- **Heuristic classifiers**: For well-defined routing decisions (e.g., "is this a bug fix or a feature?"), rule-based classifiers with keyword matching are faster, cheaper, and more deterministic.

**Recommendation**: Tiered approach:
1. **Heuristics first**: File type, keyword matching, regex patterns for simple routing
2. **Local small model**: Ollama with Phi-3 for moderate complexity decisions
3. **Cloud LLM**: Only for actual code generation, complex reasoning, and creative problem-solving

---

### 6.4 Hybrid Local-Cloud Architecture

**Architecture pattern adopted by 65% of enterprise AI applications in 2025**:

```
LOCAL (User's Machine)
  |-- Embedding Engine (nomic-embed via Ollama)
  |-- Vector Store (LanceDB)
  |-- Knowledge Graph (Kuzu)
  |-- AST Parser (tree-sitter)
  |-- Complexity Classifier (heuristic + Phi-3)
  |-- Memory Manager (Letta-inspired tier system)
  |-- Context Builder (assembles prompt from local data)
  |
  |-- [Only structured, anonymized context leaves the machine]
  |
  v
CLOUD (API)
  |-- LLM Inference (Claude, GPT-4, etc.)
  |-- Code Generation
  |-- Complex Reasoning
  |
  |-- [Only generated code/reasoning comes back]
  |
  v
LOCAL (Post-processing)
  |-- Code Validation (lint, typecheck, test)
  |-- Memory Update (store outcomes, update knowledge graph)
  |-- Confidence Tracking (update calibration)
```

**Privacy guarantees**:
- Source code never leaves the local machine in raw form
- Only curated context (function signatures, API descriptions, error messages) goes to the cloud
- All memory, embeddings, and knowledge graphs are stored locally
- The cloud LLM sees only what is necessary for the current generation task

**Relevance**: CRITICAL. Many developers and organizations will not adopt a coding AI that sends their source code to external servers. Local-first with selective cloud augmentation is the right architecture.

**Implementation complexity**: MEDIUM. Most components exist as libraries. The integration work is building the context pipeline and privacy filter.

**Key reference**: [Hybrid AI Agent Architectures 2025](https://markaicode.com/tech/hybrid-ai-agent-architectures-2025/), [Local AI Privacy Guide](https://localaimaster.com/blog/local-ai-privacy-guide)

---

## 7. Recommended Architecture for Our System

### 7.1 High-Level Architecture: "Cortex"

Combining the best patterns from this research, here is the recommended architecture:

```
+------------------------------------------------------------------+
|                        CORTEX BRAIN                               |
|                                                                   |
|  +------------------+  +------------------+  +-----------------+  |
|  | PERCEPTION       |  | COGNITION        |  | ACTION          |  |
|  | (Input Layer)    |  | (Reasoning Layer) |  | (Output Layer)  |  |
|  |                  |  |                  |  |                 |  |
|  | - Task Parser    |  | - Strategy       |  | - Code Writer   |  |
|  | - Context Builder|  |   Selector       |  | - Tool Caller   |  |
|  | - Complexity     |  |   (ReAct/        |  | - File Editor   |  |
|  |   Classifier     |  |   Reflexion/LATS)|  | - Shell Runner  |  |
|  | - Memory         |  | - Planner        |  | - Git Manager   |  |
|  |   Retriever      |  | - Evaluator      |  | - PR Creator    |  |
|  +--------+---------+  | - Reflector      |  +--------+--------+  |
|           |             +--------+---------+           |           |
|           v                      |                     v           |
|  +-------------------------------------------------------+        |
|  |                    MEMORY SYSTEM                       |        |
|  |                                                       |        |
|  |  +--Working Memory (Context Window)-+                 |        |
|  |  |  Current task, active files,     |                 |        |
|  |  |  recent outputs, reasoning chain |                 |        |
|  |  +----------------------------------+                 |        |
|  |                                                       |        |
|  |  +--Episodic Memory (LanceDB)-------+                 |        |
|  |  |  Past tasks, outcomes,           |                 |        |
|  |  |  reflections, lessons learned    |                 |        |
|  |  +----------------------------------+                 |        |
|  |                                                       |        |
|  |  +--Semantic Memory (Cognee/Kuzu+LanceDB)-+           |        |
|  |  |  Codebase knowledge graph,              |           |        |
|  |  |  conventions, domain facts              |           |        |
|  |  +----------------------------------------+           |        |
|  |                                                       |        |
|  |  +--Procedural Memory (Structured Store)--+           |        |
|  |  |  Learned procedures, skill templates,  |           |        |
|  |  |  project-specific patterns             |           |        |
|  |  +----------------------------------------+           |        |
|  +-------------------------------------------------------+        |
|                                                                   |
|  +-------------------------------------------------------+        |
|  |                  META-COGNITION                        |        |
|  |  - Confidence Calibration Engine                      |        |
|  |  - Outcome Tracker + Pattern Analyzer                 |        |
|  |  - Strategy Meta-Evaluator                            |        |
|  |  - Memory Quality Monitor                             |        |
|  |  - Sleep-Time Consolidation Scheduler                 |        |
|  +-------------------------------------------------------+        |
+------------------------------------------------------------------+
```

### 7.2 Implementation Phases

#### Phase 1: Foundation (Weeks 1-4)
**Goal**: Working agent with basic memory and ReAct reasoning

Components to build:
- ReAct execution loop with tool calling
- Working memory manager (context window optimization)
- Basic episodic memory (SQLite + LanceDB for past task logs)
- AST-based code understanding (tree-sitter integration)
- Local embedding pipeline (nomic-embed via Ollama + LanceDB)
- Basic task complexity classifier (heuristic-based)

Estimated complexity: MEDIUM

#### Phase 2: Intelligence (Weeks 5-8)
**Goal**: Agent that learns and self-corrects

Components to build:
- Reflexion loop (self-evaluation + reflection storage + retrieval)
- Semantic memory with knowledge graph (Cognee or custom Kuzu + LanceDB)
- Codebase knowledge graph builder (entities: files, functions, classes, tests)
- Outcome tracking system
- Basic confidence estimation
- Memory consolidation (extraction + deduplication)

Estimated complexity: HIGH

#### Phase 3: Autonomy (Weeks 9-12)
**Goal**: Fully autonomous agent with decision engine

Components to build:
- Risk-aware decision engine (scoring + strategy selection)
- LATS for complex tasks (tree search with LLM evaluation)
- Product Owner decision heuristics
- Procedural memory (skill library from successful tasks)
- Preference learning from code review feedback
- Ambiguity resolution without human input

Estimated complexity: HIGH

#### Phase 4: Self-Improvement (Weeks 13-16)
**Goal**: Agent that gets measurably better over time

Components to build:
- Metacognitive evaluation system
- Confidence calibration engine (calibration curve tracking)
- Sleep-time consolidation (async memory refinement)
- Technical debt detection and tracking
- Pattern analysis across task outcomes
- Strategy adaptation based on meta-evaluation

Estimated complexity: VERY HIGH

### 7.3 Key Design Decisions

1. **Cognee over custom graph+vector**: Use Cognee as the memory engine rather than building from scratch. It provides the unified graph-vector storage we need with production-proven reliability. Customize the entity schema for code-specific entities.

2. **LanceDB over ChromaDB**: LanceDB's disk-based columnar storage handles larger codebases without RAM constraints. ChromaDB is simpler but less scalable.

3. **Nomic-embed-text-v2 for embeddings**: Best accuracy among local models, MoE architecture keeps inference efficient, multilingual support for mixed-language codebases.

4. **Adaptive strategy selection over fixed approach**: Different tasks need different reasoning depths. A complexity classifier that routes to ReAct, Reflexion, or LATS based on task characteristics is more efficient than using the most powerful (and expensive) approach for everything.

5. **Letta-inspired memory tiers over flat storage**: The tiered memory system (working -> episodic -> semantic -> archival) with agent-controlled paging is essential for operating across the full lifecycle of a codebase.

6. **Local-first with selective cloud**: All memory, embeddings, and knowledge graphs stay local. Only curated context goes to cloud LLMs for generation. This enables enterprise adoption where code privacy is mandatory.

7. **Outcome-based learning over fine-tuning**: We cannot fine-tune the base LLM. Instead, we build a rich memory system that captures outcomes and patterns, effectively "training" the agent through its memory without touching model weights.

### 7.4 Key Repositories and Papers to Reference

| Resource | Type | Relevance |
|----------|------|-----------|
| [CoALA Paper (arXiv:2309.02427)](https://arxiv.org/abs/2309.02427) | Paper | Foundational cognitive architecture framework |
| [Letta/MemGPT](https://github.com/letta-ai/letta) | Repo | Memory tier system implementation |
| [Cognee](https://github.com/topoteretes/cognee) | Repo | Graph-vector hybrid memory engine |
| [Mem0](https://github.com/mem0ai/mem0) | Repo | Scalable memory extraction + consolidation |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | Repo | Production agent SDK, event-sourced architecture |
| [LATS Paper (arXiv:2310.04406)](https://arxiv.org/abs/2310.04406) | Paper | Tree search for complex agent reasoning |
| [Reflexion Paper](https://arxiv.org/abs/2303.11366) | Paper | Self-reflection and verbal reinforcement learning |
| [LanceDB](https://github.com/lancedb/lancedb) | Repo | Embedded vector store for local-first |
| [Tree-sitter](https://github.com/tree-sitter/tree-sitter) | Repo | Multi-language AST parsing |
| [Nomic Embed](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe) | Model | Best local embedding model |
| [SWE-bench](https://www.swebench.com/) | Benchmark | Standard evaluation for coding agents |
| [Memory in the Age of AI Agents (arXiv:2512.13564)](https://arxiv.org/abs/2512.13564) | Survey | Comprehensive memory systems survey |
| [Agent Reliability (arXiv:2602.16666)](https://arxiv.org/abs/2602.16666) | Paper | Confidence calibration framework |
| [Self-Improving Agents via Self-Play (arXiv:2512.02731)](https://arxiv.org/abs/2512.02731) | Paper | Self-challenge and skill library building |
| [Metacognitive Learning (ICML 2025)](https://openreview.net/forum?id=4KhDd0Ozqe) | Paper | Meta-level self-improvement |

---

## Summary

The state of the art in AI agent brain architecture (2025-2026) has converged on several key principles:

1. **Structured memory is non-negotiable**: Flat context windows are insufficient. Agents need tiered, typed memory (working, episodic, semantic, procedural) with agent-controlled paging.

2. **Adaptive reasoning depth**: No single reasoning strategy fits all tasks. The best systems route tasks to appropriate strategies (ReAct for simple, Reflexion for moderate, LATS for complex).

3. **Self-correction through reflection**: Agents must evaluate their own outputs, generate verbal reflections on failures, and retrieve past reflections to avoid repeating mistakes.

4. **Knowledge graphs for code**: Code has inherent graph structure (call graphs, dependencies, type hierarchies) that pure vector stores lose. Graph-vector hybrid systems (like Cognee) capture both structural and semantic meaning.

5. **Local-first for privacy and speed**: Embeddings, vector stores, and knowledge graphs all run locally. Only curated context goes to cloud LLMs for generation.

6. **Outcome-based improvement**: Without fine-tuning, agents improve through their memory: tracking outcomes, extracting patterns, updating strategies, and calibrating confidence.

7. **Metacognition for sustained improvement**: Beyond learning from task outcomes, the agent must evaluate and adapt its own learning processes.

The recommended architecture ("Cortex") combines these principles into a four-phase implementation plan that progressively builds from a working ReAct agent to a fully autonomous, self-improving coding AI.
