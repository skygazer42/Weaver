"""
Sandbox Web Development Tools (E2B)

This module adds Manus-parity web development helpers:
- Scaffold common frontend projects (Next.js, CRA, Vite)
- Build & start the project in the sandbox
- Optionally expose the dev server port for preview

The tools reuse the sandbox shell process tracker so outputs can be
queried via `sandbox_check_output`.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

try:
    # Reuse shell tool base so background processes are tracked together
    from tools.sandbox.sandbox_shell_tool import _SandboxShellBaseTool
except Exception:  # pragma: no cover - fallback for lint environments
    _SandboxShellBaseTool = BaseTool  # type: ignore

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    """Normalize project name to a safe folder name."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())
    cleaned = cleaned.strip("-") or "web-app"
    return cleaned.lower()


def _build_scaffold_command(
    framework: str,
    project_name: str,
    package_manager: str,
    typescript: bool,
    extra_flags: Optional[str],
) -> str:
    """Return the shell command to scaffold the project."""
    ts_flag = "--typescript" if typescript else ""
    pm_flag = ""

    if framework == "nextjs":
        pm_flag = f"--use-{package_manager}"
        # Disable prompts for unattended runs
        return (
            f"npx create-next-app@latest {project_name} "
            f"{ts_flag or '--js'} {pm_flag} --eslint --no-tailwind --no-git --src-dir --app "
            f"{extra_flags or ''}".strip()
        )

    if framework == "react":
        tmpl = "--template typescript" if typescript else ""
        return f"npx create-react-app {project_name} {tmpl} {extra_flags or ''}".strip()

    # Vite variants
    vite_template_map = {
        "vite-react": "react-ts" if typescript else "react",
        "vite-vue": "vue-ts" if typescript else "vue",
        "vite-svelte": "svelte-ts" if typescript else "svelte",
    }
    template = vite_template_map.get(framework, "react-ts" if typescript else "react")
    # npm create vite@latest <name> -- --template react-ts
    runner = {
        "npm": "npm create vite@latest",
        "yarn": "yarn create vite",
        "pnpm": "pnpm create vite",
        "bun": "bun create vite",
    }.get(package_manager, "npm create vite@latest")
    return f"{runner} {project_name} -- --template {template} {extra_flags or ''}".strip()


class ScaffoldWebProjectInput(BaseModel):
    project_name: str = Field(
        description="Project name / folder name (letters, numbers, dash, underscore)"
    )
    framework: Literal["nextjs", "react", "vite-react", "vite-vue", "vite-svelte"] = Field(
        description="Frontend framework template to use"
    )
    package_manager: Literal["npm", "yarn", "pnpm", "bun"] = Field(
        default="npm", description="Package manager to use for scaffolding"
    )
    typescript: bool = Field(default=True, description="Create a TypeScript project")
    overwrite: bool = Field(
        default=False,
        description="If true and the target folder exists, it will be removed before scaffolding",
    )
    install_deps: bool = Field(
        default=True, description="Install dependencies after scaffolding (recommended)"
    )
    extra_flags: Optional[str] = Field(
        default=None, description="Additional CLI flags to pass to the scaffold command"
    )


