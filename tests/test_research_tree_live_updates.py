from types import SimpleNamespace

from agent.workflows.research_tree import TreeExplorer


class _FakeLLM:
    def invoke(self, msg, config=None):
        text = str(msg)
        if "subtopics" in text:
            return SimpleNamespace(
                content='{"subtopics": [{"topic": "Architecture & Protocols", "relevance": 0.92}, {"topic": "Enterprise Adoption", "relevance": 0.87}]}'
            )
        if "总结以下搜索结果" in text:
            return SimpleNamespace(content="- Key finding summary from branch sources.")
        return SimpleNamespace(content='["extra query 1"]')


def test_tree_explorer_emits_live_incremental_updates_with_summary_and_sources():
    snapshots = []

    def _fake_search(payload, config=None):
        q = payload.get("query", "")
        slug = str(abs(hash(q)) % 10000)
        return [
            {
                "title": f"Article for {q[:20]}",
                "url": f"https://example.com/{slug}",
                "snippet": "Detailed analysis snippet.",
            }
        ]

    explorer = TreeExplorer(
        planner_llm=_FakeLLM(),
        researcher_llm=_FakeLLM(),
        writer_llm=_FakeLLM(),
        search_func=_fake_search,
        config={},
        max_depth=1,
        max_branches=2,
        queries_per_branch=2,
        on_tree_update=snapshots.append,
    )

    tree = explorer.run("AI Agents 2026", state={}, decompose_root=True)

    assert tree.root_id is not None
    # Expect root created, root in_progress, root completed, children added, and each child in_progress + completed
    assert len(snapshots) >= 6
    assert snapshots[0]["total_nodes"] == 1
    assert snapshots[-1]["total_nodes"] == 3
    assert snapshots[-1]["completed_nodes"] == 3

    root_dict = snapshots[-1]["nodes"][tree.root_id]
    assert root_dict["summary_preview"] == "- Key finding summary from branch sources."
    assert len(root_dict["sources"]) >= 1
    assert root_dict["sources"][0].startswith("https://example.com/")
