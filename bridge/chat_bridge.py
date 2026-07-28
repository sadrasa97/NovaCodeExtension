from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path


def _respond(ok: bool, **payload) -> None:
    print(json.dumps({"ok": ok, **payload}, ensure_ascii=False))


def _stream_chunk(text: str) -> None:
    """Write a single streaming token/chunk as a JSON line to stdout."""
    print(json.dumps({"stream": True, "chunk": text}, ensure_ascii=False), flush=True)


def _stream_end(**payload) -> None:
    """Signal the end of streaming output."""
    print(json.dumps({"stream": True, "done": True, **payload}, ensure_ascii=False), flush=True)


def _stream_event(event_type: str, **payload) -> None:
    """Emit a structured agent event (plan, step status, tool call, etc.)."""
    print(json.dumps({"stream": True, "event": event_type, **payload}, ensure_ascii=False), flush=True)


if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _project_root() -> Path:
    here = Path(__file__).resolve()
    extension_root = here.parent.parent
    # Hard-pin to extension-local runtime modules so external repo changes
    # cannot alter extension behavior.
    if (extension_root / "agent" / "providers.py").is_file() and (extension_root / "config" / "settings.py").is_file():
        return extension_root
    raise RuntimeError(
        "Extension-local runtime modules are missing. Expected: agent/providers.py and config/settings.py under vscode-extension-starter"
    )


def _referenced_files_context(workspace: str | None, prompt: str) -> str:
    """Lightweight retrieval step for Chat mode: if the user's message names a
    file (e.g. "explain readme.md"), find it and pull in its actual content --
    WITHOUT dumping the whole workspace index/tree into the model's context.
    Search first, then hand the model only what it needs."""
    import re as _re

    if not workspace or not prompt:
        return ""
    root = Path(workspace).expanduser()
    if not root.exists() or not root.is_dir():
        return ""

    # Grab plausible "name.ext" tokens from the user's message.
    candidates = _re.findall(r"[A-Za-z0-9_\-./\\]+\.[A-Za-z0-9]{1,8}", prompt)
    if not candidates:
        return ""

    try:
        from tools.code_tools import agent_find_files, agent_read_file
    except Exception:
        return ""

    seen: set[str] = set()
    sections: list[str] = []
    for token in candidates:
        base = Path(token).name
        if base in seen:
            continue
        seen.add(base)
        try:
            matches = agent_find_files(root, base, max_results=5)
        except Exception:
            continue
        if not matches or matches.strip() == "(no matches)":
            continue
        first_match = matches.splitlines()[0].strip()
        if not first_match or first_match.endswith("/"):
            continue
        try:
            content = agent_read_file(root, first_match, max_chars=12000)
        except Exception:
            continue
        sections.append(f"### {first_match}\n```\n{content}\n```")
        if len(sections) >= 3:  # don't let one message pull in half the repo
            break

    if not sections:
        return ""
    return "Relevant file(s) referenced in the user's message:\n\n" + "\n\n".join(sections)


def _dynamic_context(workspace: str | None, prompt: str) -> tuple[str, dict]:
    """Build optimized dynamic context using lazy loading.
    Only loads files relevant to the user's query instead of the full codebase."""
    if not workspace or not prompt:
        return "", {}
    root = Path(workspace).expanduser()
    if not root.exists() or not root.is_dir():
        return "", {}
    try:
        from agent.context_manager import build_lazy_context
        return build_lazy_context(root, prompt)
    except Exception:
        return "", {}


def _environment_context(workspace: str | None) -> str:
    """Get environment/terminal context for the model."""
    if not workspace:
        return ""
    try:
        from tools.terminal_tools import get_directory_context
        return get_directory_context(Path(workspace))
    except Exception:
        return ""


def _handle_terminal_command(payload: dict) -> int:
    """Handle a terminal command execution request."""
    command = payload.get("command", "")
    shell_type = payload.get("shell_type", "auto")
    cwd = payload.get("cwd")
    workspace = payload.get("workspace")

    if not command:
        _respond(False, error="No command provided")
        return 1

    try:
        from tools.terminal_tools import run_terminal_command
        work_dir = Path(cwd) if cwd else (Path(workspace) if workspace else None)
        result = run_terminal_command(
            command=command,
            cwd=work_dir,
            shell_type=shell_type,
            timeout=30,
            safe_mode=True,
        )
        _respond(True, **result)
        return 0
    except Exception as exc:
        _respond(False, error=str(exc))
        return 1


