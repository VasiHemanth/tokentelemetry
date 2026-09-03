"""A tiny on-disk ring buffer of quota readings, for the menu-bar sparkline.

The menu bar already refreshes every 60 seconds, so the trend chart is built
from samples the app is ALREADY fetching rather than from a new data source.
Nothing here touches the session scan: reading historical spend would mean
re-parsing transcripts on a timer, which is the one thing a menu-bar app must
not do.

What is stored is *consumption percentage over time* per (provider, resource),
which answers the question a menu bar is actually asked -- "am I burning this
window faster than usual?" -- rather than historical cost, which the dashboard
already shows better.

Every operation is best-effort. A missing, corrupt, or unwritable file must
never stop the menu from rendering, so all failure modes are swallowed and the
caller simply gets an empty trend.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger("tokentelemetry.menubar.history")

# Bump when the stored shape changes. A mismatch is discarded rather than
# migrated: this is a rolling cache of cheap samples, not durable user data.
VERSION = 1

# Samples kept per series. At the 60s refresh cadence this is roughly the last
# hour, which is the span where a sparkline still reads as a shape rather than
# a smear. Older points are dropped from the front.
MAX_SAMPLES = 40

FILENAME = "menubar-trend.json"


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / FILENAME


def series_key(provider_id: str, resource_id: str) -> str:
    """Series identity. Kept flat so the payload stays a one-level dict."""
    return f"{provider_id}:{resource_id}"


def load(data_dir: Path) -> Dict[str, List[float]]:
    """Read stored series, or ``{}`` when absent, unreadable, or stale."""
    try:
        raw = _path(data_dir).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return {}
    try:
        payload = json.loads(raw)
    except ValueError:
        logger.debug("menubar trend store is not valid JSON; ignoring")
        return {}
    if not isinstance(payload, Mapping) or payload.get("version") != VERSION:
        return {}
    series = payload.get("series")
    if not isinstance(series, Mapping):
        return {}
    clean: Dict[str, List[float]] = {}
    for key, values in series.items():
        if not isinstance(key, str) or not isinstance(values, Sequence):
            continue
        points = [float(v) for v in values
                  if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if points:
            clean[key] = points[-MAX_SAMPLES:]
    return clean


def record(data_dir: Path, samples: Mapping[str, float]) -> Dict[str, List[float]]:
    """Append one reading per series and return the updated series.

    ``samples`` maps :func:`series_key` to a percentage. A series absent from
    this call is left untouched rather than zero-filled: a provider that failed
    to refresh has no new reading, and inventing a 0 would draw a cliff that
    never happened.
    """
    stored = load(data_dir)
    for key, value in samples.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        points = stored.setdefault(key, [])
        points.append(max(0.0, min(100.0, float(value))))
        if len(points) > MAX_SAMPLES:
            del points[: len(points) - MAX_SAMPLES]
    _save(data_dir, stored)
    return stored


def _save(data_dir: Path, series: Mapping[str, Sequence[float]]) -> None:
    """Atomically replace the store; failure is logged, never raised."""
    payload = {"version": VERSION, "series": {k: list(v) for k, v in series.items()}}
    target = _path(data_dir)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(target.parent),
            prefix=FILENAME, suffix=".tmp", delete=False,
        )
        try:
            with handle as fh:
                json.dump(payload, fh)
            os.replace(handle.name, target)
        except BaseException:
            # A partial temp file would otherwise accumulate in the data dir.
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise
    except (OSError, ValueError, TypeError) as exc:
        logger.debug("could not write menubar trend store: %s", exc)


def trend_for(series: Mapping[str, Sequence[float]], provider_id: str,
              resource_id: str) -> Optional[List[float]]:
    """The samples for one resource, or ``None`` when there is nothing to draw.

    A single sample is treated as nothing: one bar is not a trend, and drawing
    it would imply a history the store does not have yet.
    """
    points = series.get(series_key(provider_id, resource_id))
    if not points or len(points) < 2:
        return None
    return list(points)


def samples_from_presentation(rows: Any) -> Dict[str, float]:
    """Collect the recordable percentages out of presentation rows.

    Balance rows (a dollar amount) carry no percentage and are skipped, as are
    windows whose ``pct`` never resolved.
    """
    samples: Dict[str, float] = {}
    for row in rows or ():
        if getattr(row, "is_balance", False):
            continue
        pct = getattr(row, "pct", None)
        if pct is None:
            continue
        samples[series_key(row.provider_id, row.resource_id)] = float(pct)
    return samples
