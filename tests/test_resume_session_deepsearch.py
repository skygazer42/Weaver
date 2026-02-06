import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep tests on in-memory checkpointer
os.environ["DATABASE_URL"] = ""

import main
from common.session_manager import SessionState


@pytest.mark.asyncio
async def test_resume_session_returns_deepsearch_artifact_context(monkeypatch):
    artifacts = {
        "mode": "tree",
        "queries": ["q1", "q2"],
        "research_tree": {"nodes": {"root": {"topic": "AI"}}},
        "quality_summary": {"summary_count": 2, "source_count": 5},
    }
    state = SessionState(
        thread_id="thread-123",
        state={
            "route": "deep",
            "revision_count": 1,
            "final_report": "",
            "deepsearch_artifacts": artifacts,
        },
        checkpoint_ts="",
        parent_checkpoint_id=None,
        deepsearch_artifacts=artifacts,
    )

    class FakeManager:
        @staticmethod
        def can_resume(thread_id: str):
            return True, "ok"

        @staticmethod
        def get_session_state(thread_id: str):
            return state

        @staticmethod
        def build_resume_state(thread_id: str, additional_input=None, update_state=None):
            restored = dict(state.state)
            restored["research_plan"] = list(artifacts["queries"])
            restored["research_tree"] = artifacts["research_tree"]
            restored["quality_summary"] = artifacts["quality_summary"]
            restored["resumed_from_checkpoint"] = True
            return restored

    monkeypatch.setattr(main, "checkpointer", object())
    monkeypatch.setattr(
        "common.session_manager.get_session_manager",
        lambda checkpointer: FakeManager(),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/sessions/thread-123/resume", json={})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["current_state"]["has_deepsearch_artifacts"] is True
    assert data["deepsearch_resume"]["artifacts_restored"] is True
    assert data["deepsearch_resume"]["mode"] == "tree"
    assert data["resume_state"]["research_plan_count"] == 2