def _handle_summarize(payload: dict) -> int:
    """Handle a summarization request."""
    text = payload.get("text", "")
    max_tokens = int(payload.get("max_tokens", 500))

    if not text:
        _respond(False, error="No text provided")
        return 1

    try:
        from agent.summarizer import summarize_text, estimate_tokens
        summary = summarize_text(text, max_tokens=max_tokens)
        token_count = estimate_tokens(summary)
        _respond(True, summary=summary, tokens=token_count)
        return 0
    except Exception as exc:
        _respond(False, error=str(exc))
        return 1


def _handle_enhance_prompt(payload: dict, settings) -> int:
    """Handle prompt enhancement request."""
    prompt = payload.get("prompt", "")
    workspace = payload.get("workspace")

    if not prompt:
        _respond(False, error="No prompt provided")
        return 1

    try:
        from agent.prompts import ENHANCE_PROMPT_SYSTEM
        from agent.providers import create_provider

        # Build minimal workspace context for the enhancer
        ws_context = ""
        if workspace:
            ws_context = _workspace_tree(workspace)

        provider = create_provider(settings)
        try:
            enhanced = provider.complete(
                [
                    {"role": "system", "content": ENHANCE_PROMPT_SYSTEM},
                    {"role": "user", "content": f"Original request: {prompt}\n\nWorkspace structure:\n{ws_context}"},
                ],
                workspace_context=None,
                max_tokens=1500,
            )
            _stream_chunk(enhanced)
            _stream_end()
            return 0
        finally:
            provider.close()
    except Exception as exc:
        _respond(False, error=str(exc))
        return 1


def _workspace_context(workspace: str | None) -> str:
    if not workspace:
        return ""
    root = Path(workspace).expanduser()
    if not root.exists() or not root.is_dir():
        return ""

    tree_output = _workspace_tree(workspace)

    # Build a compact symbol index so the agent knows where every function,
    # class, and method lives without reading every file.
    index_output = ""
    try:
        from tools.code_tools import build_workspace_index
        index_output = build_workspace_index(root)
    except Exception:
        pass

    parts = []
    if tree_output:
        parts.append(f"Project structure:\n{tree_output}")
    if index_output:
        parts.append(f"Code index (file -> symbols):\n{index_output}")
    return "\n\n".join(parts) if parts else f"Workspace directory: {root}"


def _workspace_tree(workspace: str | None) -> str:
    if not workspace:
        return ""
    root = Path(workspace).expanduser()
    if not root.exists() or not root.is_dir():
        return ""

    try:
        from tools.code_tools import agent_tree
        return agent_tree(root, ".", max_depth=3)
    except Exception:
        return ""


_COMPATIBLE_RANGE = ((3, 10), (3, 12))
_BUNDLED_PY_VERSION = "3.12.7"
_BUNDLED_PY_DIR_NAME = f"gguf-embedded-python-{_BUNDLED_PY_VERSION}"


def _is_compatible_version(major: int, minor: int) -> bool:
    return _COMPATIBLE_RANGE[0] <= (major, minor) <= _COMPATIBLE_RANGE[1]


def _current_python_is_compatible() -> bool:
    return _is_compatible_version(*sys.version_info[:2])


def _runtime_config_dir() -> Path:
    # Mirrors config.settings.CONFIG_DIR without importing it (that module isn't
    # guaranteed to be importable yet when this runs).
    return Path.home() / ".gguf_code_agent"


