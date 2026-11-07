"""Real token usage for Antigravity sessions, read from each conversation's own SQLite store.

Since June 2026 every Antigravity surface (the `agy` CLI, the IDE and the 2.0 app)
keeps a conversation as ``~/.gemini/antigravity*/conversations/<id>.db``. Its
``gen_metadata`` table holds one protobuf row per model call, and that row is the
only local record of what the call actually consumed. The ``brain/`` transcripts
the scanner used before carry no token accounting at all, which is why every
Antigravity session used to be an estimate (characters / 4) priced at $0.

Field numbers come from openusage's decoder (FelixIsaac, openusage#1058 / #1120),
which was worked out against the language-server binary and pinned by its tests.
There is no public schema; they can move in a future Antigravity build, so every
read here is defensive and a row that does not decode is skipped, never guessed.

    gen_metadata.data
      1  event
         4   usage     1 system-prompt tokens   2 input tokens
                       3 output tokens          5 cache-read tokens
         9   timing    4 Timestamp { 1 seconds }
         19  model id  e.g. "gemini-3.8-flash", or "gemini-pro-default" on the picker default
         21  label     e.g. "Gemini 3.1 Pro (High)", the model that actually served the turn

Newer builds leave the timing out and date the call in ``steps.metadata`` (field 1 is
a Timestamp), correlated by ``idx``.

Usage is aggregated to (model, UTC day) buckets rather than one session total so each
bucket can be priced at the rate in force that day. Cost is computed by the caller at
read time and is never stored, so a pricing change can't leave a stale number behind
in the scan cache.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# A real conversation can hold generation rows hundreds of megabytes long (inline
# media). Nothing we read lives in them, so they are skipped before SQLite hands
# the bytes over.
MAX_BLOB_BYTES = 1_048_576


# --- protobuf wire format ----------------------------------------------------

def _varint(buf: bytes, i: int) -> Tuple[int, int]:
    value = 0
    for n in range(10):
        if i + n >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[i + n]
        value |= (byte & 0x7F) << (7 * n)
        if not byte & 0x80:
            return value, i + n + 1
    raise ValueError("varint too long")


def _field(buf: Optional[bytes], number: int) -> Any:
    """First occurrence of field ``number``: int for a varint, bytes for a
    length-delimited field, None if absent or the message does not parse."""
    if not buf:
        return None
    i = 0
    try:
        while i < len(buf):
            tag, i = _varint(buf, i)
            num, wire = tag >> 3, tag & 7
            if num == 0:
                return None
            if wire == 0:
                value, i = _varint(buf, i)
                if num == number:
                    return value
            elif wire == 2:
                length, i = _varint(buf, i)
                if length > len(buf) - i:
                    return None
                if num == number:
                    return bytes(buf[i:i + length])
                i += length
            elif wire in (1, 5):
                width = 8 if wire == 1 else 4
                if len(buf) - i < width:
                    return None
                i += width
            else:
                return None
    except ValueError:
        return None
    return None


def _message(buf: Optional[bytes], number: int) -> Optional[bytes]:
    value = _field(buf, number)
    return value if isinstance(value, bytes) else None


def _count(buf: Optional[bytes], number: int) -> int:
    value = _field(buf, number)
    return value if isinstance(value, int) else 0


def _text(buf: Optional[bytes], number: int) -> Optional[str]:
    raw = _message(buf, number)
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    return text or None


# Seconds, so anything past 2100 is not a date this field ever held: a build
# that switched to milliseconds, or a varint misread as a timestamp. Letting it
# through would make datetime raise and cost the whole conversation.
_MAX_TIMESTAMP = 4_102_444_800  # 2100-01-01T00:00:00Z


def _timestamp(message: Optional[bytes]) -> Optional[int]:
    seconds = _field(message, 1)
    return seconds if isinstance(seconds, int) and 0 < seconds < _MAX_TIMESTAMP else None


def decode_generation(blob: bytes, step_metadata: Optional[bytes] = None) -> Optional[Dict[str, Any]]:
    """One model call from a ``gen_metadata.data`` blob, or None.

    None covers three different cases on purpose: a blob that does not parse, a
    prompt-context record (a system-prompt count with no model and nothing
    generated), and a call with no timestamp at all. The last is dropped rather
    than dated from the file's mtime, which moves on every write.
    """
    event = _message(blob, 1)
    usage = _message(event, 4)
    if usage is None:
        return None
    model_id = _text(event, 19)
    label = _text(event, 21)
    system_prompt = _count(usage, 1)
    input_tokens = _count(usage, 2)
    output_tokens = _count(usage, 3)
    cache_read = _count(usage, 5)

    generated = bool(input_tokens or output_tokens or cache_read)
    if not (model_id or label or generated):
        return None
    if not generated and not system_prompt:
        return None

    seconds = _timestamp(_message(_message(event, 9), 4))
    if seconds is None and step_metadata:
        seconds = _timestamp(_message(step_metadata, 1))
    if seconds is None:
        return None

    return {
        "model_id": model_id,
        "label": label,
        # The system prompt is billed as input on every call.
        "input": system_prompt + input_tokens,
        "output": output_tokens,
        "cached": cache_read,
        "ts": seconds,
    }


# --- model names ---------------------------------------------------------------

# The two vendors order their labels differently: "Gemini 3.1 Pro", "Claude Opus 4.6".
_GEMINI_LABEL_RE = re.compile(
    r"^Gemini\s+(\d+(?:\.\d+)*)\s+(Flash[ -]Lite|Pro|Flash|Ultra|Nano)\b", re.IGNORECASE)
_CLAUDE_LABEL_RE = re.compile(
    r"^Claude\s+(Opus|Sonnet|Haiku)\s+(\d+(?:\.\d+)*)\b", re.IGNORECASE)
# Reasoning-effort variants bill at the base model's rate.
_EFFORT_SUFFIX_RE = re.compile(r"-(?:minimal|low|medium|high)$")
# Antigravity's names for "whatever the picker defaults to". With no label to say
# which model actually answered, openusage prices the Pro placeholder as the
# current Pro model; the same is done here.
_PLACEHOLDERS = {"gemini-pro-default": "gemini-3.1-pro"}


def _from_label(label: str) -> Optional[str]:
    """"Gemini 3.1 Pro (High)" -> "gemini-3.1-pro"; "Claude Opus 4.6 (Thinking)" -> "claude-opus-4-6".

    The version keeps its dots for Gemini and becomes dashes for Claude, because
    that is how each vendor spells its model ids — and the pricing table also
    holds dashed Gemini decoys ("gemini-3-1-pro") priced at zero.
    """
    text = label.strip()
    m = _GEMINI_LABEL_RE.match(text)
    if m:
        return f"gemini-{m.group(1)}-{m.group(2).lower().replace(' ', '-')}"
    m = _CLAUDE_LABEL_RE.match(text)
    if m:
        return f"claude-{m.group(1).lower()}-{m.group(2).replace('.', '-')}"
    return None


def _from_id(model_id: str) -> Optional[str]:
    m = model_id.strip().lower()
    if m.endswith("-tiered"):
        m = m[: -len("-tiered")]
    if m in _PLACEHOLDERS:
        return _PLACEHOLDERS[m]
    if m.endswith("-default"):
        return None
    return _EFFORT_SUFFIX_RE.sub("", m) or None


def candidate_names(model_id: Optional[str], label: Optional[str]) -> List[str]:
    """Every name one call could be reported under, most trustworthy first.

    A placeholder id ("gemini-pro-default") says nothing, so the label, which
    records the model that really served the turn, goes first; otherwise the
    concrete id does. A bare "gemini" is never produced.
    """
    placeholder = bool(model_id) and model_id.strip().lower().replace("-tiered", "").endswith("-default")
    order = ("label", "id") if placeholder or not model_id else ("id", "label")
    names: List[str] = []
    for source in order:
        if source == "id" and model_id:
            name = _from_id(model_id)
        elif source == "label" and label:
            name = _from_label(label)
        else:
            name = None
        if name and name not in names:
            names.append(name)
    return names


def canonical_model(model_id: Optional[str], label: Optional[str],
                    is_known: Callable[[str], bool] = lambda _name: False) -> Optional[str]:
    """The model to price one call under, or None when no name is known exactly.

    Some concrete-looking ids are internal aliases: "gemini-3-flash-a" arrives with
    the label "Gemini 3.5 Flash" every time. The pricing table fuzzy-matches, so the
    alias on its own would be billed as gemini-3-flash, at a sixth of the real
    rate, and a bare "gemini" would match a generic rate. Being priced therefore
    proves nothing; only a name ``is_known`` finds in the table exactly is used.

    With no such name the call is left unpriced rather than given the nearest
    rate. Pricing is resolved at read time, so it is priced correctly as soon as
    the table learns the model.
    """
    for name in candidate_names(model_id, label):
        if is_known(name):
            return name
    return None


# --- one conversation database -------------------------------------------------

def _connect(path: Path) -> sqlite3.Connection:
    # mode=ro reads the WAL too, which is where a live session's newest calls sit.
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=2)


def read_usage(path: Path) -> Optional[Dict[str, Any]]:
    """Aggregate token usage for one conversation ``.db``.

    Returns None when the file has no ``gen_metadata`` table or cannot be read, so
    the caller can fall back to its estimate. Otherwise a JSON-serialisable dict:

        {"buckets": [{"model_id": str|None, "label": str|None, "day": "YYYY-MM-DD",
                      "input": int, "output": int, "cached": int, "calls": int}],
         "first_ts": int|None, "last_ts": int|None,
         "calls": int, "oversized": int}
    """
    try:
        con = _connect(path)
    except (sqlite3.Error, OSError, ValueError):
        return None
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "gen_metadata" not in tables:
            return None
        has_step_metadata = "steps" in tables and bool(con.execute(
            "SELECT 1 FROM pragma_table_info('steps') WHERE name = 'metadata'").fetchone())
        step_column = (
            f", (SELECT CASE WHEN length(metadata) <= {MAX_BLOB_BYTES} THEN metadata END"
            " FROM steps WHERE steps.idx = g.idx)" if has_step_metadata else ", NULL")
        rows = con.execute(
            f"SELECT CASE WHEN length(g.data) <= {MAX_BLOB_BYTES} THEN g.data END{step_column}"
            " FROM gen_metadata g WHERE g.data IS NOT NULL ORDER BY g.idx")

        buckets: Dict[Tuple[Optional[str], str], Dict[str, Any]] = {}
        first_ts = last_ts = None
        calls = oversized = 0
        for data, step_meta in rows:
            if data is None:
                oversized += 1
                continue
            event = decode_generation(bytes(data), bytes(step_meta) if step_meta else None)
            if event is None:
                continue
            day = datetime.fromtimestamp(event["ts"], tz=timezone.utc).strftime("%Y-%m-%d")
            # Raw names are kept and resolved at read time, against whatever the
            # pricing table knows then, so a table update needs no cache bump.
            key = (event["model_id"], event["label"], day)
            bucket = buckets.setdefault(key, {
                "model_id": event["model_id"], "label": event["label"], "day": day,
                "input": 0, "output": 0, "cached": 0, "calls": 0})
            bucket["input"] += event["input"]
            bucket["output"] += event["output"]
            bucket["cached"] += event["cached"]
            bucket["calls"] += 1
            calls += 1
            first_ts = event["ts"] if first_ts is None else min(first_ts, event["ts"])
            last_ts = event["ts"] if last_ts is None else max(last_ts, event["ts"])
    except sqlite3.Error:
        return None
    finally:
        con.close()

    return {
        "buckets": sorted(buckets.values(),
                          key=lambda b: (b["day"], b["model_id"] or "", b["label"] or "")),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "calls": calls,
        "oversized": oversized,
    }


def summarize(usage: Dict[str, Any], price: Callable[..., float],
              is_known: Callable[[str], bool] = lambda _name: False) -> Dict[str, Any]:
    """Session totals from ``read_usage`` output.

    ``price(model, input, output, cached, day)`` returns USD for one bucket, and
    ``is_known(model)`` says whether the pricing table holds that exact id (see
    ``canonical_model``). Calls with no exactly-known name are counted in the
    tokens but not priced: there is no rate to charge them at, and the nearest
    rate would be a number we made up. They still carry their best name for
    display, in ``unpriced_models``.

    ``model`` is the model with the most tokens, which is what the session list and
    the by-model breakdown show: a priced one if there is any, else the best
    unpriced name.
    """
    tokens = {"input": 0, "output": 0, "cached": 0}
    cost = 0.0
    per_model: Dict[str, int] = {}
    unpriced_models: Dict[str, int] = {}
    unpriced = 0
    for b in usage.get("buckets") or []:
        for key in tokens:
            tokens[key] += b[key]
        volume = b["input"] + b["output"] + b["cached"]
        model = canonical_model(b.get("model_id"), b.get("label"), is_known)
        if model:
            cost += price(model, b["input"], b["output"], b["cached"], b["day"])
            per_model[model] = per_model.get(model, 0) + volume
        else:
            unpriced += volume
            names = candidate_names(b.get("model_id"), b.get("label"))
            if names:
                unpriced_models[names[0]] = unpriced_models.get(names[0], 0) + volume
    tokens["total"] = tokens["input"] + tokens["output"] + tokens["cached"]
    tokens["cost"] = cost
    ranked = per_model or unpriced_models
    model = max(ranked, key=ranked.get) if ranked else None
    return {"tokens": tokens, "cost": cost, "model": model, "models": per_model,
            "unpriced_models": unpriced_models, "unpriced_tokens": unpriced}


def conversation_files(gemini_dir: Path) -> Dict[str, Path]:
    """Every ``<id>.db`` under ``~/.gemini/antigravity*/conversations``, one per id.

    Surfaces are discovered by prefix so a new one is picked up without a code
    change, except ``antigravity-backup``: it mirrors the others, and counting it
    would double every session in it. When an id exists in more than one store,
    the largest file wins, being the one with the most calls recorded.
    """
    found: Dict[str, Path] = {}
    try:
        stores = sorted(p for p in gemini_dir.iterdir()
                        if p.is_dir() and p.name.startswith("antigravity")
                        and p.name != "antigravity-backup")
    except OSError:
        return found
    seen: set = set()
    for store in stores:
        conv = store / "conversations"
        try:
            dbs: List[Path] = sorted(conv.glob("*.db")) if conv.is_dir() else []
        except OSError:
            continue
        for db in dbs:
            try:
                real = db.resolve()
                if real in seen:
                    continue
                seen.add(real)
                current = found.get(db.stem)
                if current is None or db.stat().st_size > current.stat().st_size:
                    found[db.stem] = db
            except OSError:
                continue
    return found


def source_mtime(path: Path) -> float:
    """The newest write to a conversation, counting its WAL: a live session
    appends to ``<id>.db-wal`` long before anything reaches ``<id>.db``."""
    stamps = []
    for candidate in (path, path.with_name(path.name + "-wal")):
        try:
            stamps.append(candidate.stat().st_mtime)
        except OSError:
            continue
    return max(stamps) if stamps else 0.0
