from agent.workflows.claim_verifier import ClaimStatus, ClaimVerifier


def test_claim_without_matching_evidence_is_unsupported():
    verifier = ClaimVerifier()
    report = "2024年该公司营收增长了20%，并在海外市场创下历史新高。"
    scraped_content = [
        {
            "query": "company update",
            "results": [
                {
                    "url": "https://example.com/product",
                    "summary": "The company launched a new product line for developers.",
                }
            ],
        }
    ]

    checks = verifier.verify_report(report, scraped_content)

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.UNSUPPORTED


def test_claim_with_conflicting_evidence_is_contradicted():
    verifier = ClaimVerifier()
    report = "The company's revenue increased in 2024 according to the annual report."
    scraped_content = [
        {
            "query": "revenue trend",
            "results": [
                {
                    "url": "https://example.com/earnings",
                    "summary": "The company's revenue did not increase in 2024 and decreased by 5%.",
                }
            ],
        }
    ]

    checks = verifier.verify_report(report, scraped_content)

    assert len(checks) == 1
    assert checks[0].status == ClaimStatus.CONTRADICTED
    assert checks[0].evidence_urls == ["https://example.com/earnings"]
