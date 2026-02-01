"""
Semantic Scholar Search Provider.

Uses Semantic Scholar API for academic paper search.
API key optional but recommended for higher rate limits.
Supports:
- Paper search
- Citation graph traversal
- Author search
- Influential citations filtering
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from common.config import settings
from tools.search.multi_search import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

S2_API_URL = "https://api.semanticscholar.org/graph/v1"
S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


class SemanticScholarProvider(SearchProvider):
    """Semantic Scholar API search provider."""

    def __init__(self):
        api_key = getattr(settings, "semantic_scholar_api_key", None)
        super().__init__("semantic_scholar", api_key)
        self._session = requests.Session()
        headers = {"User-Agent": "Weaver/1.0 (Research Tool)"}
        if api_key:
            headers["x-api-key"] = api_key
        self._session.headers.update(headers)

    def is_available(self) -> bool:
        """Semantic Scholar is always available (API key optional)."""
        return True

    def search(
        self,
        query: str,
        max_results: int = 10,
        year_range: Optional[tuple] = None,
        fields_of_study: Optional[List[str]] = None,
        open_access_only: bool = False,
    ) -> List[SearchResult]:
        """
        Search Semantic Scholar papers.

        Args:
            query: Search query
            max_results: Maximum number of results (up to 100)
            year_range: Tuple of (start_year, end_year)
            fields_of_study: Filter by fields (e.g., ["Computer Science", "Medicine"])
            open_access_only: Only return open access papers

        Returns:
            List of SearchResult objects
        """
        start_time = time.time()
        try:
            params = {
                "query": query,
                "limit": min(100, max_results),
                "fields": "paperId,title,abstract,year,citationCount,influentialCitationCount,"
                         "authors,venue,publicationDate,openAccessPdf,fieldsOfStudy,tldr",
            }

            if year_range:
                params["year"] = f"{year_range[0]}-{year_range[1]}"

            if fields_of_study:
                params["fieldsOfStudy"] = ",".join(fields_of_study)

            if open_access_only:
                params["openAccessPdf"] = ""

            response = self._session.get(S2_SEARCH_URL, params=params, timeout=15)

            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("[SemanticScholarProvider] Rate limited, waiting...")
                time.sleep(2)
                response = self._session.get(S2_SEARCH_URL, params=params, timeout=15)

            response.raise_for_status()
            data = response.json()

            results = []
            for paper in data.get("data", []):
                results.append(self._paper_to_result(paper))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.85)
            logger.info(f"[SemanticScholarProvider] Found {len(results)} papers for '{query}'")
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[SemanticScholarProvider] Search failed: {e}")
            return []

    def get_paper(self, paper_id: str) -> Optional[SearchResult]:
        """
        Get a paper by Semantic Scholar ID, DOI, or arXiv ID.

        Args:
            paper_id: Paper identifier (S2 ID, DOI:xxx, arXiv:xxx, PMID:xxx)

        Returns:
            SearchResult or None
        """
        try:
            fields = "paperId,title,abstract,year,citationCount,influentialCitationCount," \
                     "authors,venue,publicationDate,openAccessPdf,fieldsOfStudy,tldr," \
                     "references,citations"

            response = self._session.get(
                f"{S2_API_URL}/paper/{paper_id}",
                params={"fields": fields},
                timeout=10,
            )
            response.raise_for_status()
            paper = response.json()

            return self._paper_to_result(paper)

        except Exception as e:
            logger.error(f"[SemanticScholarProvider] get_paper failed: {e}")
            return None

    def get_paper_citations(
        self,
        paper_id: str,
        max_results: int = 20,
        influential_only: bool = False,
    ) -> List[SearchResult]:
        """
        Get papers that cite a given paper.

        Args:
            paper_id: Paper identifier
            max_results: Maximum number of citations
            influential_only: Only return influential citations

        Returns:
            List of citing papers
        """
        try:
            fields = "paperId,title,abstract,year,citationCount,authors,venue"
            params = {
                "fields": f"citingPaper.{fields}",
                "limit": min(1000, max_results),
            }

            response = self._session.get(
                f"{S2_API_URL}/paper/{paper_id}/citations",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("data", []):
                citing_paper = item.get("citingPaper", {})
                if citing_paper:
                    # Filter influential if requested
                    if influential_only and not item.get("isInfluential"):
                        continue
                    results.append(self._paper_to_result(citing_paper))

            return results[:max_results]

        except Exception as e:
            logger.error(f"[SemanticScholarProvider] get_paper_citations failed: {e}")
            return []

    def get_paper_references(
        self, paper_id: str, max_results: int = 20
    ) -> List[SearchResult]:
        """
        Get papers referenced by a given paper.

        Args:
            paper_id: Paper identifier
            max_results: Maximum number of references

        Returns:
            List of referenced papers
        """
        try:
            fields = "paperId,title,abstract,year,citationCount,authors,venue"
            params = {
                "fields": f"citedPaper.{fields}",
                "limit": min(1000, max_results),
            }

            response = self._session.get(
                f"{S2_API_URL}/paper/{paper_id}/references",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("data", []):
                cited_paper = item.get("citedPaper", {})
                if cited_paper:
                    results.append(self._paper_to_result(cited_paper))

            return results[:max_results]

        except Exception as e:
            logger.error(f"[SemanticScholarProvider] get_paper_references failed: {e}")
            return []

    def search_author(
        self, author_name: str, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for authors by name.

        Args:
            author_name: Author name to search
            max_results: Maximum number of results

        Returns:
            List of author information dictionaries
        """
        try:
            params = {
                "query": author_name,
                "limit": min(100, max_results),
                "fields": "authorId,name,affiliations,paperCount,citationCount,hIndex",
            }

            response = self._session.get(
                f"{S2_API_URL}/author/search",
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            return data.get("data", [])

        except Exception as e:
            logger.error(f"[SemanticScholarProvider] search_author failed: {e}")
            return []

    def _paper_to_result(self, paper: Dict[str, Any]) -> SearchResult:
        """Convert S2 paper dict to SearchResult."""
        paper_id = paper.get("paperId", "")

        # Get authors
        authors = []
        for author in paper.get("authors", []):
            if author.get("name"):
                authors.append(author["name"])

        # Get abstract or TLDR
        abstract = paper.get("abstract") or ""
        tldr = paper.get("tldr", {})
        if tldr and not abstract:
            abstract = tldr.get("text", "")

        # Calculate score based on citations
        citations = paper.get("citationCount", 0) or 0
        influential = paper.get("influentialCitationCount", 0) or 0
        score = min(0.95, 0.5 + (citations / 1000) * 0.3 + (influential / 100) * 0.15)

        # Get PDF URL if available
        pdf_info = paper.get("openAccessPdf") or {}
        pdf_url = pdf_info.get("url", "")

        return SearchResult(
            title=paper.get("title", ""),
            url=f"https://www.semanticscholar.org/paper/{paper_id}",
            snippet=abstract[:500] if abstract else "",
            content=abstract,
            score=score,
            published_date=paper.get("publicationDate"),
            provider=self.name,
            raw_data={
                "paper_id": paper_id,
                "authors": authors,
                "year": paper.get("year"),
                "venue": paper.get("venue"),
                "citation_count": citations,
                "influential_citation_count": influential,
                "fields_of_study": paper.get("fieldsOfStudy") or [],
                "pdf_url": pdf_url,
                "tldr": tldr.get("text") if tldr else None,
            },
        )