class SandboxScaffoldWebProjectTool(_SandboxShellBaseTool):
    """Create a web project (Next.js/CRA/Vite) inside the sandbox."""

    name: str = "sandbox_scaffold_web_project"
    description: str = (
        "Scaffold a web project in the sandbox (Next.js, CRA, or Vite). "
        "Returns command output and the created path. "
        "Set install_deps=false to skip dependency install."
    )
    args_schema: type[BaseModel] = ScaffoldWebProjectInput

    def _run(
        self,
        project_name: str,
        framework: str,
        package_manager: str = "npm",
        typescript: bool = True,
        overwrite: bool = False,
        install_deps: bool = True,
        extra_flags: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "scaffold_web_project",
            {
                "project_name": project_name,
                "framework": framework,
                "package_manager": package_manager,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized. Start sandbox browser first.")

            safe_name = _normalize_name(project_name)
            project_path = f"{self.workspace_path}/{safe_name}"

            # Remove existing folder if requested
            if overwrite:
                sandbox.process.start(f"rm -rf {project_path}").wait()

            # Check existence
            exists_proc = sandbox.process.start(
                f"test -d {project_path} && echo EXISTS || echo MISSING"
            )
            exists_proc.wait()
            if "EXISTS" in getattr(exists_proc, "stdout", ""):
                return {
                    "success": False,
                    "error": f"Path {project_path} already exists. Set overwrite=true to recreate.",
                }

            scaffold_cmd = _build_scaffold_command(
                framework, safe_name, package_manager, typescript, extra_flags
            )
            full_cmd = f"cd {self.workspace_path} && {scaffold_cmd}"
            proc = sandbox.process.start(full_cmd)
            proc.wait(timeout=600)

            stdout = getattr(proc, "stdout", "")
            stderr = getattr(proc, "stderr", "")
            exit_code = getattr(proc, "exit_code", 0)

            if exit_code != 0:
                self._emit_tool_result("scaffold_web_project", {"error": stderr}, start_time, False)
                return {"success": False, "error": stderr or stdout, "exit_code": exit_code}

            # Optionally install dependencies (some templates already install)
            install_output = ""
            if install_deps:
                install_cmd = {
                    "npm": "npm install",
                    "yarn": "yarn install",
                    "pnpm": "pnpm install",
                    "bun": "bun install",
                }.get(package_manager, "npm install")
                install_proc = sandbox.process.start(f"cd {project_path} && {install_cmd}")
                try:
                    install_proc.wait(timeout=600)
                except Exception:
                    install_output = "[install] timed out"
                else:
                    install_output = getattr(install_proc, "stdout", "")
                    if getattr(install_proc, "exit_code", 0) != 0:
                        install_output = install_output or getattr(install_proc, "stderr", "")

            result = {
                "success": True,
                "project_path": project_path,
                "framework": framework,
                "package_manager": package_manager,
                "typescript": typescript,
                "output": stdout[-2000:] if len(stdout) > 2000 else stdout,
                "install_output": install_output[-2000:] if install_output else None,
            }
            self._emit_tool_result("scaffold_web_project", result, start_time, True)
            return result

        except Exception as e:  # pragma: no cover - runtime safety
            self._emit_tool_result("scaffold_web_project", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class DeployWebProjectInput(BaseModel):
    project_path: str = Field(description="Path under /workspace to deploy (e.g., 'my-app')")
    package_manager: Literal["npm", "yarn", "pnpm", "bun"] = Field(
        default="npm", description="Package manager to run build/start"
    )
    build_command: Optional[str] = Field(
        default=None, description="Custom build command; defaults to <pm> run build"
    )
    start_command: Optional[str] = Field(
        default=None,
        description="Custom start command; defaults to prod start if available, otherwise dev with host/port flags",
    )
    port: int = Field(default=3000, description="Port to run the app on")
    expose: bool = Field(default=True, description="Expose the port publicly and return the URL")


class SandboxDeployWebProjectTool(_SandboxShellBaseTool):
    """Build and start a web project inside the sandbox, optionally exposing the port."""

    name: str = "sandbox_deploy_web_project"
    description: str = (
        "Build and start a web project in the sandbox. "
        "Runs build/start commands and returns the public URL if expose=true."
    )
    args_schema: type[BaseModel] = DeployWebProjectInput

    def _run(
        self,
        project_path: str,
        package_manager: str = "npm",
        build_command: Optional[str] = None,
        start_command: Optional[str] = None,
        port: int = 3000,
        expose: bool = True,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start(
            "deploy_web_project",
            {
                "project_path": project_path,
                "package_manager": package_manager,
                "port": port,
                "expose": expose,
            },
        )

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized. Start sandbox browser first.")

            # Normalize path
            rel_path = project_path.strip().lstrip("/workspace/").strip("/")
            full_path = f"{self.workspace_path}/{rel_path}"

            # Build step
            build_cmd = build_command or {
                "npm": "npm run build",
                "yarn": "yarn build",
                "pnpm": "pnpm run build",
                "bun": "bun run build",
            }.get(package_manager, "npm run build")

            build_proc = sandbox.process.start(f"cd {full_path} && {build_cmd}")
            build_proc.wait(timeout=600)
            build_stdout = getattr(build_proc, "stdout", "")
            build_exit = getattr(build_proc, "exit_code", 0)
            if build_exit != 0:
                result = {
                    "success": False,
                    "stage": "build",
                    "exit_code": build_exit,
                    "output": build_stdout,
                    "error": getattr(build_proc, "stderr", ""),
                }
                self._emit_tool_result("deploy_web_project", result, start_time, False)
                return result

            # Start step (background)
            default_start = {
                "npm": f"npm run start -- --hostname 0.0.0.0 --port {port} || npm run dev -- --host --port {port}",
                "yarn": f"yarn start --hostname 0.0.0.0 --port {port} || yarn dev --host --port {port}",
                "pnpm": f"pnpm start --hostname 0.0.0.0 --port {port} || pnpm dev --host --port {port}",
                "bun": f"bun start --hostname 0.0.0.0 --port {port} || bun dev --host --port {port}",
            }.get(
                package_manager,
                f"npm run start -- --hostname 0.0.0.0 --port {port} || npm run dev -- --host --port {port}",
            )
            start_cmd_final = start_command or default_start

            process_id = str(uuid.uuid4())[:8]
            output_file = f"/tmp/web_{process_id}.log"
            pid_file = f"/tmp/web_{process_id}.pid"

            start_proc = sandbox.process.start(
                f"cd {full_path} && nohup sh -c '{start_cmd_final}' > {output_file} 2>&1 & echo $! > {pid_file}"
            )
            start_proc.wait()

            # Track process so sandbox_check_output can read it
            processes = self._get_processes()
            processes[process_id] = {
                "command": start_cmd_final,
                "cwd": full_path,
                "output_file": output_file,
                "pid_file": pid_file,
                "started_at": time.time(),
                "status": "running",
            }

            public_url = None
            if expose:
                try:
                    host = sandbox.get_host(port)
                    public_url = f"https://{host}"
                except Exception as e:
                    logger.warning(f"[sandbox_web_dev] expose failed: {e}")
                    if hasattr(sandbox, "id"):
                        public_url = f"https://{sandbox.id}-{port}.e2b.dev"

            result = {
                "success": True,
                "process_id": process_id,
                "port": port,
                "url": public_url,
                "log_file": output_file,
                "build_output": build_stdout[-2000:] if len(build_stdout) > 2000 else build_stdout,
            }
            self._emit_tool_result("deploy_web_project", result, start_time, True)
            return result

        except Exception as e:  # pragma: no cover
            self._emit_tool_result("deploy_web_project", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


def build_sandbox_web_dev_tools(
    thread_id: str,
    emit_events: bool = True,
) -> List[BaseTool]:
    """Build sandbox web development tools (scaffold + deploy)."""
    return [
        SandboxScaffoldWebProjectTool(thread_id=thread_id, emit_events=emit_events),
        SandboxDeployWebProjectTool(thread_id=thread_id, emit_events=emit_events),
    ]
