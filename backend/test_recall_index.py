import hashlib
import json
import math
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import recall
import recall_index as ri

SECRET = "gh" + "p_" + "b" * 36


@pytest.fixture(autouse=True)
def _no_repo_resolver(monkeypatch):
    monkeypatch.setattr(recall, "repo_resolver", None)


# ------------------------------------------------------------ fakes

def _hash_vec(text, dims):
    v = [0.0] * dims
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dims] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


class FakeEmbedder:
    def __init__(self, dims=64, model="fake-embed"):
        self.dims = dims
        self.model = model
        self.doc_calls = 0
        self.docs_seen = []
        self.fail_after = None

    def embed_documents(self, texts):
        if self.fail_after is not None and self.doc_calls >= self.fail_after:
            raise ri.EmbedError("Ollama is not reachable at http://127.0.0.1:11434. Start it with: ollama serve")
        self.doc_calls += 1
        self.docs_seen.extend(texts)
        return [_hash_vec(t, self.dims) for t in texts]

    def embed_query(self, text):
        return _hash_vec(text, self.dims)


def chunk(idx, text, kind="assistant", turn=1):
    return {"idx": idx, "turn": turn, "kind": kind, "text": text}


def dt(day):
    return datetime(2026, 11, day, tzinfo=timezone.utc)


def sess(agent, sid, day, project="/r/app"):
    return {"agent": agent, "id": sid, "project": project, "timestamp": dt(day),
            "display": f"prompt {sid}", "model": "m", "tokens": {"total": 1}, "cost": 1.0}


def loader_for(table):
    def load(agent, sid):
        if (agent, sid) not in table:
            return None
        return table[(agent, sid)], "live"
    return load


@pytest.fixture
def store(tmp_path):
    return ri.VectorStore(tmp_path / "idx.db")


def build(store, emb, table, sessions):
    job = ri.IndexJob(store, emb, loader_for(table))
    job.start(sessions)
    job.wait(10)
    return job


# ------------------------------------------------------------ settings

def test_defaults_when_file_missing(tmp_path):
    s = ri.load_settings(tmp_path / "recall.json")
    assert s == {"semantic": {"enabled": False, "model": "embeddinggemma-2:740m",
                              "ollama_url": "http://127.0.0.1:11434", "dims": 256,
                              "default_mode": "keyword"}}


def test_settings_roundtrip_and_partial_update(tmp_path):
    p = tmp_path / "recall.json"
    out = ri.update_settings({"semantic": {"enabled": True}}, p)
    assert out["semantic"]["enabled"] is True and out["semantic"]["dims"] == 256
    out = ri.update_settings({"semantic": {"model": "other-model"}}, p)
    assert out["semantic"]["enabled"] is True and out["semantic"]["model"] == "other-model"
    assert json.loads(p.read_text())["semantic"]["model"] == "other-model"


def test_damaged_settings_file_gives_defaults(tmp_path):
    p = tmp_path / "recall.json"
    p.write_text("{not json")
    assert ri.load_settings(p)["semantic"]["enabled"] is False


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434", "http://LOCALHOST",
])
def test_loopback_urls_accepted(url):
    assert ri.validate_settings({"ollama_url": url})["ollama_url"] == url


@pytest.mark.parametrize("url", [
    "http://10.0.0.5:11434", "http://example.com", "http://localhost.evil.com:11434",
    "http://127.0.0.1@evil.com:11434", "ftp://127.0.0.1", "", "not a url", "http://127.0.0.1:abc",
])
def test_non_loopback_urls_rejected(url):
    with pytest.raises(ValueError):
        ri.validate_settings({"ollama_url": url})


@pytest.mark.parametrize("bad", [
    {"dims": 100}, {"dims": True}, {"dims": "256"}, {"model": ""}, {"model": "   "},
    {"default_mode": "fuzzy"}, {"enabled": "yes"},
])
def test_invalid_settings_rejected(bad):
    with pytest.raises(ValueError):
        ri.validate_settings(bad)


def test_update_rejects_bad_value_and_keeps_file(tmp_path):
    p = tmp_path / "recall.json"
    ri.update_settings({"semantic": {"model": "keep-me"}}, p)
    with pytest.raises(ValueError):
        ri.update_settings({"semantic": {"ollama_url": "http://evil.example"}}, p)
    assert ri.load_settings(p)["semantic"]["model"] == "keep-me"


# ------------------------------------------------------------ vectors

def test_fit_truncates_then_renormalizes():
    v = ri._fit([3.0, 4.0, 100.0, 100.0], 2)
    assert v == pytest.approx([0.6, 0.8])
    assert math.sqrt(sum(x * x for x in v)) == pytest.approx(1.0)
    assert ri._fit([0.0, 0.0, 0.0], 2) == [0.0, 0.0]


