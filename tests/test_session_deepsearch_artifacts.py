from types import SimpleNamespace

from common.session_manager import SessionManager


def _fake_checkpoint_tuple(state):
    return SimpleNamespace(
        checkpoint={"channel_values": state},
        metadata={"created_at": "2026-02-06T00:00:00Z"},
        parent_config={"configurable": {"checkpoint_id": "cp_parent"}},
    )


def test_session_manager_extracts_deepsearch_artifacts():
    state = {
        "route": "deep",
        "research_plan": ["q1", "q2"],
        "research_tree": {"nodes": {"root": {"topic": "AI"}}},
        "quality_summary": {"summary_count": 2, "source_count": 5},
    }

    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)

    session_state = manager.get_session_state("thread-1")
    assert session_state is not None
    payload = session_state.to_dict()

    artifacts = payload["deepsearch_artifacts"]
    assert artifacts["queries"] == ["q1", "q2"]
    assert artifacts["research_tree"]["nodes"]["root"]["topic"] == "AI"
    assert artifacts["quality_summary"]["summary_count"] == 2


def test_session_manager_build_resume_state_rehydrates_artifacts():
    artifacts = {
        "mode": "tree",
        "queries": ["q1", "q2", "q3"],
        "research_tree": {"nodes": {"root": {"topic": "AI"}}},
        "quality_summary": {"summary_count": 3},
    }
    state = {
        "route": "deep",
        "revision_count": 1,
        "deepsearch_artifacts": artifacts,
    }

    checkpointer = SimpleNamespace(get_tuple=lambda config: _fake_checkpoint_tuple(state))
    manager = SessionManager(checkpointer)

    restored = manager.build_resume_state("thread-2")
    assert restored is not None
    assert restored["research_plan"] == ["q1", "q2", "q3"]
    assert restored["research_tree"]["nodes"]["root"]["topic"] == "AI"
    assert restored["quality_summary"]["summary_count"] == 3
    assert restored["resumed_from_checkpoint"] is True
