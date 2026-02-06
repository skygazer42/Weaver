"""
Research Quality Assessor.

Enhanced evaluation of research report quality.
Provides detailed analysis of claims, contradictions, and source diversity.

Key Features:
1. Claim verification against sources
2. Contradiction detection within report
3. Source diversity scoring
4. Citation accuracy checking
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


@dataclass
class ClaimVerification:
    """Verification result for a single claim."""
    claim: str
    supported: bool
    supporting_sources: List[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""


@dataclass
class QualityReport:
    """Comprehensive quality assessment report."""
    claim_support_score: float = 0.0
    source_diversity_score: float = 0.0
    contradiction_free_score: float = 1.0
    citation_accuracy_score: float = 0.0
    citation_coverage_score: float = 1.0

    verified_claims: List[ClaimVerification] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    unique_domains: List[str] = field(default_factory=list)
    missing_citations: List[str] = field(default_factory=list)

    overall_score: float = 0.0
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_support_score": self.claim_support_score,
            "source_diversity_score": self.source_diversity_score,
            "contradiction_free_score": self.contradiction_free_score,
            "citation_accuracy_score": self.citation_accuracy_score,
            "citation_coverage_score": self.citation_coverage_score,
            "overall_score": self.overall_score,
            "verified_claims_count": len(self.verified_claims),
            "supported_claims": sum(1 for c in self.verified_claims if c.supported),
            "contradictions": self.contradictions,
            "unique_domains": self.unique_domains,
            "missing_citations": self.missing_citations[:5],
            "recommendations": self.recommendations,
        }


CLAIM_EXTRACTION_PROMPT = """
# 任务
从以下研究报告中提取所有事实性声明（claims）。

# 报告
{report}

# 要求
1. 提取所有可验证的事实性陈述
2. 忽略观点和推测
3. 每行一个声明

# 输出
每行一个事实性声明，不要序号。
"""

CLAIM_VERIFICATION_PROMPT = """
# 任务
验证以下声明是否被来源内容支持。

# 声明
{claim}

# 可用来源内容
{sources}

# 输出格式
supported: true/false
confidence: 0.0-1.0
sources: 来源URL列表（逗号分隔）
notes: 简短说明
"""

CONTRADICTION_CHECK_PROMPT = """
# 任务
检查以下研究报告中是否存在矛盾或不一致的陈述。

# 报告
{report}

