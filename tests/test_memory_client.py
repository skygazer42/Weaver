import json
from pathlib import Path

import pytest

from tools.core import memory_client


@pytest.fixture
def fallback_paths(tmp_path, monkeypatch):
    fallback = tmp_path / "repo" / "data" / "memory_store.json"
    legacy = tmp_path / "repo" / ".memory_store.json"
    legacy.parent.mkdir()
    monkeypatch.setattr(memory_client, "_fallback_path", fallback)
    monkeypatch.setattr(memory_client, "_legacy_fallback_path", legacy)
    monkeypatch.setattr(memory_client, "_mem_client", memory_client._MEM_INIT_FAILED)
    return fallback, legacy


@pytest.mark.parametrize("repo_store_exists", [False, True])
def test_override_isolates_all_memory_operations(
    tmp_path, monkeypatch, fallback_paths, repo_store_exists
):
    fallback, legacy = fallback_paths
    legacy.write_text(json.dumps({"test-user": ["legacy memory"]}), encoding="utf-8")
    if repo_store_exists:
        fallback.parent.mkdir()
        fallback.write_text(json.dumps({"test-user": ["repo memory"]}), encoding="utf-8")
    legacy_before = legacy.read_bytes()
    fallback_before = fallback.read_bytes() if repo_store_exists else None
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    store = isolated / "memory_store.json"
    store.write_text(json.dumps({"test-user": ["isolated memory"]}), encoding="utf-8")
    monkeypatch.setenv("WEAVER_DATA_DIR", f"  {isolated}  ")

    original_exists = Path.exists
    original_read_text = Path.read_text

    def isolated_exists(path):
        assert path not in fallback_paths, f"Touched repository memory path: {path}"
        return original_exists(path)

    def isolated_read_text(path, *args, **kwargs):
        assert path not in fallback_paths, f"Read repository memory path: {path}"
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(Path, "exists", isolated_exists)
        guarded.setattr(Path, "read_text", isolated_read_text)
        assert memory_client.fetch_memories(user_id="test-user") == ["isolated memory"]
        assert memory_client.add_memory_entry("new memory", user_id="test-user")
        assert memory_client.store_interaction("hello", "world", user_id="test-user")
        assert memory_client.fetch_memories(user_id="test-user", limit=3) == [
            "User: hello\nAssistant: world",
            "new memory",
            "isolated memory",
        ]

    assert json.loads(store.read_text(encoding="utf-8"))["test-user"] == [
        "isolated memory",
        "new memory",
        "User: hello\nAssistant: world",
    ]
    assert legacy.read_bytes() == legacy_before
    assert (fallback.read_bytes() if fallback.exists() else None) == fallback_before


def test_override_is_resolved_on_each_operation(tmp_path, monkeypatch, fallback_paths):
    first = tmp_path / "first"
    second = tmp_path / "second"
    monkeypatch.setenv("WEAVER_DATA_DIR", str(first))
    assert memory_client.add_memory_entry("first", user_id="test-user")
    monkeypatch.setenv("WEAVER_DATA_DIR", str(second))
    assert memory_client.fetch_memories(user_id="test-user") == []
    assert memory_client.store_interaction("second", "reply", user_id="test-user")
    monkeypatch.setenv("WEAVER_DATA_DIR", str(first))
    assert memory_client.fetch_memories(user_id="test-user") == ["first"]
    assert json.loads((second / "memory_store.json").read_text(encoding="utf-8")) == {
        "test-user": ["User: second\nAssistant: reply"]
    }
    assert all(not path.exists() for path in fallback_paths)


@pytest.mark.parametrize("override", [None, "", " \t "])
@pytest.mark.parametrize("has_legacy", [False, True])
def test_default_path_and_legacy_migration(monkeypatch, fallback_paths, override, has_legacy):
    fallback, legacy = fallback_paths
    if override is None:
        monkeypatch.delenv("WEAVER_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("WEAVER_DATA_DIR", override)
    if has_legacy:
        legacy.write_text(json.dumps({"test-user": ["legacy memory"]}), encoding="utf-8")
    assert memory_client.fetch_memories(user_id="test-user") == (
        ["legacy memory"] if has_legacy else []
    )
    assert memory_client.add_memory_entry("new memory", user_id="test-user")
    expected = (["legacy memory"] if has_legacy else []) + ["new memory"]
    assert json.loads(fallback.read_text(encoding="utf-8")) == {"test-user": expected}
    assert memory_client.fetch_memories(user_id="test-user", limit=3) == list(reversed(expected))
    assert not legacy.exists()