def _probe_python(exe: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [exe, "-c", "import sys;print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return None
        major_s, minor_s = out.stdout.strip().split()
        return int(major_s), int(minor_s)
    except Exception:
        return None


def _windows_python_candidates() -> list[str]:
    candidates: list[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        programs_dir = Path(local_app_data) / "Programs" / "Python"
        if programs_dir.is_dir():
            for sub in sorted(programs_dir.iterdir(), reverse=True):
                exe = sub / "python.exe"
                if exe.is_file():
                    candidates.append(str(exe))
    for base in ("C:/Program Files/Python312", "C:/Program Files/Python311",
                 "C:/Program Files/Python310", "C:/Python312", "C:/Python311", "C:/Python310"):
        exe = Path(base) / "python.exe"
        if exe.is_file():
            candidates.append(str(exe))
    return candidates


def _find_compatible_python() -> str | None:
    """Look for a Python 3.10-3.12 interpreter already installed on this machine."""
    if _current_python_is_compatible():
        return sys.executable

    if sys.platform == "win32":
        for ver in ("3.12", "3.11", "3.10"):
            try:
                out = subprocess.run(
                    ["py", f"-{ver}", "-c", "import sys;print(sys.executable)"],
                    capture_output=True, text=True, timeout=15,
                )
                if out.returncode == 0 and out.stdout.strip():
                    return out.stdout.strip()
            except Exception:
                continue
        for exe in _windows_python_candidates():
            version = _probe_python(exe)
            if version and _is_compatible_version(*version):
                return exe
    else:
        import shutil as _shutil
        for name in ("python3.12", "python3.11", "python3.10"):
            found = _shutil.which(name)
            if found:
                version = _probe_python(found)
                if version and _is_compatible_version(*version):
                    return found
    return None


def _bootstrap_embedded_python() -> str | None:
    """Download and prepare a private, self-contained Python 3.12 runtime.

    Only supported on Windows (matches the official embeddable distribution
    llama-cpp-python wheels target). Cached under ~/.gguf_code_agent so this
    only runs once. Returns the path to the bootstrapped python.exe, or None
    if the bootstrap could not complete (no network, etc.).
    """
    if sys.platform != "win32":
        return None

    import urllib.request
    import zipfile

    target_dir = _runtime_config_dir() / _BUNDLED_PY_DIR_NAME
    python_exe = target_dir / "python.exe"
    marker = target_dir / ".ready"
    if python_exe.is_file() and marker.is_file():
        return str(python_exe)

    try:
        target_dir.mkdir(parents=True, exist_ok=True)

        zip_url = (
            f"https://www.python.org/ftp/python/{_BUNDLED_PY_VERSION}/"
            f"python-{_BUNDLED_PY_VERSION}-embed-amd64.zip"
        )
        zip_path = target_dir / "python-embed.zip"
        urllib.request.urlretrieve(zip_url, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target_dir)
        zip_path.unlink(missing_ok=True)

        # The embeddable distribution ships with site-packages disabled and pip
        # unavailable by default; enable both so we can install dependencies.
        for pth_file in target_dir.glob("python*._pth"):
            text = pth_file.read_text(encoding="utf-8")
            text = text.replace("#import site", "import site")
            if "import site" not in text:
                text += "\nimport site\n"
            pth_file.write_text(text, encoding="utf-8")

        get_pip_path = target_dir / "get-pip.py"
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", get_pip_path)
        subprocess.check_call([str(python_exe), str(get_pip_path), "--no-warn-script-location"])
        get_pip_path.unlink(missing_ok=True)

        subprocess.check_call(
            [str(python_exe), "-m", "pip", "install", "-r", str(_project_root() / "requirements.txt")]
        )
        marker.write_text("ok", encoding="utf-8")
        return str(python_exe)
    except Exception:
        return None


def _relaunch_under_interpreter(python_exe: str) -> int:
    """Re-run this bridge script under a compatible interpreter and mirror its output."""
    try:
        result = subprocess.run(
            [python_exe, str(Path(__file__).resolve())] + sys.argv[1:],
            capture_output=True, text=True, timeout=600,
        )
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        return result.returncode
    except Exception as exc:
        _respond(False, error=f"Failed to relaunch under compatible Python ({python_exe}): {exc}")
        return 1


def _gguf_python_version_error() -> str | None:
    major, minor = sys.version_info[:2]
    if not _is_compatible_version(major, minor):
        return (
            f"GGUF backend is running under Python {major}.{minor}, but llama-cpp-python wheels "
            "are only published for Python 3.10-3.12, and no compatible interpreter (installed or "
            "auto-bootstrapped) could be prepared automatically on this machine.\n"
            "Install Python 3.12 (or 3.10/3.11), or set novacode.pythonPath to an existing "
            "3.10-3.12 python.exe, and retry."
        )
    return None


def _ensure_gguf_dependency() -> None:
    version_error = _gguf_python_version_error()
    if version_error:
        raise RuntimeError(version_error)

    try:
        import llama_cpp  # type: ignore  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get("NOVACODE_SKIP_AUTO_INSTALL") == "1":
        raise RuntimeError(
            "llama-cpp-python is not installed in the active Python environment.\n"
            "Run: python -m pip install -r requirements.txt"
        )

    try:
        install_env = os.environ.copy()
        if sys.platform == "win32":
            short_tmp = Path.home() / "TMP"
            try:
                short_tmp.mkdir(parents=True, exist_ok=True)
            except OSError:
                short_tmp = Path.cwd()
            install_env["TMP"] = str(short_tmp)
            install_env["TEMP"] = str(short_tmp)
            install_env["TMPDIR"] = str(short_tmp)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(_project_root() / "requirements.txt")],
            env=install_env,
        )
    except Exception as exc:
        raise RuntimeError(
            "llama-cpp-python is not installed in the active Python environment.\n"
            "Run: python -m pip install -r requirements.txt"
        ) from exc

    try:
        import llama_cpp  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "llama-cpp-python is still unavailable after installation.\n"
            "Run: python -m pip install -r requirements.txt"
        ) from exc


