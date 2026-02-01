"""
PubMed Search Provider.

Uses NCBI E-utilities API for biomedical literature search.
Email required, API key optional but recommended.
Supports:
- PubMed article search
- MeSH term support
- Author/affiliation search
- Date range filtering
"""

import logging
import time
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import requests

from common.config import settings
from tools.search.multi_search import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_EINFO_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi"


class PubMedProvider(SearchProvider):
    """PubMed/NCBI E-utilities search provider."""

    def __init__(self):
        api_key = getattr(settings, "pubmed_api_key", None)
        super().__init__("pubmed", api_key)
        self._email = getattr(settings, "pubmed_email", "")
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Weaver/1.0 (Research Tool)"
        })

    def is_available(self) -> bool:
        """PubMed requires email to be configured."""
        email = getattr(settings, "pubmed_email", "")
        return bool(email)

    def search(
        self,
        query: str,
        max_results: int = 10,
        date_range: Optional[tuple] = None,
        sort: str = "relevance",
    ) -> List[SearchResult]:
        """
        Search PubMed articles.

        Args:
            query: Search query (supports PubMed operators: [Title], [Author], [MeSH])
            max_results: Maximum number of results
            date_range: Tuple of (start_date, end_date) in YYYY/MM/DD format
            sort: Sort order (relevance, pub_date, author, journal)

        Returns:
            List of SearchResult objects
        """
        start_time = time.time()
        try:
            # Step 1: Search for PMIDs
            pmids = self._esearch(query, max_results, date_range, sort)
            if not pmids:
                return []

            # Step 2: Fetch article details
            results = self._efetch(pmids)

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.85)
            logger.info(f"[PubMedProvider] Found {len(results)} articles for '{query}'")
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[PubMedProvider] Search failed: {e}")
            return []

    def search_by_author(
        self, author: str, max_results: int = 20
    ) -> List[SearchResult]:
        """Search articles by author name."""
        return self.search(f"{author}[Author]", max_results=max_results)

    def search_by_mesh(
        self, mesh_term: str, max_results: int = 20
    ) -> List[SearchResult]:
        """Search articles by MeSH term."""
        return self.search(f"{mesh_term}[MeSH]", max_results=max_results)

    def get_article(self, pmid: str) -> Optional[SearchResult]:
        """
        Get article details by PMID.

        Args:
            pmid: PubMed ID

        Returns:
            SearchResult or None
        """
        try:
            results = self._efetch([pmid])
            return results[0] if results else None
        except Exception as e:
            logger.error(f"[PubMedProvider] get_article failed: {e}")
            return None

    def _esearch(
        self,
        query: str,
        max_results: int,
        date_range: Optional[tuple],
        sort: str,
    ) -> List[str]:
        """Execute ESearch to get PMIDs."""
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": min(200, max_results),
            "retmode": "json",
            "sort": sort,
            "email": self._email,
        }

        if self.api_key:
            params["api_key"] = self.api_key

        if date_range:
            params["mindate"] = date_range[0]
            params["maxdate"] = date_range[1]
            params["datetype"] = "pdat"

        response = self._session.get(PUBMED_ESEARCH_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        result = data.get("esearchresult", {})
        return result.get("idlist", [])

    def _efetch(self, pmids: List[str]) -> List[SearchResult]:
        """Fetch article details for given PMIDs."""
        if not pmids:
            return []

        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
            "email": self._email,
        }

        if self.api_key:
            params["api_key"] = self.api_key

        response = self._session.get(PUBMED_EFETCH_URL, params=params, timeout=30)
        response.raise_for_status()

        return self._parse_pubmed_xml(response.text)

    def _parse_pubmed_xml(self, xml_text: str) -> List[SearchResult]:
        """Parse PubMed XML response into SearchResults."""
        results = []

        try:
            root = ElementTree.fromstring(xml_text)

            for article in root.findall(".//PubmedArticle"):
                medline = article.find("MedlineCitation")
                if medline is None:
                    continue

                pmid = self._get_text(medline, "PMID")
                article_elem = medline.find("Article")
                if article_elem is None:
                    continue

                # Get title
                title = self._get_text(article_elem, "ArticleTitle")

                # Get abstract
                abstract_elem = article_elem.find("Abstract")
                abstract_parts = []
                if abstract_elem is not None:
                    for text in abstract_elem.findall("AbstractText"):
                        label = text.get("Label", "")
                        content = text.text or ""
                        if label:
                            abstract_parts.append(f"{label}: {content}")
                        else:
                            abstract_parts.append(content)
                abstract = " ".join(abstract_parts)

                # Get authors
                authors = []
                author_list = article_elem.find("AuthorList")
                if author_list is not None:
                    for author in author_list.findall("Author"):
                        last = self._get_text(author, "LastName")
                        first = self._get_text(author, "ForeName")
                        if last:
                            authors.append(f"{last} {first}".strip())

                # Get journal info
                journal_elem = article_elem.find("Journal")
                journal = ""
                pub_date = ""
                if journal_elem is not None:
                    journal = self._get_text(journal_elem, "Title")
                    issue = journal_elem.find("JournalIssue")
                    if issue is not None:
                        pub_date_elem = issue.find("PubDate")
                        if pub_date_elem is not None:
                            year = self._get_text(pub_date_elem, "Year")
                            month = self._get_text(pub_date_elem, "Month")
                            day = self._get_text(pub_date_elem, "Day")
                            pub_date = f"{year}-{month or '01'}-{day or '01'}"

                # Get DOI
                doi = ""
                article_id_list = article.find(".//ArticleIdList")
                if article_id_list is not None:
                    for aid in article_id_list.findall("ArticleId"):
                        if aid.get("IdType") == "doi":
                            doi = aid.text or ""
                            break

                # Get MeSH terms
                mesh_terms = []
                mesh_list = medline.find("MeshHeadingList")
                if mesh_list is not None:
                    for mesh in mesh_list.findall("MeshHeading"):
                        descriptor = mesh.find("DescriptorName")
                        if descriptor is not None and descriptor.text:
                            mesh_terms.append(descriptor.text)

                # Get keywords
                keywords = []
                keyword_list = medline.find("KeywordList")
                if keyword_list is not None:
                    for kw in keyword_list.findall("Keyword"):
                        if kw.text:
                            keywords.append(kw.text)

                # Calculate score (PubMed doesn't provide relevance scores)
                score = 0.7

                results.append(
                    SearchResult(
                        title=title,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        snippet=abstract[:500] if abstract else title,
                        content=abstract,
                        score=score,
                        published_date=pub_date if pub_date else None,
                        provider=self.name,
                        raw_data={
                            "pmid": pmid,
                            "authors": authors,
                            "journal": journal,
                            "doi": doi,
                            "mesh_terms": mesh_terms,
                            "keywords": keywords,
                        },
                    )
                )

        except ElementTree.ParseError as e:
            logger.error(f"[PubMedProvider] XML parse error: {e}")

        return results

    @staticmethod
    def _get_text(element: ElementTree.Element, path: str) -> str:
        """Safely get text from XML element."""
        child = element.find(path)
        return child.text if child is not None and child.text else ""
