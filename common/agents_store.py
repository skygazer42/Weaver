from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentProfile(BaseModel):
    """
    Lightweight “GPTs-like” agent profile.

    Stored in a local JSON file (data/agents.json) to avoid DB migrations.
    """

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    system_prompt: str = ""

    # Optional override; if empty, request.model/settings.primary_model is used.
    model: str = ""

    # Minimal tool toggles (the runtime still enforces global safety settings).
    enabled_tools: Dict[str, bool] = Field(default_factory=dict)

    # Optional per-agent MCP config override (same shape as MCP_SERVERS JSON).
    mcp_servers: Optional[Dict[str, Any]] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)


@dataclass(frozen=True)
class AgentsStorePaths:
    root: Path
    file: Path


_LOCK = threading.Lock()


def default_store_paths(project_root: Optional[Path] = None) -> AgentsStorePaths:
    root = project_root or Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    return AgentsStorePaths(root=data_dir, file=data_dir / "agents.json")


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_agents(paths: Optional[AgentsStorePaths] = None) -> List[AgentProfile]:
    """
    Load agent profiles. Returns empty list if no file exists.
    """
    paths = paths or default_store_paths()
    with _LOCK:
        if not paths.file.exists():
            return []
        raw = json.loads(paths.file.read_text(encoding="utf-8") or "[]")
        if not isinstance(raw, list):
            return []
        profiles: List[AgentProfile] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                profiles.append(AgentProfile.model_validate(item))
            except Exception:
                continue
        return profiles


def save_agents(profiles: List[AgentProfile], paths: Optional[AgentsStorePaths] = None) -> None:
    paths = paths or default_store_paths()
    payload = [p.model_dump(mode="json") for p in profiles]
    with _LOCK:
        _atomic_write_json(paths.file, payload)


def ensure_default_agent(
    *,
    default_profile: AgentProfile,
    paths: Optional[AgentsStorePaths] = None,
) -> List[AgentProfile]:
    """
    Ensure the store exists and contains `default_profile.id`.
    Returns the full updated list.
    """
    paths = paths or default_store_paths()
    profiles = load_agents(paths)
    by_id = {p.id: p for p in profiles}
    if default_profile.id in by_id:
        return profiles

    profiles = [default_profile, *profiles]
    save_agents(profiles, paths)
    return profiles


def get_agent(agent_id: str, paths: Optional[AgentsStorePaths] = None) -> Optional[AgentProfile]:
    for p in load_agents(paths):
        if p.id == agent_id:
            return p
    return None


def upsert_agent(profile: AgentProfile, paths: Optional[AgentsStorePaths] = None) -> AgentProfile:
    paths = paths or default_store_paths()
    profiles = load_agents(paths)
    now = _utc_now_iso()

    updated: List[AgentProfile] = []
    replaced = False
    for p in profiles:
        if p.id != profile.id:
            updated.append(p)
            continue
        replaced = True
        updated.append(profile.model_copy(update={"updated_at": now}))

    if not replaced:
        updated.append(profile.model_copy(update={"created_at": now, "updated_at": now}))

    save_agents(updated, paths)
    return get_agent(profile.id, paths) or profile


def delete_agent(agent_id: str, *, protected_ids: Optional[set[str]] = None, paths: Optional[AgentsStorePaths] = None) -> bool:
    protected_ids = protected_ids or set()
    if agent_id in protected_ids:
        return False

    paths = paths or default_store_paths()
    profiles = load_agents(paths)
    kept = [p for p in profiles if p.id != agent_id]
    if len(kept) == len(profiles):
        return False
    save_agents(kept, paths)
    return True
