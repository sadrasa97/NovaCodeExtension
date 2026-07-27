from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def summarize_text(text: str, max_tokens: int = 500) -> str:
    if not text:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text
    char_limit = max(1, max_tokens * 3)
    if len(text) <= char_limit:
        return text
    lines = text.splitlines()
    kept: list[str] = []
    chars = 0
    for line in lines:
        if chars + len(line) + 1 > char_limit:
            break
        kept.append(line)
        chars += len(line) + 1
    truncated = text[chars:]
    omitted = estimate_tokens(truncated)
    kept.append(f"\n...[truncated, ~{omitted} tokens omitted]")
    return "\n".join(kept)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    if len(text) < 200:
        return max(1, len(text) // 3)
    code_chars = sum(1 for c in text if c in "{}[]()<>;:=/\\|&!?#@%^~`'\",. ")
    total = len(text)
    if total == 0:
        return 0
    if code_chars / total > 0.25:
        return max(1, total // 3)
    return max(1, int(total / 3.5))


def compress_tool_result(result: str, max_chars: int = 4000) -> str:
    if not result:
        return ""
    if len(result) <= max_chars:
        return result
    lines = result.splitlines()
    kept: list[str] = []
    chars = 0
    for line in lines:
        if chars + len(line) + 1 > max_chars:
            break
        kept.append(line)
        chars += len(line) + 1
    omitted = len(result) - chars
    kept.append(f"\n...[truncated, {omitted} more chars omitted]")
    return "\n".join(kept)


def summarize_tool_calls(history: list[dict], keep_recent: int = 4) -> list[dict]:
    if len(history) <= keep_recent * 2:
        return history
    first = history[0]
    tail_start = max(1, len(history) - keep_recent * 2)
    middle = history[1:tail_start]
    tail = history[tail_start:]

    tool_names: list[str] = []
    for msg in middle:
        content = msg.get("content", "") or ""
        if msg["role"] == "user" and content.startswith("Tool result for"):
            marker = "`" if "`" in content else ""
            if marker:
                try:
                    tool_names.append(content.split(marker)[1])
                except Exception:
                    pass
            else:
                tool_names.append("unknown_tool")

    summary = {
        "role": "user",
        "content": (
            f"[Context summary: {len(middle)} earlier messages removed. "
            f"Tools executed: {', '.join(tool_names) if tool_names else 'none'}. "
            f"Continue from current state.]"
        ),
    }
    return [first, summary] + tail
