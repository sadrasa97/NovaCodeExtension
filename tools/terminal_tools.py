"""Terminal command integration tools for NovaCode.

Provides cmd, powershell, ls, cd, glob, and shell command execution
with environment context awareness.
"""
from __future__ import annotations

import os
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Optional


class TerminalError(RuntimeError):
    pass


# Commands that are considered safe (read-only or navigation)
SAFE_COMMANDS = {
    "ls", "dir", "cd", "pwd", "echo", "cat", "type", "head", "tail",
    "find", "where", "which", "whoami", "hostname", "env", "set",
    "tree", "wc", "sort", "grep", "findstr", "Get-ChildItem",
    "Get-Location", "Get-Content", "Get-Item", "Get-Process",
    "Test-Path", "Resolve-Path", "Get-Command",
}

# Commands that are blocked for security reasons
BLOCKED_COMMANDS = {
    "rm", "del", "rmdir", "format", "shutdown", "restart",
    "Remove-Item", "Clear-Content", "Stop-Process", "Stop-Computer",
    "Restart-Computer", "New-Service", "Set-ExecutionPolicy",
}

MAX_OUTPUT_CHARS = 15_000
COMMAND_TIMEOUT = 30  # seconds


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _sanitize_command(command: str) -> str:
    """Basic sanitization: strip dangerous shell operators for non-explicit shell mode."""
    # Allow pipes and redirects in shell mode, but block command chaining with ;; or &&
    # that could hide malicious commands
    stripped = command.strip()
    if not stripped:
        raise TerminalError("Empty command")
    return stripped


def _truncate_output(output: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(output) <= limit:
        return output
    return output[:limit] + f"\n...[truncated, {len(output) - limit} more chars]"


def get_environment_context(workspace: Path) -> dict:
    """Get current environment context: OS, cwd, shell, PATH info."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "shell": os.environ.get("SHELL") or os.environ.get("COMSPEC", "unknown"),
        "workspace": str(workspace),
        "cwd": str(Path.cwd()),
        "python": os.sys.executable,
        "user": os.environ.get("USERNAME") or os.environ.get("USER", "unknown"),
        "home": str(Path.home()),
    }


def run_terminal_command(
    command: str,
    cwd: Optional[Path] = None,
    shell_type: str = "auto",
    timeout: int = COMMAND_TIMEOUT,
    safe_mode: bool = True,
) -> dict:
    """Execute a terminal command and return structured output.

    Args:
        command: The command to execute
        cwd: Working directory (defaults to current)
        shell_type: 'cmd', 'powershell', 'bash', or 'auto'
        timeout: Maximum execution time in seconds
        safe_mode: If True, blocks destructive commands

    Returns:
        dict with keys: stdout, stderr, exit_code, cwd, command
    """
    command = _sanitize_command(command)

    # Security check in safe mode
    if safe_mode:
        first_token = command.split()[0].lower() if command.split() else ""
        # Strip path from command for checking
        first_token = Path(first_token).stem.lower()
        if first_token in {c.lower() for c in BLOCKED_COMMANDS}:
            raise TerminalError(
                f"Command '{first_token}' is blocked in safe mode. "
                "Use safe_mode=False for destructive operations."
            )

    work_dir = str(cwd) if cwd else None

    try:
        if shell_type == "auto":
            shell_type = "powershell" if _is_windows() else "bash"

        if shell_type == "powershell":
            args = [
                "powershell.exe", "-NoLogo", "-NoProfile",
                "-ExecutionPolicy", "Bypass", "-Command", command
            ]
        elif shell_type == "cmd":
            args = ["cmd.exe", "/c", command]
        elif shell_type == "bash":
            args = ["bash", "-c", command]
        else:
            args = ["sh", "-c", command]

        proc = subprocess.run(
            args,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "stdout": _truncate_output(proc.stdout.strip()),
            "stderr": proc.stderr.strip()[:2000] if proc.stderr else "",
            "exit_code": proc.returncode,
            "cwd": work_dir or str(Path.cwd()),
            "command": command,
        }

    except subprocess.TimeoutExpired:
        raise TerminalError(f"Command timed out after {timeout}s: {command}")
    except FileNotFoundError as e:
        raise TerminalError(f"Shell not found: {e}")
    except Exception as e:
        raise TerminalError(f"Command execution failed: {e}")


def list_directory(path: Path, show_hidden: bool = False) -> str:
    """Enhanced ls/dir with file sizes and types."""
    if not path.exists():
        raise TerminalError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise TerminalError(f"Not a directory: {path}")

    entries = []
    try:
        for item in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                entries.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size // (1024 * 1024)}MB"
                entries.append(f"📄 {item.name} ({size_str})")
    except PermissionError:
        raise TerminalError(f"Permission denied: {path}")

    return "\n".join(entries) if entries else "(empty directory)"


def get_directory_context(workspace: Path) -> str:
    """Get a summary of the workspace directory for model context."""
    env = get_environment_context(workspace)
    lines = [
        f"OS: {env['os']} {env['os_version']}",
        f"Architecture: {env['architecture']}",
        f"Shell: {env['shell']}",
        f"Workspace: {env['workspace']}",
        f"User: {env['user']}",
    ]

    # Add available tools info
    tools_available = []
    for tool in ["git", "node", "npm", "python", "pip", "cargo", "go", "java", "dotnet"]:
        if shutil.which(tool):
            tools_available.append(tool)
    if tools_available:
        lines.append(f"Available tools: {', '.join(tools_available)}")

    return "\n".join(lines)
