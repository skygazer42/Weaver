from agent.workflows.source_url_utils import canonicalize_source_url, compact_unique_sources


def test_canonicalize_source_url_strips_tracking_and_normalizes_host_path():
    url = "https://EXAMPLE.com/path/?utm_source=mail&keep=1#fragment"
    assert canonicalize_source_url(url) == "https://example.com/path?keep=1"


def test_compact_unique_sources_dedupes_and_respects_limit():
    results = [
        {
            "title": "A",
            "url": "https://example.com/a?utm_source=mail",
            "provider": "serper",
            "score": 0.9,
        },
        {
            "title": "A duplicate",
            "url": "https://EXAMPLE.com/a/",
            "provider": "serper",
            "score": 0.8,
        },
        {
            "title": "B",
            "url": "https://example.com/b",
            "provider": "serper",
            "score": 0.7,
        },
    ]

    compact = compact_unique_sources(results, limit=1)

    assert len(compact) == 1
    assert compact[0]["url"] == "https://example.com/a"
