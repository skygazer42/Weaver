"""Opt-in local Docker sandbox backend for Weaver.

Disabled by default (`ENABLE_DOCKER_SANDBOX=false`, `SANDBOX_MODE=local`).
When enabled (`ENABLE_DOCKER_SANDBOX=true` or `SANDBOX_MODE=docker`), provides
resource-limited local container execution reusing Weaver's existing
`sandbox_shell`, `sandbox_files`, and `execute_python_code` tool interfaces
without requiring an E2B API key.
"""

from __future__ import annotations

import base64
import logging
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from common.config import settings

logger = logging.getLogger(__name__)

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")

_MATPLOTLIB_PREAMBLE = """
import os as _weaver_os
_WEAVER_PLOT_PATH = "/workspace/.weaver_last_plot.png"
if _weaver_os.path.exists(_WEAVER_PLOT_PATH):
    try:
        _weaver_os.remove(_WEAVER_PLOT_PATH)
    except OSError:
        pass
try:
    import matplotlib as _weaver_mpl
    _weaver_mpl.use("Agg")
    import matplotlib.pyplot as _weaver_plt
    _weaver_orig_show = _weaver_plt.show
    def _weaver_capture_show(*args, **kwargs):
        try:
            if _weaver_plt.get_fignums():
                _weaver_plt.savefig(_WEAVER_PLOT_PATH, format="png", bbox_inches="tight", dpi=140)
        except Exception:
            pass
    _weaver_plt.show = _weaver_capture_show
except Exception:
    pass
"""

_MATPLOTLIB_EPILOGUE = """
try:
    import os as _weaver_os_end
    import matplotlib.pyplot as _weaver_plt_end
    if not _weaver_os_end.path.exists("/workspace/.weaver_last_plot.png") and _weaver_plt_end.get_fignums():
        _weaver_plt_end.savefig("/workspace/.weaver_last_plot.png", format="png", bbox_inches="tight", dpi=140)
except Exception:
    pass
"""


def _sanitize_id(raw: str) -> str:
    cleaned = _SAFE_ID_RE.sub("-", (raw or "default").strip()).strip("-.")
    return (cleaned or "default")[:48]


