"""Route-level tests for recall v3 (setup, capability, pull, index events, delta,
document search, document and image reads, settings secrets, Ask over documents).

Route coroutines are awaited directly (httpx's TestClient is not installed).
Everything lives under tmp_path: a fake home, two fake projects and a fake
embedder. No real home directory, network or Ollama is touched.
"""
import asyncio
import base64
import hashlib
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
import recall  # noqa: E402
import recall_embed as re_  # noqa: E402
import recall_index as ri  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _vec(text, dims=64):
    v = [0.0] * dims
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dims] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


class FakeEmbedder:
    supports_images = True
    identity = {"provider": "ollama", "model": "fake-embed", "endpoint_host": "127.0.0.1:11434",
                "dims": 64, "format": "ollama"}

    def __init__(self):
        self.text_calls = []   # batch sizes
        self.image_calls = 0

    def embed_texts(self, texts, kind="document", titles=None):
        self.text_calls.append(len(texts))
        return [_vec(t) for t in texts]

    def embed_images(self, images):
        self.image_calls += len(images)
        return [_vec(hashlib.md5(b).hexdigest()) for b in images]

    def lock_evidence(self):
        return {"ollama_digest": "sha256:fake", "returned_model": None}


def dt(day):
    return datetime(2026, 11, day, tzinfo=timezone.utc)


class FakeRequest:
    def __init__(self, after=None):
        self.after, self.calls = after, 0

    async def is_disconnected(self):
        self.calls += 1
        return self.after is not None and self.calls > self.after


def run(coro):
    return asyncio.run(coro)


async def _collect(resp):
    return [json.loads(raw) async for raw in resp.body_iterator]


def stream(resp):
    return asyncio.run(_collect(resp))


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "work" / "app"
    other = tmp_path / "work" / "other"
    for d in (home, proj / "docs", other):
        d.mkdir(parents=True)
    (proj / "README.md").write_text("The planner uses a classifier to route requests.\n")
    (proj / "docs" / "design.md").write_text("Thumbnail renderer design notes about large images.\n")
    (other / "README.md").write_text("Other project secret-free notes about billing.\n")
    skill = home / ".claude" / "skills" / "bug-audit"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: bug-audit\n---\nAudit the planner for serious bugs.\n")
    img_dir = home / ".codex" / "generated_images" / "c1"
    img_dir.mkdir(parents=True)
    (img_dir / "pic.png").write_bytes(PNG)
    for var in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)

    sessions = [
        {"agent": "codex", "id": "c1", "project": str(proj), "timestamp": dt(3), "display": "wire planner",
         "model": "m", "tokens": {"total": 5}, "cost": 1.0, "skills_used": ["bug-audit"]},
        {"agent": "claude", "id": "a1", "project": str(proj), "timestamp": dt(2), "display": "thumbnails",
         "model": "m", "tokens": {"total": 5}, "cost": 1.0},
        {"agent": "codex", "id": "o1", "project": str(other), "timestamp": dt(1), "display": "billing",
         "model": "m", "tokens": {"total": 5}, "cost": 1.0},
    ]
    table = {
        ("codex", "c1"): [{"idx": 0, "turn": 1, "kind": "assistant", "text": "we wired the planner classifier with langgraph routing"}],
        ("claude", "a1"): [{"idx": 0, "turn": 1, "kind": "assistant", "text": "thumbnail renderer crashed on large images"}],
        ("codex", "o1"): [{"idx": 0, "turn": 1, "kind": "assistant", "text": "billing export finished"}],
    }

    monkeypatch.setattr(recall, "repo_resolver", None)
    monkeypatch.setattr(ri, "settings_path", lambda: tmp_path / "recall.json")
    monkeypatch.setattr(ri, "index_path", lambda: tmp_path / "recall_index.db")
    monkeypatch.setattr(ri, "secrets_path", lambda: tmp_path / "recall_secrets.json")
    monkeypatch.setattr(main, "_recall_store", None)
    monkeypatch.setattr(main, "_recall_job", None)
    monkeypatch.setattr(main, "_recall_disc_cache", {})
    monkeypatch.setattr(main, "_recall_guards", {})
    monkeypatch.setattr(main, "_recall_home", lambda: home)

    async def fake_sessions():
        return sessions

    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    monkeypatch.setattr(main, "_recall_load_chunks",
                        lambda agent, sid: (table[(agent, sid)], "live") if (agent, sid) in table else None)
    emb = FakeEmbedder()
    monkeypatch.setattr(main, "_recall_embedder", lambda sem: emb)
    monkeypatch.setattr(main, "_recall_probe",
                        lambda sem: {"reachable": True, "version": "0.0.0", "model_installed": True, "error": None})

    class W:
        pass

    w = W()
    w.tmp, w.home, w.proj, w.other, w.emb, w.sessions = tmp_path, home, proj, other, emb, sessions
    w.pkey = str(proj)
    return w


