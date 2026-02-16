from tools.research.models import FetchedPage


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