def is_docker_available(timeout: float = 5.0) -> tuple[bool, str]:
    """Check whether the local Docker CLI and daemon are reachable."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False, "Docker CLI not found in PATH"
    try:
        proc = subprocess.run(
            [docker_bin, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            version = (proc.stdout or "").strip() or "unknown"
            return True, f"Docker daemon reachable (server {version})"
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit code {proc.returncode}"
        return False, f"Docker daemon unavailable: {detail}"
    except Exception as exc:
        return False, f"Docker availability check failed: {exc}"


@dataclass(frozen=True)
class DockerSandboxConfig:
    image: str = "python:3.12-slim"
    cpus: float = 1.0
    memory: str = "512m"
    pids_limit: int = 128
    network_enabled: bool = False
    timeout_seconds: int = 60
    work_root: Path | None = None

    @classmethod
    def from_settings(cls) -> DockerSandboxConfig:
        raw_root = (getattr(settings, "docker_sandbox_work_root", "") or "").strip()
        work_root = Path(raw_root) if raw_root else Path(tempfile.gettempdir()) / "weaver-docker-sandbox"
        return cls(
            image=(getattr(settings, "docker_sandbox_image", "") or "python:3.12-slim").strip(),
            cpus=float(getattr(settings, "docker_sandbox_cpus", 1.0) or 1.0),
            memory=(getattr(settings, "docker_sandbox_memory", "") or "512m").strip(),
            pids_limit=int(getattr(settings, "docker_sandbox_pids_limit", 128) or 128),
            network_enabled=bool(getattr(settings, "docker_sandbox_network_enabled", False)),
            timeout_seconds=int(getattr(settings, "docker_sandbox_timeout_seconds", 60) or 60),
            work_root=work_root,
        )


def build_docker_run_args(
    *,
    container_name: str,
    host_workspace: Path,
    thread_id: str,
    config: DockerSandboxConfig,
) -> list[str]:
    """Build hardened `docker run` arguments for an isolated local sandbox container."""
    network_mode = "bridge" if config.network_enabled else "none"
    return [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "--cpus",
        str(config.cpus),
        "--memory",
        config.memory,
        "--pids-limit",
        str(config.pids_limit),
        "--network",
        network_mode,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--label",
        "weaver.sandbox=true",
        "--label",
        f"weaver.thread_id={_sanitize_id(thread_id)}",
        "-v",
        f"{host_workspace.resolve()}:/workspace:rw",
        "-w",
        "/workspace",
        config.image,
        "sleep",
        "infinity",
    ]


class DockerSandboxFilesystem:
    """Host-backed filesystem adapter scoped strictly inside a thread's `/workspace` mount."""

    def __init__(self, root: Path, workspace_prefix: str = "/workspace") -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.workspace_prefix = workspace_prefix.rstrip("/")

    def _resolve(self, sandbox_path: str) -> Path:
        raw = (sandbox_path or "").strip().replace("\\", "/")
        if raw == self.workspace_prefix or raw == f"{self.workspace_prefix}/":
            rel = ""
        elif raw.startswith(f"{self.workspace_prefix}/"):
            rel = raw[len(self.workspace_prefix) + 1 :]
        else:
            rel = raw.lstrip("/")
        candidate = (self.root / rel).resolve()
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise ValueError(f"Path escapes sandbox workspace: {sandbox_path}")
        return candidate

    def read(self, path: str) -> str:
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        return target.read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def read_bytes(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        return target.read_bytes()

    def write_bytes(self, path: str, content: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def make_dir(self, path: str) -> None:
        target = self._resolve(path)
        target.mkdir(parents=True, exist_ok=True)

    def remove(self, path: str) -> None:
        target = self._resolve(path)
        if target == self.root:
            raise ValueError("Refusing to remove workspace root")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        else:
            raise FileNotFoundError(f"Path not found: {path}")

    def list(self, path: str) -> list[Any]:
        target = self._resolve(path)
        if not target.is_dir():
            raise FileNotFoundError(f"Directory not found: {path}")
        entries = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            entries.append(SimpleNamespace(name=child.name, is_dir=child.is_dir()))
        return entries


class _DockerProcessHandle:
    """E2B-compatible process handle backed by `docker exec`."""

    def __init__(self, popen: subprocess.Popen[str]) -> None:
        self._popen = popen
        self.stdout: str = ""
        self.stderr: str = ""
        self.exit_code: int = 0

    def wait(self, timeout: float | None = None) -> int:
        stdout, stderr = self._popen.communicate(timeout=timeout)
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.exit_code = int(self._popen.returncode or 0)
        return self.exit_code

    def kill(self) -> None:
        with suppress(Exception):
            self._popen.kill()


class DockerSandboxProcessManager:
    """E2B-compatible `.process.start(command)` adapter executing inside the Docker container."""

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    def start(self, command: str) -> _DockerProcessHandle:
        container = self._sandbox.ensure_started()
        cmd = ["docker", "exec", "-i", container, "sh", "-c", command]
        popen = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return _DockerProcessHandle(popen)


class DockerSandbox:
    """Thread-scoped local Docker sandbox with E2B-compatible `filesystem` and `process` APIs."""

    def __init__(self, thread_id: str, config: DockerSandboxConfig | None = None) -> None:
        self.thread_id = thread_id or "default"
        self.config = config or DockerSandboxConfig.from_settings()
        base_root = self.config.work_root or (Path(tempfile.gettempdir()) / "weaver-docker-sandbox")
        safe_tid = _sanitize_id(self.thread_id)
        self.host_workspace = (base_root / safe_tid).resolve()
        self.host_workspace.mkdir(parents=True, exist_ok=True)
        self.id = f"weaver-sb-{safe_tid}-{uuid.uuid4().hex[:8]}"
        self.filesystem = DockerSandboxFilesystem(self.host_workspace)
        self.process = DockerSandboxProcessManager(self)
        self._started = False
        self._lock = threading.Lock()

    def ensure_started(self) -> str:
        with self._lock:
            if self._started:
                return self.id
            available, detail = is_docker_available()
            if not available:
                raise RuntimeError(
                    f"Local Docker sandbox is enabled, but Docker is unavailable ({detail}). "
                    "Start Docker Desktop/daemon or disable ENABLE_DOCKER_SANDBOX."
                )
            cmd = build_docker_run_args(
                container_name=self.id,
                host_workspace=self.host_workspace,
                thread_id=self.thread_id,
                config=self.config,
            )
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()
                raise RuntimeError(f"Failed to start Docker sandbox container: {err}")
            self._started = True
            logger.info(
                "[docker_sandbox] Started container %s (image=%s, cpus=%s, mem=%s, net=%s)",
                self.id,
                self.config.image,
                self.config.cpus,
                self.config.memory,
                "bridge" if self.config.network_enabled else "none",
            )
            return self.id

    def run_python(self, code: str, timeout: int | None = None) -> dict[str, Any]:
        """Run a Python snippet inside the Docker container and capture stdout/stderr/plot PNG."""
        effective_timeout = int(timeout or self.config.timeout_seconds or 60)
        script_name = f".weaver_exec_{uuid.uuid4().hex[:8]}.py"
        script_path = f"/workspace/{script_name}"
        plot_path = self.host_workspace / ".weaver_last_plot.png"
        wrapped = f"{_MATPLOTLIB_PREAMBLE}\n{code}\n{_MATPLOTLIB_EPILOGUE}\n"

        try:
            self.filesystem.write(script_path, wrapped)
            proc = self.process.start(f"python -u {script_path}")
            try:
                proc.wait(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                return {
                    "success": False,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "error": f"Python execution timed out after {effective_timeout}s",
                    "image": None,
                }

            image_b64: str | None = None
            if plot_path.is_file():
                try:
                    image_b64 = base64.b64encode(plot_path.read_bytes()).decode("ascii")
                finally:
                    plot_path.unlink(missing_ok=True)

            success = proc.exit_code == 0
            return {
                "success": success,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "error": None if success else (proc.stderr.strip() or f"Exit code {proc.exit_code}"),
                "image": image_b64,
            }
        except Exception as exc:
            logger.error("[docker_sandbox] Python execution failed: %s", exc)
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": str(exc),
                "image": None,
            }
        finally:
            with suppress(Exception):
                self.filesystem.remove(script_path)

    def get_host(self, port: int) -> str:
        return f"localhost:{port}"

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self.id],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except Exception as exc:
                logger.warning("[docker_sandbox] Failed to stop container %s: %s", self.id, exc)
            finally:
                self._started = False


class DockerSandboxSessionManager:
    """Manage per-thread local Docker sandboxes."""

    def __init__(self) -> None:
        self._sandboxes: dict[str, DockerSandbox] = {}
        self._lock = threading.Lock()

    def get_or_create(self, thread_id: str) -> DockerSandbox:
        key = thread_id or "default"
        with self._lock:
            sandbox = self._sandboxes.get(key)
            if sandbox is None:
                sandbox = DockerSandbox(key)
                self._sandboxes[key] = sandbox
            return sandbox

    def run_python(self, code: str, thread_id: str = "default", timeout: int | None = None) -> dict[str, Any]:
        return self.get_or_create(thread_id).run_python(code, timeout=timeout)

    def stop(self, thread_id: str) -> None:
        key = thread_id or "default"
        with self._lock:
            sandbox = self._sandboxes.pop(key, None)
        if sandbox is not None:
            sandbox.stop()

    def stop_all(self) -> None:
        with self._lock:
            items = list(self._sandboxes.values())
            self._sandboxes.clear()
        for sandbox in items:
            sandbox.stop()


docker_sandbox_sessions = DockerSandboxSessionManager()
