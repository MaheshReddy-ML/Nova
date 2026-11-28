import time

import httpx
import pytest
from docx import Document

from nova import provenance
from nova.domain import NovaError
from nova.store import Store
from nova.toolkit import FollowUps, document_path, list_documents, save_document, search_papers

S2 = {"data": [{"title": "Holistic Evaluation of Language Models", "year": 2022, "citationCount": 1500,
                "authors": [{"name": "Percy Liang"}], "venue": "TMLR", "abstract": "We present HELM.",
                "url": "https://www.semanticscholar.org/paper/x", "externalIds": {"ArXiv": "2211.09110"}}]}
ARXIV = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2307.03109v2</id><published>2023-07-06T00:00:00Z</published>
<title>A Survey on Evaluation of
 Large Language Models</title><summary>  We survey evaluation. </summary><author><name>Yupeng Chang</name></author></entry>
<entry><id>http://arxiv.org/abs/1901.00001v1</id><published>2019-01-01T00:00:00Z</published>
<title>Old paper</title><summary>Old.</summary></entry></feed>"""


async def test_papers_prefer_semantic_scholar_and_record_provenance(tmp_path):
    store = Store(tmp_path / "s.db")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=S2)))
    token, fetches = provenance.begin()
    try:
        result = await search_papers(client, store, "LLM evaluation benchmarks")
    finally:
        provenance.end(token)
        await client.aclose()
    assert result["provider"] == "Semantic Scholar"
    assert result["papers"][0]["url"] == "https://arxiv.org/abs/2211.09110" and result["papers"][0]["citations"] == 1500
    assert fetches and fetches[0]["provider"] == "Semantic Scholar"


async def test_papers_fall_back_to_arxiv_with_year_filter(tmp_path):
    def handler(request):
        if "semanticscholar" in request.url.host:
            return httpx.Response(429)
        assert "all:LLM" in request.url.params["search_query"]
        return httpx.Response(200, content=ARXIV)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await search_papers(client, Store(tmp_path / "s.db"), "LLM evaluation", since_year=2020)
    finally:
        await client.aclose()
    assert result["provider"] == "arXiv" and len(result["papers"]) == 1
    paper = result["papers"][0]
    assert paper["title"] == "A Survey on Evaluation of Large Language Models"
    assert paper["url"] == "https://arxiv.org/abs/2307.03109" and paper["year"] == 2023


def test_documents_markdown_and_word(tmp_path):
    body = "## Themes\n\n- **Benchmarks** drift over time\n1. Read [HELM](https://crfm.stanford.edu)\n\nClosing paragraph."
    saved = save_document(tmp_path, "LLM evaluation review", body)
    text = (tmp_path / "documents" / saved["file"]).read_text()
    assert text.startswith("# LLM evaluation review") and saved["url"] == f"/documents/{saved['file']}"
    word = save_document(tmp_path, "Grant proposal: draft", body, "docx")
    doc = Document(tmp_path / "documents" / word["file"])
    assert [p.style.name for p in doc.paragraphs][:4] == ["Title", "Heading 1", "List Bullet", "List Number"]
    assert doc.paragraphs[2].runs[0].bold and "HELM (https://crfm.stanford.edu)" in doc.paragraphs[3].text
    assert {item["file"] for item in list_documents(tmp_path)} == {saved["file"], word["file"]}
    for bad in ("../.env", "x.py", saved["file"] + "x"):
        with pytest.raises(NovaError):
            document_path(tmp_path, bad)
    with pytest.raises(NovaError):
        save_document(tmp_path, "Hi", "too short")


def test_follow_ups_reach_briefing(tmp_path):
    from types import SimpleNamespace

    from nova.briefing import collect

    store = Store(tmp_path / "f.db")
    follow_ups = FollowUps(store)
    said = follow_ups.schedule("Brew Lab Café", days=3, note="Ask about the concept")
    assert "Brew Lab Café" in said["say"] and follow_ups.due() == []
    assert [row["business"] for row in follow_ups.due(time.time() + 4 * 86400)] == ["Brew Lab Café"]
    with pytest.raises(NovaError):
        follow_ups.schedule("Somebody", days=400)
    follow_ups.complete("brew lab")
    assert follow_ups.upcoming() == []
    # Due follow-ups are part of the spoken briefing data.
    key = follow_ups.schedule("Clay Studio", days=1)["follow_up_id"]
    store.db.execute("UPDATE follow_ups SET due=? WHERE id=?", (time.time() - 60, key))
    runtime = SimpleNamespace(store=store, follow_ups=follow_ups,
                              outbox=SimpleNamespace(list=lambda limit: []),
                              business=SimpleNamespace(ledger=lambda: {"outstanding_paise": 0}),
                              schedules=SimpleNamespace(list=lambda: []))
    store.db.execute("CREATE TABLE IF NOT EXISTS approvals(state TEXT)")
    store.db.execute("CREATE TABLE IF NOT EXISTS leads(url TEXT, score REAL, task_id TEXT)")
    assert [row["business"] for row in collect(runtime, 0)["follow_ups"]] == ["Clay Studio"]


def test_cached_fetches_do_not_break_answer_verification():
    result = provenance.verify_answer("See arxiv.org", ["https://arxiv.org/abs/1"],
                                      [{"url": "search:x", "status": "cache"}, {"url": "https://arxiv.org/abs/1", "status": 200},
                                       {"url": "https://a.org", "status": None}])
    assert result["ok_fetches"] == 2 and result["unverified_sites"] == []


def test_fit_context_trims_old_tool_results_instead_of_failing():
    from nova.agent import context_estimate, fit_context

    messages = [{"role": "system", "content": "rules " * 200}, {"role": "user", "content": "redesign regalmuse.in"},
                *({"role": "tool", "tool_call_id": str(i), "name": "load_skill", "content": "x" * 6000} for i in range(3)),
                {"role": "tool", "tool_call_id": "last", "name": "read_website", "content": "y" * 3000}]
    assert context_estimate(messages, []) > 4000
    assert fit_context(messages, [], 4000) and context_estimate(messages, []) <= 4000
    assert messages[0]["content"] == "rules " * 200 and messages[-1]["content"] == "y" * 3000
    assert not fit_context([{"role": "system", "content": "z" * 30000}, {"role": "user", "content": "hi"}], [], 1000)
