import pytest


def test_normalize_interrupt_resume_payload_passthrough_decisions():
    from main import _normalize_interrupt_resume_payload

    payload = {"decisions": [{"type": "approve"}]}
    assert _normalize_interrupt_resume_payload(payload) == payload


def test_normalize_interrupt_resume_payload_legacy_tool_approved_true_translates_to_edit_decisions():
    from main import _normalize_interrupt_resume_payload

    payload = {
        "tool_approved": True,
        "tool_calls": [
            {"id": "c1", "name": "browser_search", "args": {"query": "cats"}},
            {"id": "c2", "name": "execute_python_code", "args": {"code": "print(1)"}},
        ],
    }

    assert _normalize_interrupt_resume_payload(payload) == {
        "decisions": [
            {
                "type": "edit",
                "edited_action": {"name": "browser_search", "args": {"query": "cats"}},
            },
            {
                "type": "edit",
                "edited_action": {"name": "execute_python_code", "args": {"code": "print(1)"}},
            },
        ]
    }


def test_normalize_interrupt_resume_payload_legacy_tool_approved_false_translates_to_reject_decisions_with_message():
    from main import _normalize_interrupt_resume_payload

    payload = {
        "tool_approved": False,
        "tool_calls": [
            {"id": "c1", "name": "browser_search", "args": {"query": "cats"}},
            {"id": "c2", "name": "execute_python_code", "args": {"code": "print(1)"}},
        ],
        "message": "No tool usage allowed.",
    }

    assert _normalize_interrupt_resume_payload(payload) == {
        "decisions": [
            {"type": "reject", "message": "No tool usage allowed."},
            {"type": "reject", "message": "No tool usage allowed."},
        ]
    }


def test_normalize_interrupt_resume_payload_legacy_missing_tool_calls_raises():
    from main import _normalize_interrupt_resume_payload

    with pytest.raises(ValueError):
        _normalize_interrupt_resume_payload({"tool_approved": True})

