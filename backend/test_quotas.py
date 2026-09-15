"""Tests for native provider quota collection and stale-while-revalidate cache."""

from __future__ import annotations

import json
import sys
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quotas as quotas_module
from quotas import (
    AGENT_NOT_RUNNING,
    AntigravityQuotaProvider,
    CACHE_LOCK_TIMEOUT_SECONDS,
    _CacheFileLock,
    ClaudeQuotaProvider,
    CodexQuotaProvider,
    CopilotQuotaProvider,
    CursorQuotaProvider,
    FRESHNESS,
    GeminiQuotaProvider,
    GrokQuotaProvider,
    OpenCodeQuotaProvider,
    QuotaService,
    QuotaSnapshot,
    StaticQuotaProvider,
    default_quota_providers,
)


def test_codex_provider_normalizes_windows_credits_and_reset_expiries(tmp_path):
    home = tmp_path / "home"
    codex = home / ".codex"
    codex.mkdir(parents=True)
    (codex / "auth.json").write_text(json.dumps({
        "tokens": {"access_token": "token", "account_id": "account"},
    }))

    def fetch(url, headers):
        if url.endswith("rate-limit-reset-credits"):
            return 200, {"credits": [{"expires_at": "2026-09-02T10:00:00Z"}]}
        return 200, {
            "plan_type": "pro",
            "rate_limit": {
                "primary_window": {
                    "used_percent": 18,
                    "limit_window_seconds": 18_000,
                    "reset_after_seconds": 900,
                },
                "secondary_window": {
                    "used_percent": 45,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_788_339_600,
                },
            },
            "rate_limit_reset_credits": {"available_count": 1},
            "credits": {"balance": 25},
        }

    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    snapshot = CodexQuotaProvider(home=home, fetch_json=fetch).refresh(now)

    assert snapshot.plan == "Pro 20x"
    assert snapshot.resources["session"].used == 18
    assert snapshot.resources["session"].limit == 100
    assert snapshot.resources["session"].resets_at == now + timedelta(minutes=15)
    assert snapshot.resources["weekly"].used == 45
    assert snapshot.resources["credits"].available == 25
    assert snapshot.resources["rateLimitResets"].available == 1
    assert snapshot.resources["rateLimitResets"].expires_at == [datetime(2026, 9, 2, 10, tzinfo=timezone.utc)]


def test_claude_provider_maps_session_weekly_and_extra_usage(tmp_path):
    home = tmp_path / "home"
    credentials = home / ".claude" / ".credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text(json.dumps({
        "claudeAiOauth": {
            "accessToken": "token",
            "subscriptionType": "max",
            "rateLimitTier": "default_claude_max_20x",
        },
    }))

    snapshot = ClaudeQuotaProvider(home=home, fetch_json=lambda _url, _headers: (200, {
        "five_hour": {"utilization": 12, "resets_at": "2026-09-01T05:00:00Z"},
        "seven_day": {"utilization": 34, "resets_at": "2026-09-07T00:00:00Z"},
        "extra_usage": {"is_enabled": True, "used_credits": 250, "monthly_limit": 1_000},
    })).refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))

    assert snapshot.plan == "Max 20x"
    assert snapshot.resources["session"].used == 12
    assert snapshot.resources["weekly"].used == 34
    assert snapshot.resources["extraUsage"].used == 2.5
    assert snapshot.resources["extraUsage"].limit == 10
    assert snapshot.resources["extraUsage"].unit == "usd"


def test_opencode_and_copilot_providers_normalize_their_native_quota_shapes(tmp_path):
    home = tmp_path / "home"
    opencode_auth = home / ".local" / "share" / "opencode" / "auth.json"
    opencode_auth.parent.mkdir(parents=True)
    opencode_auth.write_text(json.dumps({"opencode-go": {"key": "go-key"}}))
    opencode = OpenCodeQuotaProvider(home=home, fetch_json=lambda _url, _headers: (200, {
        "usage": {
            "rolling": {"percent": 22, "resetsAt": "2026-09-01T04:00:00Z"},
            "weekly": {"percent": 44, "resetsAt": "2026-09-08T00:00:00Z"},
            "monthly": {"percent": 66, "resetsAt": "2026-10-01T00:00:00Z"},
        },
    })).refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))

    copilot_auth = home / ".config" / "github-copilot" / "apps.json"
    copilot_auth.parent.mkdir(parents=True)
    copilot_auth.write_text(json.dumps({"github.com:1": {"oauth_token": "gh-token"}}))
    copilot = CopilotQuotaProvider(home=home, fetch_json=lambda _url, _headers: (200, {
        "copilot_plan": "individual_pro",
        "quota_reset_date": "2026-10-01T00:00:00Z",
        "quota_snapshots": {
            "premium_interactions": {"entitlement": 300, "remaining": 225, "overage_permitted": True, "overage_count": 4},
            "chat": {"unlimited": True},
        },
    })).refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))

    assert opencode.resources["session"].used == 22
    assert opencode.resources["monthly"].resets_at == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert copilot.plan == "Individual Pro"
    assert copilot.resources["credits"].used == 25
    assert copilot.resources["credits"].limit == 100
    assert copilot.resources["extraUsage"].used == 4


def test_cursor_provider_reads_its_local_state_db_and_maps_monthly_quota(tmp_path):
    import sqlite3

    home = tmp_path / "home"
    db = home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    db.parent.mkdir(parents=True)
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    connection.executemany("INSERT INTO ItemTable VALUES (?, ?)", [
        ("cursorAuth/accessToken", "cursor-token"),
        ("cursorAuth/stripeMembershipType", "pro"),
    ])
    connection.commit()
    connection.close()

    def post(url, headers):
        assert url.endswith("GetCurrentPeriodUsage")
        assert headers["Authorization"] == "Bearer cursor-token"
        return 200, {
            "enabled": True,
            "billingCycleStart": 1_788_307_200_000,
            "billingCycleEnd": 1_790_985_600_000,
            "planUsage": {"totalPercentUsed": 27, "autoPercentUsed": 13, "apiPercentUsed": 4},
            "spendLimitUsage": {"individualLimit": 1_000, "individualRemaining": 750},
        }

    snapshot = CursorQuotaProvider(home=home, post_json=post).refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))

    assert snapshot.plan == "Pro"
    assert snapshot.resources["monthly"].used == 27
    assert snapshot.resources["cursorModels"].used == 13
    assert snapshot.resources["otherModels"].used == 4
    assert snapshot.resources["onDemand"].used == 2.5
    assert snapshot.resources["onDemand"].limit == 10


