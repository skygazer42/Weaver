import pytest


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("a", ["a"]),
        (" a, ,b , ", ["a", "b"]),
    ],
)
def test_interrupt_nodes_list_strips_and_drops_empty(raw, expected):
    from common.config import Settings

    s = Settings(_env_file=None, interrupt_before_nodes=raw)
    assert s.interrupt_nodes_list == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("foo", ["foo"]),
        (" foo, ,bar , ", ["foo", "bar"]),
    ],
)
def test_tool_whitelist_list_strips_and_drops_empty(raw, expected):
    from common.config import Settings

    s = Settings(_env_file=None, tool_whitelist=raw)
    assert s.tool_whitelist_list == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("foo", ["foo"]),
        (" foo, ,bar , ", ["foo", "bar"]),
    ],
)
def test_tool_blacklist_list_strips_and_drops_empty(raw, expected):
    from common.config import Settings

    s = Settings(_env_file=None, tool_blacklist=raw)
    assert s.tool_blacklist_list == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("a", ["a"]),
        (" a, ,b , ", ["a", "b"]),
    ],
)
def test_tool_selector_always_include_list_strips_and_drops_empty(raw, expected):
    from common.config import Settings

    s = Settings(_env_file=None, tool_selector_always_include=raw)
    assert s.tool_selector_always_include_list == expected


def test_search_engines_list_defaults_to_tavily_when_empty():
    from common.config import Settings

    s = Settings(_env_file=None, search_engines="")
    assert s.search_engines_list == ["tavily"]


def test_cors_origins_list_includes_local_defaults_in_dev():
    from common.config import Settings

    s = Settings(_env_file=None, cors_origins="http://example.com", app_env="dev")
    origins = s.cors_origins_list

    assert "http://example.com" in origins
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "http://localhost:3100" in origins
    assert "http://127.0.0.1:3100" in origins


def test_cors_origins_list_does_not_auto_expand_in_prod():
    from common.config import Settings

    s = Settings(
        _env_file=None,
        cors_origins="http://example.com, http://foo.com, ",
        app_env="prod",
    )
    assert s.cors_origins_list == ["http://example.com", "http://foo.com"]
