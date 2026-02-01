"""
Reddit Search Provider.

Uses PRAW (Python Reddit API Wrapper) for Reddit search.
Supports:
- Subreddit search
- All of Reddit search
- Sort: hot, new, top, rising
- Time filter: hour, day, week, month, year, all
"""

import logging
import time
from typing import Any, Dict, List, Optional

from common.config import settings
from tools.search.multi_search import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class RedditProvider(SearchProvider):
    """Reddit PRAW search provider."""

    def __init__(self):
        client_id = getattr(settings, "reddit_client_id", None)
        super().__init__("reddit", client_id)
        self._reddit = None

    def _get_reddit(self):
        """Lazy initialize PRAW Reddit instance."""
        if self._reddit is None:
            try:
                import praw

                client_id = getattr(settings, "reddit_client_id", "")
                client_secret = getattr(settings, "reddit_client_secret", "")
                user_agent = getattr(settings, "reddit_user_agent", "Weaver/1.0")

                if client_id and client_secret:
                    self._reddit = praw.Reddit(
                        client_id=client_id,
                        client_secret=client_secret,
                        user_agent=user_agent,
                    )
            except ImportError:
                logger.warning("[RedditProvider] praw not installed")
        return self._reddit

    def is_available(self) -> bool:
        """Check if Reddit API is configured."""
        client_id = getattr(settings, "reddit_client_id", "")
        client_secret = getattr(settings, "reddit_client_secret", "")
        if not (client_id and client_secret):
            return False
        try:
            import praw

            return True
        except ImportError:
            return False

    def search(
        self,
        query: str,
        max_results: int = 10,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time_filter: str = "all",
    ) -> List[SearchResult]:
        """
        Search Reddit posts.

        Args:
            query: Search query
            max_results: Maximum number of results
            subreddit: Specific subreddit to search (None for all)
            sort: Sort order (relevance, hot, top, new, comments)
            time_filter: Time filter (hour, day, week, month, year, all)

        Returns:
            List of SearchResult objects
        """
        reddit = self._get_reddit()
        if not reddit:
            return []

        start_time = time.time()
        try:
            # Get the search target
            if subreddit:
                search_target = reddit.subreddit(subreddit)
            else:
                search_target = reddit.subreddit("all")

            # Execute search
            submissions = search_target.search(
                query,
                sort=sort,
                time_filter=time_filter,
                limit=max_results,
            )

            results = []
            for post in submissions:
                # Calculate score based on upvotes and comments
                upvote_score = min(1.0, post.score / 10000)
                comment_score = min(1.0, post.num_comments / 1000)
                combined_score = (upvote_score * 0.6 + comment_score * 0.4)

                # Build snippet
                snippet = post.selftext[:500] if post.selftext else post.title
                if post.is_self:
                    content = post.selftext
                else:
                    content = f"[Link: {post.url}]\n\n{post.selftext}"

                results.append(
                    SearchResult(
                        title=post.title,
                        url=f"https://reddit.com{post.permalink}",
                        snippet=snippet,
                        content=content,
                        score=combined_score,
                        published_date=self._format_timestamp(post.created_utc),
                        provider=self.name,
                        raw_data={
                            "post_id": post.id,
                            "subreddit": post.subreddit.display_name,
                            "author": str(post.author) if post.author else "[deleted]",
                            "upvotes": post.score,
                            "upvote_ratio": post.upvote_ratio,
                            "num_comments": post.num_comments,
                            "is_self": post.is_self,
                            "link_url": post.url if not post.is_self else None,
                            "awards": post.total_awards_received,
                            "flair": post.link_flair_text,
                        },
                    )
                )

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.75)
            logger.info(f"[RedditProvider] Found {len(results)} posts for '{query}'")
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[RedditProvider] Search failed: {e}")
            return []

    def get_hot_posts(
        self, subreddit: str = "all", max_results: int = 10
    ) -> List[SearchResult]:
        """
        Get hot posts from a subreddit.

        Args:
            subreddit: Subreddit name
            max_results: Maximum number of posts

        Returns:
            List of SearchResult objects
        """
        reddit = self._get_reddit()
        if not reddit:
            return []

        try:
            sub = reddit.subreddit(subreddit)
            results = []

            for post in sub.hot(limit=max_results):
                upvote_score = min(1.0, post.score / 10000)
                comment_score = min(1.0, post.num_comments / 1000)
                combined_score = (upvote_score * 0.6 + comment_score * 0.4)

                results.append(
                    SearchResult(
                        title=post.title,
                        url=f"https://reddit.com{post.permalink}",
                        snippet=post.selftext[:500] if post.selftext else post.title,
                        content=post.selftext,
                        score=combined_score,
                        published_date=self._format_timestamp(post.created_utc),
                        provider=self.name,
                        raw_data={
                            "post_id": post.id,
                            "subreddit": subreddit,
                            "upvotes": post.score,
                            "num_comments": post.num_comments,
                        },
                    )
                )

            return results

        except Exception as e:
            logger.error(f"[RedditProvider] get_hot_posts failed: {e}")
            return []

    def get_post_comments(
        self, post_url: str, max_comments: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top comments from a Reddit post.

        Args:
            post_url: Full Reddit post URL
            max_comments: Maximum number of comments

        Returns:
            List of comment dictionaries
        """
        reddit = self._get_reddit()
        if not reddit:
            return []

        try:
            submission = reddit.submission(url=post_url)
            submission.comments.replace_more(limit=0)

            comments = []
            for comment in submission.comments[:max_comments]:
                comments.append({
                    "id": comment.id,
                    "author": str(comment.author) if comment.author else "[deleted]",
                    "body": comment.body,
                    "score": comment.score,
                    "created_utc": self._format_timestamp(comment.created_utc),
                    "is_op": comment.is_submitter,
                })

            return comments

        except Exception as e:
            logger.error(f"[RedditProvider] get_post_comments failed: {e}")
            return []

    @staticmethod
    def _format_timestamp(utc_timestamp: float) -> str:
        """Format Unix timestamp to ISO string."""
        from datetime import datetime

        return datetime.utcfromtimestamp(utc_timestamp).isoformat()