def test_blob_roundtrip_and_ranking(store):
    texts = ["alpha beta gamma", "delta epsilon", "alpha alpha zeta"]
    chunks = [chunk(i, t) for i, t in enumerate(texts)]
    vecs = [_hash_vec(t, 64) for t in texts]
    store.upsert_session("claude", "s1", "m", 64, "fp", chunks, vecs)
    q = _hash_vec("alpha", 64)
    top = store.top_k(q, {("claude", "s1")}, "m", 64)
    assert [t[2] for t in top] == [2, 0, 1]
    assert top[0][3] == pytest.approx(sum(a * b for a, b in zip(q, vecs[2])), abs=1e-6)
    # blob decodes to what was stored
    import sqlite3
    from array import array
    row = sqlite3.connect(store.path).execute("SELECT vec FROM vectors WHERE idx=1").fetchone()
    a = array("f")
    a.frombytes(row[0])
    assert list(a) == pytest.approx(vecs[1], abs=1e-6)


def test_upsert_replaces_atomically(store):
    store.upsert_session("c", "s", "m", 8, "fp1", [chunk(0, "a"), chunk(1, "b")],
                         [_hash_vec("a", 8), _hash_vec("b", 8)])
    store.upsert_session("c", "s", "m", 8, "fp2", [chunk(0, "c")], [_hash_vec("c", 8)])
    st = store.stats()
    assert st["chunks"] == 1 and st["sessions"] == 1
    assert store.is_current("c", "s", "m", 8, "fp2")
    assert not store.is_current("c", "s", "m", 8, "fp1")
    with pytest.raises(ValueError):
        store.upsert_session("c", "s", "m", 8, "fp3", [chunk(0, "x")], [[0.0] * 3])
    assert store.is_current("c", "s", "m", 8, "fp2")  # failed write left the old rows


def test_model_and_dim_switch_ignored(store):
    store.upsert_session("c", "s", "old-model", 8, "fp", [chunk(0, "alpha")], [_hash_vec("alpha", 8)])
    q = _hash_vec("alpha", 8)
    assert store.top_k(q, {("c", "s")}, "new-model", 8) == []
    assert store.top_k(_hash_vec("alpha", 16), {("c", "s")}, "old-model", 16) == []
    assert not store.is_current("c", "s", "new-model", 8, "fp")
    assert not store.is_current("c", "s", "old-model", 16, "fp")
    assert store.is_current("c", "s", "old-model", 8, "fp")


def test_allowed_sessions_filter(store):
    for sid in ("a", "b"):
        store.upsert_session("c", sid, "m", 8, "fp", [chunk(0, "alpha")], [_hash_vec("alpha", 8)])
    out = store.top_k(_hash_vec("alpha", 8), {("c", "b")}, "m", 8)
    assert [(a, i) for a, i, _, _ in out] == [("c", "b")]
    assert store.top_k(_hash_vec("alpha", 8), set(), "m", 8) == []


@pytest.mark.parametrize("use_numpy", [True, False])
def test_top_k_streams_and_bounds_memory(store, monkeypatch, use_numpy):
    if use_numpy:
        pytest.importorskip("numpy")
    else:
        monkeypatch.setattr(ri, "_np", None)
    dim = 8
    n_sessions, per = 50, 100  # 5000 rows
    for s in range(n_sessions):
        chunks = [chunk(i, f"w{s} {i}") for i in range(per)]
        store.upsert_session("c", f"s{s}", "m", dim, "fp", chunks,
                             [_hash_vec(f"w{s} {i}", dim) for i in range(per)])
    allowed = {("c", f"s{s}") for s in range(n_sessions)}
    q = _hash_vec("w3 7", dim)
    out = store.top_k(q, allowed, "m", dim, k=200)
    assert len(out) == 200
    assert store.last_peak_heap <= 200
    assert store.last_max_batch <= ri.SCAN_BATCH < 5000
    scores = [t[3] for t in out]
    assert scores == sorted(scores, reverse=True)
    # matches a brute-force recompute
    rows = []
    for s in range(n_sessions):
        for i in range(per):
            v = _hash_vec(f"w{s} {i}", dim)
            rows.append(sum(a * b for a, b in zip(q, v)))
    assert scores[:5] == pytest.approx(sorted(rows, reverse=True)[:5], abs=1e-5)


def test_stats(store):
    assert store.stats() == {"chunks": 0, "sessions": 0, "model": None, "bytes": store.stats()["bytes"],
                             "updated_at": None}
    store.upsert_session("c", "s", "m", 8, "fp", [chunk(0, "a")], [_hash_vec("a", 8)])
    st = store.stats()
    assert st["chunks"] == 1 and st["sessions"] == 1 and st["model"] == "m"
    assert st["bytes"] > 0 and st["updated_at"].endswith("Z")