def enable(**extra):
    run(main.recall_put_settings({"semantic": {"enabled": True, **extra}}))


def index(project, full=False):
    st = run(main.recall_index_start({"project": project, "full": full}))
    main._recall_job.wait(15)
    return st


def events(since=None):
    return stream(run(main.recall_index_events(FakeRequest(), since)))


# ------------------------------------------------------------ setup and capability

def test_setup_reports_provider_and_capability_without_speed_test(world, monkeypatch):
    monkeypatch.setattr(main._recall_embed, "version", lambda url: "0.9.9")
    monkeypatch.setattr(main._recall_embed, "model_installed", lambda url, model: False)
    monkeypatch.setattr(main._recall_capability, "memory", lambda: {"total": 16 * 2**30, "available": 8 * 2**30})
    monkeypatch.setattr(main._recall_capability, "disk_free", lambda p: 100 * 2**30)
    out = run(main.recall_setup(project="app"))
    assert out["provider"] == "ollama" and out["enabled"] is False
    assert out["ollama"]["reachable"] is True and out["ollama"]["model_installed"] is False
    assert out["api"]["api_key_set"] is False
    cap = out["capability"]
    assert cap["provider"] == "ollama" and cap["ollama"]["version"] == "0.9.9"
    assert cap["estimate"] is None
    assert world.emb.text_calls == []  # setup never runs the speed test


def test_capability_speed_test_uses_up_to_32_real_chunks_when_model_installed(world, monkeypatch):
    monkeypatch.setattr(main._recall_embed, "version", lambda url: "0.9.9")
    monkeypatch.setattr(main._recall_embed, "model_installed", lambda url, model: True)
    monkeypatch.setattr(main._recall_capability, "memory", lambda: {"total": 16 * 2**30, "available": 8 * 2**30})
    monkeypatch.setattr(main._recall_capability, "disk_free", lambda p: 100 * 2**30)
    cap = run(main.recall_capability(project="app"))
    assert cap["estimate"] is None and world.emb.text_calls == []
    cap = run(main.recall_capability(project="app", sample_project=True))
    assert cap["status"] == "ready"
    assert cap["estimate"] is not None and cap["estimate"]["chunks"] > 0
    assert len(world.emb.text_calls) == 1 and 1 <= world.emb.text_calls[0] <= 32


def test_capability_no_speed_test_when_model_missing_or_ollama_down(world, monkeypatch):
    monkeypatch.setattr(main._recall_embed, "version", lambda url: "0.9.9")
    monkeypatch.setattr(main._recall_embed, "model_installed", lambda url, model: False)
    cap = run(main.recall_capability(project="app"))
    assert world.emb.text_calls == [] and cap["ollama"]["model_installed"] is False

    def down(url):
        raise re_.EmbedError("Ollama is not running on 127.0.0.1:11434.", "Start Ollama.")

    monkeypatch.setattr(main._recall_embed, "version", down)
    cap = run(main.recall_capability(project="app"))
    assert cap["status"] == "blocked"
    assert [r["code"] for r in cap["reasons"]][0] == "ollama_missing"
    assert world.emb.text_calls == []


