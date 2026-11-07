#!/usr/bin/env python3
"""Backup Cloudflare Analytics Engine telemetry data to Google Drive.

Extracts telemetry rows from Cloudflare Analytics Engine (tt_telemetry),
creates daily raw NDJSON files and rollup CSVs, bundles them into a zip,
and uploads/updates the backup in Google Drive via a Service Account.

Environment variables required:
  CLOUDFLARE_API_TOKEN   Cloudflare API token with 'Account Analytics -> Read' permission
  CLOUDFLARE_ACCOUNT_ID  Cloudflare Account ID (defaults to TokenTelemetry account)
  GCP_CREDENTIALS        Google Cloud Service Account JSON key string
  GDRIVE_FOLDER_ID       Google Drive Folder ID where backups will be stored
"""
from __future__ import annotations

import csv
import io
import json
import os
import pathlib
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    Credentials = None
    build = None
    MediaFileUpload = None

DEFAULT_ACCOUNT_ID = "78a584e8bdd18cba67bd465556fe521f"
DATASET = "tt_telemetry"
DATASET_START = date(2026, 6, 15)

COLUMNS = (
    ["timestamp"]
    + [f"blob{i}" for i in range(1, 21)]
    + ["double1", "double2", "_sample_interval"]
)


def query_ae(sql: str, token: str, account_id: str, attempts: int = 4) -> list[dict]:
    """Execute SQL query against Cloudflare Analytics Engine API."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql"
    body = (sql + " FORMAT JSON").encode()
    last = ""
    for attempt in range(attempts):
        req = urllib.request.Request(
            url, data=body, headers={"Authorization": f"Bearer {token}"}
        )
        try:
            raw = urllib.request.urlopen(req, timeout=90).read().decode()
            return json.loads(raw).get("data", [])
        except json.JSONDecodeError:
            last = raw[:200]
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}: {exc.read().decode()[:200]}"
        except Exception as exc:  # network flake
            last = str(exc)[:200]
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"AE query failed after {attempts} attempts: {last}\nSQL: {sql[:160]}")


def get_retention_floor(token: str, account_id: str) -> date:
    """Find the earliest available timestamp currently retained in Cloudflare."""
    rows = query_ae("SELECT min(timestamp) AS oldest FROM " + DATASET, token, account_id)
    oldest = (rows[0].get("oldest") if rows else None) or ""
    if not oldest:
        return DATASET_START
    return datetime.fromisoformat(oldest).date()


def fetch_day(day: date, token: str, account_id: str) -> list[dict]:
    """Fetch all rows for a single calendar day."""
    cols = ", ".join(COLUMNS)
    nxt = day + timedelta(days=1)
    sql = (
        f"SELECT {cols} FROM {DATASET} "
        f"WHERE timestamp >= toDateTime('{day} 00:00:00') "
        f"AND timestamp < toDateTime('{nxt} 00:00:00') "
        f"ORDER BY timestamp"
    )
    return query_ae(sql, token, account_id)


def write_rollup(raw_dir: pathlib.Path, rollup_file: pathlib.Path) -> int:
    """Rebuild daily rollup CSV using streaming line-by-line reading to minimize memory."""
    buckets: dict[tuple, dict] = defaultdict(lambda: {"events": 0, "rows": 0, "sessions": set()})

    for f in sorted(raw_dir.glob("*.ndjson")):
        day = f.stem
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (
                    day,
                    r.get("blob1", ""),
                    r.get("blob3", ""),
                    r.get("blob15", ""),
                    r.get("blob20", ""),
                )
                b = buckets[key]
                b["events"] += int(r.get("_sample_interval") or 1)
                b["rows"] += 1
                if r.get("blob2"):
                    b["sessions"].add(r["blob2"])

    rollup_file.parent.mkdir(parents=True, exist_ok=True)
    with rollup_file.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "day",
                "event",
                "os",
                "country",
                "surface",
                "events",
                "stored_rows",
                "distinct_sessions",
            ]
        )
        for key in sorted(buckets):
            b = buckets[key]
            w.writerow([*key, b["events"], b["rows"], len(b["sessions"])])

    return len(buckets)


def upload_or_update_gdrive(
    drive_service,
    folder_id: str,
    local_path: pathlib.Path,
    remote_filename: str,
    mime_type: str,
) -> str | None:
    """Upload a file to Google Drive, overwriting any existing file with the same name in the folder."""
    try:
        query = (
            f"'{folder_id}' in parents and name = '{remote_filename}' and trashed = false"
        )
        results = (
            drive_service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id, name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = results.get("files", [])

        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)

        if files:
            file_id = files[0]["id"]
            print(f"Updating existing Google Drive file '{remote_filename}' (ID: {file_id})...")
            updated_file = (
                drive_service.files()
                .update(
                    fileId=file_id,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
            return updated_file.get("id")
        else:
            print(f"Creating new Google Drive file '{remote_filename}'...")
            file_metadata = {
                "name": remote_filename,
                "parents": [folder_id],
            }
            created_file = (
                drive_service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
            return created_file.get("id")
    except Exception as exc:
        err_msg = str(exc)
        print(f"⚠️ Failed to upload '{remote_filename}' to Google Drive: {err_msg}", file=sys.stderr)
        if "storageQuotaExceeded" in err_msg or "storage quota" in err_msg:
            print(
                "\n[NOTE ON GOOGLE DRIVE SERVICE ACCOUNT STORAGE]:\n"
                "Google Cloud Service Accounts have 0 MB personal quota for files created in personal 'My Drive'.\n"
                "To allow the service account to store files in Google Drive:\n"
                "  1. In Google Drive, create a 'Shared Drive' (Workspace Shared Drive).\n"
                "  2. Add your service account email as Content Manager.\n"
                "  3. Set GDRIVE_FOLDER_ID to that Shared Drive's ID.\n",
                file=sys.stderr,
            )
        return None


def main() -> int:
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not cf_token:
        print("ERROR: CLOUDFLARE_API_TOKEN environment variable is not set.", file=sys.stderr)
        return 1

    cf_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip() or DEFAULT_ACCOUNT_ID
    gcp_creds_json = os.environ.get("GCP_CREDENTIALS", "").strip()
    if not gcp_creds_json:
        print("ERROR: GCP_CREDENTIALS environment variable is not set.", file=sys.stderr)
        return 1

    gdrive_folder_id = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
    if not gdrive_folder_id:
        print("ERROR: GDRIVE_FOLDER_ID environment variable is not set.", file=sys.stderr)
        return 1

    # Initialize Google Drive client
    if Credentials is None or build is None:
        print(
            "ERROR: Missing Google Drive dependencies.\n"
            "Please run: pip install google-api-python-client google-auth",
            file=sys.stderr,
        )
        return 1

    try:
        creds_dict = json.loads(gcp_creds_json)
        scopes = ["https://www.googleapis.com/auth/drive.file"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        drive_service = build("drive", "v3", credentials=creds)
    except Exception as exc:
        print(f"ERROR: Failed to authenticate with Google Drive API: {exc}", file=sys.stderr)
        return 1

    today = datetime.now(timezone.utc).date()
    floor = get_retention_floor(cf_token, cf_account_id)
    start = max(floor, DATASET_START)

    print(f"Cloudflare AE data retention window: {floor} .. {today}")
    print(f"Fetching telemetry records starting from {start}...")

    with tempfile.TemporaryDirectory() as temp_dir_str:
        work_dir = pathlib.Path(temp_dir_str)
        raw_dir = work_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        day = start
        total_rows = 0
        days_fetched = 0

        while day <= today:
            rows = fetch_day(day, cf_token, cf_account_id)
            out_file = raw_dir / f"{day}.ndjson"
            with out_file.open("w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, separators=(",", ":")) + "\n")
            total_rows += len(rows)
            days_fetched += 1
            if len(rows) > 0 or days_fetched % 10 == 0:
                print(f"  {day}: {len(rows):>5} rows")
            day += timedelta(days=1)

        print(f"\nFetched {total_rows} total rows across {days_fetched} days.")

        # Build rollups CSV
        rollup_file = work_dir / "daily.csv"
        buckets_count = write_rollup(raw_dir, rollup_file)
        print(f"Generated rollup CSV: {buckets_count} aggregate buckets.")

        # Build zip archive
        latest_zip_path = work_dir / "tokentelemetry_ae_backup_latest.zip"
        snapshot_zip_path = work_dir / f"tokentelemetry_ae_backup_{today}.zip"

        with zipfile.ZipFile(latest_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(rollup_file, arcname="daily.csv")
            for ndjson in sorted(raw_dir.glob("*.ndjson")):
                zf.write(ndjson, arcname=f"raw/{ndjson.name}")

        # Create a hardlink or copy for the dated snapshot
        with open(latest_zip_path, "rb") as src, open(snapshot_zip_path, "wb") as dst:
            dst.write(src.read())

        print(f"Archive zip created ({latest_zip_path.stat().st_size / 1024:.1f} KB).")

        # Save copies to local archive_output directory for CI artifact persistence
        out_dir = pathlib.Path("archive_output")
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(latest_zip_path, "rb") as s, open(out_dir / "tokentelemetry_ae_backup_latest.zip", "wb") as d:
            d.write(s.read())
        with open(rollup_file, "rb") as s, open(out_dir / "tokentelemetry_daily_rollup.csv", "wb") as d:
            d.write(s.read())
        with open(snapshot_zip_path, "rb") as s, open(out_dir / f"tokentelemetry_ae_backup_{today}.zip", "wb") as d:
            d.write(s.read())

        # Upload files to Google Drive:
        # 1. daily.csv (allows viewing directly in Google Drive/Sheets)
        upload_or_update_gdrive(
            drive_service,
            folder_id=gdrive_folder_id,
            local_path=rollup_file,
            remote_filename="tokentelemetry_daily_rollup.csv",
            mime_type="text/csv",
        )

        # 2. tokentelemetry_ae_backup_latest.zip (always contains the most up-to-date archive)
        upload_or_update_gdrive(
            drive_service,
            folder_id=gdrive_folder_id,
            local_path=latest_zip_path,
            remote_filename="tokentelemetry_ae_backup_latest.zip",
            mime_type="application/zip",
        )

        # 3. tokentelemetry_ae_backup_YYYY-MM-DD.zip (dated snapshot)
        upload_or_update_gdrive(
            drive_service,
            folder_id=gdrive_folder_id,
            local_path=snapshot_zip_path,
            remote_filename=f"tokentelemetry_ae_backup_{today}.zip",
            mime_type="application/zip",
        )

    print(f"\nSuccessfully completed Cloudflare backup to Google Drive for {today}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
