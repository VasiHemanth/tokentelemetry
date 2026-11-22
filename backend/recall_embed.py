"""Embedding providers and the same-model lock for project recall (spec v3, sections 2 and 3).

Pure library: urllib only, no settings store, no routes. Callers pass the
`semantic` settings dict and the data directory.

Unverified against a live server (see docs/design/recall-embedding-runtime.md):
  * the Ollama image payload ({"image": "<base64>"} items in /api/embed input),
  * the Gemini embedContent / batchEmbedContents response shape
    (read as embeddings[].values) and whether it ever returns a model name,
  * the Voyage multimodalembeddings request for images (image_base64 as a data
    URL) and whether truncating its vectors client-side is Matryoshka-safe.
The OpenAI shape and the Ollama text, tags, version and pull shapes follow the
published docs.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import math
import os
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlparse

PROBE_TEXT = "TokenTelemetry recall probe: the quick brown fox checks the index model."
PROBE_COSINE_MIN = 0.999
LOCK_CACHE_TTL = 600.0
OLLAMA_BATCH = 32
API_BATCH = 32
GEMINI_IMAGE_BATCH = 6
MAX_RETRIES = 3
SECRETS_FILE = "recall_secrets.json"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

# Patched out in tests so retries do not really sleep.
_sleep = time.sleep


class EmbedError(Exception):
    """A failure with a plain-English message and an actionable fix."""

    def __init__(self, message: str, fix: str = ""):
        super().__init__(message)
        self.message = message
        self.fix = fix

    def to_dict(self) -> Dict[str, str]:
        return {"message": self.message, "fix": self.fix}


class ImageDecodeError(EmbedError):
    """The provider rejected one document's image bytes."""


