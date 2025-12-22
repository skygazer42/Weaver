"""
Enhanced Content Extractor for web pages.

Inspired by @agent-infra/browser-context, this module provides intelligent
content extraction from web pages, converting them to structured Markdown.

Features:
- Smart main content detection (similar to Readability algorithm)
- HTML to Markdown conversion with GFM support
- Metadata extraction (title, description, author, etc.)
- Interactive element detection (forms, buttons, links)
- Table and code block preservation

Usage:
    from tools.browser.content_extractor import extract_page_content

    content = await extract_page_content(page)
    print(content.title)
    print(content.markdown)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExtractedLink:
    """Represents an extracted link."""
    text: str
    url: str
    title: Optional[str] = None


@dataclass
class ExtractedForm:
    """Represents an extracted form."""
    action: str
    method: str
    inputs: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ExtractedContent:
    """Structured content extracted from a webpage."""
    url: str
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[str] = None
    text: str = ""
    markdown: str = ""
    links: List[ExtractedLink] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    forms: List[ExtractedForm] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


# JavaScript for content extraction (injected into page)
EXTRACTION_SCRIPT = """
() => {
    // Helper functions
    const getMetaContent = (name) => {
        const meta = document.querySelector(`meta[name="${name}"], meta[property="${name}"]`);
        return meta ? meta.getAttribute('content') : null;
    };

    const getTextContent = (el) => {
        if (!el) return '';
        return el.innerText || el.textContent || '';
    };

    const isVisible = (el) => {
        const style = window.getComputedStyle(el);
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               style.opacity !== '0' &&
               el.offsetWidth > 0 &&
               el.offsetHeight > 0;
    };

    // Extract metadata
    const metadata = {
        title: document.title || '',
        description: getMetaContent('description') || getMetaContent('og:description') || '',
        author: getMetaContent('author') || getMetaContent('article:author') || '',
        published: getMetaContent('article:published_time') || getMetaContent('datePublished') || '',
        url: window.location.href,
        canonical: document.querySelector('link[rel="canonical"]')?.href || '',
    };

    // Extract main content
    // Try common article containers first
    const contentSelectors = [
        'article',
        '[role="main"]',
        'main',
        '.post-content',
        '.article-content',
        '.entry-content',
        '.content',
        '#content',
        '.main-content',
        '#main-content',
    ];

    let mainContent = null;
    for (const selector of contentSelectors) {
        const el = document.querySelector(selector);
        if (el && getTextContent(el).length > 200) {
            mainContent = el;
            break;
        }
    }

    // Fallback to body
    if (!mainContent) {
        mainContent = document.body;
    }

    // Extract visible text
    const extractText = (el) => {
        const walker = document.createTreeWalker(
            el,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: (node) => {
                    const parent = node.parentElement;
                    if (!parent) return NodeFilter.FILTER_REJECT;
                    const tag = parent.tagName.toLowerCase();
                    if (['script', 'style', 'noscript', 'svg'].includes(tag)) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (!isVisible(parent)) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );

        let text = '';
        while (walker.nextNode()) {
            const content = walker.currentNode.textContent.trim();
            if (content) {
                text += content + ' ';
            }
        }
        return text.replace(/\\s+/g, ' ').trim();
    };

    // Extract headings
    const headings = [];
    mainContent.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
        const text = getTextContent(h).trim();
        if (text && text.length < 200) {
            headings.push({
                level: parseInt(h.tagName[1]),
                text: text
            });
        }
    });

    // Extract links
    const links = [];
    const seenUrls = new Set();
    mainContent.querySelectorAll('a[href]').forEach(a => {
        const href = a.href;
        const text = getTextContent(a).trim();
        if (href && text && !seenUrls.has(href) && !href.startsWith('javascript:')) {
            seenUrls.add(href);
            links.push({
                text: text.slice(0, 100),
                url: href,
                title: a.title || null
            });
        }
    });

    // Extract images
    const images = [];
    mainContent.querySelectorAll('img[src]').forEach(img => {
        if (isVisible(img) && img.naturalWidth > 100) {
            images.push({
                src: img.src,
                alt: img.alt || '',
                title: img.title || '',
                width: img.naturalWidth,
                height: img.naturalHeight
            });
        }
    });

    // Extract forms
    const forms = [];
    document.querySelectorAll('form').forEach(form => {
        const inputs = [];
        form.querySelectorAll('input, textarea, select').forEach(input => {
            inputs.push({
                type: input.type || input.tagName.toLowerCase(),
                name: input.name || '',
                id: input.id || '',
                placeholder: input.placeholder || ''
            });
        });
        if (inputs.length > 0) {
            forms.push({
                action: form.action || '',
                method: (form.method || 'get').toUpperCase(),
                inputs: inputs
            });
        }
    });

    // Simple HTML to Markdown conversion
    const htmlToMarkdown = (el) => {
        let md = '';

        const processNode = (node, depth = 0) => {
            if (node.nodeType === Node.TEXT_NODE) {
                return node.textContent;
            }

            if (node.nodeType !== Node.ELEMENT_NODE) {
                return '';
            }

            if (!isVisible(node)) {
                return '';
            }

            const tag = node.tagName.toLowerCase();

            // Skip unwanted elements
            if (['script', 'style', 'noscript', 'svg', 'nav', 'footer', 'aside'].includes(tag)) {
                return '';
            }

            let content = '';
            node.childNodes.forEach(child => {
                content += processNode(child, depth + 1);
            });
            content = content.trim();

            if (!content && !['img', 'br', 'hr'].includes(tag)) {
                return '';
            }

            switch (tag) {
                case 'h1': return '\\n# ' + content + '\\n\\n';
                case 'h2': return '\\n## ' + content + '\\n\\n';
                case 'h3': return '\\n### ' + content + '\\n\\n';
                case 'h4': return '\\n#### ' + content + '\\n\\n';
                case 'h5': return '\\n##### ' + content + '\\n\\n';
                case 'h6': return '\\n###### ' + content + '\\n\\n';
                case 'p': return '\\n' + content + '\\n\\n';
                case 'br': return '\\n';
                case 'hr': return '\\n---\\n\\n';
                case 'strong':
                case 'b': return '**' + content + '**';
                case 'em':
                case 'i': return '*' + content + '*';
                case 'code': return '`' + content + '`';
                case 'pre': return '\\n```\\n' + content + '\\n```\\n\\n';
                case 'blockquote': return '\\n> ' + content.replace(/\\n/g, '\\n> ') + '\\n\\n';
                case 'a':
                    const href = node.getAttribute('href');
                    if (href && !href.startsWith('javascript:')) {
                        return '[' + content + '](' + href + ')';
                    }
                    return content;
                case 'img':
                    const src = node.getAttribute('src');
                    const alt = node.getAttribute('alt') || '';
                    return src ? '![' + alt + '](' + src + ')' : '';
                case 'ul':
                    return '\\n' + content + '\\n';
                case 'ol':
                    return '\\n' + content + '\\n';
                case 'li':
                    return '- ' + content + '\\n';
                case 'table':
                    return '\\n' + content + '\\n';
                case 'tr':
                    return '| ' + content + '\\n';
                case 'th':
                case 'td':
                    return content + ' | ';
                default:
                    return content;
            }
        };

        md = processNode(el);

        // Clean up
        md = md
            .replace(/\\n{3,}/g, '\\n\\n')  // Max 2 newlines
            .replace(/^\\s+|\\s+$/g, '')     // Trim
            .replace(/\\| \\n/g, '|\\n');    // Fix table rows

        return md;
    };

    return {
        metadata: metadata,
        text: extractText(mainContent),
        markdown: htmlToMarkdown(mainContent),
        headings: headings,
        links: links.slice(0, 50),  // Limit to 50 links
        images: images.slice(0, 20), // Limit to 20 images
        forms: forms
    };
}
"""


async def extract_page_content(page: Any) -> ExtractedContent:
    """
    Extract structured content from a Playwright page.

    Args:
        page: Playwright Page object

    Returns:
        ExtractedContent with title, text, markdown, links, etc.
    """
    try:
        # Execute extraction script
        result = await page.evaluate(EXTRACTION_SCRIPT)

        metadata = result.get("metadata", {})

        # Build ExtractedContent
        content = ExtractedContent(
            url=metadata.get("url", page.url),
            title=metadata.get("title", ""),
            description=metadata.get("description"),
            author=metadata.get("author"),
            published_date=metadata.get("published"),
            text=result.get("text", ""),
            markdown=result.get("markdown", ""),
            headings=[h["text"] for h in result.get("headings", [])],
            links=[
                ExtractedLink(
                    text=link.get("text", ""),
                    url=link.get("url", ""),
                    title=link.get("title")
                )
                for link in result.get("links", [])
            ],
            images=result.get("images", []),
            forms=[
                ExtractedForm(
                    action=form.get("action", ""),
                    method=form.get("method", "GET"),
                    inputs=form.get("inputs", [])
                )
                for form in result.get("forms", [])
            ],
            metadata=metadata
        )

        logger.debug(f"Extracted content from {content.url}: "
                    f"{len(content.text)} chars, {len(content.links)} links")

        return content

    except Exception as e:
        logger.error(f"Failed to extract page content: {e}")
        # Return minimal content on error
        return ExtractedContent(
            url=page.url if hasattr(page, 'url') else "",
            title="",
            text="",
            markdown=""
        )


def extract_page_content_sync(page: Any) -> ExtractedContent:
    """
    Synchronous version of extract_page_content.

    Args:
        page: Playwright Page object (sync API)

    Returns:
        ExtractedContent with title, text, markdown, links, etc.
    """
    try:
        # Execute extraction script
        result = page.evaluate(EXTRACTION_SCRIPT)

        metadata = result.get("metadata", {})

        # Build ExtractedContent
        content = ExtractedContent(
            url=metadata.get("url", page.url),
            title=metadata.get("title", ""),
            description=metadata.get("description"),
            author=metadata.get("author"),
            published_date=metadata.get("published"),
            text=result.get("text", ""),
            markdown=result.get("markdown", ""),
            headings=[h["text"] for h in result.get("headings", [])],
            links=[
                ExtractedLink(
                    text=link.get("text", ""),
                    url=link.get("url", ""),
                    title=link.get("title")
                )
                for link in result.get("links", [])
            ],
            images=result.get("images", []),
            forms=[
                ExtractedForm(
                    action=form.get("action", ""),
                    method=form.get("method", "GET"),
                    inputs=form.get("inputs", [])
                )
                for form in result.get("forms", [])
            ],
            metadata=metadata
        )

        return content

    except Exception as e:
        logger.error(f"Failed to extract page content: {e}")
        return ExtractedContent(
            url=page.url if hasattr(page, 'url') else "",
            title="",
            text="",
            markdown=""
        )


def clean_markdown(markdown: str) -> str:
    """
    Clean and normalize extracted markdown.

    Args:
        markdown: Raw markdown string

    Returns:
        Cleaned markdown
    """
    # Remove excessive whitespace
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)

    # Remove empty links
    markdown = re.sub(r'\[\s*\]\([^)]*\)', '', markdown)

    # Remove empty headers
    markdown = re.sub(r'^#{1,6}\s*$', '', markdown, flags=re.MULTILINE)

    # Normalize list items
    markdown = re.sub(r'^(\s*)-\s+', r'\1- ', markdown, flags=re.MULTILINE)

    return markdown.strip()