def test_grok_provider_maps_its_weekly_credit_pool(tmp_path):
    home = tmp_path / "home"
    auth = home / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"https://auth.x.ai::account": {"key": "grok-token"}}))

    def fetch(url, headers):
        assert headers["Authorization"] == "Bearer grok-token"
        if url.endswith("/settings"):
            return 200, {"subscription_tier_display": "SuperGrok"}
        return 200, {"config": {"creditUsagePercent": 31, "currentPeriod": {
            "type": "USAGE_PERIOD_TYPE_WEEKLY",
            "start": "2026-09-01T00:00:00Z",
            "end": "2026-09-08T00:00:00Z",
        }}}

    snapshot = GrokQuotaProvider(home=home, fetch_json=fetch).refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))

    assert snapshot.plan == "SuperGrok"
    assert snapshot.resources["weekly"].used == 31
    assert snapshot.resources["weekly"].resets_at == datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_gemini_provider_discovers_project_and_maps_per_model_buckets(tmp_path):
    home = tmp_path / "home"
    credentials = home / ".gemini" / "oauth_creds.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text(json.dumps({"access_token": "stale-token", "expiry_date": 1}))

    def post(url, headers, body=None):
        assert headers["Authorization"] == "Bearer fresh-token"
        if url.endswith("loadCodeAssist"):
            return 200, {"currentTier": {"id": "standard-tier"}, "cloudaicompanionProject": "proj-1"}
        assert url.endswith("retrieveUserQuota")
        assert body == {"project": "proj-1"}
        return 200, {"buckets": [
            {"modelId": "gemini-3-pro", "remainingFraction": 0.9, "resetTime": "2026-09-02T00:00:00Z"},
            {"modelId": "gemini-3-pro", "tokenType": "TOKENS", "remainingFraction": 0.4, "resetTime": "2026-09-02T00:00:00Z"},
            {"modelId": "gemini-3-flash", "remainingFraction": 1.0, "resetTime": "2026-09-02T00:00:00Z"},
        ]}

    class RefreshingProvider(GeminiQuotaProvider):
        def _refreshed_token(self, refresh_token):
            return "fresh-token"

    snapshot = RefreshingProvider(home=home, post_json=post).refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))

    assert snapshot.plan == "Standard-Tier"
    assert snapshot.resources["gemini-3-pro"].used == 60
    assert snapshot.resources["gemini-3-pro"].resets_at == datetime(2026, 9, 2, tzinfo=timezone.utc)
    assert snapshot.resources["gemini-3-flash"].used == 0


def test_gemini_provider_uses_environment_project_and_skips_assist_failure(tmp_path):
    home = tmp_path / "home"
    credentials = home / ".config" / "gemini" / "oauth_creds.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text(json.dumps({"access_token": "token", "expiry_date": 9_999_999_999_999}))

    calls = []

    def post(url, headers, body=None):
        calls.append((url, body))
        if url.endswith("loadCodeAssist"):
            raise RuntimeError("network")
        assert url.endswith("retrieveUserQuota")
        return 200, {"buckets": [{"modelId": "gemini-3-pro", "remainingFraction": 0.5}]}

    snapshot = GeminiQuotaProvider(
        home=home, post_json=post,
        environment={"GOOGLE_CLOUD_PROJECT": "env-project"},
    ).refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))

    assert ("https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota", {"project": "env-project"}) in calls
    assert snapshot.plan is None
    assert snapshot.resources["gemini-3-pro"].used == 50


def test_gemini_provider_reports_rejected_login_and_invalid_responses(tmp_path):
    home = tmp_path / "home"
    credentials = home / ".gemini" / "oauth_creds.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text(json.dumps({"access_token": "token"}))

    def rejected(url, headers, body=None):
        return 401, {}

    provider = GeminiQuotaProvider(home=home, post_json=rejected)
    try:
        provider.refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))
        raise AssertionError("expected rejection")
    except RuntimeError as error:
        assert str(error) == "local login was rejected"

    def empty(url, headers, body=None):
        return 200, {}

    provider = GeminiQuotaProvider(home=home, post_json=empty)
    try:
        provider.refresh(datetime(2026, 9, 1, tzinfo=timezone.utc))
        raise AssertionError("expected invalid response")
    except RuntimeError as error:
        assert str(error) == "invalid response"


def test_service_keeps_last_good_snapshot_when_a_refresh_fails(tmp_path):
    class Provider:
        provider_id = "codex"
        display_name = "Codex"

        def __init__(self):
            self.should_fail = False

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            if self.should_fail:
                raise RuntimeError("provider rejected the local login")
            return QuotaSnapshot(
                provider_id=self.provider_id,
                display_name=self.display_name,
                fetched_at=now,
                resources={},
            )

    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    provider = Provider()
    service = QuotaService([provider], cache_path=tmp_path / "quotas.json", now=lambda: now)

    first = service.collect(force=True)
    provider.should_fail = True
    second = service.collect(force=True)

    assert "codex" in first["providers"]
    assert "codex" in second["providers"]
    assert second["providers"]["codex"]["fetchedAt"] == first["providers"]["codex"]["fetchedAt"]
    assert second["errors"] == [{"providerId": "codex", "message": "Could not refresh quota data."}]
    assert second["capabilities"]["codex"]["state"] == "refreshFailed"


