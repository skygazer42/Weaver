"""
Academic Search Providers for Weaver.

Provides access to academic literature:
- arXiv (preprints, no API key)
- Semantic Scholar (papers with citations)
- PubMed (biomedical literature)
"""

from tools.search.academic.arxiv_provider import ArxivProvider
from tools.search.academic.pubmed_provider import PubMedProvider
from tools.search.academic.semantic_scholar_provider import SemanticScholarProvider

__all__ = [
    "ArxivProvider",
    "SemanticScholarProvider",
    "PubMedProvider",
]