class BadVectorError(EmbedError):
    """The provider answered, but a vector is unusable (all zero, NaN).

    A content problem with one input, not a provider outage: callers skip the
    input and keep going instead of failing a whole index run.
    """


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: an API key must not travel to another host."""

    def redirect_request(self, *a, **k):  # type: ignore[override]
        return None


def _is_loopback(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return host in LOOPBACK_HOSTS


class _HttpError(Exception):
    def __init__(self, status: int, body: str, retry_after: Optional[float] = None):
        super().__init__("HTTP %s" % status)
        self.status = status
        self.body = body
        self.retry_after = retry_after


def _open(method: str, url: str, body: Optional[bytes], headers: Dict[str, str], timeout: float):
    handlers: List[Any] = [_NoRedirect()]
    if _is_loopback(url):
        handlers.append(urllib.request.ProxyHandler({}))  # never route loopback via env proxies
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            text = e.read(65536).decode("utf-8", "replace")
        except Exception:
            text = ""
        ra = None
        try:
            hdr = e.headers.get("Retry-After") if e.headers else None
            ra = float(hdr) if hdr else None
        except (TypeError, ValueError):
            ra = None
        raise _HttpError(e.code, text, ra)


def _json_request(method: str, url: str, payload: Optional[dict] = None,
                  headers: Optional[Dict[str, str]] = None, timeout: float = 60.0,
                  retries: int = MAX_RETRIES) -> Any:
    """JSON request with retry on 429/5xx. Never retries other 4xx."""
    h = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    attempt = 0
    while True:
        try:
            with _open(method, url, data, h, timeout) as r:
                raw = r.read()
            try:
                return json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                raise _HttpError(502, "response was not JSON")
        except _HttpError as e:
            if (e.status == 429 or e.status >= 500) and attempt < retries:
                delay = e.retry_after if e.retry_after is not None else 2 ** attempt
                _sleep(min(max(delay, 0.0), 30.0))
                attempt += 1
                continue
            raise


def _body_msg(body: str) -> str:
    """Short, single-line excerpt of a provider error body."""
    try:
        j = json.loads(body)
        if isinstance(j, dict):
            err = j.get("error")
            if isinstance(err, dict):
                err = err.get("message") or err.get("status")
            if isinstance(err, str) and err:
                return err[:300]
            if isinstance(j.get("message"), str):
                return j["message"][:300]
    except ValueError:
        pass
    return " ".join(body.split())[:300]


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def _finish(vec: Any, dims: int, strict: bool = False) -> List[float]:
    """Truncate to dims, then L2 normalize. strict: native size must equal dims."""
    if not isinstance(vec, list) or not vec:
        raise EmbedError("The embedding server returned an empty vector.",
                         "Check the model name; it may not be an embedding model.")
    try:
        v = [float(x) for x in vec]
    except (TypeError, ValueError):
        raise EmbedError("The embedding server returned a malformed vector.",
                         "Check the model name and endpoint.")
    n = len(v)
    if n < dims or (strict and n != dims):
        raise EmbedError(
            "This model returns %d-number vectors but the index is set to %d." % (n, dims),
            "Set the dimensions to %d in recall settings." % n)
    v = v[:dims]
    if any(not math.isfinite(x) for x in v):
        raise BadVectorError("The model returned invalid numbers (NaN).",
                             "This can happen with half-precision builds; use a different model build.")
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0.0:
        raise BadVectorError("The model returned an all-zero vector.", "Try a different model.")
    return [x / norm for x in v]


def cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _chunks(seq: List[Any], n: int) -> Iterator[List[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _mime(img: bytes) -> str:
    if img[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if img[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if img[:4] == b"RIFF" and img[8:12] == b"WEBP":
        return "image/webp"
    if img[:4] == b"GIF8":
        return "image/gif"
    return "image/png"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


# ---------------------------------------------------------------------------
# Embedders
# ---------------------------------------------------------------------------

class Embedder:
    provider = ""
    format = ""
    supports_images = False

    def __init__(self, model: str, dims: int, endpoint: str):
        self.model = model
        self.dims = int(dims)
        self.endpoint = endpoint
        self._returned_model: Optional[str] = None

    @property
    def endpoint_host(self) -> str:
        return urlparse(self.endpoint).netloc

    @property
    def identity(self) -> Dict[str, Any]:
        return {"provider": self.provider, "model": self.model,
                "endpoint_host": self.endpoint_host, "dims": self.dims, "format": self.format,
                "endpoint_id": hashlib.sha256(self.endpoint.encode()).hexdigest()}

    def __repr__(self) -> str:  # never includes secrets
        return "<%s model=%s host=%s dims=%d>" % (
            type(self).__name__, self.model, self.endpoint_host, self.dims)

    __str__ = __repr__

    def embed_texts(self, texts: List[str], kind: str = "document",
                    titles: Optional[List[Optional[str]]] = None) -> List[List[float]]:
        raise NotImplementedError

    def format_document(self, text: str, title: Optional[str]) -> str:
        """The exact string embedded for a document chunk. The index hashes
        this, so it must match what embed_texts sends."""
        return text

    def embed_images(self, images: List[bytes]) -> List[List[float]]:
        raise EmbedError("This provider does not embed images.",
                         "Turn off image indexing or pick a multimodal model.")

    def lock_evidence(self) -> Dict[str, Optional[str]]:
        raise NotImplementedError


class OllamaEmbedder(Embedder):
    provider = "ollama"
    format = "ollama"

    def __init__(self, url: str, model: str, dims: int, images: bool = True):
        super().__init__(model, dims, url.rstrip("/"))
        self.url = url.rstrip("/")
        low = model.lower()
        text_only = any(t in low for t in ("270m", "570m"))
        self.supports_images = bool(images) and not text_only

    @property
    def uses_gemma_prefix(self) -> bool:
        return "embeddinggemma" in self.model.lower()

    def format_document(self, text: str, title: Optional[str]) -> str:
        if not self.uses_gemma_prefix:
            return text
        return "title: %s | text: %s" % (title or "none", text)

    def _prefix(self, text: str, kind: str, title: Optional[str]) -> str:
        if not self.uses_gemma_prefix:
            return text
        if kind == "query":
            return "task: search result | query: %s" % text
        return self.format_document(text, title)

    def _embed(self, inputs: List[Any]) -> List[List[float]]:
        out: List[List[float]] = []
        for batch in _chunks(inputs, OLLAMA_BATCH):
            try:
                j = _json_request("POST", self.url + "/api/embed",
                                  {"model": self.model, "input": batch, "truncate": True},
                                  timeout=300.0)
            except _HttpError as e:
                if e.status == 400 and isinstance(batch[0], dict) and "decode image" in e.body.lower():
                    raise ImageDecodeError("Ollama could not decode this image.") from e
                raise _ollama_error(e, self.url, self.model)
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                raise _ollama_down(self.url)
            embs = j.get("embeddings") if isinstance(j, dict) else None
            if not isinstance(embs, list) or len(embs) != len(batch):
                raise EmbedError("Ollama returned an unexpected embedding response.",
                                 "Update Ollama and try again.")
            out.extend(_finish(v, self.dims) for v in embs)
        return out

    def embed_texts(self, texts, kind="document", titles=None):
        titles = titles or [None] * len(texts)
        return self._embed([self._prefix(t, kind, ti) for t, ti in zip(texts, titles)])

    def embed_images(self, images):
        if not self.supports_images:
            return super().embed_images(images)
        return self._embed([{"image": _b64(b)} for b in images])

    def lock_evidence(self):
        return {"ollama_digest": digest_for(tags(self.url), self.model), "returned_model": None}


class ApiEmbedder(Embedder):
    provider = "api"

    def __init__(self, fmt: str, endpoint: str, model: str, dims: int,
                 api_key: Optional[str], images: bool = False):
        if fmt not in ("openai", "gemini", "voyage"):
            raise EmbedError("Unknown API format %r." % fmt, "Use openai, gemini or voyage.")
        super().__init__(model, dims, endpoint)
        self.format = fmt
        self._key = api_key or ""
        self.supports_images = bool(images) and fmt in ("gemini", "voyage")

    def _headers(self) -> Dict[str, str]:
        if not self._key:
            return {}
        if self.format == "gemini":
            return {"x-goog-api-key": self._key}
        return {"Authorization": "Bearer " + self._key}

    def _scrub(self, s: str) -> str:
        return s.replace(self._key, "***") if self._key else s

    @property
    def _strict_dims(self) -> bool:
        """True when the provider has no documented way to shrink vectors."""
        if self.format in ("gemini", "voyage"):
            return False
        return not self.model.lower().startswith("text-embedding-3")

    def _post(self, url: str, payload: dict) -> Any:
        try:
            return _json_request("POST", url, payload, self._headers(), timeout=120.0)
        except _HttpError as e:
            raise self._http_error(e)
        except (urllib.error.URLError, OSError, TimeoutError):
            raise EmbedError("Could not reach the embedding API at %s." % self.endpoint_host,
                             "Check the endpoint URL and your network connection.")
        except (ValueError, http.client.HTTPException):
            # http.client errors can quote header values; never pass them on.
            raise EmbedError("The embedding API request could not be sent.",
                             "Check the API key and endpoint URL in recall settings.") from None

    def _http_error(self, e: _HttpError) -> EmbedError:
        detail = self._scrub(_body_msg(e.body))
        s = e.status
        if s in (401, 403):
            return EmbedError("The embedding API rejected the API key (HTTP %d)." % s,
                              "Check the API key in recall settings.")
        if s == 429:
            return EmbedError("The embedding API is rate limiting requests.",
                              "Wait a minute and resume; indexing continues where it stopped.")
        if s == 413:
            return EmbedError("A document was too large for the embedding API.",
                              "Try again; oversized inputs are skipped or shortened.")
        if s == 404:
            return EmbedError("The embedding API did not find that model or endpoint. %s" % detail,
                              "Check the endpoint URL and model name in recall settings.")
        if s >= 500:
            return EmbedError("The embedding API had a server error (HTTP %d)." % s,
                              "Try again later.")
        return EmbedError("The embedding API rejected the request (HTTP %d). %s" % (s, detail),
                          "Check the model name, dimensions and endpoint in recall settings.")

    def _note_model(self, name: Any) -> None:
        if isinstance(name, str) and name:
            self._returned_model = name

    def _fin(self, v: Any) -> List[float]:
        return _finish(v, self.dims, strict=self._strict_dims)

    def embed_texts(self, texts, kind="document", titles=None):
        out: List[List[float]] = []
        for batch in _chunks(list(texts), API_BATCH):
            out.extend(self._call(batch, kind, text=True))
        return out

    def embed_images(self, images):
        if not self.supports_images:
            return super().embed_images(images)
        out: List[List[float]] = []
        size = GEMINI_IMAGE_BATCH if self.format == "gemini" else API_BATCH
        for batch in _chunks(list(images), size):
            out.extend(self._call(batch, "document", text=False))
        return out

    def _call(self, batch: List[Any], kind: str, text: bool) -> List[List[float]]:
        if self.format == "openai":
            payload: Dict[str, Any] = {"model": self.model, "input": batch}
            if self.model.lower().startswith("text-embedding-3"):
                payload["dimensions"] = self.dims
            j = self._post(self.endpoint, payload)
            data = j.get("data") if isinstance(j, dict) else None
            if not isinstance(data, list) or len(data) != len(batch):
                raise self._bad_shape()
            self._note_model(j.get("model"))
            data = sorted(data, key=lambda d: d.get("index", 0) if isinstance(d, dict) else 0)
            return [self._fin(d.get("embedding") if isinstance(d, dict) else None) for d in data]

        if self.format == "gemini":
            reqs = []
            for item in batch:
                part = {"text": item} if text else {
                    "inline_data": {"mime_type": _mime(item), "data": _b64(item)}}
                reqs.append({"model": "models/" + self.model.split("/")[-1],
                             "content": {"parts": [part]},
                             "output_dimensionality": self.dims})
            j = self._post(self._gemini_batch_url(), {"requests": reqs})
            embs = j.get("embeddings") if isinstance(j, dict) else None
            if not isinstance(embs, list) or len(embs) != len(batch):
                raise self._bad_shape()
            self._note_model(j.get("model") or j.get("modelVersion"))
            return [self._fin(e.get("values") if isinstance(e, dict) else None) for e in embs]

        # voyage
        inputs = []
        for item in batch:
            if text:
                inputs.append({"content": [{"type": "text", "text": item}]})
            else:
                inputs.append({"content": [{"type": "image_base64",
                                            "image_base64": "data:%s;base64,%s" % (_mime(item), _b64(item))}]})
        j = self._post(self.endpoint, {"inputs": inputs, "model": self.model,
                                       "input_type": "query" if kind == "query" else "document"})
        data = j.get("data") if isinstance(j, dict) else None
        if not isinstance(data, list) or len(data) != len(batch):
            raise self._bad_shape()
        self._note_model(j.get("model"))
        data = sorted(data, key=lambda d: d.get("index", 0) if isinstance(d, dict) else 0)
        return [self._fin(d.get("embedding") if isinstance(d, dict) else None) for d in data]

    def _bad_shape(self) -> EmbedError:
        return EmbedError("The embedding API returned an unexpected response.",
                          "Check that the API format matches the endpoint.")

    def _gemini_batch_url(self) -> str:
        ep = self.endpoint
        if ep.endswith(":batchEmbedContents"):
            return ep
        if ep.endswith(":embedContent"):
            return ep[: -len(":embedContent")] + ":batchEmbedContents"
        return "%s/models/%s:batchEmbedContents" % (ep.rstrip("/"), self.model.split("/")[-1])

    def lock_evidence(self):
        return {"ollama_digest": None, "returned_model": self._returned_model}


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

def _ollama_down(url: str) -> EmbedError:
    return EmbedError("Ollama is not running at %s." % url,
                      "Start it with `ollama serve`, or install it from ollama.com.")


def _ollama_error(e: _HttpError, url: str, model: str) -> EmbedError:
    body = e.body or ""
    if e.status == 412 or "newer version" in body.lower():
        return _too_old(url, model)
    if e.status == 404 or "not found" in body.lower():
        return EmbedError("The model %s is not installed in Ollama." % model,
                          "Install it with `ollama pull %s` or the Install button." % model)
    if e.status == 429 or e.status >= 500:
        return EmbedError("Ollama had an error (HTTP %d)." % e.status, "Try again in a moment.")
    return EmbedError("Ollama rejected the request (HTTP %d). %s" % (e.status, _body_msg(body)),
                      "Check the model name in recall settings.")


def _too_old(url: str, model: str) -> EmbedError:
    try:
        v = version(url)
    except EmbedError:
        v = ""
    return EmbedError("Ollama %s is too old for %s" % (v or "(unknown version)", model),
                      "Update Ollama to the latest version from ollama.com, then try again.")


def version(url: str) -> str:
    url = url.rstrip("/")
    try:
        j = _json_request("GET", url + "/api/version", timeout=10.0, retries=0)
    except _HttpError as e:
        raise EmbedError("Ollama answered with HTTP %d." % e.status, "Check the Ollama URL.")
    except (urllib.error.URLError, OSError, TimeoutError):
        raise _ollama_down(url)
    return str(j.get("version", "")) if isinstance(j, dict) else ""


def tags(url: str) -> Dict[str, str]:
    """Installed models as {name: digest}."""
    url = url.rstrip("/")
    try:
        j = _json_request("GET", url + "/api/tags", timeout=10.0, retries=0)
    except _HttpError as e:
        raise EmbedError("Ollama answered with HTTP %d." % e.status, "Check the Ollama URL.")
    except (urllib.error.URLError, OSError, TimeoutError):
        raise _ollama_down(url)
    out: Dict[str, str] = {}
    for m in (j.get("models") if isinstance(j, dict) else None) or []:
        if isinstance(m, dict) and m.get("name"):
            out[str(m["name"])] = str(m.get("digest") or "")
    return out


def digest_for(installed: Dict[str, str], model: str) -> Optional[str]:
    if model in installed:
        return installed[model]
    if ":" not in model and model + ":latest" in installed:
        return installed[model + ":latest"]
    return None


def model_installed(url: str, model: str) -> bool:
    return digest_for(tags(url), model) is not None


def pull(url: str, model: str) -> Iterator[Dict[str, Any]]:
    """Stream /api/pull progress as {status, completed, total, percent}."""
    url = url.rstrip("/")
    data = json.dumps({"model": model, "stream": True}).encode("utf-8")
    try:
        resp = _open("POST", url + "/api/pull", data,
                     {"Content-Type": "application/json"}, 600.0)
    except _HttpError as e:
        if e.status == 412 or "newer version" in (e.body or "").lower():
            raise _too_old(url, model)
        raise EmbedError("Ollama could not pull %s (HTTP %d). %s" % (model, e.status, _body_msg(e.body)),
                         "Check the model name and your network connection.")
    except (urllib.error.URLError, OSError, TimeoutError):
        raise _ollama_down(url)
    with resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            try:
                j = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            if not isinstance(j, dict):
                continue
            if j.get("error"):
                err = str(j["error"])
                if "newer version" in err.lower() or "412" in err:
                    raise _too_old(url, model)
                raise EmbedError("Ollama could not pull %s: %s" % (model, err[:300]),
                                 "Check the model name and your network connection.")
            total = j.get("total")
            completed = j.get("completed") or 0
            pct = None
            if isinstance(total, (int, float)) and total > 0:
                pct = round(min(100.0, 100.0 * completed / total), 1)
            yield {"status": str(j.get("status", "")), "completed": completed,
                   "total": total if isinstance(total, (int, float)) else None, "percent": pct}


# ---------------------------------------------------------------------------
# Same-model lock (section 3)
# ---------------------------------------------------------------------------

_ID_FIELDS = ("provider", "model", "endpoint_host", "dims", "ollama_digest", "returned_model")


def lock_id(lock: Dict[str, Any]) -> str:
    """Stable hash of the identity fields (not the probe, not created_at)."""
    ident = {k: lock.get(k) for k in _ID_FIELDS}
    blob = json.dumps(ident, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def make_lock(embedder: Embedder) -> Dict[str, Any]:
    probe = embedder.embed_texts([PROBE_TEXT], "document")[0]
    ev = embedder.lock_evidence()
    ident = embedder.identity
    return {
        "provider": ident["provider"], "model": ident["model"],
        "endpoint_host": ident["endpoint_host"], "dims": ident["dims"],
        "returned_model": ev.get("returned_model"), "ollama_digest": ev.get("ollama_digest"),
        "probe": [round(x, 6) for x in probe],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class LockCache:
    """In-memory cache of check results, 10 minutes, injectable clock."""

    def __init__(self, ttl: float = LOCK_CACHE_TTL, clock=time.monotonic):
        self.ttl = ttl
        self.clock = clock
        self._d: Dict[Tuple[Any, ...], Tuple[float, Dict[str, Any]]] = {}

    def get(self, key):
        hit = self._d.get(key)
        if not hit:
            return None
        if self.clock() - hit[0] >= self.ttl:
            self._d.pop(key, None)
            return None
        return dict(hit[1])

    def put(self, key, value) -> None:
        self._d[key] = (self.clock(), dict(value))

    def clear(self) -> None:
        self._d.clear()


def check_lock(stored: Dict[str, Any], embedder: Embedder,
               cache: Optional[LockCache] = None, project_key: str = "") -> Dict[str, Any]:
    """Compare a stored lock with the configured embedder: {ok, reason}.

    Raises EmbedError when the provider cannot be reached: that is not a model
    change and callers must not flag the index as model_changed for it.
    The cache key is (project_key, lock_id(stored), current identity) so a
    settings change is never answered from an older result.
    """
    ident = embedder.identity
    key = (project_key, lock_id(stored),
           (ident["provider"], ident["model"], ident["endpoint_host"], ident["dims"], ident["format"]))
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            return hit
    result = _check(stored, embedder)
    if cache is not None:
        cache.put(key, result)
    return result


def _bad(reason: str) -> Dict[str, Any]:
    return {"ok": False, "reason": reason}


def _check(stored: Dict[str, Any], embedder: Embedder) -> Dict[str, Any]:
    ident = embedder.identity
    for k, label in (("provider", "provider"), ("model", "model"),
                     ("endpoint_host", "endpoint"), ("dims", "dimensions")):
        if stored.get(k) != ident[k]:
            return _bad("The %s changed (index built with %s, now %s)." % (label, stored.get(k), ident[k]))
    if embedder.provider == "ollama":
        ev = embedder.lock_evidence()
        if ev.get("ollama_digest") != stored.get("ollama_digest"):
            return _bad("The Ollama model %s was updated since this index was built." % ident["model"])
    fresh = embedder.embed_texts([PROBE_TEXT], "document")[0]
    if embedder.provider != "ollama":
        b = embedder.lock_evidence().get("returned_model")
        a = stored.get("returned_model")
        if a is not None and b is not None and a != b:
            return _bad("The API now serves a different model (%s, was %s)." % (b, a))
    old = stored.get("probe") or []
    if len(old) != len(fresh):
        return _bad("The vector size changed.")
    sim = cosine(old, fresh)
    if sim < PROBE_COSINE_MIN:
        return _bad("The model's output drifted from the stored probe (similarity %.4f)." % sim)
    return {"ok": True, "reason": ""}


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def _secrets_path(data_dir) -> str:
    return os.path.join(str(data_dir), SECRETS_FILE)


def save_api_key(data_dir, key: str) -> None:
    """Write the key to recall_secrets.json (mode 0600). An empty key removes it."""
    path = _secrets_path(data_dir)
    if not key:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(str(data_dir), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".recall_secrets.", dir=str(data_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"api_key": key}, f)
        try:
            # Restricts to the owner on macOS/Linux. Windows ignores the mode bits,
            # so there the file relies on the user profile's permissions.
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def load_api_key(data_dir) -> str:
    try:
        with open(_secrets_path(data_dir), "r", encoding="utf-8") as f:
            j = json.load(f)
        k = j.get("api_key") if isinstance(j, dict) else ""
        return k if isinstance(k, str) else ""
    except (OSError, ValueError):
        return ""


def has_api_key(data_dir) -> bool:
    return bool(load_api_key(data_dir))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _valid_endpoint(url: str, what: str) -> None:
    p = urlparse(url or "")
    if p.scheme == "https" and p.hostname:
        return
    if p.scheme == "http" and p.hostname in LOOPBACK_HOSTS:
        return
    raise EmbedError("The %s must use https, or http on this machine." % what,
                     "Change the URL in recall settings.")


def make_embedder(semantic: Dict[str, Any], data_dir) -> Embedder:
    dims = int(semantic.get("dims") or 256)
    images = bool(semantic.get("images", True))
    provider = semantic.get("provider", "ollama")
    if provider == "ollama":
        o = semantic.get("ollama") or {}
        url = o.get("url") or "http://127.0.0.1:11434"
        if not _is_loopback(url) or urlparse(url).scheme not in ("http", "https"):
            raise EmbedError("The Ollama URL must be on this machine.",
                             "Use http://127.0.0.1:11434 in recall settings.")
        return OllamaEmbedder(url, o.get("model") or "embeddinggemma-2:740m", dims, images)
    if provider == "api":
        a = semantic.get("api") or {}
        endpoint = a.get("endpoint") or ""
        _valid_endpoint(endpoint, "API endpoint")
        key = load_api_key(data_dir)
        if not key and not _is_loopback(endpoint):
            raise EmbedError("No API key is saved for the embedding API.",
                             "Enter an API key in recall settings.")
        return ApiEmbedder(a.get("format") or "openai", endpoint,
                           a.get("model") or "text-embedding-3-small", dims, key, images)
    raise EmbedError("Unknown embedding provider %r." % provider, "Use ollama or api.")
