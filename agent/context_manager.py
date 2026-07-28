"""Dynamic Context Management (Lazy Loading) for NovaCode.

Instead of sending the entire codebase, this module parses the user's request,
identifies relevant directories/modules, and provides only the specific code
snippets or files necessary to resolve the query.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from tools.code_tools import (
    agent_find_files,
    agent_read_file,
    agent_search,
    agent_tree,
    build_workspace_index,
    IGNORED_DIRS,
    TEXT_EXTENSIONS,
)


# Maximum tokens (chars) to include in context
MAX_CONTEXT_CHARS = 30_000
MAX_FILES_IN_CONTEXT = 8
MAX_CHARS_PER_FILE = 8_000


def _extract_file_references(text: str) -> list[str]:
    """Extract file names/paths mentioned in user text."""
    # Match common file patterns: name.ext, path/to/file.ext
    patterns = [
        r'[A-Za-z0-9_\-./\\]+\.[A-Za-z0-9]{1,8}',  # file.ext
        r'`([^`]+\.[A-Za-z0-9]{1,8})`',  # `file.ext` in backticks
    ]
    candidates = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = match.group(1) if match.lastindex else match.group(0)
            # Filter out URLs, version numbers, etc.
            if not candidate.startswith("http") and not re.match(r'^\d+\.\d+', candidate):
                candidates.add(candidate)
    return list(candidates)


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from user request for code search."""
    # Remove common stop words and extract technical terms
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "this", "that", "these",
        "those", "i", "you", "he", "she", "it", "we", "they", "what", "which",
        "who", "when", "where", "why", "how", "all", "each", "every", "both",
        "few", "more", "most", "other", "some", "such", "no", "not", "only",
        "same", "so", "than", "too", "very", "just", "because", "as", "until",
        "while", "of", "at", "by", "for", "with", "about", "against", "between",
        "through", "during", "before", "after", "above", "below", "to", "from",
        "up", "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "and", "but", "or", "nor",
        "if", "my", "your", "his", "her", "its", "our", "their", "me",
        "please", "want", "need", "help", "make", "create", "add", "fix",
        "change", "update", "modify", "implement", "write", "code", "file",
    }

    # Extract words that look like identifiers or technical terms
    words = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text)
    keywords = []
    for word in words:
        lower = word.lower()
        if lower not in stop_words and len(word) > 2:
            keywords.append(word)
    return list(dict.fromkeys(keywords))[:15]  # deduplicate, limit


def _identify_relevant_modules(
    workspace: Path,
    keywords: list[str],
    file_refs: list[str],
) -> list[str]:
    """Identify which files/modules are relevant based on keywords and references."""
    relevant_files: list[str] = []
    scores: dict[str, int] = {}

    # Direct file references get highest priority
    for ref in file_refs:
        try:
            matches = agent_find_files(workspace, Path(ref).name, max_results=5)
            if matches and matches.strip() != "(no matches)":
                for line in matches.splitlines():
                    path = line.strip()
                    if path and not path.endswith("/"):
                        scores[path] = scores.get(path, 0) + 10
        except Exception:
            continue

    # Search for keywords in code
    for keyword in keywords[:8]:  # Limit searches
        try:
            results = agent_search(workspace, rf"\b{re.escape(keyword)}\b", is_regex=True)
            if results and "[no matches]" not in results:
                for line in results.splitlines()[:10]:
                    # Extract file path from search results (format: "path:line: content")
                    if ":" in line:
                        path = line.split(":")[0].strip()
                        if path and not path.startswith("["):
                            scores[path] = scores.get(path, 0) + 1
        except Exception:
            continue

    # Sort by relevance score
    sorted_files = sorted(scores.items(), key=lambda x: -x[1])
    relevant_files = [f for f, _ in sorted_files[:MAX_FILES_IN_CONTEXT]]
    return relevant_files


def build_lazy_context(
    workspace: Path,
    user_prompt: str,
    include_tree: bool = True,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, dict]:
    """Build optimized context by analyzing the user's request.

    Returns:
        tuple of (context_string, metadata_dict)
        metadata_dict contains: files_loaded, total_chars, keywords_used
    """
    if not workspace or not workspace.exists():
        return "", {"files_loaded": [], "total_chars": 0, "keywords_used": []}

    # Step 1: Parse request to identify relevant content
    file_refs = _extract_file_references(user_prompt)
    keywords = _extract_keywords(user_prompt)

    context_parts: list[str] = []
    total_chars = 0
    files_loaded: list[str] = []

    # Step 2: Add compact tree (low cost, high value)
    if include_tree:
        try:
            tree = agent_tree(workspace, ".", max_depth=2)
            if tree:
                tree_section = f"Project structure:\n{tree}"
                context_parts.append(tree_section)
                total_chars += len(tree_section)
        except Exception:
            pass

    # Step 3: Identify and load relevant files
    relevant_files = _identify_relevant_modules(workspace, keywords, file_refs)

    for file_path in relevant_files:
        if total_chars >= max_chars:
            break
        try:
            remaining = max_chars - total_chars
            chars_for_file = min(MAX_CHARS_PER_FILE, remaining)
            content = agent_read_file(
                workspace, file_path,
                max_chars=chars_for_file,
                numbered=True,
            )
            if content:
                section = f"\n### {file_path}\n```\n{content}\n```"
                context_parts.append(section)
                total_chars += len(section)
                files_loaded.append(file_path)
        except Exception:
            continue

    # Step 4: If no files found by search, include workspace index as fallback
    if not files_loaded and total_chars < max_chars // 2:
        try:
            index = build_workspace_index(workspace)
            if index:
                index_section = f"Code index (file -> symbols):\n{index}"
                context_parts.append(index_section)
                total_chars += len(index_section)
        except Exception:
            pass

    context = "\n\n".join(context_parts)
    metadata = {
        "files_loaded": files_loaded,
        "total_chars": total_chars,
        "keywords_used": keywords[:5],
    }

    return context, metadata


def estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 chars for English text)."""
    return len(text) // 4
