"""
Result Aggregator - Intelligent fusion of search results for writer node.

Provides deduplication, relevance ranking, and tiered output to prevent
token explosion when synthesizing research content.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from agent.workflows.source_registry import SourceRegistry

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Normalized search result with metadata."""

    query: str
    title: str
    url: str
    content: str
    timestamp: str = ""
    score: float = 0.0
    source_idx: int = 0
    result_idx: int = 0
    source_id: str = ""
    canonical_url: str = ""

    @property
    def tag(self) -> str:
        """Generate a source tag like S1-1."""
        return f"S{self.source_idx + 1}-{self.result_idx + 1}"

    @property
    def domain(self) -> str:
        """Extract domain from URL."""
        try:
            base_url = self.canonical_url or self.url
            return urlparse(base_url).netloc
        except Exception:
            return ""

    @property
    def url_hash(self) -> str:
        """Generate URL hash for deduplication."""
        if self.source_id:
            return self.source_id
        try:
            base_url = self.canonical_url or self.url
            normalized = urlparse(base_url)._replace(fragment="").geturl().lower().rstrip("/")
        except Exception:
            normalized = self.url.lower().rstrip("/")
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    @property
    def content_fingerprint(self) -> str:
        """Generate content fingerprint for similarity detection."""
        # Normalize content: lowercase, remove punctuation, collapse whitespace
        text = re.sub(r"[^\w\s]", "", self.content.lower())
        text = re.sub(r"\s+", " ", text).strip()
        # Take first 500 chars for fingerprinting
        return hashlib.md5(text[:500].encode()).hexdigest()[:16]


