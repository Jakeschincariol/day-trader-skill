/* Assistant chat: a drawer on every page. Answers come from the dashboard's own data through
   read-only tools; the engine is built-in rules (free), Ollama (free, local) or Claude (API key). */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  let status = null, chatId = null, busy = false;
  const log = []; // {who, text, used, sources, engine}

  const SUGGEST = ["How is my portfolio doing today?", "Why is my biggest holding moving?", "Is ASML a good buy now?",
    "What earnings and events are coming this week?", "How is the market?"];

  // tiny, safe markdown: escape first, then **bold**, *italic*, [text](link), "- " bullets
  function md(text) {
    const td = T();
    const link = (label, url) => /^(https?:\/\/|#\/)/.test(url) ? `<a href="${url}"${url.startsWith("#") ? "" : ' target="_blank" rel="noopener noreferrer"'}>${label}</a>` : label;
    const inline = (s) => td.esc(s)
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, l, u) => link(l, u.replace(/&amp;/g, "&").replace(/"/g, "%22")))
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>").replace(/`([^`]+)`/g, "<code>$1</code>");
    const out = [];
    let list = null;
    for (const raw of String(text || "").split("\n")) {
      const line = raw.trimEnd();
      const m = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
      if (m) { (list = list || []).push(`<li>${inline(m[1])}</li>`); continue; }
      if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; }
      const h = line.match(/^#{1,4}\s+(.*)$/);
      if (h) out.push(`<p><b>${inline(h[1])}</b></p>`);
      else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    }
    if (list) out.push(`<ul>${list.join("")}</ul>`);
    return out.join("");
  }

  function build() {
    if ($("#aiBtn")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <button type="button" class="ai-fab" id="aiBtn" aria-label="Open the assistant" aria-haspopup="dialog"><i data-lucide="message-circle"></i><span>Ask</span></button>
      <section class="ai-drawer" id="aiDrawer" role="dialog" aria-modal="false" aria-labelledby="aiTitle" hidden>
        <header class="ai-head"><h2 id="aiTitle"><i data-lucide="sparkles"></i>Assistant</h2><span class="ai-engine" id="aiEngine"></span>
          <button type="button" class="rf" id="aiNew" title="New conversation" aria-label="New conversation"><i data-lucide="square-pen"></i></button>
          <button type="button" class="rf" id="aiCfgBtn" title="Settings" aria-label="Assistant settings"><i data-lucide="settings"></i></button>
          <button type="button" class="rf" id="aiClose" aria-label="Close the assistant"><i data-lucide="x"></i></button></header>
        <div class="ai-cfg" id="aiCfg" hidden></div>
        <div class="ai-log" id="aiLog" aria-live="polite"></div>
        <form class="ai-form" id="aiForm" autocomplete="off">
          <textarea id="aiIn" rows="1" placeholder="Ask about your stocks…" aria-label="Your question"></textarea>
          <button class="btn primary" type="submit" id="aiSend" aria-label="Send"><i data-lucide="send"></i></button>
        </form>
      </section>`);
    $("#aiBtn").addEventListener("click", open);
    $("#aiClose").addEventListener("click", close);
    $("#aiNew").addEventListener("click", () => { chatId = null; log.length = 0; paint(); $("#aiIn").focus(); });
    $("#aiCfgBtn").addEventListener("click", () => { const c = $("#aiCfg"); c.hidden = !c.hidden; if (!c.hidden) settings(); });
    $("#aiForm").addEventListener("submit", (e) => { e.preventDefault(); send($("#aiIn").value); });
    const ta = $("#aiIn");
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(ta.value); } });
    ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(140, ta.scrollHeight) + "px"; });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#aiDrawer").hidden) close(); });
    if (window.lucide) window.lucide.createIcons();
  }

  async function loadStatus() {
    try { status = await T().api("/api/ai/status"); } catch (e) { status = { provider: "builtin" }; }
    const name = { builtin: "Built-in · free", ollama: "Ollama · " + (status.ollamaModel || ""), claude: (status.models || {})[status.model] ? status.models[status.model].split(" (")[0] : "Claude" }[status.provider] || "";
    $("#aiEngine").textContent = name;
  }

  async function open() {
    $("#aiDrawer").hidden = false;
    document.body.classList.add("ai-open");
    $("#aiBtn").setAttribute("aria-expanded", "true");
    if (!status) await loadStatus();
    paint();
    setTimeout(() => $("#aiIn").focus(), 50);
  }
  function close() {
    $("#aiDrawer").hidden = true;
    document.body.classList.remove("ai-open");
    $("#aiBtn").setAttribute("aria-expanded", "false");
    $("#aiBtn").focus();
  }

  function paint() {
    const td = T(), el = $("#aiLog");
    if (!log.length) {
      const builtin = !status || status.provider === "builtin";
      el.innerHTML = `<div class="ai-hello"><p><b>Ask me about your stocks.</b> I read your portfolio, live prices, news, the calendar and the dashboard's scores before answering. I can't place orders.</p>
        ${builtin ? `<p class="muted">Free built-in mode: I understand common questions like the ones below. For any question in your own words, connect a free local AI (Ollama) or Claude in ⚙ settings.</p>` : ""}
        <div class="ai-sugg">${SUGGEST.map((s) => `<button type="button" class="chip-btn" data-q="${td.esc(s)}">${td.esc(s)}</button>`).join("")}</div></div>`;
      el.querySelectorAll("[data-q]").forEach((b) => b.addEventListener("click", () => send(b.dataset.q)));
      return;
    }
    el.innerHTML = log.map((m) => m.who === "me" ? `<div class="ai-msg me">${td.esc(m.text)}</div>`
      : `<div class="ai-msg bot${m.error ? " err" : ""}">${m.pending ? `<span class="ai-dots" aria-label="Thinking"><i></i><i></i><i></i></span><span class="muted"> Checking your data…</span>` : md(m.text)}
        ${m.sources && m.sources.length ? `<div class="ai-src">Sources: ${m.sources.filter((s) => /^https?:\/\//.test(s.url || "")).map((s, i) => `<a href="${td.esc(s.url)}" target="_blank" rel="noopener noreferrer">${td.esc(s.title || "link " + (i + 1))}</a>`).join(" · ")}</div>` : ""}
        ${m.used && m.used.length ? `<div class="ai-used">Checked: ${m.used.map(td.esc).join(" · ")}${m.engine ? " — " + td.esc(m.engine) : ""}</div>` : ""}</div>`).join("");
    el.scrollTop = el.scrollHeight;
  }

  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    const td = T();
    busy = true; $("#aiSend").disabled = true;
    $("#aiIn").value = ""; $("#aiIn").style.height = "auto";
    log.push({ who: "me", text }, { who: "bot", pending: true });
    paint();
    const sym = (location.hash.match(/^#\/stock\/([^/?]+)/) || [])[1];
    try {
      const r = await td.post("/api/ai/chat", { message: text, chat: chatId, manual: td.store.get("manual", []),
        symbol: sym ? decodeURIComponent(sym) : "", ccy: (td.state.t212 && td.state.t212.currency) || (td.state.revolut && td.state.revolut.currency) || td.settings().ccy || "" });
      chatId = r.chat || null;
      log[log.length - 1] = { who: "bot", text: r.text, used: r.used, sources: r.sources, engine: r.engine };
    } catch (e) {
      log[log.length - 1] = { who: "bot", text: e.message, error: true };
    }
    busy = false; $("#aiSend").disabled = false;
    paint();
  }

  async function settings() {
    const td = T(), el = $("#aiCfg");
    await loadStatus();
    const s = status;
    el.innerHTML = `<form id="aiCfgF" class="form">
        <fieldset class="ai-prov"><legend>Engine</legend>
          <label><input type="radio" name="p" value="builtin" ${s.provider === "builtin" ? "checked" : ""}> <b>Built-in</b> · free, fixed rules, common questions only</label>
          <label><input type="radio" name="p" value="ollama" ${s.provider === "ollama" ? "checked" : ""}> <b>Ollama</b> · free AI that runs on your PC</label>
          <label><input type="radio" name="p" value="claude" ${s.provider === "claude" ? "checked" : ""}> <b>Claude</b> · best answers and web search, paid per question</label></fieldset>
        <div data-for="ollama" ${s.provider === "ollama" ? "" : "hidden"}>
          <p class="muted">Install Ollama from <b>ollama.com</b>, then in a Command Prompt run <code>ollama pull ${td.esc(s.ollamaModel || "qwen3:8b")}</code> once (about 5 GB). Keep Ollama open while you chat. Needs a PC with 16 GB of memory; no web search.</p>
          <label class="field">Model<input name="om" value="${td.esc(s.ollamaModel || "qwen3:8b")}" spellcheck="false"></label></div>
        <div data-for="claude" ${s.provider === "claude" ? "" : "hidden"}>
          <p class="muted">Create a key at <b>console.anthropic.com</b> → API keys, and add a little credit (this is separate from a Claude app subscription). A typical question costs about €0.02–0.10 with Opus, less with Sonnet or Haiku.</p>
          <label class="field">API key ${s.hasKey ? `<span class="pill live">saved</span>` : ""}<input name="key" type="password" autocomplete="off" spellcheck="false" placeholder="${s.hasKey ? "•••••• (leave empty to keep)" : "sk-ant-…"}"></label>
          <label class="field">Model<select name="model">${Object.entries(s.models || {}).map(([k, v]) => `<option value="${td.esc(k)}" ${k === s.model ? "selected" : ""}>${td.esc(v)}</option>`).join("")}</select></label>
          ${s.hasKey ? `<button type="button" class="btn sm danger" id="aiForget">Remove the key</button>` : ""}</div>
        <button class="btn primary" type="submit">Save</button>
        <p class="muted" style="font-size:12px;margin:0">Settings and the key are kept only on your PC (dashboard/.ai.json). Questions you send to Claude go to Anthropic with the data needed to answer them; Ollama and Built-in stay on your PC.</p>
        <p class="error" id="aiCfgErr" role="alert"></p></form>`;
    const f = $("#aiCfgF", el);
    const sync = () => { const p = f.p.value; el.querySelectorAll("[data-for]").forEach((d) => (d.hidden = d.dataset.for !== p)); };
    f.querySelectorAll("input[name=p]").forEach((r) => r.addEventListener("change", sync));
    const forget = $("#aiForget", el);
    if (forget) forget.addEventListener("click", async () => {
      try { await td.post("/api/ai/config", { key: "", provider: "builtin" }); td.toast("Key removed"); settings(); loadStatus(); } catch (e) { $("#aiCfgErr").textContent = e.message; }
    });
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { provider: f.p.value, ollamaModel: f.om.value, model: f.model.value };
      if (f.key.value.trim()) body.key = f.key.value.trim();
      try {
        await td.post("/api/ai/config", body);
        td.toast("Assistant settings saved"); chatId = null;
        el.hidden = true; await loadStatus(); paint();
      } catch (err) { $("#aiCfgErr").textContent = err.message; }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build); else build();
  window.Assistant = { open, md };
})();
