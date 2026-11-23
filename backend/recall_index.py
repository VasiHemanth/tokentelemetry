"""Semantic index for recall: settings, Ollama embedder, vector store, build job.

Design: docs/design/cross-harness-recall-v2.md and ...-v3.md (settings, store
v3, delta, IndexRun events, project search; see the "v3" section at the end).
The v2 classes (OllamaEmbedder, IndexJob, make_semantic) stay for v2 callers.
Everything is local unless the user configures an API provider. Vectors
are float32 blobs in SQLite, scored in pure Python (numpy is used per batch
when importable, never required). Ollama must be on loopback.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import os
import random
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, urlsplit

import recall
from recall_embed import BadVectorError, ImageDecodeError, EmbedError as ProviderEmbedError
from tt_paths import data_dir

try:  # optional speed-up only
    import numpy as _np  # type: ignore
except Exception:  # noqa: BLE001
    _np = None

DEFAULT_MODEL = "embeddinggemma-2:740m"
DEFAULT_URL = "http://127.0.0.1:11434"
DIMS_ALLOWED = (128, 256, 512, 768)
DEFAULT_DIMS = 256
MODES = recall.MODES
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
DOC_PREFIX = "title: none | text: "
QUERY_PREFIX = "task: search result | query: "
TEXT_CAP = 6000
EMBED_BATCH = 32
TOP_K = 200
SCAN_BATCH = 512
STORE_VERSION = 3

# One fingerprint implementation, shared with recall.search().
session_fingerprint = recall.session_fingerprint


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- settings

def settings_path() -> Path:
    return data_dir() / "recall.json"


def index_path() -> Path:
    return data_dir() / "recall_index.db"


PROVIDERS = ("ollama", "api")
API_FORMATS = ("openai", "gemini", "voyage")
DEFAULT_API = {"format": "openai", "endpoint": "https://api.openai.com/v1/embeddings",
               "model": "text-embedding-3-small"}
_TOP_KEYS = ("enabled", "provider", "ollama", "api", "dims", "images", "default_mode")
# v2 flat keys. Still accepted on input and still present on output (aliases of
# ollama.model and ollama.url) so v2 callers keep working.
_FLAT_ALIASES = {"model": "model", "ollama_url": "url"}


def _loopback_url(url: Any, name: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"{name} must be a loopback URL such as " + DEFAULT_URL)
    url = url.strip().rstrip("/")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        raise ValueError(f"{name} is not a valid URL") from None
    if parts.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS:
        raise ValueError(f"{name} must point at this machine (127.0.0.1, localhost or ::1)")
    return url


def _api_endpoint(url: Any) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("api.endpoint must be an https:// URL")
    url = url.strip()
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018
    except ValueError:
        raise ValueError("api.endpoint is not a valid URL") from None
    if not host or parts.username or parts.password or parts.fragment:
        raise ValueError("api.endpoint is not a valid URL")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        name = key.lower().replace("_", "-")
        if name in {"key", "sig", "signature", "authorization"} or any(
            part in name for part in ("api-key", "apikey", "token", "secret", "credential", "password")
        ):
            raise ValueError("Put credentials in the API key field, not in the endpoint URL")
    if parts.scheme == "https" or (parts.scheme == "http" and host in LOOPBACK_HOSTS):
        return url
    raise ValueError("api.endpoint must be https://, or http:// on this machine")


def _name(value: Any, label: str, example: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty name, for example {example}")
    return value.strip()


def validate_settings(sem: Dict[str, Any]) -> Dict[str, Any]:
    """Return a clean, complete semantic settings dict or raise ValueError.

    Accepts the v3 shape (``provider``, ``ollama``, ``api``, ``images``) and the
    v2 flat keys (``model``, ``ollama_url``). When both name the same setting
    the v3 key wins. The result carries both, the flat ones as aliases of
    ``ollama.model`` and ``ollama.url``. Unknown keys (an API key included)
    are dropped, so nothing secret reaches recall.json.
    """
    if not isinstance(sem, dict):
        raise ValueError("semantic settings must be an object")
    enabled = sem.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")
    provider = sem.get("provider", "ollama")
    if provider not in PROVIDERS:
        raise ValueError("provider must be ollama or api")

    oll = sem.get("ollama", {})
    if not isinstance(oll, dict):
        raise ValueError("ollama must be an object")
    model = _name(oll.get("model", sem.get("model", DEFAULT_MODEL)), "model", DEFAULT_MODEL)
    url = _loopback_url(oll.get("url", sem.get("ollama_url", DEFAULT_URL)),
                        "ollama_url" if "url" not in oll else "ollama.url")

    api_in = sem.get("api", {})
    if not isinstance(api_in, dict):
        raise ValueError("api must be an object")
    api = {**DEFAULT_API, **{k: api_in[k] for k in DEFAULT_API if k in api_in}}
    if api["format"] not in API_FORMATS:
        raise ValueError("api.format must be openai, gemini or voyage")
    api["endpoint"] = _api_endpoint(api["endpoint"])
    api["model"] = _name(api["model"], "api.model", DEFAULT_API["model"])

    dims = sem.get("dims", DEFAULT_DIMS)
    if isinstance(dims, bool) or dims not in DIMS_ALLOWED:
        raise ValueError("dims must be one of " + ", ".join(str(d) for d in DIMS_ALLOWED))
    if "images" in sem:
        images = sem["images"]
        if not isinstance(images, bool):
            raise ValueError("images must be true or false")
    else:
        images = provider == "ollama"  # an API provider only gets images on request
    mode = sem.get("default_mode", "hybrid")
    if mode not in MODES:
        raise ValueError("default_mode must be keyword, semantic or hybrid")
    return {"enabled": enabled, "provider": provider, "ollama": {"url": url, "model": model},
            "api": api, "dims": dims, "images": images, "default_mode": mode,
            "model": model, "ollama_url": url}


DEFAULTS: Dict[str, Any] = validate_settings({})


def _nested(sem: Dict[str, Any]) -> Dict[str, Any]:
    """The v3 keys of a settings dict, without the flat v2 aliases."""
    out = {k: sem[k] for k in _TOP_KEYS if k in sem}
    for k in ("ollama", "api"):
        if isinstance(out.get(k), dict):
            out[k] = dict(out[k])
    return out


def load_settings(path: Optional[Path] = None) -> Dict[str, Any]:
    """Settings with defaults filled in. A missing or damaged file, or one
    holding values that no longer validate, yields the defaults. v2 files
    (flat ``model`` / ``ollama_url``) load as they are."""
    p = path or settings_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        sem = raw.get("semantic") if isinstance(raw, dict) else None
        return {"semantic": validate_settings(sem if isinstance(sem, dict) else {})}
    except (OSError, ValueError):
        return {"semantic": validate_settings({})}


def save_settings(settings: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
    """Validate and write. The file holds the v3 shape only."""
    clean = {"semantic": validate_settings(settings.get("semantic") or {})}
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"semantic": _nested(clean["semantic"])}, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return clean


def update_settings(patch: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
    """Merge ``patch`` (``{"semantic": {...}}``) into the stored settings.

    ``ollama`` and ``api`` merge key by key. The v2 flat keys in a patch are
    applied to ``ollama``. Switching provider without naming ``images``
    resets it to that provider's default (off for ``api``).
    """
    if not isinstance(patch, dict) or not isinstance(patch.get("semantic", {}), dict):
        raise ValueError("body must look like {\"semantic\": {...}}")
    cur = load_settings(path)["semantic"]
    merged = _nested(cur)
    p = dict(patch.get("semantic") or {})
    for flat, nested_key in _FLAT_ALIASES.items():
        if flat in p:
            sub = p.get("ollama")
            sub = dict(sub) if isinstance(sub, dict) else {}
            sub.setdefault(nested_key, p[flat])
            p["ollama"] = sub
    for k in _TOP_KEYS:
        if k not in p:
            continue
        if k in ("ollama", "api") and isinstance(p[k], dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **p[k]}
        else:
            merged[k] = p[k]
    if "provider" in p and p["provider"] != cur["provider"] and "images" not in p:
        merged.pop("images", None)
    return save_settings({"semantic": merged}, path)


# ---------------------------------------------------------------- API key file

def secrets_path() -> Path:
    return data_dir() / "recall_secrets.json"


def write_api_key(key: str, path: Optional[Path] = None) -> None:
    """Store the API key (mode 0600 where chmod applies). An empty key removes it.
    Called only by the settings route; no reader returns the key to a client."""
    if not isinstance(key, str):
        raise ValueError("api key must be text")
    p = path or secrets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    key = key.strip()
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"api_key": key} if key else {}, f)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, p)


def read_api_key(path: Optional[Path] = None) -> str:
    try:
        raw = json.loads((path or secrets_path()).read_text(encoding="utf-8"))
        key = raw.get("api_key") if isinstance(raw, dict) else ""
        return key if isinstance(key, str) else ""
    except (OSError, ValueError):
        return ""


def api_key_set(path: Optional[Path] = None) -> bool:
    return bool(read_api_key(path))


# ---------------------------------------------------------------- embedder

class EmbedError(Exception):
    """Embedding failed. The message is plain English, safe to show."""


def _opener() -> urllib.request.OpenerDirector:
    # Loopback only: never route through an environment proxy.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fit(vec: Sequence[float], dims: int) -> List[float]:
    """First ``dims`` values (Matryoshka truncation), then unit length."""
    v = [float(x) for x in vec[:dims]]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v] if norm > 0 else v


class OllamaEmbedder:
    def __init__(self, url: str = DEFAULT_URL, model: str = DEFAULT_MODEL, dims: int = DEFAULT_DIMS,
                 timeout: float = 120.0):
        self.url = url.rstrip("/")
        self.model = model
        self.dims = dims
        self.timeout = timeout

    def _unreachable(self) -> EmbedError:
        return EmbedError(f"Ollama is not reachable at {self.url}. Start it with: ollama serve")

    def _missing(self) -> EmbedError:
        return EmbedError(f"Model {self.model} is not installed. Run: ollama pull {self.model}")

    def _get(self, path: str, timeout: float) -> Any:
        with _opener().open(self.url + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def probe(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"reachable": False, "version": None, "model_installed": False, "error": None}
        try:
            out["version"] = str(self._get("/api/version", 2).get("version") or "")
            out["reachable"] = True
            names = [str(m.get("name") or m.get("model") or "") for m in (self._get("/api/tags", 2).get("models") or [])]
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            if not out["reachable"]:
                out["error"] = str(self._unreachable())
            else:
                out["error"] = "Ollama answered but its model list could not be read."
            return out
        want = self.model
        out["model_installed"] = any(n == want or (":" not in want and n == want + ":latest") for n in names)
        if not out["model_installed"]:
            out["error"] = str(self._missing())
        return out

    def _post(self, texts: List[str]) -> List[List[float]]:
        body = json.dumps({"model": self.model, "input": texts, "truncate": True}).encode()
        req = urllib.request.Request(self.url + "/api/embed", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with _opener().open(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200] if hasattr(e, "read") else ""
            if e.code == 404 or "not found" in detail.lower():
                raise self._missing() from None
            raise EmbedError(f"Ollama returned HTTP {e.code} while embedding. {detail}".strip()) from None
        except (urllib.error.URLError, OSError):
            raise self._unreachable() from None
        except ValueError:
            raise EmbedError("Ollama sent a reply that could not be read.") from None
        vecs = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(vecs, list) or len(vecs) != len(texts):
            raise EmbedError("Ollama returned the wrong number of embeddings.")
        out = []
        for v in vecs:
            if not isinstance(v, list) or len(v) < self.dims:
                raise EmbedError(f"Model {self.model} returned vectors shorter than {self.dims} values. "
                                 "Pick a smaller dims in the settings.")
            out.append(_fit(v, self.dims))
        return out

    def _embed(self, texts: Iterable[str], prefix: str) -> List[List[float]]:
        prepared = [prefix + t[:TEXT_CAP] for t in texts]
        out: List[List[float]] = []
        for i in range(0, len(prepared), EMBED_BATCH):
            out.extend(self._post(prepared[i:i + EMBED_BATCH]))
        return out

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return self._embed(texts, DOC_PREFIX)

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text], QUERY_PREFIX)[0]


# ---------------------------------------------------------------- store

class VectorStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else index_path()
        self.last_peak_heap = 0
        self.last_max_batch = 0
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            with conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                    agent TEXT, id TEXT, model TEXT, fingerprint TEXT, chunks INTEGER, indexed_at TEXT,
                    PRIMARY KEY (agent, id))""")
                conn.execute("""CREATE TABLE IF NOT EXISTS vectors (
                    agent TEXT, id TEXT, idx INTEGER, model TEXT, dim INTEGER, vec BLOB,
                    PRIMARY KEY (agent, id, idx))""")
                # v3 tables. A v2 file keeps its sessions/vectors tables (the v2
                # methods below still serve them); see migrate_v2().
                conn.execute("""CREATE TABLE IF NOT EXISTS locks (
                    project_key TEXT PRIMARY KEY, lock_json TEXT, state TEXT, updated_at TEXT)""")
                conn.execute("""CREATE TABLE IF NOT EXISTS documents (
                    project_key TEXT, doc_id TEXT, type TEXT, agent TEXT, scope TEXT, title TEXT,
                    source_json TEXT, mtime REAL, size INTEGER, cheap_fp TEXT, content_fp TEXT,
                    chunks INTEGER, indexed_at TEXT, PRIMARY KEY (project_key, doc_id))""")
                conn.execute("""CREATE TABLE IF NOT EXISTS chunk_vectors (
                    lock_id TEXT, chunk_hash TEXT, dim INTEGER, vec BLOB,
                    PRIMARY KEY (lock_id, chunk_hash))""")
                conn.execute("""CREATE TABLE IF NOT EXISTS doc_chunks (
                    project_key TEXT, doc_id TEXT, idx INTEGER, lock_id TEXT, chunk_hash TEXT,
                    PRIMARY KEY (project_key, doc_id, idx))""")
                conn.execute("CREATE INDEX IF NOT EXISTS doc_chunks_ref ON doc_chunks (lock_id, chunk_hash)")
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version < STORE_VERSION:
                    conn.execute(f"PRAGMA user_version = {STORE_VERSION}")
        finally:
            conn.close()

    def migrate_v2(self, drop: bool = True) -> int:
        """Remove the v2 session vectors and return how many chunks went.

        v2 rows hold no chunk text, so they cannot be keyed by chunk hash, and
        they were embedded without a document title, so they are not reusable
        by v3 even for the same model. They stay readable by the v2 methods until
        a v3 run supersedes the session (``put_document`` drops that session's
        v2 rows) or this is called.
        """
        conn = self._conn()
        try:
            with conn:
                n = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
                if drop:
                    conn.execute("DELETE FROM vectors")
                    conn.execute("DELETE FROM sessions")
            return int(n)
        finally:
            conn.close()

    def upsert_session(self, agent: str, sid: str, model: str, dim: int, fingerprint: str,
                       chunks: Sequence[Dict[str, Any]], vectors: Sequence[Sequence[float]]) -> None:
        """Replace a session's rows in one transaction."""
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk is required")
        rows = []
        for pos, (c, v) in enumerate(zip(chunks, vectors)):
            if len(v) != dim:
                raise ValueError("vector length does not match dim")
            rows.append((agent, sid, int(c.get("idx", pos)), model, dim, array("f", v).tobytes()))
        conn = self._conn()
        try:
            with conn:
                conn.execute("DELETE FROM vectors WHERE agent=? AND id=?", (agent, sid))
                conn.execute("DELETE FROM sessions WHERE agent=? AND id=?", (agent, sid))
                conn.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?,?)", rows)
                conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)",
                             (agent, sid, model, fingerprint, len(rows), _now()))
        finally:
            conn.close()

    def is_current(self, agent: str, sid: str, model: str, dim: int, fingerprint: str) -> bool:
        conn = self._conn()
        try:
            row = conn.execute("SELECT model, fingerprint, chunks FROM sessions WHERE agent=? AND id=?",
                               (agent, sid)).fetchone()
            if not row or row[0] != model or row[1] != fingerprint:
                return False
            if row[2] == 0:
                return True
            return conn.execute("SELECT 1 FROM vectors WHERE agent=? AND id=? AND model=? AND dim=? LIMIT 1",
                                (agent, sid, model, dim)).fetchone() is not None
        finally:
            conn.close()

    def top_k(self, query_vec: Sequence[float], sessions_allowed: Set[Tuple[str, str]], model: str,
              dim: int, k: int = TOP_K) -> List[Tuple[str, str, int, float]]:
        """Best ``k`` chunks by dot product (vectors are unit length, so cosine).

        Rows stream from a cursor in batches of SCAN_BATCH; only the batch and a
        k-sized heap are ever held, whatever the index size.
        """
        self.last_peak_heap = 0
        self.last_max_batch = 0
        if not sessions_allowed or len(query_vec) != dim or k <= 0:
            return []
        q = [float(x) for x in query_vec]
        qa = _np.asarray(q, dtype=_np.float32) if _np is not None else None
        heap: List[Tuple[float, int, str, str, int]] = []
        n = 0
        conn = self._conn()
        try:
            cur = conn.execute("SELECT agent, id, idx, vec FROM vectors WHERE model = ? AND dim = ?",
                               (model, dim))
            while True:
                rows = cur.fetchmany(SCAN_BATCH)
                if not rows:
                    break
                batch = [r for r in rows if (r[0], r[1]) in sessions_allowed]
                self.last_max_batch = max(self.last_max_batch, len(batch))
                if batch:
                    if qa is not None:
                        mat = _np.frombuffer(b"".join(r[3] for r in batch), dtype=_np.float32).reshape(len(batch), dim)
                        scores = (mat @ qa).tolist()
                    else:
                        scores = []
                        for r in batch:
                            a = array("f")
                            a.frombytes(r[3])
                            scores.append(sum(x * y for x, y in zip(a, q)))
                    for r, sc in zip(batch, scores):
                        n += 1
                        item = (sc, -n, r[0], r[1], r[2])
                        if len(heap) < k:
                            heapq.heappush(heap, item)
                        elif item > heap[0]:
                            heapq.heapreplace(heap, item)
                        self.last_peak_heap = max(self.last_peak_heap, len(heap))
        finally:
            conn.close()
        return [(a, i, idx, float(sc)) for sc, _n, a, i, idx in sorted(heap, reverse=True)]

    # ------------------------------------------------ v3: locks and documents

    def get_lock(self, project_key: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT lock_json, state, updated_at FROM locks WHERE project_key=?",
                               (project_key,)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        try:
            lock = json.loads(row[0])
        except ValueError:
            return None
        return {"lock": lock, "lock_id": lock_id_of(lock), "state": row[1], "updated_at": row[2]}

    def set_lock(self, project_key: str, lock: Dict[str, Any], state: str = "building") -> None:
        if state not in LOCK_STATES:
            raise ValueError("unknown lock state")
        conn = self._conn()
        try:
            with conn:
                conn.execute("INSERT OR REPLACE INTO locks VALUES (?,?,?,?)",
                             (project_key, json.dumps(lock), state, _now()))
        finally:
            conn.close()

    def set_state(self, project_key: str, state: str) -> None:
        if state not in LOCK_STATES:
            raise ValueError("unknown lock state")
        conn = self._conn()
        try:
            with conn:
                conn.execute("UPDATE locks SET state=?, updated_at=? WHERE project_key=?",
                             (state, _now(), project_key))
        finally:
            conn.close()

    def documents(self, project_key: str) -> Dict[str, Dict[str, Any]]:
        """Every stored document row of the project, by doc_id."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT doc_id, type, agent, scope, title, source_json, mtime, size, cheap_fp, content_fp, "
                "chunks, indexed_at FROM documents WHERE project_key=?", (project_key,)).fetchall()
        finally:
            conn.close()
        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            try:
                source = json.loads(r[5]) if r[5] else {}
            except ValueError:
                source = {}
            out[r[0]] = {"doc_id": r[0], "type": r[1], "agent": r[2], "scope": r[3], "title": r[4],
                         "source": source, "mtime": r[6], "size": r[7], "cheap_fp": r[8],
                         "content_fp": r[9], "chunks": r[10], "indexed_at": r[11]}
        return out

    def project_map(self, project_key: str, images: bool = True) -> List[Dict[str, Any]]:
        """Project the first stored chunk of each indexed document."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT d.doc_id, d.type, d.agent, d.title, c.lock_id, v.vec
                   FROM documents d
                   JOIN doc_chunks c ON c.project_key=d.project_key AND c.doc_id=d.doc_id
                   JOIN chunk_vectors v ON v.lock_id=c.lock_id AND v.chunk_hash=c.chunk_hash
                   WHERE d.project_key=? AND (? OR d.type!='image')
                     AND c.idx=(SELECT MIN(first.idx) FROM doc_chunks first
                                WHERE first.project_key=d.project_key AND first.doc_id=d.doc_id)
                   ORDER BY d.doc_id""", (project_key, images)).fetchall()
        finally:
            conn.close()
        projectors: Dict[str, Projector] = {}
        points = []
        for doc_id, doc_type, agent, title, lock_id, blob in rows:
            if lock_id not in projectors:
                projectors[lock_id] = Projector(lock_id)
            vec = array("f")
            vec.frombytes(blob)
            points.append({"doc_id": doc_id, "doc_type": doc_type, "agent": agent,
                           "title": _title(title), "xy": projectors[lock_id].xy(vec)})
        return points

    def have_hashes(self, lock_id: str, hashes: Iterable[str]) -> Set[str]:
        want = list(dict.fromkeys(hashes))
        found: Set[str] = set()
        conn = self._conn()
        try:
            for i in range(0, len(want), 500):
                part = want[i:i + 500]
                q = "SELECT chunk_hash FROM chunk_vectors WHERE lock_id=? AND chunk_hash IN (%s)" % ",".join("?" * len(part))
                found.update(r[0] for r in conn.execute(q, [lock_id, *part]))
        finally:
            conn.close()
        return found

    def get_vector(self, lock_id: str, chunk_hash: str) -> Optional[List[float]]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT vec FROM chunk_vectors WHERE lock_id=? AND chunk_hash=?",
                               (lock_id, chunk_hash)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        a = array("f")
        a.frombytes(row[0])
        return list(a)

    @staticmethod
    def _collect(conn: sqlite3.Connection, where: str, args: Tuple[Any, ...]) -> List[Tuple[str, str]]:
        return [(r[0], r[1]) for r in conn.execute(
            f"SELECT DISTINCT lock_id, chunk_hash FROM doc_chunks WHERE {where}", args)]

    @staticmethod
    def _gc(conn: sqlite3.Connection, pairs: Sequence[Tuple[str, str]]) -> int:
        """Delete the given chunk_vectors rows that no doc_chunks row references.
        Runs inside the caller's transaction."""
        n = 0
        for lock_id, h in pairs:
            n += conn.execute(
                "DELETE FROM chunk_vectors WHERE lock_id=? AND chunk_hash=? AND NOT EXISTS "
                "(SELECT 1 FROM doc_chunks WHERE lock_id=? AND chunk_hash=?)",
                (lock_id, h, lock_id, h)).rowcount
        return n

    def put_document(self, project_key: str, doc: Dict[str, Any], lock_id: str, dim: int,
                     content_fp: str, idxs: Sequence[int], hashes: Sequence[str],
                     new_vectors: Dict[str, Sequence[float]]) -> None:
        """Replace one document in a single transaction.

        ``hashes[i]`` is the chunk hash at chunk position ``idxs[i]``. ``new_vectors``
        holds vectors for hashes not yet stored. Vectors the old version of this
        document referenced and nothing else does are collected before commit.
        """
        if len(idxs) != len(hashes):
            raise ValueError("one hash per chunk position is required")
        rows = []
        for h, v in new_vectors.items():
            if len(v) != dim:
                raise ValueError("vector length does not match dim")
            rows.append((lock_id, h, dim, array("f", v).tobytes()))
        doc_id = doc["doc_id"]
        conn = self._conn()
        try:
            with conn:
                old = self._collect(conn, "project_key=? AND doc_id=?", (project_key, doc_id))
                conn.execute("DELETE FROM doc_chunks WHERE project_key=? AND doc_id=?", (project_key, doc_id))
                conn.executemany("INSERT OR IGNORE INTO chunk_vectors VALUES (?,?,?,?)", rows)
                conn.executemany("INSERT OR REPLACE INTO doc_chunks VALUES (?,?,?,?,?)",
                                 [(project_key, doc_id, int(i), lock_id, h) for i, h in zip(idxs, hashes)])
                conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (project_key, doc_id, doc.get("type"), doc.get("agent"), doc.get("scope"),
                              doc.get("title") or "", json.dumps(doc.get("source") or {}),
                              float(doc.get("mtime") or 0), int(doc.get("size") or 0),
                              doc.get("cheap_fp") or "", content_fp, len(hashes), _now()))
                keep = {(lock_id, h) for h in hashes}
                self._gc(conn, [p for p in old if p not in keep])
                if doc.get("type") == "session" and (doc.get("source") or {}).get("kind") == "session":
                    # superseded v2 rows for the same session
                    a, sid = doc.get("agent"), (doc.get("source") or {}).get("id")
                    conn.execute("DELETE FROM vectors WHERE agent=? AND id=?", (a, sid))
                    conn.execute("DELETE FROM sessions WHERE agent=? AND id=?", (a, sid))
        finally:
            conn.close()

    def remove_documents(self, project_key: str, doc_ids: Iterable[str]) -> int:
        """Counted deletion: drop the documents, then every vector nothing
        references any more. Vectors other documents (or projects) use stay."""
        ids = list(doc_ids)
        conn = self._conn()
        try:
            with conn:
                pairs: List[Tuple[str, str]] = []
                for d in ids:
                    pairs.extend(self._collect(conn, "project_key=? AND doc_id=?", (project_key, d)))
                    conn.execute("DELETE FROM doc_chunks WHERE project_key=? AND doc_id=?", (project_key, d))
                    conn.execute("DELETE FROM documents WHERE project_key=? AND doc_id=?", (project_key, d))
                self._gc(conn, list(dict.fromkeys(pairs)))
        finally:
            conn.close()
        return len(ids)

    def drop_project(self, project_key: str) -> None:
        """Forget a project's documents and lock (the first step of a full re-index).
        Deletes only that project's rows, then collects unreferenced vectors."""
        conn = self._conn()
        try:
            with conn:
                pairs = self._collect(conn, "project_key=?", (project_key,))
                conn.execute("DELETE FROM doc_chunks WHERE project_key=?", (project_key,))
                conn.execute("DELETE FROM documents WHERE project_key=?", (project_key,))
                conn.execute("DELETE FROM locks WHERE project_key=?", (project_key,))
                self._gc(conn, pairs)
        finally:
            conn.close()

    def reset_project(self, project_key: str, lock: Dict[str, Any], state: str = "building") -> None:
        """Drop the project's rows and install a new lock in one transaction,
        so a failed full re-index never leaves the project without an index."""
        if state not in LOCK_STATES:
            raise ValueError("unknown lock state")
        conn = self._conn()
        try:
            with conn:
                pairs = self._collect(conn, "project_key=?", (project_key,))
                conn.execute("DELETE FROM doc_chunks WHERE project_key=?", (project_key,))
                conn.execute("DELETE FROM documents WHERE project_key=?", (project_key,))
                conn.execute("INSERT OR REPLACE INTO locks VALUES (?,?,?,?)",
                             (project_key, json.dumps(lock), state, _now()))
                self._gc(conn, pairs)
        finally:
            conn.close()

    def counts(self) -> Dict[str, int]:
        conn = self._conn()
        try:
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("locks", "documents", "chunk_vectors", "doc_chunks")}
        finally:
            conn.close()

    def search_project(self, project_key: str, lock_id: str, query_vec: Sequence[float], dim: int,
                       types: Optional[Iterable[str]] = None, doc_ids: Optional[Set[str]] = None,
                       k: int = TOP_K) -> List[Tuple[str, int, float]]:
        """Best ``k`` ``(doc_id, chunk idx, cosine)`` among the project's chunks
        under one lock. Streams in batches of SCAN_BATCH with a k-sized heap."""
        self.last_peak_heap = 0
        self.last_max_batch = 0
        if len(query_vec) != dim or k <= 0:
            return []
        want = set(types) if types else None
        docs = self.documents(project_key)
        allowed = {d for d, r in docs.items()
                   if (want is None or r["type"] in want) and (doc_ids is None or d in doc_ids)}
        if not allowed:
            return []
        q = [float(x) for x in query_vec]
        qa = _np.asarray(q, dtype=_np.float32) if _np is not None else None
        heap: List[Tuple[float, int, str, int]] = []
        n = 0
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT dc.doc_id, dc.idx, cv.vec FROM doc_chunks dc JOIN chunk_vectors cv "
                "ON cv.lock_id = dc.lock_id AND cv.chunk_hash = dc.chunk_hash "
                "WHERE dc.project_key = ? AND dc.lock_id = ? AND cv.dim = ?", (project_key, lock_id, dim))
            while True:
                rows = cur.fetchmany(SCAN_BATCH)
                if not rows:
                    break
                batch = [r for r in rows if r[0] in allowed]
                self.last_max_batch = max(self.last_max_batch, len(batch))
                if not batch:
                    continue
                if qa is not None:
                    mat = _np.frombuffer(b"".join(r[2] for r in batch), dtype=_np.float32).reshape(len(batch), dim)
                    scores = (mat @ qa).tolist()
                else:
                    scores = []
                    for r in batch:
                        a = array("f")
                        a.frombytes(r[2])
                        scores.append(sum(x * y for x, y in zip(a, q)))
                for r, sc in zip(batch, scores):
                    n += 1
                    item = (sc, -n, r[0], r[1])
                    if len(heap) < k:
                        heapq.heappush(heap, item)
                    elif item > heap[0]:
                        heapq.heapreplace(heap, item)
                    self.last_peak_heap = max(self.last_peak_heap, len(heap))
        finally:
            conn.close()
        return [(d, idx, float(sc)) for sc, _n, d, idx in sorted(heap, reverse=True)]

    def stats(self, model: Optional[str] = None) -> Dict[str, Any]:
        conn = self._conn()
        try:
            where, args = ("WHERE model = ?", (model,)) if model else ("", ())
            sessions, chunks, updated = conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(chunks), 0), MAX(indexed_at) FROM sessions {where}", args).fetchone()
            latest = conn.execute("SELECT model FROM sessions ORDER BY indexed_at DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        size = 0
        for suffix in ("", "-wal", "-shm"):
            try:
                size += os.path.getsize(str(self.path) + suffix)
            except OSError:
                pass
        return {"chunks": int(chunks), "sessions": int(sessions), "model": model or (latest[0] if latest else None),
                "bytes": size, "updated_at": updated}


# ---------------------------------------------------------------- job

class JobBusy(Exception):
    def __init__(self, status: Dict[str, Any]):
        super().__init__("An index build is already running.")
        self.status = status


def _blank_status() -> Dict[str, Any]:
    return {"state": "idle", "project": None, "sessions_total": 0, "sessions_done": 0,
            "sessions_skipped": 0, "chunks_embedded": 0, "chunks_per_sec": 0.0,
            "started_at": None, "finished_at": None, "error": None}


class IndexJob:
    """Builds the index in a background thread, one job at a time."""

    def __init__(self, store: VectorStore, embedder: Any, loader: recall.Loader,
                 select: Optional[Callable[[Sequence[Dict[str, Any]], Optional[str]], Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.store = store
        self.embedder = embedder
        self.loader = loader
        self.select = select or (lambda sessions, project: recall._select(sessions, project, None, None))
        self.clock = clock
        self._lock = threading.Lock()
        self._status = _blank_status()
        self._thread: Optional[threading.Thread] = None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            s = dict(self._status)
            if s["project"]:
                s["project"] = dict(s["project"])
            return s

    def _set(self, **kw: Any) -> None:
        with self._lock:
            self._status.update(kw)

    def start(self, sessions: Sequence[Dict[str, Any]], project: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if self._status["state"] == "running":
                raise JobBusy(dict(self._status))
            proj, metas = self.select(sessions, project)
            self._status = {**_blank_status(), "state": "running", "project": proj,
                            "sessions_total": len(metas), "started_at": _now()}
            self._thread = threading.Thread(target=self._run, args=(metas,), daemon=True, name="recall-index")
            self._thread.start()
            return dict(self._status)

    def wait(self, timeout: Optional[float] = None) -> None:
        t = self._thread
        if t is not None:
            t.join(timeout)

    def _run(self, metas: List[Dict[str, Any]]) -> None:
        t0 = self.clock()
        model, dims = self.embedder.model, self.embedder.dims
        embedded = done = skipped = 0
        try:
            for m in metas:
                agent, sid = m["agent"], m["id"]
                loaded = None
                try:
                    loaded = self.loader(agent, sid)
                except Exception:  # noqa: BLE001 - one unreadable transcript does not stop the build
                    loaded = None
                if loaded is not None:
                    chunks, _source = loaded
                    chunks, texts = recall.index_view(chunks)
                    fp = recall.fingerprint_texts(texts)
                    if self.store.is_current(agent, sid, model, dims, fp):
                        skipped += 1
                    else:
                        vecs = self.embedder.embed_documents(texts) if texts else []
                        self.store.upsert_session(agent, sid, model, dims, fp, chunks, vecs)
                        embedded += len(vecs)
                done += 1
                elapsed = max(self.clock() - t0, 1e-9)
                self._set(sessions_done=done, sessions_skipped=skipped, chunks_embedded=embedded,
                          chunks_per_sec=round(embedded / elapsed, 1))
            self._set(state="done", finished_at=_now())
        except EmbedError as e:
            self._set(state="error", error=str(e), finished_at=_now())
        except Exception as e:  # noqa: BLE001
            self._set(state="error", error=f"Indexing stopped unexpectedly ({type(e).__name__}).",
                      finished_at=_now())


def make_semantic(store: VectorStore, embedder: Any) -> recall.Semantic:
    """Bundle for ``recall.search(semantic=...)`` backed by a store and embedder."""
    model, dims = embedder.model, embedder.dims
    return recall.Semantic(
        model=model,
        is_current=lambda agent, sid, fp: store.is_current(agent, sid, model, dims, fp),
        rank=lambda q, allowed: store.top_k(embedder.embed_query(q), allowed, model, dims),
    )


# ================================================================ v3
# Project knowledge index: locks, documents, delta, index run, search.
# Design: docs/design/cross-harness-recall-v3.md (sections 3, 5, 7, 8).

LOCK_STATES = ("ready", "model_changed", "building")
DOC_TYPES = ("session", "image", "skill", "command", "agent", "artifact", "markdown", "mcp")
PROBE_TEXT = "TokenTelemetry recall probe: the quick brown fox checks the index model."
PROBE_COSINE = 0.999
LOCK_CHECK_TTL = 600.0
LOCK_IDENTITY_KEYS = ("provider", "model", "endpoint_host", "dims", "format", "endpoint_id")
LOCK_EVIDENCE_KEYS = ("ollama_digest", "returned_model")
TEXT_CHUNK_CHARS = 600   # same size as summaries.build_chunks
MAX_DOC_CHUNKS = 500     # per text document; the rest is not embedded
MAX_TEXT_BYTES = 1_000_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
VECTOR_EVENTS_PER_SEC = 40
PROGRESS_EVERY_S = 0.25
DEFAULT_CHUNKS_PER_SEC = 25.0
SESSION_CHUNKS_GUESS = 40


# ---------------------------------------------------------------- lock

def lock_id_of(lock: Dict[str, Any]) -> str:
    """Stable id of a model identity. Projects with equal ids share vectors."""
    ident = {k: lock.get(k) for k in LOCK_IDENTITY_KEYS + LOCK_EVIDENCE_KEYS}
    if not lock.get("ollama_digest"):
        # A cloud alias can keep its name while serving new vectors. A full
        # rebuild must never reuse old vectors still held by another project.
        ident["probe"] = lock.get("probe")
    return hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()[:24]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else -1.0


def _evidence(embedder: Any) -> Dict[str, Any]:
    fn = getattr(embedder, "lock_evidence", None)
    try:
        ev = fn() if callable(fn) else {}
    except Exception:  # noqa: BLE001 - evidence is best effort
        ev = {}
    return ev if isinstance(ev, dict) else {}


def make_lock(embedder: Any) -> Dict[str, Any]:
    """Lock record for the embedder as configured now, with a probe vector."""
    ident = dict(embedder.identity)
    probe = embedder.embed_texts([PROBE_TEXT], "document")[0]
    ev = _evidence(embedder)
    return {**{k: ident.get(k) for k in LOCK_IDENTITY_KEYS},
            "returned_model": ev.get("returned_model"), "ollama_digest": ev.get("ollama_digest"),
            "probe": [round(float(x), 6) for x in probe], "created_at": _now()}


def identity_mismatch(lock: Dict[str, Any], identity: Dict[str, Any]) -> Optional[str]:
    """Why the stored lock and this identity differ, or None. No I/O."""
    for k in LOCK_IDENTITY_KEYS:
        if lock.get(k) != identity.get(k):
            return f"{k} changed from {lock.get(k)} to {identity.get(k)}"
    return None


def check_lock(embedder: Any, lock: Dict[str, Any]) -> Tuple[bool, str]:
    """Same-model check from spec section 3: identity, digest or returned
    model, then a fresh probe vector against the stored one."""
    why = identity_mismatch(lock, dict(embedder.identity))
    if why:
        return False, why
    fresh = embedder.embed_texts([PROBE_TEXT], "document")[0]
    ev = _evidence(embedder)
    for k in LOCK_EVIDENCE_KEYS:
        if lock.get(k) and ev.get(k) and lock[k] != ev[k]:
            return False, f"{k} changed"
    if _cosine(lock.get("probe") or [], fresh) < PROBE_COSINE:
        return False, "the model returns different vectors than when the index was built"
    return True, ""


class LockMismatch(Exception):
    def __init__(self, message: str, fix: str):
        super().__init__(message)
        self.fix = fix


def _model_label(lock: Dict[str, Any]) -> str:
    return str(lock.get("model") or "unknown model")


class LockGuard:
    """Runs check_lock at most once per TTL per project and keeps the verdict
    in the store, so a mismatch sticks until the project is re-indexed."""

    def __init__(self, store: "VectorStore", embedder: Any, ttl: float = LOCK_CHECK_TTL,
                 clock: Callable[[], float] = time.monotonic,
                 check: Optional[Callable[[Any, Dict[str, Any]], Tuple[bool, str]]] = None):
        self.store = store
        self.embedder = embedder
        self.ttl = ttl
        self.clock = clock
        self._check = check or check_lock
        self._cache: Dict[str, Tuple[float, bool, str]] = {}
        self._mu = threading.Lock()

    def forget(self, project_key: str) -> None:
        with self._mu:
            self._cache.pop(project_key, None)

    def check(self, project_key: str, *, fresh: bool = False) -> Tuple[bool, str]:
        rec = self.store.get_lock(project_key)
        if rec is None:
            return True, ""
        if rec["state"] == "model_changed":
            return False, "model changed"
        now = self.clock()
        with self._mu:
            hit = self._cache.get(project_key)
        if not fresh and hit and now - hit[0] < self.ttl:
            return hit[1], hit[2]
        ok, why = self._check(self.embedder, rec["lock"])
        with self._mu:
            self._cache[project_key] = (now, ok, why)
        if not ok:
            self.store.set_state(project_key, "model_changed")
        return ok, why

    def state(self, project_key: str) -> str:
        """``never_indexed``, ``ready`` (also while building) or ``model_changed``."""
        if self.store.get_lock(project_key) is None:
            return "never_indexed"
        ok, _why = self.check(project_key)
        return "ready" if ok else "model_changed"


# ---------------------------------------------------------------- chunking

def split_text(text: str, size: int = TEXT_CHUNK_CHARS) -> List[str]:
    """Cut plain text into pieces of about ``size`` characters at a newline or
    space, the way summaries.build_chunks cuts message text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    out: List[str] = []
    while text:
        if len(text) <= size:
            out.append(text)
            break
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        piece = text[:cut].strip()
        if piece:
            out.append(piece)
        text = text[cut:].strip()
    return out


def text_chunks(text: str) -> List[str]:
    """Redacted chunk texts of a text document (key blocks that span chunks are
    masked), capped at MAX_DOC_CHUNKS."""
    chunks = [{"idx": i, "text": t} for i, t in enumerate(split_text(text)[:MAX_DOC_CHUNKS])]
    return recall._redacted_texts(chunks, recall.mask_key_continuations(chunks))


def text_content_fp(text: str) -> str:
    """content_fp of a text document, for the query-time staleness check."""
    return recall.fingerprint_texts(text_chunks(text))


def image_content_fp(data: bytes) -> str:
    return "img:" + hashlib.sha256(data).hexdigest()


def prefix_document(embedder: Any, text: str, title: str) -> str:
    """The text the embedder actually sees for a document chunk. Chunk hashes
    are taken over this, so a changed title or prefix re-embeds."""
    fn = getattr(embedder, "format_document", None)
    if callable(fn):
        return str(fn(text, title))
    model = str((getattr(embedder, "identity", {}) or {}).get("model") or "").lower()
    if "embeddinggemma" in model:
        return f"title: {title or 'none'} | text: {text}"
    return text


def chunk_hash(prefixed: str) -> str:
    return hashlib.sha256(prefixed.encode("utf-8", "replace")).hexdigest()


def _title(raw: Any) -> str:
    return recall._collapse(raw or "", recall.TITLE_MAX)


# ---------------------------------------------------------------- documents

def session_cheap_fp(session: Dict[str, Any]) -> str:
    """Fingerprint of a scanned session from fields the scan already holds:
    last timestamp, token total and message count. No transcript is read."""
    last = recall._iso(recall._to_dt(session.get("timestamp") or session.get("last_ts"))) or ""
    tokens = session.get("tokens")
    total = tokens.get("total") if isinstance(tokens, dict) else tokens
    count = ""
    for k in ("message_count", "messages", "n_messages", "turns"):
        v = session.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            count = str(int(v))
            break
    return hashlib.sha1(f"{last}|{recall._num(total)}|{count}".encode()).hexdigest()


def session_doc_id(agent: str, sid: str) -> str:
    return f"session:{agent}:{sid}"


def session_document(session: Dict[str, Any]) -> Dict[str, Any]:
    """Document dict for a scanned session (what recall_sources does for files)."""
    m = recall._meta(session)
    last = m["_last"]
    return {"doc_id": session_doc_id(str(m["agent"]), str(m["id"])), "type": "session",
            "agent": m["agent"], "scope": "project", "title": m["title"],
            "source": {"kind": "session", "id": m["id"]},
            "mtime": last.timestamp() if last else 0.0, "size": m["tokens"],
            "cheap_fp": session_cheap_fp(session)}


def default_text_reader(doc: Dict[str, Any]) -> Optional[str]:
    """Text of a document: ``source.text`` when the discoverer rendered it (MCP
    servers), else the file at ``source.path`` (``~`` expanded, 1 MB cap)."""
    src = doc.get("source") or {}
    if isinstance(src.get("text"), str):
        return src["text"]
    path = src.get("path")
    if not isinstance(path, str) or not path:
        return None
    try:
        p = Path(path).expanduser()
        if p.stat().st_size > MAX_TEXT_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def default_image_reader(doc: Dict[str, Any]) -> Optional[bytes]:
    src = doc.get("source") or {}
    path = src.get("path")
    if not isinstance(path, str) or not path:
        return None
    try:
        p = Path(path).expanduser()
        if p.stat().st_size > MAX_IMAGE_BYTES:
            return None
        return p.read_bytes()
    except OSError:
        return None


# ---------------------------------------------------------------- delta

def _est_chunks(doc: Dict[str, Any], stored: Optional[Dict[str, Any]]) -> int:
    if isinstance(doc.get("chunks_estimate"), int):
        return max(0, doc["chunks_estimate"])
    t = doc.get("type")
    if t == "image":
        return 1
    if t == "session":
        if stored:
            return max(1, -(-int(stored.get("chunks") or 0) // 10))  # appended tail, about a tenth
        return SESSION_CHUNKS_GUESS
    size = int(doc.get("size") or 0)
    return max(1, min(MAX_DOC_CHUNKS, -(-size // TEXT_CHUNK_CHARS)))


def compute_delta(store: "VectorStore", project_key: str, discovered_documents: Iterable[Dict[str, Any]],
                  session_cheap_fps: Optional[Dict[Any, str]] = None, *,
                  identity: Optional[Dict[str, Any]] = None, images: bool = True,
                  chunks_per_sec: Optional[float] = None, unavailable: bool = False) -> Dict[str, Any]:
    """What a run would do, without reading transcripts or embedding anything.

    ``discovered_documents`` are Document dicts with ``cheap_fp``. For sessions
    ``session_cheap_fps`` (keyed by doc_id, or by ``(agent, session id)``) gives
    the scan-derived fingerprint and overrides the document's own. ``identity``
    (the embedder's) lets a settings change show as ``model_changed`` without
    a probe call. ``images`` False leaves image documents out of the count.
    """
    discovered_documents = list(discovered_documents)
    fps = session_cheap_fps or {}
    rec = store.get_lock(project_key)
    stored = store.documents(project_key)
    seen: Set[str] = set()
    new: Dict[str, int] = {}
    changed: Dict[str, int] = {}
    est = 0
    for d in discovered_documents:
        t = d.get("type")
        if t == "image" and not images:
            continue
        did = d.get("doc_id")
        if not did:
            continue
        seen.add(did)
        fp = fps.get(did)
        if fp is None and d.get("agent") is not None and (d.get("source") or {}).get("id") is not None:
            fp = fps.get((d.get("agent"), d["source"]["id"]))
        if fp is None:
            fp = d.get("cheap_fp")
        row = stored.get(did)
        if row is None:
            new[t] = new.get(t, 0) + 1
            est += _est_chunks(d, None)
        elif row["cheap_fp"] != fp:
            changed[t] = changed.get(t, 0) + 1
            est += _est_chunks(d, row)
    removed: Dict[str, int] = {}
    for did, row in stored.items():
        source = row["source"]
        if source.get("kind") == "inline_image" and session_doc_id(row["agent"], source["session_id"]) in seen:
            continue
        if did not in seen and not (row["type"] == "image" and not images):
            removed[row["type"]] = removed.get(row["type"], 0) + 1
    if unavailable:
        state = "unavailable"
    elif rec is None and not stored:
        state = "never_indexed"
    elif rec is not None and rec["state"] == "model_changed":
        state = "model_changed"
    elif rec is not None and identity is not None and identity_mismatch(rec["lock"], identity):
        state = "model_changed"
    elif new or changed or removed or (rec is not None and rec["state"] == "building"):
        state = "stale"
    else:
        state = "up_to_date"
    indexed = [r["indexed_at"] for r in stored.values() if r.get("indexed_at")]
    rate = chunks_per_sec if chunks_per_sec and chunks_per_sec > 0 else DEFAULT_CHUNKS_PER_SEC
    lock = rec["lock"] if rec else None
    return {"state": state, "last_indexed_at": max(indexed) if indexed else (rec["updated_at"] if rec else None),
            "lock": {"model": lock.get("model"), "provider": lock.get("provider")} if lock else None,
            "new": new, "changed": changed, "removed": removed,
            "new_chunks_estimate": est, "estimate_seconds": max(0.1, round(est / rate, 1)) if est else 0.0}


def _store_delta(self: "VectorStore", project_key: str, discovered_documents: Iterable[Dict[str, Any]],
                 session_cheap_fps: Optional[Dict[Any, str]] = None, **kw: Any) -> Dict[str, Any]:
    return compute_delta(self, project_key, discovered_documents, session_cheap_fps, **kw)


VectorStore.delta = _store_delta  # type: ignore[attr-defined]


# ---------------------------------------------------------------- events

class EventLog:
    """Ordered in-memory events of one run. Clients replay with ``since``."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._events: List[Dict[str, Any]] = []
        self._cv = threading.Condition()
        self.closed = False

    def append(self, etype: str, **fields: Any) -> Dict[str, Any]:
        with self._cv:
            ev = {"seq": len(self._events) + 1, "type": etype, "run": self.run_id, **fields}
            self._events.append(ev)
            if etype in ("done", "error"):
                self.closed = True
            self._cv.notify_all()
            return ev

    def count(self) -> int:
        with self._cv:
            return len(self._events)

    def since(self, seq: int = 0) -> List[Dict[str, Any]]:
        with self._cv:
            return list(self._events[max(0, int(seq)):])

    def wait(self, seq: int, timeout: float) -> List[Dict[str, Any]]:
        with self._cv:
            if len(self._events) <= seq and not self.closed:
                self._cv.wait(timeout)
            return list(self._events[max(0, int(seq)):])


class Projector:
    """Fixed random projection of a vector to 2D, seeded by the lock id so the
    same text lands in the same place on every run."""

    def __init__(self, seed: str):
        self.seed = seed
        self._axes: Dict[int, Tuple[List[float], List[float]]] = {}

    def _axis(self, dim: int) -> Tuple[List[float], List[float]]:
        ax = self._axes.get(dim)
        if ax is None:
            rx, ry = random.Random(f"{self.seed}:x"), random.Random(f"{self.seed}:y")
            ax = ([rx.gauss(0, 1) for _ in range(dim)], [ry.gauss(0, 1) for _ in range(dim)])
            self._axes[dim] = ax
        return ax

    def xy(self, vec: Sequence[float]) -> List[float]:
        ax, ay = self._axis(len(vec))
        # a unit vector projected on a Gaussian axis is about N(0, 1); 3 sigma maps to the edge
        px = sum(v * a for v, a in zip(vec, ax)) / 3.0
        py = sum(v * a for v, a in zip(vec, ay)) / 3.0
        return [round(max(-1.0, min(1.0, px)), 4), round(max(-1.0, min(1.0, py)), 4)]


# ---------------------------------------------------------------- run

def _run_status_blank() -> Dict[str, Any]:
    return {"state": "idle", "run": None, "project": None, "documents_total": 0, "documents_done": 0,
            "documents_skipped": 0, "documents_removed": 0, "documents_unreadable": 0,
            "chunks_embedded": 0, "chunks_reused": 0, "tokens": 0, "per_sec": 0.0,
            "started_at": None, "finished_at": None, "error": None, "seq": 0}


class _Prepared:
    __slots__ = ("idxs", "texts", "content_fp", "image")

    def __init__(self, idxs: List[int], texts: List[str], content_fp: str, image: Optional[bytes] = None):
        self.idxs, self.texts, self.content_fp, self.image = idxs, texts, content_fp, image


class IndexRun:
    """One index run at a time for one project. Replaces IndexJob for v3.

    ``loader(agent, session_id)`` returns ``(chunks, source)`` like the v2 job.
    ``text_reader(doc)`` returns a text document's text, ``image_reader(doc)``
    an image's bytes; both default to reading ``doc["source"]``. Events go to
    ``self.log`` (see ``events`` / ``stream``).
    """

    def __init__(self, store: VectorStore, embedder: Any, loader: recall.Loader, *,
                 text_reader: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None,
                 image_reader: Optional[Callable[[Dict[str, Any]], Optional[bytes]]] = None,
                 images: bool = True, clock: Callable[[], float] = time.monotonic,
                 inline_discover: Optional[Callable[..., Iterable[Dict[str, Any]]]] = None,
                 guard: Optional[LockGuard] = None,
                 lock_factory: Optional[Callable[[Any], Dict[str, Any]]] = None):
        self.store = store
        self.embedder = embedder
        self.loader = loader
        self.text_reader = text_reader or default_text_reader
        self.image_reader = image_reader or default_image_reader
        self.images = images
        self.inline_discover = inline_discover
        self.clock = clock
        self.guard = guard or LockGuard(store, embedder)
        self.lock_factory = lock_factory or make_lock
        self._mu = threading.Lock()
        self._status = _run_status_blank()
        self._thread: Optional[threading.Thread] = None
        self.log = EventLog("none")

    # -- public

    def status(self) -> Dict[str, Any]:
        with self._mu:
            s = dict(self._status)
        if s["project"]:
            s["project"] = dict(s["project"])
        s["seq"] = self.log.count()
        return s

    def events(self, since: int = 0) -> List[Dict[str, Any]]:
        return self.log.since(since)

    def stream(self, since: int = 0, poll: float = 0.25) -> Iterable[Dict[str, Any]]:
        """Yield events after ``since`` as they arrive, until the run ends."""
        log, seq = self.log, int(since)
        while True:
            for ev in log.wait(seq, poll):
                seq = ev["seq"]
                yield ev
            if log.run_id == "none" or (log.closed and seq >= log.count()):
                return

    def wait(self, timeout: Optional[float] = None) -> None:
        t = self._thread
        if t is not None:
            t.join(timeout)

    def start(self, project: Any, documents: Sequence[Dict[str, Any]], full: bool = False) -> Dict[str, Any]:
        proj = {"key": project, "name": recall.project_name(project)} if isinstance(project, str) else dict(project)
        if not proj.get("key"):
            raise ValueError("a project is required")
        with self._mu:
            if self._status["state"] == "running":
                raise JobBusy(dict(self._status))
            run_id = uuid.uuid4().hex[:8]
            self.log = EventLog(run_id)
            self._status = {**_run_status_blank(), "state": "running", "run": run_id, "project": proj,
                            "started_at": _now()}
            self._thread = threading.Thread(target=self._run, args=(proj, list(documents), bool(full), self.log),
                                            daemon=True, name="recall-index")
            self._thread.start()
            return dict(self._status)

    # -- internals

    def _set(self, **kw: Any) -> None:
        with self._mu:
            self._status.update(kw)

    def _wanted(self, doc: Dict[str, Any]) -> bool:
        if doc.get("type") == "image":
            return bool(self.images and getattr(self.embedder, "supports_images", False))
        return True

    def _mark_unreadable(self, project_key: str, doc: Dict[str, Any], lock_id: str, dim: int) -> None:
        """Record a document that could not be embedded as a zero-chunk row.

        Its cheap fingerprint is stored, so delta stops offering it as "new" on
        every visit (empty sessions, deleted transcripts, content the model
        rejects). If the document changes, the fingerprint changes and the
        next run tries it again.
        """
        try:
            self.store.put_document(project_key, doc, lock_id, dim, "unreadable", [], [], {})
        except Exception:  # noqa: BLE001 - bookkeeping must not stop the run
            pass

    def _prepare(self, doc: Dict[str, Any]) -> Optional[_Prepared]:
        t = doc.get("type")
        if t == "session":
            src = doc.get("source") or {}
            loaded = self.loader(doc.get("agent"), src.get("id"))
            if loaded is None:
                return None
            chunks, texts = recall.index_view(loaded[0])
            idxs = [int(c.get("idx", pos)) for pos, c in enumerate(chunks)]
            keep = [i for i, tx in enumerate(texts) if tx.strip()]
            return _Prepared([idxs[i] for i in keep], [texts[i] for i in keep], recall.fingerprint_texts(texts))
        if t == "image":
            data = self.image_reader(doc)
            if not data or len(data) > MAX_IMAGE_BYTES:
                return None
            return _Prepared([0], [], image_content_fp(data), image=data)
        text = self.text_reader(doc)
        if text is None:
            return None
        texts = text_chunks(text)
        keep = [i for i, tx in enumerate(texts) if tx.strip()]
        return _Prepared(keep, [texts[i] for i in keep], recall.fingerprint_texts(texts))

    def _ensure_lock(self, key: str) -> Tuple[str, Dict[str, Any]]:
        rec = self.store.get_lock(key)
        if rec is None:
            lock = self.lock_factory(self.embedder)
            self.store.set_lock(key, lock, "building")
            self.guard.forget(key)
            return lock_id_of(lock), lock
        if rec["state"] != "model_changed":
            ok, _why = self.guard.check(key, fresh=True)
            if ok:
                self.store.set_state(key, "building")
                return rec["lock_id"], rec["lock"]
        new_model = str((self.embedder.identity or {}).get("model") or "the current model")
        raise LockMismatch(
            f"This project was indexed with {_model_label(rec['lock'])}, which is no longer the configured model.",
            f"Re-index everything with {new_model}.")

    def _run(self, proj: Dict[str, Any], documents: List[Dict[str, Any]], full: bool, log: EventLog) -> None:
        key = proj["key"]
        t0 = self.clock()
        c = {"embedded": 0, "reused": 0, "tokens": 0, "done": 0, "skipped": 0, "removed": 0,
             "unreadable": 0, "vectors_sent": 0, "vectors_sampled_out": 0}
        by_type: Dict[str, int] = {}
        by_agent: Dict[str, int] = {}
        last_progress = [t0]
        last_vec: List[Optional[float]] = [None]
        locked = False

        def progress(force: bool = False) -> None:
            now = self.clock()
            if not force and now - last_progress[0] < PROGRESS_EVERY_S:
                return
            last_progress[0] = now
            per_sec = round(c["embedded"] / max(now - t0, 1e-9), 1)
            log.append("progress", documents_done=c["done"], chunks_embedded=c["embedded"],
                       chunks_reused=c["reused"], tokens=c["tokens"], per_sec=per_sec,
                       by_type=dict(by_type), by_agent=dict(by_agent))
            self._set(documents_done=c["done"], chunks_embedded=c["embedded"], chunks_reused=c["reused"],
                      tokens=c["tokens"], per_sec=per_sec, documents_skipped=c["skipped"],
                      documents_removed=c["removed"], documents_unreadable=c["unreadable"])

        try:
            if full:
                # Build (and probe) the new lock before touching the old index.
                new_lock = self.lock_factory(self.embedder)
                self.store.reset_project(key, new_lock, "building")
                self.guard.forget(key)
                lock_id, lock = lock_id_of(new_lock), new_lock
                stored = self.store.documents(key)
            else:
                stored = self.store.documents(key)
                lock_id, lock = self._ensure_lock(key)
            locked = True
            if self.inline_discover and self.images and self.embedder.supports_images:
                # Index images before their parent so a failed image is retried.
                documents = list(self.inline_discover(documents, stored)) + documents
            wanted = [d for d in documents if self._wanted(d) and d.get("doc_id")]
            seen = {d["doc_id"] for d in wanted}
            gone = [i for i, r in stored.items() if i not in seen and
                    not (r["type"] == "image" and not self._wanted(r))]
            todo = [d for d in wanted
                    if d["doc_id"] not in stored or stored[d["doc_id"]]["cheap_fp"] != (d.get("cheap_fp") or "")]
            totals_by_type: Dict[str, int] = {}
            for d in todo:
                totals_by_type[d.get("type")] = totals_by_type.get(d.get("type"), 0) + 1
            self._set(documents_total=len(todo))
            log.append("start", project=proj, full=full,
                       totals={"documents": len(todo), "by_type": totals_by_type,
                               "unchanged": len(wanted) - len(todo), "removed": len(gone)})
            dim = int(lock.get("dims") or (self.embedder.identity or {}).get("dims") or 0)
            if gone:
                c["removed"] = self.store.remove_documents(key, gone)
            c["skipped"] = len(wanted) - len(todo)
            projector = Projector(lock_id)
            min_gap = 1.0 / VECTOR_EVENTS_PER_SEC

            for doc in todo:
                try:
                    prep = self._prepare(doc)
                except Exception:  # noqa: BLE001 - one unreadable document does not stop the run
                    prep = None
                if prep is None:
                    c["unreadable"] += 1
                    self._mark_unreadable(key, doc, lock_id, dim)
                    continue
                title = _title(doc.get("title"))
                if prep.image is not None:
                    prefixed: List[str] = []
                    hashes = [chunk_hash("image:" + hashlib.sha256(prep.image).hexdigest())]
                else:
                    prefixed = [prefix_document(self.embedder, t, title) for t in prep.texts]
                    hashes = [chunk_hash(p) for p in prefixed]
                have = self.store.have_hashes(lock_id, hashes)
                missing: Dict[str, int] = {}
                for pos, h in enumerate(hashes):
                    if h not in have and h not in missing:
                        missing[h] = pos
                new_vecs: Dict[str, List[float]] = {}
                entries = list(missing.items())
                try:
                    for offset in range(0, len(entries), EMBED_BATCH):
                        batch = entries[offset:offset + EMBED_BATCH]
                        if prep.image is not None:
                            vecs = self.embedder.embed_images([prep.image])
                        else:
                            vecs = self.embedder.embed_texts(
                                [prep.texts[pos] for _, pos in batch], "document", titles=[title] * len(batch))
                        if len(vecs) != len(batch):
                            raise ValueError("embedder returned the wrong number of vectors")
                        for (h, _), v in zip(batch, vecs):
                            if dim and len(v) != dim:
                                raise ValueError("embedder returned vectors of the wrong length")
                            new_vecs[h] = [float(x) for x in v]
                        c["embedded"] += len(batch)
                        if prefixed:
                            c["tokens"] += sum(len(prefixed[pos]) for _, pos in batch) // 4
                        # Keep progress moving during a long session without
                        # exposing a partially written document to readers.
                        if offset + len(batch) < len(entries):
                            progress()
                except (ImageDecodeError, BadVectorError):
                    # One document's content the model could not embed: skip
                    # it and keep indexing. Provider outages still stop the run.
                    c["unreadable"] += 1
                    self._mark_unreadable(key, doc, lock_id, dim)
                    continue
                first = next(iter(new_vecs.values()), None)
                self.store.put_document(key, doc, lock_id, dim or len(first or []),
                                        prep.content_fp, prep.idxs, hashes, new_vecs)
                n_new = len(entries)
                c["reused"] += len(hashes) - n_new
                c["done"] += 1
                dtype, agent = str(doc.get("type")), str(doc.get("agent"))
                by_type[dtype] = by_type.get(dtype, 0) + 1
                by_agent[agent] = by_agent.get(agent, 0) + 1
                vec = None
                if hashes:
                    first_vector = new_vecs.get(hashes[0])
                    vec = array("f", first_vector) if first_vector is not None else self.store.get_vector(lock_id, hashes[0])
                xy = projector.xy(vec) if vec is not None else None
                log.append("doc", doc_id=doc["doc_id"], doc_type=dtype, agent=agent, title=title,
                           chunks=len(hashes), reused=len(hashes) - n_new, xy=xy)
                if vec is not None:
                    now = self.clock()
                    if last_vec[0] is None or now - last_vec[0] >= min_gap:
                        last_vec[0] = now
                        c["vectors_sent"] += 1
                        log.append("vector", doc_id=doc["doc_id"], doc_type=dtype,
                                   preview=[round(x, 4) for x in vec[:24]], xy=xy)
                    else:
                        c["vectors_sampled_out"] += 1
                progress()
            progress(force=True)
            self.store.set_state(key, "ready")
            summary = {"documents": c["done"], "chunks_embedded": c["embedded"], "chunks_reused": c["reused"],
                       "tokens": c["tokens"], "unchanged": c["skipped"], "removed": c["removed"],
                       "unreadable": c["unreadable"], "vector_events": c["vectors_sent"],
                       "vector_events_sampled_out": c["vectors_sampled_out"],
                       "by_type": dict(by_type), "by_agent": dict(by_agent)}
            self._set(state="done", finished_at=_now())
            log.append("done", elapsed_s=round(self.clock() - t0, 3), summary=summary)
        except LockMismatch as e:
            self._fail(log, key, str(e), e.fix, "model_changed")
        except Exception as e:  # noqa: BLE001
            if isinstance(e, (EmbedError, ProviderEmbedError)):
                self._fail(log, key, str(e), str(getattr(e, "fix", "") or "Fix the embedder and run the index again."),
                           "ready" if locked else None)
            else:
                self._fail(log, key, f"Indexing stopped unexpectedly ({type(e).__name__}).",
                           "Run it again. Documents already indexed are kept.", "ready" if locked else None)

    def _fail(self, log: EventLog, key: str, message: str, fix: str, state: Optional[str]) -> None:
        if state:
            try:
                self.store.set_state(key, state)
            except Exception:  # noqa: BLE001
                pass
        self._set(state="error", error={"message": message, "fix": fix}, finished_at=_now())
        log.append("error", message=message, fix=fix)


# ---------------------------------------------------------------- search

def semantic_search(store: VectorStore, embedder: Any, project_key: str, query: str, *,
                    types: Optional[Iterable[str]] = None, k: int = TOP_K,
                    guard: Optional[LockGuard] = None,
                    is_current: Optional[Callable[[Dict[str, Any]], bool]] = None) -> Dict[str, Any]:
    """Rank the project's chunks under its current lock.

    Returns ``{"state", "hits", "stale"}``. ``state`` is ``never_indexed``,
    ``ready`` or ``model_changed``; the last two give no hits, so the caller
    falls back to keyword. ``is_current(doc_row)`` is the query-time staleness
    check (current content_fp equals the stored one); documents failing it are
    left out and listed in ``stale``.
    """
    guard = guard or LockGuard(store, embedder)
    state = guard.state(project_key)
    rec = store.get_lock(project_key) if state == "ready" else None
    if rec is None:
        return {"state": state, "hits": [], "stale": []}
    dim = int(rec["lock"].get("dims") or 0)
    qv = embedder.embed_texts([query], "query")[0]
    ranked = store.search_project(project_key, rec["lock_id"], qv, dim, types=types, k=k)
    docs = store.documents(project_key)
    hits: List[Dict[str, Any]] = []
    stale: List[str] = []
    verdict: Dict[str, bool] = {}
    for doc_id, idx, score in ranked:
        row = docs.get(doc_id)
        if row is None:
            continue
        if is_current is not None:
            if doc_id not in verdict:
                try:
                    verdict[doc_id] = bool(is_current(row))
                except Exception:  # noqa: BLE001 - unreadable now means unverifiable
                    verdict[doc_id] = False
                if not verdict[doc_id]:
                    stale.append(doc_id)
            if not verdict[doc_id]:
                continue
        hits.append({"doc_id": doc_id, "doc_type": row["type"], "agent": row["agent"], "title": row["title"],
                     "source": row["source"], "idx": idx, "score": round(score, 4)})
    return {"state": state, "hits": hits, "stale": stale}


def make_semantic_v3(store: VectorStore, embedder: Any, project_key: str,
                     guard: Optional[LockGuard] = None, k: int = TOP_K) -> recall.Semantic:
    """``recall.search(semantic=...)`` bundle over one project's v3 index
    (session documents only; other types go through ``semantic_search``).
    A project that is not ``ready`` reports every session as not indexed, so
    search falls back to keyword and says so in its coverage."""
    guard = guard or LockGuard(store, embedder)
    cache: Dict[str, Any] = {}

    def ready() -> bool:
        if "ready" not in cache:
            cache["ready"] = guard.state(project_key) == "ready"
        return cache["ready"]

    def docs() -> Dict[str, Dict[str, Any]]:
        if "docs" not in cache:
            cache["docs"] = store.documents(project_key)
        return cache["docs"]

    def is_current(agent: str, sid: str, fp: str) -> bool:
        if not ready():
            return False
        row = docs().get(session_doc_id(agent, sid))
        return bool(row and row["content_fp"] == fp)

    def rank(q: str, allowed: set) -> List[Tuple[str, str, int, float]]:
        if not ready() or not allowed:
            return []
        rec = store.get_lock(project_key)
        if rec is None:
            return []
        by_doc = {session_doc_id(a, i): (a, i) for a, i in allowed}
        qv = embedder.embed_texts([q], "query")[0]
        res = store.search_project(project_key, rec["lock_id"], qv, int(rec["lock"].get("dims") or 0),
                                   types=("session",), doc_ids=set(by_doc), k=k)
        return [(by_doc[d][0], by_doc[d][1], idx, sc) for d, idx, sc in res]

    return recall.Semantic(model=str((embedder.identity or {}).get("model") or ""), is_current=is_current, rank=rank)
