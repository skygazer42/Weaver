from agent.workflows.domain_router import ResearchDomain, build_provider_profile
from tools.search.multi_search import (
    MultiSearchOrchestrator,
    SearchProvider,
    SearchResult,
    SearchStrategy,
)


class DummyProvider(SearchProvider):
    def __init__(self, name: str):
        super().__init__(name)
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        self.calls += 1
        return [
            SearchResult(
                title=f"{self.name} result",
                url=f"https://{self.name}.example.com",
                snippet="ok",
                score=0.7,
                provider=self.name,
            )
        ]


def test_build_provider_profile_for_scientific_domain():
    profile = build_provider_profile(
        suggested_sources=[
            "arxiv.org",
            "pubmed.ncbi.nlm.nih.gov",
            "nature.com",
        ],
        domain=ResearchDomain.SCIENTIFIC,
    )

    assert "arxiv" in profile
    assert "pubmed" in profile
    assert "semantic_scholar" in profile


def test_multi_search_respects_provider_profile():
    tavily = DummyProvider("tavily")
    arxiv = DummyProvider("arxiv")
    orchestrator = MultiSearchOrchestrator(
        providers=[tavily, arxiv],
        strategy=SearchStrategy.FALLBACK,
    )

    results = orchestrator.search(
        query="transformer paper",
        max_results=3,
        strategy=SearchStrategy.FALLBACK,
        provider_profile=["arxiv"],
    )

    assert arxiv.calls == 1
    assert tavily.calls == 0
    assert results
    assert results[0].provider == "arxiv"
