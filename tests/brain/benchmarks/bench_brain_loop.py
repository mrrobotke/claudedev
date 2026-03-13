"""Phase 1 performance benchmarks.

Benchmarks:
- Brain loop latency < 100ms (with mocked bridge)
- Episodic write throughput > 100 writes/sec
- Token counting 100% accuracy vs tiktoken reference
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import tiktoken

from claudedev.brain.cortex import Cortex
from claudedev.brain.integration.claude_bridge import ClaudeResult
from claudedev.brain.memory.episodic import EpisodicStore
from claudedev.brain.memory.working import WorkingMemory
from claudedev.brain.models import EpisodicMemory, Task

if TYPE_CHECKING:
    from pathlib import Path

    from claudedev.brain.config import BrainConfig
    from claudedev.brain.integration.claude_bridge import ClaudeBridge


@pytest.fixture
def fast_bridge(brain_config: BrainConfig) -> ClaudeBridge:
    """Minimal-overhead bridge for latency benchmarks."""
    from claudedev.brain.integration.claude_bridge import ClaudeBridge as _ClaudeBridge

    bridge = _ClaudeBridge.__new__(_ClaudeBridge)
    bridge._model = brain_config.claude_model
    bridge._max_retries = brain_config.max_retries
    bridge.execute_task = AsyncMock(  # type: ignore[method-assign]
        return_value=ClaudeResult(
            content="Done.",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
            tool_use_history=[],
            success=True,
            duration_ms=1.0,
        )
    )
    return bridge


class TestBrainLoopLatency:
    """Brain loop (perceive -> recall -> decide -> act -> remember) must complete < 100ms."""

    async def test_single_task_under_100ms(
        self, brain_config: BrainConfig, fast_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, fast_bridge)
        task = Task(description="Latency benchmark task")

        start = time.perf_counter()
        result = await cortex.run(task)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result.success is True
        assert elapsed_ms < 100, f"Brain loop took {elapsed_ms:.1f}ms (budget: 100ms)"
        await cortex.shutdown()

    async def test_ten_sequential_tasks_average_under_100ms(
        self, brain_config: BrainConfig, fast_bridge: ClaudeBridge
    ) -> None:
        cortex = await Cortex.create(brain_config, fast_bridge)
        n = 10
        start = time.perf_counter()
        for i in range(n):
            result = await cortex.run(Task(description=f"Bench task {i}"))
            assert result.success is True
        total_ms = (time.perf_counter() - start) * 1000
        avg_ms = total_ms / n

        assert avg_ms < 100, f"Average loop: {avg_ms:.1f}ms (budget: 100ms)"
        await cortex.shutdown()

    async def test_cold_start_latency(
        self, brain_config: BrainConfig, fast_bridge: ClaudeBridge
    ) -> None:
        """First task after Cortex.create() must also be < 100ms."""
        start = time.perf_counter()
        cortex = await Cortex.create(brain_config, fast_bridge)
        result = await cortex.run(Task(description="Cold start bench"))
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result.success is True
        assert elapsed_ms < 100, f"Cold start took {elapsed_ms:.1f}ms (budget: 100ms)"
        await cortex.shutdown()


class TestEpisodicWriteThroughput:
    """Episodic store must sustain > 100 writes/sec."""

    async def test_100_writes_under_1_second(self, tmp_path: Path) -> None:
        store = EpisodicStore(db_path=str(tmp_path / "bench.db"))
        await store.initialize()

        episodes = [
            EpisodicMemory(
                task=f"Benchmark task {i}",
                approach="direct",
                outcome="success",
                tools_used=["Edit"],
                files_modified=[f"file_{i}.py"],
                confidence=0.9,
            )
            for i in range(100)
        ]

        start = time.perf_counter()
        for ep in episodes:
            await store.store(ep)
        elapsed = time.perf_counter() - start

        throughput = 100 / elapsed
        assert throughput > 100, f"Throughput: {throughput:.0f} writes/sec (need >100)"
        assert await store.count() == 100
        await store.close()

    async def test_500_writes_sustained(self, tmp_path: Path) -> None:
        store = EpisodicStore(db_path=str(tmp_path / "bench500.db"))
        await store.initialize()

        start = time.perf_counter()
        for i in range(500):
            await store.store(
                EpisodicMemory(
                    task=f"Sustained write {i}",
                    approach="direct",
                    outcome="success",
                    confidence=0.85,
                )
            )
        elapsed = time.perf_counter() - start

        throughput = 500 / elapsed
        assert throughput > 100, f"Sustained throughput: {throughput:.0f} writes/sec (need >100)"
        assert await store.count() == 500
        await store.close()

    async def test_write_then_search_latency(self, tmp_path: Path) -> None:
        """After 200 writes, search must still be fast."""
        store = EpisodicStore(db_path=str(tmp_path / "bench_search.db"))
        await store.initialize()

        for i in range(200):
            await store.store(
                EpisodicMemory(
                    task=f"Authentication fix {i}" if i % 3 == 0 else f"Database task {i}",
                    approach="direct",
                    outcome="success",
                    confidence=0.9,
                )
            )

        start = time.perf_counter()
        results = await store.search("authentication")
        search_ms = (time.perf_counter() - start) * 1000

        assert len(results) > 0
        assert search_ms < 50, f"Search took {search_ms:.1f}ms (budget: 50ms)"
        await store.close()


class TestTokenCountingAccuracy:
    """Token counting must match tiktoken cl100k_base exactly."""

    @pytest.fixture
    def encoding(self) -> tiktoken.Encoding:
        return tiktoken.get_encoding("cl100k_base")

    async def test_empty_string(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=10000)
        expected = len(encoding.encode(""))
        assert wm._count_tokens("") == expected

    async def test_simple_sentence(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=10000)
        text = "The quick brown fox jumps over the lazy dog."
        expected = len(encoding.encode(text))
        assert wm._count_tokens(text) == expected

    async def test_code_snippet(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=10000)
        text = """def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
"""
        expected = len(encoding.encode(text))
        assert wm._count_tokens(text) == expected

    async def test_unicode_content(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=10000)
        text = "Hello world! Bonjour le monde! Hola mundo!"
        expected = len(encoding.encode(text))
        assert wm._count_tokens(text) == expected

    async def test_long_context(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=100000)
        text = "You are the NEXUS brain. " * 500
        expected = len(encoding.encode(text))
        assert wm._count_tokens(text) == expected

    async def test_special_characters(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=10000)
        text = '{"key": "value", "items": [1, 2, 3], "nested": {"a": true}}'
        expected = len(encoding.encode(text))
        assert wm._count_tokens(text) == expected

    async def test_multiline_markdown(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=10000)
        text = """# Heading

- Item 1
- Item 2
  - Sub-item

```python
print("hello")
```
"""
        expected = len(encoding.encode(text))
        assert wm._count_tokens(text) == expected

    async def test_mixed_whitespace(self, encoding: tiktoken.Encoding) -> None:
        wm = WorkingMemory(max_tokens=10000)
        text = "tabs\there\t\tand   multiple   spaces\n\nnewlines"
        expected = len(encoding.encode(text))
        assert wm._count_tokens(text) == expected