@dataclass
class AggregatedResults:
    """Aggregated and tiered search results."""

    tier_1: List[SearchResult] = field(default_factory=list)  # High relevance
    tier_2: List[SearchResult] = field(default_factory=list)  # Medium relevance
    tier_3: List[SearchResult] = field(default_factory=list)  # Low relevance / backup

    total_before: int = 0
    total_after: int = 0
    duplicates_removed: int = 0

    def all_results(self) -> List[SearchResult]:
        """Get all results in tier order."""
        return self.tier_1 + self.tier_2 + self.tier_3

    def to_context(
        self,
        max_tier_1: int = 5,
        max_tier_2: int = 3,
        max_tier_3: int = 2,
        max_content_length: int = 500,
    ) -> Tuple[str, str]:
        """
        Format results as context for the writer.

        Returns:
            (research_context, sources_table)
        """
        blocks: List[str] = []
        sources: List[str] = []

        # Tier 1 - Primary sources
        if self.tier_1:
            blocks.append("## Primary Sources (High Relevance)")
            for res in self.tier_1[:max_tier_1]:
                content_preview = res.content[:max_content_length]
                if len(res.content) > max_content_length:
                    content_preview += "..."
                blocks.append(f"[{res.tag}] **{res.title}** ({res.domain})")
                blocks.append(f"   Query: {res.query}")
                blocks.append(f"   {content_preview}")
                blocks.append("")
                display_url = res.canonical_url or res.url
                sources.append(f"[{res.tag}] {res.title} - {display_url}")

        # Tier 2 - Supporting sources
        if self.tier_2:
            blocks.append("## Supporting Sources (Medium Relevance)")
            for res in self.tier_2[:max_tier_2]:
                content_preview = res.content[: max_content_length // 2]
                if len(res.content) > max_content_length // 2:
                    content_preview += "..."
                blocks.append(f"[{res.tag}] **{res.title}** ({res.domain})")
                blocks.append(f"   {content_preview}")
                blocks.append("")
                display_url = res.canonical_url or res.url
                sources.append(f"[{res.tag}] {res.title} - {display_url}")

        # Tier 3 - Additional context (abbreviated)
        if self.tier_3:
            blocks.append("## Additional Sources")
            for res in self.tier_3[:max_tier_3]:
                blocks.append(f"[{res.tag}] {res.title} ({res.domain})")
                display_url = res.canonical_url or res.url
                sources.append(f"[{res.tag}] {res.title} - {display_url}")

        return "\n".join(blocks), "\n".join(sources)


class ResultAggregator:
    """
    Aggregates and ranks search results for efficient writer consumption.

    Features:
    - URL-based deduplication
    - Semantic similarity detection (lightweight, no embeddings)
    - Query-relevance scoring
    - Tiered output (primary, supporting, additional)
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        max_results_per_query: int = 3,
        tier_1_threshold: float = 0.6,
        tier_2_threshold: float = 0.3,
    ):
        self.similarity_threshold = similarity_threshold
        self.max_results_per_query = max_results_per_query
        self.tier_1_threshold = tier_1_threshold
        self.tier_2_threshold = tier_2_threshold

    def aggregate(
        self,
        scraped_content: List[Dict[str, Any]],
        original_query: str = "",
    ) -> AggregatedResults:
        """
        Aggregate and rank search results.

        Args:
            scraped_content: Raw scraped content from parallel searches
            original_query: The user's original question for relevance scoring

        Returns:
            AggregatedResults with tiered, deduplicated results
        """
        # Step 1: Normalize all results
        all_results = self._normalize_results(scraped_content)
        total_before = len(all_results)

        if not all_results:
            return AggregatedResults(total_before=0, total_after=0)

        # Step 2: Deduplicate by URL
        url_deduped = self._dedupe_by_url(all_results)

        # Step 3: Deduplicate by content similarity
        content_deduped = self._dedupe_by_similarity(url_deduped)
        duplicates_removed = total_before - len(content_deduped)

        # Step 4: Score by relevance
        scored = self._score_relevance(content_deduped, original_query)

        # Step 5: Sort by score and tier
        scored.sort(key=lambda x: x.score, reverse=True)

        # Step 6: Assign to tiers
        tier_1, tier_2, tier_3 = [], [], []
        for res in scored:
            if res.score >= self.tier_1_threshold:
                tier_1.append(res)
            elif res.score >= self.tier_2_threshold:
                tier_2.append(res)
            else:
                tier_3.append(res)

        logger.info(
            f"[aggregator] Aggregated {total_before} -> {len(scored)} results "
            f"(removed {duplicates_removed} duplicates). "
            f"Tiers: {len(tier_1)}/{len(tier_2)}/{len(tier_3)}"
        )

        return AggregatedResults(
            tier_1=tier_1,
            tier_2=tier_2,
            tier_3=tier_3,
            total_before=total_before,
            total_after=len(scored),
            duplicates_removed=duplicates_removed,
        )

    def _normalize_results(self, scraped_content: List[Dict[str, Any]]) -> List[SearchResult]:
        """Convert raw scraped content to normalized SearchResult objects."""
        results: List[SearchResult] = []
        source_registry = SourceRegistry()

        for idx, item in enumerate(scraped_content):
            query = item.get("query", "")
            timestamp = item.get("timestamp", "")
            raw_results = item.get("results") or []

            for ridx, res in enumerate(raw_results[: self.max_results_per_query]):
                title = (res.get("title") or "Untitled").strip()
                url = (res.get("url") or "").strip()
                content = (
                    res.get("content") or res.get("summary") or res.get("snippet") or ""
                ).strip()

                if not url or not content:
                    continue

                source = source_registry.register(url=url, title=title)
                canonical_url = source.canonical_url if source else url
                source_id = source.source_id if source else ""

                results.append(
                    SearchResult(
                        query=query,
                        title=title,
                        url=url,
                        content=content,
                        timestamp=timestamp,
                        source_idx=idx,
                        result_idx=ridx,
                        source_id=source_id,
                        canonical_url=canonical_url,
                    )
                )

        return results

    def _dedupe_by_url(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove duplicates based on URL hash."""
        seen: Dict[str, SearchResult] = {}
        for res in results:
            url_hash = res.url_hash
            if url_hash not in seen:
                seen[url_hash] = res
            else:
                # Keep the one with more content
                if len(res.content) > len(seen[url_hash].content):
                    seen[url_hash] = res
        return list(seen.values())

    def _dedupe_by_similarity(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove near-duplicates based on content similarity."""
        if len(results) <= 1:
            return results

        # Group by fingerprint first (fast exact match)
        fingerprint_groups: Dict[str, List[SearchResult]] = {}
        for res in results:
            fp = res.content_fingerprint
            if fp not in fingerprint_groups:
                fingerprint_groups[fp] = []
            fingerprint_groups[fp].append(res)

        # Take best from each fingerprint group
        candidates: List[SearchResult] = []
        for group in fingerprint_groups.values():
            # Keep the one with most content
            best = max(group, key=lambda x: len(x.content))
            candidates.append(best)

        # Optimized similarity check using set-based tracking
        # Avoid O(N) list.remove() by tracking kept indices
        kept_indices: List[int] = []
        similarity_cache: Dict[tuple, float] = {}

        for i, res in enumerate(candidates):
            is_duplicate = False
            replace_idx = -1

            for j in kept_indices:
                existing = candidates[j]
                # Use cache key based on truncated content hash
                cache_key = (id(res), id(existing))
                if cache_key not in similarity_cache:
                    similarity_cache[cache_key] = self._text_similarity(res.content, existing.content)
                similarity = similarity_cache[cache_key]

                if similarity >= self.similarity_threshold:
                    is_duplicate = True
                    # Keep the longer/better one
                    if len(res.content) > len(existing.content):
                        replace_idx = kept_indices.index(j)
                    break

            if not is_duplicate:
                kept_indices.append(i)
            elif replace_idx >= 0:
                kept_indices[replace_idx] = i

        return [candidates[i] for i in kept_indices]

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity ratio between two texts."""
        # Normalize for comparison
        t1 = text1.lower()[:1000]
        t2 = text2.lower()[:1000]
        return SequenceMatcher(None, t1, t2).ratio()

    def _score_relevance(
        self,
        results: List[SearchResult],
        original_query: str,
    ) -> List[SearchResult]:
        """Score results by relevance to the original query."""
        if not original_query:
            # Without original query, use position-based scoring
            for i, res in enumerate(results):
                res.score = max(0.5, 1.0 - (i * 0.1))
            return results

        query_terms = set(self._tokenize(original_query))

        for res in results:
            score = 0.0

            # Title match (high weight)
            title_terms = set(self._tokenize(res.title))
            title_overlap = len(query_terms & title_terms) / max(len(query_terms), 1)
            score += title_overlap * 0.4

            # Content match (medium weight)
            content_terms = set(self._tokenize(res.content[:500]))
            content_overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
            score += content_overlap * 0.3

            # Search query match (the query that found this result)
            search_query_terms = set(self._tokenize(res.query))
            query_match = len(query_terms & search_query_terms) / max(len(query_terms), 1)
            score += query_match * 0.2

            # Domain authority bonus (simple heuristic)
            if any(
                d in res.domain
                for d in [
                    "wikipedia",
                    "github",
                    "stackoverflow",
                    "arxiv",
                    "nature",
                    "science",
                    ".gov",
                    ".edu",
                    "ieee",
                    "acm",
                ]
            ):
                score += 0.1

            res.score = min(score, 1.0)

        return results

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization for matching."""
        # Remove punctuation and split
        text = re.sub(r"[^\w\s]", " ", text.lower())
        tokens = text.split()
        # Filter short tokens and stopwords
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "and",
            "but",
            "or",
            "nor",
            "so",
            "yet",
            "both",
            "either",
            "neither",
            "not",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "also",
        }
        return [t for t in tokens if len(t) > 2 and t not in stopwords]
