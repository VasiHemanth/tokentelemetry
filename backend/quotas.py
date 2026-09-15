"""Native live quota collection for coding-agent providers.

Provider credentials are read only for the lifetime of a refresh. The persisted
cache contains normalized quota values and safe error messages only.
"""

from __future__ import annotations

import base64
import json
import re
import os
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tt_paths import data_dir


SCHEMA = "tokentelemetry.quotas.v1"
FRESHNESS = timedelta(minutes=5)
CACHE_LOCK_TIMEOUT_SECONDS = 15
# A fetchedAt read off disk this far ahead of the loader's own clock cannot
# be trusted; treat it as no cached snapshot rather than an indefinitely
# fresh one.
MAX_FUTURE_SKEW = timedelta(minutes=5)

# ``flock``/``msvcrt.locking`` coordinate separate processes, but their
# same-process behaviour differs by platform. Keep a per-cache thread lock as
# well, so two independently constructed services in one app cannot bypass the
# interprocess lock while another process is also using the cache.
_cache_locks: Dict[str, threading.Lock] = {}
_cache_locks_guard = threading.Lock()

# Some provider edges (OpenCode sits behind Cloudflare) reject the stdlib's
# default "Python-urllib/x.y" agent with a 1010 browser-signature ban, which
# looks exactly like an auth failure. Always identify ourselves instead.
USER_AGENT = "TokenTelemetry"

# Refresh failures are raised as RuntimeError with one of these messages so the
# service can tell "you were never signed in" from "your session died" from
# "this account has no entitlement" — three different things for the user to do.
NOT_SIGNED_IN = "not logged in"
SESSION_EXPIRED = "session expired"
NOT_ENTITLED = "not entitled"
LOGIN_REJECTED = "local login was rejected"
# Distinct from NOT_SIGNED_IN: the agent keeps its quota behind a server it
# only runs while it is open. The login is fine, so telling the user to sign
# in again sends them to fix something that is not broken.
AGENT_NOT_RUNNING = "agent not running"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _cache_locks_guard:
        return _cache_locks.setdefault(key, threading.Lock())


class _CacheFileLock:
    """A bounded advisory lock that works on the supported desktop platforms."""

    def __init__(self, cache_path: Path, timeout: float = CACHE_LOCK_TIMEOUT_SECONDS) -> None:
        self.path = cache_path.with_name(f"{cache_path.name}.lock")
        self.timeout = timeout
        self._thread_lock = _cache_lock_for(cache_path)
        self._handle: Optional[Any] = None
        self._acquired = False

    def __enter__(self) -> bool:
        if not self._thread_lock.acquire(timeout=self.timeout):
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a+b")
            self._handle.seek(0, os.SEEK_END)
            if self._handle.tell() == 0:
                self._handle.write(b"0")
                self._handle.flush()

            deadline = time.monotonic() + self.timeout
            while True:
                if self._try_acquire():
                    self._acquired = True
                    return True
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    self._thread_lock.release()
                    return False
                time.sleep(0.05)
        except OSError:
            if self._handle is not None:
                self._handle.close()
                self._handle = None
            self._thread_lock.release()
            return False

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self._handle is not None:
            try:
                if self._acquired:
                    self._release()
            finally:
                self._handle.close()
                self._handle = None
        if self._acquired:
            self._thread_lock.release()
            self._acquired = False

    def _try_acquire(self) -> bool:
        assert self._handle is not None
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    def _release(self) -> None:
        assert self._handle is not None
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date(value: Any) -> Optional[datetime]:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except ValueError:
        return None


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _title(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.replace("_", " ").title()


@dataclass
class QuotaResource:
    kind: str
    unit: str
    used: Optional[float] = None
    available: Optional[float] = None
    limit: Optional[float] = None
    resets_at: Optional[datetime] = None
    window_seconds: Optional[float] = None
    expires_at: List[datetime] = field(default_factory=list)
    estimated: bool = False

    def wire(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"kind": self.kind, "unit": self.unit}
        if self.used is not None:
            used = max(0.0, self.used)
            result["used"] = used
            if self.limit is not None:
                limit = max(0.0, self.limit)
                result["limit"] = limit
                result["remaining"] = max(0.0, limit - used)
                result["utilization"] = used / limit if limit else None
        if self.available is not None:
            result["available"] = max(0.0, self.available)
        if self.resets_at:
            result["resetsAt"] = _iso(self.resets_at)
        if self.window_seconds is not None:
            result["windowSeconds"] = self.window_seconds
        if self.expires_at:
            result["expiresAt"] = [_iso(value) for value in sorted(self.expires_at)]
        if self.estimated:
            result["estimated"] = True
        return {key: value for key, value in result.items() if value is not None}

    @classmethod
    def from_wire(cls, value: Dict[str, Any]) -> "QuotaResource":
        return cls(
            kind=str(value.get("kind") or "consumption"),
            unit=str(value.get("unit") or "count"),
            used=_number(value.get("used")),
            available=_number(value.get("available")),
            limit=_number(value.get("limit")),
            resets_at=_date(value.get("resetsAt")),
            window_seconds=_number(value.get("windowSeconds")),
            expires_at=[parsed for item in value.get("expiresAt", []) if (parsed := _date(item))],
            estimated=value.get("estimated") is True,
        )


@dataclass
class QuotaSnapshot:
    provider_id: str
    display_name: str
    fetched_at: datetime
    resources: Dict[str, QuotaResource]
    plan: Optional[str] = None

    def wire(self, generated_at: datetime) -> Dict[str, Any]:
        expires = self.fetched_at + FRESHNESS
        return {
            "displayName": self.display_name,
            "plan": self.plan,
            "fetchedAt": _iso(self.fetched_at),
            "expiresAt": _iso(expires),
            "stale": generated_at >= expires,
            "resources": {key: value.wire() for key, value in self.resources.items()},
        }

    @classmethod
    def from_wire(cls, provider_id: str, value: Dict[str, Any], now: datetime) -> Optional["QuotaSnapshot"]:
        fetched_at = _date(value.get("fetchedAt"))
        resources = value.get("resources")
        if not fetched_at or not isinstance(resources, dict):
            return None
        if fetched_at > now + MAX_FUTURE_SKEW:
            return None
        parsed = {
            str(key): QuotaResource.from_wire(resource)
            for key, resource in resources.items()
            if isinstance(resource, dict)
        }
        return cls(
            provider_id=provider_id,
            display_name=str(value.get("displayName") or provider_id),
            plan=value.get("plan") if isinstance(value.get("plan"), str) else None,
            fetched_at=fetched_at,
            resources=parsed,
        )


class QuotaProvider(Protocol):
    provider_id: str
    display_name: str

    def has_local_credentials(self) -> bool: ...
    def refresh(self, now: datetime) -> QuotaSnapshot: ...


FetchJSON = Callable[[str, Dict[str, str]], tuple[int, Dict[str, Any]]]


def _fetch_json(url: str, headers: Dict[str, str]) -> tuple[int, Dict[str, Any]]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT, **headers})
    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        status, body = error.code, error.read()
    except (URLError, OSError) as error:
        raise RuntimeError("network") from error
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("invalid response") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("invalid response")
    return status, decoded


def _post_json(url: str, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None) -> tuple[int, Dict[str, Any]]:
    request = Request(url, data=json.dumps(body or {}).encode("utf-8"), method="POST", headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        **headers,
    })
    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        status, body = error.code, error.read()
    except (URLError, OSError) as error:
        raise RuntimeError("network") from error
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("invalid response") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("invalid response")
    return status, decoded


def _post_form(url: str, body: Dict[str, str]) -> tuple[int, Dict[str, Any]]:
    request = Request(url, data=urlencode(body).encode("utf-8"), method="POST", headers={
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    })
    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        status, body = error.code, error.read()
    except (URLError, OSError) as error:
        raise RuntimeError("network") from error
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("invalid response") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("invalid response")
    return status, decoded


