"""
Domain Expert Router.

Classifies research queries by domain and provides domain-specific hints.
Enables specialized handling for different fields like scientific, legal, medical, etc.

Key Features:
1. LLM-based domain classification
2. Domain-specific search hints
3. Confidence scoring
4. Prompt template selection
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ResearchDomain(str, Enum):
    """Supported research domains."""
    SCIENTIFIC = "scientific"      # Academic, research papers
    LEGAL = "legal"                # Laws, regulations, cases
    FINANCIAL = "financial"        # Markets, economics, investments
    TECHNICAL = "technical"        # Software, engineering, tech
    MEDICAL = "medical"            # Health, medicine, clinical
    BUSINESS = "business"          # Companies, industries, markets
    HISTORICAL = "historical"      # History, events, archives
    GENERAL = "general"            # General knowledge


@dataclass
class DomainClassification:
    """Result of domain classification."""
    domain: ResearchDomain
    confidence: float
    reasoning: str
    search_hints: List[str] = field(default_factory=list)
    suggested_sources: List[str] = field(default_factory=list)
    language_hints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "search_hints": self.search_hints,
            "suggested_sources": self.suggested_sources,
            "language_hints": self.language_hints,
        }


# Domain-specific configurations
DOMAIN_CONFIGS = {
    ResearchDomain.SCIENTIFIC: {
        "suggested_sources": ["arxiv.org", "scholar.google.com", "pubmed.ncbi.nlm.nih.gov", "nature.com", "sciencedirect.com"],
        "search_prefixes": ["research paper", "study", "scientific analysis"],
        "language_hints": ["peer-reviewed", "methodology", "hypothesis", "findings"],
    },
    ResearchDomain.LEGAL: {
        "suggested_sources": ["law.cornell.edu", "westlaw.com", "lexisnexis.com", "courtlistener.com"],
        "search_prefixes": ["legal", "law", "regulation", "court case"],
        "language_hints": ["statute", "precedent", "jurisdiction", "ruling"],
    },
    ResearchDomain.FINANCIAL: {
        "suggested_sources": ["bloomberg.com", "reuters.com", "wsj.com", "sec.gov", "finance.yahoo.com"],
        "search_prefixes": ["financial analysis", "market", "investment"],
        "language_hints": ["ROI", "valuation", "market cap", "fiscal"],
    },
    ResearchDomain.TECHNICAL: {
        "suggested_sources": ["github.com", "stackoverflow.com", "docs.microsoft.com", "developer.mozilla.org"],
        "search_prefixes": ["documentation", "tutorial", "implementation", "API"],
        "language_hints": ["algorithm", "framework", "architecture", "protocol"],
    },
    ResearchDomain.MEDICAL: {
        "suggested_sources": ["pubmed.ncbi.nlm.nih.gov", "who.int", "cdc.gov", "mayoclinic.org", "webmd.com"],
        "search_prefixes": ["clinical", "medical study", "treatment", "diagnosis"],
        "language_hints": ["clinical trial", "symptoms", "prognosis", "therapeutic"],
    },
    ResearchDomain.BUSINESS: {
        "suggested_sources": ["crunchbase.com", "linkedin.com", "forbes.com", "businessinsider.com"],
        "search_prefixes": ["company", "industry analysis", "market research"],
        "language_hints": ["revenue", "market share", "competitive analysis", "strategy"],
    },
    ResearchDomain.HISTORICAL: {
        "suggested_sources": ["jstor.org", "archive.org", "britannica.com", "history.com"],
        "search_prefixes": ["historical", "history of", "timeline"],
        "language_hints": ["era", "period", "historical context", "primary source"],
    },
    ResearchDomain.GENERAL: {
        "suggested_sources": ["wikipedia.org", "britannica.com"],
        "search_prefixes": [],
        "language_hints": [],
    },
}

# Provider profiles for multi-search orchestration.
_SOURCE_PROVIDER_HINTS = {
    "arxiv": "arxiv",
    "pubmed": "pubmed",
    "scholar.google": "semantic_scholar",
    "semantic scholar": "semantic_scholar",
    "nature.com": "semantic_scholar",
    "sciencedirect.com": "semantic_scholar",
    "jstor.org": "semantic_scholar",
    "reuters.com": "serper",
    "bloomberg.com": "serper",
    "wsj.com": "serper",
    "sec.gov": "tavily",
    "law.cornell.edu": "tavily",
    "courtlistener.com": "tavily",
    "github.com": "duckduckgo",
    "stackoverflow.com": "duckduckgo",
    "developer.mozilla.org": "duckduckgo",
    "docs.microsoft.com": "duckduckgo",
    "who.int": "tavily",
    "cdc.gov": "tavily",
    "wikipedia.org": "tavily",
}

_DOMAIN_PROVIDER_DEFAULTS = {
    ResearchDomain.SCIENTIFIC: ["arxiv", "pubmed", "semantic_scholar", "exa", "tavily"],
    ResearchDomain.MEDICAL: ["pubmed", "semantic_scholar", "tavily", "serper"],
    ResearchDomain.TECHNICAL: ["duckduckgo", "tavily", "serper", "exa"],
    ResearchDomain.FINANCIAL: ["serper", "tavily", "brave", "exa"],
    ResearchDomain.LEGAL: ["tavily", "serper", "duckduckgo"],
    ResearchDomain.BUSINESS: ["serper", "tavily", "exa"],
    ResearchDomain.HISTORICAL: ["tavily", "duckduckgo", "serper"],
    ResearchDomain.GENERAL: ["tavily", "duckduckgo", "serper"],
}


class DomainClassificationResponse(BaseModel):
    """Structured response for domain classification."""
    domain: str = Field(description="The research domain: scientific, legal, financial, technical, medical, business, historical, or general")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the classification (0-1)")
    reasoning: str = Field(description="Brief explanation for the classification")
    search_hints: List[str] = Field(default_factory=list, description="Domain-specific search query suggestions")


CLASSIFICATION_PROMPT = """
# Task
Classify the following research query into the most appropriate domain.

