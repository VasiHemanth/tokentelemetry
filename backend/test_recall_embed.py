"""Tests for recall_embed: fake loopback servers, no real network."""
import json
import math
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import recall_embed as re_  # noqa: E402
from recall_embed import EmbedError  # noqa: E402

FAKE_KEY = "sk-" + "fake" + "-key-" + "12345"


class Fake:
    """Loopback server. routes: (method, path) -> callable(body, headers) -> (status, obj|str, hdrs)
    or a list of such results consumed in order (last repeats)."""

    def __init__(self):
        self.routes = {}
        self.calls = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = None
                fake.calls.append((self.command, self.path, body, dict(self.headers)))
                route = fake.routes.get((self.command, self.path.split("?")[0]))
                if route is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                if isinstance(route, list):
                    res = route.pop(0) if len(route) > 1 else route[0]
                elif callable(route):
                    res = route(body, self.headers)
                else:
                    res = route
                status, obj, *rest = res
                hdrs = rest[0] if rest else {}
                data = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in hdrs.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _do

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = "http://127.0.0.1:%d" % self.port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def fake():
    f = Fake()
    yield f
    f.close()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(re_, "_sleep", lambda s: slept.append(s))
    return slept


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def vec(n, seed=1.0):
    return [seed + i * 0.01 for i in range(n)]


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def ollama_embed_route(n=768):
    def r(body, h):
        return 200, {"embeddings": [vec(n, 1.0 + i) for i, _ in enumerate(body["input"])]}
    return r


def test_ollama_text_prefixes_truncate_normalize(fake):
    fake.routes[("POST", "/api/embed")] = ollama_embed_route()
    e = re_.OllamaEmbedder(fake.url, "embeddinggemma-2:740m", 256)
    out = e.embed_texts(["hello"], "document", titles=["My Session"])
    assert len(out[0]) == 256 and abs(norm(out[0]) - 1) < 1e-9
    body = fake.calls[-1][2]
    assert body["input"] == ["title: My Session | text: hello"]
    assert body["truncate"] is True and body["model"] == "embeddinggemma-2:740m"
    e.embed_texts(["find it"], "query")
    assert fake.calls[-1][2]["input"] == ["task: search result | query: find it"]
    e.embed_texts(["x"], "document")
    assert fake.calls[-1][2]["input"] == ["title: none | text: x"]


def test_ollama_reports_an_image_decode_error(fake):
    fake.routes[("POST", "/api/embed")] = (400, {"error": "decode image: webp: invalid format"})
    emb = re_.OllamaEmbedder(fake.url, "embeddinggemma-2:740m", 256)
    with pytest.raises(re_.ImageDecodeError):
        emb.embed_images([b"bad image"])
    with pytest.raises(EmbedError) as exc:
        emb.embed_texts(["text"], "query")
    assert not isinstance(exc.value, re_.ImageDecodeError)


def test_ollama_no_prefix_for_other_models(fake):
    fake.routes[("POST", "/api/embed")] = ollama_embed_route(1024)
    e = re_.OllamaEmbedder(fake.url, "nomic-embed-text", 256)
    e.embed_texts(["plain"], "query")
    assert fake.calls[-1][2]["input"] == ["plain"]


def test_ollama_batches_of_32(fake):
    fake.routes[("POST", "/api/embed")] = ollama_embed_route()
    e = re_.OllamaEmbedder(fake.url, "embeddinggemma-2:740m", 128)
    out = e.embed_texts(["t%d" % i for i in range(70)], "document")
    assert len(out) == 70
    sizes = [len(c[2]["input"]) for c in fake.calls if c[1] == "/api/embed"]
    assert sizes == [32, 32, 6]


def test_ollama_image_payload(fake):
    fake.routes[("POST", "/api/embed")] = ollama_embed_route()
    e = re_.OllamaEmbedder(fake.url, "embeddinggemma-2:740m", 256)
    assert e.supports_images
    out = e.embed_images([b"\x89PNG\r\n\x1a\nabc"])
    assert len(out) == 1 and len(out[0]) == 256
    item = fake.calls[-1][2]["input"][0]
    assert list(item.keys()) == ["image"]
    import base64
    assert base64.b64decode(item["image"]) == b"\x89PNG\r\n\x1a\nabc"


