# ClaudeDev v0.2.0 NEXUS AI Brain — GitHub Issues Summary

Created: 2026-03-09

## Milestones

| # | Milestone | Due Date | Description |
|---|-----------|----------|-------------|
| 1 | `v0.2.0-phase1-foundation` | 2026-03-30 | Phase 1: Foundation (Weeks 1-3) — Core brain loop, working memory, episodic memory, Claude Code bridge, System 1 decision engine |
| 2 | `v0.2.0-phase2-intelligence` | 2026-04-20 | Phase 2: Intelligence (Weeks 4-6) — Embedding engine, LanceDB, knowledge topology, predictive coding, System 2, tool proficiency |
| 3 | `v0.2.0-phase3-autonomy` | 2026-05-11 | Phase 3: Autonomy (Weeks 7-9) — Product Owner mode, Coding Constitution, System 3 LATS, confidence calibration, dreaming engine |
| 4 | `v0.2.0-phase4-evolution` | 2026-06-01 | Phase 4: Evolution (Weeks 10-12) — Skill library, cross-project learning, offline dreamer, memory lifecycle, Apple Silicon optimization |

## Labels

| Label | Color | Description |
|-------|-------|-------------|
| `brain:core` | #0052CC | Core brain loop and orchestration |
| `brain:memory` | #5319E7 | Memory system (episodic, semantic, procedural, working) |
| `brain:decision` | #D93F0B | Decision engine and constitution |
| `brain:integration` | #0E8A16 | Claude Code integration and hooks |
| `brain:tools` | #FEF2C0 | Tool registry, proficiency, composition |
| `brain:evolution` | #F9D0C4 | Self-improvement and evolution engine |
| `brain:macos` | #BFD4F2 | macOS-native capabilities |
| `phase-1` | #C5DEF5 | Phase 1: Foundation |
| `phase-2` | #BFD4F2 | Phase 2: Intelligence |
| `phase-3` | #D4C5F9 | Phase 3: Autonomy |
| `phase-4` | #F9D0C4 | Phase 4: Evolution |
| `architecture` | #FBCA04 | Architecture and design decisions |
| `priority:critical` | #B60205 | Must have for milestone |
| `priority:high` | #D93F0B | Important for milestone |
| `priority:medium` | #E4E669 | Nice to have |

## Phase 1: Foundation (Issues #1-#6)

| Issue | Title | Priority | Labels | Dependencies |
|-------|-------|----------|--------|--------------|
| #1 | [NEXUS] Implement core brain loop (Cortex) | critical | brain:core, phase-1 | None |
| #2 | [NEXUS] Implement working memory manager | critical | brain:memory, phase-1 | #1 |
| #3 | [NEXUS] Implement episodic memory store | critical | brain:memory, phase-1 | #2 |
| #4 | [NEXUS] Implement Claude Code bridge via Agent SDK | critical | brain:integration, phase-1 | #1 |
| #5 | [NEXUS] Implement decision engine with System 1 mode | critical | brain:decision, phase-1 | #2, #3 |
| #6 | [NEXUS] Phase 1 integration test suite and quality gates | high | brain:core, phase-1 | #1, #2, #3, #4, #5 |

## Phase 2: Intelligence (Issues #7-#13)

| Issue | Title | Priority | Labels | Dependencies |
|-------|-------|----------|--------|--------------|
| #7 | [NEXUS] Implement local embedding engine via Ollama | critical | brain:memory, brain:macos, phase-2 | Phase 1 (#6) |
| #8 | [NEXUS] Implement semantic knowledge store with LanceDB | critical | brain:memory, phase-2 | #7 |
| #9 | [NEXUS] Implement living knowledge topology (Mind Map) | critical | brain:memory, phase-2 | #7, #8 |
| #10 | [NEXUS] Implement predictive coding engine | critical | brain:decision, phase-2 | #9 |
| #11 | [NEXUS] Implement System 2 deliberation mode | high | brain:decision, phase-2 | #5, #10 |
| #12 | [NEXUS] Implement hierarchical tool registry and proficiency tracker | high | brain:tools, phase-2 | Phase 1 (#6), #3 |
| #13 | [NEXUS] Phase 2 integration test suite | high | brain:core, phase-2 | #7, #8, #9, #10, #11, #12 |

