from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    if len(text) < 200:
        return max(1, len(text) // 3)
    code_chars = sum(1 for c in text if c in "{}[]()<>;:=/\\|&!?#@%^~`'\",. ")
    total = len(text)
    if code_chars / max(total, 1) > 0.25:
        return max(1, total // 3)
    return max(1, int(total / 3.5))


def estimate_message_tokens(msg: dict) -> int:
    content = msg.get("content", "") or ""
    overhead = 20
    return overhead + estimate_tokens(content)


def estimate_messages_tokens(messages: list[dict]) -> int:
    return sum(estimate_message_tokens(m) for m in messages)


class ContextBudget:
    def __init__(self, context_size: int, max_response_tokens: int, safety_buffer: float = 0.15):
        self.total = max(1, context_size)
        self.max_response = max(1, max_response_tokens)
        self.buffer = int(self.total * safety_buffer)
        self.available = self.total - self.buffer - self.max_response

    def remaining_for_input(self, used: int) -> int:
        return max(0, self.available - used)


class ContextManager:
    def __init__(self, settings, workspace_context: str = ""):
        self.settings = settings
        self.raw_workspace_context = workspace_context or ""
        self.workspace_index: dict[str, Any] = {}
        self.project_summary: str = ""
        self._workspace_context_tokens = 0

        self._build_workspace_index()

    def _build_workspace_index(self) -> None:
        workspace = getattr(self.settings, "workspace_path", None)
        if not workspace:
            return
        try:
            from tools.code_tools import build_workspace_index
            raw = build_workspace_index(workspace)
            self.raw_workspace_context = raw
            self._workspace_context_tokens = estimate_tokens(raw)
        except Exception as exc:
            logger.debug("Workspace index build failed: %s", exc)
            self._workspace_context_tokens = estimate_tokens(self.raw_workspace_context)

    def build_context(
        self,
        history: list[dict],
        system_prompt: str,
        mode: str = "Chat",
    ) -> tuple[list[dict], dict]:
        system_tokens = estimate_tokens(system_prompt)
        budget = ContextBudget(
            context_size=getattr(self.settings, "context_size", 4096),
            max_response_tokens=getattr(self.settings, "max_tokens", 2048),
        )
        used = system_tokens
        report = {
            "system_tokens": system_tokens,
            "workspace_tokens": 0,
            "history_tokens": 0,
            "total_input_tokens": 0,
            "budget": budget.total,
            "available": budget.available,
            "truncated": False,
        }

        messages: list[dict] = [{"role": "system", "content": system_prompt}]

        ws_limit = budget.remaining_for_input(used)
        ws_text = ""
        if self.raw_workspace_context and ws_limit > 0:
            ws_tokens = self._workspace_context_tokens
            if ws_tokens <= ws_limit:
                ws_text = self.raw_workspace_context
                used += ws_tokens
            else:
                ws_text = self._truncate_text(self.raw_workspace_context, ws_limit)
                used += ws_limit
                report["truncated"] = True
                logger.warning(
                    "Workspace context truncated: %d tokens -> %d tokens",
                    ws_tokens, ws_limit,
                )
            report["workspace_tokens"] = estimate_tokens(ws_text)

        if ws_text:
            messages.append({"role": "system", "content": f"Project context:\n{ws_text}"})

        trimmed, hist_tokens, truncated = self._trim_history(history, budget.remaining_for_input(used))
        used += hist_tokens
        report["history_tokens"] = hist_tokens
        report["truncated"] = report["truncated"] or truncated

        messages.extend(trimmed)
        report["total_input_tokens"] = used
        logger.info(
            "Context budget: total=%d, system=%d, workspace=%d, history=%d, total_input=%d, truncated=%s",
            report["budget"], report["system_tokens"], report["workspace_tokens"],
            report["history_tokens"], report["total_input_tokens"], report["truncated"],
        )
        return messages, report

    def _truncate_text(self, text: str, token_limit: int) -> str:
        char_limit = max(1, token_limit * 3)
        if len(text) <= char_limit:
            return text
        truncated = text[:char_limit]
        return truncated + f"\n\n...[Context truncated. {estimate_tokens(text) - token_limit} tokens omitted]"

    def _trim_history(self, history: list[dict], token_limit: int) -> tuple[list[dict], int, bool]:
        if not history:
            return [], 0, False

        if token_limit <= 0:
            return [], 0, True

        result: list[dict] = []
        used = 0
        truncated = False
        for msg in reversed(history):
            t = estimate_message_tokens(msg)
            if used + t > token_limit and result:
                truncated = True
                break
            result.insert(0, msg)
            used += t

        if len(result) != len(history):
            truncated = True
        return result, used, truncated