# ------------------------------------------------------------ fingerprint

def test_fingerprint_uses_redacted_text_and_constants(monkeypatch):
    a = [chunk(0, f"token {SECRET} here")]
    b = [chunk(0, "token " + "gh" + "p_" + "c" * 36 + " here")]
    assert ri.session_fingerprint(a) == ri.session_fingerprint(b)  # same after redaction
    base = ri.session_fingerprint(a)
    assert ri.session_fingerprint(a + [chunk(1, "more")]) != base
    monkeypatch.setattr(recall, "RESULT_CHARS", recall.RESULT_CHARS + 1)
    assert ri.session_fingerprint(a) != base
    monkeypatch.undo()
    monkeypatch.setattr(recall, "INDEX_VERSION", recall.INDEX_VERSION + 1)
    assert ri.session_fingerprint(a) != base


# ------------------------------------------------------------ job

def test_job_builds_skips_and_reports(store):
    emb = FakeEmbedder()
    table = {("claude", "a"): [chunk(0, "alpha one"), chunk(1, "beta two")],
             ("codex", "b"): [chunk(0, "gamma three")]}
    sessions = [sess("claude", "a", 10), sess("codex", "b", 11)]
    job = build(store, emb, table, sessions)
    st = job.status()
    assert st["state"] == "done" and st["error"] is None
    assert st["sessions_total"] == 2 and st["sessions_done"] == 2 and st["sessions_skipped"] == 0
    assert st["chunks_embedded"] == 3 and st["finished_at"].endswith("Z")
    assert st["project"] == {"key": None, "name": None} or st["project"] is None
    assert set(st) == {"state", "project", "sessions_total", "sessions_done", "sessions_skipped",
                       "chunks_embedded", "chunks_per_sec", "started_at", "finished_at", "error"}
    calls = emb.doc_calls
    job2 = build(store, emb, table, sessions)
    assert job2.status()["sessions_skipped"] == 2 and job2.status()["chunks_embedded"] == 0
    assert emb.doc_calls == calls


def test_job_project_filter_and_name(store):
    emb = FakeEmbedder()
    table = {("claude", "a"): [chunk(0, "alpha")], ("claude", "z"): [chunk(0, "zeta")]}
    sessions = [sess("claude", "a", 10, "/r/app"), sess("claude", "z", 11, "/r/other")]
    job = ri.IndexJob(store, emb, loader_for(table))
    job.start(sessions, "app")
    job.wait(10)
    st = job.status()
    assert st["sessions_total"] == 1 and st["project"] == {"key": "/r/app", "name": "app"}
    assert store.stats()["sessions"] == 1


def test_job_embeds_redacted_text_only(store):
    emb = FakeEmbedder()
    pem = [chunk(0, "-----BEGIN PRIVATE KEY-----\nAAAA"), chunk(1, "BBBB continued"),
           chunk(2, f"use {SECRET} now")]
    build(store, emb, {("claude", "a"): pem}, [sess("claude", "a", 10)])
    joined = "\n".join(emb.docs_seen)
    assert "AAAA" not in joined and "BBBB" not in joined and SECRET not in joined


def test_job_busy_while_running_then_free(store):
    gate = threading.Event()
    emb = FakeEmbedder()
    orig = emb.embed_documents

    def slow(texts):
        gate.wait(5)
        return orig(texts)
    emb.embed_documents = slow
    table = {("claude", "a"): [chunk(0, "alpha")]}
    job = ri.IndexJob(store, emb, loader_for(table))
    job.start([sess("claude", "a", 10)])
    with pytest.raises(ri.JobBusy) as e:
        job.start([sess("claude", "a", 10)])
    assert e.value.status["state"] == "running"
    gate.set()
    job.wait(10)
    assert job.status()["state"] == "done"
    job.start([sess("claude", "a", 10)])  # allowed again
    job.wait(10)


def test_job_ollama_error_stops_and_keeps_written(store):
    emb = FakeEmbedder()
    emb.fail_after = 1
    table = {("claude", "a"): [chunk(0, "alpha")], ("claude", "b"): [chunk(0, "beta")]}
    job = build(store, emb, table, [sess("claude", "a", 11), sess("claude", "b", 10)])
    st = job.status()
    assert st["state"] == "error" and "ollama serve" in st["error"]
    assert store.stats()["sessions"] == 1  # newest session was written before the failure


