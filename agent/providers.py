from __future__ import annotations

import json
import os
import re
from typing import Iterator, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request


from config.settings import Settings

SYSTEM_PROMPT = (
    "You are an expert software engineer and coding assistant embedded in a "
    "VS Code-like desktop IDE. When asked to write code, produce clean, "
    "runnable code inside a single fenced code block with the correct "
    "language tag. After the code block, you may add a short explanation. "
    "Never truncate code. Always write complete, working implementations. "
    "Never emit <think>, <thinking>, or any other reasoning/meta tags, and "
    "never show chain-of-thought or step-by-step deliberation -- output only "
    "the final answer."
)

# Matches <think>...</think> / <thinking>...</thinking> blocks (including an
# unterminated opening tag some GGUF models emit when generation is cut off),
# case-insensitively and across newlines.
_THINK_BLOCK_RE = re.compile(
    r"<\s*think(?:ing)?\s*>.*?(?:<\s*/\s*think(?:ing)?\s*>|$)",
    re.IGNORECASE | re.DOTALL,
)


def strip_think_tags(text: str) -> str:
    """Remove any <think>/<thinking> reasoning blocks a model may have emitted,
    regardless of provider. This is a safety net on top of the system-prompt
    instruction not to produce them at all."""
    if not text or "<think" not in text.lower():
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    return cleaned.strip()


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    name = "base"

    def __init__(self, settings: Settings):
        self.settings = settings

    def _messages(self, history: list[dict], workspace_context: Optional[str]) -> list[dict]:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        if workspace_context:
            msgs.append({"role": "system", "content": workspace_context})
        msgs.extend(history)
        return msgs

    def stream(self, history, workspace_context=None, max_tokens=None, **_kwargs) -> Iterator[str]:
        raise NotImplementedError

    def complete(self, history, workspace_context=None, max_tokens=None, **kwargs) -> str:
        text = "".join(self.stream(history, workspace_context, max_tokens, **kwargs))
        return strip_think_tags(text)

    def close(self):
        pass

    def request_stop(self):
        pass


class GGUFProvider(BaseProvider):
    name = "gguf"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._llm = None
        self._stop_requested = False
        self._load()

    def _load(self):
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise ProviderError(
                "llama-cpp-python is not installed in the active Python environment.\n"
                "Run: pip install llama-cpp-python"
            ) from exc

        model_path = self.settings.model_path
        if not model_path or not os.path.isfile(model_path):
            raise ProviderError(f"Model file not found: {model_path}")

        kwargs = dict(
            model_path=model_path,
            n_ctx=self.settings.context_size,
            n_gpu_layers=self.settings.gpu_layers,
            verbose=self.settings.verbose,
        )
        if self.settings.threads is not None:
            kwargs["n_threads"] = self.settings.threads
        self._llm = Llama(**kwargs)

    def _build_prompt(self, history: list[dict], workspace_context: Optional[str]) -> str:
        parts = [f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>"]
        if workspace_context:
            parts.append(f"<|im_start|>system\n{workspace_context}<|im_end|>")
        for msg in history:
            parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
        # Qwen3-family models disable their reasoning mode when the assistant
        # turn is pre-filled with an empty <think></think> block, so the model
        # continues straight into the final answer. Unlike appending "/no_think"
        # to the user's message, this never touches user content, so it can't
        # be misread as part of the actual request.
        parts.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
        return "\n".join(parts)

    def stream(self, history, workspace_context=None, max_tokens=None, **_kwargs) -> Iterator[str]:
        self._stop_requested = False
        prompt = self._build_prompt(history, workspace_context)
        out = self._llm(
            prompt,
            max_tokens=max_tokens or self.settings.max_tokens,
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            repeat_penalty=self.settings.repeat_penalty,
            stop=["<|im_end|>", "<|endoftext|>"],
            echo=False,
            stream=True,
        )
        for chunk in out:
            if self._stop_requested:
                break
            yield chunk["choices"][0]["text"]

    def request_stop(self):
        self._stop_requested = True


class _OpenAICompatibleProvider(BaseProvider):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    extra_headers: dict = {}

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._stop_requested = False
        self._active_response = None

    def stream(self, history, workspace_context=None, max_tokens=None, **_kwargs) -> Iterator[str]:
        if not self.api_key:
            raise ProviderError(f"{self.name}: API key not configured.")

        self._stop_requested = False
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": self._messages(history, workspace_context),
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "max_tokens": max_tokens or self.settings.max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            # urllib's default User-Agent ("Python-urllib/3.x") is routinely blocked
            # by upstream WAFs (this is what caused OpenRouter's 403 "Access denied
            # by security policy" response), so identify as a real client instead.
            "User-Agent": "NovaCode-VSCode-Extension/1.5.0",
        }
        headers.update(self.extra_headers)

        req = urllib_request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=120) as resp:
                self._active_response = resp
                status = getattr(resp, "status", resp.getcode())
                if status != 200:
                    body = resp.read().decode("utf-8", errors="replace")
                    raise ProviderError(f"{self.name} API error {status}: {body[:500]}")
                for raw_line in resp:
                    if self._stop_requested:
                        break
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    token = delta.get("content")
                    if token:
                        yield token
        except urllib_error.HTTPError as exc:
            if self._stop_requested:
                return
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            details = body[:500] if body else str(exc)
            raise ProviderError(f"{self.name} API error {exc.code}: {details}") from exc
        except (urllib_error.URLError, TimeoutError, OSError) as exc:
            if self._stop_requested:
                return
            raise ProviderError(f"{self.name} request failed: {exc}") from exc
        finally:
            self._active_response = None

    def request_stop(self):
        self._stop_requested = True
        if self._active_response is not None:
            try:
                self._active_response.close()
            except Exception:
                pass


class OpenRouterProvider(_OpenAICompatibleProvider):
    name = "openrouter"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.base_url = settings.openrouter_base_url
        self.api_key = settings.openrouter_api_key
        self.model = settings.openrouter_model
        self.extra_headers = {
            "HTTP-Referer": "https://novacode.local",
            "X-Title": "NovaCode AI Chat",
        }


class NvidiaProvider(_OpenAICompatibleProvider):
    name = "nvidia"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.base_url = settings.nvidia_base_url
        self.api_key = settings.nvidia_api_key
        self.model = settings.nvidia_model
        self.extra_headers = {}


class OpenAIProvider(_OpenAICompatibleProvider):
    name = "openai"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.base_url = settings.openai_base_url
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.extra_headers = {}


def create_provider(settings: Settings) -> BaseProvider:
    err = settings.validate_backend()
    if err:
        raise ProviderError(err)
    if settings.backend == "gguf":
        return GGUFProvider(settings)
    if settings.backend == "openrouter":
        return OpenRouterProvider(settings)
    if settings.backend == "nvidia":
        return NvidiaProvider(settings)
    if settings.backend == "openai":
        return OpenAIProvider(settings)
    raise ProviderError(f"Unknown backend: {settings.backend}")