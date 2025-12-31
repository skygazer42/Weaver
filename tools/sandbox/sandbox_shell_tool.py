"""
Sandbox Shell Tool for E2B Sandbox Command Execution.

This module provides shell command execution in an E2B sandbox:
- Execute commands (blocking and non-blocking)
- Session management (tmux-like)
- Process monitoring and control
- Command output retrieval

Similar to Manus's sb_shell_tool.py but adapted for Weaver's E2B integration.

Usage:
    from tools.sandbox.sandbox_shell_tool import build_sandbox_shell_tools

    tools = build_sandbox_shell_tools(thread_id="thread_123")
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _get_sandbox_session(thread_id: str):
    """Get sandbox session for a thread."""
    from tools.sandbox.sandbox_browser_session import sandbox_browser_sessions

    return sandbox_browser_sessions.get(thread_id)


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread."""
    from agent.core.events import get_emitter_sync

    return get_emitter_sync(thread_id)


class _SandboxShellBaseTool(BaseTool):
    """Base class for sandbox shell tools."""

    thread_id: str = "default"
    emit_events: bool = True
    workspace_path: str = "/workspace"

    # Track running processes per thread
    _processes: Dict[str, Dict[str, Any]] = {}

    def _get_sandbox(self):
        """Get the E2B sandbox instance."""
        session = _get_sandbox_session(self.thread_id)
        if session and hasattr(session, "_handles") and session._handles:
            return session._handles.sandbox
        return None

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event."""
        if not self.emit_events:
            return
        emitter = _get_event_emitter(self.thread_id)
        if emitter:
            try:
                emitter.emit_sync(event_type, data)
            except Exception as e:
                logger.warning(f"[sandbox_shell] Failed to emit event: {e}")

    def _emit_tool_start(self, action: str, args: Dict[str, Any]) -> float:
        """Emit tool start event."""
        start_time = time.time()
        self._emit_event("tool_start", {
            "tool": self.name,
            "action": action,
            "args": args,
            "thread_id": self.thread_id,
        })
        return start_time

    def _emit_tool_result(
        self,
        action: str,
        result: Dict[str, Any],
        start_time: float,
        success: bool = True,
    ) -> None:
        """Emit tool result event."""
        duration_ms = (time.time() - start_time) * 1000
        self._emit_event("tool_result", {
            "tool": self.name,
            "action": action,
            "success": success,
            "duration_ms": round(duration_ms, 2),
        })

    def _get_processes(self) -> Dict[str, Any]:
        """Get processes for this thread."""
        if self.thread_id not in _SandboxShellBaseTool._processes:
            _SandboxShellBaseTool._processes[self.thread_id] = {}
        return _SandboxShellBaseTool._processes[self.thread_id]


class ExecuteCommandInput(BaseModel):
    """Input for execute_command."""
    command: str = Field(description="Shell command to execute")
    folder: Optional[str] = Field(
        default=None,
        description="Subdirectory of /workspace to run command in"
    )
    timeout: int = Field(
        default=60,
        description="Timeout in seconds (for blocking mode)"
    )
    background: bool = Field(
        default=False,
        description="Run command in background (non-blocking)"
    )


class SandboxExecuteCommandTool(_SandboxShellBaseTool):
    """Execute a shell command in the sandbox."""

    name: str = "sandbox_execute_command"
    description: str = (
        "Execute a shell command in the sandbox. "
        "Commands run in /workspace by default. "
        "Use background=true for long-running commands like servers."
    )
    args_schema: type[BaseModel] = ExecuteCommandInput

    def _run(
        self,
        command: str,
        folder: Optional[str] = None,
        timeout: int = 60,
        background: bool = False,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("execute_command", {
            "command": command[:100] + "..." if len(command) > 100 else command,
            "folder": folder,
            "background": background,
        })

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized. Start sandbox browser first.")

            # Build working directory
            cwd = self.workspace_path
            if folder:
                folder = folder.strip("/")
                cwd = f"{self.workspace_path}/{folder}"

            if background:
                # Non-blocking execution
                process_id = str(uuid.uuid4())[:8]

                # Use nohup and redirect output to a file for later retrieval
                output_file = f"/tmp/cmd_{process_id}.out"
                pid_file = f"/tmp/cmd_{process_id}.pid"

                bg_command = (
                    f"cd {cwd} && "
                    f"nohup sh -c '{command}' > {output_file} 2>&1 & "
                    f"echo $! > {pid_file}"
                )

                proc = sandbox.process.start(bg_command)
                proc.wait()

                # Store process info
                self._get_processes()[process_id] = {
                    "command": command,
                    "cwd": cwd,
                    "output_file": output_file,
                    "pid_file": pid_file,
                    "started_at": time.time(),
                    "status": "running",
                }

                result = {
                    "success": True,
                    "process_id": process_id,
                    "message": f"Command started in background. Use sandbox_check_output with process_id='{process_id}' to check results.",
                    "cwd": cwd,
                }

                self._emit_tool_result("execute_command", result, start_time, True)
                return result

            else:
                # Blocking execution
                full_command = f"cd {cwd} && {command}"

                proc = sandbox.process.start(full_command)

                # Wait with timeout
                try:
                    proc.wait(timeout=timeout)
                except Exception as e:
                    # Timeout or error
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return {
                        "success": False,
                        "error": f"Command timed out after {timeout}s",
                        "partial_output": proc.stdout if hasattr(proc, "stdout") else "",
                    }

                # Get output
                stdout = proc.stdout if hasattr(proc, "stdout") else ""
                stderr = proc.stderr if hasattr(proc, "stderr") else ""
                exit_code = proc.exit_code if hasattr(proc, "exit_code") else 0

                result = {
                    "success": exit_code == 0,
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "cwd": cwd,
                }

                self._emit_tool_result("execute_command", result, start_time, exit_code == 0)
                return result

        except Exception as e:
            self._emit_tool_result("execute_command", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class CheckOutputInput(BaseModel):
    """Input for check_output."""
    process_id: str = Field(description="Process ID from execute_command")
    tail_lines: int = Field(default=50, description="Number of lines to return from end")


class SandboxCheckOutputTool(_SandboxShellBaseTool):
    """Check output of a background command."""

    name: str = "sandbox_check_output"
    description: str = (
        "Check the output of a background command. "
        "Use the process_id from execute_command."
    )
    args_schema: type[BaseModel] = CheckOutputInput

    def _run(
        self,
        process_id: str,
        tail_lines: int = 50,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("check_output", {"process_id": process_id})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            processes = self._get_processes()
            if process_id not in processes:
                return {
                    "success": False,
                    "error": f"Process '{process_id}' not found.",
                }

            proc_info = processes[process_id]
            output_file = proc_info["output_file"]
            pid_file = proc_info["pid_file"]

            # Check if process is still running
            check_cmd = f"cat {pid_file} 2>/dev/null | xargs -I{{}} sh -c 'kill -0 {{}} 2>/dev/null && echo running || echo stopped'"
            check_proc = sandbox.process.start(check_cmd)
            check_proc.wait()
            status = check_proc.stdout.strip() if hasattr(check_proc, "stdout") else "unknown"

            # Get output
            tail_cmd = f"tail -n {tail_lines} {output_file} 2>/dev/null || echo '[No output yet]'"
            tail_proc = sandbox.process.start(tail_cmd)
            tail_proc.wait()
            output = tail_proc.stdout if hasattr(tail_proc, "stdout") else ""

            # Update status
            proc_info["status"] = status

            result = {
                "success": True,
                "process_id": process_id,
                "command": proc_info["command"],
                "status": status,
                "output": output,
                "cwd": proc_info["cwd"],
                "running_time": round(time.time() - proc_info["started_at"], 1),
            }

            self._emit_tool_result("check_output", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("check_output", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class KillProcessInput(BaseModel):
    """Input for kill_process."""
    process_id: str = Field(description="Process ID to kill")


class SandboxKillProcessTool(_SandboxShellBaseTool):
    """Kill a background process."""

    name: str = "sandbox_kill_process"
    description: str = "Kill a background process by its process_id."
    args_schema: type[BaseModel] = KillProcessInput

    def _run(self, process_id: str) -> Dict[str, Any]:
        start_time = self._emit_tool_start("kill_process", {"process_id": process_id})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            processes = self._get_processes()
            if process_id not in processes:
                return {
                    "success": False,
                    "error": f"Process '{process_id}' not found.",
                }

            proc_info = processes[process_id]
            pid_file = proc_info["pid_file"]

            # Kill the process
            kill_cmd = f"cat {pid_file} 2>/dev/null | xargs -I{{}} kill {{}} 2>/dev/null; rm -f {pid_file} {proc_info['output_file']}"
            kill_proc = sandbox.process.start(kill_cmd)
            kill_proc.wait()

            # Update status
            proc_info["status"] = "killed"

            result = {
                "success": True,
                "message": f"Process '{process_id}' killed.",
                "command": proc_info["command"],
            }

            self._emit_tool_result("kill_process", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("kill_process", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class SandboxListProcessesTool(_SandboxShellBaseTool):
    """List all tracked background processes."""

    name: str = "sandbox_list_processes"
    description: str = "List all tracked background processes for this session."

    def _run(self) -> Dict[str, Any]:
        start_time = self._emit_tool_start("list_processes", {})

        try:
            processes = self._get_processes()

            process_list = []
            for pid, info in processes.items():
                process_list.append({
                    "process_id": pid,
                    "command": info["command"][:50] + "..." if len(info["command"]) > 50 else info["command"],
                    "status": info.get("status", "unknown"),
                    "cwd": info["cwd"],
                    "running_time": round(time.time() - info["started_at"], 1),
                })

            result = {
                "success": True,
                "processes": process_list,
                "total": len(process_list),
            }

            self._emit_tool_result("list_processes", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("list_processes", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class InstallPackageInput(BaseModel):
    """Input for install_package."""
    packages: str = Field(description="Package name(s) to install (space-separated)")
    package_manager: str = Field(
        default="auto",
        description="Package manager: 'npm', 'pip', 'apt', or 'auto' to detect"
    )
    folder: Optional[str] = Field(
        default=None,
        description="Subdirectory for npm/pip install"
    )


class SandboxInstallPackageTool(_SandboxShellBaseTool):
    """Install packages in the sandbox."""

    name: str = "sandbox_install_package"
    description: str = (
        "Install packages using npm, pip, or apt. "
        "Use 'auto' to detect based on package names."
    )
    args_schema: type[BaseModel] = InstallPackageInput

    def _run(
        self,
        packages: str,
        package_manager: str = "auto",
        folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("install_package", {
            "packages": packages,
            "package_manager": package_manager,
        })

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            # Auto-detect package manager
            if package_manager == "auto":
                # Check for common patterns
                pkg_lower = packages.lower()
                if any(p in pkg_lower for p in ["react", "vue", "next", "express", "lodash", "@"]):
                    package_manager = "npm"
                elif any(p in pkg_lower for p in ["pandas", "numpy", "flask", "django", "requests"]):
                    package_manager = "pip"
                else:
                    package_manager = "apt"

            # Build command
            cwd = self.workspace_path
            if folder:
                folder = folder.strip("/")
                cwd = f"{self.workspace_path}/{folder}"

            if package_manager == "npm":
                command = f"cd {cwd} && npm install {packages}"
            elif package_manager == "pip":
                command = f"pip install {packages}"
            elif package_manager == "apt":
                command = f"apt-get update && apt-get install -y {packages}"
            else:
                return {"success": False, "error": f"Unknown package manager: {package_manager}"}

            # Execute
            proc = sandbox.process.start(command)
            try:
                proc.wait(timeout=300)  # 5 min timeout for installs
            except Exception:
                return {"success": False, "error": "Installation timed out"}

            stdout = proc.stdout if hasattr(proc, "stdout") else ""
            stderr = proc.stderr if hasattr(proc, "stderr") else ""
            exit_code = proc.exit_code if hasattr(proc, "exit_code") else 0

            result = {
                "success": exit_code == 0,
                "packages": packages,
                "package_manager": package_manager,
                "output": stdout[-2000:] if len(stdout) > 2000 else stdout,  # Trim long output
                "error": stderr if exit_code != 0 else None,
            }

            self._emit_tool_result("install_package", result, start_time, exit_code == 0)
            return result

        except Exception as e:
            self._emit_tool_result("install_package", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class ExposePortInput(BaseModel):
    """Input for expose_port."""
    port: int = Field(description="Port number to expose")


class SandboxExposePortTool(_SandboxShellBaseTool):
    """Expose a port from the sandbox to the internet."""

    name: str = "sandbox_expose_port"
    description: str = (
        "Expose a port from the sandbox to get a public URL. "
        "Use this after starting a dev server."
    )
    args_schema: type[BaseModel] = ExposePortInput

    def _run(self, port: int) -> Dict[str, Any]:
        start_time = self._emit_tool_start("expose_port", {"port": port})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            # Get the public URL for the port
            try:
                # E2B provides get_host method to get public URL
                host = sandbox.get_host(port)
                url = f"https://{host}"
            except Exception as e:
                logger.warning(f"[sandbox_shell] Failed to get host: {e}")
                # Fallback - try to construct URL from sandbox info
                if hasattr(sandbox, "id"):
                    url = f"https://{sandbox.id}-{port}.e2b.dev"
                else:
                    return {"success": False, "error": f"Failed to expose port: {e}"}

            result = {
                "success": True,
                "port": port,
                "url": url,
                "message": f"Port {port} is now accessible at {url}",
            }

            self._emit_tool_result("expose_port", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("expose_port", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


def build_sandbox_shell_tools(
    thread_id: str,
    emit_events: bool = True,
) -> List[BaseTool]:
    """
    Build sandbox shell tools for a thread.

    Args:
        thread_id: Thread/conversation ID
        emit_events: Whether to emit events

    Returns:
        List of shell tools
    """
    return [
        SandboxExecuteCommandTool(thread_id=thread_id, emit_events=emit_events),
        SandboxCheckOutputTool(thread_id=thread_id, emit_events=emit_events),
        SandboxKillProcessTool(thread_id=thread_id, emit_events=emit_events),
        SandboxListProcessesTool(thread_id=thread_id, emit_events=emit_events),
        SandboxInstallPackageTool(thread_id=thread_id, emit_events=emit_events),
        SandboxExposePortTool(thread_id=thread_id, emit_events=emit_events),
    ]
