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
    # v3 intentionally adds provider/ollama/api/images; the v2 flat keys remain as aliases.
    s = ri.load_settings(tmp_path / "recall.json")["semantic"]
    assert s["enabled"] is False and s["provider"] == "ollama" and s["images"] is True
    assert s["ollama"] == {"url": "http://127.0.0.1:11434", "model": "embeddinggemma-2:740m"}
    assert s["api"] == {"format": "openai", "endpoint": "https://api.openai.com/v1/embeddings",
                        "model": "text-embedding-3-small"}
    assert s["dims"] == 256 and s["default_mode"] == "keyword"
    assert s["model"] == "embeddinggemma-2:740m" and s["ollama_url"] == "http://127.0.0.1:11434"


def test_settings_roundtrip_and_partial_update(tmp_path):
    p = tmp_path / "recall.json"
    out = ri.update_settings({"semantic": {"enabled": True}}, p)
    assert out["semantic"]["enabled"] is True and out["semantic"]["dims"] == 256
    out = ri.update_settings({"semantic": {"model": "other-model"}}, p)
    assert out["semantic"]["enabled"] is True and out["semantic"]["model"] == "other-model"
    # the file now holds the v3 shape (nested), not the v2 flat keys
    assert json.loads(p.read_text())["semantic"]["ollama"]["model"] == "other-model"


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


# ================================================================ v3
import os  # noqa: E402
import sqlite3  # noqa: E402
import stat  # noqa: E402
import time  # noqa: E402

# ------------------------------------------------------------ v3 settings


def test_v2_settings_file_still_loads(tmp_path):
    p = tmp_path / "recall.json"
    p.write_text(json.dumps({"semantic": {"enabled": True, "model": "old-model",
                                          "ollama_url": "http://localhost:11434", "dims": 512,
                                          "default_mode": "hybrid"}}))
    s = ri.load_settings(p)["semantic"]
    assert s["enabled"] is True and s["dims"] == 512 and s["default_mode"] == "hybrid"
    assert s["ollama"] == {"url": "http://localhost:11434", "model": "old-model"}
    assert s["model"] == "old-model" and s["provider"] == "ollama" and s["images"] is True
    # an update upgrades the file to the v3 shape without losing the v2 values
    ri.update_settings({"semantic": {"images": False}}, p)
    raw = json.loads(p.read_text())["semantic"]
    assert raw["ollama"]["model"] == "old-model" and raw["images"] is False and "model" not in raw


@pytest.mark.parametrize("query", ["key=example", "api_key=example", "access_token=example", "sig=example"])
def test_embedding_api_credentials_do_not_belong_in_endpoint(query):
    with pytest.raises(ValueError, match="API key field"):
        ri.validate_settings({"api": {"endpoint": "https://example.invalid/v1/embeddings?" + query}})


def test_v3_provider_images_and_api_validation(tmp_path):
    p = tmp_path / "recall.json"
    out = ri.update_settings({"semantic": {"provider": "api", "api": {"model": "m1"}}}, p)["semantic"]
    assert out["provider"] == "api" and out["images"] is False and out["api"]["model"] == "m1"
    assert out["api"]["format"] == "openai"  # untouched keys survive the merge
    out = ri.update_settings({"semantic": {"images": True}}, p)["semantic"]
    assert out["images"] is True
    out = ri.update_settings({"semantic": {"provider": "ollama"}}, p)["semantic"]
    assert out["images"] is True  # back to the ollama default
    for bad in ({"provider": "cloud"}, {"api": {"format": "cohere"}}, {"api": {"endpoint": "http://example.com/v1"}},
                {"api": {"endpoint": "ftp://x"}}, {"api": {"model": ""}}, {"images": "yes"}, {"api": []},
                {"ollama": {"url": "http://example.com"}}):
        with pytest.raises(ValueError):
            ri.validate_settings(bad)
    assert ri.validate_settings({"api": {"endpoint": "http://127.0.0.1:1234/v1/embeddings"}})["api"]["endpoint"]
    assert ri.validate_settings({"api": {"format": "gemini", "endpoint": "https://x.example/v1"}})["api"]["format"] == "gemini"


def test_api_key_file_is_private_and_never_in_settings(tmp_path):
    sec = tmp_path / "recall_secrets.json"
    key = "sk" + "-" + "z" * 30
    ri.write_api_key(key, sec)
    assert ri.api_key_set(sec) and ri.read_api_key(sec) == key
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(sec).st_mode) == 0o600
    p = tmp_path / "recall.json"
    ri.update_settings({"semantic": {"api_key": key, "api": {"api_key": key}}}, p)
    assert key not in p.read_text()
    ri.write_api_key("", sec)
    assert not ri.api_key_set(sec)


