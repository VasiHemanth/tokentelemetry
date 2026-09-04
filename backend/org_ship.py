"""Org mode shipping agent: push this machine's session rollups to a collector.

Runs on each teammate's machine, reads sessions from the LOCAL TokenTelemetry
backend, and POSTs metrics-only rollups (id, agent, project, timestamp, token
counts) to the team's self-hosted collector at /org/ingest. Prompt content
never leaves the machine, and the only outbound call is to the collector URL
you configure. Model and cost are shipped as null in this MVP.

Designed for cron/launchd scheduling: it is a one-shot run, idempotent on the
collector side (re-sending the same sessions upserts, never double-counts),
prints a single summary line on success, and exits non-zero with a plain
message when the local backend or the collector is unreachable.

Usage:
    python backend/org_ship.py --central-url https://tt.example.com --token <hex>
        [--source-url http://127.0.0.1:8000] [--batch-size 200]

TT_CENTRAL_URL and TT_MACHINE_TOKEN work as env fallbacks for --central-url
and --token, keeping the token out of the crontab line if preferred.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _fetch_local_sessions(source_url: str) -> list:
    url = source_url.rstrip("/") + "/sessions"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        sys.exit(f"Could not read sessions from the local backend at {url}. "
                 f"Is TokenTelemetry running? ({e})")
    if not isinstance(data, list):
        sys.exit(f"Unexpected response from {url}: expected a session list.")
    return data


def _to_rollup(session: dict) -> dict:
    tokens = session.get("tokens") or {}
    return {
        "id": str(session.get("id", "")),
        "agent": str(session.get("agent", "")),
        "project": str(session.get("project", "")),
        "timestamp": str(session.get("timestamp", "")),
        "tokens": {
            "input": int(tokens.get("input") or 0),
            "output": int(tokens.get("output") or 0),
            "cached": int(tokens.get("cached") or 0),
            "total": int(tokens.get("total") or 0),
        },
        "model": None,
        "cost": None,
    }


def _post_batch(central_url: str, token: str, batch: list) -> dict:
    url = central_url.rstrip("/") + "/org/ingest"
    req = urllib.request.Request(
        url,
        data=json.dumps({"sessions": batch}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-TT-Machine-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("The collector rejected the machine token (401). "
                     "Check the token against the collector's org.json.")
        sys.exit(f"The collector at {url} returned HTTP {e.code}.")
    except (urllib.error.URLError, OSError, ValueError) as e:
        sys.exit(f"Could not reach the collector at {url}. ({e})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ship this machine's session rollups to an org-mode collector."
    )
    parser.add_argument("--central-url", default=os.environ.get("TT_CENTRAL_URL", ""),
                        help="Collector base URL (env: TT_CENTRAL_URL)")
    parser.add_argument("--token", default=os.environ.get("TT_MACHINE_TOKEN", ""),
                        help="This machine's token from the collector's org.json (env: TT_MACHINE_TOKEN)")
    parser.add_argument("--source-url", default="http://127.0.0.1:8000",
                        help="Local TokenTelemetry backend to read sessions from")
    parser.add_argument("--batch-size", type=int, default=200,
                        help="Sessions per POST to /org/ingest")
    args = parser.parse_args()

    if not args.central_url.strip():
        sys.exit("A collector URL is required (--central-url or TT_CENTRAL_URL).")
    if not args.token.strip():
        sys.exit("A machine token is required (--token or TT_MACHINE_TOKEN).")
    if args.batch_size < 1:
        sys.exit("--batch-size must be at least 1.")

    rollups = [_to_rollup(s) for s in _fetch_local_sessions(args.source_url)]
    accepted = updated = 0
    for i in range(0, len(rollups), args.batch_size):
        result = _post_batch(args.central_url.strip(), args.token.strip(),
                             rollups[i:i + args.batch_size])
        accepted += int(result.get("accepted") or 0)
        updated += int(result.get("updated") or 0)
    print(f"Shipped {len(rollups)} sessions: {accepted} accepted, {updated} updated.")


if __name__ == "__main__":
    main()