def test_capability_api_provider_uses_one_test_call(world, monkeypatch):
    run(main.recall_put_settings({"semantic": {"provider": "api", "api": {"endpoint": "https://example.invalid/v1/embeddings"}}}))
    cap = run(main.recall_capability(project="app"))
    assert cap["provider"] == "api" and cap["status"] == "ready"
    assert world.emb.text_calls == [1]

    def boom(sem):
        raise re_.EmbedError("No API key is saved for the embedding API.", "Enter an API key in recall settings.")

    monkeypatch.setattr(main, "_recall_embedder", boom)
    cap = run(main.recall_capability(project="app"))
    assert cap["status"] == "blocked" and cap["reasons"][0]["code"] == "api"
    assert "API key" in cap["reasons"][0]["fix"] or "key" in cap["reasons"][0]["text"]


# ------------------------------------------------------------ pull

def test_pull_streams_progress_and_success(world, monkeypatch):
    seen = {}

    def fake_pull(url, model):
        seen["args"] = (url, model)
        yield {"status": "pulling manifest", "completed": 0, "total": None, "percent": None}
        yield {"status": "pulling abc", "completed": 50, "total": 100, "percent": 50.0}
        yield {"status": "success", "completed": 0, "total": None, "percent": None}

    monkeypatch.setattr(main._recall_embed, "pull", fake_pull)
    resp = run(main.recall_setup_pull(FakeRequest(), None))
    evs = stream(resp)
    assert [e["status"] for e in evs] == ["pulling manifest", "pulling abc", "success"]
    assert evs[1]["percent"] == 50.0
    assert seen["args"] == ("http://127.0.0.1:11434", ri.DEFAULT_MODEL)
    assert resp.media_type == "application/x-ndjson"


def test_pull_refuses_old_ollama_with_412(world, monkeypatch):
    def fake_pull(url, model):
        raise re_.EmbedError("Ollama 0.5.0 is too old for %s" % model, "Update Ollama to the latest version.")
        yield  # pragma: no cover

    monkeypatch.setattr(main._recall_embed, "pull", fake_pull)
    resp = run(main.recall_setup_pull(FakeRequest(), None))
    assert resp.status_code == 412
    body = json.loads(resp.body)
    assert "too old" in body["detail"] and "Update Ollama" in body["fix"]


def test_pull_midstream_error_becomes_error_event(world, monkeypatch):
    def fake_pull(url, model):
        yield {"status": "pulling abc", "completed": 1, "total": 10, "percent": 10.0}
        raise re_.EmbedError("Ollama could not pull m: disk full", "Free disk space.")

    monkeypatch.setattr(main._recall_embed, "pull", fake_pull)
    evs = stream(run(main.recall_setup_pull(FakeRequest(), None)))
    assert evs[0]["status"] == "pulling abc"
    assert evs[-1] == {"type": "error", "message": "Ollama could not pull m: disk full", "fix": "Free disk space."}


def test_pull_client_disconnect_closes_the_pull(world, monkeypatch):
    closed = {}

    def fake_pull(url, model):
        try:
            for i in range(10000):
                yield {"status": "pulling", "completed": i, "total": 10000, "percent": 1.0}
        finally:
            closed["yes"] = True

    monkeypatch.setattr(main._recall_embed, "pull", fake_pull)
    evs = stream(run(main.recall_setup_pull(FakeRequest(after=2), None)))
    assert 1 <= len(evs) < 100
    import time
    for _ in range(30):
        if closed.get("yes"):
            break
        time.sleep(0.1)
    assert closed.get("yes")


# ------------------------------------------------------------ settings and secrets

