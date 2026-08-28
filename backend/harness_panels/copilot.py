"""GitHub Copilot CLI panel — recorded billing units, latency, checkpoints.

`~/.copilot/session-store.db` is the only store on a typical machine that records
what a request actually cost in the vendor's own billing units. Copilot bills in
*premium requests*, not tokens: `total_nano_aiu` is the billed amount in
nano-AIU, and `request_multiplier` is the per-model factor applied to it. There
is no way to derive either from a transcript, so this table is the difference
between reporting Copilot cost and guessing at it.

It also carries `time_to_first_token_ms` and `inter_token_latency_ms`, which give
a measured tokens-per-second instead of the total-latency approximation the power
model otherwise has to use.

`turns.user_message` / `assistant_response` hold raw prompt text. This module
never selects those columns.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    HOME, dir_size, field, human_bytes, iso, newest_mtime, not_installed,
    panel, preview, ro_sqlite, safe, section, table_exists, tilde, unavailable,
)

COPILOT_DIR = HOME / ".copilot"
STORE_DB = COPILOT_DIR / "session-store.db"

EVENT_ROWS = 25

# Copilot reports billed usage in nano-AIU (1e9 nano-AIU = 1 AIU, its premium
# request unit). Dividing here keeps the unit conversion in one place.
NANO_PER_AIU = 1_000_000_000


def _ms(value: Any) -> Optional[str]:
    """Render a millisecond duration at a precision a human can read."""
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return f"{n:.0f} ms" if n < 1000 else f"{n / 1000:.1f} s"


def _usage_summary(conn) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT COUNT(*) n, "
        "       SUM(COALESCE(total_nano_aiu,0)) aiu, "
        "       AVG(NULLIF(request_multiplier,0)) avg_mult, "
        "       MAX(COALESCE(request_multiplier,0)) max_mult "
        "FROM assistant_usage_events"
    ).fetchone()
    if not row or not row["n"]:
        return None

    aiu = (row["aiu"] or 0) / NANO_PER_AIU
    detail_bits = [f"{row['n']} requests"]
    if row["avg_mult"]:
        detail_bits.append(f"avg multiplier ×{row['avg_mult']:.2f}")
    if row["max_mult"]:
        detail_bits.append(f"peak ×{row['max_mult']:.2f}")

    # There is no local record of the account's monthly premium-request
    # allowance, so a percentage would be invented. Show the absolute figure and
    # say what it is instead of drawing a bar against a made-up denominator.
    return section(
        "fields", "Premium request usage",
        tilde(STORE_DB) + " → assistant_usage_events",
        fields=[
            field("Billed units (AIU)", f"{aiu:,.3f}"),
            field("Requests", row["n"]),
            field("Multiplier", " · ".join(detail_bits[1:]) or "—"),
        ],
        note="Copilot bills premium requests in AIU, not tokens. This is the "
             "amount Copilot itself recorded; TokenTelemetry cannot derive it "
             "from a transcript. No local file states the plan allowance, so "
             "this is an absolute total rather than a percentage.",
    )


def _usage_events(conn) -> Optional[Dict[str, Any]]:
    total = conn.execute("SELECT COUNT(*) FROM assistant_usage_events").fetchone()[0]
    if not total:
        return None
    rows: List[List[Any]] = []
    for r in conn.execute(
        "SELECT model, input_tokens, output_tokens, cache_read_tokens, "
        "       cache_write_tokens, reasoning_tokens, total_nano_aiu, "
        "       request_multiplier, duration_ms, time_to_first_token_ms, "
        "       inter_token_latency_ms, finish_reason, created_at "
        "FROM assistant_usage_events ORDER BY id DESC LIMIT ?", (EVENT_ROWS,)
    ):
        # inter_token_latency_ms is the mean gap between output tokens, so its
        # reciprocal is a true generation rate — unlike output/total-latency,
        # which is diluted by time-to-first-token and tool round-trips.
        #
        # Guard the degenerate case: rows with a handful of output tokens report
        # sub-millisecond gaps (0.44 ms is present on this machine), which would
        # render as 2,272 tok/s. That is an artefact of averaging over almost no
        # tokens, not a measurement, so it is suppressed rather than shown.
        itl = r["inter_token_latency_ms"] or 0
        tok_s = round(1000.0 / itl, 1) if itl >= 1.0 else None
        rows.append([
            r["model"] or "—",
            r["input_tokens"] or 0,
            r["output_tokens"] or 0,
            r["cache_read_tokens"] or 0,
            r["reasoning_tokens"] or 0,
            round((r["total_nano_aiu"] or 0) / NANO_PER_AIU, 4),
            # Stored to microsecond precision; six decimal places in a table cell
            # is noise, and past a second the useful unit is seconds.
            _ms(r["time_to_first_token_ms"]),
            tok_s,
            r["finish_reason"] or "—",
            r["created_at"],
        ])
    return section(
        "table", "Per-request detail", tilde(STORE_DB) + " → assistant_usage_events",
        columns=["Model", "In", "Out", "Cache rd", "Reasoning", "AIU",
                 "TTFT", "tok/s", "Finish", "When"],
        rows=rows, total=total,
        note="tok/s is derived from inter_token_latency_ms, a true generation "
             "rate rather than output tokens over total wall-clock."
             + ("" if total <= EVENT_ROWS else f" Showing {EVENT_ROWS} of {total}."),
    )


def _checkpoints(conn) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Structured progress summaries. Returns (section, unavailable)."""
    if not table_exists(conn, "checkpoints"):
        return None, None
    total = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    if not total:
        return section(
            "checkpoints", "Checkpoints", tilde(STORE_DB) + " → checkpoints",
            columns=["Title", "Work done", "Next steps", "When"], rows=[],
            empty_reason="Copilot writes structured checkpoints — title, work done, "
                         "important files, next steps — but none exist on this machine yet.",
        ), None
    rows = [
        [preview(r["title"]),
         preview(r["work_done"]),
         preview(r["next_steps"]),
         r["created_at"]]
        for r in conn.execute(
            "SELECT title, work_done, next_steps, created_at FROM checkpoints "
            "ORDER BY id DESC LIMIT 15")
    ]
    return section(
        "checkpoints", "Checkpoints", tilde(STORE_DB) + " → checkpoints",
        columns=["Title", "Work done", "Next steps", "When"], rows=rows, total=total,
    ), None