def main() -> int:
    if len(sys.argv) < 2:
        _respond(False, error="Missing bridge payload.")
        return 1

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        _respond(False, error=f"Invalid bridge payload: {exc}")
        return 1

    root = _project_root()
    sys.path.insert(0, str(root))
    os.chdir(root)

    # Handle special command types that don't need full model setup
    command_type = payload.get("command_type")
    if command_type == "terminal":
        return _handle_terminal_command(payload)
    if command_type == "summarize":
        return _handle_summarize(payload)

    requested_backend = payload.get("backend") or "gguf"
    if requested_backend == "gguf" and not _current_python_is_compatible():
        alt_python = _find_compatible_python() or _bootstrap_embedded_python()
        if alt_python and Path(alt_python).resolve() != Path(sys.executable).resolve():
            return _relaunch_under_interpreter(alt_python)
        # No compatible interpreter available anywhere and bootstrap failed (e.g. offline,
        # non-Windows without a 3.10-3.12 install). Fall through so the normal
        # _ensure_gguf_dependency() call below raises a clear, actionable error.

    try:
        from config.settings import Settings
        from agent.providers import create_provider

        settings = Settings.load()
        settings.backend = payload.get("backend") or settings.backend
        settings.model_path = payload.get("model_path") or settings.model_path
        settings.context_size = int(payload.get("context_size") or settings.context_size)
        settings.gpu_layers = int(payload.get("gpu_layers") if payload.get("gpu_layers") is not None else settings.gpu_layers)
        settings.threads = payload.get("threads")
        settings.temperature = float(payload.get("temperature") or settings.temperature)
        settings.max_tokens = int(payload.get("max_tokens") or settings.max_tokens)
        settings.openrouter_api_key = payload.get("openrouter_api_key") or settings.openrouter_api_key
        settings.openrouter_model = payload.get("openrouter_model") or settings.openrouter_model
        settings.nvidia_api_key = payload.get("nvidia_api_key") or settings.nvidia_api_key
        settings.nvidia_model = payload.get("nvidia_model") or settings.nvidia_model
        settings.openai_api_key = payload.get("openai_api_key") or settings.openai_api_key
        settings.openai_base_url = payload.get("openai_base_url") or settings.openai_base_url
        settings.openai_model = payload.get("openai_model") or settings.openai_model
        settings.deepseek_api_key = payload.get("deepseek_api_key") or settings.deepseek_api_key
        settings.deepseek_model = payload.get("deepseek_model") or settings.deepseek_model
        settings.workspace = payload.get("workspace") or settings.workspace

        if settings.backend == "gguf":
            _ensure_gguf_dependency()

        mode = payload.get("mode") or "Chat"
        prompt = payload.get("prompt") or ""
        if not prompt.strip():
            _respond(False, error="Prompt is empty.")
            return 1

        # Handle prompt enhancement request
        if command_type == "enhance_prompt":
            return _handle_enhance_prompt(payload, settings)

        from agent.prompts import CHAT_SYSTEM_PROMPT, AGENT_SYSTEM_PROMPT, PLAN_SYSTEM_PROMPT, SEARCH_SYSTEM_PROMPT, ENHANCE_PROMPT_SYSTEM

        mode_prompts = {
            "Chat": CHAT_SYSTEM_PROMPT,
            "Agent": AGENT_SYSTEM_PROMPT,
            "Plan": PLAN_SYSTEM_PROMPT,
            "WebSearch": SEARCH_SYSTEM_PROMPT,
        }
        system_prompt = mode_prompts.get(mode, CHAT_SYSTEM_PROMPT)

        # Override provider's default system prompt
        from agent import providers as _prov
        _prov.SYSTEM_PROMPT = system_prompt

        history = [{
            "role": "user",
            "content": prompt,
        }]
        provider = create_provider(settings)
        try:
            if mode in ("Agent", "Plan", "WebSearch"):
                from agent.tools_agent import AgentSession

                def _on_status(msg: str) -> None:
                    _stream_event("status", message=msg)

                session = AgentSession(provider, settings, on_status=_on_status)
                chunks: list[str] = []
                for item in session.run(history, workspace_context=_workspace_context(settings.workspace)):
                    # The agent yields either plain text chunks or dict events
                    if isinstance(item, dict):
                        _stream_event(item.get("type", "status"), **{k: v for k, v in item.items() if k != "type"})
                    else:
                        _stream_chunk(item)
                        chunks.append(item)
                # Append modified files summary
                if session.applied_files:
                    unique_files = list(dict.fromkeys(session.applied_files))
                    files_section = "\n\n---\n\n**📁 Modified Files:**\n"
                    for f in unique_files:
                        files_section += f"- `{f}`\n"
                    _stream_chunk(files_section)
                    chunks.append(files_section)
                text = "".join(chunks)
                _stream_end(modified_files=list(dict.fromkeys(session.applied_files)))
            else:
                # Chat mode
                from agent.providers import strip_think_tags
                from agent.tools_agent import _is_small_talk, SMALL_TALK_SYSTEM_PROMPT

                if _is_small_talk(prompt):
                    # Skip workspace indexing entirely for greetings/thanks/etc:
                    # this is what made a plain "hi" pay the cost of scanning
                    # the whole project.
                    reply = provider.complete(
                        [
                            {"role": "system", "content": SMALL_TALK_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        workspace_context=None,
                        max_tokens=200,
                    )
                    reply = reply.strip() or "Hi! What would you like help with?"
                    for i in range(0, len(reply), 24):
                        _stream_chunk(reply[i:i + 24])
                    _stream_end()
                    return 0

                # Real question: use dynamic context (lazy loading) to only
                # include files relevant to the user's query, plus environment
                # context for terminal/path awareness.
                env_ctx = _environment_context(settings.workspace)
                dynamic_ctx, ctx_metadata = _dynamic_context(settings.workspace, prompt)
                file_ctx = _referenced_files_context(settings.workspace, prompt)

                ws_ctx_parts = []
                if env_ctx:
                    ws_ctx_parts.append(f"Environment:\n{env_ctx}")
                if dynamic_ctx:
                    ws_ctx_parts.append(dynamic_ctx)
                if file_ctx:
                    ws_ctx_parts.append(file_ctx)
                ws_ctx = "\n\n".join(p for p in ws_ctx_parts if p)

                # Track token usage for status dashboard
                from agent.summarizer import estimate_tokens as _est_tokens
                context_tokens = _est_tokens(ws_ctx)
                prompt_tokens = _est_tokens(prompt)

                raw_chunks: list[str] = []
                for token in provider.stream(
                    history,
                    workspace_context=ws_ctx,
                    max_tokens=settings.max_tokens,
                ):
                    raw_chunks.append(token)
                    _stream_chunk(token)
                # Emit token usage metadata for the status dashboard
                response_tokens = _est_tokens("".join(raw_chunks))
                _stream_end(
                    token_usage={
                        "context": context_tokens,
                        "prompt": prompt_tokens,
                        "response": response_tokens,
                        "total": context_tokens + prompt_tokens + response_tokens,
                        "files_loaded": ctx_metadata.get("files_loaded", []),
                    }
                )
        finally:
            provider.close()

        return 0
    except Exception as exc:
        _respond(False, error=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())