def test_api_key_is_write_only_and_stored_0600(world):
    secret = "sk-" + "test" + "-" + "abc123"
    patch = {"semantic": {"provider": "api", "enabled": True,
                          "api": {"format": "openai", "endpoint": "https://example.invalid/v1/embeddings",
                                  "model": "text-embedding-3-small", "api_key": secret}}}
    out = run(main.recall_put_settings(patch))
    assert out["semantic"]["api_key_set"] is True and out["semantic"]["api"]["api_key_set"] is True
    assert secret not in json.dumps(out)
    assert secret not in json.dumps(run(main.recall_get_settings()))
    assert secret not in (world.tmp / "recall.json").read_text()
    sec = world.tmp / "recall_secrets.json"
    assert json.loads(sec.read_text()) == {"api_key": secret}
    if os.name == "posix":
        assert stat.S_IMODE(sec.stat().st_mode) == 0o600
    # A patch without the key keeps it; an empty key removes it.
    out = run(main.recall_put_settings({"semantic": {"dims": 128}}))
    assert out["semantic"]["api_key_set"] is True
    out = run(main.recall_put_settings({"semantic": {"api_key": ""}}))
    assert out["semantic"]["api_key_set"] is False and not sec.exists()
    with pytest.raises(HTTPException) as e:
        run(main.recall_put_settings({"semantic": {"api_key": 5}}))
    assert e.value.status_code == 400


def test_settings_validation_errors_do_not_echo_the_key(world):
    secret = "sk-" + "test" + "-" + "zzz999"
    with pytest.raises(HTTPException) as e:
        run(main.recall_put_settings({"semantic": {"api": {"endpoint": "http://example.com/v1", "api_key": secret}}}))
    assert e.value.status_code == 400 and secret not in str(e.value.detail)
    assert not (world.tmp / "recall_secrets.json").exists()


# ------------------------------------------------------------ delta, index, events

def test_delta_never_indexed_then_up_to_date_then_stale(world):
    enable()
    d = run(main.recall_index_delta(project="app"))
    assert d["state"] == "never_indexed"
    assert d["new"]["session"] == 2 and d["new"]["markdown"] == 2 and d["new"]["skill"] == 1
    assert d["new"]["image"] == 1
    assert d["new_chunks_estimate"] > 0 and d["estimate_seconds"] > 0
    index("app")
    d = run(main.recall_index_delta(project="app"))
    assert d["state"] == "up_to_date" and d["new"] == {} and d["changed"] == {} and d["removed"] == {}
    assert d["lock"]["model"] == "fake-embed"
    # A new file and a deleted file.
    (world.proj / "docs" / "extra.md").write_text("A new note about caching.\n")
    (world.proj / "docs" / "design.md").unlink()
    main._recall_disc_cache.clear()
    d = run(main.recall_index_delta(project="app"))
    assert d["state"] == "stale" and d["new"] == {"markdown": 1} and d["removed"] == {"markdown": 1}
    with pytest.raises(HTTPException) as e:
        run(main.recall_index_delta(project="nope"))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        run(main.recall_index_delta(project=""))


def test_delta_model_changed_when_identity_differs(world):
    enable()
    index("app")
    world.emb.identity = {**FakeEmbedder.identity, "model": "other-embed"}
    d = run(main.recall_index_delta(project="app"))
    assert d["state"] == "model_changed"


def test_delta_unavailable_when_embedder_cannot_be_built(world, monkeypatch):
    enable()

    def boom(sem):
        raise re_.EmbedError("No API key is saved for the embedding API.", "Enter an API key.")

    monkeypatch.setattr(main, "_recall_embedder", boom)
    d = run(main.recall_index_delta(project="app"))
    assert d["state"] == "unavailable" and "API key" in d["reason"]


def test_index_requires_project_and_known_project(world):
    enable()
    for body in ({}, {"project": ""}, {"project": 5}, {"project": "app", "full": "yes"}):
        with pytest.raises(HTTPException) as e:
            run(main.recall_index_start(body))
        assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        run(main.recall_index_start({"project": "nope"}))
    assert e.value.status_code == 400