def test_ollama_text_only_tag_refuses_images(fake):
    e = re_.OllamaEmbedder(fake.url, "embeddinggemma-2:270m", 256)
    assert not e.supports_images
    with pytest.raises(EmbedError):
        e.embed_images([b"x"])


def test_ollama_not_running():
    e = re_.OllamaEmbedder("http://127.0.0.1:1", "embeddinggemma-2:740m", 256)
    with pytest.raises(EmbedError) as ei:
        e.embed_texts(["x"], "query")
    assert "not running" in ei.value.message and "ollama serve" in ei.value.fix


def test_ollama_model_missing(fake):
    fake.routes[("POST", "/api/embed")] = (404, {"error": "model \"x\" not found, try pulling it first"})
    e = re_.OllamaEmbedder(fake.url, "embeddinggemma-2:740m", 256)
    with pytest.raises(EmbedError) as ei:
        e.embed_texts(["x"], "query")
    assert "not installed" in ei.value.message and "ollama pull" in ei.value.fix


def test_ollama_version_tags_installed(fake):
    fake.routes[("GET", "/api/version")] = (200, {"version": "0.14.2"})
    fake.routes[("GET", "/api/tags")] = (200, {"models": [
        {"name": "embeddinggemma-2:740m", "digest": "sha256:aaa"},
        {"name": "nomic-embed-text:latest", "digest": "sha256:bbb"}]})
    assert re_.version(fake.url) == "0.14.2"
    assert re_.tags(fake.url) == {"embeddinggemma-2:740m": "sha256:aaa",
                                  "nomic-embed-text:latest": "sha256:bbb"}
    assert re_.model_installed(fake.url, "embeddinggemma-2:740m")
    assert re_.model_installed(fake.url, "nomic-embed-text")  # implicit :latest
    assert not re_.model_installed(fake.url, "other:1b")


def ndjson(*objs):
    return "\n".join(json.dumps(o) for o in objs) + "\n"


def test_pull_stream_progress(fake):
    fake.routes[("POST", "/api/pull")] = (200, ndjson(
        {"status": "pulling manifest"},
        {"status": "pulling abc", "digest": "sha256:abc", "total": 200},
        {"status": "pulling abc", "total": 200, "completed": 50},
        {"status": "pulling abc", "total": 200, "completed": 200},
        {"status": "success"}))
    evs = list(re_.pull(fake.url, "embeddinggemma-2:740m"))
    assert evs[0] == {"status": "pulling manifest", "completed": 0, "total": None, "percent": None}
    assert evs[1]["percent"] == 0.0 and evs[1]["total"] == 200
    assert evs[2]["percent"] == 25.0
    assert evs[3]["percent"] == 100.0
    assert evs[-1]["status"] == "success"
    assert fake.calls[-1][2] == {"model": "embeddinggemma-2:740m", "stream": True}


def test_pull_http_412_too_old(fake):
    fake.routes[("POST", "/api/pull")] = (412, {"error": "this model requires a newer version of Ollama"})
    fake.routes[("GET", "/api/version")] = (200, {"version": "0.9.0"})
    with pytest.raises(EmbedError) as ei:
        list(re_.pull(fake.url, "embeddinggemma-2:740m"))
    assert ei.value.message == "Ollama 0.9.0 is too old for embeddinggemma-2:740m"
    assert "Update Ollama" in ei.value.fix


def test_pull_stream_error_newer_version(fake):
    fake.routes[("POST", "/api/pull")] = (200, ndjson(
        {"status": "pulling manifest"},
        {"error": "pull model manifest: 412: this model requires a newer version of Ollama"}))
    fake.routes[("GET", "/api/version")] = (200, {"version": "0.9.0"})
    with pytest.raises(EmbedError) as ei:
        list(re_.pull(fake.url, "m"))
    assert "too old" in ei.value.message


def test_pull_other_stream_error(fake):
    fake.routes[("POST", "/api/pull")] = (200, ndjson({"error": "pull model manifest: file does not exist"}))
    with pytest.raises(EmbedError) as ei:
        list(re_.pull(fake.url, "nope"))
    assert "file does not exist" in ei.value.message


# ---------------------------------------------------------------------------
# API formats
# ---------------------------------------------------------------------------

