from agent.workflows.result_aggregator import ResultAggregator
from agent.workflows.source_registry import SourceRegistry


def test_source_registry_canonicalizes_tracking_params_and_fragments():
    registry = SourceRegistry()

    url_a = "HTTPS://Example.com/path/?utm_source=newsletter&a=1#section"
    url_b = "https://example.com/path?a=1"

    canonical_a = registry.canonicalize_url(url_a)
    canonical_b = registry.canonicalize_url(url_b)

    assert canonical_a == canonical_b
    assert canonical_a == "https://example.com/path?a=1"


def test_source_registry_generates_stable_source_id_for_equivalent_urls():
    registry = SourceRegistry()

    source_a = registry.register("https://example.com/a/?utm_medium=email")
    source_b = registry.register("https://example.com/a")

    assert source_a is not None
    assert source_b is not None
    assert source_a.source_id == source_b.source_id
    assert source_a.canonical_url == source_b.canonical_url


def test_result_aggregator_dedupes_by_canonical_source():
    aggregator = ResultAggregator()

    aggregated = aggregator.aggregate(
        scraped_content=[
            {
                "query": "q1",
                "timestamp": "t1",
                "results": [
                    {
                        "title": "Source A",
                        "url": "https://example.com/news?id=42&utm_campaign=weekly",
                        "content": "short",
                    },
                    {
                        "title": "Source A canonical",
                        "url": "https://example.com/news?id=42",
                        "content": "this is longer canonical content",
                    },
                ],
            }
        ],
        original_query="",
    )

    assert aggregated.total_before == 2
    assert aggregated.total_after == 1
    result = aggregated.all_results()[0]
    assert result.canonical_url == "https://example.com/news?id=42"
    assert result.source_id.startswith("src_")
