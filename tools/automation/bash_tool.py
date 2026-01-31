import shlex
import subprocess
from pathlib import Path
from typing import List, Optional

from langchain.tools import tool

SAFE_DEFAULT_CWD = Path(".")
DEFAULT_TIMEOUT = 20  # seconds
DISALLOWED = {"rm", "shutdown", "reboot"}


@tool
def safe_bash(cmd: str, cwd: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    """
    Run a shell command with basic safety guard (no destructive commands).

    Args:
        cmd: command string
        cwd: optional working directory (default repo root)
        timeout: seconds before kill
    """
    parts = shlex.split(cmd)
    if any(part in DISALLOWED for part in parts):
        return "Error: disallowed command"

    workdir = Path(cwd) if cwd else SAFE_DEFAULT_CWD
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"[exit {result.returncode}] {out}\\n{err}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    except Exception as e:
        return f"Error: {e}"