def test_openai_format_dimensions_and_model(fake):
    def r(body, h):
        return 200, {"object": "list", "model": "text-embedding-3-small-2024",
                     "data": [{"object": "embedding", "index": i, "embedding": vec(256, i + 1)}
                              for i in reversed(range(len(body["input"])))]}
    fake.routes[("POST", "/v1/embeddings")] = r
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY)
    out = e.embed_texts(["a", "b"], "document")
    body = fake.calls[-1][2]
    assert body == {"model": "text-embedding-3-small", "input": ["a", "b"], "dimensions": 256}
    assert fake.calls[-1][3]["Authorization"] == "Bearer " + FAKE_KEY
    # reordered by index
    assert out[0] != out[1]
    assert all(abs(norm(v) - 1) < 1e-9 for v in out)
    assert e.lock_evidence()["returned_model"] == "text-embedding-3-small-2024"


def test_openai_no_dimensions_param_for_other_models_and_strict(fake):
    fake.routes[("POST", "/v1/embeddings")] = lambda b, h: (200, {
        "model": "m", "data": [{"index": 0, "embedding": vec(1024)}]})
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "mistral-embed", 256, FAKE_KEY)
    with pytest.raises(EmbedError) as ei:
        e.embed_texts(["a"], "document")
    assert "dimensions" in ei.value.fix and "1024" in ei.value.fix
    assert "dimensions" not in fake.calls[-1][2]
    e2 = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "mistral-embed", 1024, FAKE_KEY)
    assert len(e2.embed_texts(["a"], "document")[0]) == 1024


def test_openai_never_images(fake):
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY,
                        images=True)
    assert not e.supports_images
    with pytest.raises(EmbedError):
        e.embed_images([b"x"])


def test_gemini_format_text_and_image(fake):
    def r(body, h):
        return 200, {"embeddings": [{"values": vec(768, 1 + i)} for i, _ in enumerate(body["requests"])]}
    fake.routes[("POST", "/v1beta/models/gemini-embedding-2:batchEmbedContents")] = r
    e = re_.ApiEmbedder("gemini", fake.url + "/v1beta/models/gemini-embedding-2:embedContent",
                        "gemini-embedding-2", 256, FAKE_KEY, images=True)
    assert e.supports_images
    out = e.embed_texts(["hi", "there"], "query")
    assert len(out) == 2 and len(out[0]) == 256 and abs(norm(out[0]) - 1) < 1e-9
    c = fake.calls[-1]
    assert c[3]["X-Goog-Api-Key"] == FAKE_KEY and "Authorization" not in c[3]
    assert c[2]["requests"][0]["output_dimensionality"] == 256
    assert c[2]["requests"][0]["content"]["parts"] == [{"text": "hi"}]
    out = e.embed_images([b"\xff\xd8\xff\xe0jpeg"])
    part = fake.calls[-1][2]["requests"][0]["content"]["parts"][0]
    assert part["inline_data"]["mime_type"] == "image/jpeg" and part["inline_data"]["data"]
    assert len(out) == 1


def test_gemini_images_batched_by_six(fake):
    fake.routes[("POST", "/v1beta/models/g:batchEmbedContents")] = lambda b, h: (
        200, {"embeddings": [{"values": vec(128)} for _ in b["requests"]]})
    e = re_.ApiEmbedder("gemini", fake.url + "/v1beta/models/g:embedContent", "g", 128, FAKE_KEY, images=True)
    assert len(e.embed_images([b"\x89PNG\r\n\x1a\n%d" % i for i in range(13)])) == 13
    assert [len(c[2]["requests"]) for c in fake.calls] == [6, 6, 1]


def test_voyage_format_input_type_and_images(fake):
    def r(body, h):
        return 200, {"model": "voyage-multimodal-3.5",
                     "data": [{"index": i, "embedding": vec(1024, i + 1)} for i in range(len(body["inputs"]))]}
    fake.routes[("POST", "/v1/multimodalembeddings")] = r
    e = re_.ApiEmbedder("voyage", fake.url + "/v1/multimodalembeddings", "voyage-multimodal-3.5", 256,
                        FAKE_KEY, images=True)
    out = e.embed_texts(["q"], "query")
    b = fake.calls[-1][2]
    assert b["input_type"] == "query"
    assert b["inputs"] == [{"content": [{"type": "text", "text": "q"}]}]
    assert len(out[0]) == 256 and abs(norm(out[0]) - 1) < 1e-9
    e.embed_texts(["d"], "document")
    assert fake.calls[-1][2]["input_type"] == "document"
    e.embed_images([b"\x89PNG\r\n\x1a\nxx"])
    piece = fake.calls[-1][2]["inputs"][0]["content"][0]
    assert piece["type"] == "image_base64" and piece["image_base64"].startswith("data:image/png;base64,")
    assert fake.calls[-1][3]["Authorization"] == "Bearer " + FAKE_KEY
    assert e.lock_evidence()["returned_model"] == "voyage-multimodal-3.5"