# 输出
如果发现矛盾，每行描述一个矛盾。
如果没有矛盾，输出"无矛盾"。
"""


class QualityAssessor:
    """
    Assesses research report quality across multiple dimensions.

    Evaluates:
    - Claim support: Are facts backed by sources?
    - Contradictions: Are there internal inconsistencies?
    - Source diversity: Are sources from varied domains?
    - Citation accuracy: Are citations properly formatted?
    """

    def __init__(self, llm: BaseChatModel, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}

    def assess(
        self,
        report: str,
        scraped_content: List[Dict[str, Any]],
        sources: List[str] = None,
    ) -> QualityReport:
        """
        Perform comprehensive quality assessment.

        Args:
            report: The research report text
            scraped_content: List of search results with content
            sources: List of source URLs

        Returns:
            QualityReport with detailed assessment
        """
        quality = QualityReport()

        # 1. Check source diversity
        all_urls = self._extract_urls(scraped_content, sources)
        quality.unique_domains = self._get_unique_domains(all_urls)
        quality.source_diversity_score = self._calculate_diversity_score(quality.unique_domains)

        # 2. Check claims
        quality.verified_claims = self.check_claims(report, scraped_content)
        if quality.verified_claims:
            supported = sum(1 for c in quality.verified_claims if c.supported)
            quality.claim_support_score = supported / len(quality.verified_claims)

        # 3. Check contradictions
        quality.contradictions = self.check_contradictions(report)
        quality.contradiction_free_score = 1.0 if not quality.contradictions else max(0, 1 - len(quality.contradictions) * 0.2)

        # 4. Check citation accuracy
        quality.missing_citations, quality.citation_accuracy_score = self.check_citation_accuracy(report, all_urls)
        coverage_missing, quality.citation_coverage_score = self.check_citation_coverage(report)
        if coverage_missing:
            merged_missing = quality.missing_citations + coverage_missing
            # Keep first occurrence order stable while deduping.
            quality.missing_citations = list(dict.fromkeys(merged_missing))

        # Calculate overall score
        citation_quality = (
            quality.citation_accuracy_score + quality.citation_coverage_score
        ) / 2.0
        quality.overall_score = (
            quality.claim_support_score * 0.35 +
            quality.source_diversity_score * 0.2 +
            quality.contradiction_free_score * 0.25 +
            citation_quality * 0.2
        )

        # Generate recommendations
        quality.recommendations = self._generate_recommendations(quality)

        logger.info(
            f"[QualityAssessor] Overall: {quality.overall_score:.2f}, "
            f"Claims: {quality.claim_support_score:.2f}, "
            f"Diversity: {quality.source_diversity_score:.2f}"
        )

        return quality

    def check_claims(
        self,
        report: str,
        scraped_content: List[Dict[str, Any]],
        max_claims: int = 10,
    ) -> List[ClaimVerification]:
        """
        Extract and verify claims from the report.

        Args:
            report: Report text
            scraped_content: Source content for verification
            max_claims: Maximum claims to verify

        Returns:
            List of ClaimVerification results
        """
        # Extract claims
        extract_prompt = ChatPromptTemplate.from_messages([
            ("user", CLAIM_EXTRACTION_PROMPT)
        ])
        msg = extract_prompt.format_messages(report=report[:8000])
        response = self.llm.invoke(msg, config=self.config)
        claims_text = getattr(response, "content", "") or ""

        claims = [c.strip() for c in claims_text.split("\n") if c.strip() and len(c) > 20]
        claims = claims[:max_claims]

        if not claims:
            return []

        # Build sources context
        sources_context = self._build_sources_context(scraped_content)

        # Verify each claim
        verifications = []
        for claim in claims:
            verification = self._verify_claim(claim, sources_context)
            verifications.append(verification)

        return verifications

    def _verify_claim(self, claim: str, sources_context: str) -> ClaimVerification:
        """Verify a single claim against sources."""
        verify_prompt = ChatPromptTemplate.from_messages([
            ("user", CLAIM_VERIFICATION_PROMPT)
        ])
        msg = verify_prompt.format_messages(
            claim=claim,
            sources=sources_context[:6000],
        )

        try:
            response = self.llm.invoke(msg, config=self.config)
            content = getattr(response, "content", "") or ""

            supported = "true" in content.lower().split("supported:")[1].split("\n")[0] if "supported:" in content.lower() else False
            confidence = 0.0
            sources = []
            notes = ""

            for line in content.split("\n"):
                line_lower = line.lower().strip()
                if line_lower.startswith("confidence:"):
                    try:
                        confidence = float(re.search(r"[\d.]+", line).group())
                    except:
                        pass
                elif line_lower.startswith("sources:"):
                    sources = [s.strip() for s in line.split(":", 1)[1].split(",") if s.strip()]
                elif line_lower.startswith("notes:"):
                    notes = line.split(":", 1)[1].strip()

            return ClaimVerification(
                claim=claim,
                supported=supported,
                supporting_sources=sources,
                confidence=confidence,
                notes=notes,
            )

        except Exception as e:
            logger.error(f"Claim verification error: {e}")
            return ClaimVerification(claim=claim, supported=False, notes=str(e))

    def check_contradictions(self, report: str) -> List[str]:
        """
        Check for contradictions within the report.

        Args:
            report: Report text

        Returns:
            List of contradiction descriptions
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", CONTRADICTION_CHECK_PROMPT)
        ])
        msg = prompt.format_messages(report=report[:8000])

        try:
            response = self.llm.invoke(msg, config=self.config)
            content = getattr(response, "content", "") or ""

            if "无矛盾" in content or "no contradiction" in content.lower():
                return []

            contradictions = [c.strip() for c in content.split("\n") if c.strip() and len(c) > 10]
            return contradictions[:5]

        except Exception as e:
            logger.error(f"Contradiction check error: {e}")
            return []

    def check_citation_accuracy(
        self,
        report: str,
        known_urls: List[str],
    ) -> Tuple[List[str], float]:
        """
        Check citation formatting and accuracy.

        Args:
            report: Report text
            known_urls: List of valid source URLs

        Returns:
            Tuple of (missing_citations, accuracy_score)
        """
        # Find all citation patterns in report
        citation_patterns = [
            r"\[(\d+)\]",  # [1] style
            r"\[\s*来源[：:]\s*([^\]]+)\]",  # [来源: xxx] style
            r"(?:参考|来源|引用)[：:]?\s*(https?://\S+)",  # URL references
        ]

        found_citations = set()
        for pattern in citation_patterns:
            matches = re.findall(pattern, report)
            found_citations.update(matches)

        # Check for statements that look like they need citations
        # Sentences with numbers, dates, or definitive statements
        needs_citation_patterns = [
            r"据[^，。]+(?:统计|显示|报道)",
            r"\d{4}年[^，。]*(?:达到|增长|下降)",
            r"研究(?:表明|显示|发现)",
            r"(?:约|超过|达到)\s*[\d.]+\s*[%万亿]",
        ]

        potential_uncited = []
        for pattern in needs_citation_patterns:
            matches = re.findall(pattern, report)
            for m in matches:
                # Check if this sentence area has a citation nearby
                idx = report.find(m)
                context = report[max(0, idx-20):idx+len(m)+50]
                if not re.search(r"\[\d+\]|\[来源", context):
                    potential_uncited.append(m)

        # Calculate score
        if not found_citations and not potential_uncited:
            return [], 0.8  # No citations but also no obvious needs

        if potential_uncited and not found_citations:
            return potential_uncited[:5], 0.3

        if found_citations:
            ratio = len(found_citations) / (len(found_citations) + len(potential_uncited))
            return potential_uncited[:5], min(1.0, ratio)

        return [], 0.5

    def check_citation_coverage(self, report: str) -> Tuple[List[str], float]:
        """
        Estimate citation coverage over claim-like sentences.

        Returns:
            Tuple of (uncited_claims, coverage_ratio)
        """
        if not report:
            return [], 1.0

        claim_like_sentences: List[str] = []
        sentence_candidates = re.split(r"(?<=[。！？.!?])\s+", report)
        claim_markers = [
            r"\d{4}",
            r"\d+%",
            r"\d+\.\d+",
            r"(?:research|study|report|data|according to|shows|found)",
            r"(?:研究|数据显示|统计|报告|发现|增长|下降)",
        ]

        for sentence in sentence_candidates:
            text = sentence.strip()
            if len(text) < 15:
                continue
            if any(re.search(marker, text, flags=re.IGNORECASE) for marker in claim_markers):
                claim_like_sentences.append(text)

        if not claim_like_sentences:
            return [], 1.0

        citation_pattern = re.compile(r"\[(?:S\d+-\d+|\d+)\]|\[来源[：:].*?\]|https?://\S+", re.IGNORECASE)
        uncited_claims = [s for s in claim_like_sentences if not citation_pattern.search(s)]
        coverage = 1.0 - (len(uncited_claims) / max(1, len(claim_like_sentences)))
        return uncited_claims[:5], max(0.0, min(1.0, coverage))

    def check_source_diversity(self, sources: List[str]) -> Tuple[List[str], float]:
        """
        Check diversity of source domains.

        Args:
            sources: List of source URLs

        Returns:
            Tuple of (unique_domains, diversity_score)
        """
        unique_domains = self._get_unique_domains(sources)
        score = self._calculate_diversity_score(unique_domains)
        return unique_domains, score

    def _extract_urls(
        self,
        scraped_content: List[Dict[str, Any]],
        sources: List[str] = None,
    ) -> List[str]:
        """Extract all URLs from scraped content and sources list."""
        urls = list(sources) if sources else []

        for item in scraped_content:
            for r in item.get("results", []):
                url = r.get("url")
                if url and url not in urls:
                    urls.append(url)

        return urls

    def _get_unique_domains(self, urls: List[str]) -> List[str]:
        """Extract unique domains from URLs."""
        domains = set()
        for url in urls:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                # Remove www prefix
                if domain.startswith("www."):
                    domain = domain[4:]
                if domain:
                    domains.add(domain)
            except:
                pass
        return sorted(domains)

    def _calculate_diversity_score(self, domains: List[str]) -> float:
        """
        Calculate source diversity score.

        Higher score for more unique domains, penalize if too few sources.
        """
        if not domains:
            return 0.0

        # Base score from domain count
        count = len(domains)
        if count >= 10:
            base_score = 1.0
        elif count >= 5:
            base_score = 0.8
        elif count >= 3:
            base_score = 0.6
        else:
            base_score = 0.4

        # Bonus for having authoritative domains
        authoritative = {"wikipedia.org", "gov", "edu", "arxiv.org", "nature.com", "sciencedirect.com"}
        auth_count = sum(1 for d in domains if any(a in d for a in authoritative))
        auth_bonus = min(0.2, auth_count * 0.05)

        return min(1.0, base_score + auth_bonus)

    def _build_sources_context(self, scraped_content: List[Dict[str, Any]]) -> str:
        """Build sources context string for claim verification."""
        parts = []
        for item in scraped_content:
            for r in item.get("results", []):
                url = r.get("url", "unknown")
                text = r.get("raw_excerpt") or r.get("summary") or r.get("snippet") or ""
                if text:
                    parts.append(f"[Source: {url}]\n{text[:1000]}")

        return "\n\n---\n\n".join(parts[:15])

    def _generate_recommendations(self, quality: QualityReport) -> List[str]:
        """Generate improvement recommendations based on quality scores."""
        recommendations = []

        if quality.claim_support_score < 0.6:
            recommendations.append("增加更多来源支持的事实陈述，确保每个关键论点都有引用")

        if quality.source_diversity_score < 0.5:
            recommendations.append("扩展信息来源范围，使用更多不同领域的权威来源")

        if quality.contradiction_free_score < 0.8:
            recommendations.append(f"解决报告中发现的矛盾: {', '.join(quality.contradictions[:2])}")

        if quality.citation_accuracy_score < 0.6:
            recommendations.append("改进引用格式，确保关键数据和事实都有明确来源标注")
        if quality.citation_coverage_score < 0.6:
            recommendations.append("提高引用覆盖率：为每个关键数据或结论补充明确引用标签")

        if not recommendations:
            recommendations.append("报告质量良好，可以进一步丰富细节和案例")

        return recommendations
