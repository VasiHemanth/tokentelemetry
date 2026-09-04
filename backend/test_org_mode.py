"""Tests for org mode (self-hosted collector): /org/ingest, /org/status,
/org/summary and the org_store SQLite layer.

Pins the API contract both sides depend on:

  * /org/ingest requires a valid X-TT-Machine-Token on EVERY request, even
    loopback, and resolves the machine label server-side (body can't spoof it);
  * re-sending the same batch upserts (accepted 0, updated N) and totals in
    /org/summary do not move — idempotency is proven by the numbers;
  * /org/status flips `enabled` on org.json presence;
  * summary rollups (by_machine / by_agent / by_project, tokens desc) are exact;
  * the RemoteAuthMiddleware bypass: a remote machine WITHOUT TT_AUTH_TOKEN can
    still reach /org/ingest when it holds a machine token.

Follows test_remote_auth.py: no httpx — the real ASGI app is driven with
constructed scopes, which also lets us set the client IP. State is isolated by
pointing TOKENTELEMETRY_DATA_DIR at a temp dir BEFORE importing main, so
org.json / org.db never touch the real ~/.tokentelemetry.
Run directly:  python backend/test_org_mode.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# Must be set before main (and org_store) resolve any paths.
_TMP = tempfile.mkdtemp(prefix="tt-org-test-")
os.environ["TOKENTELEMETRY_DATA_DIR"] = _TMP

import main  # noqa: E402
from main import app  # noqa: E402
import org_store  # noqa: E402


async def _request(method, path, *, headers=None, body=None, client=("127.0.0.1", 5555)):
    """Send one request through the real ASGI app; return (status, json_or_none)."""
    payload = json.dumps(body).encode() if body is not None else b""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if body is not None:
        raw_headers.append((b"content-type", b"application/json"))
        raw_headers.append((b"content-length", str(len(payload)).encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
    }
    status = {"code": None}
    body_parts: list = []
    pending = [{"type": "http.request", "body": payload, "more_body": False}]

    async def receive():
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
        elif message["type"] == "http.response.body":
            body_parts.append(message.get("body", b""))

    await app(scope, receive, send)
    raw = b"".join(body_parts)
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = None
    return status["code"], data


def _call(method, path, **kw):
    return asyncio.run(_request(method, path, **kw))


REMOTE = ("203.0.113.7", 5555)
TOKEN_A = "aaaa1111aaaa1111"
TOKEN_B = "bbbb2222bbbb2222"


def _reset(machines=None):
    """Reset org state: fresh org.json (or none) and no org.db."""
    os.environ.pop("TT_AUTH_TOKEN", None)
    cfg = Path(_TMP) / "org.json"
    db = Path(_TMP) / "org.db"
    if db.exists():
        db.unlink()
    if machines is None:
        if cfg.exists():
            cfg.unlink()
    else:
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"machines": machines}), encoding="utf-8")


def _two_machines():
    _reset([
        {"label": "kyle-laptop", "token": TOKEN_A},
        {"label": "maria-desktop", "token": TOKEN_B},
    ])


def _session(sid, agent="claude", project="tt", total=100, ts="2026-07-01T10:00:00+05:30"):
    return {
        "id": sid, "agent": agent, "project": project, "timestamp": ts,
        "tokens": {"input": total // 2, "output": total // 2, "cached": 0, "total": total},
        "model": None, "cost": None,
    }


def test_ingest_valid_token_accepts():
    _two_machines()
    status, data = _call("POST", "/org/ingest",
                         headers={"X-TT-Machine-Token": TOKEN_A},
                         body={"sessions": [_session("s1"), _session("s2")]})
    assert status == 200, (status, data)
    assert data == {"accepted": 2, "updated": 0}, data


def test_ingest_resend_is_idempotent():
    _two_machines()
    payload = {"sessions": [_session("s1", total=100), _session("s2", total=200)]}
    _call("POST", "/org/ingest", headers={"X-TT-Machine-Token": TOKEN_A}, body=payload)
    _, before = _call("GET", "/org/summary")
    status, data = _call("POST", "/org/ingest",
                         headers={"X-TT-Machine-Token": TOKEN_A}, body=payload)
    assert status == 200, status
    assert data == {"accepted": 0, "updated": 2}, data
    _, after = _call("GET", "/org/summary")
    assert before["totals"] == after["totals"] == {"sessions": 2, "tokens": 300, "cost": 0.0}, (before, after)


def test_ingest_resend_with_changed_values_overwrites():
    """Re-sending a known session_id with new values must replace the old row
    (DO UPDATE), not skip it: totals reflect the new numbers, not old, not sum."""
    _two_machines()
    _call("POST", "/org/ingest", headers={"X-TT-Machine-Token": TOKEN_A},
          body={"sessions": [_session("s1", agent="claude", total=100)]})
    changed = _session("s1", agent="codex", total=999)
    changed["cost"] = 1.25
    status, data = _call("POST", "/org/ingest",
                         headers={"X-TT-Machine-Token": TOKEN_A},
                         body={"sessions": [changed]})
    assert status == 200 and data == {"accepted": 0, "updated": 1}, (status, data)
    _, summ = _call("GET", "/org/summary")
    assert summ["totals"] == {"sessions": 1, "tokens": 999, "cost": 1.25}, summ["totals"]
    assert [(a["agent"], a["tokens"]) for a in summ["by_agent"]] == [("codex", 999)], summ["by_agent"]


def test_ingest_bad_or_missing_token_is_401():
    _two_machines()
    body = {"sessions": [_session("s1")]}
    status_wrong, _ = _call("POST", "/org/ingest",
                            headers={"X-TT-Machine-Token": "not-a-token"}, body=body)
    assert status_wrong == 401, status_wrong
    status_missing, _ = _call("POST", "/org/ingest", body=body)
    assert status_missing == 401, status_missing
    _, summ = _call("GET", "/org/summary")
    assert summ["totals"]["sessions"] == 0, summ


def test_ingest_machine_field_in_body_is_ignored():
    """The label always comes from the token's config entry, never the body."""
    _two_machines()
    s = _session("s1")
    s["machine"] = "spoofed-label"
    status, _ = _call("POST", "/org/ingest",
                      headers={"X-TT-Machine-Token": TOKEN_B}, body={"sessions": [s]})
    assert status == 200, status
    _, summ = _call("GET", "/org/summary")
    assert [m["machine"] for m in summ["by_machine"]] == ["maria-desktop"], summ


