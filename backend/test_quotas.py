"""Tests for native provider quota collection and stale-while-revalidate cache."""

from __future__ import annotations

import json
import sys
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from quotas import (
    ClaudeQuotaProvider,
    CodexQuotaProvider,
    CopilotQuotaProvider,
    CursorQuotaProvider,
    GeminiQuotaProvider,
    GrokQuotaProvider,
    OpenCodeQuotaProvider,
    QuotaService,
    QuotaSnapshot,
    StaticQuotaProvider,
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
