from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Iterable


class ToolError(RuntimeError):
    pass


IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "node_modules_old",
    "__pycache__",
    "dist",
    "build",
    "out",
}

TEXT_EXTENSIONS = {
    "py", "ts", "tsx", "js", "jsx", "json", "md", "txt", "yml", "yaml", "toml",
    "ini", "cfg", "env", "sh", "ps1", "bat", "sql", "html", "css", "xml", "svg",
    "go", "rs", "java", "c", "cpp", "h", "hpp", "cs", "rb", "php", "swift", "kt", "lua", "pl", "r", "dart",
}

SYMBOL_PATTERNS = [
    (re.compile(r"^\s*class\s+([A-Za-z_$][\w$]*)"), "class"),
    (re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"), "function"),
    (re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*[:{]"), "method"),
    (re.compile(r"^\s*(?:export\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)"), "symbol"),
]


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def resolve_workspace_path_from_base(workspace: Path, base: Path, target: str) -> Path:
    workspace = workspace.resolve()
    base = base.resolve()
    if not _within(workspace, base):
        raise ValueError("Base path is outside workspace")

    raw = Path(target).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (base / raw).resolve()
    if not _within(workspace, candidate):
        raise ValueError(f"Path escapes workspace: {target}")
    return candidate


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def _is_probably_text(path: Path) -> bool:
    ext = path.suffix.lower().lstrip(".")
    return not ext or ext in TEXT_EXTENSIONS


def _relative(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def _line_slice(lines: list[str], start_line: int | None, end_line: int | None) -> tuple[int, int]:
    total = len(lines)
    start = 1 if start_line is None else max(1, int(start_line))
    end = total if end_line is None else min(total, int(end_line))
    if end < start:
        return start, start - 1
    return start, end


def _numbered_lines(lines: Iterable[str], first_line: int) -> str:
    return "\n".join(f"{index:>5} | {line}" for index, line in enumerate(lines, start=first_line))


def agent_glob_paths(
    workspace: Path,
    pattern: str,
    cwd: str = ".",
    include_files: bool = True,
    include_dirs: bool = True,
    max_results: int = 4000,
) -> str:
    workspace = workspace.resolve()
    base = resolve_workspace_path_from_base(workspace, workspace, cwd)

    results: list[str] = []
    for p in sorted(base.glob(pattern)):
        if len(results) >= max_results:
            break
        rel = p.resolve().relative_to(workspace)
        if _is_ignored(rel):
            continue
        if p.is_file() and include_files:
            results.append(rel.as_posix())
        elif p.is_dir() and include_dirs:
            results.append(rel.as_posix() + "/")

    if not results:
        return "(no matches)"
    return "\n".join(results)


def agent_list_dir(workspace: Path, path: str = ".", recursive: bool = False, max_depth: int = 2, max_results: int = 400) -> str:
    workspace = workspace.resolve()
    base = resolve_workspace_path_from_base(workspace, workspace, path)
    if not base.exists() or not base.is_dir():
        raise ToolError(f"Not a directory: {path}")

    results: list[str] = []
    base_depth = len(base.parts)
    iterator = base.rglob("*") if recursive else base.iterdir()
    for item in sorted(iterator):
        if len(results) >= max_results:
            break
        rel = item.resolve().relative_to(workspace)
        if _is_ignored(rel) or item.name.startswith("."):
            continue
        depth = len(item.parts) - base_depth
        if recursive and depth > max_depth:
            continue
        suffix = "/" if item.is_dir() else ""
        results.append(rel.as_posix() + suffix)

    if not results:
        return "(empty directory)"
    if len(results) == max_results:
        results.append(f"... (showing first {max_results} entries)")
    return "\n".join(results)


def agent_read_file(
    workspace: Path,
    path: str,
    max_chars: int = 20000,
    start_line: int | None = None,
    end_line: int | None = None,
    numbered: bool = True,
) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")
    if not _is_probably_text(target):
        raise ToolError(f"Refusing to read non-text file: {path}")

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    first, last = _line_slice(lines, start_line, end_line)
    selected = lines[first - 1:last]
    text = _numbered_lines(selected, first) if numbered else "\n".join(selected)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n...[truncated, {len(text) - max_chars} more chars]"
    return text


def agent_read_many_files(workspace: Path, paths: list[str], max_chars_per_file: int = 12000) -> str:
    if not paths:
        raise ToolError("read_many_files requires at least one path")
    chunks: list[str] = []
    for item in paths[:20]:
        chunks.append(f"--- {item} ---")
        chunks.append(agent_read_file(workspace, item, max_chars=max_chars_per_file))
    if len(paths) > 20:
        chunks.append(f"... skipped {len(paths) - 20} more files")
    return "\n".join(chunks)


def agent_file_info(workspace: Path, path: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists():
        raise ToolError(f"Path not found: {path}")

    rel = target.relative_to(workspace).as_posix()
    stat = target.stat()
    kind = "directory" if target.is_dir() else "file"
    return "\n".join([
        f"path: {rel}",
        f"type: {kind}",
        f"size: {stat.st_size}",
        f"modified: {int(stat.st_mtime)}",
    ])


def agent_list_functions(workspace: Path, path: str, max_results: int = 500) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")

    results: list[str] = []
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    rel = target.relative_to(workspace).as_posix()
    for index, line in enumerate(lines, start=1):
        for pattern, kind in SYMBOL_PATTERNS:
            match = pattern.search(line)
            if match:
                results.append(f"{rel}:{index}: {kind} {match.group(1)}")
                break
        if len(results) >= max_results:
            break

    return "\n".join(results) if results else "(no functions or symbols found)"


def agent_write_file(workspace: Path, path: str, content: str, overwrite: bool = True) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and not overwrite:
        raise ToolError(f"File already exists: {path}")

    target.write_text(content, encoding="utf-8")
    return f"Wrote file: {target.relative_to(workspace).as_posix()}"


def agent_create_directory(workspace: Path, path: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    target.mkdir(parents=True, exist_ok=True)
    return f"Created directory: {_relative(workspace, target)}"


def agent_edit_file(workspace: Path, path: str, old_str: str, new_str: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")

    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(old_str)
    if count == 0:
        raise ToolError("old_str not found in file")
    if count > 1:
        raise ToolError(f"old_str matched {count} times; expected exactly once")

    updated = text.replace(old_str, new_str, 1)
    target.write_text(updated, encoding="utf-8")
    return f"Edited file: {target.relative_to(workspace).as_posix()}"


def agent_replace_regex(workspace: Path, path: str, pattern: str, replacement: str, count: int = 0) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")
    if not pattern:
        raise ToolError("replace_regex requires 'pattern'")

    text = target.read_text(encoding="utf-8", errors="replace")
    try:
        updated, replacements = re.subn(pattern, replacement, text, count=max(0, int(count)), flags=re.MULTILINE)
    except re.error as exc:
        raise ToolError(f"Invalid regex: {exc}") from exc
    if replacements == 0:
        raise ToolError("regex matched 0 times")
    target.write_text(updated, encoding="utf-8")
    return f"Edited file: {_relative(workspace, target)} ({replacements} replacement(s))"


def agent_insert_at_line(workspace: Path, path: str, line: int, content: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    insert_at = max(0, min(len(lines), int(line) - 1))
    inserted = content.splitlines()
    updated = lines[:insert_at] + inserted + lines[insert_at:]
    target.write_text("\n".join(updated) + ("\n" if updated else ""), encoding="utf-8")
    return f"Inserted {len(inserted)} line(s) at {_relative(workspace, target)}:{insert_at + 1}"


def agent_append_file(workspace: Path, path: str, content: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(content)
    return f"Appended to file: {_relative(workspace, target)}"


def agent_prepend_file(workspace: Path, path: str, content: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    old = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content + old, encoding="utf-8")
    return f"Prepended to file: {_relative(workspace, target)}"


def agent_move_file(workspace: Path, source: str, destination: str, overwrite: bool = False) -> str:
    workspace = workspace.resolve()
    src = resolve_workspace_path_from_base(workspace, workspace, source)
    dst = resolve_workspace_path_from_base(workspace, workspace, destination)
    if not src.exists():
        raise ToolError(f"Source not found: {source}")
    if dst.exists() and not overwrite:
        raise ToolError(f"Destination already exists: {destination}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved {_relative(workspace, src)} -> {_relative(workspace, dst)}"


def agent_copy_file(workspace: Path, source: str, destination: str, overwrite: bool = False) -> str:
    workspace = workspace.resolve()
    src = resolve_workspace_path_from_base(workspace, workspace, source)
    dst = resolve_workspace_path_from_base(workspace, workspace, destination)
    if not src.exists() or not src.is_file():
        raise ToolError(f"Source file not found: {source}")
    if dst.exists() and not overwrite:
        raise ToolError(f"Destination already exists: {destination}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"Copied {_relative(workspace, src)} -> {_relative(workspace, dst)}"


def agent_delete_file(workspace: Path, path: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists():
        raise ToolError(f"Path not found: {path}")

    if target.is_dir():
        shutil.rmtree(target)
        return f"Deleted directory: {target.relative_to(workspace).as_posix()}"

    target.unlink()
    return f"Deleted file: {target.relative_to(workspace).as_posix()}"


def agent_search(workspace: Path, query: str, is_regex: bool = True, max_results: int = 400) -> str:
    workspace = workspace.resolve()
    try:
        pattern = re.compile(query, re.IGNORECASE) if is_regex else re.compile(re.escape(query), re.IGNORECASE)
    except re.error as exc:
        raise ToolError(f"Invalid regex: {exc}") from exc

    results: list[str] = []
    for root, dirs, files in os.walk(workspace, topdown=True):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        root_path = Path(root)

        for name in files:
            if len(results) >= max_results:
                break
            if name.startswith("."):
                continue

            file_path = root_path / name
            rel = file_path.relative_to(workspace)
            if _is_ignored(rel):
                continue

            ext = file_path.suffix.lower().lstrip(".")
            if ext and ext not in TEXT_EXTENSIONS:
                continue

            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            for i, line in enumerate(lines, start=1):
                if pattern.search(line):
                    results.append(f"{rel.as_posix()}:{i}: {line.strip()}")
                    if len(results) >= max_results:
                        break

        if len(results) >= max_results:
            break

    if not results:
        return "(no matches)"

    if len(results) == max_results:
        results.append(f"... (showing first {max_results} matches)")
    return "\n".join(results)


def agent_find_files(workspace: Path, query: str, max_results: int = 400) -> str:
    workspace = workspace.resolve()
    needle = query.lower().strip()
    if not needle:
        raise ToolError("find_files requires 'query'")

    results: list[str] = []
    for root, dirs, files in os.walk(workspace, topdown=True):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        root_path = Path(root)
        for name in sorted([*dirs, *files]):
            if len(results) >= max_results:
                break
            if name.startswith(".") or needle not in name.lower():
                continue
            p = root_path / name
            rel = p.relative_to(workspace)
            if _is_ignored(rel):
                continue
            results.append(rel.as_posix() + ("/" if p.is_dir() else ""))
        if len(results) >= max_results:
            break

    if not results:
        return "(no matches)"
    if len(results) == max_results:
        results.append(f"... (showing first {max_results} matches)")
    return "\n".join(results)


IMPORT_PATTERNS = [
    re.compile(r"^(?:from\s+([\w.]+)\s+import\s+(.+))"),
    re.compile(r"^(?:import\s+([\w.]+))"),
    re.compile(r"^(?:require\(\s*['\"]([\w./]+)['\"]\s*\))"),
    re.compile(r"^(?:use\s+([\w\\]+))"),
    re.compile(r"^(?:include!\s*\(\s*['\"]([\w./]+)['\"]\s*\))"),
]


def agent_analyze_imports(workspace: Path, path: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    imports: list[str] = []
    for line in lines:
        for pattern in IMPORT_PATTERNS:
            m = pattern.match(line.strip())
            if m:
                imports.append(line.strip())
                break

    rel = target.relative_to(workspace).as_posix()
    if not imports:
        return f"{rel}: (no imports detected)"
    return f"{rel}:\n" + "\n".join(f"  {i}" for i in imports)


def agent_diff(workspace: Path, path: str, old_content: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")

    new_content = target.read_text(encoding="utf-8", errors="replace")
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    changes: list[str] = []
    max_lines = max(len(old_lines), len(new_lines))
    for i in range(max_lines):
        old_line = old_lines[i] if i < len(old_lines) else None
        new_line = new_lines[i] if i < len(new_lines) else None
        if old_line != new_line:
            if old_line is not None:
                changes.append(f"- {i + 1}: {old_line}")
            if new_line is not None:
                changes.append(f"+ {i + 1}: {new_line}")

    rel = target.relative_to(workspace).as_posix()
    if not changes:
        return f"{rel}: (no changes)"
    return f"{rel}:\n" + "\n".join(changes[:200])


def agent_find_symbol_references(workspace: Path, symbol: str, max_results: int = 200) -> str:
    workspace = workspace.resolve()
    if not symbol:
        raise ToolError("find_symbol_references requires 'symbol'")

    pattern = re.compile(re.escape(symbol))
    results: list[str] = []
    for root, dirs, files in os.walk(workspace, topdown=True):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        root_path = Path(root)
        for name in files:
            if len(results) >= max_results:
                break
            if name.startswith("."):
                continue
            file_path = root_path / name
            rel = file_path.relative_to(workspace)
            if _is_ignored(rel):
                continue
            ext = file_path.suffix.lower().lstrip(".")
            if ext and ext not in TEXT_EXTENSIONS:
                continue
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, start=1):
                if pattern.search(line):
                    results.append(f"{rel.as_posix()}:{i}: {line.strip()}")
                    if len(results) >= max_results:
                        break
        if len(results) >= max_results:
            break

    if not results:
        return f"(no references to '{symbol}' found)"
    if len(results) == max_results:
        results.append(f"... (showing first {max_results} references)")
    return "\n".join(results)


def agent_format_code(workspace: Path, path: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {path}")

    ext = target.suffix.lower().lstrip(".")
    content = target.read_text(encoding="utf-8", errors="replace")

    if ext in {"py"}:
        try:
            import black
            mode = black.Mode()
            formatted = black.format_str(content, mode=mode)
            target.write_text(formatted, encoding="utf-8")
            return f"Formatted {target.relative_to(workspace).as_posix()} with black"
        except Exception:
            pass

    if ext in {"js", "ts", "jsx", "tsx"}:
        try:
            import jsbeautifier
            opts = jsbeautifier.default_options()
            opts.indent_size = 2
            formatted = jsbeautifier.beautify(content, opts)
            target.write_text(formatted, encoding="utf-8")
            return f"Formatted {target.relative_to(workspace).as_posix()} with js-beautify"
        except Exception:
            pass

    return f"No formatter available for .{ext}"


def agent_batch_edit(workspace: Path, edits: list[dict]) -> str:
    workspace = workspace.resolve()
    results: list[str] = []
    for edit in edits:
        path = edit.get("path", "")
        old_str = edit.get("old_str", "")
        new_str = edit.get("new_str", "")
        if not path or not old_str:
            results.append(f"[tool error] batch edit requires 'path' and 'old_str'")
            continue
        try:
            resolved = resolve_workspace_path_from_base(workspace, workspace, path)
            text = resolved.read_text(encoding="utf-8", errors="replace")
            count = text.count(old_str)
            if count == 0:
                results.append(f"[tool error] {path}: old_str not found")
                continue
            updated = text.replace(old_str, new_str, 1)
            resolved.write_text(updated, encoding="utf-8")
            results.append(f"Edited {resolved.relative_to(workspace).as_posix()}")
        except Exception as exc:
            results.append(f"[tool error] {path}: {exc}")
    return "\n".join(results) if results else "(no edits applied)"


def agent_rename_symbol(workspace: Path, old_name: str, new_name: str, file_path: str) -> str:
    workspace = workspace.resolve()
    target = resolve_workspace_path_from_base(workspace, workspace, file_path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"File not found: {file_path}")

    text = target.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(r"\b" + re.escape(old_name) + r"\b")
    matches = list(pattern.finditer(text))
    if not matches:
        raise ToolError(f"Symbol '{old_name}' not found in {file_path}")

    updated = pattern.sub(new_name, text)
    target.write_text(updated, encoding="utf-8")
    rel = target.relative_to(workspace).as_posix()
    return f"Renamed {len(matches)} occurrence(s) of '{old_name}' -> '{new_name}' in {rel}"


def agent_tree(workspace: Path, path: str = ".", max_depth: int = 3) -> str:
    workspace = workspace.resolve()
    base = resolve_workspace_path_from_base(workspace, workspace, path)
    if not base.exists() or not base.is_dir():
        raise ToolError(f"Not a directory: {path}")

    lines: list[str] = []
    base_depth = len(base.parts)

    def walk(dir_path: Path, depth: int, prefix: str = "") -> None:
        if depth > max_depth:
            return
        items = sorted(dir_path.iterdir())
        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            rel = item.relative_to(workspace)
            if _is_ignored(rel) or item.name.startswith("."):
                continue
            connector = "└── " if is_last else "├── "
            suffix = "/" if item.is_dir() else ""
            lines.append(f"{prefix}{connector}{item.name}{suffix}")
            if item.is_dir():
                extension = "    " if is_last else "│   "
                walk(item, depth + 1, prefix + extension)

    lines.append(base.name + "/")
    walk(base, 1)
    return "\n".join(lines)
