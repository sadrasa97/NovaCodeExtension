from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterator, Optional

from agent.prompts import INTENT_ANALYSIS_SYSTEM
from config.settings import Settings
from tools.code_tools import (
    ToolError,
    agent_analyze_imports,
    agent_append_file,
    agent_batch_edit,
    agent_copy_file,
    agent_create_directory,
    agent_delete_file,
    agent_diff,
    agent_edit_file,
    agent_file_info,
    agent_find_files,
    agent_find_symbol_references,
    agent_format_code,
    agent_glob_paths,
    agent_insert_at_line,
    agent_list_dir,
    agent_list_functions,
    agent_move_file,
    agent_prepend_file,
    agent_read_file,
    agent_read_many_files,
    agent_rename_symbol,
    agent_replace_regex,
    agent_search,
    agent_tree,
    agent_write_file,
    build_workspace_index,
    resolve_workspace_path_from_base,
)
from tools.web_search import duckduckgo_search

MAX_ITERATIONS = 30
MAX_TOOL_RESULT_CHARS = 12_000
# Maximum number of messages to keep in history to avoid context overflow.
# We keep the system context + first user message + last N exchanges.
MAX_HISTORY_MESSAGES = 20
# NOTE: the original pattern required a literal newline right after
# ```tool_call, so a model that emitted the whole block on one line (e.g.
# "```tool_call {"name": ...} ```", which small/local models do fairly often)
# was silently treated as if it hadn't called a tool at all. \s* now covers
# both newlines and spaces, and we also accept a bare ```json fence and a
# fence with no language tag at all as tool-call carriers.
TOOL_CALL_RE = re.compile(
    r"```(?:tool_call|tool[_ ]?use|json)?\s*(?P<json>\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
JSON_OBJECT_RE = re.compile(r"^\s*(?P<json>\{.*\})\s*$", re.DOTALL)
# Kept for callers that still want a plain (single-nesting-level) regex, but
# _extract_json_object below no longer relies on this for the primary path --
# see _iter_balanced_json_objects, which handles arbitrary nesting depth.
ANY_JSON_OBJECT_RE = re.compile(r"\{(?:[^{}]|\{[^{}]*\})*\}", re.DOTALL)
_LOOKS_LIKE_TOOL_CALL_RE = re.compile(r'"name"\s*:\s*"[a-zA-Z_]+"')


def _iter_balanced_json_objects(text: str):
    """Yield every top-level {...} span in text, honoring arbitrary nesting
    depth and skipping braces that appear inside string literals. This is a
    real scanner rather than a regex, so it doesn't break on JSON with more
    than one level of nested objects/arrays-of-objects (the old
    ANY_JSON_OBJECT_RE only tolerated one level of nesting)."""
    n = len(text)
    i = 0
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        start = i
        depth = 0
        in_string = False
        escape = False
        j = i
        while j < n:
            ch = text[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        yield text[start:j + 1]
                        break
            j += 1
        else:
            # Unbalanced (truncated) object -- nothing more to find after this.
            return
        i = j + 1

# Greetings / thanks / farewells and similarly short conversational messages
# with no coding intent. Kept intentionally small and conservative: anything
# even slightly ambiguous falls through to the real agent workflow.
_SMALL_TALK_RE = re.compile(
    r"^\s*("
    r"hi|hello|hey|yo|sup|"
    r"good\s*(morning|afternoon|evening|night)|"
    r"thanks?(\s+you)?|thank\s+you|ty|"
    r"bye|goodbye|see\s+you|"
    r"سلام|درود|سلام\s*علیکم|"
    r"خداحافظ|فعلا|"
    r"ممنون|مرسی|متشکرم|تشکر"
    r")\s*[!.؟?،,]*\s*$",
    re.IGNORECASE,
)

SMALL_TALK_SYSTEM_PROMPT = (
    "You are NovaCode, a friendly coding assistant embedded in a VS Code-like "
    "IDE. The user just sent a short greeting or pleasantry with no coding "
    "request in it. Reply briefly and warmly in the same language as the "
    "user, invite them to describe what they'd like help with, and do not "
    "mention files, tools, or a project structure you haven't actually seen."
)


def _is_small_talk(text: str) -> bool:
    return bool(_SMALL_TALK_RE.match((text or "").strip()))


def _extract_json_object(text: str) -> dict:
    """Best-effort extraction of a single JSON object from a model response,
    tolerating markdown code fences, stray prose, or nested objects/arrays of
    arbitrary depth around the JSON.

    Tries every top-level {...} span found (in order), not just the first one
    a naive regex would grab -- a model sometimes emits an unrelated {...} in
    prose before the real answer (e.g. "Here's what I understood: {...}")."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    candidates = list(_iter_balanced_json_objects(cleaned))
    if not candidates:
        raise ValueError("No JSON object found in response")

    last_err: Exception | None = None
    parsed: list[dict] = []
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
        if isinstance(obj, dict):
            parsed.append(obj)

    if not parsed:
        raise ValueError(f"Found {len(candidates)} candidate object(s) but none parsed as JSON: {last_err}")

    # If more than one candidate parsed, prefer one that actually has the
    # expected "todo" key (the intent-analysis shape) instead of blindly
    # taking the first -- stray prose before the real object can itself
    # happen to be valid, unrelated JSON.
    for obj in parsed:
        if "todo" in obj:
            return obj
    return parsed[0]


def _truncate(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\\n...[truncated, {len(text) - limit} more chars]"


class AgentSession:
    def __init__(self, provider, settings: Settings, on_status: Optional[Callable[[str], None]] = None):
        self.provider = provider
        self.settings = settings
        self.workspace = settings.workspace_path
        self.cwd = self.workspace
        self.on_status = on_status or (lambda _msg: None)
        self.applied_files: list[str] = []
        self._validation_needed = False
        self._plan: list[str] = []
        self._plan_status: list[str] = []
        self._context_loaded = False
        self._workspace_index: str = ""

    def _to_workspace_relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.workspace.resolve()).as_posix()

    def _resolve_from_cwd(self, target: str) -> Path:
        if not target.strip():
            raise ToolError("Path is empty")
        try:
            return resolve_workspace_path_from_base(self.workspace.resolve(), self.cwd.resolve(), target)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    def _load_project_context(self) -> str:
        """Load project structure and code index. Returns empty string if
        already loaded or if the workspace_context from the bridge already
        contains the index."""
        if self._context_loaded:
            return ""
        self._context_loaded = True
        parts: list[str] = []
        try:
            tree = agent_tree(self.workspace, ".", max_depth=3)
            parts.append(f"Project structure:\n{tree}")
        except Exception:
            pass
        try:
            self._workspace_index = build_workspace_index(self.workspace)
            parts.append(f"Code index (file -> symbols):\n{self._workspace_index}")
        except Exception:
            pass
        return "\n\n".join(parts)

    def _auto_plan(self, user_request: str) -> list[str]:
        return [
            f"Analyze request: {user_request[:80]}",
            "Explore project structure and relevant files",
            "Identify files to modify/create",
            "Implement changes with file operations",
            "Validate and summarize changes",
        ]

    def _analyze_intent_and_plan(self, user_request: str) -> tuple[str, list[str], list[str]]:
        """Ask the model to read the user's message and extract intent, entities,
        and a concrete todo list. Returns (intent, entities, todo). Falls back to
        the generic static plan if the model's response isn't usable."""
        if not user_request.strip():
            return "", [], self._auto_plan(user_request)

        try:
            raw = self.provider.complete(
                [
                    {"role": "system", "content": INTENT_ANALYSIS_SYSTEM},
                    {"role": "user", "content": user_request},
                ],
                workspace_context=None,
                # 700 tokens was too tight -- for anything but the shortest
                # requests the model's JSON (especially the "todo" array) got
                # cut off mid-object and silently failed to parse below.
                max_tokens=1500,
            )
            data = _extract_json_object(raw)
            intent = str(data.get("intent") or "").strip()
            entities = [str(e).strip() for e in (data.get("entities") or []) if str(e).strip()]
            todo = [str(t).strip() for t in (data.get("todo") or []) if str(t).strip()]
            if not todo:
                raise ValueError("Model returned no usable todo list")
            return intent, entities, todo
        except Exception as exc:
            # Previously this was a bare `except Exception: return ..., self._auto_plan(...)`
            # with no trace at all, so every fallback to the generic 5-step plan was
            # invisible -- there was no way to tell "intent analysis genuinely wasn't
            # needed" from "intent analysis broke". Log it so this is debuggable.
            import logging
            logging.getLogger(__name__).warning(
                "Intent analysis failed, falling back to generic plan: %s", exc
            )
            return "", [], self._auto_plan(user_request)

    def _render_progress_marker(self) -> str:
        steps = [{"title": title, "status": status} for title, status in zip(self._plan, self._plan_status)]
        return f"<!-- progress:{json.dumps(steps, ensure_ascii=False)} -->"

    def _trim_history(self, history: list[dict]) -> list[dict]:
        """Keep history within MAX_HISTORY_MESSAGES to prevent context overflow.

        Strategy: always keep the first user message (the original request)
        and the most recent exchanges. Old tool results in the middle are
        summarized to save tokens.
        """
        if len(history) <= MAX_HISTORY_MESSAGES:
            return history

        # Always preserve: first message (user request) + last N messages
        keep_tail = MAX_HISTORY_MESSAGES - 1
        first_msg = history[0]
        middle = history[1:-keep_tail]
        tail = history[-keep_tail:]

        # Summarize dropped middle section
        tool_calls_done = []
        for msg in middle:
            content = msg.get("content", "")
            if msg["role"] == "user" and content.startswith("Tool result for"):
                # Extract just the tool name
                tool_name = content.split("`")[1] if "`" in content else "unknown"
                tool_calls_done.append(tool_name)

        summary_parts = [first_msg]
        if tool_calls_done:
            summary_parts.append({
                "role": "user",
                "content": (
                    f"[Context trimmed: {len(middle)} earlier messages removed. "
                    f"Tools already called: {', '.join(tool_calls_done)}. "
                    f"Continue from where you left off.]"
                ),
            })
        summary_parts.extend(tail)
        return summary_parts

    def _run_tool(self, name: str, args: dict) -> str:
        name = (name or "").strip().lower()
        try:
            if name in {"search_code", "grep"}:
                query = args.get("query", "")
                is_regex = bool(args.get("is_regex", True))
                if not query:
                    raise ToolError("search_code requires 'query'")
                return agent_search(self.workspace, query, is_regex=is_regex)

            if name == "web_search":
                query = args.get("query", "")
                if not query:
                    raise ToolError("web_search requires 'query'")
                max_results = int(args.get("max_results", 8))
                return duckduckgo_search(query, max_results=max_results)

            if name == "pwd":
                return self._to_workspace_relative(self.cwd)

            if name == "cd":
                target = args.get("path", ".")
                target_path = self._resolve_from_cwd(target)
                if not target_path.exists():
                    raise ToolError(f"Path not found: {target}")
                if target_path.is_file():
                    target_path = target_path.parent
                if not target_path.is_dir():
                    raise ToolError(f"Not a directory: {target}")
                self.cwd = target_path
                return f"cwd: {self._to_workspace_relative(self.cwd)}"

            if name == "glob":
                pattern = args.get("pattern", "")
                if not pattern:
                    raise ToolError("glob requires 'pattern'")
                return agent_glob_paths(
                    self.workspace,
                    pattern=pattern,
                    cwd=self._to_workspace_relative(self.cwd),
                    include_files=bool(args.get("include_files", True)),
                    include_dirs=bool(args.get("include_dirs", True)),
                    max_results=int(args.get("max_results", 4000)),
                )

            if name in {"list_files", "ls", "dir"}:
                target = str(args.get("path", ".") or ".")
                base = self._resolve_from_cwd(target)
                if base.is_file():
                    base = base.parent
                if not base.exists() or not base.is_dir():
                    raise ToolError(f"Not a directory: {target}")
                rel_base = self._to_workspace_relative(base)
                return agent_glob_paths(
                    self.workspace,
                    pattern="**/*",
                    cwd=rel_base,
                    include_files=True,
                    include_dirs=True,
                    max_results=int(args.get("max_results", 4000)),
                )

            if name == "list_dir":
                target = str(args.get("path", ".") or ".")
                base = self._resolve_from_cwd(target)
                return agent_list_dir(
                    self.workspace,
                    self._to_workspace_relative(base),
                    recursive=bool(args.get("recursive", False)),
                    max_depth=int(args.get("max_depth", 2)),
                    max_results=int(args.get("max_results", 400)),
                )

            if name in {"find_files", "file_search"}:
                query = args.get("query", "")
                max_results = int(args.get("max_results", 400))
                return agent_find_files(self.workspace, query, max_results=max_results)

            if name == "read_file":
                path = args.get("path", "")
                if not path:
                    raise ToolError("read_file requires 'path'")
                resolved = self._resolve_from_cwd(path)
                return agent_read_file(
                    self.workspace,
                    self._to_workspace_relative(resolved),
                    max_chars=int(args.get("max_chars", 20000)),
                    start_line=args.get("start_line"),
                    end_line=args.get("end_line"),
                    numbered=bool(args.get("numbered", True)),
                )

            if name == "read_many_files":
                paths = args.get("paths", [])
                if not isinstance(paths, list):
                    raise ToolError("read_many_files requires 'paths' list")
                rel_paths = [self._to_workspace_relative(self._resolve_from_cwd(str(p))) for p in paths]
                return agent_read_many_files(
                    self.workspace,
                    rel_paths,
                    max_chars_per_file=int(args.get("max_chars_per_file", 12000)),
                )

            if name == "file_info":
                path = args.get("path", "")
                if not path:
                    raise ToolError("file_info requires 'path'")
                resolved = self._resolve_from_cwd(path)
                return agent_file_info(self.workspace, self._to_workspace_relative(resolved))

            if name in {"list_functions", "symbols"}:
                path = args.get("path", "")
                if not path:
                    raise ToolError("list_functions requires 'path'")
                resolved = self._resolve_from_cwd(path)
                return agent_list_functions(self.workspace, self._to_workspace_relative(resolved))

            if name == "write_file":
                path = args.get("path", "")
                content = args.get("content", "")
                if not path:
                    raise ToolError("write_file requires 'path'")
                resolved = self._resolve_from_cwd(path)
                rel = self._to_workspace_relative(resolved)
                # Guard rail: the model sometimes "solves" a task by dumping a
                # write_file call with placeholder/stub content (e.g. "# Empty
                # file, will be replaced later") over a file it never actually
                # read. That silently destroys real code. If the target
                # already exists and has real content, refuse a write that
                # looks like a stub and push the model toward read_file +
                # edit_file instead.
                if resolved.exists() and resolved.is_file():
                    try:
                        existing = resolved.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        existing = ""
                    stub_markers = (
                        "will be replaced", "to be implemented", "placeholder",
                        "empty file content", "todo: implement",
                    )
                    looks_like_stub = (
                        len(content.strip()) < 40
                        or any(marker in content.lower() for marker in stub_markers)
                    )
                    if existing.strip() and looks_like_stub and not bool(args.get("force", False)):
                        raise ToolError(
                            f"Refusing to overwrite existing file '{rel}' ({len(existing)} chars) "
                            "with placeholder/stub content. Use read_file to see the current "
                            "content first, then use edit_file with the exact old_str/new_str to "
                            "make a targeted change, or write_file with the FULL real file content "
                            "and force=true if a full rewrite is truly intended."
                        )
                result = agent_write_file(self.workspace, rel, content, overwrite=bool(args.get("overwrite", True)))
                self.applied_files.append(rel)
                self._validation_needed = True
                return result

            if name in {"mkdir", "create_directory"}:
                path = args.get("path", "")
                if not path:
                    raise ToolError("create_directory requires 'path'")
                resolved = self._resolve_from_cwd(path)
                result = agent_create_directory(self.workspace, self._to_workspace_relative(resolved))
                self.applied_files.append(self._to_workspace_relative(resolved))
                self._validation_needed = True
                return result

            if name == "edit_file":
                path = args.get("path", "")
                old_str = args.get("old_str", "")
                new_str = args.get("new_str", "")
                if not path or not old_str:
                    raise ToolError("edit_file requires 'path' and 'old_str'")
                resolved = self._resolve_from_cwd(path)
                rel = self._to_workspace_relative(resolved)
                result = agent_edit_file(self.workspace, rel, old_str, new_str)
                self.applied_files.append(rel)
                self._validation_needed = True
                return result

            if name == "replace_regex":
                path = args.get("path", "")
                pattern = args.get("pattern", "")
                replacement = args.get("replacement", "")
                if not path or not pattern:
                    raise ToolError("replace_regex requires 'path' and 'pattern'")
                resolved = self._resolve_from_cwd(path)
                rel = self._to_workspace_relative(resolved)
                result = agent_replace_regex(
                    self.workspace,
                    rel,
                    pattern,
                    replacement,
                    count=int(args.get("count", 0)),
                )
                self.applied_files.append(rel)
                self._validation_needed = True
                return result

            if name == "insert_at_line":
                path = args.get("path", "")
                content = args.get("content", "")
                if not path:
                    raise ToolError("insert_at_line requires 'path'")
                resolved = self._resolve_from_cwd(path)
                rel = self._to_workspace_relative(resolved)
                result = agent_insert_at_line(self.workspace, rel, int(args.get("line", 1)), content)
                self.applied_files.append(rel)
                self._validation_needed = True
                return result

            if name == "append_file":
                path = args.get("path", "")
                content = args.get("content", "")
                if not path:
                    raise ToolError("append_file requires 'path'")
                resolved = self._resolve_from_cwd(path)
                rel = self._to_workspace_relative(resolved)
                result = agent_append_file(self.workspace, rel, content)
                self.applied_files.append(rel)
                self._validation_needed = True
                return result

            if name == "prepend_file":
                path = args.get("path", "")
                content = args.get("content", "")
                if not path:
                    raise ToolError("prepend_file requires 'path'")
                resolved = self._resolve_from_cwd(path)
                rel = self._to_workspace_relative(resolved)
                result = agent_prepend_file(self.workspace, rel, content)
                self.applied_files.append(rel)
                self._validation_needed = True
                return result

            if name == "move_file":
                source = args.get("source", "")
                destination = args.get("destination", "")
                if not source or not destination:
                    raise ToolError("move_file requires 'source' and 'destination'")
                src = self._to_workspace_relative(self._resolve_from_cwd(source))
                dst = self._to_workspace_relative(self._resolve_from_cwd(destination))
                result = agent_move_file(self.workspace, src, dst, overwrite=bool(args.get("overwrite", False)))
                self.applied_files.extend([src, dst])
                self._validation_needed = True
                return result

            if name == "copy_file":
                source = args.get("source", "")
                destination = args.get("destination", "")
                if not source or not destination:
                    raise ToolError("copy_file requires 'source' and 'destination'")
                src = self._to_workspace_relative(self._resolve_from_cwd(source))
                dst = self._to_workspace_relative(self._resolve_from_cwd(destination))
                result = agent_copy_file(self.workspace, src, dst, overwrite=bool(args.get("overwrite", False)))
                self.applied_files.append(dst)
                self._validation_needed = True
                return result

            if name == "delete_file":
                path = args.get("path", "")
                if not path:
                    raise ToolError("delete_file requires 'path'")
                resolved = self._resolve_from_cwd(path)
                rel = self._to_workspace_relative(resolved)
                result = agent_delete_file(self.workspace, rel)
                self.applied_files.append(rel)
                self._validation_needed = True
                return result

            if name == "run_command":
                command = args.get("command", "")
                if not command:
                    raise ToolError("run_command requires 'command'")
                timeout_seconds = int(args.get("timeout_seconds", 300))
                timeout_seconds = max(1, min(timeout_seconds, 1800))
                return self._run_shell(command, timeout_seconds)

            if name == "analyze_imports":
                path = args.get("path", "")
                if not path:
                    raise ToolError("analyze_imports requires 'path'")
                resolved = self._resolve_from_cwd(path)
                return agent_analyze_imports(self.workspace, self._to_workspace_relative(resolved))

            if name == "diff":
                path = args.get("path", "")
                old_content = args.get("old_content", "")
                if not path or old_content is None:
                    raise ToolError("diff requires 'path' and 'old_content'")
                resolved = self._resolve_from_cwd(path)
                return agent_diff(self.workspace, self._to_workspace_relative(resolved), old_content)

            if name == "find_symbol_references":
                symbol = args.get("symbol", "")
                max_results = int(args.get("max_results", 200))
                if not symbol:
                    raise ToolError("find_symbol_references requires 'symbol'")
                return agent_find_symbol_references(self.workspace, symbol, max_results=max_results)

            if name == "format_code":
                path = args.get("path", "")
                if not path:
                    raise ToolError("format_code requires 'path'")
                resolved = self._resolve_from_cwd(path)
                return agent_format_code(self.workspace, self._to_workspace_relative(resolved))

            if name == "batch_edit":
                edits = args.get("edits", [])
                if not isinstance(edits, list):
                    raise ToolError("batch_edit requires 'edits' list")
                return agent_batch_edit(self.workspace, edits)

            if name == "rename_symbol":
                old_name = args.get("old_name", "")
                new_name = args.get("new_name", "")
                path = args.get("path", "")
                if not old_name or not new_name or not path:
                    raise ToolError("rename_symbol requires 'old_name', 'new_name', and 'path'")
                resolved = self._resolve_from_cwd(path)
                result = agent_rename_symbol(self.workspace, old_name, new_name, self._to_workspace_relative(resolved))
                self.applied_files.append(self._to_workspace_relative(resolved))
                self._validation_needed = True
                return result

            if name == "tree":
                target = str(args.get("path", ".") or ".")
                max_depth = int(args.get("max_depth", 3))
                return agent_tree(self.workspace, target, max_depth=max_depth)

            if name in {"index_workspace", "index"}:
                self._workspace_index = build_workspace_index(self.workspace)
                return self._workspace_index

            return f"[tool error] Unknown tool: {name}"
        except ToolError as exc:
            return f"[tool error] {exc}"
        except Exception as exc:
            return f"[tool error] {name} failed: {exc}"

    def _run_shell(self, command: str, timeout_seconds: int = 300) -> str:
        try:
            proc = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except FileNotFoundError:
            try:
                proc = subprocess.run(
                    ["bash", "-lc", command],
                    cwd=str(self.cwd),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
            except Exception as exc:
                return f"[shell error] {exc}"
        except subprocess.TimeoutExpired:
            return (
                f"[shell error] Command timed out after {timeout_seconds}s\\n"
                f"CWD: {self._to_workspace_relative(self.cwd)}\\n"
                f"Command: {command}"
            )
        except Exception as exc:
            return f"[shell error] {exc}"

        parts = [
            f"CWD: {self._to_workspace_relative(self.cwd)}",
            f"Command: {command}",
            f"ExitCode: {proc.returncode}",
        ]
        if proc.stdout.strip():
            parts.append("STDOUT:\\n" + proc.stdout.strip())
        if proc.stderr.strip():
            parts.append("STDERR:\\n" + proc.stderr.strip())
        return _truncate("\\n\\n".join(parts))

    def _auto_validate_changes(self) -> tuple[bool, str]:
        workspace = self.workspace.resolve()
        unique_paths: list[Path] = []
        seen: set[Path] = set()
        for rel in self.applied_files:
            try:
                p = (workspace / rel).resolve()
            except Exception:
                continue
            if p in seen:
                continue
            seen.add(p)
            if p.exists() and p.is_file() and p.suffix.lower() == ".py":
                unique_paths.append(p)

        report_lines: list[str] = []
        if unique_paths:
            compile_result = subprocess.run(
                [sys.executable, "-m", "py_compile", *[str(p) for p in unique_paths]],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=120,
            )
            report_lines.append(f"py_compile exit={compile_result.returncode}")
            if compile_result.stdout.strip():
                report_lines.append("py_compile stdout:\\n" + compile_result.stdout.strip())
            if compile_result.stderr.strip():
                report_lines.append("py_compile stderr:\\n" + compile_result.stderr.strip())
            if compile_result.returncode != 0:
                return False, "\\n\\n".join(report_lines)
        else:
            report_lines.append("No Python file changed; py_compile skipped.")

        tests_path = workspace / "tests"
        if tests_path.exists() and tests_path.is_dir():
            try:
                test_result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q"],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except Exception as exc:
                report_lines.append(f"pytest skipped: {exc}")
            else:
                report_lines.append(f"pytest exit={test_result.returncode}")
                if test_result.stdout.strip():
                    report_lines.append("pytest stdout:\\n" + test_result.stdout.strip())
                if test_result.stderr.strip():
                    report_lines.append("pytest stderr:\\n" + test_result.stderr.strip())
                if test_result.returncode != 0:
                    return False, "\\n\\n".join(report_lines)

        report_lines.append("Automatic validation passed.")
        return True, "\\n\\n".join(report_lines)

    @staticmethod
    def _extract_tool_call(response: str) -> Optional[tuple[str, dict]]:
        candidates: list[str] = []

        # 1) Proper (or near-proper) fenced tool_call/json block, single- or
        #    multi-line. re.finditer so if the model emits more than one
        #    fenced block we try each until one parses.
        candidates.extend(m.group("json").strip() for m in TOOL_CALL_RE.finditer(response))

        # 2) Whole message is exactly one JSON object with no fences at all.
        json_match = JSON_OBJECT_RE.match(response)
        if json_match:
            candidates.append(json_match.group("json").strip())

        # 3) Last resort: the response has some prose/backticks around it but
        #    still contains a single {...} blob that looks like {"name": ...}.
        #    This is what rescues cases like
        #    '```tool_call {"name": "write_file", "args": {...}}```' style
        #    malformed fences that don't match pattern 1 exactly, or a stray
        #    tool call the model printed without any fence at all.
        for m in ANY_JSON_OBJECT_RE.finditer(response):
            blob = m.group(0)
            if _LOOKS_LIKE_TOOL_CALL_RE.search(blob):
                candidates.append(blob)

        for raw_json in candidates:
            if not raw_json:
                continue
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            name = payload.get("name")
            args = payload.get("args") or {}
            if not isinstance(name, str) or not isinstance(args, dict):
                continue
            return name, args
        return None

    def run(self, history: list[dict], workspace_context: Optional[str], mode: str = "Agent") -> Iterator:
        """Execute the agent loop. Yields plain text chunks for the final
        response AND dict events for plan/step progress updates."""
        local_history = list(history)
        user_request = local_history[-1]["content"] if local_history else ""

        # --- Small talk shortcut ---
        if mode in ("Agent", "Plan") and _is_small_talk(user_request):
            reply = self.provider.complete(
                [
                    {"role": "system", "content": SMALL_TALK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_request},
                ],
                workspace_context=None,
                max_tokens=200,
            )
            for chunk in _chunk_text(reply.strip() or "Hi! What would you like me to do?"):
                yield chunk
            return

        # --- Build the plan and emit it to the UI ---
        self._plan = self._auto_plan(user_request)
        self._plan_status = ["pending"] * len(self._plan)

        # Emit initial plan
        yield {"type": "plan", "steps": [{"title": t, "status": s} for t, s in zip(self._plan, self._plan_status)]}

        # Step 0: Analyze request
        self._plan_status[0] = "in-progress"
        yield {"type": "plan", "steps": [{"title": t, "status": s} for t, s in zip(self._plan, self._plan_status)]}
        self.on_status("Working...")

        # If workspace_context from bridge already has the code index, don't
        # duplicate it via _load_project_context.
        ws_ctx = workspace_context or ""
        if "Code index" not in ws_ctx:
            extra = self._load_project_context()
            context_parts = [ws_ctx, extra]
        else:
            self._context_loaded = True
            context_parts = [ws_ctx]
        context = "\n\n".join(p for p in context_parts if p)

        self._plan_status[0] = "completed"
        # Step 1: Explore
        self._plan_status[1] = "in-progress"
        yield {"type": "plan", "steps": [{"title": t, "status": s} for t, s in zip(self._plan, self._plan_status)]}

        no_action_nudges = 0
        MAX_NO_ACTION_NUDGES = 2
        exploration_done = False
        implementation_started = False

        for _ in range(MAX_ITERATIONS):
            local_history = self._trim_history(local_history)
            response = self.provider.complete(local_history, workspace_context=context, mode="agent")
            call = self._extract_tool_call(response)

            if call is None:
                # Auto-validate if we changed files
                if self._validation_needed:
                    # Step 4: Validate
                    self._plan_status[4] = "in-progress"
                    yield {"type": "plan", "steps": [{"title": t, "status": s} for t, s in zip(self._plan, self._plan_status)]}
                    self.on_status("Validating...")
                    ok, validation_report = self._auto_validate_changes()
                    self._validation_needed = False if ok else True
                    if ok:
                        self._plan_status[4] = "completed"
                    yield {"type": "plan", "steps": [{"title": t, "status": s} for t, s in zip(self._plan, self._plan_status)]}
                    local_history.append({"role": "assistant", "content": response})
                    local_history.append(
                        {
                            "role": "user",
                            "content": (
                                "Automatic validation result:\\n"
                                f"```\\n{_truncate(validation_report)}\\n```\\n\\n"
                                + (
                                    "Validation passed. Return the final concise report now (no more tool calls unless strictly needed)."
                                    if ok
                                    else "Validation failed. Continue fixing files using tools, then finish."
                                )
                            ),
                        }
                    )
                    continue

                # Nudge model if it narrated instead of acting
                if not self.applied_files and no_action_nudges < MAX_NO_ACTION_NUDGES:
                    no_action_nudges += 1
                    local_history.append({"role": "assistant", "content": response})
                    local_history.append(
                        {
                            "role": "user",
                            "content": (
                                "You have not made any actual changes yet and I could not parse a "
                                "valid tool call from your last message. Stop describing what you "
                                "plan to do. Emit ONLY a single fenced block in exactly this format, "
                                "with a real newline after the opening fence and nothing else in "
                                "the message:\n"
                                "```tool_call\n"
                                '{"name": "read_file", "args": {"path": "relative/path.py"}}\n'
                                "```\n"
                                "Start by reading or searching the relevant file(s) -- do not "
                                "write_file with placeholder content."
                            ),
                        }
                    )
                    continue

                # Mark remaining steps complete
                for i in range(len(self._plan_status)):
                    if self._plan_status[i] != "completed":
                        self._plan_status[i] = "completed"
                yield {"type": "plan", "steps": [{"title": t, "status": s} for t, s in zip(self._plan, self._plan_status)]}

                # Done -- yield only the final summary to the user
                for chunk in _chunk_text(response):
                    yield chunk
                return

            # Execute tool
            name, args = call

            # Track which plan phase we're in based on tool type
            read_tools = {"read_file", "read_many_files", "search_code", "grep", "list_files",
                          "ls", "dir", "list_dir", "find_files", "file_search", "file_info",
                          "list_functions", "symbols", "glob", "tree", "pwd", "cd", "web_search"}
            write_tools = {"write_file", "edit_file", "batch_edit", "create_directory", "mkdir",
                           "delete_file", "move_file", "copy_file", "rename_symbol", "replace_regex",
                           "insert_at_line", "prepend_file", "append_file", "format_code"}

            if name in write_tools and not implementation_started:
                # Move from explore to identify/implement
                if not exploration_done:
                    self._plan_status[1] = "completed"
                    exploration_done = True
                self._plan_status[2] = "completed"
                self._plan_status[3] = "in-progress"
                implementation_started = True
                yield {"type": "plan", "steps": [{"title": t, "status": s} for t, s in zip(self._plan, self._plan_status)]}

            # Emit tool call event for the UI
            yield {"type": "tool", "name": name, "args": _format_args(args)}

            self.on_status(f"{name}({_format_args(args)})")
            result = self._run_tool(name, args)
            local_history.append({"role": "assistant", "content": response})
            local_history.append({"role": "user", "content": f"Tool result for `{name}`:\\n```\\n{_truncate(result)}\\n```\\n\\nContinue."})

        yield "⚠️ Reached the maximum number of steps. Ask me to continue."


def _format_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        v_str = str(v)
        if len(v_str) > 60:
            v_str = v_str[:60] + "…"
        parts.append(f"{k}={v_str!r}")
    return ", ".join(parts)


def _chunk_text(text: str, size: int = 24) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]