def test_job_unreadable_session_does_not_stop(store):
    emb = FakeEmbedder()
    table = {("claude", "b"): [chunk(0, "beta")]}
    job = build(store, emb, table, [sess("claude", "a", 11), sess("claude", "b", 10)])
    assert job.status()["state"] == "done" and job.status()["sessions_done"] == 2
    assert store.stats()["sessions"] == 1


# ------------------------------------------------------------ search integration

def test_semantic_search_end_to_end_and_append_falls_back(store):
    emb = FakeEmbedder()
    table = {("claude", "a"): [chunk(0, "render pipeline timeout", "user"), chunk(1, "fixed the render queue")],
             ("codex", "b"): [chunk(0, "thumbnail colours washed out", "user")]}
    sessions = [sess("claude", "a", 10), sess("codex", "b", 11)]
    build(store, emb, table, sessions)
    sem = ri.make_semantic(store, emb)
    out = recall.search(sessions, loader_for(table), "render timeout", mode="hybrid", semantic=sem)
    cov = out["coverage"]["semantic"]
    assert cov == {"mode": "hybrid", "model": "fake-embed", "indexed_sessions": 2, "unindexed_sessions": 0}
    assert out["hits"][0]["id"] == "a" and out["hits"][0]["match"] in ("both", "semantic")

    # append a chunk to one session: its fingerprint no longer matches
    table[("claude", "a")] = table[("claude", "a")] + [chunk(2, "render regression again")]
    out = recall.search(sessions, loader_for(table), "render", mode="hybrid", semantic=sem)
    assert out["coverage"]["semantic"]["unindexed_sessions"] == 1
    assert out["coverage"]["semantic"]["indexed_sessions"] == 1
    assert any(h["id"] == "a" and h["match"] == "keyword" for h in out["hits"])  # keyword still works
    assert not any(h["id"] == "a" and h["match"] != "keyword" for h in out["hits"])


# ------------------------------------------------------------ Ollama client

class _Ollama(BaseHTTPRequestHandler):
    models = ["embeddinggemma-2:740m"]
    posts = []

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._send(200, {"version": "0.36.1"})
        elif self.path == "/api/tags":
            self._send(200, {"models": [{"name": n} for n in self.models]})
        else:
            self._send(404, {})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).posts.append(req)
        if req["model"] not in self.models:
            return self._send(404, {"error": f"model \"{req['model']}\" not found, try pulling it first"})
        self._send(200, {"embeddings": [[3.0, 4.0, 12.0, 0.0] + [1.0] * 8 for _ in req["input"]]})


@pytest.fixture
def ollama():
    _Ollama.models = ["embeddinggemma-2:740m"]
    _Ollama.posts = []
    srv = HTTPServer(("127.0.0.1", 0), _Ollama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_probe_ok_and_missing_model(ollama):
    e = ri.OllamaEmbedder(ollama, "embeddinggemma-2:740m", 4)
    assert e.probe() == {"reachable": True, "version": "0.36.1", "model_installed": True, "error": None}
    p = ri.OllamaEmbedder(ollama, "nomic-embed-text", 4).probe()
    assert p["reachable"] and not p["model_installed"]
    assert p["error"] == "Model nomic-embed-text is not installed. Run: ollama pull nomic-embed-text"


def test_probe_unreachable():
    p = ri.OllamaEmbedder("http://127.0.0.1:9", "m", 4).probe()
    assert p["reachable"] is False and "ollama serve" in p["error"]


def test_embed_prefixes_batches_truncates_and_normalizes(ollama):
    e = ri.OllamaEmbedder(ollama, "embeddinggemma-2:740m", 2)
    vecs = e.embed_documents(["x" * 7000] + ["t"] * 40)
    assert len(vecs) == 41
    assert vecs[0] == pytest.approx([0.6, 0.8])
    assert [len(p["input"]) for p in _Ollama.posts] == [32, 9]
    first = _Ollama.posts[0]["input"][0]
    assert first.startswith("title: none | text: ") and len(first) == len("title: none | text: ") + 6000
    assert _Ollama.posts[0]["truncate"] is True
    e.embed_query("hello")
    assert _Ollama.posts[-1]["input"] == ["task: search result | query: hello"]


def test_embed_missing_model_has_fix_and_short_vectors_explained(ollama):
    with pytest.raises(ri.EmbedError, match="ollama pull nope"):
        ri.OllamaEmbedder(ollama, "nope", 4).embed_query("q")
    with pytest.raises(ri.EmbedError, match="shorter than 768"):
        ri.OllamaEmbedder(ollama, "embeddinggemma-2:740m", 768).embed_query("q")
    with pytest.raises(ri.EmbedError, match="ollama serve"):
        ri.OllamaEmbedder("http://127.0.0.1:9", "m", 4).embed_query("q")
