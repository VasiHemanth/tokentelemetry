# Feature Friday — 2026-06-26

> Based on: git log since 2026-06-19 | UPDATE.json tag 2026-06-23
> Shipped this week: 6 feat: commits, 2 refactors, 1 chore, 1 fix

---

## X / Twitter Thread

**Tweet 1 — Hook**

TokenTelemetry now shows you exactly what your agent swarm is doing and what it's costing — in real time.

Four new features landed this week for people running multi-agent workflows. 🧵

*[Suggested visual: screenshot of the new /workflows page showing a named task with aggregated cost + the System resource panel side by side]*

---

**Tweet 2 — Workflow grouping**

New: group any sessions from any agent into a named Workflow.

Running three agents in parallel to ship a feature? Tag them all. You'll see the total token count, cost, and which agents are still active — in one place.

Great for the "how much did this actually cost?" question you always ask after.

*[Suggested visual: /workflows page showing a named task with multiple agent sessions rolled up, total cost visible]*

---

**Tweet 3 — Workflows UI**

The /workflows page also got a full UI overhaul:

- Grid / list / compact view toggle (persisted per user)
- Rich session rows with model, duration, and cost inline
- Search + filter so you can find the workflow you care about

*[Suggested visual: the view toggle in action — grid vs. list]*

---

**Tweet 4 — Concurrency timeline**

New: concurrency timeline shows which agent sessions were running at the same time.

If you run Claude Code + Codex in parallel, you can see the window where both were burning tokens and the combined $/hr during that overlap.

Finally a way to see the "parallel agents tax."

*[Suggested visual: concurrency timeline with two overlapping session bars, combined cost/hr callout]*

---

**Tweet 5 — Attribution cost tree**

New: when a parent agent spawns subagents, its session now rolls up the full cost of the entire tree.

Open the parent → see every child session's tokens and cost, recursively. No more adding up subagent totals manually.

*[Suggested visual: session detail page showing parent cost + delegation tree breakdown]*

---

**Tweet 6 — Live process monitor**

New: a System panel shows real-time CPU, memory, and disk IO for every AI agent process on your machine.

If a write rate exceeds 5 MB/s, you get a warning banner. This is the exact class of issue that caused Codex Desktop to write ~222 TB/year unnoticed.

---

**Tweet 7 — Close + install**

All of this is local, zero-config, free, and open source.

Install in one line:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

GitHub → https://github.com/VasiHemanth/tokentelemetry

---

## Discord #announcements Post

**TokenTelemetry — Feature Friday update (2026-06-26)**

Four new features shipped this week focused on multi-agent visibility and cost attribution:

**🗂 Workflow grouping**
Tag sessions from any agent into a named workflow and see the total cost, token count, and active agents for that task. Useful when you're using multiple agents in parallel on the same feature or bug fix and want to know the real total.

**🔀 Concurrency timeline**
A new analytics view shows which agent sessions were running at the same time and the combined cost per hour during those overlaps. Handy when you're running parallel agents and want to understand cumulative burn.

**🌳 Recursive attribution cost tree**
When a parent agent spawns subagents, its session now shows the full cost of the entire delegation tree — not just its own tokens. Open any session with children to see the complete breakdown.

**📊 Live agent process monitor**
A new System panel shows real-time disk IO, CPU, and memory for every AI agent process running on your machine. Write rates above 5 MB/s trigger a warning banner — the exact kind of silent runaway that caused Codex Desktop to write ~222 TB/year unnoticed.

**Workflows UI polish**
The /workflows page also got richer session rows, a grid/list/compact view toggle (persisted per user), and search + filters.

---

Install / update:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Full changelog: https://github.com/VasiHemanth/tokentelemetry/commits/main

---

## LinkedIn Post

**Finally: visibility into what your agent fleet is actually doing**

If you're using AI coding agents seriously in 2026 — running Claude Code, Codex, Antigravity, or any combination in parallel — you've probably asked yourself: "how much did that actually cost?" or "why is my disk so active right now?"

This week, TokenTelemetry shipped four features that answer those questions.

**Workflow grouping** lets you tag any set of agent sessions — across multiple agents and tools — into a named workflow. Say you used Claude Code for planning, Codex for implementation, and another agent for review on a single feature. Tag them all as "auth refactor" and you see the combined cost, total tokens, and which agents are still running. For engineering managers and lead developers who want to understand the real cost of an AI-assisted task, this is the view that's been missing.

**Concurrency timeline** shows which agent sessions overlapped in time and what the combined hourly cost was during those windows. Running two agents in parallel isn't just double the cost — the overlap window tells you exactly when you were spending most.

**Recursive cost attribution** solves the hidden subagent cost problem. When a parent agent spawns subagents (which is common in Claude Code's architecture), the parent session now shows the total cost of the entire delegation tree recursively. Previously, you'd see only the parent's own tokens; the subagent costs were invisible unless you went looking.

**Live process monitoring** adds a System panel to the dashboard with real-time CPU, memory, and disk write rates for every AI agent process on your machine. A threshold warning fires at 5 MB/s of disk writes — catching the class of runaway I/O that caused one popular agent to write an estimated 222 TB/year in the background unnoticed.

TokenTelemetry is open source, 100% local, and installs in one line. No account, no cloud, no data leaves your machine.

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry

---

*Note for reviewer: the refactor commits this week (relabeling Hermes tree → "Session Continuation Tree", scoping cost tree to Hermes sessions only) are internal naming cleanups — not mentioned above. The website mobile nav fix (PR #110) is also omitted from the user-facing announcements as a minor patch.*
