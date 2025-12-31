"""
Sandbox Files Tool for E2B Sandbox File Operations.

This module provides file system operations in an E2B sandbox:
- Create, read, update, delete files
- List directory contents
- Upload and download files
- String replacement and file editing

Similar to Manus's sb_files_tool.py but adapted for Weaver's E2B integration.

Usage:
    from tools.sandbox.sandbox_files_tool import build_sandbox_files_tools

    tools = build_sandbox_files_tools(thread_id="thread_123")
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# File patterns to exclude
EXCLUDED_PATTERNS = [
    "__pycache__",
    ".git",
    "node_modules",
    ".next",
    ".nuxt",
    "dist",
    "build",
    ".cache",
    ".venv",
    "venv",
    ".env",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.egg-info",
]


def should_exclude_file(path: str) -> bool:
    """Check if a file/directory should be excluded."""
    path_lower = path.lower()
    for pattern in EXCLUDED_PATTERNS:
        if pattern.startswith("*"):
            # Extension pattern
            if path_lower.endswith(pattern[1:]):
                return True
        else:
            # Directory/file name pattern
            if pattern in path_lower.split("/"):
                return True
    return False


def clean_path(path: str, workspace: str = "/workspace") -> str:
    """Clean and normalize a path to be relative to workspace."""
    # Remove leading/trailing whitespace
    path = path.strip()

    # Remove workspace prefix if present
    if path.startswith(workspace):
        path = path[len(workspace):]

    # Remove leading slashes
    path = path.lstrip("/")

    # Remove any .. components for security
    parts = []
    for part in path.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part and part != ".":
            parts.append(part)

    return "/".join(parts)


def _get_sandbox_session(thread_id: str):
    """Get sandbox session for a thread."""
    from tools.sandbox.sandbox_browser_session import sandbox_browser_sessions

    return sandbox_browser_sessions.get(thread_id)


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread."""
    from agent.core.events import get_emitter_sync

    return get_emitter_sync(thread_id)


class _SandboxFilesBaseTool(BaseTool):
    """Base class for sandbox file tools."""

    thread_id: str = "default"
    emit_events: bool = True
    workspace_path: str = "/workspace"

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
                logger.warning(f"[sandbox_files] Failed to emit event: {e}")

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


class CreateFileInput(BaseModel):
    """Input for create_file."""
    file_path: str = Field(description="Path relative to /workspace (e.g., 'src/main.py')")
    file_contents: str = Field(description="Content to write to the file")
    permissions: str = Field(default="644", description="File permissions in octal (e.g., '644')")


