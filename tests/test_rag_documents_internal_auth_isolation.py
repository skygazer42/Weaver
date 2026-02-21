import hashlib

import pytest
from httpx import ASGITransport, AsyncClient

import main


class _FakeRag:
    def __init__(self) -> None:
        self.added = []
        self.deleted = []
        self.searched = []

    def add_document(self, *, content: bytes, filename: str):
        self.added.append((filename, content))
        return {"success": True, "chunks": 1}

    def list_documents(self, *, limit: int = 100):
        return []

    def count(self) -> int:
        return 0

    def delete_document(self, source: str):
        self.deleted.append(source)
        return {"success": True, "deleted": 0}

    def search(self, query: str, *, n_results: int = 5):
        self.searched.append((query, n_results))
        return []


def _expected_collection(principal_id: str) -> str:
    suffix = hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:12]
    return f"weaver_documents__u_{suffix}"


@pytest.mark.asyncio
async def test_rag_upload_uses_isolated_collection_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setitem(main.settings.__dict__, "rag_enabled", True)
    monkeypatch.setitem(main.settings.__dict__, "rag_collection_name", "weaver_documents")

    import tools.rag.rag_tool as rag_tool_mod

    seen_collections = []
    rag = _FakeRag()

    def _fake_get_rag_tool(*, collection_name=None):
        seen_collections.append(collection_name)
        return rag

    monkeypatch.setattr(rag_tool_mod, "get_rag_tool", _fake_get_rag_tool)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/documents/upload",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
            files={"file": ("doc.md", b"# hello\n", "text/markdown")},
        )
        assert resp.status_code == 200

    assert seen_collections == [_expected_collection("alice")]


@pytest.mark.asyncio
async def test_rag_list_uses_isolated_collection_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setitem(main.settings.__dict__, "rag_enabled", True)
    monkeypatch.setitem(main.settings.__dict__, "rag_collection_name", "weaver_documents")

    import tools.rag.rag_tool as rag_tool_mod

    seen_collections = []
    rag = _FakeRag()

    def _fake_get_rag_tool(*, collection_name=None):
        seen_collections.append(collection_name)
        return rag

    monkeypatch.setattr(rag_tool_mod, "get_rag_tool", _fake_get_rag_tool)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/documents/list",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "bob",
            },
        )
        assert resp.status_code == 200

    assert seen_collections == [_expected_collection("bob")]