# ------------------------------------------------------------ v3 fakes

class FakeEmbedder3:
    """Matches the spec section 2 interface. ``texts`` counts real chunks only
    (the lock probe is not counted)."""

    supports_images = True

    def __init__(self, dims=32, model="fake-v3", digest="sha256:aaa"):
        self.dims = dims
        self.model = model
        self.digest = digest
        self.texts = []
        self.titles = []
        self.images = []
        self.probe_calls = 0
        self.fail_on = None

    @property
    def identity(self):
        return {"provider": "ollama", "model": self.model, "endpoint_host": "127.0.0.1:11434",
                "dims": self.dims, "format": None}

    def lock_evidence(self):
        return {"ollama_digest": self.digest, "returned_model": None}

    def embed_texts(self, texts, kind, titles=None):
        out = []
        for i, t in enumerate(texts):
            if t == ri.PROBE_TEXT:
                self.probe_calls += 1
            elif kind == "document":
                self.texts.append(t)
                self.titles.append(titles[i] if titles else None)
                if self.fail_on and self.fail_on in t:
                    raise ri.EmbedError("Ollama is not reachable at http://127.0.0.1:11434. Start it with: ollama serve")
            out.append(_hash_vec(t + self.model, self.dims))
        return out

    def embed_images(self, images):
        self.images.extend(images)
        return [_hash_vec("img" + hashlib.md5(b).hexdigest(), self.dims) for b in images]


def sess3(agent, sid, day, project="/r/app", tokens=1, messages=None):
    s = sess(agent, sid, day, project)
    s["tokens"] = {"total": tokens}
    if messages is not None:
        s["message_count"] = messages
    return s


def file_doc(name, text, dtype="skill", agent="claude", scope="project"):
    return {"doc_id": f"{dtype}:{agent}:{scope}:{name}", "type": dtype, "agent": agent, "scope": scope,
            "title": name, "source": {"kind": "text", "text": text}, "mtime": 1.0, "size": len(text),
            "cheap_fp": hashlib.md5(text.encode()).hexdigest()}


def image_doc(name, data):
    return {"doc_id": f"image:claude:project:{name}", "type": "image", "agent": "claude", "scope": "project",
            "title": name, "source": {"kind": "file", "path": name}, "mtime": 1.0, "size": len(data),
            "cheap_fp": hashlib.md5(data).hexdigest()}


def make_run(store, emb, table=None, images=None, **kw):
    return ri.IndexRun(store, emb, loader_for(table or {}),
                       image_reader=lambda d: (images or {}).get(d["title"]), **kw)


def do_run(run, project, docs, full=False):
    run.start(project, docs, full=full)
    run.wait(20)
    return run.status()


def sdocs(sessions):
    return [ri.session_document(s) for s in sessions]


PROJ = {"key": "/r/app", "name": "app"}
PROJ2 = {"key": "/r/other", "name": "other"}


# ------------------------------------------------------------ v3 store, delta, reuse

def test_index_then_delta_up_to_date_and_append_is_incremental(store):
    emb = FakeEmbedder3()
    table = {("claude", "a"): [chunk(0, "render pipeline timeout", "user"), chunk(1, "fixed the render queue")],
             ("codex", "b"): [chunk(0, "thumbnail colours washed out", "user")]}
    sessions = [sess3("claude", "a", 10, tokens=10, messages=2), sess3("codex", "b", 11, tokens=5, messages=1)]
    docs = sdocs(sessions)
    run = make_run(store, emb, table)
    st = do_run(run, PROJ, docs)
    assert st["state"] == "done" and st["chunks_embedded"] == 3 and st["chunks_reused"] == 0
    d = store.delta("/r/app", docs)
    assert d["state"] == "up_to_date" and d["new"] == {} and d["changed"] == {} and d["removed"] == {}
    assert d["lock"] == {"model": "fake-v3", "provider": "ollama"} and d["last_indexed_at"].endswith("Z")

    # a second run is a no-op: nothing loaded, nothing embedded
    n = len(emb.texts)
    st = do_run(run, PROJ, docs)
    assert st["state"] == "done" and len(emb.texts) == n and st["documents_skipped"] == 2

    # append to session a: delta says stale, the run embeds only the new chunk
    table[("claude", "a")] = table[("claude", "a")] + [chunk(2, "render regression again")]
    sessions[0] = sess3("claude", "a", 12, tokens=14, messages=3)
    docs = sdocs(sessions)
    d = store.delta("/r/app", docs)
    assert d["state"] == "stale" and d["changed"] == {"session": 1} and d["new"] == {}
    assert d["new_chunks_estimate"] >= 1 and d["estimate_seconds"] > 0
    st = do_run(run, PROJ, docs)
    assert len(emb.texts) == n + 1 and "regression" in emb.texts[-1]
    assert st["chunks_embedded"] == 1 and st["chunks_reused"] == 2
    assert store.delta("/r/app", docs)["state"] == "up_to_date"