def test_status_enabled_flips_on_config_presence():
    _reset(None)
    status, data = _call("GET", "/org/status")
    assert status == 200 and data == {"enabled": False, "machines": 0, "sessions": 0}, data
    _two_machines()
    status, data = _call("GET", "/org/status")
    assert status == 200 and data == {"enabled": True, "machines": 2, "sessions": 0}, data


def test_summary_disabled_shape_has_all_keys():
    _reset(None)
    status, data = _call("GET", "/org/summary")
    assert status == 200, status
    assert data == {
        "enabled": False,
        "totals": {"sessions": 0, "tokens": 0, "cost": 0.0},
        "by_machine": [], "by_agent": [], "by_project": [], "recent": [],
    }, data


def test_summary_rollup_math_two_machines():
    _two_machines()
    _call("POST", "/org/ingest", headers={"X-TT-Machine-Token": TOKEN_A}, body={"sessions": [
        _session("a1", agent="claude", project="tt", total=100, ts="2026-07-01T10:00:00+05:30"),
        _session("a2", agent="codex", project="web", total=300, ts="2026-07-02T10:00:00+05:30"),
    ]})
    _call("POST", "/org/ingest", headers={"X-TT-Machine-Token": TOKEN_B}, body={"sessions": [
        _session("b1", agent="claude", project="tt", total=500, ts="2026-07-03T10:00:00+05:30"),
    ]})
    status, data = _call("GET", "/org/summary")
    assert status == 200, status
    assert data["enabled"] is True
    assert data["totals"] == {"sessions": 3, "tokens": 900, "cost": 0.0}, data["totals"]
    machines = [(m["machine"], m["sessions"], m["tokens"], m["cost"]) for m in data["by_machine"]]
    assert machines == [("maria-desktop", 1, 500, 0.0), ("kyle-laptop", 2, 400, 0.0)], machines
    assert all(m["last_seen"] for m in data["by_machine"]), data["by_machine"]
    agents = [(a["agent"], a["sessions"], a["tokens"]) for a in data["by_agent"]]
    assert agents == [("claude", 2, 600), ("codex", 1, 300)], agents
    projects = [(p["project"], p["tokens"]) for p in data["by_project"]]
    assert projects == [("tt", 600), ("web", 300)], projects
    assert [r["id"] for r in data["recent"]] == ["b1", "a2", "a1"], data["recent"]
    assert data["recent"][0]["tokens_total"] == 500, data["recent"][0]


