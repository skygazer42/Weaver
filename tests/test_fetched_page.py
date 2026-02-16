import json

from tools.research.models import FetchedPage, truncate_bytes


def test_fetched_page_serializes():
    page = FetchedPage(
        url="https://example.com/",
        raw_url="https://example.com/?utm=1",
        method="direct_http",
        text="hi",
    )
    d = page.to_dict()
    assert d["url"] == "https://example.com/"
    assert d["method"] == "direct_http"
    json.dumps(d)


def test_truncate_bytes_truncates_when_over_limit():
    assert truncate_bytes(b"abcdef", max_bytes=3) == b"abc"


def test_truncate_bytes_is_noop_when_disabled():
    assert truncate_bytes(b"abcdef", max_bytes=0) == b"abcdef"
