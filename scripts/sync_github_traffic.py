#!/usr/bin/env python3
"""Sync GitHub traffic (views, clones, referrers, popular paths) into Google Sheets.

Env vars:
  GCP_CREDENTIALS  JSON string of the service-account key (full contents).
  GH_PAT           GitHub PAT with `repo` (or admin:repo) scope for the target repos.
  TT_SHEET_ID      ID of the target Google Spreadsheet (shared Editor with the service account).

The target spreadsheet must already exist and be shared (Editor) with the
service account email. Per-repo tabs expected:
  <base>            daily views + clones timeline
  <base>_Referrers  14-day referrer snapshots
  <base>_Paths      14-day popular-path snapshots
"""

import json
import os
from datetime import datetime

import gspread
import requests
from google.oauth2.service_account import Credentials

REPOS_TO_TRACK = {
    "VasiHemanth/tokentelemetry": "TokenTelemetry",
    "VasiHemanth/tokentelemetry-hermes-plugin": "Hermes-Plugin",
}


def gh_get(url, headers):
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def ensure_tab(spreadsheet, title, header):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(8, len(header)))
        ws.append_row(header)
        return ws
    # Backfill a header row if the sheet is empty.
    if not ws.row_values(1):
        ws.update("A1", [header])
    return ws


def main():
    for var in ("GCP_CREDENTIALS", "GH_PAT", "TT_SHEET_ID"):
        if not os.environ.get(var):
            print(f"Skipping: {var} not set.")
            return

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_json = json.loads(os.environ["GCP_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(os.environ["TT_SHEET_ID"])

    gh_token = os.environ["GH_PAT"]
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {gh_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    today_snapshot = datetime.utcnow().strftime("%Y-%m-%d")

    for repo_path, base_tab in REPOS_TO_TRACK.items():
        print(f"Fetching traffic for {repo_path}...")

        # --- Views & Clones (time-series) ---
        views = gh_get(
            f"https://api.github.com/repos/{repo_path}/traffic/views", headers
        ).get("views", [])
        clones = gh_get(
            f"https://api.github.com/repos/{repo_path}/traffic/clones", headers
        ).get("clones", [])

        daily = {}
        for v in views:
            d = v["timestamp"][:10]
            daily.setdefault(d, {"views": 0, "u_views": 0, "clones": 0, "u_clones": 0})
            daily[d]["views"] = v["count"]
            daily[d]["u_views"] = v["uniques"]
        for c in clones:
            d = c["timestamp"][:10]
            daily.setdefault(d, {"views": 0, "u_views": 0, "clones": 0, "u_clones": 0})
            daily[d]["clones"] = c["count"]
            daily[d]["u_clones"] = c["uniques"]

        main_sheet = ensure_tab(
            spreadsheet, base_tab, ["date", "views", "unique_views", "clones", "unique_clones"]
        )
        existing_dates = set(main_sheet.col_values(1))
        new_rows = [
            [d, m["views"], m["u_views"], m["clones"], m["u_clones"]]
            for d, m in sorted(daily.items())
            if d not in existing_dates
        ]
        if new_rows:
            main_sheet.append_rows(new_rows, value_input_option="USER_ENTERED")
            print(f"  + {len(new_rows)} daily rows -> {base_tab}")
        else:
            print(f"  = no new daily rows for {base_tab}")

        # --- Referrers (14-day snapshot) ---
        referrers = gh_get(
            f"https://api.github.com/repos/{repo_path}/traffic/popular/referrers", headers
        )
        ref_sheet = ensure_tab(
            spreadsheet,
            f"{base_tab}_Referrers",
            ["snapshot_date", "referrer", "views", "uniques"],
        )
        if referrers:
            ref_sheet.append_rows(
                [
                    [today_snapshot, r["referrer"], r["count"], r["uniques"]]
                    for r in referrers
                ],
                value_input_option="USER_ENTERED",
            )
            print(f"  + {len(referrers)} referrer rows -> {base_tab}_Referrers")

        # --- Popular paths (14-day snapshot) ---
        paths = gh_get(
            f"https://api.github.com/repos/{repo_path}/traffic/popular/paths", headers
        )
        path_sheet = ensure_tab(
            spreadsheet,
            f"{base_tab}_Paths",
            ["snapshot_date", "title", "path", "views", "uniques"],
        )
        if paths:
            path_sheet.append_rows(
                [
                    [today_snapshot, p["title"], p["path"], p["count"], p["uniques"]]
                    for p in paths
                ],
                value_input_option="USER_ENTERED",
            )
            print(f"  + {len(paths)} path rows -> {base_tab}_Paths")

    print("Total traffic sync complete!")


if __name__ == "__main__":
    main()
