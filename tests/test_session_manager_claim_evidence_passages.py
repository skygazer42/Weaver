from common.session_manager import SessionManager


def test_session_manager_enriches_claims_with_passage_level_evidence():
    manager = SessionManager(checkpointer=object())

    state = {
        "final_report": "The company's revenue increased in 2024 according to the annual report.",
        "scraped_content": [],
        "deepsearch_artifacts": {
            "passages": [
                {
                    "url": "https://example.com/earnings?utm_source=test",
                    "text": "In 2024, the company's revenue increased by 5% year over year.",
                    "snippet_hash": "passage_123",
                    "quote": "In 2024, the company's revenue increased by 5% year over year.",
                    "heading_path": ["Results"],
                }
            ]
        },
    }

    artifacts = manager._extract_deepsearch_artifacts(state)
    claims = artifacts.get("claims")
    assert isinstance(claims, list)
    assert claims, "expected ClaimVerifier to produce at least one claim"
    claim = (claims or [None])[0] or {}
    assert isinstance(claim.get("evidence_urls"), list)
    assert isinstance(claim.get("evidence_passages"), list)
    assert claim.get("evidence_passages"), "expected evidence_passages to be attached"

    passage = (claim.get("evidence_passages") or [None])[0] or {}
    assert passage.get("snippet_hash") == "passage_123"
    assert passage.get("heading_path") == ["Results"]
    assert "utm_source" not in str(passage.get("url") or "")
