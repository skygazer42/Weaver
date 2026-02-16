from agent.workflows.evidence_extractor import extract_message_sources


def test_extract_message_sources_returns_canonicalized_urls_and_titles():
    scraped = [{"results": [{"title": "A", "url": "https://example.com/?utm_source=x"}]}]
    sources = extract_message_sources(scraped)
    assert sources[0]["url"] == "https://example.com/"
    assert sources[0]["title"] == "A"

