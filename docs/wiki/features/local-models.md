---
type: Feature
title: Local models
description: Inventory of local models from Ollama and Hugging Face caches, with electricity-cost context.
resource: /website/content/docs/configuration/local-models.mdx
tags: [feature, local-models, power]
timestamp: 2026-07-02
---

# Local models

`/local-models` lists models found in `~/.ollama` and
`~/.cache/huggingface` (`OLLAMA_DIR`, `HF_DIR` in `backend/main.py`) and
ties into [power costing](../subsystems/power-cost.md): local inference is
priced by electricity (watts x latency) instead of API rates, enabling
API-vs-local savings comparisons.