class SandboxCreateFileTool(_SandboxFilesBaseTool):
    """Create a new file in the sandbox."""

    name: str = "sandbox_create_file"
    description: str = (
        "Create a new file with the provided contents in the sandbox. "
        "Path must be relative to /workspace (e.g., 'src/main.py'). "
        "Use sandbox_update_file to modify existing files."
    )
    args_schema: type[BaseModel] = CreateFileInput

    def _run(
        self,
        file_path: str,
        file_contents: str,
        permissions: str = "644",
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("create_file", {"file_path": file_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized. Start sandbox browser first.")

            # Clean the path
            file_path = clean_path(file_path, self.workspace_path)
            full_path = f"{self.workspace_path}/{file_path}"

            # Check if file exists
            try:
                sandbox.filesystem.read(full_path)
                self._emit_tool_result("create_file", {"error": "exists"}, start_time, False)
                return {
                    "success": False,
                    "error": f"File '{file_path}' already exists. Use sandbox_update_file to modify.",
                }
            except Exception:
                pass  # File doesn't exist, good

            # Create parent directories
            parent_dir = "/".join(full_path.split("/")[:-1])
            if parent_dir:
                try:
                    sandbox.filesystem.make_dir(parent_dir)
                except Exception:
                    pass  # Directory may already exist

            # Write the file
            if isinstance(file_contents, dict):
                file_contents = json.dumps(file_contents, indent=2)

            sandbox.filesystem.write(full_path, file_contents)

            result = {
                "success": True,
                "message": f"File '{file_path}' created successfully.",
                "path": file_path,
                "size": len(file_contents),
            }

            self._emit_tool_result("create_file", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("create_file", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class ReadFileInput(BaseModel):
    """Input for read_file."""
    file_path: str = Field(description="Path relative to /workspace")
    max_lines: Optional[int] = Field(default=None, description="Maximum lines to read")


class SandboxReadFileTool(_SandboxFilesBaseTool):
    """Read a file from the sandbox."""

    name: str = "sandbox_read_file"
    description: str = (
        "Read the contents of a file from the sandbox. "
        "Path must be relative to /workspace."
    )
    args_schema: type[BaseModel] = ReadFileInput

    def _run(
        self,
        file_path: str,
        max_lines: Optional[int] = None,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("read_file", {"file_path": file_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            file_path = clean_path(file_path, self.workspace_path)
            full_path = f"{self.workspace_path}/{file_path}"

            # Read the file
            content = sandbox.filesystem.read(full_path)

            # Limit lines if requested
            if max_lines and max_lines > 0:
                lines = content.split("\n")
                if len(lines) > max_lines:
                    content = "\n".join(lines[:max_lines])
                    content += f"\n... (truncated, {len(lines) - max_lines} more lines)"

            result = {
                "success": True,
                "path": file_path,
                "content": content,
                "size": len(content),
            }

            self._emit_tool_result("read_file", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("read_file", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class UpdateFileInput(BaseModel):
    """Input for update_file (full rewrite)."""
    file_path: str = Field(description="Path relative to /workspace")
    file_contents: str = Field(description="New content for the file")


class SandboxUpdateFileTool(_SandboxFilesBaseTool):
    """Update/rewrite a file in the sandbox."""

    name: str = "sandbox_update_file"
    description: str = (
        "Completely rewrite an existing file with new content. "
        "Use sandbox_str_replace for targeted edits."
    )
    args_schema: type[BaseModel] = UpdateFileInput

    def _run(
        self,
        file_path: str,
        file_contents: str,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("update_file", {"file_path": file_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            file_path = clean_path(file_path, self.workspace_path)
            full_path = f"{self.workspace_path}/{file_path}"

            # Check if file exists
            try:
                sandbox.filesystem.read(full_path)
            except Exception:
                self._emit_tool_result("update_file", {"error": "not found"}, start_time, False)
                return {
                    "success": False,
                    "error": f"File '{file_path}' does not exist. Use sandbox_create_file.",
                }

            # Write new content
            sandbox.filesystem.write(full_path, file_contents)

            result = {
                "success": True,
                "message": f"File '{file_path}' updated successfully.",
                "path": file_path,
                "size": len(file_contents),
            }

            self._emit_tool_result("update_file", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("update_file", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class StrReplaceInput(BaseModel):
    """Input for str_replace."""
    file_path: str = Field(description="Path relative to /workspace")
    old_str: str = Field(description="Text to be replaced (must appear exactly once)")
    new_str: str = Field(description="Replacement text")


class SandboxStrReplaceTool(_SandboxFilesBaseTool):
    """Replace a specific string in a file."""

    name: str = "sandbox_str_replace"
    description: str = (
        "Replace specific text in a file. The old_str must appear exactly once. "
        "Use this for targeted edits instead of rewriting the entire file."
    )
    args_schema: type[BaseModel] = StrReplaceInput

    def _run(
        self,
        file_path: str,
        old_str: str,
        new_str: str,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("str_replace", {
            "file_path": file_path,
            "old_str_len": len(old_str),
            "new_str_len": len(new_str),
        })

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            file_path = clean_path(file_path, self.workspace_path)
            full_path = f"{self.workspace_path}/{file_path}"

            # Read current content
            try:
                content = sandbox.filesystem.read(full_path)
            except Exception:
                return {"success": False, "error": f"File '{file_path}' not found."}

            # Expand tabs for consistent matching
            old_str = old_str.expandtabs()
            new_str = new_str.expandtabs()

            # Check occurrences
            occurrences = content.count(old_str)
            if occurrences == 0:
                return {"success": False, "error": f"String not found in file."}
            if occurrences > 1:
                lines = [i + 1 for i, line in enumerate(content.split("\n")) if old_str in line]
                return {
                    "success": False,
                    "error": f"Multiple occurrences found on lines {lines}. Make the string more specific.",
                }

            # Perform replacement
            new_content = content.replace(old_str, new_str)
            sandbox.filesystem.write(full_path, new_content)

            # Show snippet around edit
            replacement_line = content.split(old_str)[0].count("\n")
            lines = new_content.split("\n")
            start_line = max(0, replacement_line - 3)
            end_line = min(len(lines), replacement_line + 4 + new_str.count("\n"))
            snippet = "\n".join(lines[start_line:end_line])

            result = {
                "success": True,
                "message": "Replacement successful.",
                "path": file_path,
                "line": replacement_line + 1,
                "snippet": snippet,
            }

            self._emit_tool_result("str_replace", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("str_replace", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class DeleteFileInput(BaseModel):
    """Input for delete_file."""
    file_path: str = Field(description="Path relative to /workspace")


class SandboxDeleteFileTool(_SandboxFilesBaseTool):
    """Delete a file from the sandbox."""

    name: str = "sandbox_delete_file"
    description: str = "Delete a file from the sandbox."
    args_schema: type[BaseModel] = DeleteFileInput

    def _run(self, file_path: str) -> Dict[str, Any]:
        start_time = self._emit_tool_start("delete_file", {"file_path": file_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            file_path = clean_path(file_path, self.workspace_path)
            full_path = f"{self.workspace_path}/{file_path}"

            # Check if file exists
            try:
                sandbox.filesystem.read(full_path)
            except Exception:
                return {"success": False, "error": f"File '{file_path}' not found."}

            # Delete the file
            sandbox.filesystem.remove(full_path)

            result = {
                "success": True,
                "message": f"File '{file_path}' deleted successfully.",
            }

            self._emit_tool_result("delete_file", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("delete_file", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class ListFilesInput(BaseModel):
    """Input for list_files."""
    path: str = Field(default="", description="Path relative to /workspace (default: root)")
    recursive: bool = Field(default=False, description="List files recursively")
    max_depth: int = Field(default=3, description="Maximum depth for recursive listing")


class SandboxListFilesTool(_SandboxFilesBaseTool):
    """List files in a sandbox directory."""

    name: str = "sandbox_list_files"
    description: str = (
        "List files and directories in the sandbox. "
        "Optionally list recursively up to a maximum depth."
    )
    args_schema: type[BaseModel] = ListFilesInput

    def _run(
        self,
        path: str = "",
        recursive: bool = False,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("list_files", {"path": path, "recursive": recursive})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            path = clean_path(path, self.workspace_path) if path else ""
            full_path = f"{self.workspace_path}/{path}" if path else self.workspace_path

            files = []
            dirs = []

            def list_dir(dir_path: str, depth: int = 0):
                if depth > max_depth:
                    return

                try:
                    entries = sandbox.filesystem.list(dir_path)
                    for entry in entries:
                        rel_path = entry.path.replace(self.workspace_path + "/", "")

                        # Skip excluded files
                        if should_exclude_file(rel_path):
                            continue

                        if entry.is_dir:
                            dirs.append({
                                "path": rel_path,
                                "type": "directory",
                            })
                            if recursive and depth < max_depth:
                                list_dir(entry.path, depth + 1)
                        else:
                            files.append({
                                "path": rel_path,
                                "type": "file",
                                "size": getattr(entry, "size", 0),
                            })
                except Exception as e:
                    logger.warning(f"[sandbox_files] Failed to list {dir_path}: {e}")

            list_dir(full_path)

            result = {
                "success": True,
                "path": path or "/",
                "directories": sorted(dirs, key=lambda x: x["path"]),
                "files": sorted(files, key=lambda x: x["path"]),
                "total_dirs": len(dirs),
                "total_files": len(files),
            }

            self._emit_tool_result("list_files", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("list_files", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class UploadFileInput(BaseModel):
    """Input for upload_file."""
    file_path: str = Field(description="Destination path relative to /workspace")
    content_base64: str = Field(description="Base64 encoded file content")


class SandboxUploadFileTool(_SandboxFilesBaseTool):
    """Upload a file to the sandbox (binary-safe)."""

    name: str = "sandbox_upload_file"
    description: str = (
        "Upload a file to the sandbox using base64 encoding. "
        "Use this for binary files like images, PDFs, etc."
    )
    args_schema: type[BaseModel] = UploadFileInput

    def _run(
        self,
        file_path: str,
        content_base64: str,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("upload_file", {"file_path": file_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            file_path = clean_path(file_path, self.workspace_path)
            full_path = f"{self.workspace_path}/{file_path}"

            # Decode base64
            try:
                content = base64.b64decode(content_base64)
            except Exception:
                return {"success": False, "error": "Invalid base64 content."}

            # Create parent directories
            parent_dir = "/".join(full_path.split("/")[:-1])
            if parent_dir:
                try:
                    sandbox.filesystem.make_dir(parent_dir)
                except Exception:
                    pass

            # Write binary content
            sandbox.filesystem.write_bytes(full_path, content)

            result = {
                "success": True,
                "message": f"File '{file_path}' uploaded successfully.",
                "path": file_path,
                "size": len(content),
            }

            self._emit_tool_result("upload_file", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("upload_file", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


class DownloadFileInput(BaseModel):
    """Input for download_file."""
    file_path: str = Field(description="Path relative to /workspace")


class SandboxDownloadFileTool(_SandboxFilesBaseTool):
    """Download a file from the sandbox (returns base64)."""

    name: str = "sandbox_download_file"
    description: str = (
        "Download a file from the sandbox as base64. "
        "Use this for binary files like images, PDFs, etc."
    )
    args_schema: type[BaseModel] = DownloadFileInput

    def _run(self, file_path: str) -> Dict[str, Any]:
        start_time = self._emit_tool_start("download_file", {"file_path": file_path})

        try:
            sandbox = self._get_sandbox()
            if not sandbox:
                raise RuntimeError("Sandbox not initialized.")

            file_path = clean_path(file_path, self.workspace_path)
            full_path = f"{self.workspace_path}/{file_path}"

            # Read binary content
            try:
                content = sandbox.filesystem.read_bytes(full_path)
            except Exception:
                return {"success": False, "error": f"File '{file_path}' not found."}

            result = {
                "success": True,
                "path": file_path,
                "content_base64": base64.b64encode(content).decode("ascii"),
                "size": len(content),
            }

            self._emit_tool_result("download_file", result, start_time, True)
            return result

        except Exception as e:
            self._emit_tool_result("download_file", {"error": str(e)}, start_time, False)
            return {"success": False, "error": str(e)}


def build_sandbox_files_tools(
    thread_id: str,
    emit_events: bool = True,
) -> List[BaseTool]:
    """
    Build sandbox file tools for a thread.

    Args:
        thread_id: Thread/conversation ID
        emit_events: Whether to emit events

    Returns:
        List of file tools
    """
    return [
        SandboxCreateFileTool(thread_id=thread_id, emit_events=emit_events),
        SandboxReadFileTool(thread_id=thread_id, emit_events=emit_events),
        SandboxUpdateFileTool(thread_id=thread_id, emit_events=emit_events),
        SandboxStrReplaceTool(thread_id=thread_id, emit_events=emit_events),
        SandboxDeleteFileTool(thread_id=thread_id, emit_events=emit_events),
        SandboxListFilesTool(thread_id=thread_id, emit_events=emit_events),
        SandboxUploadFileTool(thread_id=thread_id, emit_events=emit_events),
        SandboxDownloadFileTool(thread_id=thread_id, emit_events=emit_events),
    ]
