from typing import List, Dict, Any, Optional
from langchain.tools import tool

try:
    from crawl4ai import crawl
except ImportError:
    crawl = None


@tool
def crawl4ai(urls: List[str], max_depth: int = 1, max_pages: int = 20) -> List[Dict[str, Any]]:
    """
    Crawl web pages using crawl4ai (if installed). Returns list of page dicts.
    """
    if crawl is None:
        return [{"error": "crawl4ai not installed"}]
    results = []
    for url in urls:
        try:
            data = crawl(url, max_depth=max_depth, max_pages=max_pages)
            results.append({"url": url, "data": data})
        except Exception as e:
            results.append({"url": url, "error": str(e)})
    return results
