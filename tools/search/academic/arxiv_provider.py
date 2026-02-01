"""
arXiv Search Provider.

Uses arXiv API for searching preprints.
No API key required.
Supports:
- Full-text search
- Category filtering (cs.AI, physics.*, etc.)
- Date range filtering
- Author search
"""

import logging
import time
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import requests

from common.config import settings
from tools.search.multi_search import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"

# arXiv category mappings
ARXIV_CATEGORIES = {
    "cs": "Computer Science",
    "math": "Mathematics",
    "physics": "Physics",
    "q-bio": "Quantitative Biology",
    "q-fin": "Quantitative Finance",
    "stat": "Statistics",
    "eess": "Electrical Engineering and Systems Science",
    "econ": "Economics",
}


class ArxivProvider(SearchProvider):
    """arXiv API search provider."""

    def __init__(self):
        # No API key required for arXiv
        super().__init__("arxiv", None)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Weaver/1.0 (Research Tool; mailto:research@example.com)"
        })

    def is_available(self) -> bool:
        """arXiv is always available if enabled."""
        return getattr(settings, "arxiv_enabled", True)

    def search(
        self,
        query: str,
        max_results: int = 10,
        categories: Optional[List[str]] = None,
        sort_by: str = "relevance",
        sort_order: str = "descending",
    ) -> List[SearchResult]:
        """
        Search arXiv papers.

        Args:
            query: Search query (supports arXiv operators: ti:, au:, abs:, cat:)
            max_results: Maximum number of results
            categories: Filter by categories (e.g., ["cs.AI", "cs.LG"])
            sort_by: Sort field (relevance, lastUpdatedDate, submittedDate)
            sort_order: Sort order (ascending, descending)

        Returns:
            List of SearchResult objects
        """
        start_time = time.time()
        try:
            # Build search query
            search_query = query
            if categories:
                cat_query = " OR ".join([f"cat:{cat}" for cat in categories])
                search_query = f"({query}) AND ({cat_query})"

            params = {
                "search_query": f"all:{search_query}",
                "start": 0,
                "max_results": min(100, max_results),
                "sortBy": sort_by,
                "sortOrder": sort_order,
            }

            response = self._session.get(ARXIV_API_URL, params=params, timeout=30)
            response.raise_for_status()

            # Parse Atom XML response
            results = self._parse_arxiv_response(response.text)

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.9)
            logger.info(f"[ArxivProvider] Found {len(results)} papers for '{query}'")
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[ArxivProvider] Search failed: {e}")
            return []

    def search_by_author(
        self, author: str, max_results: int = 20
    ) -> List[SearchResult]:
        """Search papers by author name."""
        return self.search(f"au:{author}", max_results=max_results)

    def search_by_title(self, title: str, max_results: int = 10) -> List[SearchResult]:
        """Search papers by title."""
        return self.search(f"ti:{title}", max_results=max_results)

    def get_paper_by_id(self, arxiv_id: str) -> Optional[SearchResult]:
        """
        Get a specific paper by arXiv ID.

        Args:
            arxiv_id: arXiv ID (e.g., "2301.00001" or "arXiv:2301.00001")

        Returns:
            SearchResult or None
        """
        # Clean up ID
        arxiv_id = arxiv_id.replace("arXiv:", "").strip()

        try:
            params = {
                "id_list": arxiv_id,
                "max_results": 1,
            }

            response = self._session.get(ARXIV_API_URL, params=params, timeout=10)
            response.raise_for_status()

            results = self._parse_arxiv_response(response.text)
            return results[0] if results else None

        except Exception as e:
            logger.error(f"[ArxivProvider] get_paper_by_id failed: {e}")
            return None

    def _parse_arxiv_response(self, xml_text: str) -> List[SearchResult]:
        """Parse arXiv Atom XML response into SearchResults."""
        results = []

        # Define namespaces
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }

        try:
            root = ElementTree.fromstring(xml_text)

            for entry in root.findall("atom:entry", namespaces):
                # Extract fields
                title = self._get_text(entry, "atom:title", namespaces)
                summary = self._get_text(entry, "atom:summary", namespaces)
                published = self._get_text(entry, "atom:published", namespaces)
                updated = self._get_text(entry, "atom:updated", namespaces)

                # Get arXiv ID from the id element
                entry_id = self._get_text(entry, "atom:id", namespaces)
                arxiv_id = entry_id.split("/abs/")[-1] if entry_id else ""

                # Get PDF link
                pdf_link = ""
                for link in entry.findall("atom:link", namespaces):
                    if link.get("title") == "pdf":
                        pdf_link = link.get("href", "")
                        break

                # Get abstract page URL
                abs_link = f"https://arxiv.org/abs/{arxiv_id}"

                # Get authors
                authors = []
                for author in entry.findall("atom:author", namespaces):
                    name = self._get_text(author, "atom:name", namespaces)
                    if name:
                        authors.append(name)

                # Get categories
                categories = []
                primary_category = entry.find("arxiv:primary_category", namespaces)
                if primary_category is not None:
                    categories.append(primary_category.get("term", ""))

                for cat in entry.findall("atom:category", namespaces):
                    term = cat.get("term", "")
                    if term and term not in categories:
                        categories.append(term)

                # Get DOI and journal reference if available
                doi = self._get_text(entry, "arxiv:doi", namespaces)
                journal_ref = self._get_text(entry, "arxiv:journal_ref", namespaces)

                # Calculate score based on recency (papers from last year score higher)
                score = 0.7
                if updated:
                    from datetime import datetime
                    try:
                        update_date = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                        days_ago = (datetime.now(update_date.tzinfo) - update_date).days
                        score = max(0.5, min(0.95, 0.95 - (days_ago / 365) * 0.3))
                    except Exception:
                        pass

                results.append(
                    SearchResult(
                        title=title.strip() if title else "",
                        url=abs_link,
                        snippet=summary[:500].strip() if summary else "",
                        content=summary.strip() if summary else "",
                        score=score,
                        published_date=published,
                        provider=self.name,
                        raw_data={
                            "arxiv_id": arxiv_id,
                            "authors": authors,
                            "categories": categories,
                            "primary_category": categories[0] if categories else "",
                            "pdf_url": pdf_link,
                            "doi": doi,
                            "journal_ref": journal_ref,
                            "updated": updated,
                        },
                    )
                )

        except ElementTree.ParseError as e:
            logger.error(f"[ArxivProvider] XML parse error: {e}")

        return results

    @staticmethod
    def _get_text(
        element: ElementTree.Element,
        path: str,
        namespaces: Dict[str, str],
    ) -> str:
        """Safely get text from XML element."""
        child = element.find(path, namespaces)
        return child.text if child is not None and child.text else ""
