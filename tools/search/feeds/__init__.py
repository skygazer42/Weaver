"""
Real-time Feed Providers for Weaver.

Provides access to social media and tech news feeds:
- Twitter/X (via tweepy)
- Reddit (via PRAW)
- HackerNews (via Algolia API)
"""

from tools.search.feeds.hackernews_provider import HackerNewsProvider
from tools.search.feeds.reddit_provider import RedditProvider
from tools.search.feeds.twitter_provider import TwitterProvider

__all__ = [
    "TwitterProvider",
    "RedditProvider",
    "HackerNewsProvider",
]
