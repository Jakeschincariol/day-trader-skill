/* Insights without an AI key: morning briefing, news impact badges, economic calendar,
   holdings correlation heatmap, Revolut statement import, and the Ctrl+K search shortcut. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  // ------------------------------------------------------------ news badges
  const MOOD = { bullish: ["up", "Bullish"], bearish: ["down", "Bearish"] };
  function newsBadges(n) {
    const m = MOOD[n.mood];
    return (m ? `<span class="nb nb-${m[0]}" title="Tone of the headline (keyword rules)">${m[1]}</span>` : "") +
      (n.impact === "high" ? `<span class="nb nb-hi" title="Likely to move the price">High impact</span>` : n.impact === "medium" ? `<span class="nb nb-md">Medium</span>` : "");
  }
  // ticker chips inside a news link open the stock page instead of the article
  document.addEventListener("click", (e) => {
    const c = e.target.closest && e.target.closest("[data-go]");
    if (!c) return;
    e.preventDefault(); e.stopPropagation();
    location.hash = "#/stock/" + encodeURIComponent(c.dataset.go);
  }, true);

  // ------------------------------------------------------------ morning briefing
  const ICON = { market: "activity", portfolio: "wallet", movers: "zap", news: "newspaper", earnings: "calendar-clock", event: "landmark" };
  function greeting() {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  }
  async function briefing(el, symbols, weights) {
    const td = T();
    el.innerHTML = td.skeleton(4);
    const w = Object.entries(weights || {}).map(([k, v]) => k + ":" + Math.round(v)).join(",");
    let b;
    try { b = await td.api("/api/briefing?symbols=" + encodeURIComponent(symbols.slice(0, 40).join(",")) + "&w=" + encodeURIComponent(w)); }
    catch (e) { el.innerHTML = `<p class="error">${td.esc(e.message)}</p>`; return; }
    if (!el.isConnected) return;
    const chips = (l) => (l.symbols || []).map((s) => `<button type="button" class="tag tag-go" data-go="${td.esc(s)}">${td.esc(s)}</button>`).join("");
    el.innerHTML = `<p class="brief-hi">${greeting()}. Here's what matters ${symbols.length ? "for your stocks" : "today"}:</p>
      <ul class="brief">${b.lines.map((l) => `<li class="b-${l.kind}"><span class="b-ico ${l.tone}"><i data-lucide="${ICON[l.kind] || "dot"}"></i></span>
        <div>${l.link ? `<a href="${/^https?:/.test(l.link) ? td.esc(l.link) : "#"}" target="_blank" rel="noopener noreferrer">${td.esc(l.text)}</a>` : td.esc(l.text)}
        ${l.kind === "news" ? `<span class="b-meta">${newsBadges(l)} ${td.esc(l.publisher || "")}</span>` : ""} ${chips(l)}</div></li>`).join("")}</ul>
      <p class="muted" style="font-size:12px;margin:6px 0 0">Built from live prices, headlines and the economic calendar with fixed rules (no AI service). Not advice.</p>`;
  }

  // ------------------------------------------------------------ economic calendar
  const FLAG = { USD: "🇺🇸", EUR: "🇪🇺", GBP: "🇬🇧", JPY: "🇯🇵", CNY: "🇨🇳" };
  async function calendar(el, symbols) {
    const td = T();
    el.innerHTML = td.skeleton(8);
    let c;
    try { c = await td.api("/api/calendar?symbols=" + encodeURIComponent(symbols.slice(0, 60).join(","))); }
    catch (e) { el.innerHTML = `<p class="error">${td.esc(e.message)}</p>`; return; }
    if (!el.isConnected) return;
    const now = Date.now() / 1000;
    const days = {};
    for (const e of c.econ) {
      const d = new Date(e.ts * 1000);
      const k = d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" });
      (days[k] = days[k] || []).push(e);
    }
    el.innerHTML = `<div class="card"><div class="card-head"><h2><i data-lucide="calendar-clock"></i>Earnings of your stocks</h2></div>
        ${c.earnings.length ? `<ul class="cal-earn">${c.earnings.map((e) => `<li><button type="button" class="tag tag-go" data-go="${td.esc(e.symbol)}">${td.logo(e.symbol, 18)} ${td.esc(e.symbol)}</button>
          <span>${td.esc(e.date)}</span><b class="${e.days <= 7 ? "warn" : ""}">${e.days === 0 ? "today" : e.days === 1 ? "tomorrow" : "in " + e.days + " days"}</b></li>`).join("")}</ul>`
          : `<p class="muted">No earnings dates in the next 45 days for your US-listed stocks.</p>`}
        <p class="muted" style="font-size:12px;margin:8px 0 0">Prices often jump 5–20% on earnings day. Many long-term investors avoid adding just before.</p></div>
      <div class="card" style="margin-top:16px"><div class="card-head"><h2><i data-lucide="landmark"></i>Economic calendar</h2><span class="muted" style="font-size:12px">this week and next · your local time</span></div>
        ${c.error ? `<p class="error">${td.esc(c.error)}</p>` : ""}
        ${Object.entries(days).map(([d, evs]) => `<h3 class="cal-day">${td.esc(d)}</h3><ul class="cal-list">${evs.map((e) => `<li class="${e.ts < now ? "past" : ""}">
          <span class="cal-t num">${new Date(e.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
          <span class="cal-imp ${e.impact}" title="${e.impact} impact"></span>
          <div><b>${FLAG[e.country] || ""} ${td.esc(e.country)} · ${td.esc(e.title)}</b>
            <span class="cal-n">${e.actual ? `Actual <b>${td.esc(e.actual)}</b> · ` : ""}${e.forecast ? "Forecast " + td.esc(e.forecast) : ""}${e.previous ? " · Previous " + td.esc(e.previous) : ""}</span>
            ${e.why ? `<span class="cal-why">${td.esc(e.why)}</span>` : ""}</div></li>`).join("")}</ul>`).join("") || `<p class="muted">No major events found.</p>`}
        <p class="muted" style="font-size:12px;margin:8px 0 0">Red = high impact, orange = medium. Source: Forex Factory weekly calendar.</p></div>`;
  }

  // ------------------------------------------------------------ correlation heatmap
  let heat = null;
  async function correlation(el, symbols) {
    const td = T();
    if (symbols.length < 2) { el.innerHTML = `<p class="muted">Add at least two holdings to see how they move together.</p>`; return; }
    el.innerHTML = td.skeleton(6);
    let c;
    try { c = await td.api("/api/correlation?symbols=" + encodeURIComponent(symbols.slice(0, 20).join(","))); }
    catch (e) { el.innerHTML = `<p class="error">${td.esc(e.message)}</p>`; return; }
    if (!el.isConnected) return;
    if (!c.matrix.length) { el.innerHTML = `<p class="muted">Not enough price history yet.</p>`; return; }
    const avg = c.avg;
    const verdict = avg >= 0.6 ? ["down", "Most of your holdings move together: one bad day for the sector hits almost everything at once."]
      : avg >= 0.4 ? ["warn", "Your holdings are fairly linked: diversification helps, but less than the number of stocks suggests."]
        : ["up", "Your holdings move fairly independently: good diversification."];
    const n = c.symbols.length;
    el.innerHTML = `<div class="corr-sum"><div class="perf-tile"><div class="k">Average link</div><div class="v num ${verdict[0]}">${avg != null ? avg.toFixed(2) : "–"}</div><div class="b">0 = independent · 1 = move together</div></div>
        <p class="${verdict[0] === "warn" ? "" : verdict[0]}" style="margin:0;flex:1;min-width:200px">${verdict[1]}</p></div>
      <div id="corrHeat" style="height:${Math.max(260, Math.min(560, 26 * n + 80))}px"></div>
      <div class="grid g2" style="gap:12px;margin-top:8px">
        <div><h3 class="proj-h">Move most alike</h3><ul class="corr-pairs">${c.pairs.map((p) => `<li><span>${td.esc(p.a)} + ${td.esc(p.b)}</span><b class="num">${p.corr.toFixed(2)}</b></li>`).join("")}</ul></div>
        <div><h3 class="proj-h">Best diversifiers</h3><ul class="corr-pairs">${(c.low || []).map((p) => `<li><span>${td.esc(p.a)} + ${td.esc(p.b)}</span><b class="num">${p.corr.toFixed(2)}</b></li>`).join("")}</ul></div>
      </div>
      <p class="muted" style="font-size:12px;margin:8px 0 0">Correlation of weekly returns over the last ${c.weeks ? Math.round(c.weeks / 52 * 10) / 10 + " years" : "shared history"}. Above 0.7 two holdings behave almost like one; below 0.3 they really spread your risk.</p>`;
    const EC = window.echarts, box = $("#corrHeat", el);
    if (!EC || !box) return;
    if (heat) { heat.dispose(); heat = null; }
    heat = EC.init(box);
    new ResizeObserver(() => heat && heat.resize()).observe(box);
    const data = [];
    c.matrix.forEach((row, i) => row.forEach((v, j) => data.push([j, i, v == null ? "-" : v])));
    heat.setOption({
      backgroundColor: "transparent", animation: false, textStyle: { fontFamily: "Inter", color: css("--text-secondary") },
      grid: { left: 64, right: 10, top: 10, bottom: 64 },
      tooltip: { backgroundColor: "#2c2c2a", borderColor: "rgba(255,255,255,.1)", textStyle: { color: "#f0efec" },
        formatter: (p) => `${c.symbols[p.value[1]]} + ${c.symbols[p.value[0]]}: <b>${p.value[2] === "-" ? "n/a" : (+p.value[2]).toFixed(2)}</b>` },
      xAxis: { type: "category", data: c.symbols, axisLabel: { color: css("--text-muted"), rotate: 60, fontSize: 11 }, axisLine: { show: false }, splitArea: { show: false } },
      yAxis: { type: "category", data: c.symbols, inverse: true, axisLabel: { color: css("--text-muted"), fontSize: 11 }, axisLine: { show: false } },
      visualMap: { show: false, min: -0.2, max: 1, inRange: { color: ["#1d2733", "#1f4f8a", "#3987e5", "#9cc8ff"] } },
      series: [{ type: "heatmap", data, label: { show: n <= 12, fontSize: 10, color: "#f0efec", textBorderColor: "rgba(0,0,0,.6)", textBorderWidth: 2, formatter: (p) => p.value[2] === "-" ? "" : (+p.value[2]).toFixed(1) },
        itemStyle: { borderColor: css("--surface-1"), borderWidth: 1 } }],
    }, true);
  }

  // ------------------------------------------------------------ Revolut (statement import)
  function revolutCard(el, onChange) {
    const td = T(), r = td.state.revolut;
    const ccy0 = (r && r.currency) || td.settings().ccy || "EUR";
    const imp = `<label class="btn primary file-btn"><i data-lucide="upload"></i> ${r && r.linked ? "Import a newer statement" : "Choose the statement file"}<input type="file" id="revFile" accept=".csv,.xlsx,.xls,.txt,text/csv"></label>
      <label class="field" style="max-width:200px">Account currency<select id="revCcy">${["EUR", "USD", "GBP", "CHF", "PLN", "RON"].map((c) => `<option ${c === ccy0 ? "selected" : ""}>${c}</option>`).join("")}</select></label>`;
    if (r && r.linked) {
      const t = r.totals || {};
      el.innerHTML = `<div class="card-head"><h2>Revolut</h2><span class="pill live">Imported</span></div>
        <p class="sec" style="margin-top:0">${r.positions.length} holdings from <b>${td.esc(r.file || "statement")}</b>, imported ${new Date(r.imported * 1000).toLocaleDateString()}. Prices are live; shares are as of the statement.</p>
        <div class="ret-grid" style="margin-bottom:10px">
          <div class="perf-tile"><div class="k">Value</div><div class="v num">${td.money(t.value, r.currency)}</div></div>
          <div class="perf-tile"><div class="k">Gain so far</div><div class="v num ${td.cls(r.ppl)}">${r.ppl >= 0 ? "+" : ""}${td.money(r.ppl, r.currency)}</div></div>
          ${t.realized ? `<div class="perf-tile"><div class="k">Gain from sales</div><div class="v num ${td.cls(t.realized)}">${td.money(t.realized, r.currency)}</div></div>` : ""}
          ${t.dividends ? `<div class="perf-tile"><div class="k">Dividends</div><div class="v num up">${td.money(t.dividends, r.currency)}</div></div>` : ""}</div>
        ${(r.warnings || []).length ? `<p class="muted" style="font-size:12px">${r.warnings.map(td.esc).join(" · ")}</p>` : ""}
        <div class="form-row" style="align-items:end">${imp}<button class="btn danger" type="button" id="revDel">Remove</button></div>
        <p class="error" id="revErr" role="alert"></p>`;
    } else {
      const t212On = td.state.t212Status && td.state.t212Status.linked;
      const body = `<h2>Use Revolut?</h2>
        <p class="sec" style="margin-top:0">Revolut has no API for personal investing accounts, so the dashboard reads your statement file instead.</p>
        <ol class="steps"><li>In the Revolut app open <b>Invest</b> → <b>…</b> (More) → <b>Documents</b> → <b>Brokerage account</b> → <b>Account statement</b>.</li>
          <li>Choose <b>Excel</b> (not PDF) and the period <b>All time</b>, then send the file to this computer (email, OneDrive, AirDrop). Menu names can differ a little between app versions. On iPhone you can pick it straight from the Files app.</li>
          <li>Import it here. Re-import a new statement after you trade.</li></ol>
        <div class="form-row" style="align-items:end;margin-top:10px">${imp}</div>
        <p class="muted" style="font-size:12px;margin:0">The file stays on your computer (dashboard/.revolut.json). Works with any broker's CSV that has Symbol and Quantity columns.</p>
        <p class="error" id="revErr" role="alert"></p>`;
      // already on Trading 212: keep the Revolut help folded away
      el.innerHTML = t212On ? `<details class="fold-inline"><summary><b>Also use Revolut?</b> <span class="muted">import a statement</span></summary>${body.replace("<h2>Use Revolut?</h2>", "")}</details>` : body;
    }
    $("#revFile", el).addEventListener("change", (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 10 * 1024 * 1024) { $("#revErr", el).textContent = "That file is larger than 10 MB."; return; }
      const rd = new FileReader();
      rd.onload = async () => {
        $("#revErr", el).textContent = "";
        td.toast("Importing " + f.name + "…");
        try {
          const out = await td.post("/api/revolut/import", { data: rd.result, base64: true, name: f.name, currency: $("#revCcy", el).value });
          td.toast(`Imported ${out.trades} trades: ${out.positions} holdings`);
          td.state.revolut = await td.api("/api/revolut/portfolio").catch(() => null);
          onChange && onChange();
        } catch (err) { $("#revErr", el).textContent = err.message; }
      };
      rd.readAsDataURL(f);
    });
    const del = $("#revDel", el);
    if (del) del.addEventListener("click", async () => {
      if (!confirm("Remove the imported Revolut holdings from this dashboard?")) return;
      await td.post("/api/revolut/clear", {});
      td.state.revolut = null; td.toast("Revolut import removed"); onChange && onChange();
    });
  }

  // ------------------------------------------------------------ keyboard: Ctrl+K or / jumps to search
  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || "");
    if (((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") || (e.key === "/" && !typing)) {
      const i = document.getElementById("searchInput");
      if (i) { e.preventDefault(); i.focus(); i.select(); }
    }
  });

  window.Insights = { newsBadges, briefing, calendar, correlation, revolutCard };
})();