# ---------------------------------------------------------------------------
# Retries and errors
# ---------------------------------------------------------------------------

def test_retry_429_then_ok(fake, no_sleep):
    fake.routes[("POST", "/v1/embeddings")] = [
        (429, {"error": {"message": "slow down"}}),
        (200, {"model": "m", "data": [{"index": 0, "embedding": vec(1536)}]}),
    ]
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY)
    assert len(e.embed_texts(["a"], "document")) == 1
    assert len(fake.calls) == 2 and len(no_sleep) == 1


def test_retry_5xx_gives_up_after_three_retries(fake, no_sleep):
    fake.routes[("POST", "/v1/embeddings")] = (503, {"error": "down"})
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY)
    with pytest.raises(EmbedError) as ei:
        e.embed_texts(["a"], "document")
    assert "server error" in ei.value.message
    assert len(fake.calls) == 4 and no_sleep == [1, 2, 4]


def test_429_exhausted_message(fake):
    fake.routes[("POST", "/v1/embeddings")] = (429, {"error": "x"})
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY)
    with pytest.raises(EmbedError) as ei:
        e.embed_texts(["a"], "document")
    assert "rate limiting" in ei.value.message


@pytest.mark.parametrize("status", [401, 403, 400])
def test_no_retry_on_auth_or_bad_request(fake, status, no_sleep):
    fake.routes[("POST", "/v1/embeddings")] = (status, {"error": {"message": "nope " + FAKE_KEY}})
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY)
    with pytest.raises(EmbedError) as ei:
        e.embed_texts(["a"], "document")
    assert len(fake.calls) == 1 and no_sleep == []
    assert FAKE_KEY not in ei.value.message and FAKE_KEY not in ei.value.fix
    if status in (401, 403):
        assert "API key" in ei.value.message and "API key" in ei.value.fix


def test_redirect_not_followed(fake):
    fake.routes[("POST", "/v1/embeddings")] = (302, "", {"Location": "http://127.0.0.1:1/x"})
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY)
    with pytest.raises(EmbedError):
        e.embed_texts(["a"], "document")
    assert len(fake.calls) == 1


def test_nan_vector_rejected():
    with pytest.raises(EmbedError):
        re_._finish([float("nan"), 1.0], 2)
    with pytest.raises(EmbedError):
        re_._finish([0.0, 0.0], 2)


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------

def test_probe_text_exact():
    assert re_.PROBE_TEXT == "TokenTelemetry recall probe: the quick brown fox checks the index model."


class FakeOllamaState:
    def __init__(self, fake, digest="sha256:aaa", seed=1.0):
        self.digest = digest
        self.seed = seed
        fake.routes[("GET", "/api/tags")] = lambda b, h: (
            200, {"models": [{"name": "embeddinggemma-2:740m", "digest": self.digest}]})
        fake.routes[("POST", "/api/embed")] = lambda b, h: (
            200, {"embeddings": [vec(768, self.seed) for _ in b["input"]]})


def ollama_embedder(fake, dims=256):
    return re_.OllamaEmbedder(fake.url, "embeddinggemma-2:740m", dims)


def test_make_lock_ollama(fake):
    FakeOllamaState(fake)
    lock = re_.make_lock(ollama_embedder(fake))
    assert lock["provider"] == "ollama" and lock["model"] == "embeddinggemma-2:740m"
    assert lock["endpoint_host"] == "127.0.0.1:%d" % fake.port
    assert lock["dims"] == 256 and lock["ollama_digest"] == "sha256:aaa"
    assert lock["returned_model"] is None and len(lock["probe"]) == 256 and lock["created_at"]
    probe_call = [c for c in fake.calls if c[1] == "/api/embed"][0]
    assert probe_call[2]["input"] == ["title: none | text: " + re_.PROBE_TEXT]


