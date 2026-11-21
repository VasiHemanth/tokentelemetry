"""Semantic index for recall: settings, Ollama embedder, vector store, build job.

Design: docs/design/cross-harness-recall-v2.md. Everything is local. Vectors
are float32 blobs in SQLite, scored in pure Python (numpy is used per batch
when importable, never required). Ollama must be on loopback.
"""
from __future__ import annotations

import heapq
import json
import math
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit

import recall
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

DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "model": DEFAULT_MODEL,
    "ollama_url": DEFAULT_URL,
    "dims": DEFAULT_DIMS,
    "default_mode": "keyword",
}

# One fingerprint implementation, shared with recall.search().
session_fingerprint = recall.session_fingerprint


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- settings

def settings_path() -> Path:
    return data_dir() / "recall.json"


def index_path() -> Path:
    return data_dir() / "recall_index.db"


def validate_settings(sem: Dict[str, Any]) -> Dict[str, Any]:
    """Return a clean, complete semantic settings dict or raise ValueError."""
    if not isinstance(sem, dict):
        raise ValueError("semantic settings must be an object")
    out = {**DEFAULTS, **{k: v for k, v in sem.items() if k in DEFAULTS}}
    if not isinstance(out["enabled"], bool):
        raise ValueError("enabled must be true or false")
    model = out["model"]
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty name, for example " + DEFAULT_MODEL)
    out["model"] = model.strip()
    url = out["ollama_url"]
    if not isinstance(url, str) or not url.strip():
        raise ValueError("ollama_url must be a loopback URL such as " + DEFAULT_URL)
    url = url.strip().rstrip("/")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        raise ValueError("ollama_url is not a valid URL") from None
    if parts.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS:
        raise ValueError("ollama_url must point at this machine (127.0.0.1, localhost or ::1)")
    out["ollama_url"] = url
    dims = out["dims"]
    if isinstance(dims, bool) or dims not in DIMS_ALLOWED:
        raise ValueError("dims must be one of " + ", ".join(str(d) for d in DIMS_ALLOWED))
    if out["default_mode"] not in MODES:
        raise ValueError("default_mode must be keyword, semantic or hybrid")
    return out


def load_settings(path: Optional[Path] = None) -> Dict[str, Any]:
    """Settings with defaults filled in. A missing or damaged file, or one
    holding values that no longer validate, yields the defaults."""
    p = path or settings_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        sem = raw.get("semantic") if isinstance(raw, dict) else None
        return {"semantic": validate_settings(sem if isinstance(sem, dict) else {})}
    except (OSError, ValueError):
        return {"semantic": dict(DEFAULTS)}


def save_settings(settings: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
    clean = {"semantic": validate_settings(settings.get("semantic") or {})}
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return clean


def update_settings(patch: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
    """Merge ``patch`` (``{"semantic": {...}}``) into the stored settings."""
    if not isinstance(patch, dict) or not isinstance(patch.get("semantic", {}), dict):
        raise ValueError("body must look like {\"semantic\": {...}}")
    cur = load_settings(path)
    merged = {"semantic": {**cur["semantic"], **(patch.get("semantic") or {})}}
    return save_settings(merged, path)


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