def test_recent_orders_by_instant_across_offsets():
    """'2026-07-01T20:00:00+05:30' is 14:30 UTC, EARLIER than 16:00 UTC even
    though the string sorts higher; recent must order by instant, not text."""
    _two_machines()
    _call("POST", "/org/ingest", headers={"X-TT-Machine-Token": TOKEN_A}, body={"sessions": [
        _session("ist", ts="2026-07-01T20:00:00+05:30"),
        _session("utc", ts="2026-07-01T16:00:00+00:00"),
    ]})
    _, summ = _call("GET", "/org/summary")
    assert [r["id"] for r in summ["recent"]] == ["utc", "ist"], summ["recent"]


def test_ingest_non_ascii_token_is_401():
    """Header bytes outside ASCII reach the handler latin-1 decoded; the token
    lookup must answer 401, not crash in hmac.compare_digest with a 500."""
    _two_machines()
    status, _ = _call("POST", "/org/ingest",
                      headers={"X-TT-Machine-Token": "caf\xe9-token"},
                      body={"sessions": []})
    assert status == 401, status


def test_ingest_oversized_batch_is_422():
    _two_machines()
    sessions = [_session(f"s{i}") for i in range(1001)]
    status, _ = _call("POST", "/org/ingest",
                      headers={"X-TT-Machine-Token": TOKEN_A},
                      body={"sessions": sessions})
    assert status == 422, status
    _, summ = _call("GET", "/org/summary")
    assert summ["totals"]["sessions"] == 0, summ


def test_ingest_bypasses_remote_auth_gate():
    """A remote shipper without TT_AUTH_TOKEN reaches /org/ingest; its machine
    token is still mandatory. Every other path stays gated for that client."""
    _two_machines()
    os.environ["TT_AUTH_TOKEN"] = "dashboard-secret"
    try:
        status, data = _call("POST", "/org/ingest", client=REMOTE,
                             headers={"X-TT-Machine-Token": TOKEN_A},
                             body={"sessions": [_session("s1")]})
        assert status == 200, (status, data)
        status_no_machine_token, _ = _call("POST", "/org/ingest", client=REMOTE,
                                           body={"sessions": [_session("s2")]})
        assert status_no_machine_token == 401, status_no_machine_token
        status_other, _ = _call("GET", "/org/summary", client=REMOTE)
        assert status_other == 401, status_other
    finally:
        os.environ.pop("TT_AUTH_TOKEN", None)


def test_corrupt_org_json_means_disabled():
    _reset(None)
    (Path(_TMP) / "org.json").write_text("{not json", encoding="utf-8")
    assert org_store.read_org_config() == {"machines": []}
    assert org_store.resolve_machine(TOKEN_A) is None
    status, data = _call("GET", "/org/status")
    assert status == 200 and data["enabled"] is False, data


def test_malformed_body_is_422():
    _two_machines()
    status, _ = _call("POST", "/org/ingest",
                      headers={"X-TT-Machine-Token": TOKEN_A},
                      body={"sessions": [{"id": "x"}]})
    assert status == 422, status


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
