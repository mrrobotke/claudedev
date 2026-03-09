# Exhaustive Academic Research Survey: AI Agent Cognition, Memory Systems, Tool Use, and Autonomous Decision-Making

**Purpose**: Foundational research for building a revolutionary AI brain for an autonomous coding tool on macOS.
**Date**: March 9, 2026
**Scope**: 40+ papers spanning 2022-2026 from arxiv.org, NeurIPS, ICML, ICLR, Nature Communications, and research labs (Anthropic, DeepMind, OpenAI, Meta AI, Microsoft Research).

---

## Table of Contents

1. [LLM Agent Cognitive Architectures](#1-llm-agent-cognitive-architectures)
2. [Memory and Knowledge Systems](#2-memory-and-knowledge-systems)
3. [Tool Use Research](#3-tool-use-research)
4. [Autonomous Decision-Making](#4-autonomous-decision-making)
5. [Self-Improving AI Systems](#5-self-improving-ai-systems)
6. [Novel / Paradigm-Breaking Ideas](#6-novel--paradigm-breaking-ideas)
7. [SYNTHESIS: A Novel AI Brain Architecture](#7-synthesis-a-novel-ai-brain-architecture)

---

## 1. LLM Agent Cognitive Architectures

### 1.1 CoALA: Cognitive Architectures for Language Agents (2023/2024)

**Authors**: Theodore R. Sumers, Shunyu Yao, Karthik Narasimhan, Thomas L. Griffiths
**Venue**: Transactions on Machine Learning Research 2024 | arXiv:2309.02427
**Link**: https://arxiv.org/abs/2309.02427

**Key Insight**: The foundational framework that organizes ALL language agent designs into a unified cognitive architecture with modular memory, structured action spaces, and generalized decision-making loops.

**Architecture**:
```
+---------------------------------------------+
|              CoALA Agent                     |
|  +--------+  +----------+  +-----------+    |
|  |Working |  |Long-Term |  |  Action   |    |
|  |Memory  |  | Memory   |  |  Space    |    |
|  | (ctx)  |  | (epi+sem)|  | (int+ext) |    |
|  +---+----+  +----+-----+  +-----+-----+    |
|      |            |              |           |
|      +------+-----+-----+-------+           |
|             |            |                   |
|      +------v------+  +-v-----------+        |
|      |  Decision   |  | Grounding   |        |
|      |  Procedure  |  | (retrieval  |        |
|      | (plan+exec) |  |  +learning) |        |
|      +-------------+  +-------------+        |
+---------------------------------------------+
```

**Memory**: Three tiers:
- Working memory = LLM context window (ephemeral)
- Episodic memory = past experiences stored externally
- Semantic memory = general knowledge (embeddings, KGs)
- Procedural memory = learned skills/code

**Decision Engine**: Generalized loop of propose -> evaluate -> select -> execute, with optional planning via internal simulation.

**Tool Use**: External actions (API calls, shell commands, file ops) sit alongside internal actions (retrieval, reasoning, self-reflection) in a unified action space.

**Relevance to Our System**: CoALA is the meta-framework. Every other paper maps onto it. Our architecture MUST implement all four memory types (working, episodic, semantic, procedural) and both action types (internal + external). The key innovation space is in decision procedures and memory grounding.

**Limitation**: Descriptive framework, not prescriptive. Does not specify HOW to implement the decision procedure optimally or how memory types should interact dynamically.

---

### 1.2 ReAct: Synergizing Reasoning and Acting in Language Models (2023)

**Authors**: Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik Narasimhan, Yuan Cao
**Venue**: ICLR 2023 | arXiv:2210.03629
**Link**: https://arxiv.org/abs/2210.03629

**Key Insight**: Interleaving reasoning traces (thought) with environment actions (act) in a single prompt dramatically improves both grounding and planning over pure reasoning or pure acting.

**Architecture**:
```
Loop:
  Thought_t  ->  "I need to search for X because..."
  Action_t   ->  Search[X]
  Obs_t      ->  "Result shows Y..."
  Thought_t+1 -> "Based on Y, I should now..."
  Action_t+1  -> Lookup[Z]
  ...
```

**Memory**: Implicit in the context window. Reasoning traces serve as working memory. No explicit long-term memory.

**Decision Engine**: Greedy step-by-step interleaving. No lookahead or backtracking. The LLM decides what to think and what to do at each step.

**Tool Use**: Actions are typed API calls (Search, Lookup, Finish). The LLM generates the action name and arguments as text.

**Relevance to Our System**: ReAct is the baseline loop for any coding agent. Every tool invocation should be preceded by explicit reasoning about WHY. But ReAct alone is insufficient -- it lacks backtracking, long-term memory, and learning.

**Limitation**: Greedy, no backtracking. Hallucinates action names. Cannot recover from wrong paths. No learning between tasks. Context window is the only memory.

---

### 1.3 Reflexion: Language Agents with Verbal Reinforcement Learning (2023)

**Authors**: Noah Shinn, Federico Cassano, Edward Berman, Ashwin Gopinath, Karthik Narasimhan, Shunyu Yao
**Venue**: NeurIPS 2023 | arXiv:2303.11366
**Link**: https://arxiv.org/abs/2303.11366

**Key Insight**: Agents can improve across episodes by reflecting on failures in natural language and storing those reflections in an episodic memory buffer, without ANY weight updates.

**Architecture**:
```
Episode 1: Act -> Fail -> Reflect ("I failed because...")
                              |
                    [Store reflection in memory]
                              |
Episode 2: [Load reflections] -> Act -> Succeed
```

**Memory**: Episodic memory buffer of natural language reflections. These are prepended to the prompt in subsequent attempts. Memory is per-task (not cross-task).

**Decision Engine**: Trial-and-error with verbal self-reflection. After failure, the agent generates a structured reflection analyzing what went wrong, then uses it to guide the next attempt.

**Tool Use**: Same as the underlying agent (ReAct-style).

**Relevance to Our System**: CRITICAL. Our agent must reflect on failed coding attempts and store structured reflections. The key insight is that natural language reflections are a powerful, interpretable, zero-cost form of learning. We should extend this ACROSS tasks -- reflections from one project should inform future projects.

**Limitation**: Reflections are per-task, not generalizable. No mechanism for cross-task transfer. Memory grows unboundedly. Reflection quality depends on the LLM's self-assessment ability (which can be unreliable).

---

### 1.4 Language Agent Tree Search (LATS) (2024)

**Authors**: Andy Zhou, Kai Yan, Michal Shlapentokh-Rothman, Haohan Wang, Yu-Xiong Wang
**Venue**: ICML 2024 | arXiv:2310.04406
**Link**: https://arxiv.org/abs/2310.04406

**Key Insight**: Unifies reasoning, acting, AND planning by treating the agent's decision process as a tree search (Monte Carlo Tree Search), with the LLM serving as both the policy (action proposer) and value function (state evaluator).

**Architecture**:
```
             Root (Initial State)
            /        |         \
       Action1    Action2    Action3
        /    \       |        /   \
      A1a   A1b    A2a     A3a   A3b
       |            |             |
    [eval]       [eval]        [eval]
    Score=0.7    Score=0.3    Score=0.9  <- LLM as value fn
                                 |
                            [Expand]
                            /      \
                         A3b1    A3b2
```

**Memory**: The search tree itself is memory. Self-reflections from failed branches inform exploration of new branches. Combines exploration (trying new actions) with exploitation (following high-value paths).

**Decision Engine**: MCTS with LLM as both policy (proposes actions) and value function (evaluates states). This gives true lookahead and backtracking.

**Tool Use**: Actions are environment interactions. The key innovation is that tool use is now PLANNED rather than reactive -- the agent considers multiple possible tool sequences before committing.

**Relevance to Our System**: For complex coding tasks, tree search is essential. When the agent encounters a bug fix that could go multiple ways, LATS-style search lets it explore alternatives and backtrack. Our system should use MCTS for high-stakes decisions (architecture choices, complex refactors) and greedy ReAct for routine operations.

**Limitation**: Computationally expensive (many LLM calls per decision). The LLM as value function can be poorly calibrated. Not practical for every decision -- need a way to decide WHEN to tree-search vs. act greedily.

---

### 1.5 SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering (2024)

**Authors**: John Yang, Carlos E. Jimenez, Alexander Wettig, Kilian Lieret, Shunyu Yao, Karthik Narasimhan, Ofir Press
**Venue**: NeurIPS 2024 | arXiv:2405.15793
**Link**: https://arxiv.org/abs/2405.15793

**Key Insight**: The INTERFACE between the agent and the computer matters as much as the agent itself. Custom Agent-Computer Interfaces (ACIs) designed for LLMs dramatically outperform generic shell interfaces.

**Architecture**:
```
+----------------+     +------------------+
|   LLM Agent    |     |   ACI Layer      |
| (ReAct-style)  |<--->| - File viewer    |
|                |     | - Search tool    |
|                |     | - Edit commands  |
|                |     | - Guardrails     |
|                |     | - Linter feedback|
+----------------+     +------------------+
         |                      |
         v                      v
+----------------------------------------+
|        Linux Environment               |
|  (git repo, terminal, test runner)     |
+----------------------------------------+
```

**Memory**: Primarily context window. The ACI provides a compact representation of file state that fits in context. History of actions is maintained in context.

**Decision Engine**: ReAct loop with specialized ACI actions. The agent sees file contents through a scrollable window view, searches with ripgrep, and edits with a custom edit command that includes linting feedback.

**Tool Use**: THIS IS THE KEY CONTRIBUTION. SWE-agent's tools are:
- `open <file>` - Opens file in scrollable viewer
- `goto <line>` - Navigate within file
- `scroll_down/up` - Page through file
- `search_file <pattern>` - Search within file
- `search_dir <pattern>` - Search across files
- `edit <start>:<end> <replacement>` - Edit with automatic lint check
- `submit` - Submit the patch

**Relevance to Our System**: FOUNDATIONAL. Our ACI must be even better than SWE-agent's:
1. File viewing should include semantic context (function signatures, class hierarchy)
2. Edit commands should provide type-checking feedback, not just linting
3. Search should be semantic (embedding-based) in addition to pattern-based
4. The ACI should expose macOS-native capabilities (Spotlight, AppleScript, system APIs)

**Limitation**: 12.5% solve rate on SWE-bench (at the time). No learning between tasks. No codebase understanding beyond what fits in context. Cannot handle tasks requiring architectural understanding.

---

### 1.6 AgentBench: Evaluating LLMs as Agents (2024)

**Authors**: Xiao Liu et al. (THUDM)
**Venue**: ICLR 2024 | arXiv:2308.03688
**Link**: https://arxiv.org/abs/2308.03688

**Key Insight**: Systematic evaluation across 8 environments reveals that poor long-term reasoning, decision-making, and instruction following are the main obstacles for LLM agents, with massive gaps between commercial and open-source models.

**Memory**: Each environment provides different memory challenges (database state tracking, web page navigation history, code execution state).

**Decision Engine**: Tests various decision-making strategies across environments including operating system interaction, database operations, knowledge graph reasoning, card games, lateral thinking puzzles, household tasks, web browsing, and web shopping.

**Relevance to Our System**: Provides benchmark dimensions we must target. Our agent must excel at: (1) long-term reasoning across many steps, (2) following complex instructions precisely, (3) maintaining coherent state across interactions.

**Limitation**: Static benchmark -- does not test learning, adaptation, or improvement over time.

---

### 1.7 DeepCode: Open Agentic Coding (2025)

**Authors**: Zongwei Li et al. (University of Hong Kong)
**Venue**: arXiv:2512.07921
**Link**: https://arxiv.org/abs/2512.07921

**Key Insight**: Treats repository synthesis as a channel optimization problem, orchestrating four information operations to maximize task-relevant signals under finite context budgets.

**Architecture**:
```
+------------------+    +------------------+    +------------------+
| Blueprint        |    | Stateful Code    |    | RAG Knowledge    |
| Distillation     |--->| Memory           |--->| Injection        |
| (compress src)   |    | (structured idx) |    | (conditional)    |
+------------------+    +------------------+    +------------------+
         |                       |                       |
         +----------+------------+-----------+-----------+
                    |                        |
            +-------v--------+       +-------v--------+
            | Code Generation|       | Error Correction|
            | (from plan)    |<------| (closed-loop)   |
            +----------------+       +------------------+
```

**Memory**: Stateful code memory provides a structured index of the growing codebase. As files are generated, the memory is updated so later generation steps have full awareness of what has been built.

**Decision Engine**: Blueprint-first planning with iterative closed-loop error correction. The system first distills the source document into a blueprint, then generates code module-by-module with continuous error detection and correction.

**Tool Use**: Code generation, file management, test execution, error analysis tools. RAG for pulling in relevant documentation.

**Relevance to Our System**: The stateful code memory concept is essential. As our agent modifies a codebase, it must maintain a living index of what exists, what changed, and what depends on what. The blueprint distillation concept is valuable for architectural planning before implementation.

**Limitation**: Focused on paper-to-code synthesis rather than general software engineering. Evaluated primarily on PaperBench, not on real-world maintenance/debugging tasks.

---

### 1.8 OpenHands CodeAct 2.1 (2025)

**Venue**: OpenHands Blog, November 2025
**Link**: https://openhands.dev/blog/openhands-codeact-21-an-open-state-of-the-art-software-development-agent

**Key Insight**: Unified agent action space through executable Python code leads to performance gains compared to text- or JSON-based actions. Achieves 53% resolve rate on SWE-Bench Verified (SOTA at publication).

**Architecture**: Uses CodeAct paradigm where the agent communicates through executable Python code rather than structured JSON tool calls. This gives maximum flexibility and composability.

**Relevance to Our System**: The code-as-action paradigm is powerful for a coding agent. Instead of predefined tools, the agent can compose arbitrary tool sequences by writing code. Our system should support both structured tools AND freeform code execution.

---

### 1.9 Devin: The AI Software Engineer (2024-2025)

**Organization**: Cognition AI
**Link**: https://cognition.ai/blog/devin-2

**Key Insight**: First fully autonomous software engineering agent with a cloud IDE, sandboxed browser, terminal, and multi-agent architecture. Achieves multi-hour autonomous work sessions with confidence-based human escalation.

**Architecture**:
```
+---------------------------------------------------+
|                 Devin 2.0                         |
|  +----------+  +----------+  +-----------+       |
|  | Planner  |  | Code     |  | Browser   |       |
|  | (arch    |  | Editor   |  | (web      |       |
|  |  brain)  |  | (IDE)    |  |  research)|       |
|  +----+-----+  +----+-----+  +-----+-----+      |
|       |              |              |              |
|       +---------+----+------+-------+              |
|                 |           |                      |
|           +-----v-----+ +--v-----------+           |
|           | Terminal   | | Multi-Agent  |           |
|           | (exec)     | | Dispatch     |           |
|           +------------+ +--------------+           |
|                                                    |
|  [Repository Auto-Indexing + Wiki Generation]      |
|  [Confidence Evaluation + Human Escalation]        |
+---------------------------------------------------+
```

**Memory**: Repository auto-indexing every few hours creates detailed wikis with architecture diagrams. This serves as persistent semantic memory of the codebase.

**Decision Engine**: Planning-first approach with the "Architectural Brain" that maps out the entire development path before writing code. Multi-agent dispatch for parallelization. Confidence-based human escalation when uncertain.

**Tool Use**: Full cloud IDE with code editor, terminal, sandboxed browser, and planning tools. Can launch multiple agents in parallel.

**Relevance to Our System**: Devin's confidence-based human escalation is critical. Our agent must know when it is uncertain and escalate appropriately. Repository auto-indexing as persistent memory is also essential. The multi-agent architecture for parallel work is a pattern we should adopt.

**Limitation**: Proprietary, closed-source. Performance reviews indicate significant failure modes on complex tasks. High cost per task.

---

## 2. Memory and Knowledge Systems

### 2.1 MemGPT: Towards LLMs as Operating Systems (2023/2024)

**Authors**: Charles Packer, Sarah Wooders, Kevin Lin, Vivian Fang, Shishir G. Patil, Ion Stoica, Joseph E. Gonzalez
**Venue**: arXiv:2310.08560
**Link**: https://arxiv.org/abs/2310.08560

**Key Insight**: Treats the LLM context window as a constrained memory resource (like RAM) and builds a virtual memory system with paging between fast (context) and slow (external storage) memory, inspired by operating system design.

**Architecture**:
```
+-------------------------------------------+
|           MemGPT Memory Hierarchy          |
|                                            |
|  +------------+                            |
|  | Main Context|  <-- "RAM" (fast, small) |
|  | (LLM window)|                           |
|  +------+-----+                            |
|         | page in/out                       |
|  +------v-----------+                      |
|  | External Storage  |  <-- "Disk" (slow,  |
|  | (vector DB, files)|      large)         |
|  +-------------------+                     |
|                                            |
|  [Self-directed memory management]         |
|  [Function calls for read/write/search]    |
|  [Interrupt-driven control flow]           |
+-------------------------------------------+
```

**Memory Storage**: External storage uses vector databases and structured files. Memories are stored as natural language with embeddings for retrieval.

**Memory Retrieval**: The LLM itself decides when to page memories in/out of context, using function calls like `core_memory_append`, `core_memory_replace`, `archival_memory_insert`, `archival_memory_search`.

**Memory Update**: Self-directed -- the LLM manages its own memory through explicit function calls. It can consolidate, update, or evict memories as needed.

**Decision-Making Use**: Memory state directly influences the agent's behavior. Persistent persona and user information guide responses. Archival memory provides long-term knowledge.

**Relevance to Our System**: MemGPT's self-managed memory is a powerful pattern. Our agent should manage its own memory through explicit memory operations, deciding what to remember, what to forget, and what to consolidate. The OS-inspired hierarchy (context = RAM, external = disk) maps perfectly to our tiered memory design.

**Limitation**: Memory management adds overhead to every interaction. The LLM's memory management decisions can be suboptimal (forgetting important things, keeping irrelevant things). No learning of memory management strategies over time.

---

### 2.2 Generative Agents: Interactive Simulacra of Human Behavior (2023)

**Authors**: Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy Liang, Michael S. Bernstein
**Venue**: UIST 2023 | arXiv:2304.03442
**Link**: https://arxiv.org/abs/2304.03442

**Key Insight**: A memory stream architecture with retrieval based on recency, importance, and relevance enables believable long-term agent behavior, including planning, reflection, and social interaction.

**Architecture**:
```
+------------------------------------------------+
|           Memory Stream Architecture           |
|                                                |
|  [Observation] -> Memory Stream (timestamped)  |
|       |                                        |
|  +----v----------+                             |
|  | Retrieval      |                            |
|  | Score = alpha*recency                       |
|  |      + beta*importance                      |
|  |      + gamma*relevance                      |
|  +----+-----------+                            |
|       |                                        |
|  +----v----------+   +------------------+      |
|  | Reflection    |-->| Higher-order     |      |
|  | (periodic)    |   | memories (plans, |      |
|  |               |   | insights, goals) |      |
|  +---------------+   +------------------+      |
|                                                |
|  [Plan] -> [Act] -> [Observe] -> [Remember]   |
+------------------------------------------------+
```

**Memory Storage**: Linear memory stream of observations with timestamps, stored as natural language. Each memory has a recency score (exponential decay), importance score (LLM-rated 1-10), and relevance score (embedding cosine similarity to current query).

**Memory Retrieval**: Weighted combination of recency (exponential decay), importance (LLM-assigned), and relevance (embedding similarity). The weights alpha, beta, gamma are tuned for the application.

**Memory Update**: Periodic reflection synthesizes low-level observations into higher-level insights. These reflections become new memories that can themselves be reflected upon, creating a hierarchy of abstraction.

**Decision-Making Use**: Retrieved memories directly inform daily planning, conversation, and behavior. Reflections guide long-term goals and character development.

**Relevance to Our System**: The three-factor retrieval scoring (recency + importance + relevance) is essential. For a coding agent:
- Recency: Recent code changes matter more than old ones
- Importance: Critical bugs, architecture decisions, security issues rated higher
- Relevance: Semantic similarity to current task
The reflection mechanism should synthesize "what did I learn from this project?" periodically.

**Limitation**: Computationally expensive (many LLM calls for importance scoring and reflection). The linear memory stream does not capture relationships between memories. No forgetting mechanism -- memory grows unboundedly.

---

### 2.3 Voyager: An Open-Ended Embodied Agent with Large Language Models (2023)

**Authors**: Guanzhi Wang, Yuqi Xie, Yunfan Jiang et al.
**Venue**: arXiv:2305.16291
**Link**: https://arxiv.org/abs/2305.16291

**Key Insight**: A skill library of executable code serves as procedural memory, enabling compositional learning where complex behaviors are built from simpler learned skills, preventing catastrophic forgetting.

**Architecture**:
```
+----------------------------------------------+
|              Voyager Architecture             |
|                                              |
|  +----------------+  +------------------+    |
|  | Automatic      |  | Skill Library    |    |
|  | Curriculum     |  | (code snippets)  |    |
|  | (exploration)  |  | indexed by desc  |    |
|  +-------+--------+  +--------+---------+    |
|          |                     |              |
|     +----v-----+        +-----v------+       |
|     | Iterative|        | Retrieval  |       |
|     | Prompting|<-------| (embedding |       |
|     | Mechanism|        |  similarity)|      |
|     +----+-----+        +------------+       |
|          |                                    |
|     +----v--------------+                     |
|     | Code Generation   |                     |
|     | + Self-Verification|                    |
|     | + Error Feedback   |                    |
|     +--------------------+                    |
+----------------------------------------------+
```

**Memory Storage**: Skills stored as executable JavaScript code with natural language descriptions. Indexed by embedding vectors of the descriptions. Skills are composable -- complex skills call simpler ones.

**Memory Retrieval**: Embedding similarity between current task description and skill descriptions. Top-k most relevant skills are included in the prompt as examples.

**Memory Update**: New skills are added after verification (testing in environment). Failed skills are iteratively refined using execution feedback. No skill deletion.

**Decision-Making Use**: The skill library directly provides action templates. The agent retrieves relevant skills, composes them, and generates new skills when needed.

**Relevance to Our System**: THE SKILL LIBRARY CONCEPT IS ESSENTIAL. Our agent should build a library of:
1. Code patterns (how to implement common features in this codebase)
2. Fix patterns (how to debug common error types)
3. Test patterns (how to write tests for this codebase)
4. Refactoring patterns (safe transformation sequences)
Each skill is executable code with a natural language description, composable with other skills.

**Limitation**: Skills are domain-specific (Minecraft). Transfer to new domains requires rebuilding the library. No skill pruning or consolidation. The automatic curriculum can be myopic.

---

### 2.4 A-MEM: Agentic Memory for LLM Agents (2025)

**Authors**: Zhenyu Xu, Haiyan Liang et al.
**Venue**: arXiv:2502.12110
**Link**: https://arxiv.org/abs/2502.12110

**Key Insight**: Memories should be structured as interconnected atomic notes (Zettelkasten method) with dynamic indexing and linking, enabling emergent knowledge organization through self-organizing connections.

**Memory Storage**: Each memory is stored as a structured note containing:
- Contextual description
- Keywords and tags
- Embedding vector
- Links to related memories

**Memory Retrieval**: Multi-modal retrieval combining embedding similarity, keyword matching, and graph traversal through memory links.

**Memory Update**: When new memories are added, the system analyzes historical memories to identify connections, establishes links, and can trigger updates to contextual representations of existing memories. The network continuously refines itself.

**Relevance to Our System**: The Zettelkasten-inspired approach is powerful for coding knowledge. Each memory (a bug fix, a design decision, a pattern learned) becomes an atomic note that links to related notes. Over time, the agent builds a rich knowledge graph of coding knowledge.

---

### 2.5 Zep: A Temporal Knowledge Graph Architecture for Agent Memory (2025)

**Authors**: Preston Rasmussen et al.
**Venue**: arXiv:2501.13956
**Link**: https://arxiv.org/abs/2501.13956

**Key Insight**: Bi-temporal knowledge graphs that track both event time and ingestion time provide superior agent memory, outperforming MemGPT by 18.5% accuracy with 90% lower latency.

**Architecture**:
```
+--------------------------------------------------+
|             Zep / Graphiti Engine                 |
|                                                  |
|  G = (N, E, phi)  where:                        |
|   N = nodes (entities, concepts)                 |
|   E = edges (relationships, temporal)            |
|   phi = incidence function                       |
|                                                  |
|  Three-tier subgraph hierarchy:                  |
|  +-------------+                                 |
|  | Episode     | (raw interaction records)       |
|  | Subgraph    |                                 |
|  +------+------+                                 |
|         |                                        |
|  +------v------+                                 |
|  | Semantic    | (entity nodes with              |
|  | Entity      |  1024-dim embeddings)           |
|  | Subgraph    |                                 |
|  +------+------+                                 |
|         |                                        |
|  +------v------+                                 |
|  | Community   | (clustered entity               |
|  | Subgraph    |  communities)                   |
|  +-------------+                                 |
|                                                  |
|  Bi-temporal model:                              |
|   T  = chronological event ordering              |
|   T' = data ingestion ordering                   |
|                                                  |
|  Retrieval: semantic + BM25 + graph traversal    |
+--------------------------------------------------+
```

**Memory Storage**: Entities stored as nodes with 1024-dimensional embeddings. Relationships stored as edges with temporal metadata. Episodes stored as interaction records.

**Memory Retrieval**: Combines semantic embeddings (cosine similarity), keyword search (BM25), and graph traversal. No LLM summarization needed at query time, enabling sub-second retrieval.

**Memory Update**: Bi-temporal tracking allows the system to understand both when events happened and when the system learned about them. New information can update existing entities while preserving historical state.

**Relevance to Our System**: For codebase understanding, a temporal knowledge graph is ideal:
- Entities = files, functions, classes, modules, dependencies
- Relationships = imports, calls, inherits, modifies
- Temporal = when each relationship was established, how it evolved
This gives the agent a living mental model of the codebase that evolves over time.

**Limitation**: Graph construction requires LLM calls for entity extraction. Storage overhead for large codebases. Community detection adds latency to updates.

---

### 2.6 Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory (2025)

**Authors**: Prateek Chhikara et al.
**Venue**: arXiv:2504.19413
**Link**: https://arxiv.org/abs/2504.19413

**Key Insight**: Production-grade agent memory requires a dual extraction-update pipeline with vector storage, achieving 26% accuracy improvement, 91% lower latency, and 90% token savings compared to full-context approaches.

**Memory Storage**: Vector database for embedding-based retrieval, with optional graph memory (Mem0^g) for relational structures.

**Memory Retrieval**: Embedding similarity search with optional graph traversal. Designed for sub-second latency at production scale.

**Memory Update**: Two-phase pipeline:
1. Extraction Phase: Ingests context sources and uses LLM to extract candidate memories
2. Update Phase: Each new fact is compared against existing entries for deduplication, conflict resolution, and consolidation

**Relevance to Our System**: Production-ready patterns for memory management. The extraction-update pipeline is directly applicable. The 90% token savings demonstrate that intelligent memory management is far more efficient than stuffing everything into context.

---

### 2.7 AriGraph: Knowledge Graph World Models with Episodic Memory (2024/2025)

**Venue**: IJCAI 2025 | arXiv:2407.04363
**Link**: https://arxiv.org/abs/2407.04363

**Key Insight**: Integrating semantic and episodic memories in a unified knowledge graph, where episodic events are stored as timestamped subgraphs alongside persistent semantic facts, significantly enhances agent performance.

**Relevance to Our System**: The code knowledge graph should store both persistent facts (function X calls function Y) and episodic events (on date Z, the agent fixed bug B by modifying function X). This dual representation enables both structural reasoning and experience-based learning.

---

### 2.8 Memory in the Age of AI Agents: A Survey (2025)

**Authors**: Yuyang Hu et al. (46 co-authors)
**Venue**: arXiv:2512.13564
**Link**: https://arxiv.org/abs/2512.13564

**Key Insight**: Comprehensive taxonomy distinguishing factual, experiential, and working memory by function, and token-level, parametric, and latent memory by form. Identifies memory automation and RL integration as key frontiers.

**Memory Taxonomy**:
```
By Function:
  - Factual Memory: What the agent knows (facts, knowledge)
  - Experiential Memory: What the agent has done (episodes, skills)
  - Working Memory: What the agent is currently processing

By Form:
  - Token-level: Natural language stored in context or external DB
  - Parametric: Encoded in model weights (via fine-tuning)
  - Latent: Compressed representations (embeddings, hidden states)

By Dynamics:
  - Formation: How memories are created (extraction, encoding)
  - Evolution: How memories change (consolidation, forgetting)
  - Retrieval: How memories are accessed (search, activation)
```

**Relevance to Our System**: This taxonomy maps directly to our design. We need ALL three functional types and should implement all three forms for maximum flexibility.

---

## 3. Tool Use Research

### 3.1 Toolformer: Language Models Can Teach Themselves to Use Tools (2023)

**Authors**: Timo Schick et al. (Meta AI)
**Venue**: NeurIPS 2023 | arXiv:2302.04761
**Link**: https://arxiv.org/abs/2302.04761

**Key Insight**: LLMs can learn to use tools in a self-supervised way by annotating their own training data with API calls, without any human demonstrations of tool use.

**Tool Use Strategy**: The model learns WHEN to call a tool, WHICH tool to call, and WHAT arguments to pass, by evaluating whether the tool call reduces perplexity on the next token. Tools include: calculator, Q&A system, search engines, translator, calendar.

**Relevance to Our System**: The self-supervised learning approach is valuable. Our agent should be able to discover when a new tool would be helpful and learn its usage pattern from documentation, without explicit programming.

---

### 3.2 Gorilla: Large Language Model Connected with Massive APIs (2023)

**Authors**: Shishir G. Patil, Tianjun Zhang, Xin Wang, Joseph E. Gonzalez
**Venue**: NeurIPS 2024 | arXiv:2305.15334
**Link**: https://arxiv.org/abs/2305.15334

**Key Insight**: Retrieval-augmented fine-tuning enables LLMs to accurately select from large, overlapping API sets while dramatically reducing hallucination. Gorilla surpasses GPT-4 on API call accuracy.

**Tool Use Strategy**: Two-phase approach:
1. Retrieval: Fetch relevant API documentation based on the user query
2. Generation: Generate the correct API call with accurate arguments

The APIBench benchmark includes 11,000+ instruction-API pairs across HuggingFace, TorchHub, and TensorHub.

**Relevance to Our System**: For macOS tool use, our agent needs access to thousands of APIs (shell commands, AppleScript, system frameworks, Homebrew packages, Xcode tools). Gorilla's retrieval-augmented approach scales to this level.

---

### 3.3 ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs (2024)

**Authors**: Yujia Qin et al.
**Venue**: ICLR 2024 | arXiv:2307.16789
**Link**: https://arxiv.org/abs/2307.16789

**Key Insight**: A depth-first search decision tree algorithm enhances LLM reasoning for complex multi-tool scenarios, enabling evaluation of multiple reasoning traces and expanded search spaces.

**Architecture**:
```
User Query
    |
    v
+-------------------+
| Neural API        |
| Retriever         |  <- Select relevant APIs from 16,000+
+--------+----------+
         |
    +----v----+
    | DFSDT   |  <- Depth-First Search Decision Tree
    | Solver  |  <- Explore multiple API call sequences
    +----+----+
         |
    +----v----+
    | Self-   |  <- Retry with different API combinations
    |Reflect  |     if initial solution fails
    +---------+
```

**Tool Use Strategy**:
- Neural API retriever recommends relevant APIs from 16,000+ options
- DFSDT solver explores multiple reasoning traces for complex multi-tool tasks
- Self-reflection mechanism retries with different API combinations on failure
- Handles single-tool and multi-tool scenarios

**Relevance to Our System**: The hierarchical retrieval (category -> tool -> API endpoint) maps perfectly to macOS tooling (system framework -> class -> method). The DFSDT solver is superior to linear ReAct for complex tool composition tasks.

---

### 3.4 AnyTool: Self-Reflective, Hierarchical Agents for Large-Scale API Calls (2024)

**Authors**: Yu Du, Fangyun Wei, Hongyang Zhang
**Venue**: ICML 2024 | arXiv:2402.04253
**Link**: https://arxiv.org/abs/2402.04253

**Key Insight**: Hierarchical API retrieval with self-reflection enables operation over 16,000+ APIs, with the key innovation being a solver that can self-correct when initial API selections prove impractical.

**Architecture**:
```
+-------------------------------------------+
|          AnyTool Architecture             |
|                                           |
|  +------------------+                     |
|  | Hierarchical API | Category -> Tool    |
|  | Retriever        | -> API endpoint     |
|  +--------+---------+                     |
|           |                               |
|  +--------v---------+                     |
|  | GPT-4 Function   | Resolves query      |
|  | Calling Solver    | using selected APIs |
|  +--------+---------+                     |
|           |                               |
|  +--------v---------+                     |
|  | Self-Reflection   | If impractical,    |
|  | Mechanism         | re-activate with   |
|  |                   | different APIs     |
|  +-------------------+                     |
+-------------------------------------------+
```

**Tool Use Strategy**: Three-tier hierarchy:
1. API Retriever: Organizes 16,000+ APIs into categories, selects relevant candidates
2. Solver: Uses GPT-4 function calling to compose API calls
3. Self-Reflection: If the solution is impractical, re-activates with different API selection

Outperforms ToolLLM by +35.4% in average pass rate.

**Relevance to Our System**: The hierarchical retrieval pattern is essential for scaling. On macOS, we have:
- System level: Shell, AppleScript, Automator, Shortcuts
- Framework level: Foundation, AppKit, CoreData, SwiftUI, etc.
- Package level: Homebrew, npm, pip packages
- Tool level: git, docker, xcodebuild, etc.
The self-reflection loop ensures the agent recovers from wrong tool selections.

---

## 4. Autonomous Decision-Making

### 4.1 Agentic Uncertainty Quantification (2026)

**Venue**: arXiv, January 2026
**Link**: https://arxiv.org/html/2601.15703

**Key Insight**: Addresses the "Spiral of Hallucination" in long-horizon agents by transforming verbalized uncertainty into active control signals through dual systems: System 1 (Uncertainty-Aware Memory) for implicit confidence propagation, and System 2 (Uncertainty-Aware Reflection) for targeted resolution.

**Architecture**:
```
+----------------------------------------------+
|    Agentic Uncertainty Quantification        |
|                                              |
|  System 1: Uncertainty-Aware Memory          |
|  +------------------------------------------+
|  | Each memory entry tagged with confidence  |
|  | Confidence propagates through decisions   |
|  | Low-confidence memories get less weight   |
|  +------------------------------------------+
|                                              |
|  System 2: Uncertainty-Aware Reflection      |
|  +------------------------------------------+
|  | When cumulative uncertainty exceeds       |
|  | threshold, trigger deep reflection        |
|  | Targeted resolution of uncertain beliefs  |
|  | May involve re-gathering information      |
|  +------------------------------------------+
|                                              |
|  Balance: Fast execution when confident,     |
|           deep deliberation when uncertain   |
+----------------------------------------------+
```

**Decision Engine**: Dual-process architecture inspired by Kahneman:
- System 1: Fast, confidence-propagating, implicit uncertainty tracking
- System 2: Slow, deliberate, explicitly resolves uncertainty when triggered

**Relevance to Our System**: CRITICAL. Our agent must:
1. Tag every decision with a confidence score
2. Propagate confidence through chains of reasoning
3. Trigger deep reflection when confidence drops below threshold
4. Escalate to human when reflection cannot resolve uncertainty
This prevents the "spiral of hallucination" where the agent compounds errors.

---

### 4.2 Scaling Autonomous Agents via Automatic Reward Modeling and Planning (2025)

**Venue**: arXiv:2502.12130
**Link**: https://arxiv.org/abs/2502.12130

**Key Insight**: Reward models can be automatically learned from environment interactions without human annotations, enabling scalable autonomous agent planning.

**Decision Engine**: Learns reward functions from environment feedback (test results, lint output, type check results). Uses learned rewards to evaluate action trajectories and guide planning.

**Relevance to Our System**: For coding tasks, reward signals are abundant:
- Tests pass/fail (binary reward)
- Lint warnings (count-based reward)
- Type errors (count-based reward)
- Build success (binary reward)
- Code review feedback (delayed reward)
Our agent should learn a composite reward model from these signals to guide its planning.

---

### 4.3 Constitutional AI: Harmlessness from AI Feedback (2022)

**Authors**: Yuntao Bai et al. (Anthropic)
**Venue**: arXiv:2212.08073
**Link**: https://arxiv.org/abs/2212.08073

**Key Insight**: AI systems can self-improve through a constitutional approach: a set of principles guides self-critique and revision, enabling alignment without human labels.

**Decision Engine**: Two phases:
1. Supervised: Model generates responses, self-critiques against principles, revises
2. RL: Preference model trained from AI feedback (not human feedback)

**Relevance to Our System**: Our agent should have a "coding constitution" -- principles that guide autonomous decisions:
- "Always run tests before committing changes"
- "Never modify files outside the task scope"
- "Prefer minimal changes over large refactors"
- "Always handle error cases explicitly"
- "Security vulnerabilities take priority over features"
These principles enable autonomous operation while maintaining quality.

---

### 4.4 Confidence Calibration and Rationalization for LLMs via Multi-Agent Deliberation (2024)

**Venue**: arXiv:2404.09127
**Link**: https://arxiv.org/abs/2404.09127

**Key Insight**: Post-hoc confidence calibration using multiple tool-augmented LLM agents in simulated group deliberation improves confidence accuracy without any training.

**Relevance to Our System**: When our agent must make a critical decision (e.g., choosing between two refactoring approaches), it should simulate deliberation between multiple perspectives (performance, maintainability, security) to calibrate its confidence.

---

### 4.5 Multi-Objective Planning with Contextual Lexicographic Reward Preferences (2025)

**Venue**: arXiv:2502.10476
**Link**: https://arxiv.org/abs/2502.10476

**Key Insight**: Autonomous agents must plan under multiple objectives with context-dependent priority ordering. A Contextual Lexicographic MDP (CLMDP) enables planning with varying objective priorities.

**Relevance to Our System**: Coding decisions involve multiple objectives:
1. Correctness (highest priority)
2. Security (high priority in production code)
3. Performance (context-dependent)
4. Readability (high priority in shared code)
5. Simplicity (generally preferred)
The priority ordering changes based on context (prototyping vs. production, hot path vs. cold path).

---

## 5. Self-Improving AI Systems

### 5.1 Self-Refine: Iterative Refinement with Self-Feedback (2023)

**Authors**: Aman Madaan, Niket Tandon, Prakhar Gupta et al.
**Venue**: NeurIPS 2023 | arXiv:2303.17651
**Link**: https://arxiv.org/abs/2303.17651

**Key Insight**: LLMs can iteratively improve their own outputs through self-generated feedback, achieving ~20% improvement on average across 7 tasks, without any training.

**Architecture**:
```
Initial Output
    |
    v
+----------+     +-----------+     +----------+
| Generate |---->| Feedback  |---->| Refine   |--+
| (draft)  |     | (critique)|     | (improve)|  |
+----------+     +-----------+     +-----+----+  |
                                         |        |
                                         +--------+
                                    (iterate until satisfactory)
```

**Self-Improvement Mechanism**: Same LLM acts as generator, critic, and refiner. No external training or reward model needed. Improvement comes from the model's ability to identify issues in its own output.

**Relevance to Our System**: Every code generation should go through at least one self-refine cycle:
1. Generate code
2. Self-critique (check for bugs, style issues, edge cases)
3. Refine based on critique
4. Repeat until critique is satisfactory or max iterations reached

---

### 5.2 MACLA: Learning Hierarchical Procedural Memory (2025)

**Authors**: S. Forouzandeh et al.
**Venue**: AAMAS 2025 | arXiv:2512.18950
**Link**: https://arxiv.org/abs/2512.18950

**Key Insight**: Decouple reasoning from learning by maintaining a frozen LLM while performing all adaptation in external hierarchical procedural memory. Achieves 78.1% across four benchmarks while being 2800x faster than fine-tuning.

**Architecture**:
```
+----------------------------------------------+
|              MACLA Framework                 |
|                                              |
|  +----------------+                          |
|  | Frozen LLM     | (no weight updates)      |
|  +-------+--------+                          |
|          |                                    |
|  +-------v--------+                          |
|  | Procedural     |                          |
|  | Memory (ext.)  |                          |
|  |  - Procedures  | (reusable action seqs)   |
|  |  - Bayesian    | (reliability tracking)   |
|  |    posteriors   |                          |
|  |  - Expected    | (action selection)       |
|  |    utility     |                          |
|  +-------+--------+                          |
|          |                                    |
|  +-------v--------+                          |
|  | Contrastive    | (learn from success      |
|  | Refinement     |  vs. failure)            |
|  +----------------+                          |
+----------------------------------------------+
```

**Self-Improvement Mechanism**:
1. Extract reusable procedures from successful trajectories
2. Track reliability via Bayesian posteriors (how often does this procedure work?)
3. Select actions via expected utility (reliability x reward)
4. Refine procedures by contrasting successes and failures

15:1 compression ratio (2,851 trajectories -> 187 procedures).

**Relevance to Our System**: MACLA is the blueprint for our procedural memory. Our agent should:
1. Extract coding procedures from successful task completions
2. Track reliability of each procedure across different contexts
3. Use Bayesian selection for procedure retrieval
4. Refine procedures when they fail in new contexts
This gives us learning WITHOUT fine-tuning, in 56 seconds of compute.

---

### 5.3 Self-Improving AI Agents through Self-Play (2025)

**Authors**: (December 2025)
**Venue**: arXiv:2512.02731
**Link**: https://arxiv.org/abs/2512.02731

**Key Insight**: A unified theoretical framework for self-improving agents through the Generator-Verifier-Updater (GVU) operator, where the coefficient of self-improvement is the Lie derivative of the capability functional.

**Architecture**:
```
GVU Operator:
  Generator: Produces candidate outputs
  Verifier:  Evaluates output quality
  Updater:   Improves the system based on evaluation

Existing Methods as GVU Instances:
  AlphaZero:        MCTS (G) + Game outcome (V) + RL update (U)
  GANs:             Generator (G) + Discriminator (V) + GD update (U)
  STaR:             LLM (G) + Answer check (V) + Fine-tune (U)
  Constitutional AI: LLM (G) + Principles (V) + RLHF update (U)
  Self-Instruct:    LLM (G) + Filter (V) + Fine-tune (U)
```

**Relevance to Our System**: Our agent's self-improvement loop:
- Generator: Code generation (from task description to implementation)
- Verifier: Tests, linting, type checking, code review
- Updater: Procedural memory refinement (no weight updates needed)
This theoretical framework ensures our self-improvement is grounded in formal guarantees.

---

### 5.4 WebRL: Self-Evolving Online Curriculum RL (2024)

**Venue**: arXiv:2411.02337
**Link**: https://arxiv.org/abs/2411.02337

**Key Insight**: Self-evolving curricula that generate new tasks from unsuccessful attempts address the scarcity of training tasks and sparse feedback in agent learning.

**Relevance to Our System**: When our agent fails at a task, it should generate similar but simpler tasks to practice on, building up competence before re-attempting the original task. This is curriculum learning applied to coding skill development.

---

### 5.5 AgentRR: Get Experience from Practice (2025)

**Venue**: arXiv:2505.17716
**Link**: https://arxiv.org/abs/2505.17716

**Key Insight**: Multi-level experience design where lower-level experiences provide precise behavioral operations for rapid replay, while high-level experiences offer generalized summaries for better adaptation.

**Relevance to Our System**: Our experience memory should have two levels:
1. Low-level: Exact tool call sequences that worked (for replay in identical situations)
2. High-level: Generalized strategies that abstract over specific implementations (for adaptation to new situations)

---

### 5.6 AutoSkill: Experience-Driven Lifelong Learning (2025/2026)

**Venue**: arXiv:2603.01145
**Link**: https://arxiv.org/html/2603.01145

**Key Insight**: Separation between an online serving path that retrieves relevant skills during response generation and a background learning path that continuously extracts and maintains skills from interaction experience.

**Architecture**:
```
+----------------------------------------------+
|           AutoSkill Architecture             |
|                                              |
|  Online Serving Path (real-time):            |
|  +------------------------------------------+
|  | User Query -> Skill Retrieval -> Response |
|  +------------------------------------------+
|                                              |
|  Background Learning Path (async):           |
|  +------------------------------------------+
|  | Interaction Logs -> Skill Extraction      |
|  | -> Skill Deduplication -> Skill Library   |
|  +------------------------------------------+
|                                              |
|  Separation ensures learning never blocks    |
|  serving, and serving always benefits from   |
|  latest learning.                            |
+----------------------------------------------+
```

**Relevance to Our System**: The serving/learning separation is architecturally critical. Our agent must:
- SERVE: Handle coding tasks in real-time using current skill library
- LEARN: Asynchronously extract skills from completed tasks
- NEVER let learning block serving
This is the "dreaming" phase -- offline skill extraction and consolidation.

---

### 5.7 Meta-RL Induces Exploration in Language Agents (LaMer) (2025)

**Venue**: arXiv:2512.16848
**Link**: https://arxiv.org/abs/2512.16848

**Key Insight**: Cross-episode training encourages exploration and long-term reward optimization. In-context policy adaptation via reflection allows test-time adaptation without gradient updates.

**Relevance to Our System**: Our agent should optimize for long-term rewards across multiple tasks, not just immediate task completion. A debugging shortcut that creates technical debt should score lower than a proper fix, even if both solve the immediate problem.

---

## 6. Novel / Paradigm-Breaking Ideas

### 6.1 Neural Brain: A Neuroscience-Inspired Framework for Embodied Agents (2025)

**Authors**: Jian Liu et al.
**Venue**: arXiv:2505.07634
**Link**: https://arxiv.org/abs/2505.07634

**Key Insight**: First framework to define the "Neural Brain" of embodied agents through the lens of neuroscience, with four biologically-inspired modules: multimodal sensing, perception-cognition-action function, neuroplasticity-based memory, and neuromorphic hardware optimization.

**Architecture**:
```
+--------------------------------------------------+
|              Neural Brain Framework               |
|                                                   |
|  +-----------+  +-----------+  +-------------+   |
|  | SENSING   |  | FUNCTION  |  | MEMORY      |   |
|  | - Multi-  |  | - Predict-|  | - Hierarch- |   |
|  |   modal   |  |   ive     |  |   ical      |   |
|  |   fusion  |  |   percept-|  | - Neuro-    |   |
|  | - Active  |  |   ion     |  |   plastic   |   |
|  |   sensing |  | - Cogni-  |  |   adapta-   |   |
|  | - Adaptive|  |   tive    |  |   tion      |   |
|  |   calib-  |  |   reason- |  | - Context   |   |
|  |   ration  |  |   ing     |  |   aware     |   |
|  |           |  | - Action  |  |             |   |
|  |           |  |   closed- |  |             |   |
|  |           |  |   loop    |  |             |   |
|  +-----------+  +-----------+  +-------------+   |
|                                                   |
|  +-----------------------------------------------+
|  | HARDWARE/SOFTWARE CO-DESIGN                   |
|  | - Event-driven processing                     |
|  | - Neuromorphic architecture                   |
|  | - Hardware-software optimization              |
|  +-----------------------------------------------+
+--------------------------------------------------+
```

**Key Concepts for Our System**:
1. **Active Sensing**: Don't passively read files -- actively probe the codebase based on hypotheses
2. **Predictive Perception**: Before reading a file, predict what it contains based on context
3. **Action Closed-Loop**: Every action produces feedback that immediately updates perception
4. **Neuroplastic Memory**: Memory structure itself changes based on experience, not just content

---

### 6.2 MAP: Modular Agentic Planner (Brain-Inspired) (2025)

**Authors**: Taylor Webb, Shanka Subhra Mondal et al. (Microsoft Research)
**Venue**: Nature Communications 2025 | arXiv:2310.00194
**Link**: https://www.nature.com/articles/s41467-025-63804-5

**Key Insight**: Planning via specialized brain-inspired modules (error monitoring, action proposal, state prediction, state evaluation, task decomposition, task coordination) yields 63% improvement over baseline LLM planning.

**Architecture**:
```
+------------------------------------------------------+
|            MAP: Modular Agentic Planner              |
|                                                      |
|  +---------------+  +------------------+             |
|  | Error Monitor |  | Action Proposer  |             |
|  | (ACC analog)  |  | (PFC analog)     |             |
|  | - Detects     |  | - Generates      |             |
|  |   conflicts   |  |   candidate      |             |
|  |   & errors    |  |   actions        |             |
|  +-------+-------+  +--------+---------+             |
|          |                    |                       |
|  +-------v--------+  +-------v---------+             |
|  | State Predictor|  | State Evaluator |             |
|  | (hippocampus   |  | (OFC analog)    |             |
|  |  analog)       |  | - Values states |             |
|  | - Simulates    |  |   based on      |             |
|  |   future states|  |   goals         |             |
|  +-------+--------+  +--------+--------+             |
|          |                     |                      |
|  +-------v---------+  +-------v---------+            |
|  | Task Decomposer |  | Task Coordinator|            |
|  | (DLPFC analog)  |  | (DLPFC analog)  |            |
|  | - Breaks complex|  | - Sequences     |            |
|  |   tasks into    |  |   subtasks      |            |
|  |   subtasks      |  |   efficiently   |            |
|  +-----------------+  +-----------------+            |
+------------------------------------------------------+
```

**Key Innovation**: Each module can be a DIFFERENT LLM (or the same LLM with different prompts). Smaller, cheaper models can handle specific functions while a larger model coordinates.

**Relevance to Our System**: Our agent brain should have distinct specialized modules:
- Error Monitor: Continuously checks for bugs, type errors, security issues
- Action Proposer: Generates candidate code changes
- State Predictor: Simulates what the codebase will look like after changes
- State Evaluator: Assesses whether predicted state achieves goals
- Task Decomposer: Breaks complex features into implementable subtasks
- Task Coordinator: Sequences subtasks based on dependencies

---

### 6.3 Dreaming and Knowledge Consolidation

**Multiple Papers**:
- Dream2Learn (arXiv:2603.01935)
- SleepNet/DreamNet (arXiv:2409.01633)
- Neuromorphic Dreaming (arXiv:2405.15616)
- CosmoCore: Affective Dream-Replay (arXiv:2510.18895)

**Key Insight**: Agents benefit from "sleep" phases where they consolidate experiences, generate synthetic training data, and reorganize memories without active task execution.

**Dream Architecture**:
```
AWAKE PHASE:
  Agent interacts with environment
  Collects experiences in short-term buffer
  Updates world model from observations

DREAMING PHASE:
  Uses learned world model to generate simulated experiences
  Replays and reorganizes recent memories
  Consolidates procedural skills from episodic episodes
  Prunes low-value memories
  Strengthens high-value connections

Key Results:
  - SleepNet: Integrates unsupervised "sleep" into supervised training
  - DreamNet: Uses autoencoder for deeper feature consolidation
  - 55% less replay samples needed for same performance (SIESTA)
  - Dream-replay with 80% Dream Queue + 20% uniform diversity
```

**Relevance to Our System**: PARADIGM-CRITICAL. Our agent should have scheduled "dreaming" phases:
1. After each project completion: Consolidate what was learned
2. Daily: Reorganize skill library, prune outdated patterns
3. Weekly: Reflect on cross-project patterns, update mental models
4. On demand: When performance degrades, trigger deep consolidation

---

### 6.4 Agentic Uncertainty Quantification: System 1/System 2 for Agents (2026)

(Detailed above in Section 4.1)

**Novel Contribution**: The explicit connection between Kahneman's dual-process theory and agent architecture, with confidence scores serving as the switching mechanism between fast (System 1) and slow (System 2) processing.

---

### 6.5 Transformer-Squared and Peripheral Memory (2025)

**From**: Memory-Augmented Transformers Survey (arXiv:2508.10824)

**Key Insight**: Real-time task adaptation by encoding procedural expertise directly into parameter space using SVD decomposition, and CPU-RAM analogous architectures where LLMs interface with parameter-encoded memory banks.

**Relevance to Our System**: Represents the frontier of memory-architecture co-design. While we cannot modify the underlying LLM, we can build equivalent functionality through external memory systems that feel as natural as internal parameters.

---

### 6.6 CWM: Code World Models (2025)

**Venue**: arXiv:2510.02387
**Link**: https://arxiv.org/abs/2510.02387

**Key Insight**: LLMs can be trained to simulate code execution step-by-step, serving as "world models" for code. This enables the agent to predict the outcome of code changes without actually running them.

**Relevance to Our System**: A code world model is the ultimate tool for a coding agent. If our agent can mentally simulate "what happens when I change this line?", it can plan more effectively and avoid bugs proactively. This is analogous to a chess player thinking ahead several moves.

---

### 6.7 DyMo: Dynamics Modeling for Agent World Models (2025)

**Key Insight**: Augmenting LLMs with state prediction capability alongside function calling during post-training, enabling agents to predict future states of their actions through an internal environment model. Significantly reduces hallucinations.

**Relevance to Our System**: State prediction for coding means predicting: "If I modify file X, what tests will break? What imports will need updating? What will the type checker report?" This predictive capability is essential for confident autonomous operation.

---

### 6.8 Brain-Inspired AI Agent: The Way Towards AGI (2024/2025)

**Venue**: arXiv:2412.08875
**Link**: https://arxiv.org/html/2412.08875v1

**Key Insight**: A general-purpose AI agent designed by emulating the structure of the human brain, with the need for System 2 thinking to be distilled into System 1 reflexes over time.

**Key Concept**: Neuro-symbolic AI bridges learning from data (neural System 1) with reasoning over structured knowledge (symbolic System 2). Over time, frequently used System 2 reasoning patterns should be compiled into fast System 1 responses.

**Relevance to Our System**: As our agent encounters the same patterns repeatedly (e.g., "add a new API endpoint"), the detailed planning process (System 2) should be compiled into fast procedural skills (System 1). This is the mechanism by which the agent becomes faster and more confident over time.

---

### 6.9 Advances in Foundation Agents: Brain-Inspired to Evolutionary, Collaborative, and Safe Systems (2025)

**Venue**: arXiv:2504.01990
**Link**: https://arxiv.org/abs/2504.01990

**Key Insight**: Comprehensive survey of foundation agents identifying key frontiers: brain-inspired design, evolutionary self-improvement, multi-agent collaboration, and safety constraints as core pillars of next-generation agent systems.

---

### 6.10 Effective Harnesses for Long-Running Agents (Anthropic, 2025)

**Organization**: Anthropic Engineering Blog
**Link**: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

**Key Insight**: Long-running agents must bridge context windows through external memory artifacts (e.g., progress files + git history). Different prompts for the first context window (setup) vs. subsequent windows (continuation).

**Architecture**:
```
Context Window 1 (Initializer):
  - Read task description
  - Explore codebase
  - Create claude-progress.txt with plan
  - Set up environment
  - Start implementation

Context Window 2..N (Continuation):
  - Read claude-progress.txt
  - Read git diff since last session
  - Continue from where left off
  - Update claude-progress.txt
  - ...
```

**Relevance to Our System**: The progress file pattern is simple and effective. Our agent should maintain a structured state file that persists across context windows, containing:
1. Current task description and status
2. Plan with completed/remaining steps
3. Key decisions made and rationale
4. Known issues and blockers
5. Relevant file paths and relationships

---

## 7. SYNTHESIS: A Novel AI Brain Architecture

### The CORTEX Architecture
**C**ognitive **O**rchestration for **R**eal-**T**ime **E**xecution and e**X**perience

Based on the synthesis of 40+ papers across cognitive architectures, memory systems, tool use, decision-making, and self-improvement, we propose a novel layered cognitive architecture that combines the best ideas into something that has not been proposed before.

### Core Design Principles

1. **Separation of Timescales**: Inspired by neuroscience (Neural Brain, MAP), our system operates on four distinct timescales -- reactive (milliseconds), deliberative (seconds), reflective (minutes), and consolidative (hours/days). Most existing systems collapse these into one.

2. **Memory as First-Class Architecture**: Unlike systems that bolt on memory as an afterthought, memory IS the architecture. Every component reads from and writes to memory. Computation is memory transformation.

3. **Confidence-Driven Mode Switching**: Inspired by Kahneman's System 1/2 and the Agentic Uncertainty Quantification paper, the agent dynamically switches between fast-reactive and slow-deliberative modes based on calibrated confidence.

4. **Learning Without Training**: Inspired by MACLA, Reflexion, and Voyager, all learning happens through external memory manipulation, not weight updates. The LLM is a frozen reasoning engine; intelligence accumulates in memory.

5. **Dreaming is Mandatory**: Inspired by SleepNet/DreamNet and neuroscience, the system has explicit offline consolidation phases that reorganize, compress, and strengthen memories.

### Architecture Diagram

```
+======================================================================+
|                    CORTEX: AI Brain Architecture                     |
|                                                                      |
|  +------------------------------ LAYER 5: META-COGNITION -----------+
|  |                                                                   |
|  |  [Self-Monitor]     [Confidence     [Mode         [Goal          |
|  |   - Performance      Calibrator]     Selector]     Manager]      |
|  |     tracking         - Per-decision  - System 1    - Task        |
|  |   - Failure          - Bayesian       (fast)        decomp       |
|  |     detection         posteriors    - System 2    - Priority     |
|  |   - Capability       - Escalation     (deliberate)  ordering    |
|  |     assessment        thresholds   - System 3    - Dependency   |
|  |                                      (tree search)  tracking    |
|  +-------------------------------------------------------------------+
|                               |
|  +------------------------------ LAYER 4: PLANNING & REASONING -----+
|  |                                                                   |
|  |  +----------------+  +------------------+  +------------------+  |
|  |  | Blueprint      |  | Multi-Objective  |  | World Model     |  |
|  |  | Architect      |  | Optimizer        |  | Simulator       |  |
|  |  | (MAP-inspired) |  | (CLMDP)          |  | (CWM-inspired)  |  |
|  |  | - Error Monitor|  | - Correctness    |  | - Predict state |  |
|  |  | - Action       |  | - Security       |  |   after changes |  |
|  |  |   Proposer     |  | - Performance    |  | - Simulate test |  |
|  |  | - State        |  | - Readability    |  |   outcomes      |  |
|  |  |   Predictor    |  | - Simplicity     |  | - Detect side   |  |
|  |  | - State        |  | - Context-aware  |  |   effects       |  |
|  |  |   Evaluator    |  |   priority       |  |                 |  |
|  |  +----------------+  +------------------+  +------------------+  |
|  +-------------------------------------------------------------------+
|                               |
|  +------------------------------ LAYER 3: TOOL ORCHESTRATION -------+
|  |                                                                   |
|  |  +-------------------+  +------------------+  +----------------+ |
|  |  | Hierarchical Tool |  | Tool Composer    |  | ACI Layer      | |
|  |  | Retriever         |  | (multi-tool      |  | (SWE-agent+)   | |
|  |  | (AnyTool-style)   |  |  sequencing)     |  | - Semantic     | |
|  |  | System > Framework|  | - DFSDT solver   |  |   file viewer  | |
|  |  | > Package > Tool  |  | - Self-reflection|  | - Typed edit   | |
|  |  | > API endpoint    |  | - Composition    |  |   commands     | |
|  |  |                   |  |   planning       |  | - macOS native | |
|  |  | macOS-native:     |  |                  |  |   integration  | |
|  |  | Shell, AppleScript|  |                  |  | - Guardrails   | |
|  |  | Spotlight, etc.   |  |                  |  | + lint/type    | |
|  |  +-------------------+  +------------------+  +----------------+ |
|  +-------------------------------------------------------------------+
|                               |
|  +------------------------------ LAYER 2: MEMORY SYSTEM ------------+
|  |                                                                   |
|  |  TIER 1: Working Memory (Context Window)                         |
|  |  +---------------------------------------------------------------+
|  |  | Current task, recent actions, active file contents,           |
|  |  | retrieved memories, current plan state                        |
|  |  | [Managed via MemGPT-style paging]                             |
|  |  +---------------------------------------------------------------+
|  |                                                                   |
|  |  TIER 2: Episodic Memory (Temporal Knowledge Graph)              |
|  |  +---------------------------------------------------------------+
|  |  | [Zep/Graphiti-inspired bi-temporal graph]                      |
|  |  | Events: "Fixed bug X in file Y on date Z"                     |
|  |  | Decisions: "Chose approach A over B because..."               |
|  |  | Failures: "Approach C failed because..."                      |
|  |  | Reflections: "Pattern: bugs in module M often relate to..."   |
|  |  | [Retrieval: recency + importance + relevance scoring]         |
|  |  | [Storage: 1024-dim embeddings + BM25 index + graph edges]     |
|  |  +---------------------------------------------------------------+
|  |                                                                   |
|  |  TIER 3: Semantic Memory (Codebase Knowledge Graph)              |
|  |  +---------------------------------------------------------------+
|  |  | [Living mental model of each codebase]                        |
|  |  | Entities: files, functions, classes, modules, dependencies    |
|  |  | Relations: imports, calls, inherits, modifies, tests          |
|  |  | Properties: complexity, test coverage, last modified, owner   |
|  |  | [Auto-indexed, evolves with every interaction]                |
|  |  | [Retrieval: graph traversal + semantic search]                |
|  |  +---------------------------------------------------------------+
|  |                                                                   |
|  |  TIER 4: Procedural Memory (Skill Library)                       |
|  |  +---------------------------------------------------------------+
|  |  | [MACLA-inspired + Voyager-inspired]                            |
|  |  | Skills: executable code patterns with NL descriptions         |
|  |  | Reliability: Bayesian posteriors per skill per context         |
|  |  | Composition: skills reference other skills                    |
|  |  | Selection: expected utility = reliability x value             |
|  |  | Refinement: contrastive learning from success vs. failure     |
|  |  | [Two levels: exact replay + generalized strategies]           |
|  |  +---------------------------------------------------------------+
|  |                                                                   |
|  |  MEMORY DYNAMICS ENGINE                                           |
|  |  +---------------------------------------------------------------+
|  |  | Formation: Extract memories from every interaction            |
|  |  | Consolidation: Periodic dreaming phases                       |
|  |  |   - Compress episodic -> semantic (pattern extraction)        |
|  |  |   - Compress episodic -> procedural (skill extraction)        |
|  |  |   - Prune low-importance, low-reliability entries             |
|  |  | Forgetting: Ebbinghaus-inspired decay (MemoryBank-style)      |
|  |  |   - Unused memories decay; accessed memories strengthen       |
|  |  | Linking: A-MEM Zettelkasten-style cross-references            |
|  |  +---------------------------------------------------------------+
|  +-------------------------------------------------------------------+
|                               |
|  +------------------------------ LAYER 1: EXECUTION ENGINE ---------+
|  |                                                                   |
|  |  +---------------------+  +-------------------+                  |
|  |  | ReAct Core Loop     |  | Self-Refine Loop  |                  |
|  |  | Think -> Act -> Obs |  | Generate ->       |                  |
|  |  | (baseline operation)|  | Critique ->       |                  |
|  |  |                     |  | Refine -> Verify  |                  |
|  |  +---------------------+  +-------------------+                  |
|  |                                                                   |
|  |  +---------------------+  +-------------------+                  |
|  |  | Reflexion Engine    |  | LATS Engine       |                  |
|  |  | (on failure:        |  | (for complex      |                  |
|  |  |  reflect + retry)   |  |  decisions: MCTS) |                  |
|  |  +---------------------+  +-------------------+                  |
|  +-------------------------------------------------------------------+
|                               |
|  +------------------------------ LAYER 0: FOUNDATION ---------------+
|  |                                                                   |
|  |  [Frozen LLM]  [Local Embeddings]  [macOS Runtime]               |
|  |  Claude/etc.   EmbeddingGemma/     Shell, AppleScript,           |
|  |  (via API)     e5-small            Spotlight, system APIs        |
|  |                (on-device,         git, docker, xcodebuild       |
|  |                 sub-15ms)          File system, processes        |
|  |                                                                   |
|  +-------------------------------------------------------------------+
+======================================================================+
```

### How CORTEX Differs from Existing Systems

**vs. ReAct**: ReAct is our Layer 1 baseline. CORTEX adds 4 layers on top: memory system, tool orchestration, planning, and meta-cognition. ReAct has no memory, no learning, no confidence tracking.

**vs. CoALA**: CoALA is a descriptive framework; CORTEX is a prescriptive architecture. Where CoALA says "have memory," CORTEX specifies four tiers with specific data structures, retrieval algorithms, and consolidation mechanisms.

**vs. MemGPT**: MemGPT handles one aspect (context window management). CORTEX integrates this as one component of a comprehensive four-tier memory system with consolidation, forgetting, and cross-tier transfer.

**vs. Devin**: Devin is a monolithic product. CORTEX is a modular architecture where each component can be independently upgraded. Devin's memory is repository indexing; CORTEX has episodic, semantic, and procedural memory with active consolidation.

**vs. SWE-agent**: SWE-agent focuses on the ACI layer (our Layer 3). CORTEX adds planning, meta-cognition, and rich memory above the ACI, plus learning from experience.

**vs. MACLA**: MACLA provides procedural memory (our Tier 4). CORTEX adds three more memory tiers and five processing layers around it.

### Key Innovations in CORTEX

#### Innovation 1: Confidence-Driven Three-Mode Execution
```
IF confidence > 0.9:
  System 1 (Fast): Execute from procedural memory, no deliberation
  - Use skill library directly
  - Sub-second response for known patterns

ELIF confidence > 0.6:
  System 2 (Deliberate): Full planning with MAP-style modules
  - Error monitoring, state prediction, multi-objective optimization
  - 10-60 second deliberation for medium-complexity tasks

ELSE:
  System 3 (Search): LATS-style tree search with backtracking
  - Explore multiple approaches in parallel
  - 1-10 minute deep exploration for high-stakes decisions
  - Escalate to human if confidence remains below 0.3
```

Most systems use a single execution mode. CORTEX dynamically selects the mode based on calibrated confidence, optimizing the compute-quality tradeoff.

#### Innovation 2: Four-Tier Memory with Active Consolidation
```
Working Memory (Tier 1)   <-- Fast, small, context window
       |  page in/out (MemGPT-style)
       v
Episodic Memory (Tier 2)  <-- Medium, temporal KG (Zep-style)
       |  reflection (Generative Agents-style)
       v
Semantic Memory (Tier 3)  <-- Large, codebase KG (AriGraph-style)
       |  skill extraction (MACLA-style)
       v
Procedural Memory (Tier 4) <-- Compact, skill library (Voyager-style)
       |
       |  [Dreaming Phase: Periodic consolidation]
       |  - Episodes -> Reflections -> Semantic facts -> Skills
       |  - Ebbinghaus decay on unused memories
       |  - Zettelkasten linking across tiers
       |  - Contrastive refinement of skills
```

No existing system implements all four tiers with active consolidation between them. This is the mechanism by which the agent accumulates intelligence over time without any weight updates.

#### Innovation 3: Predictive Coding for Code
Inspired by the CWM (Code World Models) and DyMo papers, our agent maintains an internal model of the codebase that can:
1. Predict test outcomes before running tests
2. Predict type errors before running the type checker
3. Predict side effects of changes before making them
4. Predict which files will need updates for a given change

This is the coding equivalent of a chess engine thinking ahead. Wrong predictions are used as learning signal to improve the world model.

#### Innovation 4: Coding Constitution for Autonomous Operation
Drawing from Constitutional AI, our agent operates under a set of inviolable principles:
```
CODING CONSTITUTION:
1. Correctness First: Never introduce a known bug, even to meet a deadline.
2. Test Before Commit: Every code change must be verified before submission.
3. Minimal Footprint: Prefer the smallest change that solves the problem.
4. Explicit Over Implicit: Handle errors explicitly; never swallow exceptions.
5. Security by Default: Assume all inputs are adversarial.
6. Document Decisions: Record WHY, not just WHAT was changed.
7. Reversibility: Prefer changes that can be easily reverted.
8. Escalate Uncertainty: When confidence is below threshold, ask a human.
9. Learn From Failure: Every failure generates a reflection and skill update.
10. Respect Boundaries: Never modify files outside the declared scope.
```

These principles enable autonomous operation while preventing catastrophic decisions.

#### Innovation 5: macOS-Native Brain
Unlike cloud-dependent systems, CORTEX is designed to run natively on macOS:
```
Local Components:
  - EmbeddingGemma (308M params, <200MB RAM, <15ms latency)
  - SQLite + JSON for memory storage (no external DB needed)
  - Spotlight integration for file search
  - AppleScript for system automation
  - FSEvents for real-time file system monitoring
  - Core ML for local model inference where needed

Cloud Components:
  - LLM API calls (Claude/GPT for reasoning)
  - Backup memory sync (optional)

Hybrid Strategy:
  - System 1 (fast): Fully local, sub-second
  - System 2 (deliberate): Local + 1-2 API calls
  - System 3 (search): Multiple API calls with local caching
```

#### Innovation 6: Dreaming Phase Architecture
```
DREAMING SCHEDULE:

  Micro-Dream (after each task, ~30 seconds):
    - Extract key learnings from completed task
    - Update procedural memory with new skills
    - Log reflection to episodic memory
    - Update codebase knowledge graph

  Daily Dream (end of day, ~5 minutes):
    - Review all episodes from the day
    - Identify patterns across multiple tasks
    - Consolidate episodic memories into semantic facts
    - Prune decayed memories (Ebbinghaus curve)
    - Run contrastive refinement on skills

  Deep Dream (weekly or on-demand, ~30 minutes):
    - Comprehensive codebase re-indexing
    - Cross-project pattern extraction
    - Skill library deduplication and compression
    - Performance benchmarking of skill reliability
    - Generate synthetic practice scenarios for weak areas
```

### Implementation Roadmap

**Phase 1: Foundation (Months 1-2)**
- Layer 0: macOS runtime integration (shell, AppleScript, FSEvents)
- Layer 1: ReAct core loop + Self-Refine
- Local embeddings (EmbeddingGemma) with SQLite vector store
- Basic working memory (context management)

**Phase 2: Memory (Months 3-4)**
- Tier 2: Episodic memory with temporal tracking
- Tier 3: Codebase knowledge graph (auto-indexed)
- MemGPT-style context management (paging in/out)
- Three-factor retrieval (recency + importance + relevance)

**Phase 3: Planning & Tools (Months 5-6)**
- Layer 3: Hierarchical tool retriever + ACI layer
- Layer 4: MAP-inspired modular planner
- Multi-objective optimizer with context-aware priorities
- Reflexion engine for failure recovery

**Phase 4: Meta-Cognition & Learning (Months 7-8)**
- Layer 5: Confidence calibrator + mode selector
- Tier 4: Procedural memory with Bayesian skill selection
- MACLA-inspired contrastive refinement
- Coding constitution enforcement

**Phase 5: Dreaming & Consolidation (Months 9-10)**
- Memory dynamics engine (formation, consolidation, forgetting)
- Micro/daily/deep dream schedules
- World model (predict-before-execute)
- LATS engine for complex decisions

**Phase 6: Integration & Optimization (Months 11-12)**
- End-to-end integration testing
- Performance optimization (latency, memory usage)
- User experience refinement
- Cross-project knowledge transfer

---

## Appendix A: Paper Index by Topic

### Cognitive Architectures
| Paper | Year | Key Contribution |
|-------|------|-----------------|
| CoALA | 2023 | Foundational framework |
| ReAct | 2023 | Reasoning + Acting interleaving |
| Reflexion | 2023 | Verbal reinforcement learning |
| LATS | 2024 | Monte Carlo Tree Search for agents |
| SWE-agent | 2024 | Agent-Computer Interface design |
| AgentBench | 2024 | Multi-environment evaluation |
| DeepCode | 2025 | Channel optimization for code synthesis |
| CodeAct 2.1 | 2025 | Code-as-action paradigm |
| MAP | 2025 | Brain-inspired modular planning |
| Neural Brain | 2025 | Neuroscience-inspired framework |

### Memory Systems
| Paper | Year | Key Contribution |
|-------|------|-----------------|
| Generative Agents | 2023 | Memory stream with recency/importance/relevance |
| MemGPT | 2023 | OS-inspired virtual context management |
| Voyager | 2023 | Skill library as procedural memory |
| AriGraph | 2024 | Episodic + semantic knowledge graph |
| A-MEM | 2025 | Zettelkasten-inspired memory linking |
| Zep/Graphiti | 2025 | Bi-temporal knowledge graph |
| Mem0 | 2025 | Production-ready extraction-update pipeline |
| Memory Survey | 2025 | Comprehensive taxonomy (forms, functions, dynamics) |
| MACLA | 2025 | Bayesian procedural memory |

### Tool Use
| Paper | Year | Key Contribution |
|-------|------|-----------------|
| Toolformer | 2023 | Self-supervised tool learning |
| Gorilla | 2023 | Retrieval-augmented API selection |
| ToolLLM | 2024 | DFSDT for 16,000+ APIs |
| AnyTool | 2024 | Hierarchical retrieval + self-reflection |

### Autonomous Decision-Making
| Paper | Year | Key Contribution |
|-------|------|-----------------|
| Constitutional AI | 2022 | Principle-based self-improvement |
| Agentic UQ | 2026 | System 1/2 uncertainty management |
| Auto Reward | 2025 | Automatic reward modeling from environment |
| CLMDP | 2025 | Multi-objective contextual planning |

### Self-Improvement
| Paper | Year | Key Contribution |
|-------|------|-----------------|
| Self-Refine | 2023 | Iterative self-feedback |
| GVU Framework | 2025 | Unified theory of self-improvement |
| WebRL | 2024 | Self-evolving online curriculum |
| AgentRR | 2025 | Multi-level experience replay |
| AutoSkill | 2025 | Serving/learning separation |
| LaMer | 2025 | Meta-RL for exploration |
| Lifelong Learning Survey | 2025 | Roadmap for lifelong agent learning |

### Novel Ideas
| Paper | Year | Key Contribution |
|-------|------|-----------------|
| CWM | 2025 | Code world models for state prediction |
| DyMo | 2025 | Dynamics modeling reduces hallucination |
| Dream2Learn | 2026 | Dreaming for continual learning |
| SleepNet/DreamNet | 2025 | Sleep cycles for memory consolidation |
| Self-Evolving Survey | 2025 | Taxonomy of agent evolution |
| Anthropic Harnesses | 2025 | Progress files for multi-context agents |

---

## Appendix B: Key URLs and Resources

### Primary Papers (arXiv)
- CoALA: https://arxiv.org/abs/2309.02427
- ReAct: https://arxiv.org/abs/2210.03629
- Reflexion: https://arxiv.org/abs/2303.11366
- LATS: https://arxiv.org/abs/2310.04406
- SWE-agent: https://arxiv.org/abs/2405.15793
- AgentBench: https://arxiv.org/abs/2308.03688
- MemGPT: https://arxiv.org/abs/2310.08560
- Generative Agents: https://arxiv.org/abs/2304.03442
- Voyager: https://arxiv.org/abs/2305.16291
- Toolformer: https://arxiv.org/abs/2302.04761
- Gorilla: https://arxiv.org/abs/2305.15334
- ToolLLM: https://arxiv.org/abs/2307.16789
- AnyTool: https://arxiv.org/abs/2402.04253
- Self-Refine: https://arxiv.org/abs/2303.17651
- Constitutional AI: https://arxiv.org/abs/2212.08073
- A-MEM: https://arxiv.org/abs/2502.12110
- Zep: https://arxiv.org/abs/2501.13956
- Mem0: https://arxiv.org/abs/2504.19413
- MACLA: https://arxiv.org/abs/2512.18950
- DeepCode: https://arxiv.org/abs/2512.07921
- Neural Brain: https://arxiv.org/abs/2505.07634
- CWM: https://arxiv.org/abs/2510.02387
- MAP: https://arxiv.org/abs/2310.00194
- Memory Survey: https://arxiv.org/abs/2512.13564
- Self-Improving Agents: https://arxiv.org/abs/2512.02731
- Auto Reward: https://arxiv.org/abs/2502.12130
- Agentic UQ: https://arxiv.org/html/2601.15703
- Self-Evolving Survey: https://arxiv.org/abs/2507.21046
- Lifelong Learning: https://arxiv.org/abs/2501.07278
- AgentRR: https://arxiv.org/abs/2505.17716
- LaMer: https://arxiv.org/abs/2512.16848

### Research Blogs
- Anthropic Multi-Agent: https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic Long-Running Agents: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Devin 2.0: https://cognition.ai/blog/devin-2
- OpenHands CodeAct: https://openhands.dev/blog/openhands-codeact-21-an-open-state-of-the-art-software-development-agent

### GitHub Repositories
- SWE-agent: https://github.com/SWE-agent/SWE-agent
- Voyager: https://github.com/MineDojo/Voyager
- Reflexion: https://github.com/noahshinn/reflexion
- LATS: https://github.com/lapisrocks/LanguageAgentTreeSearch
- Gorilla: https://github.com/ShishirPatil/gorilla
- ToolLLM: https://github.com/beijixiong1/ToolLLM
- AnyTool: https://github.com/dyabel/AnyTool
- A-MEM: https://github.com/agiresearch/A-mem
- MACLA: https://github.com/S-Forouzandeh/MACLA-LLM-Agents-AAMAS-Conference
- Zep/Graphiti: https://github.com/getzep/graphiti
- Mem0: https://github.com/mem0ai/mem0
- Agent Memory Paper List: https://github.com/Shichun-Liu/Agent-Memory-Paper-List
- Self-Evolving Agents: https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents

---

*This research survey was compiled on March 9, 2026. The field moves rapidly -- papers referenced here represent the state of knowledge as of this date. The CORTEX architecture proposal synthesizes insights from all surveyed papers into a novel design that has not been previously proposed in the literature.*