def test_index_events_order_replay_and_exact_counts(world):
    enable()
    st = run(main.recall_index_start({"project": "app"}))
    assert st["state"] == "running" and st["project"]["name"] == "app"
    main._recall_job.wait(15)
    evs = events()
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    assert evs[0]["type"] == "start" and evs[-1]["type"] == "done"
    assert evs[0]["totals"]["by_type"] == {"session": 2, "markdown": 2, "skill": 1, "image": 1}
    kinds = [e["type"] for e in evs]
    assert kinds.count("doc") == 6 and "vector" in kinds and "progress" in kinds
    vec = next(e for e in evs if e["type"] == "vector")
    assert len(vec["preview"]) == 24 and len(vec["xy"]) == 2 and all(-1.0 <= c <= 1.0 for c in vec["xy"])
    summary = evs[-1]["summary"]
    assert summary["documents"] == 6 and summary["by_type"]["session"] == 2
    # Replay from a seq returns exactly the later events.
    assert events(3) == evs[3:]
    assert events(len(evs)) == []
    # Status carries both the v3 and the v2 names.
    s = run(main.recall_index_status())
    assert s["state"] == "done" and s["documents_done"] == 6 and s["sessions_done"] == 6
    assert s["error"] is None and world.emb.image_calls == 1


def test_event_stream_rejects_a_different_run(world):
    enable()
    status = index("app")
    assert stream(run(main.recall_index_events(FakeRequest(), run_id=status["run"])))[0]["type"] == "start"
    with pytest.raises(HTTPException) as exc:
        run(main.recall_index_events(FakeRequest(), run_id="different-run"))
    assert exc.value.status_code == 404


def test_events_without_a_run_is_an_empty_stream(world):
    assert events() == []


def test_second_run_reuses_unchanged_chunks_and_embeds_only_new(world):
    enable()
    index("app")
    first = main._recall_job.status()["chunks_embedded"]
    assert first > 0
    index("app")
    again = main._recall_job.status()
    assert again["chunks_embedded"] == 0 and again["documents_skipped"] == 6
    # Append to a file: only its new tail is embedded.
    p = world.proj / "README.md"
    p.write_text(p.read_text() + ("filler line about routing.\n" * 60) + "Brand new closing remarks.\n")
    main._recall_disc_cache.clear()
    before = world.emb.text_calls[:]
    index("app")
    st = main._recall_job.status()
    assert st["chunks_embedded"] >= 1 and st["chunks_reused"] >= 0
    assert st["documents_done"] == 1
    assert sum(world.emb.text_calls) - sum(before) == st["chunks_embedded"] + 1  # model lock probe


def test_model_change_blocks_incremental_and_full_reindex_recovers(world):
    enable()
    index("app")
    world.emb.identity = {**FakeEmbedder.identity, "model": "other-embed"}
    index("app")
    evs = events()
    assert evs[-1]["type"] == "error" and "other-embed" in evs[-1]["fix"]
    assert run(main.recall_index_delta(project="app"))["state"] == "model_changed"
    index("app", full=True)
    assert events()[-1]["type"] == "done"
    d = run(main.recall_index_delta(project="app"))
    assert d["state"] == "up_to_date" and d["lock"]["model"] == "other-embed"


def test_model_changed_search_falls_back_to_keyword(world):
    enable()
    index("app")
    world.emb.identity = {**FakeEmbedder.identity, "model": "other-embed"}
    res = run(main.recall_search(q="planner classifier", project="app", mode="hybrid", types="session,markdown"))
    assert res["coverage"]["semantic"]["indexed_sessions"] == 0
    assert [h["id"] for h in res["hits"]] == ["c1"] and res["hits"][0]["match"] == "keyword"
    assert res["coverage"]["documents"]["searched"] is False


# ------------------------------------------------------------ search types and doc hits

def test_search_types_returns_document_hits(world):
    enable()
    index("app")
    res = run(main.recall_search(q="planner classifier", project="app", mode="semantic", types="markdown,skill"))
    assert res["hits"] and all(h["doc_type"] in ("markdown", "skill") for h in res["hits"])
    top = res["hits"][0]
    assert top["doc_id"].startswith("markdown:") and top["path"].endswith("README.md")
    assert top["match"] == "semantic" and "classifier" in top["snippet"]
    assert res["by_agent"] and res["coverage"]["documents"]["searched"] is True
    assert res["coverage"]["candidates"] == 0  # no session was searched

    both = run(main.recall_search(q="planner classifier", project="app", mode="semantic"))
    kinds = {h["doc_type"] for h in both["hits"]}
    assert "session" in kinds and kinds - {"session"}
    only = run(main.recall_search(q="planner classifier", project="app", mode="hybrid", types="session"))
    assert {h["doc_type"] for h in only["hits"]} == {"session"}