def test_delta_session_fps_override_and_removed_and_never_indexed(store):
    docs = sdocs([sess3("claude", "a", 10)])
    assert store.delta("/r/app", docs)["state"] == "never_indexed"
    emb = FakeEmbedder3()
    do_run(make_run(store, emb, {("claude", "a"): [chunk(0, "alpha")]}), PROJ, docs)
    did = docs[0]["doc_id"]
    assert store.delta("/r/app", docs, {did: "different"})["changed"] == {"session": 1}
    assert store.delta("/r/app", docs, {("claude", "a"): "different"})["state"] == "stale"
    assert store.delta("/r/app", [])["removed"] == {"session": 1}
    assert store.delta("/r/app", docs, unavailable=True)["state"] == "unavailable"


def test_two_projects_share_chunks_and_full_reindex_keeps_the_other(store):
    emb = FakeEmbedder3()
    shared = "shared skill text about deployment"
    a_docs = [file_doc("s", shared), file_doc("only-a", "text only project a has")]
    b_docs = [file_doc("s", shared)]
    run = make_run(store, emb)
    do_run(run, PROJ, a_docs)
    n = len(emb.texts)
    st = do_run(run, PROJ2, b_docs)
    assert len(emb.texts) == n and st["chunks_embedded"] == 0 and st["chunks_reused"] == 1  # reused across projects
    before = store.counts()
    assert before["chunk_vectors"] == 2 and before["doc_chunks"] == 3

    st = do_run(run, PROJ, a_docs, full=True)
    assert st["state"] == "done" and st["chunks_embedded"] == 1 and st["chunks_reused"] == 1  # B kept the shared vector
    # vectors of A's own chunk were dropped by the full re-index and re-embedded
    assert len(emb.texts) == n + 1 and "only project a" in emb.texts[-1]
    assert store.counts()["chunk_vectors"] == 2
    res = ri.semantic_search(store, emb, "/r/other", shared)
    assert res["state"] == "ready" and res["hits"][0]["doc_id"] == b_docs[0]["doc_id"]


def test_counted_deletion_collects_only_unreferenced(store):
    emb = FakeEmbedder3()
    docs = [file_doc("one", "same text"), file_doc("two", "same text"), file_doc("three", "unique text")]
    # titles differ, so with embeddinggemma prefixes the hashes would differ; this fake has no prefix
    run = make_run(store, emb)
    do_run(run, PROJ, docs)
    assert store.counts()["chunk_vectors"] == 2
    assert store.remove_documents("/r/app", [docs[0]["doc_id"]]) == 1
    assert store.counts()["chunk_vectors"] == 2  # still referenced by doc two
    store.remove_documents("/r/app", [docs[1]["doc_id"]])
    assert store.counts()["chunk_vectors"] == 1
    # a run that no longer discovers a document removes it the same way
    st = do_run(run, PROJ, [])
    assert st["documents_removed"] == 1 and store.counts()["chunk_vectors"] == 0
    assert store.documents("/r/app") == {}


def test_chunk_hash_includes_title_prefix_for_embeddinggemma(store):
    emb = FakeEmbedder3(model="embeddinggemma-2:740m")
    docs = [file_doc("one", "same text"), file_doc("two", "same text")]
    do_run(make_run(store, emb), PROJ, docs)
    assert store.counts()["chunk_vectors"] == 2  # the title is part of what is embedded
    assert sorted(emb.titles) == ["one", "two"]


def test_replacing_a_document_collects_its_old_vectors(store):
    emb = FakeEmbedder3()
    run = make_run(store, emb)
    do_run(run, PROJ, [file_doc("s", "first version text")])
    do_run(run, PROJ, [file_doc("s", "second version text")])
    assert store.counts()["chunk_vectors"] == 1 and store.counts()["doc_chunks"] == 1


