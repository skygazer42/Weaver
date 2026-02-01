"""
Collaboration models for sharing, comments, and version history.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# File-based storage for collaboration data (no extra DB dependency)
_DATA_DIR = Path("data/collaboration")


def _ensure_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(filename: str) -> Dict[str, Any]:
    path = _DATA_DIR / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_json(filename: str, data: Dict[str, Any]) -> None:
    _ensure_dir()
    path = _DATA_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Share Links ──────────────────────────────────────────────────────────

def create_share_link(
    thread_id: str,
    permissions: str = "view",
    expires_hours: Optional[int] = 72,
) -> Dict[str, Any]:
    """Create a share link for a session."""
    share_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()
    expires_at = None
    if expires_hours:
        expires_at = (datetime.now() + timedelta(hours=expires_hours)).isoformat()

    link = {
        "id": share_id,
        "thread_id": thread_id,
        "permissions": permissions,
        "created_at": now,
        "expires_at": expires_at,
        "view_count": 0,
    }

    shares = _load_json("shares.json")
    shares[share_id] = link
    _save_json("shares.json", shares)

    logger.info(f"[collaboration] Created share link {share_id} for thread {thread_id}")
    return link


def get_share_link(share_id: str) -> Optional[Dict[str, Any]]:
    """Get share link details."""
    shares = _load_json("shares.json")
    link = shares.get(share_id)
    if not link:
        return None

    # Check expiration
    if link.get("expires_at"):
        expires = datetime.fromisoformat(link["expires_at"])
        if datetime.now() > expires:
            return None

    # Increment view count
    link["view_count"] = link.get("view_count", 0) + 1
    shares[share_id] = link
    _save_json("shares.json", shares)

    return link


def delete_share_link(share_id: str) -> bool:
    """Delete a share link."""
    shares = _load_json("shares.json")
    if share_id in shares:
        del shares[share_id]
        _save_json("shares.json", shares)
        return True
    return False


def list_share_links(thread_id: str) -> List[Dict[str, Any]]:
    """List all share links for a thread."""
    shares = _load_json("shares.json")
    return [s for s in shares.values() if s.get("thread_id") == thread_id]


# ─── Comments ────────────────────────────────────────────────────────────

def add_comment(
    thread_id: str,
    content: str,
    author: str = "anonymous",
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a comment to a session."""
    comment_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()

    comment = {
        "id": comment_id,
        "thread_id": thread_id,
        "message_id": message_id,
        "author": author,
        "content": content,
        "created_at": now,
        "updated_at": now,
    }

    comments = _load_json("comments.json")
    if thread_id not in comments:
        comments[thread_id] = []
    comments[thread_id].append(comment)
    _save_json("comments.json", comments)

    logger.info(f"[collaboration] Comment {comment_id} added to thread {thread_id}")
    return comment


def get_comments(
    thread_id: str,
    message_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get comments for a session, optionally filtered by message."""
    comments = _load_json("comments.json")
    thread_comments = comments.get(thread_id, [])

    if message_id:
        return [c for c in thread_comments if c.get("message_id") == message_id]
    return thread_comments


def delete_comment(thread_id: str, comment_id: str) -> bool:
    """Delete a comment."""
    comments = _load_json("comments.json")
    thread_comments = comments.get(thread_id, [])
    initial_len = len(thread_comments)
    comments[thread_id] = [c for c in thread_comments if c.get("id") != comment_id]
    if len(comments[thread_id]) < initial_len:
        _save_json("comments.json", comments)
        return True
    return False


# ─── Version History ─────────────────────────────────────────────────────

def save_version(
    thread_id: str,
    state_snapshot: Dict[str, Any],
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Save a version snapshot of a session."""
    versions = _load_json("versions.json")
    thread_versions = versions.get(thread_id, [])

    version_number = len(thread_versions) + 1
    version_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()

    version = {
        "id": version_id,
        "thread_id": thread_id,
        "version_number": version_number,
        "label": label or f"Version {version_number}",
        "created_at": now,
        "snapshot_size": len(json.dumps(state_snapshot, default=str)),
    }

    # Save snapshot separately (can be large)
    _ensure_dir()
    snapshot_path = _DATA_DIR / f"snapshot_{version_id}.json"
    snapshot_path.write_text(
        json.dumps(state_snapshot, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    thread_versions.append(version)
    versions[thread_id] = thread_versions
    _save_json("versions.json", versions)

    logger.info(f"[collaboration] Saved version {version_number} for thread {thread_id}")
    return version


def list_versions(thread_id: str) -> List[Dict[str, Any]]:
    """List all versions for a session."""
    versions = _load_json("versions.json")
    return versions.get(thread_id, [])


def get_version_snapshot(version_id: str) -> Optional[Dict[str, Any]]:
    """Get the full state snapshot for a version."""
    snapshot_path = _DATA_DIR / f"snapshot_{version_id}.json"
    if snapshot_path.exists():
        try:
            return json.loads(snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None
