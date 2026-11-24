import json
from base64 import b64encode

import httpx
import pytest
from langchain_core.messages import AIMessage

from workbench import project_workflows


def stub_model(monkeypatch, draft):
    captured = {}

    class Model:
        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            captured["request"] = json.loads(messages[-1].content)
            return AIMessage(content=json.dumps(draft))

    monkeypatch.setattr(project_workflows, "create_chat_model", lambda *args, **kwargs: Model())
    return captured


def stub_github(monkeypatch, handler):
    monkeypatch.setattr(
        project_workflows,
        "AsyncClient",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )


def requirements_draft(source="S1", quote="Monthly exports must include totals."):
    return {
        "title": "Monthly export requirements",
        "language": "en",
        "requirements": [
            {
                "text": "Include totals in monthly exports.",
                "acceptance": ["Generate a monthly export and verify a total is present."],
                "citations": [{"source": source, "quote": quote}],
            }
        ],
        "assumptions": ["Exports use UTC."],
        "open_questions": ["What format should totals use?"],
    }


async def run_workflow(flow, **kwargs):
    args = {
        "prompt": "Revise the draft for the finance team.",
        "model": "test-model",
        "context": {"name": "Forecast", "instructions": "", "decisions": "", "files": []},
        "repository": None,
        "release_tag": None,
        "prior": None,
        **kwargs,
    }
    return [event async for event in project_workflows.run_project_workflow(flow, **args)]


@pytest.mark.asyncio
async def test_requirements_revision_links_exact_file_passage(monkeypatch):
    model = stub_model(monkeypatch, requirements_draft())
    file_url = "/api/workspaces/project/files/notes"
    events = await run_workflow(
        "requirements-spec",
        context={
            "name": "Forecast",
            "instructions": "Keep it brief.",
            "decisions": "Approved for finance.",
            "files": [
                {
                    "id": "notes",
                    "name": "notes.md",
                    "url": file_url,
                    "text": "Forecast notes.\n\nMonthly exports must include totals.",
                }
            ],
        },
        prior={"id": "draft", "title": "Prior draft", "content": "Prior scope", "sources": []},
    )

    assert model["request"]["project"]["instructions"] == "Keep it brief."
    assert model["request"]["prior"]["content"] == "Prior scope"
    assert [kind for kind, _ in events] == ["status", "sources", "status", "deliverable"]
    assert events[1][1]["sources"][0]["url"] == file_url
    deliverable = events[-1][1]
    assert deliverable["title"] == "Monthly export requirements"
    assert deliverable["sources"] == [
        {
            "id": "S1",
            "title": "notes.md",
            "kind": "project_file",
            "url": file_url,
            "snippet": "Monthly exports must include totals.",
        }
    ]
    content = deliverable["content"]
    assert "Include totals in monthly exports. [S1]" in content
    assert "Generate a monthly export and verify a total is present." in content
    assert "## Assumptions\n\n- Exports use UTC." in content
    assert "## Open questions\n\n- What format should totals use?" in content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "quote"),
    [("S99", "Monthly exports must include totals."), ("S1", "Export hourly.")],
)
async def test_requirements_rejects_invented_citations(monkeypatch, source, quote):
    stub_model(monkeypatch, requirements_draft(source, quote))
    with pytest.raises(project_workflows.ProjectWorkflowError, match="source passage"):
        await run_workflow(
            "requirements-spec",
            context={
                "name": "Forecast",
                "instructions": "",
                "decisions": "",
                "files": [
                    {
                        "id": "notes",
                        "name": "notes.md",
                        "text": "Monthly exports must include totals.",
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_requirements_keeps_sections_when_scope_is_unconfirmed(monkeypatch):
    stub_model(
        monkeypatch,
        {
            "title": "Draft scope",
            "language": "en",
            "requirements": [],
            "assumptions": [],
            "open_questions": ["Who should be able to download the report?"],
        },
    )
    events = await run_workflow("requirements-spec")
    deliverable = events[-1][1]
    assert "## Confirmed requirements" in deliverable["content"]
    assert "## Acceptance criteria" in deliverable["content"]
    assert deliverable["sources"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("release_tag", [None, "ships/v2.1"])
async def test_release_reads_official_endpoints_at_the_resolved_tag(monkeypatch, release_tag):
    release_path = b"/repos/acme/planner/releases/" + (
        b"tags/ships%2Fv2.1" if release_tag else b"latest"
    )
    requested = []

    def github(request):
        requested.append(request.url)
        assert request.method == "GET"
        assert request.url.host == "api.github.com"
        assert "authorization" not in request.headers
        assert "Finance team" not in str(request.url)
        if request.url.raw_path == release_path:
            return httpx.Response(
                200,
                json={
                    "name": "February",
                    "tag_name": "ships/v2.1",
                    "published_at": "2025-02-01T00:00:00Z",
                    "prerelease": False,
                    "body": "Account export is available.",
                    "html_url": "https://untrusted.example/release",
                },
            )
        assert request.url.path == "/repos/acme/planner/readme"
        assert dict(request.url.params) == {"ref": "refs/tags/ships/v2.1"}
        return httpx.Response(
            200,
            json={
                "path": "README.md",
                "encoding": "base64",
                "content": b64encode(b"# Planner\nRun planner migrate.").decode(),
                "download_url": "https://untrusted.example/readme",
            },
        )

    stub_github(monkeypatch, github)
    stub_model(
        monkeypatch,
        {
            "title": "February release brief",
            "language": "en",
            "summary": {
                "text": "This release adds account exports.",
                "citations": [{"source": "S1", "quote": "Account export is available."}],
            },
            "highlights": [],
            "upgrade_notes": [
                {
                    "text": "Run planner migrate.",
                    "citations": [{"source": "S2", "quote": "Run planner migrate."}],
                }
            ],
            "open_questions": [],
        },
    )

    events = await run_workflow(
        "release-brief",
        repository="acme/planner",
        release_tag=release_tag,
        prompt="Finance team",
    )

    assert len(requested) == 2
    deliverable = events[-1][1]
    assert [source["url"] for source in deliverable["sources"]] == [
        "https://github.com/acme/planner/releases/tag/ships%2Fv2.1",
        "https://github.com/acme/planner/blob/refs/tags/ships/v2.1/README.md",
    ]
    assert "This release adds account exports. [S1]" in deliverable["content"]
    assert "Run planner migrate. [S2]" in deliverable["content"]


@pytest.mark.asyncio
async def test_release_rejects_repository_urls_before_requesting_github(monkeypatch):
    stub_github(monkeypatch, lambda _: pytest.fail("Invalid repository made a request."))
    with pytest.raises(project_workflows.ProjectWorkflowError, match="owner/repo"):
        await run_workflow("release-brief", repository="https://github.com/acme/planner")


@pytest.mark.asyncio
async def test_release_rejects_dot_segments_in_tag_before_requesting_github(monkeypatch):
    stub_github(monkeypatch, lambda _: pytest.fail("Invalid tag made a request."))
    with pytest.raises(project_workflows.ProjectWorkflowError, match="release tag"):
        await run_workflow("release-brief", repository="acme/planner", release_tag="v1/../v2")


@pytest.mark.asyncio
async def test_release_does_not_follow_github_redirects(monkeypatch):
    requested = []

    def github(request):
        requested.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://untrusted.example/"})

    stub_github(monkeypatch, github)
    with pytest.raises(project_workflows.ProjectWorkflowError, match="public repository"):
        await run_workflow("release-brief", repository="acme/planner")
    assert requested == ["api.github.com"]
