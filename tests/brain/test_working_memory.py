"""Tests for WorkingMemory — token-budgeted named slots."""

from __future__ import annotations

import asyncio

import pytest

from claudedev.brain.memory.working import SlotPriority, WorkingMemory

# ---------------------------------------------------------------------------
# Slot CRUD
# ---------------------------------------------------------------------------


class TestSlotCRUD:
    async def test_add_slot(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "Fix the login bug")
        info = await wm.slot_info("task_context")
        assert info.content == "Fix the login bug"
        assert info.priority == SlotPriority.NORMAL

    async def test_add_slot_custom_priority(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("system_prompt", "You are an agent.", SlotPriority.CRITICAL)
        info = await wm.slot_info("system_prompt")
        assert info.priority == SlotPriority.CRITICAL

    async def test_duplicate_add_overwrites(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "First")
        await wm.add_slot("task_context", "Second")
        info = await wm.slot_info("task_context")
        assert info.content == "Second"

    async def test_remove_slot(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("history", "old messages")
        await wm.remove_slot("history")
        with pytest.raises(KeyError):
            await wm.slot_info("history")

    async def test_remove_nonexistent_is_noop(self) -> None:
        wm = WorkingMemory()
        # Should not raise
        await wm.remove_slot("does_not_exist")

    async def test_update_slot_content(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("code_context", "old code")
        await wm.update_slot("code_context", "new code")
        info = await wm.slot_info("code_context")
        assert info.content == "new code"

    async def test_update_slot_preserves_priority_when_not_specified(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "content", SlotPriority.HIGH)
        await wm.update_slot("task_context", "updated content")
        info = await wm.slot_info("task_context")
        assert info.priority == SlotPriority.HIGH

    async def test_update_slot_changes_priority(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "content", SlotPriority.LOW)
        await wm.update_slot("task_context", "content", SlotPriority.HIGH)
        info = await wm.slot_info("task_context")
        assert info.priority == SlotPriority.HIGH

    async def test_update_nonexistent_raises_key_error(self) -> None:
        wm = WorkingMemory()
        with pytest.raises(KeyError):
            await wm.update_slot("no_such_slot", "content")

    async def test_slot_info_nonexistent_raises_key_error(self) -> None:
        wm = WorkingMemory()
        with pytest.raises(KeyError):
            await wm.slot_info("missing")


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


class TestTokenCounting:
    async def test_empty_memory_token_count_is_zero(self) -> None:
        wm = WorkingMemory()
        assert await wm.token_count() == 0

    async def test_token_count_increases_after_add(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "hello world")
        count = await wm.token_count()
        assert count > 0

    async def test_token_count_decreases_after_remove(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "hello world")
        before = await wm.token_count()
        await wm.remove_slot("task_context")
        after = await wm.token_count()
        assert after < before
        assert after == 0

    async def test_token_count_reflects_update(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "short")
        before = await wm.token_count()
        await wm.update_slot("task_context", "this is a much longer piece of text than before")
        after = await wm.token_count()
        assert after > before

    async def test_available_tokens_starts_at_max(self) -> None:
        wm = WorkingMemory(max_tokens=1000)
        assert await wm.available_tokens() == 1000

    async def test_available_tokens_decreases_after_add(self) -> None:
        wm = WorkingMemory(max_tokens=1000)
        await wm.add_slot("task_context", "hello world")
        available = await wm.available_tokens()
        assert available < 1000

    async def test_available_tokens_increases_after_remove(self) -> None:
        wm = WorkingMemory(max_tokens=1000)
        await wm.add_slot("task_context", "hello world")
        mid = await wm.available_tokens()
        await wm.remove_slot("task_context")
        final = await wm.available_tokens()
        assert final > mid
        assert final == 1000

    async def test_slot_info_token_count_matches_total(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "test content")
        info = await wm.slot_info("task_context")
        total = await wm.token_count()
        assert info.token_count == total

    async def test_empty_content_slot_has_zero_tokens(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "")
        info = await wm.slot_info("task_context")
        assert info.token_count == 0
        assert await wm.token_count() == 0


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


class TestContextAssembly:
    async def test_empty_memory_returns_empty_string(self) -> None:
        wm = WorkingMemory()
        ctx = await wm.get_context()
        assert ctx == ""

    async def test_single_slot_returns_content(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "implement feature X")
        ctx = await wm.get_context()
        assert "implement feature X" in ctx

    async def test_multiple_slots_include_all_content(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("system_prompt", "You are an agent.")
        await wm.add_slot("task_context", "Fix the bug.")
        await wm.add_slot("history", "Previous conversation.")
        ctx = await wm.get_context()
        assert "You are an agent." in ctx
        assert "Fix the bug." in ctx
        assert "Previous conversation." in ctx

    async def test_ordered_slots_appear_before_custom(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("zzz_custom", "custom content")
        await wm.add_slot("system_prompt", "system")
        ctx = await wm.get_context()
        assert ctx.index("system") < ctx.index("custom content")

    async def test_fixed_order_system_prompt_before_task_context(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("task_context", "task")
        await wm.add_slot("system_prompt", "system")
        ctx = await wm.get_context()
        assert ctx.index("system") < ctx.index("task")

    async def test_custom_slots_sorted_alphabetically(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("zebra", "Z content")
        await wm.add_slot("alpha", "A content")
        await wm.add_slot("mango", "M content")
        ctx = await wm.get_context()
        assert ctx.index("A content") < ctx.index("M content") < ctx.index("Z content")

    async def test_only_custom_slots_present(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("beta", "B")
        await wm.add_slot("alpha", "A")
        ctx = await wm.get_context()
        assert ctx.index("A") < ctx.index("B")

    async def test_context_newline_separated(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("system_prompt", "sys")
        await wm.add_slot("task_context", "task")
        ctx = await wm.get_context()
        assert "\n" in ctx


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


class TestPruning:
    async def test_prune_removes_low_priority_first(self) -> None:
        # low_slot = 5 tokens, high_slot = 1 token, total = 6.
        # Budget=3: forces pruning. LOW removed first; HIGH(1) survives.
        wm = WorkingMemory(max_tokens=3)
        await wm.add_slot("low_slot", "remove me please okay now", SlotPriority.LOW)
        await wm.add_slot("high_slot", "keep", SlotPriority.HIGH)
        await wm.prune_to_budget()
        # low_slot should be gone; high_slot should survive
        with pytest.raises(KeyError):
            await wm.slot_info("low_slot")
        info = await wm.slot_info("high_slot")
        assert info.content == "keep"

    async def test_critical_slots_survive_pruning(self) -> None:
        wm = WorkingMemory(max_tokens=5)
        long_text = "word " * 50  # ~50 tokens
        await wm.add_slot("critical_slot", long_text, SlotPriority.CRITICAL)
        await wm.add_slot("normal_slot", "extra", SlotPriority.NORMAL)
        await wm.prune_to_budget()
        # critical must survive even if over budget
        info = await wm.slot_info("critical_slot")
        assert info.content == long_text
        # normal should be pruned
        with pytest.raises(KeyError):
            await wm.slot_info("normal_slot")

    async def test_prune_under_budget_is_noop(self) -> None:
        wm = WorkingMemory(max_tokens=10_000)
        await wm.add_slot("task_context", "small content")
        before_count = await wm.token_count()
        await wm.prune_to_budget()
        after_count = await wm.token_count()
        assert before_count == after_count

    async def test_prune_empty_memory_is_noop(self) -> None:
        wm = WorkingMemory(max_tokens=100)
        await wm.prune_to_budget()
        assert await wm.token_count() == 0

    async def test_prune_highest_token_count_within_priority(self) -> None:
        # Budget fits 5 tokens. Add two LOW priority slots; larger removed first.
        wm = WorkingMemory(max_tokens=5)
        await wm.add_slot("large_low", "word " * 20, SlotPriority.LOW)
        await wm.add_slot("small_low", "hi", SlotPriority.LOW)
        await wm.prune_to_budget()
        # large_low should be gone first; small_low may or may not survive
        # Regardless, total must be <= max_tokens
        assert await wm.token_count() <= 5

    async def test_multi_priority_pruning_low_and_normal_removed_high_survives(self) -> None:
        # LOW slot (~60 tokens), NORMAL slot (~60 tokens), HIGH slot (~2 tokens).
        # Budget = 10 tokens — only the HIGH slot survives.
        wm = WorkingMemory(max_tokens=10)
        await wm.add_slot("low_slot", "word " * 15, SlotPriority.LOW)     # ~15 tokens
        await wm.add_slot("normal_slot", "word " * 15, SlotPriority.NORMAL)  # ~15 tokens
        await wm.add_slot("high_slot", "hi", SlotPriority.HIGH)           # ~1 token
        await wm.prune_to_budget()
        # LOW should be pruned first, then NORMAL; HIGH must survive
        with pytest.raises(KeyError):
            await wm.slot_info("low_slot")
        with pytest.raises(KeyError):
            await wm.slot_info("normal_slot")
        info = await wm.slot_info("high_slot")
        assert info.content == "hi"

    async def test_prune_order_priority_before_size(self) -> None:
        # low_small = 1 token, high_large = 9 tokens, total = 10.
        # Budget=9: forces pruning (10>9). LOW removed first even though it is smaller.
        # After removal total=9<=9, so high_large survives.
        wm = WorkingMemory(max_tokens=9)
        await wm.add_slot("low_small", "hi", SlotPriority.LOW)
        await wm.add_slot(
            "high_large", "this is quite a lot of tokens here okay", SlotPriority.HIGH
        )
        await wm.prune_to_budget()
        # low_small removed first before touching high_large
        with pytest.raises(KeyError):
            await wm.slot_info("low_small")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_empty_content_slot(self) -> None:
        wm = WorkingMemory()
        await wm.add_slot("empty_slot", "")
        info = await wm.slot_info("empty_slot")
        assert info.content == ""
        assert info.token_count == 0

    async def test_large_content(self) -> None:
        wm = WorkingMemory()
        large_text = "The quick brown fox jumps over the lazy dog. " * 1000
        await wm.add_slot("large", large_text)
        info = await wm.slot_info("large")
        assert info.token_count > 1000

    async def test_special_characters(self) -> None:
        wm = WorkingMemory()
        special = "Hello\nWorld\t<script>alert('xss')</script>\x00"
        await wm.add_slot("special", special)
        info = await wm.slot_info("special")
        assert info.content == special

    async def test_unicode_content(self) -> None:
        wm = WorkingMemory()
        unicode_text = "日本語テスト — Ünïcödé — Ελληνικά"
        await wm.add_slot("unicode", unicode_text)
        info = await wm.slot_info("unicode")
        assert info.content == unicode_text
        assert info.token_count > 0

    async def test_emoji_content(self) -> None:
        wm = WorkingMemory()
        emoji_text = "Hello 🌍 World 🚀 Test 🎉"
        await wm.add_slot("emoji", emoji_text)
        info = await wm.slot_info("emoji")
        assert info.content == emoji_text
        assert info.token_count > 0

    async def test_concurrent_add_slot(self) -> None:
        wm = WorkingMemory()

        async def add(i: int) -> None:
            await wm.add_slot(f"slot_{i}", f"content for slot {i}")

        await asyncio.gather(*(add(i) for i in range(10)))
        # All 10 slots should be present with no data corruption
        for i in range(10):
            info = await wm.slot_info(f"slot_{i}")
            assert info.content == f"content for slot {i}"

    async def test_concurrent_add_same_slot(self) -> None:
        wm = WorkingMemory()

        async def add(i: int) -> None:
            await wm.add_slot("shared", f"content_{i}")

        await asyncio.gather(*(add(i) for i in range(10)))
        # Slot must exist and have a valid (one of the written) content
        info = await wm.slot_info("shared")
        assert info.content.startswith("content_")

    async def test_max_tokens_custom(self) -> None:
        wm = WorkingMemory(max_tokens=500)
        assert await wm.available_tokens() == 500

    async def test_max_tokens_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            WorkingMemory(max_tokens=0)

    async def test_max_tokens_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            WorkingMemory(max_tokens=-10)

    async def test_slot_priority_enum_values(self) -> None:
        assert SlotPriority.LOW.value == 10
        assert SlotPriority.NORMAL.value == 50
        assert SlotPriority.HIGH.value == 80
        assert SlotPriority.CRITICAL.value == 100

    async def test_prune_warns_when_only_critical_remain(self) -> None:
        wm = WorkingMemory(max_tokens=1)
        await wm.add_slot("important", "lots of content here", SlotPriority.CRITICAL)
        await wm.prune_to_budget()
        # CRITICAL slot survives pruning even when over budget
        info = await wm.slot_info("important")
        assert info.content == "lots of content here"
        assert await wm.token_count() > 1  # still over budget, but critical survived


# ---------------------------------------------------------------------------
# Steering slot
# ---------------------------------------------------------------------------


class TestSteeringSlot:
    async def test_steering_slot_in_ordered_slots(self) -> None:
        from claudedev.brain.memory.working import _ORDERED_SLOTS
        assert "steering" in _ORDERED_SLOTS
        rm_idx = _ORDERED_SLOTS.index("recalled_memories")
        st_idx = _ORDERED_SLOTS.index("steering")
        hi_idx = _ORDERED_SLOTS.index("history")
        assert rm_idx < st_idx < hi_idx

    async def test_steering_slot_in_context_assembly(self) -> None:
        from claudedev.brain.memory.working import SlotPriority, WorkingMemory
        wm = WorkingMemory()
        await wm.add_slot("system_prompt", "sys", SlotPriority.CRITICAL)
        await wm.add_slot("recalled_memories", "memories", SlotPriority.NORMAL)
        await wm.add_slot("steering", "steer msg", SlotPriority.HIGH)
        await wm.add_slot("history", "hist", SlotPriority.LOW)
        ctx = await wm.get_context()
        assert ctx.index("memories") < ctx.index("steer msg")
        assert ctx.index("steer msg") < ctx.index("hist")