def test_document_filter_selects_hybrid_when_mode_is_omitted(world):
    enable(default_mode="keyword")
    index("app")
    response = run(main.recall_search(q="thumbnail renderer", project="app", types="markdown"))
    assert response["coverage"]["documents"]["searched"]
    assert response["hits"] and all(hit["doc_type"] == "markdown" for hit in response["hits"])


def test_search_types_validation_keyword_and_projectless(world):
    enable()
    index("app")
    with pytest.raises(HTTPException) as e:
        run(main.recall_search(q="planner", project="app", types="skill,bogus"))
    assert e.value.status_code == 400
    # Keyword mode keeps v1 behavior: session hits only, documents say why.
    res = run(main.recall_search(q="planner", project="app", mode="keyword", types="markdown"))
    assert res["hits"] == [] and res["coverage"]["documents"]["searched"] is False
    res = run(main.recall_search(q="planner", project="app", mode="keyword"))
    assert [h["id"] for h in res["hits"]] == ["c1"] and "documents" not in res["coverage"]
    assert res["hits"][0]["doc_type"] == "session"
    # Documents need a project.
    res = run(main.recall_search(q="planner classifier", mode="semantic", types="markdown"))
    assert res["hits"] == [] and "pick a project" in res["coverage"]["documents"]["reason"]


def test_semantic_off_keeps_keyword_default(world):
    res = run(main.recall_search(q="planner", project="app"))
    assert res["coverage"]["semantic"] == {"mode": "keyword"}
    assert [h["id"] for h in res["hits"]] == ["c1"]
    res = run(main.recall_search(q="planner", project="app", types="markdown"))
    assert res["hits"] == []
    with pytest.raises(HTTPException) as e:
        run(main.recall_search(q="planner", project="app", mode="semantic"))
    assert e.value.status_code == 400


def test_stale_document_is_dropped_from_semantic_hits(world):
    enable()
    index("app")
    (world.proj / "README.md").write_text("Completely rewritten text without the old words.\n")
    main._recall_disc_cache.clear()
    res = run(main.recall_search(q="planner classifier route", project="app", mode="semantic", types="markdown"))
    assert all(not h["path"].endswith("README.md") for h in res["hits"])
    assert res["coverage"]["documents"]["stale"] == 1


def test_documents_are_scoped_to_the_project_index(world):
    enable()
    index("app")
    index("other")
    res = run(main.recall_search(q="billing notes", project="other", mode="semantic", types="markdown"))
    assert res["hits"] and all("other" not in h["doc_id"].split(":")[0] for h in res["hits"])
    assert all("billing" in h["snippet"].lower() for h in res["hits"][:1])
    res = run(main.recall_search(q="billing notes", project="app", mode="semantic", types="markdown"))
    assert all("billing" not in h["snippet"].lower() for h in res["hits"])


# ------------------------------------------------------------ document and image reads

def _id(world, prefix):
    rows = main._recall_get_store().documents(main._recall._select(world.sessions, "app", None, None, main.ANTIGRAVITY_UNASSIGNED)[0]["key"])
    return next(d for d in rows if d.startswith(prefix))