def _post_loopback_json(
    port: int, path: str, headers: Dict[str, str], body: Dict[str, Any],
) -> tuple[int, Dict[str, Any]]:
    """POST JSON to an agent's own HTTPS server on this machine.

    Some agents answer their UI over a local HTTPS listener whose certificate
    is self-signed for a loopback address, so the usual chain check cannot
    pass. That is why this is a separate helper instead of a flag on
    ``_post_json``: relaxing the shared path would silently drop verification
    for every *remote* provider too. The host is hardcoded here, so no caller
    can point a verification-free request off this machine.
    """
    request = Request(
        f"https://127.0.0.1:{int(port)}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **headers,
        },
    )
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(request, timeout=10, context=context) as response:
            status, raw = response.status, response.read()
    except HTTPError as error:
        status, raw = error.code, error.read()
    except (URLError, OSError) as error:
        raise RuntimeError("network") from error
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("invalid response") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("invalid response")
    return status, decoded


def _process_command_lines() -> List[str]:
    """Full command lines of the running processes, or [] when unavailable.

    A provider whose agent publishes its port on its own command line reads it
    from here. Every failure degrades to an empty list, which the caller
    reports as "not running" — a quota panel must not raise because a process
    listing was slow or refused.
    """
    if os.name == "nt":
        # Written through [Console]::Out rather than PowerShell's own pipeline
        # output: the default formatter wraps strings at the host's buffer
        # width, which would split a long command line mid-flag and separate
        # an argument from its value.
        command = [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance Win32_Process | ForEach-Object "
            "{ if ($_.CommandLine) { [Console]::Out.WriteLine($_.CommandLine) } }",
        ]
    else:
        command = ["ps", "axo", "args="]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _read_keychain(service: str) -> Optional[str]:
    """Fetch a generic-password secret from the macOS login Keychain.

    Only ever called for a service TokenTelemetry knows a coding agent wrote.
    The first read of an item the user has not yet approved shows a macOS
    consent dialog, so the call is bounded by a timeout: an unanswered prompt
    must degrade to "no credentials", never hang the /quotas request thread.
    """
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    secret = result.stdout.strip()
    return secret or None


class CodexQuotaProvider:
    provider_id = "codex"
    display_name = "Codex"
    sign_in_hint = "Codex's saved login has expired. Run `codex` and sign in again."
    usage_url = "https://chatgpt.com/backend-api/wham/usage"
    reset_credits_url = "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits"

    def __init__(
        self,
        home: Optional[Path] = None,
        fetch_json: FetchJSON = _fetch_json,
        environment: Optional[Dict[str, str]] = None,
    ) -> None:
        self.home = home or Path.home()
        self.fetch_json = fetch_json
        self.environment = environment if environment is not None else os.environ

    def _auth_paths(self) -> Iterable[Path]:
        configured = self.environment.get("CODEX_HOME")
        if configured and configured.strip():
            yield Path(configured).expanduser() / "auth.json"
            return
        yield self.home / ".codex" / "auth.json"
        yield self.home / ".config" / "codex" / "auth.json"

    def _auth(self) -> Optional[Dict[str, str]]:
        for path in self._auth_paths():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            tokens = value.get("tokens") if isinstance(value, dict) else None
            if not isinstance(tokens, dict):
                continue
            access = tokens.get("access_token")
            if isinstance(access, str) and access.strip():
                account = tokens.get("account_id")
                return {"access": access.strip(), "account": account if isinstance(account, str) else ""}
        return None

    def has_local_credentials(self) -> bool:
        return self._auth() is not None

    def refresh(self, now: datetime) -> QuotaSnapshot:
        auth = self._auth()
        if not auth:
            raise RuntimeError(NOT_SIGNED_IN)
        headers = {"Authorization": f"Bearer {auth['access']}", "User-Agent": "TokenTelemetry"}
        if auth["account"]:
            headers["ChatGPT-Account-Id"] = auth["account"]
        status, payload = self.fetch_json(self.usage_url, headers)
        if status in (401, 403):
            raise RuntimeError(LOGIN_REJECTED)
        if not 200 <= status < 300:
            raise RuntimeError("usage request failed")

        resources = self._resources(payload, now)
        try:
            reset_status, reset_payload = self.fetch_json(
                self.reset_credits_url,
                {**headers, "OpenAI-Beta": "codex-1", "originator": "Codex Desktop"},
            )
        except RuntimeError:
            reset_status, reset_payload = 0, {}
        self._add_reset_credits(resources, payload, reset_payload if 200 <= reset_status < 300 else {})
        return QuotaSnapshot(
            provider_id=self.provider_id,
            display_name=self.display_name,
            plan={"prolite": "Pro 5x", "pro": "Pro 20x"}.get(str(payload.get("plan_type", "")).lower(), _title(payload.get("plan_type"))),
            fetched_at=now,
            resources=resources,
        )

    @staticmethod
    def _window_resource(window: Dict[str, Any], now: datetime) -> Optional[QuotaResource]:
        used = _number(window.get("used_percent"))
        if used is None:
            return None
        reset = _date(window.get("reset_at"))
        after = _number(window.get("reset_after_seconds"))
        if reset is None and after is not None:
            reset = now + timedelta(seconds=after)
        period = _number(window.get("limit_window_seconds"))
        return QuotaResource(
            kind="consumption", unit="percent", used=min(100.0, max(0.0, used)), limit=100,
            resets_at=reset, window_seconds=period,
        )

    def _resources(self, payload: Dict[str, Any], now: datetime) -> Dict[str, QuotaResource]:
        resources: Dict[str, QuotaResource] = {}
        rate_limit = payload.get("rate_limit")
        if isinstance(rate_limit, dict):
            for fallback_key, fallback_name in (("primary_window", "session"), ("secondary_window", "weekly")):
                window = rate_limit.get(fallback_key)
                if not isinstance(window, dict):
                    continue
                resource = self._window_resource(window, now)
                if not resource:
                    continue
                period = resource.window_seconds
                key = "session" if period and abs(period - 18_000) < 60 else "weekly" if period and abs(period - 604_800) < 60 else fallback_name
                resources[key] = resource
        extras = payload.get("additional_rate_limits")
        if isinstance(extras, list):
            for entry in extras:
                if not isinstance(entry, dict) or "spark" not in f"{entry.get('limit_name', '')} {entry.get('metered_feature', '')}".lower():
                    continue
                rate_limit = entry.get("rate_limit")
                if not isinstance(rate_limit, dict):
                    continue
                for source, key in (("primary_window", "spark"), ("secondary_window", "sparkWeekly")):
                    if isinstance(rate_limit.get(source), dict):
                        resource = self._window_resource(rate_limit[source], now)
                        if resource:
                            resources[key] = resource
                break
        credits = payload.get("credits")
        if isinstance(credits, dict):
            balance = _number(credits.get("balance"))
            if balance is not None:
                resources["credits"] = QuotaResource(kind="balance", unit="credits", available=balance)
            elif credits.get("has_credits") is False:
                resources["credits"] = QuotaResource(kind="balance", unit="credits", available=0)
        return resources

    @staticmethod
    def _add_reset_credits(resources: Dict[str, QuotaResource], usage: Dict[str, Any], dedicated: Dict[str, Any]) -> None:
        source = dedicated if _number(dedicated.get("available_count")) is not None else usage.get("rate_limit_reset_credits")
        if not isinstance(source, dict):
            return
        count = _number(source.get("available_count"))
        if count is None or count < 0:
            return
        expiries = []
        # The usage response is authoritative for the count when the optional
        # endpoint omits it, but a successful dedicated response can still add
        # per-credit expiry details. Keep both rather than discarding useful
        # reset timing just because one optional scalar was absent.
        credits = dedicated.get("credits") if isinstance(dedicated.get("credits"), list) else source.get("credits")
        if isinstance(credits, list):
            for credit in credits:
                if not isinstance(credit, dict) or credit.get("status") not in (None, "available"):
                    continue
                parsed = _date(credit.get("expires_at"))
                if parsed:
                    expiries.append(parsed)
        resources["rateLimitResets"] = QuotaResource(
            kind="balance", unit="resets", available=float(int(count)), expires_at=expiries,
        )


