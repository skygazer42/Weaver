"""
Claim verifier that matches report claims against collected evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Set, Tuple

_CLAIM_MARKERS = (
    "research",
    "study",
    "report",
    "data",
    "according to",
    "shows",
    "found",
    "研究",
    "报告",
    "数据显示",
    "统计",
    "增长",
    "下降",
)

_NEGATION_MARKERS = (
    "not",
    "no",
    "never",
    "without",
    "didn't",
    "doesn't",
    "isn't",
    "wasn't",
    "不是",
    "并非",
    "没有",
    "未",
    "无",
)

_UP_MARKERS = ("increase", "increased", "grow", "growth", "up", "rise", "rose", "增长", "上升")
_DOWN_MARKERS = ("decrease", "decreased", "decline", "down", "fell", "drop", "下降", "减少")

_STOPWORDS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "into",
    "were",
    "was",
    "are",
    "for",
    "has",
    "have",
    "had",
    "will",
    "about",
    "在",
    "是",
    "了",
    "和",
    "与",
    "对",
    "将",
    "及",
}


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"


@dataclass
class ClaimCheck:
    claim: str
    status: ClaimStatus
    evidence_urls: List[str] = field(default_factory=list)
    score: float = 0.0
    notes: str = ""


class ClaimVerifier:
    """Deterministic claim-to-evidence matcher."""

    def __init__(self, min_overlap_tokens: int = 2):
        self.min_overlap_tokens = max(1, int(min_overlap_tokens))

    def extract_claims(self, report: str, max_claims: int = 10) -> List[str]:
        if not report:
            return []

        candidates = re.split(r"(?<=[。！？.!?])\s+|\n+", report)
        claims: List[str] = []
        seen: Set[str] = set()

        for sentence in candidates:
            text = sentence.strip()
            if len(text) < 20:
                continue
            lower = text.lower()
            has_signal = any(marker in lower for marker in _CLAIM_MARKERS) or bool(
                re.search(r"\d{2,4}|\d+%|\d+\.\d+", text)
            )
            if not has_signal:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            claims.append(text)
            if len(claims) >= max_claims:
                break

        return claims

    def verify_report(
        self,
        report: str,
        scraped_content: List[Dict[str, Any]],
        max_claims: int = 10,
    ) -> List[ClaimCheck]:
        claims = self.extract_claims(report, max_claims=max_claims)
        if not claims:
            return []
        evidence = self._extract_evidence(scraped_content)
        return [self.verify_claim(claim, evidence) for claim in claims]

    def verify_claim(self, claim: str, evidence: List[Tuple[str, str]]) -> ClaimCheck:
        claim_tokens = self._tokenize(claim)
        if not claim_tokens:
            return ClaimCheck(claim=claim, status=ClaimStatus.UNSUPPORTED)

        supported_urls: List[str] = []
        contradicted_urls: List[str] = []
        best_overlap = 0

        for url, text in evidence:
            evidence_tokens = self._tokenize(text)
            overlap = len(claim_tokens & evidence_tokens)
            if overlap < self.min_overlap_tokens:
                continue

            best_overlap = max(best_overlap, overlap)
            if self._is_contradiction(claim, text):
                contradicted_urls.append(url)
            else:
                supported_urls.append(url)

        if contradicted_urls:
            urls = list(dict.fromkeys(contradicted_urls + supported_urls))
            return ClaimCheck(
                claim=claim,
                status=ClaimStatus.CONTRADICTED,
                evidence_urls=urls[:5],
                score=float(best_overlap),
                notes="conflicting evidence found",
            )

        if supported_urls:
            return ClaimCheck(
                claim=claim,
                status=ClaimStatus.VERIFIED,
                evidence_urls=list(dict.fromkeys(supported_urls))[:5],
                score=float(best_overlap),
                notes="supported by evidence",
            )

        return ClaimCheck(
            claim=claim,
            status=ClaimStatus.UNSUPPORTED,
            evidence_urls=[],
            score=0.0,
            notes="no matching evidence",
        )

    def _extract_evidence(self, scraped_content: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
        evidence: List[Tuple[str, str]] = []
        for item in scraped_content or []:
            for result in item.get("results", []) or []:
                url = str(result.get("url") or "").strip() or "unknown"
                text = (
                    result.get("raw_excerpt")
                    or result.get("content")
                    or result.get("summary")
                    or result.get("snippet")
                    or ""
                )
                text = str(text).strip()
                if text:
                    evidence.append((url, text))
        return evidence

    def _tokenize(self, text: str) -> Set[str]:
        tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", (text or "").lower())
        return {t for t in tokens if len(t) > 1 and t not in _STOPWORDS}

    def _has_negation(self, text: str) -> bool:
        lower = (text or "").lower()
        return any(marker in lower for marker in _NEGATION_MARKERS)

    def _trend_direction(self, text: str) -> int:
        lower = (text or "").lower()
        up = any(marker in lower for marker in _UP_MARKERS)
        down = any(marker in lower for marker in _DOWN_MARKERS)
        if up and not down:
            return 1
        if down and not up:
            return -1
        return 0

    def _is_contradiction(self, claim: str, evidence: str) -> bool:
        claim_neg = self._has_negation(claim)
        evidence_neg = self._has_negation(evidence)
        if claim_neg != evidence_neg:
            return True

        claim_dir = self._trend_direction(claim)
        evidence_dir = self._trend_direction(evidence)
        if claim_dir != 0 and evidence_dir != 0 and claim_dir != evidence_dir:
            return True

        return False
