const invoke = window.__TAURI__.core.invoke;
const $ = (id) => document.getElementById(id);

let dirty = false;
[
  "repoPath",
  "frontPort",
  "apiPort",
  "pollSecs",
  "startOnLaunch",
].forEach((id) => $(id).addEventListener("input", () => (dirty = true)));

function dotClass(kind) {
  if (kind === "Running" || kind === "Attached") return "dot running";
  if (kind === "Starting") return "dot starting";
  if (kind === "Error" || kind === "NeedsSetup") return "dot error";
  return "dot";
}

function render(s) {
  $("spend").textContent =
    s.spend === null || s.spend === undefined
      ? "—"
      : s.spend >= 1000
        ? `$${s.spend.toFixed(0)}`
        : `$${s.spend.toFixed(2)}`;
  $("statusText").textContent = s.status_label;
  $("dot").className = dotClass(s.status.kind);

  // Do not stomp on fields the user is mid-edit.
  if (!dirty) {
    $("repoPath").value = s.repo_path || "";
    $("frontPort").value = s.front_port;
    $("apiPort").value = s.api_port;
    $("pollSecs").value = s.poll_secs;
    $("startOnLaunch").checked = s.start_on_launch;
  }
  $("autostart").checked = s.autostart;
  $("restart").disabled = !s.repo_path;

  const rows = [
    ["node", s.node_path, true],
    ["npm", s.npm_found ? "found" : null, false],
    ["python3", s.python_found ? "found" : null, false],
  ];
  $("runtime").innerHTML = rows
    .map(([name, value]) => {
      const cls = value ? "path" : "path missing";
      const text = value || "not found";
      return `<li><span>${name}</span><span class="${cls}">${escapeHtml(text)}</span></li>`;
    })
    .join("");
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

function message(text, kind) {
  const el = $("saveMsg");
  el.textContent = text;
  el.className = kind ? `msg ${kind}` : "msg";
}

async function refresh() {
  try {
    render(await invoke("ui_state"));
    const lines = await invoke("ui_logs");
    $("logs").textContent = lines.length ? lines.join("\n") : "No output yet.";
    $("logs").scrollTop = $("logs").scrollHeight;
  } catch (e) {
    message(String(e), "err");
  }
}

$("pick").addEventListener("click", async () => {
  const picked = await invoke("pick_repo");
  if (picked) {
    $("repoPath").value = picked;
    dirty = true;
    message("Not saved yet.", null);
  }
});

$("save").addEventListener("click", async () => {
  try {
    const state = await invoke("save_settings", {
      repoPath: $("repoPath").value,
      apiPort: Number($("apiPort").value),
      frontPort: Number($("frontPort").value),
      pollSecs: Number($("pollSecs").value),
      startOnLaunch: $("startOnLaunch").checked,
    });
    dirty = false;
    render(state);
    message("Saved. Restart the services to apply port changes.", "ok");
  } catch (e) {
    message(String(e), "err");
  }
});

$("autostart").addEventListener("change", async (e) => {
  try {
    const on = await invoke("set_autostart", { enabled: e.target.checked });
    e.target.checked = on;
    message(on ? "Will launch at login." : "Will not launch at login.", "ok");
  } catch (err) {
    e.target.checked = !e.target.checked;
    message(String(err), "err");
  }
});

$("redetect").addEventListener("click", async () => {
  message("Looking for node, npm and python3…", null);
  await invoke("redetect");
  await refresh();
  message("Re-detected.", "ok");
});

$("restart").addEventListener("click", async () => {
  message("Restarting…", null);
  await invoke("restart_services");
  await refresh();
});

$("openDash").addEventListener("click", () => invoke("open_dashboard"));

refresh();
setInterval(refresh, 3000);