class ClaudeQuotaProvider:
    """Read a Claude Code OAuth session and map Anthropic's native usage response.

    Claude Code keeps the same ``claudeAiOauth`` blob in one of two places. On
    Linux and Windows it is a file; on macOS the CLI stores it in the login
    Keychain and no file exists, which is why a file-only probe reported a
    signed-in user as signed out. Both sources are read here, file first.

    ``~/.claude.json`` also caches a ``cachedUsageUtilization`` block, but it is
    only rewritten when the CLI next talks to the API and is routinely days old,
    so it is used as a clearly-marked fallback rather than a live reading.
    """

    provider_id = "claude"
    display_name = "Claude Code"
    sign_in_hint = "Claude Code's saved login has expired. Run `claude` and sign in again."
    usage_url = "https://api.anthropic.com/api/oauth/usage"
    keychain_service = "Claude Code-credentials"

    def __init__(
        self,
        home: Optional[Path] = None,
        fetch_json: FetchJSON = _fetch_json,
        environment: Optional[Dict[str, str]] = None,
        read_keychain: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self.home = home or Path.home()
        self.fetch_json = fetch_json
        self.environment = environment if environment is not None else os.environ
        self.read_keychain = read_keychain if read_keychain is not None else _read_keychain

    def _credentials_path(self) -> Path:
        configured = self.environment.get("CLAUDE_CONFIG_DIR")
        if configured and configured.strip():
            return Path(configured).expanduser() / ".credentials.json"
        return self.home / ".claude" / ".credentials.json"

    def _raw_credentials(self) -> Iterable[Any]:
        try:
            yield json.loads(self._credentials_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        secret = self.read_keychain(self.keychain_service)
        if secret:
            try:
                yield json.loads(secret)
            except json.JSONDecodeError:
                pass

    def _auth(self) -> Optional[Dict[str, str]]:
        for raw in self._raw_credentials():
            oauth = raw.get("claudeAiOauth") if isinstance(raw, dict) else None
            if not isinstance(oauth, dict):
                continue
            token = oauth.get("accessToken")
            if not isinstance(token, str) or not token.strip():
                continue
            metadata = {"access": token.strip()}
            expiry = _number(oauth.get("expiresAt"))
            if expiry is not None:
                metadata["expiresAt"] = str(expiry)
            for source, destination in (("subscriptionType", "subscription"), ("rateLimitTier", "tier")):
                value = oauth.get(source)
                if isinstance(value, str) and value.strip():
                    metadata[destination] = value.strip()
            return metadata
        return None

    def has_local_credentials(self) -> bool:
        return self._auth() is not None

    def refresh(self, now: datetime) -> QuotaSnapshot:
        auth = self._auth()
        if not auth:
            raise RuntimeError(NOT_SIGNED_IN)
        status, payload = self.fetch_json(self.usage_url, {
            "Authorization": f"Bearer {auth['access']}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "TokenTelemetry",
        })
        if status in (401, 403):
            raise RuntimeError(LOGIN_REJECTED)
        if not 200 <= status < 300:
            raise RuntimeError("usage request failed")
        resources: Dict[str, QuotaResource] = {}
        for source, key, duration in (
            ("five_hour", "session", 5 * 60 * 60),
            ("seven_day", "weekly", 7 * 24 * 60 * 60),
            ("seven_day_sonnet", "sonnetWeekly", 7 * 24 * 60 * 60),
        ):
            window = payload.get(source)
            if not isinstance(window, dict):
                continue
            used = _number(window.get("utilization"))
            if used is not None:
                resources[key] = QuotaResource(
                    kind="consumption", unit="percent", used=min(100, max(0, used)), limit=100,
                    resets_at=_date(window.get("resets_at")), window_seconds=duration,
                )
        extra = payload.get("extra_usage")
        if isinstance(extra, dict) and extra.get("is_enabled") is True:
            cents = _number(extra.get("used_credits"))
            limit_cents = _number(extra.get("monthly_limit"))
            if cents is not None:
                resources["extraUsage"] = QuotaResource(
                    kind="spend", unit="usd", used=max(0, cents) / 100,
                    limit=max(0, limit_cents) / 100 if limit_cents is not None else None,
                    window_seconds=30 * 24 * 60 * 60, estimated=limit_cents is None,
                )
        plan = _title(auth.get("subscription"))
        tier = auth.get("tier", "")
        import re
        match = re.search(r"(\d+x)", tier)
        if plan and match:
            plan = f"{plan} {match.group(1)}"
        return QuotaSnapshot(self.provider_id, self.display_name, now, resources, plan)


class OpenCodeQuotaProvider:
    provider_id = "opencode"
    display_name = "OpenCode"
    sign_in_hint = "OpenCode's saved login has expired. Run `opencode auth login` again."
    usage_url = "https://opencode.ai/zen/go/v1/usage"

    def __init__(
        self,
        home: Optional[Path] = None,
        fetch_json: FetchJSON = _fetch_json,
        environment: Optional[Dict[str, str]] = None,
    ) -> None:
        self.home = home or Path.home()
        self.fetch_json = fetch_json
        self.environment = environment if environment is not None else os.environ

    def _auth_paths(self) -> Iterable[Path]:
        configured = self.environment.get("OPENCODE_DATA_DIR") or self.environment.get("XDG_DATA_HOME")
        if configured and configured.strip():
            yield Path(configured).expanduser() / ("auth.json" if self.environment.get("OPENCODE_DATA_DIR") else "opencode/auth.json")
        yield self.home / ".local" / "share" / "opencode" / "auth.json"

    def _api_key(self) -> Optional[str]:
        for path in self._auth_paths():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            entry = raw.get("opencode-go") if isinstance(raw, dict) else None
            key = entry.get("key") if isinstance(entry, dict) else None
            if isinstance(key, str) and key.strip():
                return key.strip()
        return None

    def has_local_credentials(self) -> bool:
        return self._api_key() is not None

    def refresh(self, now: datetime) -> QuotaSnapshot:
        key = self._api_key()
        if not key:
            raise RuntimeError(NOT_SIGNED_IN)
        status, payload = self.fetch_json(self.usage_url, {"Authorization": f"Bearer {key}"})
        if status in (401, 403):
            raise RuntimeError(LOGIN_REJECTED)
        if not 200 <= status < 300:
            raise RuntimeError("usage request failed")
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            raise RuntimeError("invalid response")
        resources: Dict[str, QuotaResource] = {}
        for source, key_name, duration in (
            ("rolling", "session", 5 * 60 * 60),
            ("weekly", "weekly", 7 * 24 * 60 * 60),
            ("monthly", "monthly", 30 * 24 * 60 * 60),
        ):
            window = usage.get(source)
            percent = _number(window.get("percent")) if isinstance(window, dict) else None
            if percent is not None:
                resources[key_name] = QuotaResource(
                    kind="consumption", unit="percent", used=min(100, max(0, percent)), limit=100,
                    resets_at=_date(window.get("resetsAt")), window_seconds=duration,
                )
        if not resources:
            raise RuntimeError("invalid response")
        return QuotaSnapshot(self.provider_id, self.display_name, now, resources)


class CopilotQuotaProvider:
    provider_id = "copilot"
    display_name = "GitHub Copilot"
    sign_in_hint = "The saved GitHub Copilot login has expired. Sign in to Copilot again."
    usage_url = "https://api.github.com/copilot_internal/user"

    def __init__(self, home: Optional[Path] = None, fetch_json: FetchJSON = _fetch_json) -> None:
        self.home = home or Path.home()
        self.fetch_json = fetch_json

    def _token(self) -> Optional[str]:
        for path in (
            self.home / ".config" / "github-copilot" / "apps.json",
            self.home / ".config" / "github-copilot" / "hosts.json",
        ):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            for host, entry in raw.items():
                token = entry.get("oauth_token") if (host == "github.com" or host.startswith("github.com:")) and isinstance(entry, dict) else None
                if isinstance(token, str) and token.strip():
                    return token.strip()
        hosts = self.home / ".config" / "gh" / "hosts.yml"
        try:
            lines = hosts.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        in_github = False
        for line in lines:
            if line and not line[0].isspace():
                in_github = line.strip() == "github.com:"
                continue
            if in_github and line.strip().startswith("oauth_token:"):
                token = line.split(":", 1)[1].strip().strip("\"'")
                if token:
                    return token
        return self._opencode_copilot_token()

    def _opencode_copilot_token(self) -> Optional[str]:
        """Use the Copilot token OpenCode stores, when no editor plugin has one.

        Someone who drives Copilot through OpenCode rather than through VS Code
        has a perfectly good local Copilot login, just not where the editor
        plugin keeps it. This is the same class of file as every other source
        here — local, on the user's own machine, read immediately before the
        request — and is documented as a fallback in the design note.
        """
        try:
            raw = json.loads((self.home / ".local" / "share" / "opencode" / "auth.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        entry = raw.get("github-copilot") if isinstance(raw, dict) else None
        token = entry.get("access") if isinstance(entry, dict) else None
        return token.strip() if isinstance(token, str) and token.strip() else None

    def has_local_credentials(self) -> bool:
        return self._token() is not None

    def refresh(self, now: datetime) -> QuotaSnapshot:
        token = self._token()
        if not token:
            raise RuntimeError(NOT_SIGNED_IN)
        status, payload = self.fetch_json(self.usage_url, {
            "Authorization": f"token {token}",
            "Editor-Version": "vscode/1.96.2",
            "Editor-Plugin-Version": "copilot-chat/0.26.7",
            "User-Agent": "GitHubCopilotChat/0.26.7",
            "X-Github-Api-Version": "2025-04-01",
        })
        if status in (401, 403):
            raise RuntimeError(LOGIN_REJECTED)
        if not 200 <= status < 300:
            raise RuntimeError("usage request failed")
        reset = _date(payload.get("quota_reset_date")) or _date(payload.get("limited_user_reset_date"))
        resources: Dict[str, QuotaResource] = {}
        snapshots = payload.get("quota_snapshots")
        if isinstance(snapshots, dict):
            for source, key in (("premium_interactions", "credits"), ("chat", "chat"), ("completions", "completions")):
                entry = snapshots.get(source)
                if not isinstance(entry, dict) or entry.get("unlimited") is True:
                    continue
                entitlement, remaining = _number(entry.get("entitlement")), _number(entry.get("remaining"))
                if entitlement is None or entitlement <= 0 or entitlement == -1 or remaining == -1:
                    continue
                resources[key] = QuotaResource(
                    kind="consumption", unit="percent", used=min(100, max(0, 100 - (remaining / entitlement) * 100)),
                    limit=100, resets_at=reset, window_seconds=30 * 24 * 60 * 60,
                )
                if source == "premium_interactions" and entry.get("overage_permitted") is True:
                    resources["extraUsage"] = QuotaResource(
                        kind="usage", unit="credits", used=max(0, _number(entry.get("overage_count")) or 0),
                        estimated=True,
                    )
        if not resources:
            limited = payload.get("limited_user_quotas")
            monthly = payload.get("monthly_quotas")
            if isinstance(limited, dict) and isinstance(monthly, dict):
                for key in ("chat", "completions"):
                    remaining, total = _number(limited.get(key)), _number(monthly.get(key))
                    if remaining is not None and total and total > 0:
                        resources[key] = QuotaResource(
                            kind="consumption", unit="percent", used=min(100, max(0, (total - remaining) / total * 100)),
                            limit=100, resets_at=reset, window_seconds=30 * 24 * 60 * 60,
                        )
        if not resources and payload.get("token_based_billing") is not True:
            raise RuntimeError("invalid response")
        return QuotaSnapshot(self.provider_id, self.display_name, now, resources, _title(payload.get("copilot_plan")))


class CursorQuotaProvider:
    """Read Cursor's local VS Code state database and its dashboard quota API.

    Cursor also keeps credentials in Keychain on some installations. The state
    database is intentionally the only source here: it is a read-only, local
    probe that never causes a Keychain prompt or changes an installed session.
    """

    provider_id = "cursor"
    display_name = "Cursor"
    sign_in_hint = "Cursor's saved session has expired. Sign in again in the Cursor app."
    usage_url = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"

    def __init__(self, home: Optional[Path] = None, post_json: FetchJSON = _post_json) -> None:
        self.home = home or Path.home()
        self.post_json = post_json

    @property
    def _state_path(self) -> Path:
        return self.home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"

    def _state_value(self, key: str) -> Optional[str]:
        if not self._state_path.exists():
            return None
        try:
            with sqlite3.connect(f"file:{self._state_path}?mode=ro", uri=True) as connection:
                row = connection.execute("SELECT value FROM ItemTable WHERE key = ? LIMIT 1", (key,)).fetchone()
        except sqlite3.Error:
            return None
        value = row[0] if row else None
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _auth(self) -> Optional[Dict[str, str]]:
        access = self._state_value("cursorAuth/accessToken")
        if not access:
            return None
        membership = self._state_value("cursorAuth/stripeMembershipType")
        return {"access": access, "membership": membership or ""}

    def has_local_credentials(self) -> bool:
        return self._auth() is not None

    @staticmethod
    def _expired(token: str, now: datetime) -> bool:
        """Read the session JWT's own ``exp`` claim before spending a request.

        Cursor leaves the last token in its state database after it lapses, so a
        stale entry is indistinguishable from a live one until the server
        answers ERROR_NOT_LOGGED_IN. The claim is only read to decide whether
        asking is worthwhile; the signature is never trusted for anything.
        """
        parts = token.split(".")
        if len(parts) != 3:
            return False
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False
        expiry = _number(claims.get("exp")) if isinstance(claims, dict) else None
        return expiry is not None and expiry <= now.timestamp()

    @staticmethod
    def _cycle(value: Dict[str, Any]) -> tuple[Optional[datetime], Optional[float]]:
        start, end = _number(value.get("billingCycleStart")), _number(value.get("billingCycleEnd"))
        if end is None:
            return None, None
        # Cursor's dashboard RPC uses epoch milliseconds. Do not guess a reset
        # when the response no longer contains those documented bounds.
        reset = datetime.fromtimestamp(end / 1000, tz=timezone.utc)
        return reset, (end - start) / 1000 if start is not None and end > start else None

    def refresh(self, now: datetime) -> QuotaSnapshot:
        auth = self._auth()
        if not auth:
            raise RuntimeError(NOT_SIGNED_IN)
        if self._expired(auth["access"], now):
            raise RuntimeError(SESSION_EXPIRED)
        status, payload = self.post_json(self.usage_url, {
            "Authorization": f"Bearer {auth['access']}",
            "Connect-Protocol-Version": "1",
        })
        if status in (401, 403):
            raise RuntimeError(SESSION_EXPIRED)
        if not 200 <= status < 300 or payload.get("enabled") is False:
            raise RuntimeError("usage request failed")

        reset, duration = self._cycle(payload)
        resources: Dict[str, QuotaResource] = {}
        usage = payload.get("planUsage")
        if isinstance(usage, dict):
            total = _number(usage.get("totalPercentUsed"))
            if total is None:
                limit, spent = _number(usage.get("limit")), _number(usage.get("totalSpend"))
                total = (spent / limit * 100) if limit and limit > 0 and spent is not None else None
            for source, key in ((total, "monthly"), (_number(usage.get("autoPercentUsed")), "cursorModels"), (_number(usage.get("apiPercentUsed")), "otherModels")):
                if source is not None:
                    resources[key] = QuotaResource(
                        kind="consumption", unit="percent", used=min(100, max(0, source)), limit=100,
                        resets_at=reset, window_seconds=duration,
                    )
        spend = payload.get("spendLimitUsage")
        if isinstance(spend, dict):
            limit = _number(spend.get("individualLimit")) or _number(spend.get("pooledLimit"))
            remaining = _number(spend.get("individualRemaining")) or _number(spend.get("pooledRemaining"))
            used = _number(spend.get("individualUsed")) or _number(spend.get("pooledUsed"))
            if used is None and limit is not None and remaining is not None:
                used = max(0, limit - remaining)
            if used is not None:
                resources["onDemand"] = QuotaResource(
                    kind="spend", unit="usd", used=max(0, used) / 100,
                    limit=max(0, limit) / 100 if limit is not None else None,
                    resets_at=reset, window_seconds=duration,
                )
        if not resources:
            raise RuntimeError("invalid response")
        return QuotaSnapshot(self.provider_id, self.display_name, now, resources, _title(auth["membership"]))


class GrokQuotaProvider:
    provider_id = "grok"
    display_name = "Grok Code Fast"
    sign_in_hint = "Grok's saved login has expired. Run `grok` and sign in again."
    billing_url = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
    settings_url = "https://cli-chat-proxy.grok.com/v1/settings"

    token_url = "https://auth.x.ai/oauth2/token"

    def __init__(
        self,
        home: Optional[Path] = None,
        fetch_json: FetchJSON = _fetch_json,
        post_form: Callable[[str, Dict[str, str]], tuple[int, Dict[str, Any]]] = _post_form,
    ) -> None:
        self.home = home or Path.home()
        self.fetch_json = fetch_json
        self.post_form = post_form

    def _auth(self) -> Optional[Dict[str, Any]]:
        try:
            raw = json.loads((self.home / ".grok" / "auth.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        for entry in raw.values():
            token = entry.get("key") if isinstance(entry, dict) else None
            if isinstance(token, str) and token.strip():
                return entry
        return None

    def has_local_credentials(self) -> bool:
        return self._auth() is not None

    def _refreshed_token(self, entry: Dict[str, Any]) -> Optional[str]:
        """Exchange the stored refresh token for a live one, in memory only.

        The Grok CLI's access token lasts six hours, so a machine that has not
        run Grok today always holds a dead one. ``~/.grok/auth.json`` is never
        rewritten: mutating another agent's session file could log the user out
        of their own CLI, so the fresh token lives only for this request.

        That is only safe because x.ai's rotation is non-invalidating. It does
        return a new refresh token each time, but the stored one keeps working
        (verified by replaying the same token twice: both calls answer 200). A
        provider that invalidated on use would need the opposite design, since
        discarding the rotated token would break the user's own CLI.
        """
        refresh, client = entry.get("refresh_token"), entry.get("oidc_client_id")
        if not isinstance(refresh, str) or not refresh.strip() or not isinstance(client, str) or not client.strip():
            return None
        try:
            status, payload = self.post_form(self.token_url, {
                "grant_type": "refresh_token",
                "refresh_token": refresh.strip(),
                "client_id": client.strip(),
            })
        except RuntimeError:
            return None
        token = payload.get("access_token") if 200 <= status < 300 else None
        return token.strip() if isinstance(token, str) and token.strip() else None

    def _access_token(self, entry: Dict[str, Any], now: datetime) -> tuple[str, bool]:
        stored = str(entry.get("key") or "").strip()
        expiry = _date(entry.get("expires_at"))
        if expiry is None or expiry > now:
            return stored, False
        return self._refreshed_token(entry) or stored, True

    def refresh(self, now: datetime) -> QuotaSnapshot:
        entry = self._auth()
        if not entry:
            raise RuntimeError(NOT_SIGNED_IN)
        token, was_stale = self._access_token(entry, now)
        headers = {"Authorization": f"Bearer {token}", "X-XAI-Token-Auth": "xai-grok-cli"}
        status, payload = self.fetch_json(self.billing_url, headers)
        if status in (401, 403):
            raise RuntimeError(SESSION_EXPIRED if was_stale else LOGIN_REJECTED)
        if not 200 <= status < 300:
            raise RuntimeError("usage request failed")
        config = payload.get("config")
        period = config.get("currentPeriod") if isinstance(config, dict) else None
        if not isinstance(config, dict) or not isinstance(period, dict):
            raise RuntimeError("invalid response")
        start, end = _date(period.get("start")), _date(period.get("end"))
        if period.get("type") != "USAGE_PERIOD_TYPE_WEEKLY" or not start or not end or end <= start:
            raise RuntimeError("invalid response")
        percent = _number(config.get("creditUsagePercent"))
        if percent is None:
            percent = 0
        try:
            settings_status, settings = self.fetch_json(self.settings_url, headers)
        except RuntimeError:
            settings_status, settings = 0, {}
        plan = settings.get("subscription_tier_display") if 200 <= settings_status < 300 else None
        return QuotaSnapshot(
            self.provider_id, self.display_name, now,
            {"weekly": QuotaResource(
                kind="consumption", unit="percent", used=min(100, max(0, percent)), limit=100,
                resets_at=end, window_seconds=(end - start).total_seconds(),
            )},
            plan if isinstance(plan, str) and plan.strip() else None,
        )


def _gemini_cli_roots(home: Path, environment: Dict[str, str]) -> Iterable[Path]:
    """Plausible install roots for the @google/gemini-cli package."""
    seen: set[Path] = set()
    candidates = [
        home / ".nvm" / "versions" / "node",
        Path("/opt/homebrew/lib/node_modules"),
        Path("/usr/local/lib/node_modules"),
        home / ".npm-global" / "lib" / "node_modules",
    ]
    for base in candidates:
        if not base.exists():
            continue
        roots = [base] if base.name == "node_modules" else [
            version / "lib" / "node_modules" for version in sorted(base.iterdir()) if version.is_dir()
        ]
        for root in roots:
            package = root / "@google" / "gemini-cli"
            if package.exists() and package not in seen:
                seen.add(package)
                yield package


def _lacks_code_assist_licence(payload: Dict[str, Any]) -> bool:
    """Tell "this account has no Code Assist entitlement" from "bad token".

    Google answers both with 403. The individual free tier was retired in favour
    of Antigravity, so an ordinary personal Gemini CLI login now returns
    SUBSCRIPTION_REQUIRED — an accurate account state, not a failure to fix.
    """
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    if str(error.get("status")) == "PERMISSION_DENIED" and "license" in str(error.get("message", "")).lower():
        return True
    for detail in error.get("details", []) if isinstance(error.get("details"), list) else []:
        if isinstance(detail, dict) and detail.get("reason") in ("SUBSCRIPTION_REQUIRED", "UNSUPPORTED_CLIENT"):
            return True
    return False


class GeminiQuotaProvider:
    """Read Gemini CLI OAuth credentials and Google Code Assist quota RPCs.

    The access token in ``~/.gemini/oauth_creds.json`` is short lived. When it
    has expired, it is refreshed in memory with Google's token endpoint using
    the OAuth client that ships inside the public Gemini CLI. The credentials
    file itself is never modified, so the agent's own session state is left
    untouched.
    """

    provider_id = "gemini"
    display_name = "Gemini CLI"
    sign_in_hint = "Gemini's saved login has expired. Run `gemini` and sign in again."
    entitlement_hint = ("This Google account has no Gemini Code Assist licence, so there is no quota to read. "
                        "The individual free tier was retired in favour of Antigravity.")
    assist_url = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
    usage_url = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"
    token_url = "https://oauth2.googleapis.com/token"
    # The installed CLI's own OAuth client. Google issues a "secret" to
    # installed apps that is not actually confidential, but committing one to a
    # public repository trips secret scanning and reads like a real leak, so it
    # is located in the installed bundle at run time instead of being vendored.
    # No CLI on the machine simply means no refresh, and an expired session is
    # reported as such.
    client_id = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
    client_secret_pattern = "GOCSPX-[A-Za-z0-9_-]{16,}"

    def __init__(
        self,
        home: Optional[Path] = None,
        post_json: Callable[..., tuple[int, Dict[str, Any]]] = _post_json,
        post_form: Callable[[str, Dict[str, str]], tuple[int, Dict[str, Any]]] = _post_form,
        environment: Optional[Dict[str, str]] = None,
    ) -> None:
        self.home = home or Path.home()
        self.post_json = post_json
        self.post_form = post_form
        self.environment = environment if environment is not None else os.environ
        self._cached_secret: Optional[str] = None

    def _credential_paths(self) -> Iterable[Path]:
        yield self.home / ".gemini" / "oauth_creds.json"
        yield self.home / ".config" / "gemini" / "oauth_creds.json"

    def _auth(self) -> Optional[Dict[str, Any]]:
        for path in self._credential_paths():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            access = raw.get("access_token") if isinstance(raw, dict) else None
            if isinstance(access, str) and access.strip():
                return raw
        return None

    def has_local_credentials(self) -> bool:
        return self._auth() is not None

    def _client_secret(self) -> Optional[str]:
        """Find the installed Gemini CLI's OAuth client secret on disk.

        Only files belonging to the CLI's own bundle are searched, and only for
        the constant that pairs with ``client_id``; nothing is written back.
        """
        if self._cached_secret is not None:
            return self._cached_secret or None
        pattern = re.compile(self.client_secret_pattern)
        for root in _gemini_cli_roots(self.home, self.environment):
            for path in sorted(root.glob("**/*.js"))[:400]:
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if self.client_id not in text:
                    continue
                match = pattern.search(text)
                if match:
                    self._cached_secret = match.group(0)
                    return self._cached_secret
        self._cached_secret = ""
        return None

    def _refreshed_token(self, refresh_token: Any) -> Optional[str]:
        secret = self._client_secret()
        if not isinstance(refresh_token, str) or not refresh_token.strip() or not secret:
            return None
        try:
            status, payload = self.post_form(self.token_url, {
                "client_id": self.client_id,
                "client_secret": secret,
                "refresh_token": refresh_token.strip(),
                "grant_type": "refresh_token",
            })
        except RuntimeError:
            return None
        token = payload.get("access_token") if 200 <= status < 300 else None
        return token.strip() if isinstance(token, str) and token.strip() else None

    def _access_token(self, credentials: Dict[str, Any], now: datetime) -> tuple[str, bool]:
        """Return a usable token and whether the stored one had already lapsed.

        A failed refresh previously fell back to the dead token silently, so an
        unrefreshable session was reported as a rejected login. The staleness
        flag keeps those two outcomes distinguishable.
        """
        token = str(credentials.get("access_token")).strip()
        expiry = _number(credentials.get("expiry_date"))
        if expiry is None or expiry / 1000 > now.timestamp():
            return token, False
        return self._refreshed_token(credentials.get("refresh_token")) or token, True

    def _project_and_tier(self, headers: Dict[str, str]) -> tuple[Optional[str], Optional[str]]:
        configured = self.environment.get("GOOGLE_CLOUD_PROJECT") or self.environment.get("GOOGLE_CLOUD_PROJECT_ID")
        project = configured.strip() if isinstance(configured, str) and configured.strip() else None
        try:
            status, payload = self.post_json(self.assist_url, headers, {
                "metadata": {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"},
            })
        except RuntimeError:
            return project, None
        if not 200 <= status < 300:
            return project, None
        discovered = payload.get("cloudaicompanionProject")
        if isinstance(discovered, str) and discovered.strip():
            project = discovered.strip()
        tier = payload.get("currentTier")
        name = tier.get("name") or tier.get("id") if isinstance(tier, dict) else None
        return project, name if isinstance(name, str) and name.strip() else None

    def refresh(self, now: datetime) -> QuotaSnapshot:
        credentials = self._auth()
        if not credentials:
            raise RuntimeError(NOT_SIGNED_IN)
        token, was_stale = self._access_token(credentials, now)
        headers = {"Authorization": f"Bearer {token}"}
        project, tier = self._project_and_tier(headers)
        status, payload = self.post_json(self.usage_url, headers, {"project": project} if project else {})
        if status == 403 and _lacks_code_assist_licence(payload):
            raise RuntimeError(NOT_ENTITLED)
        if status in (401, 403):
            raise RuntimeError(SESSION_EXPIRED if was_stale else LOGIN_REJECTED)
        if not 200 <= status < 300:
            raise RuntimeError("usage request failed")
        buckets = payload.get("buckets")
        if not isinstance(buckets, list):
            raise RuntimeError("invalid response")
        # Buckets repeat per token type; the lowest remaining fraction is the
        # binding constraint for the model, so keep that one.
        fractions: Dict[str, float] = {}
        resets: Dict[str, datetime] = {}
        for bucket in buckets:
            if not isinstance(bucket, dict):
                continue
            model = bucket.get("modelId")
            fraction = _number(bucket.get("remainingFraction"))
            if not isinstance(model, str) or not model.strip() or fraction is None:
                continue
            model = model.strip()
            if model not in fractions or fraction < fractions[model]:
                fractions[model] = fraction
                reset = _date(bucket.get("resetTime"))
                if reset:
                    resets[model] = reset
        resources = {
            model: QuotaResource(
                kind="consumption", unit="percent",
                used=min(100.0, max(0.0, (1.0 - fraction) * 100)), limit=100,
                resets_at=resets.get(model),
            )
            for model, fraction in sorted(fractions.items())
        }
        return QuotaSnapshot(self.provider_id, self.display_name, now, resources, _title(tier))


class AntigravityQuotaProvider:
    """Antigravity's pool quotas, read from the server it already runs locally.

    Antigravity is Google's rebuild of the Codeium/Windsurf stack and it kept
    that lineage's local RPC server: each surface (the IDE, the 2.0 app, the
    ``agy`` CLI) launches a ``language_server`` child that answers the very
    quota call Antigravity's own UI renders. Both the port and the CSRF token
    guarding it sit on that process's command line, so this provider reads no
    credential of the user's, stores none and refreshes none — the reason it
    needs no keychain access and works the same on every platform.

    The header name is the giveaway for that history: the server still wants
    ``x-codeium-csrf-token``, not an Antigravity-branded one.

    The catch is that only a surface started with a real ``--https_server_port``
    serves it; one launched with ``--https_server_port 0`` (the 2.0 hub, and
    ``agy`` on its own) has no listener at all. So quota is readable while
    Antigravity is open and not otherwise, and that is reported as its own
    state rather than as "signed out", which would send the user off to repair
    a login that is perfectly fine.
    """

    provider_id = "antigravity"
    display_name = "Antigravity"
    service = "exa.language_server_pb.LanguageServerService"
    csrf_header = "x-codeium-csrf-token"
    not_running_hint = (
        "Antigravity reports quota only while it is running. "
        "Open Antigravity and refresh."
    )
    entitlement_hint = "This Antigravity account reports no pool quotas."

    # ``bucketId`` -> the resource key the dashboard labels. Antigravity pools
    # every Gemini model into one allowance and every third-party model
    # ("3p": Claude, GPT-OSS) into another, each with a rolling five-hour and a
    # weekly window. Using either Gemini model drains the one Gemini pool, so
    # there is deliberately no per-model meter to show.
    #
    # An unrecognised bucket id is skipped rather than guessed: drawing a new
    # pool as one of these four would overwrite a real meter with someone
    # else's number, which is worse than the bucket simply not appearing.
    BUCKETS = {
        "gemini-5h": "session",
        "gemini-weekly": "weekly",
        "3p-5h": "claude",
        "3p-weekly": "claudeWeekly",
    }
    # The payload names its window but never says how long one is, so the
    # length comes from the name. Anything else is left unset rather than
    # assumed.
    WINDOW_SECONDS = {"5h": 5 * 3600.0, "weekly": 7 * 24 * 3600.0}

    def __init__(
        self,
        home: Optional[Path] = None,
        command_lines: Callable[[], List[str]] = _process_command_lines,
        post_json: Callable[
            [int, str, Dict[str, str], Dict[str, Any]], tuple[int, Dict[str, Any]]
        ] = _post_loopback_json,
    ) -> None:
        self.home = home or Path.home()
        self.command_lines = command_lines
        self.post_json = post_json

    @staticmethod
    def _is_language_server(line: str) -> bool:
        """True when the line's own executable is a language server.

        Matching anywhere in the line would also accept a shell, an editor or
        a test runner that merely quotes one of these commands in its
        arguments — which could then point the request at an unrelated
        loopback listener. Only the executable decides.
        """
        if line.startswith('"'):
            end = line.find('"', 1)
            executable = line[1:end] if end > 0 else line[1:]
        else:
            # Split at the first flag, not the first space: the real install
            # path is "/Applications/Antigravity IDE.app/.../language_server",
            # which `ps` prints unquoted, spaces and all.
            executable = line.split(" --", 1)[0]
        return executable.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].startswith("language_server")

    def _servers(self) -> List[tuple[int, str]]:
        """Every local language server that is actually serving HTTPS."""
        found: List[tuple[int, str]] = []
        for line in self.command_lines():
            if not self._is_language_server(line):
                continue
            port = re.search(r"--https_server_port[= ](\d+)", line)
            # The same line also carries --extension_server_csrf_token, which
            # opens a different port and is rejected by this one. Requiring the
            # two leading dashes is what keeps them apart: the decoy has an
            # underscore in front of "csrf_token".
            csrf = re.search(r"--csrf_token[=\s]+\"?([^\s\"]+)", line)
            if not port or not csrf or port.group(1) == "0":
                continue
            found.append((int(port.group(1)), csrf.group(1)))
        return found

    def has_local_credentials(self) -> bool:
        """True once Antigravity is installed, whether or not it is running.

        Answering False while it is closed would report "no local credentials
        found", which is both wrong and unactionable. Claiming it instead lets
        ``refresh`` fail with the accurate reason.
        """
        root = self.home / ".gemini"
        return any(
            (root / name).is_dir()
            for name in ("antigravity", "antigravity-cli", "antigravity-ide")
        )

    def _call(self, port: int, csrf: str, method: str) -> tuple[int, Dict[str, Any]]:
        return self.post_json(
            port, f"/{self.service}/{method}", {self.csrf_header: csrf}, {},
        )

    def refresh(self, now: datetime) -> QuotaSnapshot:
        servers = self._servers()
        if not servers:
            raise RuntimeError(AGENT_NOT_RUNNING)
        # Several surfaces can be open at once and they do not all belong to
        # the same signed-in state, so a rejection by one is not an answer for
        # all: keep trying and report the last failure only if none worked.
        failure: Optional[Exception] = None
        for port, csrf in servers:
            try:
                return self._snapshot(port, csrf, now)
            except RuntimeError as error:
                failure = error
        raise failure or RuntimeError(AGENT_NOT_RUNNING)

    def _snapshot(self, port: int, csrf: str, now: datetime) -> QuotaSnapshot:
        status, payload = self._call(port, csrf, "RetrieveUserQuotaSummary")
        if status in (401, 403):
            raise RuntimeError(LOGIN_REJECTED)
        if not 200 <= status < 300:
            raise RuntimeError("usage request failed")
        response = payload.get("response")
        groups = response.get("groups") if isinstance(response, dict) else None
        if not isinstance(groups, list):
            raise RuntimeError("invalid response")

        resources: Dict[str, QuotaResource] = {}
        offered = sound = 0
        for group in groups:
            if not isinstance(group, dict):
                continue
            buckets = group.get("buckets")
            if not isinstance(buckets, list):
                continue
            for bucket in buckets:
                offered += 1
                if not isinstance(bucket, dict):
                    continue
                bucket_id = bucket.get("bucketId")
                fraction = _number(bucket.get("remainingFraction"))
                # Rejects NaN and either infinity as well as a plainly
                # impossible fraction: every comparison against NaN is False,
                # so the chain collapses and the negation throws it out. Left
                # to the clamp below, a fraction of 5 would render as a
                # confident "0% used" and a fraction of -1 as "100% used".
                if not isinstance(bucket_id, str) or fraction is None or not 0.0 <= fraction <= 1.0:
                    continue
                sound += 1
                key = self.BUCKETS.get(bucket_id)
                if key is None:
                    continue
                # A pool with nothing spent has no window to reset: the server
                # has no start to count from and answers `now + window`, so the
                # value slides forward on every refresh. Copying it faithfully
                # would render a countdown that never counts down. Dropping it
                # is what makes the meter honest -- wire() omits the key, and
                # both the panel and the gauge already render a window without
                # a reset time. Exact 1 is the signal; any real usage gives
                # 0.9999...
                started = fraction < 1.0
                # The payload reports what is LEFT; every other provider here
                # reports what is SPENT. Inverting this renders a barely-used
                # week as nearly exhausted, and looks entirely plausible.
                resources[key] = QuotaResource(
                    kind="consumption", unit="percent",
                    used=min(100.0, max(0.0, (1.0 - fraction) * 100)), limit=100,
                    resets_at=_date(bucket.get("resetTime")) if started else None,
                    window_seconds=self.WINDOW_SECONDS.get(str(bucket.get("window") or "")),
                )
        if not resources:
            # Empty for two very different reasons, and the user acts on each
            # differently. Buckets that arrived but none of which parsed means
            # the schema moved under us — a fault worth an error row. Buckets
            # that parsed but are all unrecognised, or none offered at all, is
            # an account that reports no pools, which is not a fault.
            raise RuntimeError("invalid response" if offered and not sound else NOT_ENTITLED)
        return QuotaSnapshot(
            self.provider_id, self.display_name, now, resources, self._plan(port, csrf),
        )

    def _plan(self, port: int, csrf: str) -> Optional[str]:
        """The plan label, from the status call the same server answers.

        Never fatal: a snapshot carrying real numbers and no plan name is far
        more useful than no snapshot, so every failure here degrades to None.
        """
        try:
            status, payload = self._call(port, csrf, "GetUserStatus")
        except RuntimeError:
            return None
        if not 200 <= status < 300:
            return None
        user = payload.get("userStatus")
        if not isinstance(user, dict):
            return None
        # Antigravity's own tier wins over the Windsurf plan field it
        # inherited, which older builds still fill in with a stale name.
        tier = user.get("userTier")
        if isinstance(tier, str) and tier.strip():
            return _title(tier)
        status_block = user.get("planStatus")
        info = status_block.get("planInfo") if isinstance(status_block, dict) else None
        return _title(info.get("planName")) if isinstance(info, dict) else None


class StaticQuotaProvider:
    """An explicitly visible harness with no safe native quota source yet."""

    def __init__(self, provider_id: str, display_name: str, detail: str) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.detail = detail

    def has_local_credentials(self) -> bool:
        return False

    def refresh(self, now: datetime) -> QuotaSnapshot:
        raise RuntimeError("unsupported")

    def capability(self) -> Dict[str, str]:
        return {"displayName": self.display_name, "state": "notSupported", "detail": self.detail}


def _classify(provider: Any, error: Exception) -> tuple[str, str]:
    """Turn a refresh failure into a state the dashboard can act on."""
    reason = str(error)
    if reason == NOT_SIGNED_IN:
        return "notSignedIn", "No local credentials found."
    if reason == SESSION_EXPIRED:
        hint = getattr(provider, "sign_in_hint", None)
        return "sessionExpired", hint or "The saved login has expired. Sign in with this agent again."
    if reason == NOT_ENTITLED:
        hint = getattr(provider, "entitlement_hint", None)
        return "notEntitled", hint or "This account has no plan quota to report."
    if reason == LOGIN_REJECTED:
        return "notSignedIn", "The saved login was rejected. Sign in with this agent again."
    if reason == AGENT_NOT_RUNNING:
        # Its own state, because none of the others are true: the user is
        # signed in and entitled, and nothing failed. The agent is just shut.
        hint = getattr(provider, "not_running_hint", None)
        return "notRunning", hint or "This agent reports quota only while it is running."
    return "refreshFailed", "Could not refresh quota data."


class QuotaService:
    def __init__(
        self,
        providers: Iterable[QuotaProvider],
        cache_path: Optional[Path] = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.providers = list(providers)
        self.cache_path = cache_path or data_dir() / "quotas.json"
        self.now = now
        self._snapshots: Dict[str, QuotaSnapshot] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def collect(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            # The interprocess lock guards *refreshing and writing*, not
            # reading: writes are atomic replaces, so a read sees either the
            # prior complete cache or the next one. It exists so two processes
            # (dashboard + menubar) don't fetch the same quotas twice or
            # overwrite a newer snapshot with an older one.
            #
            # A caller that loses the race does neither of those things: it
            # reads the cache and returns. So a background poll should not
            # queue behind a refresh it is not going to perform. Waiting the
            # full timeout blocked the response for that long and then served
            # the very same file it could have read immediately, which blanked
            # the Plan-limits UI for no reason. Poll with no wait; an explicit
            # refresh still waits, because someone is watching that one.
            #
            # Nothing is reported for the ordinary case: each snapshot already
            # carries fetchedAt / expiresAt / stale, so the caller can see for
            # itself how old the numbers are.
            with _CacheFileLock(
                self.cache_path,
                timeout=CACHE_LOCK_TIMEOUT_SECONDS if force else 0,
            ) as acquired:
                if not acquired:
                    # Another process is still collecting. Its atomic replace
                    # means this read is either the prior complete cache or the
                    # next complete cache; never write a competing snapshot.
                    self._load(reload=True)
                    errors: List[Dict[str, str]] = []
                    if not self._snapshots:
                        # No cached snapshot exists yet, so the response would
                        # otherwise be indistinguishable from "no agents
                        # configured" and every surface would render empty.
                        errors.append({
                            "providerId": "quotaCache",
                            "message": "Another process is refreshing the quota "
                                       "cache and no snapshot has been stored yet.",
                        })
                    return self._wire(self.now(), errors)

                # Reload *inside* the process lock. A long-lived dashboard or
                # menubar instance may have loaded a stale cache before another
                # instance refreshed it, and must not overwrite that newer file.
                self._load(reload=True)
                generated_at = self.now()
                errors = []
                capabilities: Dict[str, Dict[str, str]] = {}
                for provider in self.providers:
                    current = self._snapshots.get(provider.provider_id)
                    explicit = getattr(provider, "capability", None)
                    if callable(explicit):
                        capabilities[provider.provider_id] = explicit()
                        continue
                    is_fresh = current and generated_at < current.fetched_at + FRESHNESS
                    if not force and is_fresh:
                        capabilities[provider.provider_id] = {"displayName": provider.display_name, "state": "available"}
                        continue
                    if not provider.has_local_credentials():
                        capabilities[provider.provider_id] = {
                            "displayName": provider.display_name,
                            "state": "notSignedIn",
                            "detail": "No local credentials found.",
                        }
                        continue
                    try:
                        self._snapshots[provider.provider_id] = provider.refresh(generated_at)
                        capabilities[provider.provider_id] = {"displayName": provider.display_name, "state": "available"}
                    except Exception as error:
                        state, detail = _classify(provider, error)
                        capabilities[provider.provider_id] = {
                            "displayName": provider.display_name, "state": state, "detail": detail,
                        }
                        # A signed-out, expired or unlicensed account is a fact about
                        # the account, not a fault. Only a genuine fetch failure gets
                        # an error row, so the dashboard's warning stays meaningful.
                        if state == "refreshFailed":
                            errors.append({"providerId": provider.provider_id, "message": detail})
                self._save(generated_at)
                return self._wire(generated_at, errors, capabilities)

    def _wire(
        self,
        generated_at: datetime,
        errors: List[Dict[str, str]],
        capabilities: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "generatedAt": _iso(generated_at),
            "providers": {
                provider_id: snapshot.wire(generated_at)
                for provider_id, snapshot in sorted(self._snapshots.items())
            },
            "errors": errors,
            "capabilities": dict(sorted((capabilities or {}).items())),
        }

    def _load(self, reload: bool = False) -> None:
        if self._loaded and not reload:
            return
        self._loaded = True
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
            providers = value.get("providers") if isinstance(value, dict) else None
            if not isinstance(providers, dict):
                return
            loaded_at = self.now()
            snapshots = {
                provider_id: snapshot
                for provider_id, raw in providers.items()
                if isinstance(raw, dict) and (snapshot := QuotaSnapshot.from_wire(provider_id, raw, loaded_at))
            }
        except (OSError, json.JSONDecodeError):
            return
        self._snapshots = snapshots

    def _save(self, generated_at: datetime) -> None:
        temporary: Optional[Path] = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._wire(generated_at, [])
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.cache_path.parent,
                prefix=f".{self.cache_path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, separators=(",", ":"))
            os.replace(temporary, self.cache_path)
        except OSError:
            return
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def default_quota_providers() -> List[QuotaProvider]:
    """The ordered provider roster for the local API and any desktop/menubar client.

    Native sources first, in the order the dashboard lists them, then every
    other supported agent as a static entry so a harness is never silently
    missing from the quota page. Construction only: no credentials are read and
    nothing is written.
    """
    return [
        CodexQuotaProvider(),
        ClaudeQuotaProvider(),
        CursorQuotaProvider(),
        OpenCodeQuotaProvider(),
        CopilotQuotaProvider(),
        GrokQuotaProvider(),
        GeminiQuotaProvider(),
        AntigravityQuotaProvider(),
        StaticQuotaProvider("qwen", "Qwen CLI", "Qwen's OAuth free tier was discontinued and its Coding Plan key exposes no account-quota endpoint."),
        StaticQuotaProvider("vibe", "Vibe", "Vibe routes to configured model providers, so it has no account quota of its own."),
        StaticQuotaProvider("hermes", "Hermes Agent", "Hermes routes to configured model providers, so it has no account quota of its own."),
        StaticQuotaProvider("cline", "Cline", "Cline routes to configured model providers, so it has no account quota of its own."),
        StaticQuotaProvider("pi", "Pi", "Pi routes to configured model providers, so it has no account quota of its own."),
        StaticQuotaProvider("smallcode", "SmallCode", "SmallCode routes to configured model providers, so it has no account quota of its own."),
        StaticQuotaProvider("muse", "Muse Code", "Muse Code's local session exposes no plan-quota API."),
        StaticQuotaProvider("prime", "Prime Agent", "Prime routes to configured model providers, so it has no account quota of its own."),
        StaticQuotaProvider("dsh", "DeepSeek Harness", "The DeepSeek harness bills per API key; usage belongs to that key's own account page."),
        StaticQuotaProvider("qoder", "Qoder", "Qoder keeps its plan and usage state server-side; nothing local reports it."),
        StaticQuotaProvider("openai_compat", "OpenAI-compatible server", "This is a user-configured endpoint, so quota belongs to that provider's own account API."),
    ]
