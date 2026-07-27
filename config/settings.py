"""Configuration settings for extension-local NovaCode runtime."""
from __future__ import annotations

import json
from pathlib import Path

VALID_BACKENDS = ["gguf", "openrouter", "nvidia"]
CONFIG_DIR = Path.home() / ".gguf_code_agent"


class Settings:
    def __init__(self) -> None:
        self.backend = "gguf"
        self.model_path = ""
        self.context_size = 16384
        self.threads = None
        self.gpu_layers = -1
        self.temperature = 0.7
        self.top_p = 0.9
        self.repeat_penalty = 1.1
        self.max_tokens = 4096
        self.verbose = False

        self.openrouter_api_key = ""
        self.openrouter_model = ""
        self.openrouter_base_url = "https://openrouter.ai/api/v1"

        self.nvidia_api_key = ""
        self.nvidia_model = ""
        self.nvidia_base_url = "https://integrate.api.nvidia.com/v1"

        self.deepseek_api_key = ""
        self.deepseek_model = "deepseek-chat"

        self.workspace = str(Path.cwd())

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace).expanduser()

    def validate_backend(self) -> str | None:
        if self.backend not in VALID_BACKENDS:
            return f"Unknown backend: {self.backend}"

        if self.backend == "gguf":
            if not self.model_path:
                return "No GGUF model path is set. Choose a model in Model Settings."
            if not Path(self.model_path).expanduser().is_file():
                return f"GGUF model file not found: {self.model_path}"

        elif self.backend == "openrouter":
            if not self.openrouter_api_key:
                return "OpenRouter API key is not set."
            if not self.openrouter_model:
                return "OpenRouter model is not set."

        elif self.backend == "nvidia":
            if not self.nvidia_api_key:
                return "NVIDIA NIM API key is not set."
            if not self.nvidia_model:
                return "NVIDIA NIM model is not set."

        return None

    @classmethod
    def load(cls) -> "Settings":
        settings = cls()
        config_file = CONFIG_DIR / "config.json"
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(settings, key):
                        setattr(settings, key, value)
            except Exception:
                pass
        return settings

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config_file = CONFIG_DIR / "config.json"
        data = {}
        for key, value in vars(self).items():
            if isinstance(value, (str, int, float, bool, type(None), list)):
                data[key] = value
        config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")