from agent.workflows.evidence_passages import split_into_passages


def test_split_into_passages_includes_heading_for_markdown():
    md = "# Intro\n\nAlpha.\n\n## Details\n\nBeta.\n\nGamma.\n"
    passages = split_into_passages(md, max_chars=40)
    assert passages

    alpha = next(p for p in passages if "Alpha" in p["text"])
    assert alpha.get("heading") == "Intro"

    beta = next(p for p in passages if "Beta" in p["text"])
    assert beta.get("heading") == "Details"