def test_text_documents_redacted_chunked_and_images_embedded(store):
    emb = FakeEmbedder3()
    pem = "-----BEGIN PRIVATE KEY-----\n" + ("QUJD" * 200) + "\n-----END PRIVATE KEY-----\nafter the key"
    long_text = " ".join(f"word{i}" for i in range(400))
    docs = [file_doc("secret", f"token {SECRET} here\n{pem}", "markdown"), file_doc("long", long_text, "artifact"),
            image_doc("shot.png", b"png-bytes-1"), image_doc("big.png", b"x")]
    run = make_run(store, emb, images={"shot.png": b"png-bytes-1"})  # big.png unreadable
    st = do_run(run, PROJ, docs)
    joined = "\n".join(emb.texts)
    assert SECRET not in joined and "QUJD" not in joined
    long_rows = store.documents("/r/app")[docs[1]["doc_id"]]
    assert long_rows["chunks"] > 3 and all(len(t) <= 700 for t in emb.texts)
    assert emb.images == [b"png-bytes-1"] and st["documents_unreadable"] == 1
    assert st["documents_done"] == 3
    # images off: not embedded, not counted by delta
    store2 = ri.VectorStore(store.path.with_name("other.db"))
    emb2 = FakeEmbedder3()
    run2 = ri.IndexRun(store2, emb2, loader_for({}), images=False, image_reader=lambda d: b"png-bytes-1")
    do_run(run2, PROJ, docs[2:3])
    assert emb2.images == [] and store2.delta("/r/app", docs[2:3], images=False)["new"] == {}


def test_content_fp_matches_recall_and_text_fp_detects_edit(store):
    emb = FakeEmbedder3()
    table = {("claude", "a"): [chunk(0, f"use {SECRET} now"), chunk(1, "second")]}
    docs = sdocs([sess3("claude", "a", 10)]) + [file_doc("f", "hello world")]
    do_run(make_run(store, emb, table), PROJ, docs)
    rows = store.documents("/r/app")
    assert rows[docs[0]["doc_id"]]["content_fp"] == recall.session_fingerprint(table[("claude", "a")])
    assert rows[docs[1]["doc_id"]]["content_fp"] == ri.text_content_fp("hello world")
    assert ri.text_content_fp("hello world!") != ri.text_content_fp("hello world")


def test_delta_under_two_seconds_for_300_sessions(store):
    emb = FakeEmbedder3()
    sessions = [sess3("claude", f"s{i}", 1 + i % 28, tokens=i + 1, messages=i + 1) for i in range(300)]
    table = {("claude", f"s{i}"): [chunk(0, f"text {i}")] for i in range(300)}
    docs = sdocs(sessions)
    st = do_run(make_run(store, emb, table), PROJ, docs)
    assert st["state"] == "done" and st["documents_done"] == 300
    fps = {(s["agent"], s["id"]): ri.session_cheap_fp(s) for s in sessions}
    t0 = time.perf_counter()
    d = store.delta("/r/app", docs, fps)
    dt_s = time.perf_counter() - t0
    assert d["state"] == "up_to_date" and dt_s < 2.0
    assert emb.probe_calls == 1  # delta embedded nothing


# ------------------------------------------------------------ v3 lock

def test_lock_mismatch_gives_model_changed_and_search_falls_back(store):
    emb = FakeEmbedder3()
    table = {("claude", "a"): [chunk(0, "render pipeline timeout", "user")]}
    sessions = [sess3("claude", "a", 10)]
    docs = sdocs(sessions)
    do_run(make_run(store, emb, table), PROJ, docs)
    lock = store.get_lock("/r/app")
    assert lock["state"] == "ready" and lock["lock"]["ollama_digest"] == "sha256:aaa"
    assert len(lock["lock"]["probe"]) == 32

    sem = ri.make_semantic_v3(store, emb, "/r/app")
    out = recall.search(sessions, loader_for(table), "render timeout", mode="hybrid", semantic=sem)
    assert out["coverage"]["semantic"]["indexed_sessions"] == 1 and out["hits"][0]["match"] in ("both", "semantic")

    new = FakeEmbedder3(model="other-model")
    # delta sees the settings change without any embedding call
    assert store.delta("/r/app", docs, identity=new.identity)["state"] == "model_changed"
    assert new.probe_calls == 0
    run = make_run(store, new, table)
    st = do_run(run, PROJ, docs)
    assert st["state"] == "error" and "other-model" in st["error"]["fix"] and "fake-v3" in st["error"]["message"]
    assert run.events()[-1]["type"] == "error"
    assert store.get_lock("/r/app")["state"] == "model_changed"
    assert store.delta("/r/app", docs)["state"] == "model_changed"
    res = ri.semantic_search(store, new, "/r/app", "render")
    assert res == {"state": "model_changed", "hits": [], "stale": []}
    sem2 = ri.make_semantic_v3(store, new, "/r/app")
    out = recall.search(sessions, loader_for(table), "render timeout", mode="hybrid", semantic=sem2)
    assert out["coverage"]["semantic"]["indexed_sessions"] == 0
    assert out["hits"] and all(h["match"] == "keyword" for h in out["hits"])

    # explicit full re-index with the new model clears it
    st = do_run(make_run(store, new, table), PROJ, docs, full=True)
    assert st["state"] == "done" and store.get_lock("/r/app")["state"] == "ready"
    assert ri.semantic_search(store, new, "/r/app", "render")["state"] == "ready"


