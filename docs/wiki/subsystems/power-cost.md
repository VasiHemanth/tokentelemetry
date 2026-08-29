---
type: Subsystem
title: Power, energy and CO2 costing
description: Local-electricity and subscription costing; energy = configured watts x session latency, recomputed at read time from stored raw facts.
resource: /backend/power_meter.py
tags: [subsystem, backend, power, co2]
timestamp: 2026-07-02
---

# Power, energy and CO2 costing

Shipped from discussion #49. Code: `backend/power_config.py`,
`backend/power_meter.py`, billing in `backend/billing_mode.py` +
`backend/billing_route.py`; insights in `backend/insights.py`.

- **Model:** measured tok/s already reflects total session latency, so
  energy = configured watts x session latency. CO2 derives from energy.
- Insights are recomputed at read time from raw facts in the
  [history store](history-store.md), so changing wattage or tariff
  re-prices old sessions retroactively.
- Local model inventories come from `~/.ollama` (`OLLAMA_DIR`) and
  `~/.cache/huggingface` (`HF_DIR`); surfaced on the
  [/local-models page](../features/local-models.md).
- Billing modes cover API pay-per-token vs subscription plans; re-check
  provider billing formats before touching this code
  ([pricing](pricing.md) has the same rule).
- Tests: `test_power_config.py`, `test_power_meter.py`, `test_local_power.py`,
  `test_co2.py`, `test_billing_mode.py`, `test_billing_route.py`.