## Phase 3: Autonomy (Issues #14-#19)

| Issue | Title | Priority | Labels | Dependencies |
|-------|-------|----------|--------|--------------|
| #14 | [NEXUS] Implement autonomous Product Owner mode | critical | brain:decision, phase-3 | Phase 2 (#13), #5, #11 |
| #15 | [NEXUS] Implement executable Coding Constitution | critical | brain:decision, phase-3 | #14 |
| #16 | [NEXUS] Implement System 3 strategic exploration mode | high | brain:decision, phase-3 | #10, #11 |
| #17 | [NEXUS] Implement confidence calibration system | high | brain:decision, phase-3 | #14 |
| #18 | [NEXUS] Implement dreaming and memory consolidation engine | critical | brain:memory, brain:evolution, phase-3 | #3, #8, #9 |
| #19 | [NEXUS] Phase 3 integration test suite | high | brain:core, phase-3 | #14, #15, #16, #17, #18 |

## Phase 4: Evolution (Issues #20-#26)

| Issue | Title | Priority | Labels | Dependencies |
|-------|-------|----------|--------|--------------|
| #20 | [NEXUS] Implement Voyager-style skill library with Bayesian reliability | critical | brain:evolution, phase-4 | Phase 3 (#19), #18 |
| #21 | [NEXUS] Implement outcome tracking and pattern extraction | critical | brain:evolution, phase-4 | #20 |
| #22 | [NEXUS] Implement cross-project learning with skill transfer | high | brain:evolution, phase-4 | #20, #21 |
| #23 | [NEXUS] Implement offline dreamer for deep consolidation | high | brain:evolution, brain:macos, phase-4 | #7, #18, #21 |
| #24 | [NEXUS] Implement macOS native tool wrappers and Apple Silicon optimization | high | brain:tools, brain:macos, phase-4 | Phase 3 (#19), #12 |
| #25 | [NEXUS] Implement full memory lifecycle (creation -> consolidation -> pruning) | high | brain:memory, phase-4 | #18, #23 |
| #26 | [NEXUS] Phase 4 integration test suite and final verification | critical | brain:core, phase-4 | #20, #21, #22, #23, #24, #25 |

## Dependency Graph

```
Phase 1 (Foundation):
  #1 Cortex ──────┬──> #2 Working Memory ──┬──> #3 Episodic Store ──┬──> #5 Decision Engine S1
                  │                         │                        │
                  └──> #4 Claude Bridge     └────────────────────────┘
                                                                     │
  #1, #2, #3, #4, #5 ──────────────────────────────────────────────> #6 Phase 1 Integration

Phase 2 (Intelligence):
  #6 ──> #7 Embeddings ──> #8 Semantic Store ──> #9 Mind Map ──> #10 Predictor ──> #11 System 2
  #6 ──> #12 Tool Registry
  #7, #8, #9, #10, #11, #12 ──────────────────────────────────────> #13 Phase 2 Integration

Phase 3 (Autonomy):
  #13 ──> #14 PO Mode ──> #15 Constitution
                      ──> #17 Calibration
  #10, #11 ──> #16 System 3
  #3, #8, #9 ──> #18 Dreaming Engine
  #14, #15, #16, #17, #18 ────────────────────────────────────────> #19 Phase 3 Integration

Phase 4 (Evolution):
  #19 ──> #20 Skill Library ──> #21 Outcome Tracker ──> #22 Cross-Project Learning
  #18, #21 ──> #23 Offline Dreamer
  #19, #12 ──> #24 macOS Tools
  #18, #23 ──> #25 Memory Lifecycle
  #20, #21, #22, #23, #24, #25 ───────────────────────────────────> #26 Final Verification
```

## Summary Statistics

- **Total Milestones**: 4
- **Total Labels**: 15
- **Total Issues**: 26
  - Phase 1: 6 issues (5 critical, 1 high)
  - Phase 2: 7 issues (4 critical, 3 high)
  - Phase 3: 6 issues (3 critical, 3 high)
  - Phase 4: 7 issues (3 critical, 4 high)
- **Critical Path**: #1 -> #2 -> #3 -> #5 -> #6 -> #7 -> #8 -> #9 -> #10 -> #11 -> #13 -> #14 -> #15 -> #19 -> #20 -> #21 -> #22 -> #26