def test_service_reports_not_signed_in_and_unsupported_harnesses(tmp_path):
    class SignedOutProvider:
        provider_id = "codex"
        display_name = "Codex"

        def has_local_credentials(self):
            return False

        def refresh(self, now):
            raise AssertionError("must not refresh without credentials")

    service = QuotaService([
        SignedOutProvider(),
        StaticQuotaProvider("pi", "Pi", "This harness has no vendor quota endpoint."),
    ], cache_path=tmp_path / "quotas.json")

    result = service.collect()

    assert result["capabilities"]["codex"] == {
        "displayName": "Codex", "state": "notSignedIn", "detail": "No local credentials found."
    }
    assert result["capabilities"]["pi"] == {
        "displayName": "Pi", "state": "notSupported", "detail": "This harness has no vendor quota endpoint."
    }


def test_service_marks_a_rejected_local_login_as_not_signed_in(tmp_path):
    class Provider:
        provider_id = "cursor"
        display_name = "Cursor"

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            raise RuntimeError("local login was rejected")

    result = QuotaService([Provider()], cache_path=tmp_path / "quotas.json").collect(force=True)

    assert result["capabilities"]["cursor"] == {
        "displayName": "Cursor", "state": "notSignedIn",
        "detail": "The saved login was rejected. Sign in with this agent again."
    }


def test_service_skips_a_fresh_provider_until_a_forced_refresh(tmp_path):
    class Provider:
        provider_id = "opencode"
        display_name = "OpenCode"

        def __init__(self):
            self.calls = 0

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            self.calls += 1
            return QuotaSnapshot(
                provider_id=self.provider_id,
                display_name=self.display_name,
                fetched_at=now,
                resources={},
            )

    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    provider = Provider()
    service = QuotaService([provider], cache_path=tmp_path / "quotas.json", now=lambda: now)

    service.collect()
    service.collect()
    service.collect(force=True)

    assert provider.calls == 2


def test_second_service_reloads_a_fresh_disk_cache_before_refreshing(tmp_path):
    class Provider:
        provider_id = "opencode"
        display_name = "OpenCode"

        def __init__(self, plan):
            self.calls = 0
            self.plan = plan

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            self.calls += 1
            return QuotaSnapshot(self.provider_id, self.display_name, now, {}, plan=self.plan)

    cache_path = tmp_path / "quotas.json"
    stale_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    current_at = stale_at + FRESHNESS + timedelta(seconds=1)
    stale_provider = Provider("stale")
    stale_service = QuotaService([stale_provider], cache_path=cache_path, now=lambda: stale_at)
    stale_service.collect(force=True)

    second_provider = Provider("second")
    second_service = QuotaService([second_provider], cache_path=cache_path, now=lambda: current_at)
    second_service._load()  # Simulate a menubar process that loaded the stale cache earlier.

    first_provider = Provider("first")
    first_service = QuotaService([first_provider], cache_path=cache_path, now=lambda: current_at)
    first_service.collect(force=True)

    result = second_service.collect()

    assert second_provider.calls == 0
    assert result["providers"]["opencode"]["plan"] == "first"


def test_load_discards_a_disk_cache_written_with_a_clock_ahead_of_now(tmp_path):
    class Provider:
        provider_id = "opencode"
        display_name = "OpenCode"

        def __init__(self):
            self.calls = 0

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            self.calls += 1
            return QuotaSnapshot(self.provider_id, self.display_name, now, {})

    cache_path = tmp_path / "quotas.json"
    # A skewed clock (dual-boot RTC offset, a resumed VM snapshot) wrote a
    # cache whose fetchedAt is months in the future.
    skewed_at = datetime(2027, 3, 1, tzinfo=timezone.utc)
    QuotaService([Provider()], cache_path=cache_path, now=lambda: skewed_at).collect(force=True)

    corrected_at = datetime(2026, 9, 10, tzinfo=timezone.utc)
    reader = Provider()
    service = QuotaService([reader], cache_path=cache_path, now=lambda: corrected_at)

    result = service.collect()

    assert reader.calls == 1
    assert result["providers"]["opencode"]["fetchedAt"] == "2026-09-10T00:00:00Z"
    assert result["providers"]["opencode"]["stale"] is False


def test_load_still_trusts_a_fetched_at_a_few_seconds_ahead_of_the_loading_clock(tmp_path):
    class Provider:
        provider_id = "opencode"
        display_name = "OpenCode"

        def __init__(self):
            self.calls = 0

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            self.calls += 1
            return QuotaSnapshot(self.provider_id, self.display_name, now, {})

    cache_path = tmp_path / "quotas.json"
    # Ordinary jitter between two processes' clocks, well inside
    # MAX_FUTURE_SKEW, must not be treated as a corrupted cache.
    written_at = datetime(2026, 9, 10, 12, 0, 5, tzinfo=timezone.utc)
    QuotaService([Provider()], cache_path=cache_path, now=lambda: written_at).collect(force=True)

    reader = Provider()
    reader_now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    service = QuotaService([reader], cache_path=cache_path, now=lambda: reader_now)

    service.collect()

    assert reader.calls == 0


# --- losing the cache lock -------------------------------------------------
# The interprocess lock guards refreshing and writing, not reading. A caller
# that loses it does neither, so it should serve the cache at once rather than
# block for the timeout and then read that same file anyway.

class _LockLoser:
    """A provider that fails the test if it is ever asked to refresh."""

    provider_id = "opencode"
    display_name = "OpenCode"

    def has_local_credentials(self):
        return True

    def refresh(self, now):
        raise AssertionError("must not refresh while another process holds the lock")


def _seed_cache(cache_path, at, plan="cached"):
    class Writer(_LockLoser):
        def refresh(self, now):
            return QuotaSnapshot(self.provider_id, self.display_name, now, {}, plan=plan)

    QuotaService([Writer()], cache_path=cache_path, now=lambda: at).collect(force=True)


