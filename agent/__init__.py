"""
Lightweight facade for the agent package.

Only the stable, public-facing symbols are exported here. For anything else,
import from the relevant submodule (agent.core.*, agent.workflows.*, etc.).
"""

from agent.api import *  # noqa: F401,F403

__all__ = list(set(globals().get("__all__", [])))  # keep surface small and explicit
