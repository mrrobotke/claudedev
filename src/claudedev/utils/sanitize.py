"""XML/HTML sanitization for safe prompt embedding."""

from __future__ import annotations


def sanitize_xml(text: str) -> str:
    """Escape XML/HTML special characters for safe embedding in prompts.

    Replaces ``<`` with ``&lt;`` and ``>`` with ``&gt;`` so that attacker-controlled
    text stored in memory cannot inject new XML tags into Claude prompts.
    """
    return text.replace("<", "&lt;").replace(">", "&gt;")
