from agent.workflows.result_aggregator import ResultAggregator


def test_dedupe_by_url_strips_trailing_slash_and_keeps_longest_content():
    aggregator = ResultAggregator()

    aggregated = aggregator.aggregate(
        scraped_content=[
            {
                "query": "q1",
                "timestamp": "t1",
                "results": [
                    {
                        "title": "Example A",
                        "url": "https://example.com/a",
                        "content": "short",
                    },
                    {
                        "title": "Example A (duplicate)",
                        "url": "https://example.com/a/",
                        "content": "this is the longer content",
                    },
                ],
            }
        ],
        original_query="",
    )

    assert aggregated.total_before == 2
    assert aggregated.total_after == 1
    assert aggregated.duplicates_removed == 1
    assert aggregated.all_results()[0].content == "this is the longer content"


def test_dedupe_by_url_ignores_fragments():
    aggregator = ResultAggregator()

    aggregated = aggregator.aggregate(
        scraped_content=[
            {
                "query": "q1",
                "results": [
                    {
                        "title": "With Fragment",
                        "url": "https://example.com/a#frag",
                        "content": "apples oranges bananas",
                    },
                    {
                        "title": "Without Fragment",
                        "url": "https://example.com/a",
                        "content": "zebras quantum mechanics",
                    },
                ],
            }
        ],
        original_query="",
    )

    assert aggregated.total_before == 2
    assert aggregated.total_after == 1
    assert aggregated.duplicates_removed == 1


def test_dedupe_by_similarity_keeps_longer_content_for_near_duplicates():
    aggregator = ResultAggregator(similarity_threshold=0.7)

    aggregated = aggregator.aggregate(
        scraped_content=[
            {
                "query": "q1",
                "results": [
                    {
                        "title": "Short",
                        "url": "https://example.com/short",
                        "content": "Weaver is a web research agent with tools.",
                    },
                    {
                        "title": "Long",
                        "url": "https://example.com/long",
                        "content": "Weaver is a web research agent with tools and workflows.",
                    },
                ],
            }
        ],
        original_query="",
    )

    assert aggregated.total_before == 2
    assert aggregated.total_after == 1
    assert aggregated.duplicates_removed == 1
    assert aggregated.all_results()[0].title == "Long"


def test_tiers_are_ordered_by_score():
    aggregator = ResultAggregator(tier_1_threshold=0.6, tier_2_threshold=0.3)

    aggregated = aggregator.aggregate(
        scraped_content=[
            {
                "query": "alpha beta",
                "results": [
                    {
                        "title": "alpha beta",
                        "url": "https://example.com/high",
                        "content": "alpha beta",
                    },
                    {
                        "title": "alpha",
                        "url": "https://example.com/medium",
                        "content": "alpha",
                    },
                    {
                        "title": "unrelated",
                        "url": "https://example.com/low",
                        "content": "unrelated",
                    },
                ],
            }
        ],
        original_query="alpha beta",
    )

    assert len(aggregated.tier_1) == 1
    assert len(aggregated.tier_2) == 1
    assert len(aggregated.tier_3) == 1

    assert aggregated.all_results()[0].score >= aggregated.all_results()[1].score
    assert aggregated.all_results()[1].score >= aggregated.all_results()[2].score