def test_document_text_route_pages_redacted_chunks(world):
    enable()
    secret = "sk-" + "ant" + "-" + "api03" + "-" + "A" * 40
    (world.proj / "docs" / "notes.md").write_text("config: " + secret + "\n" + ("padding words " * 120) + "\ntail\n")
    index("app")
    did = _id(world, "markdown:repo:project:docs/notes.md")
    page = run(main.recall_document(did, project="app", offset=None, limit="2"))
    assert page["type"] == "text" and page["doc_type"] == "markdown" and page["path"].endswith("docs/notes.md")
    assert len(page["chunks"]) == 2 and page["next"] == 2 and page["total"] >= 3
    assert secret not in json.dumps(page)
    nxt = run(main.recall_document(did, project="app", offset="2", limit="50"))
    assert nxt["next"] is None and nxt["offset"] == 2
    with pytest.raises(HTTPException) as e:
        run(main.recall_document(did, project=None, offset=None, limit=None))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        run(main.recall_document(did, project="other", offset=None, limit=None))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        run(main.recall_document("markdown:repo:project:docs/missing.md", project="app", offset=None, limit=None))
    assert e.value.status_code == 404
    sid = "session:codex:c1"
    with pytest.raises(HTTPException) as e:
        run(main.recall_document(sid, project="app", offset=None, limit=None))
    assert e.value.status_code == 400


def test_image_route_serves_only_indexed_documents_of_the_requested_project(world):
    enable()
    # Not indexed yet: the file exists and is discoverable, but there is no index row.
    rows = run(main._recall_asyncio.to_thread(main._recall_discover, world.pkey, world.sessions[:2], True))
    img_id = next(d for d in rows["by_id"] if d.startswith("image:"))
    with pytest.raises(HTTPException) as e:
        run(main.recall_document_image(img_id, project="app"))
    assert e.value.status_code == 404
    index("app")
    assert world.emb.image_calls == 1
    resp = run(main.recall_document_image(img_id, project="app"))
    assert resp.body == PNG and resp.media_type == "image/png"
    assert resp.headers["x-content-type-options"] == "nosniff"
    # Another project cannot read it, even though the id is valid and indexed elsewhere.
    index("other")
    with pytest.raises(HTTPException) as e:
        run(main.recall_document_image(img_id, project="other"))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        run(main.recall_document_image(img_id, project=None))
    assert e.value.status_code == 400
    # The text route describes an image with its URL instead of bytes.
    page = run(main.recall_document(img_id, project="app", offset=None, limit=None))
    assert page["type"] == "image" and "/image?project=" in page["url"]
    # A traversal-shaped id is simply not in the index.
    with pytest.raises(HTTPException) as e:
        run(main.recall_document_image("image:codex:user:../../etc/passwd", project="app"))
    assert e.value.status_code == 404
    # A text document is not an image.
    with pytest.raises(HTTPException) as e:
        run(main.recall_document_image(_id(world, "markdown:"), project="app"))
    assert e.value.status_code == 404
    # The file is gone: refused, not an error page.
    for f in (world.home / ".codex" / "generated_images" / "c1").iterdir():
        f.unlink()
    main._recall_disc_cache.clear()
    with pytest.raises(HTTPException) as e:
        run(main.recall_document_image(img_id, project="app"))
    assert e.value.status_code == 404


def test_inline_image_is_indexed_without_delta_reading_transcripts(world, monkeypatch):
    calls = []
    payload = {"type": "user", "message": {"content": [{"type": "image",
               "source": {"type": "base64", "media_type": "image/png",
                          "data": base64.b64encode(PNG + b"inline").decode()}}]}}

    def events_for(agent, sid):
        calls.append((agent, sid))
        return [payload] if sid == "a1" else []

    monkeypatch.setattr(main, "_recall_inline_events", events_for)
    enable()
    assert run(main.recall_index_delta(project="app"))["state"] == "never_indexed"
    assert not calls
    index("app")
    assert ("claude", "a1") in calls and world.emb.image_calls == 2
    row = next(r for r in main._recall_get_store().documents(world.pkey).values()
               if r["source"]["kind"] == "inline_image")
    assert row["source"]["session_id"] == "a1"
    page = run(main.recall_document_image(row["doc_id"], project="app"))
    assert page.body == PNG + b"inline"
    calls.clear()
    assert run(main.recall_index_delta(project="app"))["state"] == "up_to_date"
    assert not calls
    index("app")
    assert not calls and world.emb.image_calls == 2
    with pytest.raises(HTTPException) as e:
        run(main.recall_document_image(row["doc_id"], project="other"))
    assert e.value.status_code == 404


