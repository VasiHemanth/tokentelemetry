# Feature Friday — 2026-07-31

> Based on: `git fetch origin` + `git log origin/main --since="7 days ago"` (Jul 24–30) + `origin/main:UPDATE.json`.
> **Note for maintainer:** the local working branch (`feat/local-model-insights`) is *behind* `origin/main` and has uncommitted local-model work in its tree — I ignored both and drafted strictly from what's shipped on `origin/main`. UPDATE.json on origin/main is current (newest entry 2026-07-26), so this is drafted from real release entries, not raw commits.
> Shipped this week (Jul 24–30, since the last Feature Friday on 07-24): **2 user-facing feature lines** — Docker/Podman container support with pre-built GHCR images (#172), and next-run time + truer cancelled/expired state on active loops (#194). Plus fixes/docs: TT_AUTH_TOKEN now forwarded into the container so remote/container auth works (#200), a Docker/Podman run guide (#192), and a privacy + Windows fix that bans session URLs and machine identifiers from anonymous telemetry and corrects Windows project names (#213).
> This is a **feature** post (not a progress post) — user-facing work landed.

**Reviewer checklist before posting:**
- **Contributor credit REQUIRED:** the headline feature (Docker/Podman, #172) was built and contributed by **slmingol** — the UPDATE.json entry already credits them, and the credit line is carried into the thread/Discord/LinkedIn below. Do not drop it. If you know their X/Discord handle, @-mention them in the hook or close.
- No numbers are invented — ports (13000 dashboard / 18000 API), `make up/down/logs`, multi-arch, loopback-only, read-only log mounts all come straight from the commit + UPDATE.json.
- Headline is **container support**. If you'd rather lead with the loops next-run improvement, it swaps into the hook cleanly, but container is the more broadly shareable "try it in 30 seconds" story.
- Suggested visuals are marked inline; grab fresh screenshots/GIFs from a running instance (a terminal recording of `make up` → dashboard loading is the strongest hook asset).

---

## X / Twitter Thread

**Tweet 1 — Hook**

You can now run TokenTelemetry without installing Python or Node on your machine at all.

`docker compose up` (or Podman) → the full local dashboard for what your AI coding agents do and cost, in a container. Pre-built multi-arch images, loopback-only, your logs mounted read-only.

Shipped this week 🧵

*[Suggested visual: a short terminal GIF — `make up` building/starting, then the dashboard loading at localhost:13000]*

---

**Tweet 2 — Container support**

If you'd rather not put a Python + Node toolchain on the host, TokenTelemetry now ships Dockerfiles + a Compose file, wrapped in a Makefile that auto-detects Docker *or* Podman:

`make up` builds & starts · `make down` stops · `make logs` tails.

Dashboard on :13000, API on :18000 — both loopback-only. Your agent logs mount read-only, so nothing leaks and nothing gets written back.

Built and contributed by **slmingol** (PR #172) 🙏

---

**Tweet 3 — Pre-built images**

Don't want to compile anything? `make up-prod` pulls pre-built multi-arch images (Intel + Apple Silicon) straight from GitHub Container Registry and runs them.

Want a known-good build pinned? `TT_IMAGE_TAG=sha-abc1234 make up-prod`. Reproducible, no local build step.

---

**Tweet 4 — Loops: next run**

Also this week: every still-live recurring loop now tells you *when it fires next* — in the Recurring loops list, on each project's Config tab, and in the session trace.

Heartbeat loops project from last-fire + cadence; cron loops compute the next real schedule match; overdue-but-alive loops read "due now" instead of hiding it. Cancelled-vs-expired state is truer too — a loop won't get marked cancelled just because some *other* scheduled task in its session was deleted.

---

**Tweet 5 — Close + install**

Free, open source, 100% local — nothing ever leaves your machine.

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Or run it in a container now: https://github.com/VasiHemanth/tokentelemetry

---

## Discord #announcements Post

**TokenTelemetry — Feature Friday (2026-07-31)**

Big one for anyone who'd rather not put a toolchain on their host: **you can run TokenTelemetry in a container now.** The highlights:

- **🐳 Container support via Docker or Podman.** TokenTelemetry now ships Dockerfiles and a Compose file, so you can run it as a container instead of installing Python and Node on the host. A Makefile does the rest and auto-detects your runtime: `make up` builds and starts, `make down` stops, `make logs` tails output. Dashboard serves on **:13000**, API on **:18000** — both loopback-only — and your agent logs are mounted **read-only**. Built and contributed by **slmingol** (PR #172) — thank you! 🙌
- **📦 Pre-built images, no local build.** Multi-arch images (Intel + Apple Silicon) are published to GitHub Container Registry, so `make up-prod` pulls and runs without compiling anything. Pin a known-good build with `TT_IMAGE_TAG=sha-abc1234` when you want reproducibility.
- **🔁 Active loops now show their next run.** Every live recurring loop shows when it fires next — in the Recurring loops list on Analytics, on each loop card in a project's Config tab, and in the session trace. Heartbeat loops project from last-fire + cadence; cron loops compute the next real schedule match; overdue-but-alive loops read "due now." And cancelled-vs-expired detection is truer: a loop is no longer marked cancelled just because a *different* scheduled task in its session got deleted (#194).
- **🔒 Fixes & hardening:** the container now forwards `TT_AUTH_TOKEN` into the backend, so token-gated remote/container access works out of the box (#200); anonymous usage telemetry now bans session URLs and machine identifiers from ever being sent, and Windows project names are resolved correctly (#213); plus a full Docker/Podman run guide in the docs (#192).

Run it in a container:
```
make up        # build + start (auto-detects Docker or Podman)
make up-prod   # or pull pre-built images from GHCR
```

Or install natively:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Full changelog: https://github.com/VasiHemanth/tokentelemetry/commits/main

---

## LinkedIn Post

**Getting a usage-and-cost dashboard for your AI coding agents onto a machine just got a lot easier: TokenTelemetry now runs in a container.**

TokenTelemetry is a free, open-source, 100%-local dashboard for what your AI coding agents actually do and what they cost. This week's headline lowers the bar to trying it — and it came from the community.

**You no longer need a Python + Node toolchain on the host.** TokenTelemetry now ships Dockerfiles and a Compose file, wrapped in a Makefile that auto-detects whether you're running Docker or Podman: `make up` to build and start, `make down` to stop, `make logs` to tail. The dashboard serves on port 13000 and the API on 18000, both loopback-only, with your agent logs mounted read-only — so the security posture stays exactly what it was for the native install: nothing leaves the machine, nothing gets written back to your logs. This was built and contributed by **slmingol** (PR #172) — the kind of contribution that makes an open-source tool genuinely easier for the next person to adopt.

**And you don't have to build the images yourself.** Multi-arch images for Intel and Apple Silicon are published to GitHub Container Registry, so `make up-prod` pulls and runs without compiling anything — and you can pin a specific known-good build for reproducibility. For anyone thinking about rolling this out across a team, "run a pre-built, pinned container" is a much shorter path than "install a toolchain on every developer's machine."

**Alongside that, recurring-loop visibility got sharper.** Every still-live scheduled loop now shows when it fires next — across the analytics list, each project's config, and the session trace — and the cancelled-versus-expired distinction is now truer, so a loop that's still running keeps its real state instead of being mislabeled. Unattended, recurring workloads are exactly the ones that quietly accumulate usage, so knowing when the next one fires is the difference between a surprise and a plan.

Everything stays local and inspectable. Free and open source — run it in a container, or install natively with one line:

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry
