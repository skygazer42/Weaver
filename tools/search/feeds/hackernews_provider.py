"""
HackerNews Search Provider.

Uses HackerNews Algolia API for search.
No API key required.
Supports:
- Story search
- Comment search
- Front page top stories
- Filter by points, date
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from tools.search.multi_search import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

# Algolia API endpoints
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_SEARCH_BY_DATE_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"


class HackerNewsProvider(SearchProvider):
    """HackerNews Algolia API search provider."""

    def __init__(self):
        # No API key required for HackerNews
        super().__init__("hackernews", None)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Weaver/1.0 (Research Tool)"
        })

    def is_available(self) -> bool:
        """HackerNews is always available (no API key needed)."""
        return True

    def search(
        self,
        query: str,
        max_results: int = 10,
        tags: Optional[str] = None,
        sort_by_date: bool = False,
        min_points: int = 0,
    ) -> List[SearchResult]:
        """
        Search HackerNews stories and comments.

        Args:
            query: Search query
            max_results: Maximum number of results
            tags: Filter tags (story, comment, poll, ask_hn, show_hn, front_page)
            sort_by_date: Sort by date instead of relevance
            min_points: Minimum points filter

        Returns:
            List of SearchResult objects
        """
        start_time = time.time()
        try:
            url = HN_SEARCH_BY_DATE_URL if sort_by_date else HN_SEARCH_URL

            params = {
                "query": query,
                "hitsPerPage": min(50, max_results),
            }

            if tags:
                params["tags"] = tags

            if min_points > 0:
                params["numericFilters"] = f"points>={min_points}"

            response = self._session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            results = []
            for hit in data.get("hits", []):
                # Determine if it's a story or comment
                is_story = hit.get("_tags", []) and "story" in hit.get("_tags", [])

                if is_story:
                    title = hit.get("title", "")
                    url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    snippet = hit.get("title", "")
                else:
                    # Comment
                    title = f"Comment by {hit.get('author', 'unknown')}"
                    url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    snippet = hit.get("comment_text", "")[:500] if hit.get("comment_text") else ""

                # Calculate score from points and comments
                points = hit.get("points") or 0
                num_comments = hit.get("num_comments") or 0
                score = min(1.0, (points / 500 + num_comments / 200) / 2)

                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        content=hit.get("comment_text") or hit.get("story_text") or "",
                        score=score,
                        published_date=hit.get("created_at"),
                        provider=self.name,
                        raw_data={
                            "object_id": hit.get("objectID"),
                            "author": hit.get("author"),
                            "points": points,
                            "num_comments": num_comments,
                            "story_id": hit.get("story_id"),
                            "parent_id": hit.get("parent_id"),
                            "tags": hit.get("_tags", []),
                        },
                    )
                )

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.8)
            logger.info(f"[HackerNewsProvider] Found {len(results)} items for '{query}'")
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[HackerNewsProvider] Search failed: {e}")
            return []

    def get_top_stories(self, max_results: int = 30) -> List[SearchResult]:
        """
        Get current top stories from HackerNews front page.

        Args:
            max_results: Maximum number of stories

        Returns:
            List of SearchResult objects
        """
        try:
            # Get top story IDs
            response = self._session.get(HN_TOP_STORIES_URL, timeout=10)
            response.raise_for_status()
            story_ids = response.json()[:max_results]

            results = []
            for story_id in story_ids:
                story = self._get_item(story_id)
                if not story or story.get("type") != "story":
                    continue

                points = story.get("score", 0)
                num_comments = story.get("descendants", 0)
                score = min(1.0, (points / 500 + num_comments / 200) / 2)

                results.append(
                    SearchResult(
                        title=story.get("title", ""),
                        url=story.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
                        snippet=story.get("title", ""),
                        content=story.get("text") or "",
                        score=score,
                        published_date=self._format_timestamp(story.get("time")),
                        provider=self.name,
                        raw_data={
                            "object_id": str(story_id),
                            "author": story.get("by"),
                            "points": points,
                            "num_comments": num_comments,
                            "type": story.get("type"),
                        },
                    )
                )

            return results

        except Exception as e:
            logger.error(f"[HackerNewsProvider] get_top_stories failed: {e}")
            return []

    def get_ask_hn(self, max_results: int = 20) -> List[SearchResult]:
        """Get recent Ask HN posts."""
        return self.search("", max_results=max_results, tags="ask_hn", sort_by_date=True)

    def get_show_hn(self, max_results: int = 20) -> List[SearchResult]:
        """Get recent Show HN posts."""
        return self.search("", max_results=max_results, tags="show_hn", sort_by_date=True)

    def get_story_comments(
        self, story_id: str, max_comments: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get comments for a HackerNews story.

        Args:
            story_id: HackerNews story ID
            max_comments: Maximum number of comments

        Returns:
            List of comment dictionaries
        """
        try:
            story = self._get_item(int(story_id))
            if not story:
                return []

            comment_ids = story.get("kids", [])[:max_comments]
            comments = []

            for cid in comment_ids:
                comment = self._get_item(cid)
                if comment and comment.get("type") == "comment":
                    comments.append({
                        "id": str(cid),
                        "author": comment.get("by", "[deleted]"),
                        "text": comment.get("text", ""),
                        "time": self._format_timestamp(comment.get("time")),
                        "parent_id": str(comment.get("parent")),
                        "replies_count": len(comment.get("kids", [])),
                    })

            return comments

        except Exception as e:
            logger.error(f"[HackerNewsProvider] get_story_comments failed: {e}")
            return []

    def _get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single HN item by ID."""
        try:
            response = self._session.get(
                HN_ITEM_URL.format(item_id),
                timeout=5,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    @staticmethod
    def _format_timestamp(unix_time: Optional[int]) -> Optional[str]:
        """Format Unix timestamp to ISO string."""
        if not unix_time:
            return None
        from datetime import datetime

        return datetime.utcfromtimestamp(unix_time).isoformat()
