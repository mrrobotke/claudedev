"""Working memory for the NEXUS brain.

Token-budgeted named slots with priority-based pruning.
Thread-safe via asyncio.Lock for all mutations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import IntEnum

import structlog
import tiktoken

logger = structlog.get_logger(__name__)


class SlotPriority(IntEnum):
    """Priority levels for working memory slots."""

    LOW = 10
    NORMAL = 50
    HIGH = 80
    CRITICAL = 100


@dataclass
class SlotInfo:
    """Information about a single working memory slot."""

    content: str
    priority: SlotPriority
    token_count: int


# Fixed slot names assembled in order before custom slots.
_ORDERED_SLOTS: tuple[str, ...] = (
    "system_prompt",
    "task_context",
    "code_context",
    "recalled_memories",
    "history",
)


class WorkingMemory:
    """Token-budgeted working memory with named priority slots.

    Slots are assembled for context in a fixed order:
    system_prompt, task_context, code_context, recalled_memories,
    history, then remaining custom slots in alphabetical order.

    CRITICAL slots are never pruned. All mutations are thread-safe
    via a single asyncio.Lock.

    Args:
        max_tokens: Maximum total token budget (default 180_000).
    """

    def __init__(self, max_tokens: int = 180_000) -> None:
        if max_tokens <= 0:
            msg = f"max_tokens must be positive, got {max_tokens}"
            raise ValueError(msg)
        self._max_tokens = max_tokens
        self._slots: dict[str, SlotInfo] = {}
        self._lock = asyncio.Lock()
        self._encoder = tiktoken.get_encoding("cl100k_base")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _count_tokens(self, text: str) -> int:
        """Return the token count for *text* using cl100k_base."""
        return len(self._encoder.encode(text))

    def _total_tokens(self) -> int:
        """Return the current total token count across all slots."""
        return sum(s.token_count for s in self._slots.values())

    # ------------------------------------------------------------------
    # Public API — mutations (all lock-protected)
    # ------------------------------------------------------------------

    async def add_slot(
        self,
        name: str,
        content: str,
        priority: SlotPriority = SlotPriority.NORMAL,
    ) -> None:
        """Add or overwrite a named slot.

        If a slot with *name* already exists it is replaced silently.

        Args:
            name: Slot identifier.
            content: Text content to store.
            priority: Priority level (default NORMAL).
        """
        token_count = self._count_tokens(content)
        info = SlotInfo(content=content, priority=priority, token_count=token_count)
        async with self._lock:
            self._slots[name] = info

    async def remove_slot(self, name: str) -> None:
        """Remove a named slot. No-op if the slot does not exist.

        Args:
            name: Slot identifier to remove.
        """
        async with self._lock:
            self._slots.pop(name, None)

    async def update_slot(
        self,
        name: str,
        content: str,
        priority: SlotPriority | None = None,
    ) -> None:
        """Update the content (and optionally priority) of an existing slot.

        Args:
            name: Slot identifier to update.
            content: New text content.
            priority: New priority. If None, existing priority is kept.

        Raises:
            KeyError: If *name* does not exist.
        """
        token_count = self._count_tokens(content)
        async with self._lock:
            if name not in self._slots:
                raise KeyError(name)
            existing = self._slots[name]
            new_priority = priority if priority is not None else existing.priority
            self._slots[name] = SlotInfo(
                content=content,
                priority=new_priority,
                token_count=token_count,
            )

    async def prune_to_budget(self) -> None:
        """Remove slots until total token count is within max_tokens.

        Pruning order:
        1. Lowest-priority non-CRITICAL slots first.
        2. Within the same priority, highest token count first.
        CRITICAL slots are never pruned.
        """
        async with self._lock:
            self._prune_unlocked()

    # ------------------------------------------------------------------
    # Read-only accessors (no lock needed — Python GIL provides safety
    # for dict reads, but we take the lock for consistency)
    # ------------------------------------------------------------------

    async def get_context(self) -> str:
        """Return all slot contents joined in canonical assembly order.

        Order: system_prompt, task_context, code_context,
        recalled_memories, history, then alphabetically sorted
        custom slots.

        Returns:
            A single string with all slot contents separated by newlines,
            or an empty string if no slots are populated.
        """
        async with self._lock:
            parts: list[str] = []
            seen: set[str] = set()
            for name in _ORDERED_SLOTS:
                if name in self._slots:
                    parts.append(self._slots[name].content)
                    seen.add(name)
            for name in sorted(self._slots):
                if name not in seen:
                    parts.append(self._slots[name].content)
            return "\n".join(parts)

    async def token_count(self) -> int:
        """Return the current total token count across all slots."""
        async with self._lock:
            return self._total_tokens()

    async def available_tokens(self) -> int:
        """Return the number of tokens remaining within the budget."""
        async with self._lock:
            return self._max_tokens - self._total_tokens()

    async def slot_info(self, name: str) -> SlotInfo:
        """Return the SlotInfo for a named slot.

        Args:
            name: Slot identifier.

        Returns:
            The SlotInfo dataclass for that slot.

        Raises:
            KeyError: If *name* does not exist.
        """
        async with self._lock:
            return self._slots[name]

    # ------------------------------------------------------------------
    # Internal helpers (called while lock is held)
    # ------------------------------------------------------------------

    def _prune_unlocked(self) -> None:
        """Prune until within budget. Must be called while lock is held."""
        while self._total_tokens() > self._max_tokens:
            # Collect prunable (non-CRITICAL) slots.
            candidates = [
                (name, info)
                for name, info in self._slots.items()
                if info.priority != SlotPriority.CRITICAL
            ]
            if not candidates:
                logger.warning(
                    "prune_budget_exceeded",
                    total_tokens=self._total_tokens(),
                    max_tokens=self._max_tokens,
                    remaining_slots=len(self._slots),
                )
                break
            # Sort: lowest priority first, then highest token count first.
            candidates.sort(key=lambda t: (t[1].priority, -t[1].token_count))
            victim_name = candidates[0][0]
            del self._slots[victim_name]