def test_digest_and_probe_changes_are_detected_and_check_is_cached(store):
    emb = FakeEmbedder3()
    docs = [file_doc("s", "some text")]
    do_run(make_run(store, emb), PROJ, docs)
    calls = emb.probe_calls
    clock = [0.0]
    guard = ri.LockGuard(store, emb, clock=lambda: clock[0])
    assert guard.state("/r/app") == "ready" and emb.probe_calls == calls + 1
    assert guard.state("/r/app") == "ready" and emb.probe_calls == calls + 1  # cached
    clock[0] = 601
    guard.state("/r/app")
    assert emb.probe_calls == calls + 2  # ttl passed

    emb.digest = "sha256:bbb"
    ok, why = ri.check_lock(emb, store.get_lock("/r/app")["lock"])
    assert not ok and "ollama_digest" in why
    emb.digest = "sha256:aaa"
    emb.dims = 32
    emb.model = "fake-v3"
    lock = dict(store.get_lock("/r/app")["lock"], probe=[1.0] + [0.0] * 31)
    ok, why = ri.check_lock(emb, lock)
    assert not ok and "different vectors" in why
    ok, why = ri.check_lock(emb, dict(store.get_lock("/r/app")["lock"], dims=64))
    assert not ok and "dims" in why


def test_reindex_changed_provider_alias_cannot_reuse_other_projects_vectors(store):
    class Alias(FakeEmbedder3):
        @property
        def identity(self):
            return {**super().identity, "provider": "api", "model": "alias", "format": "openai"}

    old = Alias(model="old-generation", digest=None)
    new = Alias(model="new-generation", digest=None)
    doc = file_doc("shared", "same source text")
    do_run(make_run(store, old), PROJ, [doc])
    do_run(make_run(store, old), {"key": "/r/other"}, [doc])
    guard = ri.LockGuard(store, old)
    assert guard.state(PROJ["key"]) == "ready"
    guard.embedder = new
    run = make_run(store, new, guard=guard)
    assert do_run(run, PROJ, [doc])["state"] == "error"
    assert do_run(run, PROJ, [doc], full=True)["state"] == "done"
    assert new.texts == ["same source text"]
    assert store.counts()["chunk_vectors"] == 2


def test_search_types_filter_and_staleness(store):
    emb = FakeEmbedder3()
    table = {("claude", "a"): [chunk(0, "deploy pipeline notes", "user")]}
    docs = sdocs([sess3("claude", "a", 10)]) + [file_doc("deploy", "deploy pipeline notes", "skill"),
                                                file_doc("plan", "deploy pipeline plan", "artifact")]
    do_run(make_run(store, emb, table), PROJ, docs)
    res = ri.semantic_search(store, emb, "/r/app", "deploy pipeline notes")
    assert {h["doc_type"] for h in res["hits"]} == {"session", "skill", "artifact"}
    res = ri.semantic_search(store, emb, "/r/app", "deploy pipeline notes", types=["skill"])
    assert {h["doc_type"] for h in res["hits"]} == {"skill"} and res["hits"][0]["title"] == "deploy"
    res = ri.semantic_search(store, emb, "/r/app", "deploy pipeline notes", types="skill,artifact".split(","))
    assert {h["doc_type"] for h in res["hits"]} == {"skill", "artifact"}
    # query-time staleness: a file edited since indexing is left out
    current = {docs[1]["doc_id"]: ri.text_content_fp("edited text"), docs[2]["doc_id"]: ri.text_content_fp("deploy pipeline plan")}
    res = ri.semantic_search(store, emb, "/r/app", "deploy pipeline notes", types=["skill", "artifact"],
                             is_current=lambda row: current[row["doc_id"]] == row["content_fp"])
    assert res["stale"] == [docs[1]["doc_id"]] and [h["doc_type"] for h in res["hits"]] == ["artifact"]
    assert ri.semantic_search(store, emb, "/r/never", "x")["state"] == "never_indexed"