def test_image_documents_follow_the_images_setting(world):
    enable(images=False)
    index("app")
    assert world.emb.image_calls == 0
    d = run(main.recall_index_delta(project="app"))
    assert d["state"] == "up_to_date" and "image" not in d["new"]


# ------------------------------------------------------------ ask

class FakeSm:
    name = "fake"

    def is_available(self):
        return True


def reply(action, args, thought="t"):
    return json.dumps({"thought": thought, "action": action, "args": args})


@pytest.fixture
def ask_env(monkeypatch):
    calls, script = [], []

    def fake_llm(sm, prompt):
        calls.append(prompt)
        return script[min(len(calls) - 1, len(script) - 1)]

    monkeypatch.setattr(main._recall_summaries, "load_config",
                        lambda: {"enabled": True, "backend": "fake", "model": None})
    monkeypatch.setattr(main, "get_summarizer", lambda *a, **k: FakeSm())
    monkeypatch.setattr(main._recall_summaries, "ask_untrusted", fake_llm)
    return calls, script


def ask(body):
    async def go():
        resp = await main.recall_ask(FakeRequest(), body)
        return await _collect(resp)
    return asyncio.run(go())


def test_ask_reads_a_document_and_cites_it(world, ask_env):
    enable()
    index("app")
    calls, script = ask_env
    script += [
        reply("search", {"query": "classifier planner routing", "mode": "semantic", "types": ["markdown"]}),
        reply("read_document", {"doc_id": "D1"}),
        reply("answer", {"answer": "The README says the planner routes with a classifier [D1].", "citations": ["D1"]}),
    ]
    events_ = ask({"question": "How does the planner route?", "project": "app"})
    ans = events_[-1]
    assert ans["type"] == "answer"
    cit = ans["citations"][0]
    assert cit["label"] == "D1" and cit["doc_type"] == "markdown" and cit["path"].endswith("README.md")
    assert cit["doc_id"].startswith("markdown:") and cit["title"]
    steps = [e for e in events_ if e["type"] == "step"]
    assert [s["action"] for s in steps] == ["search", "search", "read_document"]
    assert steps[1]["args"]["types"] == ["markdown"]
    assert any(s["action"] == "read_document" and s["args"]["doc_id"] == cit["doc_id"] for s in steps)
    obs = [e for e in events_ if e["type"] == "observation"]
    assert any("D1" in o.get("sessions", []) for o in obs)
    # The document text reached the model fenced.
    assert any("The planner uses a classifier" in c for c in calls)


def test_ask_read_document_refuses_other_projects_and_other_agents(world, ask_env):
    enable()
    index("app")
    index("other")
    other_doc = _other_id(world)
    calls, script = ask_env
    script += [
        reply("read_document", {"doc_id": other_doc}),
        reply("read_document", {"doc_id": _id(world, "skill:claude:user:bug-audit")}),
        reply("answer", {"answer": "done", "citations": []}),
    ]
    events_ = ask({"question": "What does the other README say?", "project": "app", "agent": "codex"})
    obs = [e for e in events_ if e["type"] == "observation"]
    assert [o["summary"] for o in obs if o["n"] in (1, 2)] == ["read failed", "read failed"]
    assert not any("billing" in c for c in calls)
    assert not any("Audit the planner" in c for c in calls)


def test_ask_without_project_cannot_read_documents(world, ask_env):
    enable()
    index("app")
    calls, script = ask_env
    script += [reply("read_document", {"doc_id": "markdown:repo:project:README.md"}),
               reply("answer", {"answer": "ok", "citations": []})]
    events_ = ask({"question": "anything about the planner?"})
    obs = [e for e in events_ if e["type"] == "observation"]
    assert any(o["n"] == 1 and o["summary"] == "read failed" for o in obs)


def _other_id(world):
    key = main._recall._select(world.sessions, "other", None, None, main.ANTIGRAVITY_UNASSIGNED)[0]["key"]
    return next(d for d in main._recall_get_store().documents(key) if d.startswith("markdown:"))
