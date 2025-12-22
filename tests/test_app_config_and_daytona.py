import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.config import load_app_config
from tools.sandbox import daytona_client as dc


def test_load_app_config_from_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[llm]
model = "gpt-test"
base_url = "https://api.test"
api_key = "secret"

[search]
engine = "google"
fallback_engines = ["bing"]

[daytona]
daytona_api_key = "k"
        """,
        encoding="utf-8",
    )
    app_cfg = load_app_config(str(cfg), str(tmp_path / "mcp.json"))
    assert app_cfg is not None
    assert app_cfg.llm["default"].model == "gpt-test"
    assert app_cfg.search_config.engine == "google"
    assert app_cfg.search_config.fallback_engines == ["bing"]
    assert app_cfg.daytona_config.daytona_api_key == "k"


def test_daytona_stop_all_scopes_by_thread(monkeypatch):
    # seed fake active sandboxes
    dc._ACTIVE_SANDBOX_IDS.clear()
    dc._ACTIVE_BY_THREAD.clear()
    dc._ACTIVE_SANDBOX_IDS.update({"a", "b"})
    dc._ACTIVE_BY_THREAD["t1"] = {"a"}
    dc._ACTIVE_BY_THREAD["t2"] = {"b"}

    monkeypatch.setattr(
        dc,
        "_daytona_cfg",
        lambda: ("key", "https://example.com", "us", "img", "entry", "pwd"),
    )

    class FakeResp:
        status_code = 204
        text = ""

    def fake_delete(url, headers=None, timeout=None):
        return FakeResp()

    monkeypatch.setattr(dc.requests, "delete", fake_delete)

    res = dc.daytona_stop_all(thread_id="t1")
    assert res["count"] == 1
    assert "a" not in dc._ACTIVE_SANDBOX_IDS
    assert "b" in dc._ACTIVE_SANDBOX_IDS
    assert "t1" not in dc._ACTIVE_BY_THREAD
