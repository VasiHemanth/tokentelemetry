"""Tests for the remote-access auth gate (RemoteAuthMiddleware).

When the dashboard is exposed beyond loopback (--host / TT_HOST), bin/cli.js sets
TT_AUTH_TOKEN and every *remote* request must present it. CORS is NOT a security
boundary — it only restrains browsers, not direct clients — so the gate is what
actually protects the API. These tests pin:

  * gate is a no-op when no token is configured (default local behavior);
  * remote requests require a valid token (Bearer header OR ?token= query);
  * loopback requests are always exempt;
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
        def __init__(self, headers, qp):
            self.headers = headers
            self.query_params = qp
    assert _presented_token(_Req({"Authorization": "Bearer abc"}, {})) == "abc"
    assert _presented_token(_Req({}, {"token": "xyz"})) == "xyz"
    assert _presented_token(_Req({"Authorization": "Basic abc"}, {})) == ""
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