def test_lock_id_stable_and_ignores_probe(fake):
    FakeOllamaState(fake)
    lock = re_.make_lock(ollama_embedder(fake))
    other = dict(lock, probe=[0.0], created_at="x")
    assert re_.lock_id(lock) == re_.lock_id(other)
    assert re_.lock_id(lock) != re_.lock_id(dict(lock, dims=128))
    assert re_.lock_id(lock) != re_.lock_id(dict(lock, ollama_digest="sha256:zzz"))


def test_check_lock_ok(fake):
    FakeOllamaState(fake)
    e = ollama_embedder(fake)
    assert re_.check_lock(re_.make_lock(e), e) == {"ok": True, "reason": ""}


def test_check_lock_digest_changed(fake):
    st = FakeOllamaState(fake)
    e = ollama_embedder(fake)
    lock = re_.make_lock(e)
    st.digest = "sha256:bbb"
    r = re_.check_lock(lock, e)
    assert not r["ok"] and "updated" in r["reason"]


def test_check_lock_dims_and_model_changed(fake):
    FakeOllamaState(fake)
    lock = re_.make_lock(ollama_embedder(fake, 256))
    r = re_.check_lock(lock, ollama_embedder(fake, 128))
    assert not r["ok"] and "dimensions" in r["reason"]
    e2 = re_.OllamaEmbedder(fake.url, "embeddinggemma-2:440m", 256)
    r = re_.check_lock(lock, e2)
    assert not r["ok"] and "model" in r["reason"]


def test_check_lock_probe_drift(fake):
    st = FakeOllamaState(fake)
    e = ollama_embedder(fake)
    lock = re_.make_lock(e)
    st.seed = -3.0  # different direction, same digest
    fake.routes[("POST", "/api/embed")] = lambda b, h: (
        200, {"embeddings": [[(-1) ** i * (1 + i * 0.5) for i in range(768)] for _ in b["input"]]})
    r = re_.check_lock(lock, e)
    assert not r["ok"] and "drifted" in r["reason"]


def test_check_lock_api_returned_model(fake):
    state = {"model": "m-v1"}
    fake.routes[("POST", "/v1/embeddings")] = lambda b, h: (200, {
        "model": state["model"], "data": [{"index": 0, "embedding": vec(1536)}]})
    e = re_.ApiEmbedder("openai", fake.url + "/v1/embeddings", "text-embedding-3-small", 256, FAKE_KEY)
    lock = re_.make_lock(e)
    assert lock["returned_model"] == "m-v1" and lock["ollama_digest"] is None
    assert re_.check_lock(lock, e)["ok"]
    state["model"] = "m-v2"
    r = re_.check_lock(lock, e)
    assert not r["ok"] and "different model" in r["reason"]


def test_check_lock_unreachable_raises_not_mismatch(fake):
    FakeOllamaState(fake)
    lock = re_.make_lock(ollama_embedder(fake))
    dead = re_.OllamaEmbedder("http://127.0.0.1:1", "embeddinggemma-2:740m", 256)
    # same model, other host: reported as endpoint change before any network call
    assert not re_.check_lock(lock, dead)["ok"]
    fake.close()
    with pytest.raises(EmbedError):
        re_.check_lock(lock, ollama_embedder(fake))


def test_lock_cache_hit_and_expiry(fake):
    st = FakeOllamaState(fake)
    e = ollama_embedder(fake)
    lock = re_.make_lock(e)
    now = [1000.0]
    cache = re_.LockCache(clock=lambda: now[0])
    assert re_.check_lock(lock, e, cache, "proj")["ok"]
    n = len(fake.calls)
    st.digest = "sha256:changed"
    assert re_.check_lock(lock, e, cache, "proj")["ok"]  # served from cache
    assert len(fake.calls) == n
    now[0] += 599
    assert re_.check_lock(lock, e, cache, "proj")["ok"]
    now[0] += 2  # past 10 minutes
    assert not re_.check_lock(lock, e, cache, "proj")["ok"]
    assert len(fake.calls) > n
    # another project is a separate key
    st.digest = "sha256:aaa"
    assert re_.check_lock(lock, e, cache, "other")["ok"]


# ---------------------------------------------------------------------------
# Secrets and factory
# ---------------------------------------------------------------------------

