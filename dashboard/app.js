"use strict";

const taskNames = {
  "scanner-daily": "Daily market scan",
  "scanner-orb": "Opening-range scan",
  news: "News monitor",
  entry: "Entry check",
  "exit-plan": "Exit planner",
  timemachine: "Time Machine replay",
  budget: "Position budget",
  risk: "Risk check",
  tickets: "Broker tickets (view only)",
  "alerts-check": "Alert check",
  "alerts-clock": "NYSE clock",
  "alerts-list": "Alert rules",
  analyst: "Earnings analyst",
  pelosi: "Public disclosure tracker"
};
const activityItems = new Map();
const runningJobs = new Set();
const $ = (selector, root = document) => root.querySelector(selector);

function nyClock() {
  const clock = $("#ny-clock");
  clock.textContent = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true
  }).format(new Date());
}

function getFile(state, name) {
  return state && state.files ? state.files[name] : null;
}

function formatTime(value) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

function setMode(state) {
  const tag = $("#account-mode");
  const mode = state.paper || "unknown";
  tag.className = "mode-tag " + mode;
  tag.querySelector("b").textContent =
    mode === "paper" ? "PAPER CONFIG" : mode === "live" ? "LIVE CONFIG" : "MODE UNKNOWN";
  tag.title = mode === "live"
    ? "The local config says paper trading is disabled. The dashboard still cannot submit broker orders."
    : mode === "paper"
      ? "The local config says paper trading is enabled."
      : "No readable trader/config.json with a paper setting was found.";
}

function updateWorkflowRow(filename, exists, detail) {
  const row = document.querySelector('[data-file="' + filename + '"]');
  if (!row) return;
  const stateCell = row.querySelector(".state-cell");
  stateCell.classList.toggle("present", Boolean(exists));
  stateCell.querySelector("b").textContent = exists ? detail : defaultRowLabel(filename);
}

function defaultRowLabel(filename) {
  const labels = {
    "watchlist.json": "No watchlist",
    "entry.json": "No entry check",
    "plan.json": "No plan",
    "timemachine.json": "No replay",
    "orders.json": "No order proposal"
  };
  return labels[filename] || "Not saved";
}

function updateDashboard(state) {
  const files = state.files || {};
  const config = getFile(state, "config.json");
  const scan = getFile(state, "watchlist.json");
  const entry = getFile(state, "entry.json");
  const plan = getFile(state, "plan.json");
  const orders = getFile(state, "orders.json");
  const scanData = scan && scan.data;
  const entryData = entry && entry.data;
  const planData = plan && plan.data;
  const orderData = orders && orders.data;
  setMode(state);

  const existing = Object.keys(files).filter((key) => files[key].exists);
  const latest = existing
    .map((key) => files[key].modified)
    .filter(Boolean)
    .sort()
    .pop();
  $("#updated-at").textContent = latest ? formatTime(latest) : "No saved files";
  $("#session-state").textContent = config && config.exists
    ? (state.paper === "live" ? "Live configuration detected" : state.paper === "paper" ? "Paper configuration loaded" : "Configuration found")
    : "Workspace not initialized";
  $("#session-detail").textContent = config && config.error
    ? "Configuration could not be read: " + config.error
    : config && config.exists
      ? "Risk limits and operating settings are read from trader/config.json"
      : "Run the existing tools to create trader/ outputs";

  const hits = scanData && Array.isArray(scanData.hits) ? scanData.hits : [];
  $("#scan-state").textContent = scan && scan.exists
    ? (hits.length + " matched chart" + (hits.length === 1 ? "" : "s"))
    : "No scan saved";
  $("#scan-detail").textContent = scan && scan.exists
    ? [scanData.mode, scanData.as_of ? formatTime(scanData.as_of) : null, scanData.scanned != null ? scanData.scanned + " scanned" : null].filter(Boolean).join(" · ")
    : "Run the scanner to refresh the watchlist";

  const planSymbol = planData && planData.symbol ? planData.symbol : "";
  $("#plan-state").textContent = planSymbol ? planSymbol + " long plan" : plan && plan.exists ? "Plan saved" : "No plan saved";
  $("#plan-detail").textContent = planData
    ? [planData.entry != null ? "Entry " + planData.entry : null, planData.stop != null ? "Stop " + planData.stop : null, planData.target != null ? "Target " + planData.target : null].filter(Boolean).join(" · ")
    : "Exit plans are read from trader/plan.json";

  const watchCount = hits.length;
  $("#workflow-count").textContent = existing.filter((key) => ["watchlist.json", "entry.json", "plan.json", "timemachine.json", "orders.json"].includes(key)).length + " / 5 FILES";
  updateWorkflowRow("watchlist.json", Boolean(scan && scan.exists), watchCount + " matched");
  updateWorkflowRow("entry.json", Boolean(entry && entry.exists), entryData && entryData.status ? String(entryData.status).toUpperCase() : entryData && entryData.symbol ? entryData.symbol + " checked" : "Entry checked");
  updateWorkflowRow("plan.json", Boolean(plan && plan.exists), planSymbol ? planSymbol + " planned" : "Plan saved");
  updateWorkflowRow("timemachine.json", Boolean(getFile(state, "timemachine.json") && getFile(state, "timemachine.json").exists), "Replay saved");
  updateWorkflowRow("orders.json", Boolean(orders && orders.exists), Array.isArray(orderData) ? orderData.length + " proposed" : "Proposal saved");

  $("#watchlist-caption").textContent = scan && scan.exists
    ? [watchCount + " matched", scanData.as_of ? "as of " + formatTime(scanData.as_of) : null, scanData.failed ? scanData.failed + " unavailable" : null].filter(Boolean).join(" · ")
    : "No saved scan results";
  renderWatchlist(hits);
  const path = Object.keys(files).find((key) => files[key].error);
  $("#workspace-path").textContent = path ? "Read issue: " + path : "Local files only · no broker connection";
}