# Query
{query}

# Available Domains
- scientific: Academic research, scientific studies, peer-reviewed papers
- legal: Laws, regulations, court cases, legal analysis
- financial: Markets, investments, economic analysis, financial data
- technical: Software, engineering, technology documentation
- medical: Health, medicine, clinical studies, treatments
- business: Companies, industries, market research
- historical: History, historical events, archives
- general: General knowledge that doesn't fit other categories

# Instructions
1. Analyze the query to determine its primary domain
2. Consider technical terms, context, and intent
3. Provide confidence (0-1) based on how clearly the query fits the domain
4. Suggest 2-3 domain-specific search query modifications

# Output Format
Respond with the classification in the specified structure.
"""


class DomainClassifier:
    """
    Classifies research queries by domain.

    Uses LLM to identify the domain and provide specialized search hints.
    """

    def __init__(self, llm: BaseChatModel, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}

    def classify(self, query: str, images: List[Dict[str, Any]] = None) -> DomainClassification:
        """
        Classify a research query by domain.

        Args:
            query: The research query
            images: Optional images for context

        Returns:
            DomainClassification with domain and hints
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", CLASSIFICATION_PROMPT)
        ])

        try:
            # Use structured output
            structured_llm = self.llm.with_structured_output(DomainClassificationResponse)
            response = structured_llm.invoke(
                prompt.format_messages(query=query),
                config=self.config,
            )

            # Parse domain
            domain_str = response.domain.lower().strip()
            try:
                domain = ResearchDomain(domain_str)
            except ValueError:
                domain = ResearchDomain.GENERAL

            # Get domain config
            domain_config = DOMAIN_CONFIGS.get(domain, DOMAIN_CONFIGS[ResearchDomain.GENERAL])

            classification = DomainClassification(
                domain=domain,
                confidence=response.confidence,
                reasoning=response.reasoning,
                search_hints=response.search_hints or [],
                suggested_sources=domain_config.get("suggested_sources", []),
                language_hints=domain_config.get("language_hints", []),
            )

            logger.info(
                f"[DomainClassifier] Query classified as {domain.value} "
                f"(confidence: {response.confidence:.2f})"
            )

            return classification

        except Exception as e:
            logger.warning(f"Domain classification failed: {e}, defaulting to general")
            return DomainClassification(
                domain=ResearchDomain.GENERAL,
                confidence=0.5,
                reasoning="Classification failed, using default",
            )

    def get_domain_prompt_path(self, domain: ResearchDomain) -> Optional[str]:
        """
        Get the path to domain-specific prompt template.

        Args:
            domain: Research domain

        Returns:
            Path to prompt template or None
        """
        prompt_dir = "prompts/templates/deepsearch/domains"
        domain_prompts = {
            ResearchDomain.SCIENTIFIC: f"{prompt_dir}/scientific.py",
            ResearchDomain.LEGAL: f"{prompt_dir}/legal.py",
            ResearchDomain.FINANCIAL: f"{prompt_dir}/financial.py",
            ResearchDomain.TECHNICAL: f"{prompt_dir}/technical.py",
            ResearchDomain.MEDICAL: f"{prompt_dir}/medical.py",
        }
        return domain_prompts.get(domain)

    def enhance_query(
        self,
        query: str,
        classification: DomainClassification,
    ) -> str:
        """
        Enhance query with domain-specific terms.

        Args:
            query: Original query
            classification: Domain classification result

        Returns:
            Enhanced query string
        """
        domain_config = DOMAIN_CONFIGS.get(classification.domain, {})
        prefixes = domain_config.get("search_prefixes", [])

        if not prefixes:
            return query

        # Add relevant prefix if not already present
        query_lower = query.lower()
        for prefix in prefixes:
            if prefix.lower() not in query_lower:
                return f"{prefix} {query}"

        return query


def classify_domain(
    query: str,
    llm: BaseChatModel,
    config: Dict[str, Any] = None,
) -> DomainClassification:
    """
    Convenience function to classify a query's domain.

    Args:
        query: Research query
        llm: Language model to use
        config: Optional config

    Returns:
        DomainClassification result
    """
    classifier = DomainClassifier(llm, config)
    return classifier.classify(query)


def build_provider_profile(
    suggested_sources: Optional[List[str]],
    domain: ResearchDomain = ResearchDomain.GENERAL,
) -> List[str]:
    """
    Build a provider profile for multi-search from domain and source hints.

    Args:
        suggested_sources: Domain-specific source domains from classification.
        domain: Classified research domain.

    Returns:
        Ordered list of provider names to prioritize.
    """
    profile: List[str] = []

    def add_provider(name: Optional[str]) -> None:
        if not name:
            return
        name = str(name).strip().lower()
        if name and name not in profile:
            profile.append(name)

    for source in suggested_sources or []:
        source_text = str(source or "").strip().lower()
        if not source_text:
            continue
        for hint, provider in _SOURCE_PROVIDER_HINTS.items():
            if hint in source_text:
                add_provider(provider)

    for provider in _DOMAIN_PROVIDER_DEFAULTS.get(
        domain, _DOMAIN_PROVIDER_DEFAULTS[ResearchDomain.GENERAL]
    ):
        add_provider(provider)

    return profile
