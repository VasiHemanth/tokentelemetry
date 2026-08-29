---
type: Subsystem
title: Pricing
description: Costing from a bundled, committed pricing_data.json; refreshed by a CI-only models.dev sync that opens a review PR. Zero runtime network.
resource: /backend/pricing.py
tags: [subsystem, backend, pricing, local-first]
timestamp: 2026-07-02
---

# Pricing

- `backend/pricing.py` reads only the committed `backend/pricing_data.json`.
  No network I/O at import or runtime; users get fresh prices through normal
  version updates ([local-first](../conventions/local-first.md)).
- `backend/pricing_sync.py` is the ONLY place with outbound pricing I/O:
  dev/CI-only, fetches models.dev, regenerates the JSON. Runs on a schedule
  via `.github/workflows/pricing-sync.yml`, which opens a PR so the diff is
  reviewed before shipping (latest sync: PR #117).
- Cost is computed per line/file by that line's own model, never the parent
  session's (subagent models differ; see
  [Claude Code](../harnesses/claude-code.md)).
- Hermes gets provider-aware pricing: the same model priced per aggregator
  (direct API / OpenRouter / Together / Fireworks).
- Before touching billing/subscription/drain logic, re-search current
  provider billing formats; they change often.
- Tests: `backend/test_pricing.py`, `backend/test_pricing_data.py`.
