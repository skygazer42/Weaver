from __future__ import annotations

from pathlib import Path


def test_uvicorn_reload_dirs_excludes_web_and_node_modules():
    from common.uvicorn_reload import get_uvicorn_reload_dirs

    repo_root = Path(__file__).resolve().parent.parent
    dirs = get_uvicorn_reload_dirs(repo_root)

    # Should watch backend code, not frontend deps.
    assert any(Path(p).name == "agent" for p in dirs)
    assert all(Path(p).name != "web" for p in dirs)
    assert all("node_modules" not in str(p) for p in dirs)