def test_a_poll_that_loses_the_lock_serves_the_cache_without_waiting(tmp_path):
    cache_path = tmp_path / "quotas.json"
    written_at = datetime(2026, 9, 10, tzinfo=timezone.utc)
    _seed_cache(cache_path, written_at)

    # Stale enough that a poll would normally refresh; the held lock must stop it.
    later = written_at + FRESHNESS + timedelta(seconds=1)
    service = QuotaService([_LockLoser()], cache_path=cache_path, now=lambda: later)

    with _CacheFileLock(cache_path) as held:
        assert held
        started = time.monotonic()
        result = service.collect()
        elapsed = time.monotonic() - started

    assert elapsed < 1.0, "a poll must not queue behind another process's refresh"
    assert result["providers"]["opencode"]["plan"] == "cached"
    # Nothing is reported: the snapshot carries its own fetchedAt/stale, so the
    # caller can already see how old these numbers are.
    assert result["errors"] == []
    assert result["providers"]["opencode"]["stale"] is True


def test_losing_the_lock_with_no_cache_reports_an_error_rather_than_looking_empty(tmp_path):
    """Without this, the response is identical to "no agents configured"."""
    cache_path = tmp_path / "quotas.json"
    service = QuotaService([_LockLoser()], cache_path=cache_path,
                           now=lambda: datetime(2026, 9, 10, tzinfo=timezone.utc))

    with _CacheFileLock(cache_path) as held:
        assert held
        result = service.collect()

    assert result["providers"] == {}
    assert [error["providerId"] for error in result["errors"]] == ["quotaCache"]
    assert "no snapshot has been stored yet" in result["errors"][0]["message"]


def test_a_poll_waits_not_at_all_but_an_explicit_refresh_still_waits(tmp_path, monkeypatch):
    """Nobody is watching a background poll; someone is watching Refresh."""
    seen = []
    original = quotas_module._CacheFileLock

    class Spy(original):
        def __init__(self, path, timeout=CACHE_LOCK_TIMEOUT_SECONDS):
            seen.append(timeout)
            super().__init__(path, timeout=timeout)

    monkeypatch.setattr(quotas_module, "_CacheFileLock", Spy)
    service = QuotaService([], cache_path=tmp_path / "quotas.json")

    service.collect()
    service.collect(force=True)

    assert seen == [0, CACHE_LOCK_TIMEOUT_SECONDS]


def test_second_service_never_saves_an_older_in_memory_snapshot_over_newer_disk_cache(tmp_path):
    class Provider:
        provider_id = "codex"
        display_name = "Codex"

        def __init__(self, plan):
            self.calls = 0
            self.plan = plan

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            self.calls += 1
            return QuotaSnapshot(self.provider_id, self.display_name, now, {}, plan=self.plan)

    cache_path = tmp_path / "quotas.json"
    initial_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    updated_at = initial_at + timedelta(minutes=1)
    initial_provider = Provider("initial")
    QuotaService([initial_provider], cache_path=cache_path, now=lambda: initial_at).collect(force=True)

    older_provider = Provider("older-memory")
    older_service = QuotaService([older_provider], cache_path=cache_path, now=lambda: updated_at)
    older_service._load()  # Its cache remains fresh, but another process updates it first.

    writer_provider = Provider("newer-disk")
    QuotaService([writer_provider], cache_path=cache_path, now=lambda: updated_at).collect(force=True)

    result = older_service.collect()
    persisted = json.loads(cache_path.read_text(encoding="utf-8"))

    assert older_provider.calls == 0
    assert result["providers"]["codex"]["plan"] == "newer-disk"
    assert persisted["providers"]["codex"]["plan"] == "newer-disk"


def test_local_api_routes_share_the_quota_service(monkeypatch, tmp_path):
    import main

    class Provider:
        provider_id = "codex"
        display_name = "Codex"

        def has_local_credentials(self):
            return True

        def refresh(self, now):
            return QuotaSnapshot(self.provider_id, self.display_name, now, {})

    service = QuotaService([Provider()], cache_path=tmp_path / "quotas.json")
    monkeypatch.setattr(main, "_quota_service", service)

    # asyncio.run intentionally clears the policy's default event loop. Restore
    # the test runner's loop so older endpoint tests that use get_event_loop()
    # remain independent of this focused route test.
    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        # A prior legacy test may already have cleared the policy loop. The
        # route test must remain independent of that pre-existing state.
        previous_loop = None
    try:
        result = asyncio.run(main.get_quotas())
        refreshed = asyncio.run(main.refresh_quotas())
    finally:
        if previous_loop is not None:
            asyncio.set_event_loop(previous_loop)

    assert result["schema"] == "tokentelemetry.quotas.v1"
    assert result["providers"]["codex"]["displayName"] == "Codex"
    assert refreshed["providers"]["codex"]["stale"] is False


# --- credential sources and account states -----------------------------------

def test_claude_provider_falls_back_to_the_macos_keychain_session(tmp_path):
    """macOS keeps the OAuth blob in Keychain and writes no credentials file.

    Reading only the file reported a signed-in user as signed out, which is what
    kept Claude Code off the dashboard entirely.
    """
    secret = json.dumps({"claudeAiOauth": {
        "accessToken": "kc-token", "subscriptionType": "pro", "rateLimitTier": "default_claude_20x",
    }})

    def fetch(url, headers):
        assert headers["Authorization"] == "Bearer kc-token"
        return 200, {
            "five_hour": {"utilization": 20.0, "resets_at": "2026-08-31T08:00:00Z"},
            "seven_day": {"utilization": 83.0, "resets_at": "2026-09-03T04:00:00Z"},
        }

    provider = ClaudeQuotaProvider(
        home=tmp_path / "no-such-home", fetch_json=fetch, environment={},
        read_keychain=lambda service: secret if service == "Claude Code-credentials" else None,
    )

    assert provider.has_local_credentials() is True
    snapshot = provider.refresh(datetime(2026, 8, 31, tzinfo=timezone.utc))
    assert snapshot.plan == "Pro 20x"
    assert snapshot.resources["session"].used == 20.0
    assert snapshot.resources["weekly"].used == 83.0


