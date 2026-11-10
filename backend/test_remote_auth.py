"""Tests for the remote-access auth gate (RemoteAuthMiddleware).

When the dashboard is exposed beyond loopback (--host / TT_HOST), bin/cli.js sets
TT_AUTH_TOKEN and every *remote* request must present it. CORS is NOT a security
boundary — it only restrains browsers, not direct clients — so the gate is what
actually protects the API. These tests pin:

  * gate is a no-op when no token is configured (default local behavior);
  * remote requests require a valid token (Bearer header OR ?token= query);
  * loopback requests are always exempt, unless they carry forwarding headers
    (a same-host reverse proxy relaying a remote user), which need the token;
  * the ?token= form is honoured on GET/HEAD only;
  * CORS stays the OUTERMOST layer: OPTIONS preflight is answered without a token
    and the 401 carries CORS headers so a browser can read it.

No httpx / pytest in the venv — we drive the real ASGI app (CORS + auth + routes)
directly with constructed scopes, which also lets us set the client IP.
Run directly:  python backend/test_remote_auth.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Import the fully-assembled app (CORSMiddleware wrapping RemoteAuthMiddleware).
import main  # noqa: E402
from main import app, _is_loopback, _presented_token  # noqa: E402


async def _request(method, path, *, headers=None, query=b"", client=("203.0.113.7", 5555)):
    """Send one request through the real ASGI app; return (status, headers_dict, body)."""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query if isinstance(query, bytes) else query.encode(),
        "headers": raw_headers,
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
    }
    status = {"code": None}
    resp_headers: list = []
    body_parts: list = []
    pending = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
            resp_headers.extend(message.get("headers", []))
        elif message["type"] == "http.response.body":
            body_parts.append(message.get("body", b""))

    await app(scope, receive, send)
    hdrs = {k.decode().lower(): v.decode() for k, v in resp_headers}
    return status["code"], hdrs, b"".join(body_parts)


def _get(**kw):
    status, hdrs, _ = asyncio.run(_request("GET", "/pricing", **kw))
    return status, hdrs


def _raw_status(raw_headers, query=b"", client=("203.0.113.7", 5555)):
    """GET /pricing with pre-encoded header bytes (for values str can't carry).
    Returns the status, or 500 if the app raised instead of responding."""
    scope = {
        "type": "http", "http_version": "1.1", "method": "GET", "path": "/pricing",
        "raw_path": b"/pricing", "query_string": query, "headers": raw_headers,
        "client": client, "server": ("testserver", 80), "scheme": "http",
    }
    status = {"code": None}

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    try:
        asyncio.run(app(scope, receive, send))
    except Exception:  # noqa: BLE001 - an unhandled error is a 500 on the wire
        return 500
    return status["code"]


def _remote_access(**kw):
    import json
    status, _, body = asyncio.run(_request("GET", "/remote-access", **kw))
    try:
        data = json.loads(body) if body else None
    except ValueError:
        data = None
    return status, data


TOKEN = "s3cret-token-value"
REMOTE = ("203.0.113.7", 5555)        # non-loopback source
LOOPBACK = ("127.0.0.1", 5555)
LOOPBACK6 = ("::1", 5555)
ORIGIN = {"Origin": "http://localhost:3000"}  # always in the CORS allowlist


def _set_token(value):
    if value is None:
        os.environ.pop("TT_AUTH_TOKEN", None)
    else:
        os.environ["TT_AUTH_TOKEN"] = value


def test_no_token_means_no_gate():
    """Default local install: no token configured → every request passes."""
    _set_token(None)
    status, _ = _get(client=REMOTE)
    assert status == 200, status


def test_remote_without_token_is_rejected():
    _set_token(TOKEN)
    status, _ = _get(client=REMOTE)
    assert status == 401, status


def test_remote_with_correct_bearer_passes():
    _set_token(TOKEN)
    status, _ = _get(client=REMOTE, headers={"Authorization": f"Bearer {TOKEN}"})
    assert status == 200, status


def test_remote_with_wrong_bearer_is_rejected():
    _set_token(TOKEN)
    status, _ = _get(client=REMOTE, headers={"Authorization": "Bearer nope"})
    assert status == 401, status


def test_remote_with_query_token_passes():
    """Browser-native resource loads (artifact <img>/<a>) use ?token= instead."""
    _set_token(TOKEN)
    status, _ = _get(client=REMOTE, query=f"token={TOKEN}")
    assert status == 200, status


def test_loopback_is_exempt_even_with_token_set():
    _set_token(TOKEN)
    for client in (LOOPBACK, LOOPBACK6):
        status, _ = _get(client=client)
        assert status == 200, (client, status)


# --- loopback peer that is really a reverse proxy --------------------------
# A proxy on the same host connects from 127.0.0.1 on behalf of remote users.
# Forwarding headers withdraw the loopback exemption; they never grant access.

FORWARDED_VARIANTS = [
    {"X-Forwarded-For": "198.51.100.9"},
    {"X-Real-IP": "198.51.100.9"},
    {"Forwarded": "for=198.51.100.9;proto=https"},
    {"X-Forwarded-Host": "box.example.test"},
    {"X-Forwarded-Proto": "https"},
    {"Via": "1.1 proxy"},
    {"X-Forwarded-For": "127.0.0.1"},   # claiming to be local changes nothing
]


def test_forwarded_loopback_without_token_is_rejected():
    _set_token(TOKEN)
    for fwd in FORWARDED_VARIANTS:
        for client in (LOOPBACK, LOOPBACK6):
            status, _ = _get(client=client, headers=fwd)
            assert status == 401, (fwd, client, status)


def test_forwarded_loopback_with_token_passes():
    _set_token(TOKEN)
    for fwd in FORWARDED_VARIANTS:
        status, _ = _get(client=LOOPBACK, headers={**fwd, "Authorization": f"Bearer {TOKEN}"})
        assert status == 200, (fwd, status)
        status, _ = _get(client=LOOPBACK, headers=fwd, query=f"token={TOKEN}")
        assert status == 200, (fwd, status)


def test_forwarding_headers_never_grant_access():
    """A remote peer cannot talk its way into the exemption by claiming to be
    forwarded from loopback."""
    _set_token(TOKEN)
    for hdrs in ({"X-Forwarded-For": "127.0.0.1"}, {"X-Real-IP": "::1"},
                 {"Forwarded": "for=127.0.0.1"}):
        status, _ = _get(client=REMOTE, headers=hdrs)
        assert status == 401, (hdrs, status)


def test_no_token_mode_ignores_forwarding_headers():
    """Gate off (the default): forwarding headers change nothing, from any peer."""
    _set_token(None)
    for client in (LOOPBACK, REMOTE):
        status, hdrs = _get(client=client, headers={"X-Forwarded-For": "198.51.100.9"})
        assert status == 200, (client, status)
        assert "referrer-policy" not in hdrs, hdrs


def test_remote_access_not_fetchable_through_local_proxy():
    """The token-bearing QR endpoint is for a person at this machine. Relayed
    through a same-host proxy it must never answer 200, token or not."""
    _set_token(TOKEN)
    os.environ["TT_REMOTE_CONNECT_URL"] = "http://192.168.0.6:3000/?token=" + TOKEN
    fwd = {"X-Forwarded-For": "198.51.100.9"}
    try:
        status, _ = _remote_access(client=LOOPBACK, headers=fwd)
        assert status == 401, status
        status, data = _remote_access(
            client=LOOPBACK, headers={**fwd, "Authorization": f"Bearer {TOKEN}"}
        )
        assert status == 403, status
        assert not (data or {}).get("token"), data
    finally:
        os.environ.pop("TT_REMOTE_CONNECT_URL", None)


# --- query-string token ----------------------------------------------------

def test_query_token_rejected_on_non_get():
    """?token= is for <img>/<a> loads, which are GET. A write must use the
    Authorization header, so the secret is not needed in URLs for anything else."""
    _set_token(TOKEN)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        status, _, _ = asyncio.run(_request(method, "/pricing", client=REMOTE, query=f"token={TOKEN}"))
        assert status == 401, (method, status)
        # Same request with the header gets past the gate (405: /pricing is GET-only).
        status, _, _ = asyncio.run(_request(
            method, "/pricing", client=REMOTE, headers={"Authorization": f"Bearer {TOKEN}"}))
        assert status != 401, (method, status)


def test_query_token_accepted_on_head():
    """The artifacts preview HEAD-checks file existence with the same URL."""
    _set_token(TOKEN)
    status, _, _ = asyncio.run(_request(
        "HEAD", "/artifacts", client=REMOTE, query=f"path=nope&token={TOKEN}"))
    assert status != 401, status
    status, _, _ = asyncio.run(_request("HEAD", "/artifacts", client=REMOTE, query="path=nope"))
    assert status == 401, status


def test_referrer_policy_only_in_remote_mode():
    """With a token configured, responses (including the 401) tell the browser
    not to send Referer, so a ?token= URL is not passed on to other hosts."""
    _set_token(TOKEN)
    for kw in ({"client": REMOTE, "query": f"token={TOKEN}"}, {"client": REMOTE}, {"client": LOOPBACK}):
        _, hdrs = _get(**kw)
        assert hdrs.get("referrer-policy") == "no-referrer", (kw, hdrs)
    _set_token(None)
    _, hdrs = _get(client=LOOPBACK)
    assert "referrer-policy" not in hdrs, hdrs


# --- header parsing / comparison edge cases --------------------------------

def test_bearer_scheme_is_case_insensitive():
    _set_token(TOKEN)
    for scheme in ("bearer", "BEARER", "Bearer"):
        status, _ = _get(client=REMOTE, headers={"Authorization": f"{scheme} {TOKEN}"})
        assert status == 200, (scheme, status)


def test_non_ascii_token_is_rejected_not_a_500():
    """hmac.compare_digest() raises on a non-ASCII str; that must be a clean 401,
    whether the junk arrives in the query string or the header."""
    _set_token(TOKEN)
    assert _raw_status([], query=b"token=%C3%A9%C3%A9") == 401
    assert _raw_status([(b"authorization", b"Bearer caf\xe9")]) == 401


def test_empty_presented_token_is_rejected():
    _set_token(TOKEN)
    for kw in ({"headers": {"Authorization": "Bearer "}}, {"headers": {"Authorization": "Bearer"}},
               {"query": "token="}, {"query": "token=%20"}):
        status, _ = _get(client=REMOTE, **kw)
        assert status == 401, (kw, status)


def test_blank_configured_token_means_gate_off_not_empty_match():
    """A whitespace-only TT_AUTH_TOKEN is 'unset' (bin/cli.js passes '' for
    local mode). It must not become a token that an empty value matches."""
    _set_token("   ")
    status, hdrs = _get(client=REMOTE)
    assert status == 200, status
    assert "referrer-policy" not in hdrs, hdrs


def test_preflight_is_answered_without_token():
    """CORS is outermost: an OPTIONS preflight (no Authorization) must succeed and
    carry the allow-origin header, never get a 401 from the auth layer."""
    _set_token(TOKEN)
    status, hdrs, _ = asyncio.run(_request(
        "OPTIONS", "/pricing", client=REMOTE,
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    ))
    assert status in (200, 204), status
    assert "access-control-allow-origin" in hdrs, hdrs


def test_preflight_through_local_proxy_is_answered_without_token():
    """Withdrawing the loopback exemption must not break preflight for a
    browser reaching the API through a same-host proxy."""
    _set_token(TOKEN)
    status, hdrs, _ = asyncio.run(_request(
        "OPTIONS", "/pricing", client=LOOPBACK,
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
            "X-Forwarded-For": "198.51.100.9",
        },
    ))
    assert status in (200, 204), status
    assert "access-control-allow-origin" in hdrs, hdrs


def test_401_carries_cors_headers():
    """A rejected remote request from an allowed origin must still be readable by
    the browser — i.e. CORS decorates the 401 (it would otherwise show as an
    opaque CORS error, masking the real reason)."""
    _set_token(TOKEN)
    status, hdrs = _get(client=REMOTE, headers=ORIGIN)
    assert status == 401, status
    assert "access-control-allow-origin" in hdrs, hdrs


def test_remote_access_loopback_returns_connect_info():
    """The QR endpoint hands the connect URL + token to a LOCAL caller only."""
    _set_token(TOKEN)
    os.environ["TT_REMOTE_CONNECT_URL"] = "http://192.168.0.6:3000/?token=" + TOKEN
    try:
        status, data = _remote_access(client=LOOPBACK)
        assert status == 200, status
        assert data and data.get("enabled") is True, data
        assert data.get("token") == TOKEN, data
        assert "192.168.0.6" in data.get("url", ""), data
    finally:
        os.environ.pop("TT_REMOTE_CONNECT_URL", None)


def test_remote_access_not_fetchable_remotely():
    """A remote device can never read the token: no token → 401 (middleware),
    token → 403 (endpoint's own loopback check). Never 200."""
    _set_token(TOKEN)
    os.environ["TT_REMOTE_CONNECT_URL"] = "http://192.168.0.6:3000/?token=" + TOKEN
    try:
        status_no_creds, _ = _remote_access(client=REMOTE)
        assert status_no_creds == 401, status_no_creds
        status_with_token, _ = _remote_access(
            client=REMOTE, headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert status_with_token == 403, status_with_token
    finally:
        os.environ.pop("TT_REMOTE_CONNECT_URL", None)


def test_remote_access_disabled_when_no_connect_url():
    _set_token(TOKEN)
    os.environ.pop("TT_REMOTE_CONNECT_URL", None)
    status, data = _remote_access(client=LOOPBACK)
    assert status == 200, status
    assert data == {"enabled": False}, data


def test_loopback_helper():
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("::1")
    assert _is_loopback("localhost")
    assert _is_loopback("::ffff:127.0.0.1")
    assert not _is_loopback("203.0.113.7")
    assert not _is_loopback("10.0.0.5")
    assert not _is_loopback(None)
    assert not _is_loopback("")


def test_presented_token_helper():
    class _Req:
        def __init__(self, headers, qp, method="GET"):
            self.headers = headers
            self.query_params = qp
            self.method = method
    assert _presented_token(_Req({"Authorization": "Bearer abc"}, {})) == "abc"
    assert _presented_token(_Req({"Authorization": "bearer abc"}, {})) == "abc"
    assert _presented_token(_Req({}, {"token": "xyz"})) == "xyz"
    assert _presented_token(_Req({}, {"token": "xyz"}, "HEAD")) == "xyz"
    assert _presented_token(_Req({}, {"token": "xyz"}, "POST")) == ""
    assert _presented_token(_Req({"Authorization": "Bearer abc"}, {"token": "xyz"}, "POST")) == "abc"
    assert _presented_token(_Req({"Authorization": "Basic abc"}, {})) == ""
    assert _presented_token(_Req({"Authorization": "Bearerabc"}, {})) == ""
    assert _presented_token(_Req({}, {})) == ""


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
    _set_token(None)
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