def test_v3_search_streams_with_bounded_memory(store, monkeypatch):
    monkeypatch.setattr(ri, "_np", None)
    dim = 8
    rows = {}
    for d in range(40):
        for i in range(60):
            rows[(d, i)] = _hash_vec(f"d{d} c{i}", dim)
    for d in range(40):
        doc = file_doc(f"d{d}", "x")
        hashes = [f"h{d}-{i}" for i in range(60)]
        store.put_document("/r/app", doc, "L", dim, "fp", list(range(60)), hashes,
                           {h: rows[(d, i)] for i, h in enumerate(hashes)})
    q = _hash_vec("d3 c7", dim)
    out = store.search_project("/r/app", "L", q, dim, k=50)
    assert len(out) == 50 and store.last_peak_heap <= 50 and store.last_max_batch <= ri.SCAN_BATCH < 2400
    brute = sorted((sum(a * b for a, b in zip(q, v)) for v in rows.values()), reverse=True)[:5]
    assert [t[2] for t in out[:5]] == pytest.approx(brute, abs=1e-5)


# ------------------------------------------------------------ v3 events

def test_event_order_replay_and_shapes(store):
    emb = FakeEmbedder3()
    table = {("claude", "a"): [chunk(0, "alpha one"), chunk(1, "beta two")]}
    docs = sdocs([sess3("claude", "a", 10)]) + [file_doc("skill1", "a skill about rendering", "skill"),
                                                image_doc("shot.png", b"img1")]
    run = make_run(store, emb, table, images={"shot.png": b"img1"})
    do_run(run, PROJ, docs)
    ev = run.events()
    assert [e["seq"] for e in ev] == list(range(1, len(ev) + 1))
    assert ev[0]["type"] == "start" and ev[0]["totals"]["documents"] == 3
    assert ev[0]["totals"]["by_type"] == {"session": 1, "skill": 1, "image": 1}
    assert ev[-1]["type"] == "done" and ev[-2]["type"] == "progress"
    kinds = [e["type"] for e in ev]
    assert kinds.count("doc") == 3
    for i, e in enumerate(ev):
        if e["type"] == "vector":
            assert ev[i - 1]["type"] == "doc" and len(e["preview"]) == 24
            assert len(e["xy"]) == 2 and all(-1 <= v <= 1 for v in e["xy"])
    first_doc = next(e for e in ev if e["type"] == "doc")
    assert first_doc["title"] == "prompt a" and first_doc["chunks"] == 2 and first_doc["reused"] == 0
    assert set(first_doc) >= {"doc_id", "doc_type", "agent", "title", "chunks", "reused"}
    assert "alpha" not in json.dumps(ev)  # titles only, never content
    done = ev[-1]["summary"]
    assert done["documents"] == 3 and done["chunks_embedded"] == 4 and done["by_type"] == {"session": 1, "skill": 1, "image": 1}
    last_prog = ev[-2]
    assert last_prog["documents_done"] == 3 and last_prog["chunks_embedded"] == 4 and last_prog["tokens"] > 0
    # replay: a client that saw up to seq 3 gets the rest, in order
    assert [e["seq"] for e in run.events(since=3)] == list(range(4, len(ev) + 1))
    assert list(run.stream(since=len(ev) - 1))[0]["type"] == "done"
    assert [e["seq"] for e in run.stream(since=0)] == [e["seq"] for e in ev]
    st = run.status()
    assert st["state"] == "done" and st["seq"] == len(ev) and st["error"] is None


def test_stream_follows_a_live_run(store):
    gate = threading.Event()
    emb = FakeEmbedder3()
    orig = emb.embed_texts

    def slow(texts, kind, titles=None):
        if kind == "document" and texts != [ri.PROBE_TEXT]:
            gate.wait(5)
        return orig(texts, kind, titles)
    emb.embed_texts = slow
    run = make_run(store, emb)
    run.start(PROJ, [file_doc("a", "text a")])
    got = []

    def reader():
        got.extend(run.stream(since=0, poll=0.05))
    t = threading.Thread(target=reader)
    t.start()
    time.sleep(0.2)
    assert any(e["type"] == "start" for e in got)
    with pytest.raises(ri.JobBusy):
        run.start(PROJ, [file_doc("a", "text a")])
    gate.set()
    t.join(10)
    assert got[-1]["type"] == "done" and not t.is_alive()