def test_claude_provider_prefers_the_credentials_file_over_the_keychain(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "file-token", "subscriptionType": "max"}}))

    def fetch(url, headers):
        assert headers["Authorization"] == "Bearer file-token"
        return 200, {"five_hour": {"utilization": 5.0}}

    def keychain(service):
        raise AssertionError("keychain must not be read when the file has a session")

    snapshot = ClaudeQuotaProvider(
        home=home, fetch_json=fetch, environment={}, read_keychain=keychain,
    ).refresh(datetime(2026, 8, 31, tzinfo=timezone.utc))

    assert snapshot.plan == "Max"


def test_cursor_provider_reports_an_expired_session_without_a_request(tmp_path):
    """The state DB keeps the last token after it lapses; its own exp says so."""
    import base64
    import sqlite3

    def jwt(exp):
        payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
        return f"header.{payload}.signature"

    home = tmp_path / "home"
    db = home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    db.parent.mkdir(parents=True)
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    connection.execute("INSERT INTO ItemTable VALUES (?, ?)",
                       ("cursorAuth/accessToken", jwt(1_750_000_000)))
    connection.commit()
    connection.close()

    def post(url, headers):
        raise AssertionError("a token known to be expired must not be sent")

    provider = CursorQuotaProvider(home=home, post_json=post)
    assert provider.has_local_credentials() is True
    try:
        provider.refresh(datetime(2026, 8, 31, tzinfo=timezone.utc))
        raise AssertionError("expected an expired session")
    except RuntimeError as error:
        assert str(error) == "session expired"


def test_grok_provider_refreshes_a_lapsed_token_without_rewriting_the_auth_file(tmp_path):
    home = tmp_path / "home"
    auth = home / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    original = json.dumps({"https://auth.x.ai::account": {
        "key": "stale-token", "refresh_token": "refresh-token",
        "oidc_client_id": "client-1", "expires_at": "2026-08-28T17:29:45Z",
    }})
    auth.write_text(original)

    def post_form(url, body):
        assert url == "https://auth.x.ai/oauth2/token"
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "refresh-token"
        assert body["client_id"] == "client-1"
        return 200, {"access_token": "fresh-token"}

    def fetch(url, headers):
        assert headers["Authorization"] == "Bearer fresh-token"
        if url.endswith("/settings"):
            return 200, {"subscription_tier_display": "SuperGrok"}
        return 200, {"config": {"creditUsagePercent": 2.0, "currentPeriod": {
            "type": "USAGE_PERIOD_TYPE_WEEKLY",
            "start": "2026-08-28T15:52:37Z", "end": "2026-09-04T15:52:37Z",
        }}}

    snapshot = GrokQuotaProvider(home=home, fetch_json=fetch, post_form=post_form).refresh(
        datetime(2026, 8, 31, tzinfo=timezone.utc))

    assert snapshot.plan == "SuperGrok"
    assert snapshot.resources["weekly"].used == 2.0
    assert auth.read_text() == original, "another agent's session file must not be rewritten"


def test_grok_provider_reports_an_expired_session_when_the_refresh_fails(tmp_path):
    home = tmp_path / "home"
    auth = home / ".grok" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"account": {
        "key": "stale-token", "refresh_token": "refresh-token",
        "oidc_client_id": "client-1", "expires_at": "2026-08-28T17:29:45Z",
    }}))

    provider = GrokQuotaProvider(
        home=home,
        fetch_json=lambda url, headers: (401, {"error": "Invalid or expired credentials"}),
        post_form=lambda url, body: (400, {"error": "invalid_grant"}),
    )
    try:
        provider.refresh(datetime(2026, 8, 31, tzinfo=timezone.utc))
        raise AssertionError("expected an expired session")
    except RuntimeError as error:
        assert str(error) == "session expired"


def test_gemini_provider_separates_a_missing_licence_from_a_dead_token(tmp_path):
    """Google answers both with 403; only one of them is the user's to fix."""
    home = tmp_path / "home"
    credentials = home / ".gemini" / "oauth_creds.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text(json.dumps({"access_token": "token", "expiry_date": 9_999_999_999_999}))

    def unlicensed(url, headers, body=None):
        return 403, {"error": {
            "code": 403, "status": "PERMISSION_DENIED",
            "message": "You do not have a valid license of this product.",
            "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                         "reason": "SUBSCRIPTION_REQUIRED"}],
        }}

    try:
        GeminiQuotaProvider(home=home, post_json=unlicensed).refresh(
            datetime(2026, 8, 31, tzinfo=timezone.utc))
        raise AssertionError("expected a missing entitlement")
    except RuntimeError as error:
        assert str(error) == "not entitled"


def test_service_reports_expiry_and_entitlement_without_raising_a_refresh_error(tmp_path):
    """Account states are facts, not faults, so they raise no error row.

    The dashboard's amber "could not refresh" line should mean a fetch actually
    failed, otherwise a merely signed-out agent makes the page look broken.
    """
    def provider(provider_id, reason, **attributes):
        namespace = {
            "provider_id": provider_id, "display_name": provider_id.title(),
            "has_local_credentials": lambda self: True,
            "refresh": lambda self, now: (_ for _ in ()).throw(RuntimeError(reason)),
            **attributes,
        }
        return type(f"{provider_id}Provider", (), namespace)()

    service = QuotaService([
        provider("cursor", "session expired", sign_in_hint="Sign in to Cursor again."),
        provider("gemini", "not entitled", entitlement_hint="No Code Assist licence."),
        provider("opencode", "usage request failed"),
    ], cache_path=tmp_path / "quotas.json")

    result = service.collect(force=True)

    assert result["capabilities"]["cursor"]["state"] == "sessionExpired"
    assert result["capabilities"]["cursor"]["detail"] == "Sign in to Cursor again."
    assert result["capabilities"]["gemini"]["state"] == "notEntitled"
    assert result["capabilities"]["gemini"]["detail"] == "No Code Assist licence."
    assert result["capabilities"]["opencode"]["state"] == "refreshFailed"
    assert [error["providerId"] for error in result["errors"]] == ["opencode"]


