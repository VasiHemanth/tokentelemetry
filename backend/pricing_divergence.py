#!/usr/bin/env python3
"""Report curated pricing entries that disagree with the models.dev overlay.

Why this exists: issue #303. DeepSeek repriced on 2026-08-16 and the curated
rates in pricing.py sat three months stale while the weekly models.dev sync
(.github/workflows/pricing-sync.yml) ran green every Monday. The sync could
never have fixed it — `_load_bundled_pricing()` skips any key an inline entry
already claims, and the workflow only writes pricing_data.json. So a curated
entry, once written, is invisible to every refresh that follows.

This turns that silent shadow into a reviewable signal. It does NOT decide who
is right: the inline table is authoritative by design (it captures hand-checked
direct-provider rates that aggregator-derived data gets wrong), and models.dev
is itself sometimes stale — it still carried DeepSeek's old rates eight days
after the repricing. A divergence means "a human should look", not "the inline
value is wrong".

There is a third failure mode worth naming, because it produced the largest
divergence on this repo and neither layer was stale: the curated table held
deepseek-v4-pro's $1.74/$3.48 LIST price while the overlay held $0.435/$0.87,
the 75%-promotional price the provider was actually billing. List-vs-effective
looks identical to staleness in this report. Check what the provider charges,
not just what it lists.

Detection relies on a property of the merge: because the overlay only inserts
keys the inline table does not already hold, any key whose merged value differs
from the raw overlay value MUST be an inline entry that won. Overlay-injected
keys are equal by construction, so they can never appear here.

Read the direction, not just the count. Correcting a curated rate against the
provider's price list RAISES the number of rows here whenever the overlay is
the stale side — fixing DeepSeek (#303) took this report from 25 entries to 30,
because the inline table moved to the true rate while models.dev stayed on the
old one. A rising count can mean the curated table just got more accurate. The
per-field breakdown is what tells you which side moved.

Known gap: an entry that is stale in BOTH layers is invisible to this check.
deepseek-v4-flash was exactly that — inline and overlay both said $0.14/$0.28.
Two agreeing sources are still wrong when both derive from the same stale
upstream; this catches drift between layers, not drift from reality.

Usage:
    python backend/pricing_divergence.py                # report, always exit 0
    python backend/pricing_divergence.py --fail-over 25 # exit 1 past 25% drift
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))

import pricing  # noqa: E402

_DATA = Path(__file__).parent / "pricing_data.json"
RATE_FIELDS = ("in", "out", "cached_read")


def _rel_diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Relative difference between two rates, as a percentage of the larger.

    None on either side means "not comparable" rather than "differs": a missing
    cached_read is a gap in the data, and calculate_cost substitutes 10% of the
    input rate for it, so calling that a 100% divergence would be noise.
    """
    if a is None or b is None:
        return None
    if a == b:
        return 0.0
    scale = max(abs(a), abs(b))
    if scale == 0:
        return 0.0
    return abs(a - b) / scale * 100.0


def _worst(inline: Dict[str, Any], overlay: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Largest divergence across the rate fields, plus a per-field breakdown."""
    worst, detail = 0.0, []
    for f in RATE_FIELDS:
        d = _rel_diff(inline.get(f), overlay.get(f))
        if d is None:
            continue
        if d > 0:
            detail.append(f"{f}: {inline.get(f)} vs {overlay.get(f)} ({d:.0f}%)")
        worst = max(worst, d)
    return worst, detail


def find_divergences() -> List[Dict[str, Any]]:
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    rows: List[Dict[str, Any]] = []

    for key, over in (raw.get("pricing") or {}).items():
        inline = pricing.PRICING.get(str(key).lower().strip())
        if not inline or not isinstance(over, dict):
            continue
        worst, detail = _worst(inline, over)
        if worst > 0:
            rows.append({"table": "flat", "key": key, "pct": worst, "detail": detail})

    sep = pricing._PROVIDER_SEP
    for combined, over in (raw.get("by_provider") or {}).items():
        if sep not in str(combined):
            continue
        prov, model = str(combined).split(sep, 1)
        inline = pricing.PRICING_BY_PROVIDER.get((prov.lower().strip(), model.lower().strip()))
        if not inline or not isinstance(over, dict):
            continue
        worst, detail = _worst(inline, over)
        if worst > 0:
            rows.append(
                {"table": "by_provider", "key": f"{prov}/{model}", "pct": worst, "detail": detail}
            )

    rows.sort(key=lambda r: r["pct"], reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--fail-over",
        type=float,
        default=None,
        metavar="PCT",
        help="exit 1 if any entry diverges by more than PCT (default: report only)",
    )
    ap.add_argument("--top", type=int, default=40, help="how many rows to print")
    args = ap.parse_args()

    rows = find_divergences()
    # Read the snapshot date from the file rather than a module attribute: on
    # older revisions the overlay overwrote PRICING_UPDATED instead of keeping
    # its own field, so the attribute may not exist.
    snapshot = json.loads(_DATA.read_text(encoding="utf-8")).get("updated")
    print(f"curated inline date: {getattr(pricing, 'PRICING_UPDATED', '?')}")
    print(f"models.dev snapshot: {snapshot}")
    print(f"diverging entries:   {len(rows)}\n")

    for r in rows[: args.top]:
        print(f"  [{r['pct']:5.0f}%] {r['table']:11s} {r['key']}")
        for d in r["detail"]:
            print(f"            {d}")
    if len(rows) > args.top:
        print(f"\n  ... {len(rows) - args.top} more not shown")

    if args.fail_over is not None:
        over = [r for r in rows if r["pct"] > args.fail_over]
        if over:
            print(
                f"\nFAIL: {len(over)} entr{'y' if len(over) == 1 else 'ies'} "
                f"diverge by more than {args.fail_over:g}%."
            )
            print("Either refresh the curated rate against the provider's price "
                  "list, or confirm the inline value is deliberate.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
