/* Panel rendering.
 *
 * Runs in two contexts on purpose: inside the Tauri panel window, and as a
 * plain page in a browser when `window.__PREVIEW_DATA__` is set. The preview
 * path exists so the exact same markup and CSS can be reviewed without the
 * native window, and it keeps one implementation rather than a mockup that
 * drifts from the real thing.
 */

const tauri = window.__TAURI__;
const $ = (id) => document.getElementById(id);

const fmtMoney = (n) =>
  n >= 1000 ? `$${Math.round(n).toLocaleString()}` : `$${n.toFixed(2)}`;

function fmtTokens(n) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}

const AGENT_LABELS = {
  claude: "Claude Code",
  codex: "Codex",
  gemini: "Gemini",
  antigravity: "Antigravity",
  copilot: "Copilot",
  opencode: "OpenCode",
  grok: "Grok",
  cursor: "Cursor",
  cline: "Cline",
  qwen: "Qwen",
  hermes: "Hermes",
  smallcode: "SmallCode",
  vibe: "Vibe",
};
const label = (a) => AGENT_LABELS[a] || a;

function dayName(iso) {
  // Parse as local, not UTC: new Date("2026-08-03") is midnight UTC and can
  // render as the previous day west of Greenwich.
  const [y, m, d] = iso.split("-").map(Number);
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][
    new Date(y, m - 1, d).getDay()
  ];
}