def test_every_supported_agent_has_a_quota_entry():
    """A new harness must not silently vanish from the quota page."""
    import re

    import main

    roster = set(re.findall(
        r"^  (\w+):\s*\{ key:",
        (Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "agents.ts").read_text(),
        re.M,
    ))
    reported = {provider.provider_id for provider in main._get_quota_service().providers}

    assert roster, "agent roster could not be read"
    assert roster - reported == set(), f"agents with no quota entry: {sorted(roster - reported)}"
    assert reported - roster == set(), f"quota entries for unknown agents: {sorted(reported - roster)}"


def _antigravity_home(tmp_path: Path, surface: str = "antigravity-ide") -> Path:
    """A home that looks like Antigravity is installed."""
    home = tmp_path / "home"
    (home / ".gemini" / surface).mkdir(parents=True)
    return home


# One Gemini pool and one third-party pool, each with a five-hour and a weekly
# window. Values are invented: the real response carries the signed-in user's
# own numbers, and GetUserStatus carries their name and email besides.
ANTIGRAVITY_SUMMARY = {
    "response": {
        "groups": [
            {
                "displayName": "Gemini Models",
                "buckets": [
                    {"bucketId": "gemini-weekly", "window": "weekly",
                     "remainingFraction": 0.75, "resetTime": "2026-09-20T17:13:10Z"},
                    {"bucketId": "gemini-5h", "window": "5h",
                     "remainingFraction": 0.5, "resetTime": "2026-09-15T14:29:33Z"},
                ],
            },
            {
                "displayName": "Claude and GPT models",
                "buckets": [
                    {"bucketId": "3p-weekly", "window": "weekly",
                     "remainingFraction": 1, "resetTime": "2026-09-22T14:21:11Z"},
                    {"bucketId": "3p-5h", "window": "5h",
                     "remainingFraction": 0.9, "resetTime": "2026-09-15T19:21:11Z"},
                ],
            },
        ],
    },
}


def _antigravity_stub(summary=None, user_status=None, expect_csrf="live-token"):
    """A post_json double that answers the two language-server calls."""
    calls: list[tuple[int, str, str]] = []

    def post_json(port, path, headers, body):
        calls.append((port, path, headers.get("x-codeium-csrf-token", "")))
        if headers.get("x-codeium-csrf-token") != expect_csrf:
            return 401, {"code": "unauthenticated", "message": "missing CSRF token"}
        if path.endswith("/RetrieveUserQuotaSummary"):
            return 200, summary if summary is not None else ANTIGRAVITY_SUMMARY
        if path.endswith("/GetUserStatus"):
            if user_status is None:
                return 500, {}
            return 200, user_status
        return 404, {}

    return post_json, calls


def test_antigravity_converts_remaining_fraction_into_consumed_percent(tmp_path):
    """The payload reports what is LEFT; every quota surface shows what is SPENT.

    An inversion here is invisible by inspection — a barely-touched week simply
    renders as nearly exhausted — so the conversion is pinned per bucket.
    """
    post_json, _ = _antigravity_stub(user_status={
        "userStatus": {"planStatus": {"planInfo": {"planName": "Pro"}}},
    })
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: [
            "/Applications/Antigravity.app/Contents/Resources/bin/language_server "
            "--https_server_port 51096 --csrf_token live-token --app_data_dir antigravity-ide",
        ],
        post_json=post_json,
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)

    snapshot = provider.refresh(now)

    assert snapshot.plan == "Pro"
    assert set(snapshot.resources) == {"session", "weekly", "claude", "claudeWeekly"}
    assert snapshot.resources["session"].used == 50.0
    assert snapshot.resources["weekly"].used == 25.0
    assert snapshot.resources["claude"].used == pytest.approx(10.0)
    assert snapshot.resources["claudeWeekly"].used == 0.0
    assert all(r.limit == 100 for r in snapshot.resources.values())
    # The payload names its window but never states a length.
    assert snapshot.resources["session"].window_seconds == 5 * 3600
    assert snapshot.resources["weekly"].window_seconds == 7 * 24 * 3600
    assert snapshot.resources["weekly"].resets_at == datetime(
        2026, 9, 20, 17, 13, 10, tzinfo=timezone.utc,
    )


def test_antigravity_picks_the_serving_process_and_the_servers_own_token(tmp_path):
    """Only a surface with a real --https_server_port has an HTTPS listener.

    The 2.0 hub and a bare `agy` both launch with `--https_server_port 0`, and
    every line also carries --extension_server_csrf_token, which this port
    rejects. Picking either wrong value yields a 401 that reads like a broken
    login rather than a parsing bug.
    """
    post_json, calls = _antigravity_stub(user_status=None)
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: [
            "/Applications/Antigravity.app/Contents/Resources/bin/language_server "
            "--standalone --https_server_port 0 --csrf_token hub-token",
            "language_server_macos_arm --enable_lsp --csrf_token live-token "
            "--extension_server_port 51095 --extension_server_csrf_token decoy-token "
            "--https_server_port 51096 --lsp_port 51110",
        ],
        post_json=post_json,
    )

    snapshot = provider.refresh(datetime(2026, 9, 15, tzinfo=timezone.utc))

    assert {port for port, _, _ in calls} == {51096}
    assert {csrf for _, _, csrf in calls} == {"live-token"}
    # GetUserStatus answered 500; a plan label is a nicety, the numbers are not.
    assert snapshot.plan is None
    assert snapshot.resources["session"].used == 50.0