def test_secrets_roundtrip_and_mode(tmp_path):
    assert not re_.has_api_key(tmp_path) and re_.load_api_key(tmp_path) == ""
    re_.save_api_key(tmp_path, FAKE_KEY)
    assert re_.load_api_key(tmp_path) == FAKE_KEY and re_.has_api_key(tmp_path)
    p = tmp_path / "recall_secrets.json"
    if os.name == "posix":
        assert (p.stat().st_mode & 0o777) == 0o600
    re_.save_api_key(tmp_path, FAKE_KEY + "2")  # overwrite keeps mode
    if os.name == "posix":
        assert (p.stat().st_mode & 0o777) == 0o600
    assert [f.name for f in tmp_path.iterdir()] == ["recall_secrets.json"]
    re_.save_api_key(tmp_path, "")
    assert not re_.has_api_key(tmp_path)


def test_secrets_creates_missing_dir(tmp_path):
    d = tmp_path / "nested" / "data"
    re_.save_api_key(d, FAKE_KEY)
    assert re_.load_api_key(d) == FAKE_KEY


def test_key_not_in_repr_or_errors(fake, tmp_path):
    re_.save_api_key(tmp_path, FAKE_KEY)
    sem = {"provider": "api", "dims": 256, "images": False,
           "api": {"format": "openai", "endpoint": fake.url + "/v1/embeddings",
                   "model": "text-embedding-3-small"}}
    e = re_.make_embedder(sem, tmp_path)
    assert isinstance(e, re_.ApiEmbedder)
    assert FAKE_KEY not in repr(e) and FAKE_KEY not in str(e)
    assert FAKE_KEY not in json.dumps(e.identity)
    assert FAKE_KEY not in json.dumps(re_.EmbedError("x", "y").to_dict())


def test_make_embedder_ollama_defaults(tmp_path):
    e = re_.make_embedder({"provider": "ollama", "dims": 128, "images": True,
                           "ollama": {"url": "http://127.0.0.1:11434", "model": "embeddinggemma-2:740m"}},
                          tmp_path)
    assert isinstance(e, re_.OllamaEmbedder) and e.dims == 128 and e.supports_images
    assert e.identity["endpoint_host"] == "127.0.0.1:11434"
    e = re_.make_embedder({"provider": "ollama", "images": False, "ollama": {}}, tmp_path)
    assert not e.supports_images and e.dims == 256


def test_make_embedder_validation(tmp_path):
    def api(endpoint):
        return {"provider": "api", "dims": 256, "api": {"format": "openai", "endpoint": endpoint,
                                                        "model": "text-embedding-3-small"}}
    with pytest.raises(EmbedError):
        re_.make_embedder(api("http://api.example.com/v1/embeddings"), tmp_path)
    with pytest.raises(EmbedError):
        re_.make_embedder(api("ftp://x/y"), tmp_path)
    with pytest.raises(EmbedError):
        re_.make_embedder(api(""), tmp_path)
    # https needs a key
    with pytest.raises(EmbedError) as ei:
        re_.make_embedder(api("https://api.example.com/v1/embeddings"), tmp_path)
    assert "API key" in ei.value.message
    re_.save_api_key(tmp_path, FAKE_KEY)
    assert re_.make_embedder(api("https://api.example.com/v1/embeddings"), tmp_path).format == "openai"
    # loopback http works without a key
    re_.save_api_key(tmp_path, "")
    assert re_.make_embedder(api("http://localhost:1234/v1/embeddings"), tmp_path)
    with pytest.raises(EmbedError):
        re_.make_embedder({"provider": "ollama", "ollama": {"url": "http://192.0.2.5:11434"}}, tmp_path)
    with pytest.raises(EmbedError):
        re_.make_embedder({"provider": "nope"}, tmp_path)
    with pytest.raises(EmbedError):
        re_.make_embedder({"provider": "api", "api": {"format": "weird", "endpoint": "https://x.example.com"}},
                          tmp_path)


def test_api_key_with_control_chars_raises_embed_error_without_the_key():
    secret = "sk-" + "SECRET" + "\nfoo"
    e = re_.ApiEmbedder("openai", "http://127.0.0.1:9/v1/embeddings", "text-embedding-3-small", 8, secret)
    with pytest.raises(EmbedError) as ei:
        e.embed_texts(["hello"])
    assert "SECRET" not in str(ei.value) and "foo" not in str(ei.value)
    assert "SECRET" not in str(getattr(ei.value, "fix", ""))
