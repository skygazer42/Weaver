"""
Twitter/X Search Provider.

Uses Twitter API v2 via tweepy for recent tweet search.
Supports:
- Recent search (last 7 days)
- Operators: from:, to:, #hashtag, @mention
- Rate limit handling (450 requests/15min)
"""

import logging
import time
from typing import Any, Dict, List, Optional

from common.config import settings
from tools.search.multi_search import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class TwitterProvider(SearchProvider):
    """Twitter/X API v2 search provider."""

    def __init__(self):
        api_key = getattr(settings, "twitter_bearer_token", None)
        super().__init__("twitter", api_key)
        self._client = None

    def _get_client(self):
        """Lazy initialize tweepy client."""
        if self._client is None:
            try:
                import tweepy

                bearer_token = getattr(settings, "twitter_bearer_token", "")
                if bearer_token:
                    self._client = tweepy.Client(bearer_token=bearer_token)
            except ImportError:
                logger.warning("[TwitterProvider] tweepy not installed")
        return self._client

    def is_available(self) -> bool:
        """Check if Twitter API is configured."""
        bearer_token = getattr(settings, "twitter_bearer_token", "")
        if not bearer_token:
            return False
        try:
            import tweepy

            return True
        except ImportError:
            return False

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Search recent tweets (last 7 days).

        Args:
            query: Search query (supports Twitter operators)
            max_results: Maximum number of results (10-100)

        Returns:
            List of SearchResult objects
        """
        client = self._get_client()
        if not client:
            return []

        start_time = time.time()
        try:
            # Clamp max_results to Twitter API limits
            max_results = max(10, min(100, max_results))

            # Search recent tweets with expansions
            response = client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=["created_at", "public_metrics", "author_id", "lang"],
                expansions=["author_id"],
                user_fields=["username", "name", "verified"],
            )

            if not response.data:
                return []

            # Build author lookup
            authors = {}
            if response.includes and "users" in response.includes:
                for user in response.includes["users"]:
                    authors[user.id] = {
                        "username": user.username,
                        "name": user.name,
                        "verified": getattr(user, "verified", False),
                    }

            results = []
            for tweet in response.data:
                author = authors.get(tweet.author_id, {})
                username = author.get("username", "unknown")
                metrics = tweet.public_metrics or {}

                # Calculate engagement score
                likes = metrics.get("like_count", 0)
                retweets = metrics.get("retweet_count", 0)
                replies = metrics.get("reply_count", 0)
                engagement = likes + retweets * 2 + replies

                # Normalize score (0-1)
                score = min(1.0, engagement / 1000)

                results.append(
                    SearchResult(
                        title=f"@{username}: {tweet.text[:50]}...",
                        url=f"https://twitter.com/{username}/status/{tweet.id}",
                        snippet=tweet.text,
                        content=tweet.text,
                        score=score,
                        published_date=str(tweet.created_at) if tweet.created_at else None,
                        provider=self.name,
                        raw_data={
                            "tweet_id": str(tweet.id),
                            "author_id": str(tweet.author_id),
                            "username": username,
                            "author_name": author.get("name", ""),
                            "verified": author.get("verified", False),
                            "likes": likes,
                            "retweets": retweets,
                            "replies": replies,
                            "lang": getattr(tweet, "lang", ""),
                        },
                    )
                )

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.7)
            logger.info(f"[TwitterProvider] Found {len(results)} tweets for '{query}'")
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[TwitterProvider] Search failed: {e}")
            return []

    def get_user_tweets(
        self, username: str, max_results: int = 10
    ) -> List[SearchResult]:
        """
        Get recent tweets from a specific user.

        Args:
            username: Twitter username (without @)
            max_results: Maximum number of tweets

        Returns:
            List of SearchResult objects
        """
        client = self._get_client()
        if not client:
            return []

        try:
            # Get user ID first
            user = client.get_user(username=username)
            if not user.data:
                return []

            user_id = user.data.id

            # Get user's tweets
            response = client.get_users_tweets(
                id=user_id,
                max_results=max(5, min(100, max_results)),
                tweet_fields=["created_at", "public_metrics"],
            )

            if not response.data:
                return []

            results = []
            for tweet in response.data:
                metrics = tweet.public_metrics or {}
                likes = metrics.get("like_count", 0)
                retweets = metrics.get("retweet_count", 0)
                score = min(1.0, (likes + retweets * 2) / 1000)

                results.append(
                    SearchResult(
                        title=f"@{username}: {tweet.text[:50]}...",
                        url=f"https://twitter.com/{username}/status/{tweet.id}",
                        snippet=tweet.text,
                        content=tweet.text,
                        score=score,
                        published_date=str(tweet.created_at) if tweet.created_at else None,
                        provider=self.name,
                        raw_data={
                            "tweet_id": str(tweet.id),
                            "username": username,
                            "likes": likes,
                            "retweets": retweets,
                        },
                    )
                )

            return results

        except Exception as e:
            logger.error(f"[TwitterProvider] get_user_tweets failed: {e}")
            return []