def test_antigravity_skips_pools_it_does_not_recognise(tmp_path):
    """A new bucket id must not be drawn as one of the four known meters."""
    post_json, _ = _antigravity_stub(summary={"response": {"groups": [{
        "displayName": "Gemini Models",
        "buckets": [
            {"bucketId": "gemini-5h", "window": "5h", "remainingFraction": 0.25},
            {"bucketId": "imagen-daily", "window": "daily", "remainingFraction": 0.1},
        ],
    }]}})
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: ["language_server --https_server_port 51096 --csrf_token live-token"],
        post_json=post_json,
    )

    snapshot = provider.refresh(datetime(2026, 9, 15, tzinfo=timezone.utc))

    assert set(snapshot.resources) == {"session"}
    assert snapshot.resources["session"].used == 75.0


@pytest.mark.parametrize("fraction", [5, -1, float("nan"), float("inf"), "x", None])
def test_antigravity_refuses_an_impossible_fraction(tmp_path, fraction):
    """An out-of-range or non-finite fraction must not be clamped into a number.

    Clamping is what makes this dangerous: a fraction of 5 would render as a
    confident "0% used" and -1 as "100% used", with nothing on screen to say
    the value was nonsense. A missing meter is visible; a wrong one is not.
    """
    post_json, _ = _antigravity_stub(summary={"response": {"groups": [{
        "buckets": [{"bucketId": "gemini-5h", "window": "5h", "remainingFraction": fraction}],
    }]}})
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: ["/opt/ag/language_server --https_server_port 51096 --csrf_token live-token"],
        post_json=post_json,
    )
    with pytest.raises(RuntimeError) as caught:
        provider.refresh(datetime(2026, 9, 15, tzinfo=timezone.utc))
    # Buckets arrived and none parsed: the schema moved, which is a fault.
    assert str(caught.value) == "invalid response"


def test_antigravity_unrecognised_pools_are_not_a_fault(tmp_path):
    """Well-formed buckets we simply don't map is an account fact, not a fault."""
    post_json, _ = _antigravity_stub(summary={"response": {"groups": [{
        "buckets": [{"bucketId": "imagen-daily", "window": "daily", "remainingFraction": 0.4}],
    }]}})
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: ["/opt/ag/language_server --https_server_port 51096 --csrf_token live-token"],
        post_json=post_json,
    )
    with pytest.raises(RuntimeError) as caught:
        provider.refresh(datetime(2026, 9, 15, tzinfo=timezone.utc))
    assert str(caught.value) != "invalid response"


def test_antigravity_ignores_a_process_that_merely_mentions_a_language_server(tmp_path):
    """Only the executable decides, never text quoted in someone's arguments.

    A shell or test runner echoing one of these command lines would otherwise
    be treated as a server, and its port used to address an unrelated local
    listener.
    """
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: [
            "/bin/zsh -lc echo 'language_server --https_server_port 9999 --csrf_token stolen'",
            "/usr/bin/grep language_server --https_server_port 8888 --csrf_token stolen",
        ],
        post_json=lambda *args: (_ for _ in ()).throw(AssertionError("must not be called")),
    )
    assert provider._servers() == []
    with pytest.raises(RuntimeError) as caught:
        provider.refresh(datetime(2026, 9, 15, tzinfo=timezone.utc))
    assert str(caught.value) == AGENT_NOT_RUNNING


def test_antigravity_reads_an_install_path_containing_spaces(tmp_path):
    """The real macOS path is unquoted and has a space in it.

    `ps` prints "/Applications/Antigravity IDE.app/.../language_server_macos_arm"
    with no quoting, so treating the first space as the end of the executable
    finds "/Applications/Antigravity" and rejects the one real server.
    """
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: [
            "/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/"
            "antigravity/bin/language_server_macos_arm --enable_lsp --csrf_token live-token "
            "--extension_server_csrf_token decoy-token --https_server_port 51096 --lsp_port 51110",
        ],
        post_json=lambda *args: (0, {}),
    )
    assert provider._servers() == [(51096, "live-token")]


def test_antigravity_reads_a_quoted_windows_command_line(tmp_path):
    """Windows paths carry spaces, so the executable arrives quoted."""
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: [
            '"C:\\Program Files\\Antigravity\\language_server_windows_x64.exe" '
            '--https_server_port 51096 --csrf_token "live-token"',
        ],
        post_json=lambda *args: (0, {}),
    )
    assert provider._servers() == [(51096, "live-token")]


def test_antigravity_closed_reports_not_running_rather_than_signed_out(tmp_path):
    """Installed but shut is not a login problem, and must not read as one.

    has_local_credentials stays True so the collector calls refresh at all;
    refresh then fails with the reason that is actually true. Reporting
    "no local credentials found" would send the user to fix a working login.
    """
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path, "antigravity-cli"),
        command_lines=lambda: ["/usr/bin/some-other-process --flag"],
        post_json=lambda *args: (_ for _ in ()).throw(AssertionError("must not call")),
    )
    assert provider.has_local_credentials() is True

    service = QuotaService([provider], cache_path=tmp_path / "quotas.json")
    capability = service.collect(force=True)["capabilities"]["antigravity"]

    assert capability["state"] == "notRunning"
    assert "Open Antigravity" in capability["detail"]
    # Not a fault, so it must not raise the dashboard's error banner.
    assert service.collect(force=True)["errors"] == []


def test_antigravity_not_installed_has_no_credentials(tmp_path):
    provider = AntigravityQuotaProvider(
        home=tmp_path / "empty",
        command_lines=lambda: [],
        post_json=lambda *args: (0, {}),
    )
    assert provider.has_local_credentials() is False


def test_antigravity_rejected_token_is_reported_as_a_login_problem(tmp_path):
    post_json, _ = _antigravity_stub(expect_csrf="a-different-token")
    provider = AntigravityQuotaProvider(
        home=_antigravity_home(tmp_path),
        command_lines=lambda: ["language_server --https_server_port 51096 --csrf_token stale-token"],
        post_json=post_json,
    )
    with pytest.raises(RuntimeError) as caught:
        provider.refresh(datetime(2026, 9, 15, tzinfo=timezone.utc))
    assert str(caught.value) != AGENT_NOT_RUNNING