function renderBars(days) {
  const host = $("bars");
  host.innerHTML = "";
  if (!days.length) {
    host.innerHTML = '<div class="empty">No activity in this window.</div>';
    return;
  }
  // Scale to the tallest bar. A zero-cost week must not divide by zero.
  const peak = Math.max(...days.map((d) => d.cost), 0.0001);
  for (const d of days) {
    const col = document.createElement("div");
    col.className = "bar-col" + (d.is_today ? " today" : "");
    // Hit target is the whole column, which is wider than the bar itself.
    col.title = `${d.date} (${dayName(d.date)}) · ${fmtMoney(d.cost)} · ${fmtTokens(d.tokens)} tokens`;

    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${Math.max((d.cost / peak) * 100, 2)}%`;
    col.appendChild(bar);

    // Only today carries a direct label; seven labels would be a table.
    if (d.is_today) {
      const tag = document.createElement("div");
      tag.className = "bar-tag";
      tag.textContent = fmtMoney(d.cost);
      col.appendChild(tag);
    }
    host.appendChild(col);
  }
  $("axisFrom").textContent = `${days[0].date.slice(5)} (${dayName(days[0].date)})`;
}

function renderRows(hostId, items, emptyText) {
  const host = $(hostId);
  host.innerHTML = "";
  if (!items.length) {
    host.innerHTML = `<li class="empty">${emptyText}</li>`;
    return;
  }
  const peak = Math.max(...items.map((i) => i.cost), 0.0001);
  for (const it of items.slice(0, 5)) {
    const li = document.createElement("li");
    li.className = "row";
    li.title = `${label(it.name)} · ${fmtMoney(it.cost)} · ${fmtTokens(it.tokens)} tokens`;

    const name = document.createElement("div");
    name.className = "row-name";
    name.textContent = label(it.name);

    const val = document.createElement("div");
    val.className = "row-val";
    val.textContent = fmtMoney(it.cost);

    const track = document.createElement("div");
    track.className = "track";
    const fill = document.createElement("i");
    fill.style.width = `${Math.max((it.cost / peak) * 100, 1.5)}%`;
    track.appendChild(fill);

    li.append(name, val, track);
    host.appendChild(li);
  }
}

function renderChips(d) {
  const chips = [];
  if (d.skills) chips.push(`${d.skills} skill${d.skills > 1 ? "s" : ""}`);
  if (d.mcp_servers) chips.push(`${d.mcp_servers} MCP server${d.mcp_servers > 1 ? "s" : ""}`);
  if (d.subagents) chips.push(`${d.subagents} subagent type${d.subagents > 1 ? "s" : ""}`);
  if (d.energy_wh > 0) chips.push(`${d.energy_wh.toFixed(1)} Wh`);
  if (d.co2_g > 0) chips.push(`${d.co2_g.toFixed(0)} g CO₂`);
  $("chips").innerHTML = chips
    .map((c) => `<span class="chip">${c}</span>`)
    .join("");
}

function render(d, status) {
  $("amount").textContent = fmtMoney(d.today_cost);
  $("stateText").textContent = status.text;
  $("dot").className = "dot " + status.cls;

  $("weekTotal").textContent = `${fmtMoney(d.week_cost)} · ${fmtTokens(d.week_tokens)}`;
  renderBars(d.days);

  $("tokens").textContent = fmtTokens(d.today_tokens);
  $("tokensSub").textContent = `${fmtTokens(d.output)} out`;
  $("cache").textContent = `${d.cache_hit_pct.toFixed(1)}%`;
  $("cacheSub").textContent = `${fmtTokens(d.cached)} cached`;
  $("agentCount").textContent = String(d.agents.length);
  $("agentSub").textContent = d.agents.length ? label(d.agents[0].name) : "none today";

  renderRows("agents", d.agents, "No agent activity today.");
  renderRows("models", d.models, "No model activity today.");
  renderChips(d);
}

function showError(msg) {
  document.querySelector(".sheet").innerHTML =
    `<div class="err">${msg}</div>`;
}

async function load() {
  if (window.__PREVIEW_DATA__) {
    render(window.__PREVIEW_DATA__, { text: "Running", cls: "running" });
    return;
  }
  try {
    const [d, s] = await Promise.all([
      tauri.core.invoke("panel_data"),
      tauri.core.invoke("ui_state"),
    ]);
    const kind = s.status.kind;
    render(d, {
      text: s.status_label,
      cls:
        kind === "Running" || kind === "Attached"
          ? "running"
          : kind === "Starting"
            ? "starting"
            : kind === "Error" || kind === "NeedsSetup"
              ? "error"
              : "",
    });
  } catch (e) {
    showError(String(e));
  }
}

/* When the panel was last put on screen. Auto-hide is suppressed briefly after
   that, because macOS keeps focus on the status item when you click it and
   delivers a blur to the popover the moment it appears. Acting on that blur
   hides the panel instantly, which is indistinguishable from it never having
   opened. */
let shownAt = 0;

if (tauri) {
  document.querySelectorAll("[data-route]").forEach((b) =>
    b.addEventListener("click", () => {
      tauri.core.invoke("open_route_cmd", { route: b.dataset.route });
    }),
  );
  $("prefs").addEventListener("click", () => tauri.core.invoke("show_prefs_cmd"));

  // Rust tells us each time the window is shown: reset the grace period and
  // refresh, so a reopened panel is never showing stale numbers.
  if (tauri.event && tauri.event.listen) {
    tauri.event.listen("panel-shown", () => {
      shownAt = Date.now();
      load();
    });
  }

  // Close when focus genuinely goes elsewhere, the way a popover should.
  window.addEventListener("blur", () => {
    if (Date.now() - shownAt < 800) return;
    // Re-check after the focus dust settles; a transient blur is not a dismiss.
    setTimeout(() => {
      if (!document.hasFocus()) tauri.core.invoke("hide_panel");
    }, 150);
  });
  window.addEventListener("focus", () => {
    if (!shownAt) shownAt = Date.now();
  });
}

load();
// Only while the panel is actually open and focused, and not often: each load
// makes the backend rescan every session, which is expensive on a large
// history. The panel reloads on every open anyway, so this only matters if you
// leave it sitting on screen.
setInterval(() => {
  if (!window.__PREVIEW_DATA__ && document.hasFocus()) load();
}, 120000);