def _sessions(conn) -> Optional[Dict[str, Any]]:
    if not table_exists(conn, "sessions"):
        return None
    total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if not total:
        return None
    rows = [
        [r["repository"] or "—", r["branch"] or "—",
         Path(str(r["cwd"] or "")).name or "—",
         r["host_type"] or "—", r["updated_at"]]
        for r in conn.execute(
            "SELECT repository, branch, cwd, host_type, updated_at FROM sessions "
            "ORDER BY updated_at DESC LIMIT 20")
    ]
    return section(
        "table", "Sessions", tilde(STORE_DB) + " → sessions",
        columns=["Repository", "Branch", "Directory", "Host", "Updated"],
        rows=rows, total=total,
        note="Prompt and response columns exist in this database but are never read.",
    )


def _files_touched(conn) -> Optional[Dict[str, Any]]:
    if not table_exists(conn, "session_files"):
        return None
    rows = [
        [r["file_path"], r["tool_name"] or "—", r["n"]]
        for r in conn.execute(
            "SELECT file_path, tool_name, COUNT(*) n FROM session_files "
            "GROUP BY file_path ORDER BY n DESC LIMIT 15")
    ]
    if not rows:
        return None
    return section(
        "table", "Files touched", tilde(STORE_DB) + " → session_files",
        columns=["Path", "Tool", "Sessions"], rows=rows,
    )


def _skills() -> Optional[Dict[str, Any]]:
    root = COPILOT_DIR / "skills"
    if not root.is_dir():
        return None
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    if not names:
        return None
    return section(
        "chips", "Skills", tilde(root),
        rows=[[n] for n in names], columns=["Name"],
        note="Several of these are the shared marketplace pack also installed "
             "under other agents; they are the same files, not separate copies.",
    )


def _disk() -> Optional[Dict[str, Any]]:
    if not COPILOT_DIR.is_dir():
        return None
    total, complete = dir_size(COPILOT_DIR)
    parts = []
    for child in COPILOT_DIR.iterdir():
        try:
            size = dir_size(child)[0] if child.is_dir() else child.lstat().st_size
        except OSError:
            continue
        if size > 64 * 1024:
            parts.append({"label": child.name, "bytes": size})
    parts.sort(key=lambda p: -p["bytes"])
    return {"total_bytes": total, "total_human": human_bytes(total),
            "parts": parts[:8], "complete": complete}


def build(*, with_disk: bool = True) -> Dict[str, Any]:
    if not COPILOT_DIR.is_dir():
        return not_installed("copilot")

    sections: List[Dict[str, Any]] = []
    not_avail: List[Dict[str, Any]] = []

    conn = ro_sqlite(STORE_DB)
    if conn is not None:
        try:
            if table_exists(conn, "assistant_usage_events"):
                for step in (_usage_summary, _usage_events):
                    s = safe(lambda st=step: st(conn), f"copilot {step.__name__}")
                    if s:
                        sections.append(s)
            s = safe(lambda: _sessions(conn), "copilot sessions")
            if s:
                sections.append(s)
            ck, ck_missing = safe(lambda: _checkpoints(conn), "copilot ckpt") or (None, None)
            if ck:
                sections.append(ck)
            if ck_missing:
                not_avail.append(ck_missing)
            s = safe(lambda: _files_touched(conn), "copilot files")
            if s:
                sections.append(s)
        finally:
            conn.close()

    s = safe(_skills, "copilot skills")
    if s:
        sections.append(s)

    not_avail.append(unavailable(
        "schedules",
        "Copilot CLI can schedule prompts, but the schedule lives in the GitHub "
        "cloud rather than in a local file."))

    # settings.json is small and safe. config.json in this directory is NOT valid
    # JSON on at least some installs, so it is never parsed.
    model = None
    settings = safe(
        lambda: json.loads((COPILOT_DIR / "settings.json").read_text(encoding="utf-8")),
        "copilot settings")
    if isinstance(settings, dict):
        model = settings.get("model")
    if model:
        sections.append(section(
            "fields", "Configuration", tilde(COPILOT_DIR / "settings.json"),
            fields=[field("Model", str(model))]))

    last = newest_mtime([STORE_DB, COPILOT_DIR / "session-state", COPILOT_DIR / "logs"])

    return panel(
        "copilot", COPILOT_DIR,
        sections=sections, not_available=not_avail,
        last_active=iso(last), disk=safe(_disk, "copilot disk") if with_disk else None,
    )