def test_default_quota_providers_roster_is_exact_and_stable():
    """The factory is the single source of truth for the /quotas roster.

    Pinning the ordered ids, the native provider classes, and the static
    entries' display text catches a reorder, an accidental drop, or a rewritten
    detail here rather than as silent drift in the running service.
    """
    providers = default_quota_providers()

    assert [p.provider_id for p in providers] == [
        "codex", "claude", "cursor", "opencode", "copilot", "grok", "gemini",
        "antigravity", "qwen", "vibe", "hermes", "cline", "pi", "smallcode",
        "muse", "prime", "dsh", "qoder", "openai_compat",
    ]

    native = [p for p in providers if not isinstance(p, StaticQuotaProvider)]
    assert [type(p) for p in native] == [
        CodexQuotaProvider, ClaudeQuotaProvider, CursorQuotaProvider,
        OpenCodeQuotaProvider, CopilotQuotaProvider, GrokQuotaProvider,
        GeminiQuotaProvider, AntigravityQuotaProvider,
    ]

    statics = {p.provider_id: p for p in providers if isinstance(p, StaticQuotaProvider)}
    assert set(statics) == {
        "qwen", "vibe", "hermes", "cline", "pi", "smallcode",
        "muse", "prime", "dsh", "qoder", "openai_compat",
    }
    assert statics["qwen"].display_name == "Qwen CLI"
    assert statics["dsh"].display_name == "DeepSeek Harness"
    assert statics["muse"].display_name == "Muse Code"
    assert statics["openai_compat"].display_name == "OpenAI-compatible server"
    assert [p.capability()["state"] for p in statics.values()] == ["notSupported"] * len(statics)


def test_claude_panel_and_dashboard_report_the_same_windows(tmp_path, monkeypatch):
    """One app must not show two different numbers for the same week.

    The panel's own source, ~/.claude.json, is only rewritten when the CLI next
    calls the API, so it lagged the live provider reading by days.
    """
    import harness_panels.base as base
    import harness_panels.claude as panel

    cache = tmp_path / "quotas.json"
    cache.write_text(json.dumps({"providers": {"claude": {
        "plan": "Pro",
        "resources": {
            "session": {"used": 27.0, "limit": 100, "resetsAt": "2026-08-31T07:59:59Z"},
            "weekly": {"used": 84.0, "limit": 100, "resetsAt": "2026-09-03T03:59:59Z"},
        },
    }}}))
    monkeypatch.setattr(base, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(panel, "CLAUDE_JSON", tmp_path / "stale.json")
    (tmp_path / "stale.json").write_text(json.dumps({"cachedUsageUtilization": {
        "utilization": {"five_hour": {"utilization": 34}, "seven_day": {"utilization": 30}},
    }}))

    section = panel._quota()

    assert [m["pct"] for m in section["meters"]] == [27.0, 84.0], "the stale file must not win"
    assert "live" in section["source"]


def test_claude_panel_falls_back_to_its_cached_file_without_a_live_reading(tmp_path, monkeypatch):
    import harness_panels.base as base
    import harness_panels.claude as panel

    monkeypatch.setattr(base, "data_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(panel, "CLAUDE_JSON", tmp_path / "claude.json")
    (tmp_path / "claude.json").write_text(json.dumps({"cachedUsageUtilization": {
        "fetchedAtMs": 1_787_544_557_030,
        "utilization": {"five_hour": {"utilization": 34}, "seven_day": {"utilization": 30}},
    }}))

    section = panel._quota()

    assert [m["pct"] for m in section["meters"]] == [34.0, 30.0]
    assert "claude.json" in section["source"]


def test_quota_meters_colour_at_the_same_marks_as_the_dashboard():
    """Panel and dashboard show the same windows, so they must colour alike.

    `meter()`'s generic default warns at 70; the quota cards warn at 75, which
    is where the providers' own usage screens change colour.
    """
    from harness_panels.base import quota_severity

    assert [quota_severity(p) for p in (0, 74.9)] == ["ok", "ok"]
    assert [quota_severity(p) for p in (75, 89.9)] == ["warn", "warn"]
    assert [quota_severity(p) for p in (90, 100)] == ["crit", "crit"]


def test_every_native_provider_panel_surfaces_its_live_quota(tmp_path, monkeypatch):
    """Each agent's own page shows its own limits, from the shared snapshot.

    Quota used to live only on the dashboard while everything else
    agent-specific lived on the agent page. Reading one cache keeps the page,
    the tile and the sidebar gauge from disagreeing about the same window.
    """
    import harness_panels.base as base

    (tmp_path / "quotas.json").write_text(json.dumps({"providers": {
        provider: {"plan": "Test", "resources": {
            "weekly": {"used": 42.0, "limit": 100, "resetsAt": "2026-09-03T00:00:00Z"},
        }}
        for provider in ("claude", "codex", "copilot", "grok", "opencode")
    }}))
    monkeypatch.setattr(base, "data_dir", lambda: tmp_path)

    for provider in ("claude", "codex", "copilot", "grok", "opencode"):
        section = base.live_quota(provider)
        assert section is not None, f"{provider} panel has no quota section"
        assert [m["pct"] for m in section["meters"]] == [42.0]
        assert section["meters"][0]["severity"] == "ok"


def test_live_quota_ignores_a_balance_with_no_ceiling(tmp_path, monkeypatch):
    """A bar needs a maximum; credits and spend have none, so they are skipped."""
    import harness_panels.base as base

    (tmp_path / "quotas.json").write_text(json.dumps({"providers": {"codex": {"resources": {
        "credits": {"kind": "balance", "unit": "credits", "available": 0.0},
        "rateLimitResets": {"kind": "balance", "unit": "resets", "available": 1.0},
    }}}}))
    monkeypatch.setattr(base, "data_dir", lambda: tmp_path)

    assert base.live_quota("codex") is None