class _Tick:
    def __init__(self, step):
        self.t = 0.0
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


def test_vector_events_are_sampled_but_counters_exact(store):
    emb = FakeEmbedder3()
    n = 150
    docs = [file_doc(f"d{i}", f"document number {i} about topic{i}") for i in range(n)]
    run = make_run(store, emb, clock=_Tick(0.001))  # 1000 clock calls per second of fake time
    do_run(run, PROJ, docs)
    ev = run.events()
    vec = [e for e in ev if e["type"] == "vector"]
    summary = ev[-1]["summary"]
    assert summary["documents"] == n and summary["chunks_embedded"] == n
    assert 0 < len(vec) < n // 3
    assert summary["vector_events"] == len(vec) and summary["vector_events"] + summary["vector_events_sampled_out"] == n
    dots = {e["doc_id"]: e["xy"] for e in ev if e["type"] == "doc"}
    assert len(dots) == n and all(len(xy) == 2 for xy in dots.values())
    assert dots == {p["doc_id"]: p["xy"] for p in store.project_map(PROJ["key"])}
    # fake-time gap between sent vector events is at least 1/40 s
    # progress events: periodic (250 ms of fake time) and exact
    prog = [e for e in ev if e["type"] == "progress"]
    assert len(prog) >= 2
    assert [p["documents_done"] for p in prog] == sorted(p["documents_done"] for p in prog)
    assert prog[-1]["documents_done"] == n and prog[-1]["chunks_embedded"] == n
    assert prog[-1]["by_type"] == {"skill": n}


def test_xy_is_deterministic_per_lock_and_similar_texts_land_close(tmp_path):
    def run_once(name):
        st = ri.VectorStore(tmp_path / f"{name}.db")
        emb = FakeEmbedder3(dims=64)
        docs = [file_doc("a", "render pipeline timeout queue"), file_doc("b", "render pipeline timeout queues"),
                file_doc("c", "zebra giraffe savanna migration")]
        run = make_run(st, emb, clock=_Tick(1.0))  # one tick a second: every vector event is sent
        do_run(run, PROJ, docs)
        return {e["doc_id"]: e["xy"] for e in run.events() if e["type"] == "vector"}
    one, two = run_once("one"), run_once("two")
    assert len(one) == 3 and one == two
    a, b, c = (one[f"skill:claude:project:{n}"] for n in "abc")
    dist = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])  # noqa: E731
    assert dist(a, b) < dist(a, c)
    # a different lock id gives a different projection of the same vector
    v = _hash_vec("render", 64)
    assert ri.Projector("L1").xy(v) == ri.Projector("L1").xy(v) and ri.Projector("L1").xy(v) != ri.Projector("L2").xy(v)


def test_progress_updates_before_long_session_is_committed(store):
    emb = FakeEmbedder3()
    table = {("claude", "a"): [chunk(idx, f"unique turn {idx}") for idx in range(70)]}
    docs = sdocs([sess3("claude", "a", 10)])
    run = make_run(store, emb, table, clock=_Tick(0.3))
    assert do_run(run, PROJ, docs)["state"] == "done"

    progress = [ev for ev in run.events() if ev["type"] == "progress"]
    assert [(p["chunks_embedded"], p["documents_done"]) for p in progress] == [
        (32, 0), (64, 0), (70, 1), (70, 1),
    ]
    assert store.documents(PROJ["key"])[docs[0]["doc_id"]]["chunks"] == 70


def test_bad_image_does_not_stop_other_documents(store):
    from recall_embed import ImageDecodeError

    class RejectImage(FakeEmbedder3):
        def embed_images(self, images):
            raise ImageDecodeError("Invalid image")

    docs = [image_doc("bad.webp", b"bad"), file_doc("ok", "useful text")]
    st = do_run(make_run(store, RejectImage(), images={"bad.webp": b"bad"}), PROJ, docs)
    assert st["state"] == "done" and st["documents_unreadable"] == 1
    assert set(store.documents(PROJ["key"])) == {docs[1]["doc_id"]}