function renderWatchlist(hits) {
  const container = $("#watchlist-rows");
  container.replaceChildren();
  if (!hits.length) {
    const empty = document.createElement("div");
    empty.className = "empty-row";
    empty.setAttribute("role", "row");
    empty.textContent = "Run a scan to populate this table. A match is a chart rule, not a recommendation.";
    container.append(empty);
    return;
  }
  hits.slice(0, 8).forEach((hit) => {
    const row = document.createElement("div");
    row.className = "watch-row";
    row.setAttribute("role", "row");
    const symbol = document.createElement("strong");
    symbol.className = "ticker-name";
    symbol.textContent = hit.symbol || "Unknown";
    const setup = document.createElement("span");
    setup.textContent = Array.isArray(hit.setups)
      ? hit.setups.join(", ")
      : hit.setup || hit.type || "Matched rule";
    const at = document.createElement("span");
    at.textContent = hit.at || hit.time || hit.close_date || "—";
    const status = document.createElement("span");
    status.className = "row-tag";
    status.textContent = "MATCHED";
    row.append(symbol, setup, at, status);
    container.append(row);
  });
  if (hits.length > 8) {
    const more = document.createElement("div");
    more.className = "watch-more";
    more.textContent = (hits.length - 8) + " more matches in trader/watchlist.json";
    container.append(more);
  }
}

async function refreshState() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not read the workspace.");
    updateDashboard(result);
  } catch (error) {
    $("#session-state").textContent = "Dashboard unavailable";
    $("#session-detail").textContent = error.message;
  }
}

function addActivity(id, task, status) {
  const list = $("#activity-list");
  if (list.querySelector(".activity-empty")) list.replaceChildren();
  const item = document.createElement("article");
  item.className = "activity-item " + status;
  item.dataset.jobId = id;
  const head = document.createElement("div");
  head.className = "activity-item-head";
  const title = document.createElement("strong");
  title.textContent = taskNames[task] || task;
  const state = document.createElement("span");
  state.className = "activity-state";
  state.textContent = status.toUpperCase();
  head.append(title, state);
  const output = document.createElement("pre");
  output.className = "task-output";
  output.textContent = "Starting local Python tool…";
  item.append(head, output);
  list.prepend(item);
  activityItems.set(id, item);
  while (list.children.length > 8) list.lastElementChild.remove();
  return item;
}

function updateActivity(job) {
  const item = activityItems.get(job.id);
  if (!item) return;
  item.className = "activity-item " + job.status;
  item.querySelector(".activity-state").textContent =
    job.status === "finished" ? "EXIT " + job.exit_code : job.status.toUpperCase();
  const output = item.querySelector(".task-output");
  if (job.status === "queued" || job.status === "running") {
    output.textContent = job.status === "queued" ? "Waiting for a local worker…" : "Tool is running. This may take a few minutes.";
    return;
  }
  output.textContent = job.error
    ? job.error + (job.output ? "\n\n" + job.output : "")
    : (job.output || (job.status === "completed" ? "Task completed with no console output." : "Tool finished with exit code " + job.exit_code + "."));
  runningJobs.delete(job.id);
  $("#activity-status").textContent = runningJobs.size ? "RUNNING" : "READY";
  refreshState();
}

async function watchJob(id) {
  runningJobs.add(id);
  $("#activity-status").textContent = "RUNNING";
  while (runningJobs.has(id)) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    try {
      const response = await fetch("/api/jobs/" + encodeURIComponent(id), { cache: "no-store" });
      const job = await response.json();
      if (!response.ok) throw new Error(job.error || "Could not read task status.");
      updateActivity(job);
    } catch (error) {
      updateActivity({ id, status: "failed", error: error.message });
    }
  }
}

async function startTask(task, button) {
  const payload = { task };
  if (["news", "entry", "analyst"].includes(task)) {
    const symbol = $("#symbol-input").value.trim().toUpperCase();
    if (!symbol) {
      $("#symbol-input").focus();
      $("#symbol-hint").textContent = "Enter a ticker before running this task.";
      $("#symbol-hint").classList.add("error-text");
      return;
    }
    payload.symbol = symbol;
  }
  $("#symbol-hint").textContent = "Use a ticker symbol; no order actions are available.";
  $("#symbol-hint").classList.remove("error-text");
  button.disabled = true;
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The task could not be started.");
    addActivity(result.id, task, result.status);
    watchJob(result.id);
  } catch (error) {
    const id = "error-" + Date.now();
    const item = addActivity(id, task, "failed");
    item.querySelector(".task-output").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

document.querySelectorAll("[data-task]").forEach((button) => {
  button.addEventListener("click", () => startTask(button.dataset.task, button));
});
$("#refresh-button").addEventListener("click", refreshState);
window.addEventListener("DOMContentLoaded", () => {
  nyClock();
  window.setInterval(nyClock, 1000);
  refreshState();
  window.setInterval(refreshState, 30000);
});
