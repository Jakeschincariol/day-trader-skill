/* Growth & Cash page: revenue growth (across) against free cash flow margin (up) for a group of companies,
   split into four boxes at the group's middle values, with plain suggestions and a table. Uses window.TD helpers. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  const Q = {
    king: { label: "Growth + cash", color: "#3fcf3f", text: "grow faster than the group and keep more cash: the healthiest businesses here" },
    cash: { label: "Cash machine", color: "#4a95ee", text: "slower growth but strong cash: steadier, often pay dividends or buy back shares" },
    growth: { label: "Growing, thin cash", color: "#fab219", text: "growth is not turning into much cash yet: they still have to prove it" },
    weak: { label: "Slow, thin cash", color: "#9a9891", text: "slower growth and less cash than the rest of the group: the weakest here, careful with dips" },
    burn: { label: "Burning cash", color: "#ff7a7a", text: "spend more cash than they bring in: speculative, they may need to raise money" },
  };
  const ORDER = ["king", "cash", "growth", "weak", "burn"];
  // short names for listings whose ticker is a number code
  const LABEL = { "000660.KS": "SK hynix", "005930.KS": "Samsung", "6857.T": "Advantest", "8035.T": "Tokyo Electron", "ASM.AS": "ASM Intl" };
  const short = (sym) => LABEL[sym] || sym.replace(/\.(KS|T|AS|DE|L|PA|MI|SW)$/, "");
  let chart = null;

  function suggestions(d, owned) {
    const td = T();
    const ok = d.rows.filter((r) => r.quadrant);
    if (!ok.length) return "";
    const by = (k) => ok.filter((r) => r.quadrant === k);
    const names = (arr) => arr.map((r) => `<a href="#/stock/${encodeURIComponent(r.symbol)}">${td.esc(short(r.symbol))}</a>`).join(", ");
    // best balance: rank on growth and on margin, add the two ranks
    const rank = (key) => Object.fromEntries(ok.slice().sort((a, b) => b[key] - a[key]).map((r, i) => [r.symbol, i]));
    const rg = rank("growth"), rm = rank("margin");
    const best = ok.filter((r) => r.margin > 0).sort((a, b) => rg[a.symbol] + rm[a.symbol] - (rg[b.symbol] + rm[b.symbol])).slice(0, 3);
    const lines = ORDER.filter((k) => by(k).length).map((k) => `<li><span class="gc-dot" style="background:${Q[k].color}"></span><span><b>${Q[k].label}:</b> ${names(by(k))} ${Q[k].text}.</span></li>`);
    let mine = "";
    if (d.group === "mine") {
      const burn = by("burn"), weak = by("weak"), king = by("king");
      mine = `<p class="gc-mine">Of your ${ok.length} stocks with figures, <b>${king.length}</b> ${king.length === 1 ? "is" : "are"} in the top-right box${burn.length ? `, and <b>${burn.length}</b> burn${burn.length === 1 ? "s" : ""} cash (${names(burn)}): keep those small` : ""}${weak.length ? `. ${names(weak)} ${weak.length === 1 ? "is" : "are"} the weakest of your list` : ""}.</p>`;
    } else if (owned.size) {
      const own = ok.filter((r) => owned.has(r.symbol));
      if (own.length) mine = `<p class="gc-mine">You own here: ${own.map((r) => `${td.esc(short(r.symbol))} (${Q[r.quadrant].label.toLowerCase()})`).join(", ")}.</p>`;
    }
    return `${mine}<p class="gc-best">Best balance of growth and cash in this group: <b>${names(best) || "–"}</b>.</p><ul class="gc-list">${lines.join("")}</ul>
      <p class="muted" style="font-size:12.5px;margin:8px 0 0">The boxes are split at this group's middle values (${td.pct(d.medianGrowth, 0)} growth, ${d.medianMargin}% cash margin), so "slow" means slower than the others here. In a fast group (like memory today) even the bottom-left can be growing well; in a slow one even the top-right can be modest. Check the numbers in the table.</p>`;
  }

  function draw(box, d, owned) {
    const EC = window.echarts;
    if (!EC) { box.innerHTML = `<p class="muted">The chart library did not load.</p>`; return; }
    const ok = d.rows.filter((r) => r.quadrant);
    const xs = ok.map((r) => r.growth), ys = ok.map((r) => r.margin);
    const pad = (a, b) => (b - a) * 0.08 + 2;
    let x0 = Math.min(0, ...xs), x1 = Math.max(...xs), y0 = Math.min(0, ...ys), y1 = Math.max(...ys);
    // very far points (a 500% grower) squash the rest: clamp the axes and draw those points at the edge
    const sx = xs.slice().sort((a, b) => a - b), sy = ys.slice().sort((a, b) => a - b);
    const pick = (arr, p) => arr[Math.min(arr.length - 1, Math.floor(p * (arr.length - 1)))];
    if (xs.length > 5) { x1 = Math.min(x1, pick(sx, 0.9) * 1.6 + 20); x0 = Math.max(x0, pick(sx, 0.1) * 1.6 - 20); }
    if (ys.length > 5) { y1 = Math.min(y1, Math.max(pick(sy, 0.9) * 1.5 + 10, 40)); y0 = Math.max(y0, Math.min(pick(sy, 0.1) * 1.5 - 10, -20)); }
    x0 -= pad(x0, x1); x1 += pad(x0, x1); y0 -= pad(y0, y1); y1 += pad(y0, y1);
    const step = (a, b) => ((b - a) > 150 ? 50 : (b - a) > 60 ? 20 : 10);
    const sxp = step(x0, x1), syp = step(y0, y1);
    x0 = Math.floor(x0 / sxp) * sxp; x1 = Math.ceil(x1 / sxp) * sxp; y0 = Math.floor(y0 / syp) * syp; y1 = Math.ceil(y1 / syp) * syp;
    const clampv = (v, a, b) => Math.max(a, Math.min(b, v));
    const data = ok.map((r) => {
      const cx = clampv(r.growth, x0, x1), cy = clampv(r.margin, y0, y1), cut = cx !== r.growth || cy !== r.margin;
      const mine = owned.has(r.symbol);
      return { value: [cx, cy], r, cut, symbol: cut ? "triangle" : "circle", symbolSize: mine ? 14 : 9,
        itemStyle: { color: Q[r.quadrant].color, borderColor: mine ? "#f0efec" : "transparent", borderWidth: mine ? 2 : 0 },
        label: { show: true, formatter: short(r.symbol) + (cut ? " ›" : ""), position: "top", color: mine ? "#f0efec" : "#c3c2b7", fontSize: 11, fontWeight: mine ? 700 : 500 } };
    });
    const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    if (chart && chart.getDom() !== box) { chart.dispose(); chart = null; }
    if (!chart) { chart = EC.init(box); new ResizeObserver(() => chart && chart.resize()).observe(box); }
    chart.setOption({
      backgroundColor: "transparent", animation: false, textStyle: { fontFamily: "Inter", color: css("--text-secondary") },
      grid: { left: 56, right: 20, top: 20, bottom: 46 },
      tooltip: { trigger: "item", backgroundColor: "#2c2c2a", borderColor: "rgba(255,255,255,.1)", textStyle: { color: "#f0efec" },
        formatter: (p) => { const r = p.data.r; return `<b>${T().esc(r.symbol)}</b> ${T().esc(r.name || "")}<br>Revenue growth <b>${T().pct(r.growth, 1)}</b> <span style="opacity:.7">(${T().esc(r.basis || "")})</span><br>Free cash flow margin <b>${r.margin}%</b> <span style="opacity:.7">(${T().esc(r.marginBasis || "")})</span><br>${Q[r.quadrant].label}`; } },
      xAxis: { type: "value", min: x0, max: x1, name: "Revenue growth (%)", nameLocation: "middle", nameGap: 28, axisLabel: { color: css("--text-muted"), formatter: (v) => Math.round(v) + "%" }, splitLine: { lineStyle: { color: css("--grid") } }, axisLine: { lineStyle: { color: css("--axis") } } },
      yAxis: { type: "value", min: y0, max: y1, name: "Free cash flow margin (%)", nameLocation: "middle", nameGap: 40, axisLabel: { color: css("--text-muted"), formatter: (v) => Math.round(v) + "%" }, splitLine: { lineStyle: { color: css("--grid") } }, axisLine: { lineStyle: { color: css("--axis") } } },
      series: [{
        type: "scatter", data,
        markArea: { silent: true, itemStyle: { color: "rgba(12,163,12,.08)" }, data: [[{ coord: [d.medianGrowth, d.medianMargin] }, { coord: [x1, y1] }]] },
        markLine: { silent: true, symbol: "none", lineStyle: { color: "rgba(240,239,236,.35)", type: "dashed" }, label: { show: false },
          data: [{ xAxis: d.medianGrowth }, { yAxis: d.medianMargin }, { yAxis: 0, lineStyle: { color: "rgba(255,122,122,.45)", type: "solid" } }] },
        labelLayout: { hideOverlap: true },
      }],
    }, true);
  }

  async function page(view, params) {
    const td = T();
    let group = (params && params.get("g")) || td.store.get("gcGroup", "ai-chips");
    view.innerHTML = `<div class="page-title"><h1>Growth &amp; Cash</h1><p class="sub">Which companies grow fast <b>and</b> turn their sales into real cash? Sales growth runs across, free cash flow margin (cash left after running the business and investing, per 100 of sales) runs up. Top right is the strongest.</p></div>
      <div class="seg gc-groups" id="gcGroups" role="group" aria-label="Group"><button type="button" data-g="mine">My stocks</button></div>
      <div class="card" style="margin-top:12px"><div class="card-head" style="flex-wrap:wrap"><h2 id="gcTitle"><i data-lucide="scatter-chart"></i>…</h2>${td.rf("gc")}</div>
        <div class="gc-chart" id="gcChart">${td.skeleton(10)}</div>
        <div class="legend gc-legend">${ORDER.map((k) => `<span><i style="background:${Q[k].color};border-radius:50%;width:10px;height:10px"></i>${Q[k].label}</span>`).join("")}<span><i style="background:#f0efec;border-radius:50%;width:10px;height:10px"></i>white ring: you own it</span><span>▲ ›: off the chart, real value in the table</span></div></div>
      <div class="grid gc-two" style="margin-top:16px;align-items:start">
        <div class="card"><div class="card-head"><h2><i data-lucide="lightbulb"></i>What it suggests</h2></div><div id="gcSug">${td.skeleton(5)}</div></div>
        <div class="card"><div class="card-head"><h2><i data-lucide="table"></i>The numbers</h2></div><div id="gcTbl">${td.skeleton(8)}</div></div>
      </div>
      <p class="muted" style="font-size:12px;margin-top:12px">Figures: Yahoo Finance company reports, refreshed daily (they change when companies report each quarter). Growth compares the latest quarters with the same quarters a year earlier; cash margin uses the last 12 months. Banks and insurers are left out: free cash flow means little for them. Not advice.</p>`;
    const owned = new Set();
    const load = async (fresh) => {
      $$("#gcGroups button").forEach((b) => b.classList.toggle("on", b.dataset.g === group));
      if (chart) { chart.dispose(); chart = null; } // its canvas lives inside #gcChart, which is about to be replaced
      $("#gcChart").innerHTML = td.skeleton(10); $("#gcSug").innerHTML = td.skeleton(5); $("#gcTbl").innerHTML = td.skeleton(8);
      await td.getT212().catch(() => null);
      owned.clear();
      td.brokerPositions().forEach((p) => owned.add(p.symbol)); td.store.get("manual", []).forEach((m) => owned.add(m.symbol));
      let url = `/api/growthcash?group=${encodeURIComponent(group)}`;
      if (group === "mine") {
        const syms = [...new Set([...owned, ...td.watchlist()])];
        if (!syms.length) { $("#gcChart").innerHTML = `<p class="empty">Link your broker or add stocks to your watchlist first.</p>`; $("#gcSug").innerHTML = ""; $("#gcTbl").innerHTML = ""; return; }
        url = `/api/growthcash?symbols=${encodeURIComponent(syms.join(","))}`;
      }
      let d;
      try { d = await td.api(url + (fresh ? "&fresh=1" : "")); }
      catch (e) { $("#gcChart").innerHTML = `<p class="error">${td.esc(e.message)}</p>`; return; }
      if (!$("#gcChart")) return;
      if ($$("#gcGroups button").length === 1) {
        $("#gcGroups").insertAdjacentHTML("beforeend", d.groups.map((g) => `<button type="button" data-g="${td.esc(g.id)}">${td.esc(g.name)}</button>`).join(""));
        $$("#gcGroups button").forEach((b) => b.classList.toggle("on", b.dataset.g === group));
      }
      $("#gcTitle").innerHTML = `<i data-lucide="scatter-chart"></i>${td.esc(d.name)}`;
      const ok = d.rows.filter((r) => r.quadrant);
      if (ok.length < 2) { $("#gcChart").innerHTML = `<p class="empty">Not enough companies with figures in this group.</p>`; }
      else { $("#gcChart").innerHTML = ""; draw($("#gcChart"), d, owned); }
      $("#gcSug").innerHTML = suggestions(d, owned) || `<p class="muted">No suggestions without figures.</p>`;
      const rows = ok.slice().sort((a, b) => ORDER.indexOf(a.quadrant) - ORDER.indexOf(b.quadrant) || b.margin + b.growth / 2 - (a.margin + a.growth / 2));
      const skipped = d.rows.filter((r) => !r.quadrant);
      $("#gcTbl").innerHTML = `<div class="table-wrap"><table class="gc-tbl"><thead><tr><th>Company</th><th class="r">Sales growth</th><th class="r">Cash margin</th><th>Box</th></tr></thead><tbody>
        ${rows.map((r) => `<tr><td><a class="sym" href="#/stock/${encodeURIComponent(r.symbol)}">${td.esc(short(r.symbol))}</a>${owned.has(r.symbol) ? ` <em class="mo-own">owned</em>` : ""}<small>${td.esc(r.name || "")}</small></td>
          <td class="r num ${td.cls(r.growth)}" title="${td.esc(r.basis || "")}">${td.pct(r.growth, 0)}</td><td class="r num ${r.margin < 0 ? "down" : ""}">${r.margin}%</td>
          <td><span class="gc-pill" style="color:${Q[r.quadrant].color}">${Q[r.quadrant].label}</span></td></tr>`).join("")}</tbody></table></div>
        ${skipped.length ? `<p class="muted" style="font-size:12.5px;margin:8px 0 0">No figures for ${skipped.map((r) => td.esc(r.symbol) + (r.note ? " (bank or insurer)" : "")).join(", ")}: funds, banks or very new listings.</p>` : ""}`;
    };
    $("#gcGroups").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b || b.dataset.g === group) return; group = b.dataset.g; td.store.set("gcGroup", group); history.replaceState(null, "", "#/growthcash?g=" + encodeURIComponent(group)); load(); });
    td.RF().gc = () => load(true);
    await load();
    return () => { if (chart) { chart.dispose(); chart = null; } };
  }

  window.GrowthCash = { page, Q };
})();