def test_embed_error_is_reported_and_written_docs_kept(store):
    emb = FakeEmbedder3()
    emb.fail_on = "boom"
    docs = [file_doc("a", "fine text"), file_doc("b", "boom text")]
    run = make_run(store, emb)
    st = do_run(run, PROJ, docs)
    assert st["state"] == "error" and "ollama serve" in st["error"]["message"] and st["error"]["fix"]
    last = run.events()[-1]
    assert last["type"] == "error" and last["message"] and "fix" in last
    assert set(store.documents("/r/app")) == {docs[0]["doc_id"]}
    assert store.get_lock("/r/app")["state"] == "ready"
    # retry after the fix embeds only what is missing
    emb.fail_on = None
    n = len(emb.texts)
    st = do_run(run, PROJ, docs)
    assert st["state"] == "done" and len(emb.texts) == n + 1


# ------------------------------------------------------------ v3 migration

def test_v2_database_migrates_in_place(tmp_path):
    path = tmp_path / "v2.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE sessions (agent TEXT, id TEXT, model TEXT, fingerprint TEXT, chunks INTEGER,
                    indexed_at TEXT, PRIMARY KEY (agent, id))""")
    conn.execute("""CREATE TABLE vectors (agent TEXT, id TEXT, idx INTEGER, model TEXT, dim INTEGER, vec BLOB,
                    PRIMARY KEY (agent, id, idx))""")
    from array import array
    for sid in ("a", "b"):
        conn.execute("INSERT INTO sessions VALUES ('claude', ?, 'm', 'fp', 1, '2026-11-01T00:00:00Z')", (sid,))
        conn.execute("INSERT INTO vectors VALUES ('claude', ?, 0, 'm', 8, ?)", (sid, array("f", _hash_vec(sid, 8)).tobytes()))
    conn.commit()
    conn.close()

    st = ri.VectorStore(path)
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == ri.STORE_VERSION == 3
    # v2 rows still serve v2 callers
    assert st.is_current("claude", "a", "m", 8, "fp")
    assert st.top_k(_hash_vec("a", 8), {("claude", "a")}, "m", 8)
    assert st.stats()["sessions"] == 2
    # the v3 tables exist and start empty
    assert st.counts() == {"locks": 0, "documents": 0, "chunk_vectors": 0, "doc_chunks": 0}
    # a v3 run over session a supersedes its v2 rows; b is untouched
    emb = FakeEmbedder3(dims=8)
    docs = sdocs([sess3("claude", "a", 10)])
    do_run(make_run(st, emb, {("claude", "a"): [chunk(0, "alpha")]}), PROJ, docs)
    assert not st.is_current("claude", "a", "m", 8, "fp") and st.is_current("claude", "b", "m", 8, "fp")
    assert st.migrate_v2() == 1 and st.stats()["sessions"] == 0
    assert st.delta("/r/app", docs)["state"] == "up_to_date"
    # opening again does not change anything
    ri.VectorStore(path)
    assert st.counts()["documents"] == 1


def test_document_helpers():
    s = sess3("claude", "a", 10, tokens=7, messages=3)
    d = ri.session_document(s)
    assert d["doc_id"] == "session:claude:a" and d["type"] == "session" and d["source"] == {"kind": "session", "id": "a"}
    assert d["title"] == "prompt a" and d["cheap_fp"] == ri.session_cheap_fp(s)
    assert ri.session_cheap_fp(sess3("claude", "a", 10, tokens=8, messages=3)) != d["cheap_fp"]
    assert ri.session_cheap_fp(sess3("claude", "a", 11, tokens=7, messages=3)) != d["cheap_fp"]
    assert ri.session_cheap_fp(sess3("claude", "a", 10, tokens=7, messages=4)) != d["cheap_fp"]
    assert ri.split_text("") == [] and ri.split_text("short") == ["short"]
    parts = ri.split_text("word " * 500)
    assert len(parts) > 3 and all(len(p) <= 600 for p in parts)
    assert len(ri.text_chunks("x " * 600 * ri.MAX_DOC_CHUNKS)) == ri.MAX_DOC_CHUNKS


def test_default_text_reader_reads_files_and_caps_size(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("hello skill", encoding="utf-8")
    assert ri.default_text_reader({"source": {"kind": "file", "path": str(f)}}) == "hello skill"
    big = tmp_path / "big.md"
    big.write_bytes(b"a" * (ri.MAX_TEXT_BYTES + 1))
    assert ri.default_text_reader({"source": {"path": str(big)}}) is None
    assert ri.default_text_reader({"source": {"path": str(tmp_path / "missing.md")}}) is None
    assert ri.default_text_reader({"source": {"kind": "text", "text": "rendered"}}) == "rendered"
