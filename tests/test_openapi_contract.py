from main import app


def test_openapi_has_key_paths_and_distinct_resume_schemas():
    spec = app.openapi()
    assert isinstance(spec, dict)

    paths = spec.get("paths", {}) or {}
    assert "/api/interrupt/resume" in paths
    assert "/api/sessions/{thread_id}/resume" in paths

    schemas = (spec.get("components", {}) or {}).get("schemas", {}) or {}
    assert "GraphInterruptResumeRequest" in schemas
    assert "SessionResumeRequest" in schemas
