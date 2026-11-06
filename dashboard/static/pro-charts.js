/* Pro visuals for Trader Dashboard: TradingView Lightweight Charts, Apache ECharts,
   Lucide icons and CountUp.js (all served locally from /vendor). Each piece falls
   back to the built-in charts if its library is missing. */
(function () {
  "use strict";
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const LW = window.LightweightCharts;
  const fmt = (x, d) => (x == null ? "–" : Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const vol = (v) => (v >= 1e9 ? (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(v));

  // ------------------------------------------------------------ icons: render every <i data-lucide> as it appears
  if (window.lucide) {
    let t = null;
    const draw = () => { t = null; try { window.lucide.createIcons({ attrs: { "aria-hidden": "true" } }); } catch (e) { /* ignore */ } };
    new MutationObserver(() => { if (!t) t = requestAnimationFrame(draw); }).observe(document.body, { childList: true, subtree: true });
    document.addEventListener("DOMContentLoaded", draw);
    draw();
  }

  // ------------------------------------------------------------ CountUp: <span data-count="123.4" data-fmt="money:EUR|pct|int|num:2">
  function countAll(root) {
    const CU = window.countUp && window.countUp.CountUp;
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    (root || document).querySelectorAll("[data-count]:not([data-counted])").forEach((el) => {
      el.setAttribute("data-counted", "1");
      const v = parseFloat(el.dataset.count);
      if (!isFinite(v) || !CU || reduce) return;
      const f = el.dataset.fmt || "num:2";
      const [kind, arg] = f.split(":");
      const formattingFn = (n) => {
        if (kind === "money") {
          try { return new Intl.NumberFormat(undefined, { style: "currency", currency: arg || "USD", maximumFractionDigits: 2 }).format(n).replace("US$", "$"); } catch (e) { return fmt(n, 2); }
        }
        if (kind === "pct") return (n > 0 ? "+" : "") + n.toFixed(arg ? +arg : 2) + "%";
        if (kind === "int") return Math.round(n).toLocaleString();
        return fmt(n, arg ? +arg : 2);
      };
      const final = el.textContent;
      const cu = new CU(el, v, { duration: 1.1, startVal: kind === "pct" ? 0 : v * 0.9, formattingFn, useEasing: true });
      if (!cu.error) cu.start(() => { el.textContent = final; });
    });
  }
  if (window.countUp) {
    let t = null;
    new MutationObserver(() => { if (!t) t = setTimeout(() => { t = null; countAll(document); }, 30); }).observe(document.body, { childList: true, subtree: true });
  }

  // ------------------------------------------------------------ price chart (TradingView Lightweight Charts)
  /**
   * Same inputs as TChart.PriceChart: series {t,o,h,l,c,v,sma20?,sma50?,sma200?,rsi?},
   * opts {bars, plan, forecast, target, intraday: "day"|"week", prevClose}.
   */
  function ProChart(box, s, opts) {
    if (!LW) return window.TChart.PriceChart(box, s, opts);
    const C = {
      up: css("--good"), down: css("--bad"), grid: css("--grid"), axis: css("--axis"), muted: css("--text-muted"),
      text: css("--text-secondary"), surface: css("--surface-1"), accent: css("--accent"), warn: css("--warning"),
      s20: css("--series-2"), s50: css("--series-1"), s200: css("--series-5"), rsi: css("--series-7"),
    };
    const intra = opts.intraday;
    const calm = !!opts.calm && !intra;
    const showRsi = !intra && s.rsi && !calm;
    box.classList.add("pro");
    box.setAttribute("role", "img");
    const narrow = box.clientWidth < 520;
    box.innerHTML = `<div class="lw-main"><div class="lw-legend"></div></div>${showRsi ? `<div class="lw-rsi"><span class="lw-tag">RSI 14</span></div>` : ""}`;
    const mainEl = box.querySelector(".lw-main"), legend = box.querySelector(".lw-legend");
    const off = new Date().getTimezoneOffset() * 60; // show intraday times in the viewer's time zone
    const dayStr = (ts) => new Date(ts * 1000).toISOString().slice(0, 10);
    const T = (ts) => (intra ? ts - off : dayStr(ts));
    const dec = s.c[s.c.length - 1] < 2 ? 4 : 2;
    const base = {
      autoSize: true,
      layout: { background: { type: "solid", color: "transparent" }, textColor: C.muted, fontFamily: css("--mono") || "monospace", fontSize: 11 },
      grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
      rightPriceScale: { borderColor: C.axis, minimumWidth: narrow ? 56 : 84 },
      timeScale: { borderColor: C.axis, timeVisible: !!intra, secondsVisible: false, rightOffset: 4 },
      crosshair: { mode: 0, vertLine: { color: "rgba(240,239,236,.35)", labelBackgroundColor: "#2c2c2a" }, horzLine: { color: "rgba(240,239,236,.35)", labelBackgroundColor: "#2c2c2a" } },
      localization: { priceFormatter: (p) => fmt(p, dec) },
    };
    const chart = LW.createChart(mainEl, base);
    const candles = calm
      ? chart.addAreaSeries({ lineColor: C.accent, topColor: "rgba(57,135,229,.22)", bottomColor: "rgba(57,135,229,0)", lineWidth: 2, priceLineVisible: true })
      : chart.addCandlestickSeries({ upColor: C.up, downColor: C.down, borderVisible: false, wickUpColor: C.up, wickDownColor: C.down, priceLineVisible: true });
    const n = s.c.length;
    const cdata = [], vdata = [];
    for (let i = 0; i < n; i++) {
      cdata.push({ time: T(s.t[i]), open: s.o[i], high: s.h[i], low: s.l[i], close: s.c[i] });
      vdata.push({ time: T(s.t[i]), value: s.v[i], color: s.c[i] >= s.o[i] ? "rgba(12,163,12,.35)" : "rgba(208,59,59,.35)" });
    }
    candles.setData(calm ? cdata.map((d) => ({ time: d.time, value: d.close })) : cdata);
    candles.priceScale().applyOptions({ scaleMargins: { top: calm ? 0.12 : 0.06, bottom: calm ? 0.04 : 0.2 } });
    if (!calm) {
      const volume = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "", lastValueVisible: false, priceLineVisible: false });
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
      volume.setData(vdata);
    }
    const lineOpts = (color, extra) => Object.assign({ color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }, extra || {});
    const lineData = (arr) => arr.map((v, i) => (v == null ? { time: T(s.t[i]) } : { time: T(s.t[i]), value: v }));
    if (s.sma200) chart.addLineSeries(lineOpts(C.s200)).setData(lineData(s.sma200));
    if (s.sma50 && !calm) chart.addLineSeries(lineOpts(C.s50)).setData(lineData(s.sma50));
    if (s.sma20 && !calm) chart.addLineSeries(lineOpts(C.s20)).setData(lineData(s.sma20));

    if (intra === "day" && opts.prevClose) candles.createPriceLine({ price: opts.prevClose, color: C.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "Prev close" });
    const p = !intra && opts.plan;
    if (p) {
      [["Entry", p.entry, C.accent], ["Stop", p.stop, C.down], ["Target 1", p.target1, C.up], ["Target 2", p.target2, C.up]].forEach(([title, price, color]) => {
        if (price != null) candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: !narrow, title: narrow ? "" : title });
      });
    }

    // forecast cone into future weekdays
    let F = 0;
    const fc = !intra && opts.forecast;
    if (fc) {
      F = Math.min(fc.days, Math.max(10, Math.round(Math.min(opts.bars || 126, n) * 0.4)));
      const days = [];
      let d = new Date(s.t[n - 1] * 1000);
      while (days.length < F) { d = new Date(d.getTime() + 86400000); if (d.getUTCDay() % 6) days.push(d.toISOString().slice(0, 10)); }
      const start = { time: dayStr(s.t[n - 1]), value: s.c[n - 1] };
      const seq = (arr) => [start].concat(days.map((t, k) => ({ time: t, value: arr[k] })));
      const noScale = { autoscaleInfoProvider: () => null }; // the 95% band shouldn't squash the candles
      const fill = chart.addAreaSeries({ ...noScale, lineColor: "rgba(57,135,229,.35)", topColor: "rgba(57,135,229,.16)", bottomColor: "rgba(57,135,229,.16)", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      fill.setData(seq(fc.hi2));
      const mask = chart.addAreaSeries({ ...noScale, lineColor: "rgba(57,135,229,.35)", topColor: C.surface, bottomColor: C.surface, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      mask.setData(seq(fc.lo2));
      chart.addLineSeries(lineOpts("rgba(57,135,229,.7)", { lineWidth: 1, lineStyle: 1 })).setData(seq(fc.hi1));
      chart.addLineSeries(lineOpts("rgba(57,135,229,.7)", { lineWidth: 1, lineStyle: 1 })).setData(seq(fc.lo1));
      chart.addLineSeries(lineOpts(C.accent, { lineStyle: 2, lastValueVisible: true, title: "Trend path" })).setData(seq(fc.mid));
      if (opts.target) {
        const tgt = chart.addLineSeries({ color: C.warn, lineVisible: false, pointMarkersVisible: true, pointMarkersRadius: 5, priceLineVisible: false, lastValueVisible: true, title: "Analyst target", crosshairMarkerVisible: false });
        tgt.setData([{ time: days[days.length - 1], value: opts.target }]);
      }
    }

    // keep the forecast extremes and the analyst target inside the price scale
    const extra = [];
    if (fc) extra.push(...fc.hi1.slice(0, F), ...fc.lo1.slice(0, F));
    if (intra === "day" && opts.prevClose) extra.push(opts.prevClose);
    if (fc && opts.target && Math.abs(opts.target / s.c[n - 1] - 1) < 0.35) extra.push(opts.target);
    if (extra.length) {
      const lo = Math.min(...extra), hi = Math.max(...extra);
      candles.applyOptions({ autoscaleInfoProvider: (orig) => {
        const r = orig();
        if (!r) return r;
        return { priceRange: { minValue: Math.min(r.priceRange.minValue, lo), maxValue: Math.max(r.priceRange.maxValue, hi) }, margins: r.margins };
      } });
    }

    // RSI in its own small chart, time-synced to the main one
    let rsiChart = null;
    if (showRsi) {
      const rEl = box.querySelector(".lw-rsi");
      rsiChart = LW.createChart(rEl, Object.assign({}, base, { layout: Object.assign({}, base.layout, { attributionLogo: false }), rightPriceScale: Object.assign({}, base.rightPriceScale), timeScale: Object.assign({}, base.timeScale, { visible: false }), localization: { priceFormatter: (v) => v.toFixed(0) }, handleScroll: false, handleScale: false }));
      const rs = rsiChart.addLineSeries(lineOpts(C.rsi, { lastValueVisible: true }));
      rs.setData(lineData(s.rsi));
      [30, 70].forEach((lv) => rs.createPriceLine({ price: lv, color: C.axis, lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
      chart.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (r) rsiChart.timeScale().setVisibleLogicalRange(r); });
    }

    // OHLC legend that follows the crosshair (TradingView style)
    let lastReal = n - 1;
    while (intra && lastReal > 0 && !s.v[lastReal]) lastReal--; // skip the zero-volume closing print
    box.setAttribute("aria-label", `${intra ? (intra === "day" ? "Latest session" : "Last 7 days") : "Daily"} price chart, close ${fmt(s.c[n - 1], dec)}` +
      (p ? `, entry ${fmt(p.entry, dec)}, stop ${fmt(p.stop, dec)}, target ${fmt(p.target1, dec)}` : ""));
    const showLegend = (i) => {
      if (i == null || i < 0 || i >= n) i = lastReal;
      const prev = intra === "day" && opts.prevClose ? opts.prevClose : i > 0 ? s.c[i - 1] : s.c[i];
      const ch = (s.c[i] / prev - 1) * 100;
      const when = intra ? new Date(s.t[i] * 1000).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" }) : new Date(s.t[i] * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
      if (calm) {
        legend.innerHTML = `<span>${when}</span><span><b style="color:${ch >= 0 ? "var(--good-text)" : "var(--bad-text)"}">${fmt(s.c[i], dec)} (${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%)</b></span>` +
          (s.sma200 && s.sma200[i] != null ? `<span>200-day average <b>${fmt(s.sma200[i], dec)}</b></span>` : "");
        return;
      }
      legend.innerHTML = `<span>${when}</span><span>O <b>${fmt(s.o[i], dec)}</b></span><span>H <b>${fmt(s.h[i], dec)}</b></span><span>L <b>${fmt(s.l[i], dec)}</b></span>` +
        `<span>C <b style="color:${ch >= 0 ? "var(--good-text)" : "var(--bad-text)"}">${fmt(s.c[i], dec)} (${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%)</b></span><span>Vol <b>${vol(s.v[i])}</b></span>` +
        (s.rsi && !intra && s.rsi[i] != null ? `<span>RSI <b>${s.rsi[i].toFixed(1)}</b></span>` : "");
    };
    chart.subscribeCrosshairMove((param) => {
      if (!param || param.logical == null || !param.time) return showLegend(lastReal);
      showLegend(Math.round(param.logical));
    });
    showLegend(lastReal);

    const bars = Math.min(opts.bars || 126, n);
    chart.timeScale().setVisibleLogicalRange({ from: n - bars - 0.5, to: n - 1 + F + 2 });
    if (rsiChart) rsiChart.timeScale().setVisibleLogicalRange({ from: n - bars - 0.5, to: n - 1 + F + 2 });
    return { destroy() { try { chart.remove(); rsiChart && rsiChart.remove(); } catch (e) { /* ignore */ } box.classList.remove("pro"); } };
  }

  // ------------------------------------------------------------ ECharts helpers
  const EC = window.echarts;
  const diverge = (v, span) => {
    // red (#d03b3b) - neutral (#3a3a37) - green (#0ca30c), clamped at +/- span
    const t = Math.max(-1, Math.min(1, (v || 0) / span)); // ends dark enough for white labels (AA)
    const mix = (a, b, k) => Math.round(a + (b - a) * k);
    const [r0, g0, b0] = [0x3a, 0x3a, 0x37];
    const [r1, g1, b1] = t >= 0 ? [0x08, 0x7a, 0x08] : [0xc0, 0x34, 0x34];
    const k = Math.abs(t);
    return `rgb(${mix(r0, r1, k)},${mix(g0, g1, k)},${mix(b0, b1, k)})`;
  };

  /** Finviz-style market map: tiles grouped by sector, sized by dollar volume, coloured by the chosen metric. */
  function MarketMap(el, rows, metric, onPick) {
    if (!EC) { el.innerHTML = `<p class="empty">Chart library missing.</p>`; return { destroy() {} }; }
    const M = {
      changePct: { label: "Today", span: 3, val: (r) => r.changePct },
      ret1m: { label: "1 month", span: 15, val: (r) => r.ret1m },
      ret3m: { label: "3 months", span: 30, val: (r) => r.ret3m },
      score: { label: "Signal score", span: 50, val: (r) => (r.score == null ? null : r.score - 50) },
    }[metric];
    const groups = {};
    rows.forEach((r) => {
      const size = Math.max(1, (r.price || 0) * (r.avgVolume || 0));
      (groups[r.sector] = groups[r.sector] || []).push({
        name: r.symbol, value: size, raw: r,
        itemStyle: { color: diverge(M.val(r), M.span) },
      });
    });
    const data = Object.entries(groups).map(([name, children]) => ({ name, children }));
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", `Market map of ${rows.length} stocks by sector, coloured by ${M.label.toLowerCase()}. Use the List button for a table.`);
    const chart = EC.init(el, null, { renderer: "canvas" });
    const txt = (r) => metric === "score" ? String(r.score) : (M.val(r) >= 0 ? "+" : "") + (M.val(r) == null ? "–" : M.val(r).toFixed(metric === "changePct" ? 2 : 1) + "%");
    chart.setOption({
      backgroundColor: "transparent",
      animation: !reduce, animationDurationUpdate: 600, aria: { enabled: true },
      tooltip: {
        backgroundColor: "#2c2c2a", borderColor: "rgba(255,255,255,.1)", textStyle: { color: "#f0efec", fontFamily: "Inter" },
        formatter: (p) => {
          const r = p.data && p.data.raw;
          if (!r) return `<b>${p.name}</b>`;
          return `<b>${r.symbol}</b> ${r.name ? "· " + r.name : ""}<br>Price ${fmt(r.price, 2)}<br>Today ${(r.changePct >= 0 ? "+" : "") + fmt(r.changePct, 2)}%` +
            `<br>1M ${fmt(r.ret1m, 1)}% · 3M ${fmt(r.ret3m, 1)}%<br>Rating ${r.rating || "–"} (${r.score ?? "–"})<br><span style="color:#898781">Tile size = daily traded value</span>`;
        },
      },
      series: [{
        type: "treemap", data, roam: false, nodeClick: false, breadcrumb: { show: false },
        width: "100%", height: "100%", top: 0, left: 0, right: 0, bottom: 0,
        visibleMin: 300, squareRatio: 0.9,
        upperLabel: { show: true, height: 22, color: "#c3c2b7", fontFamily: "Inter", fontWeight: 600, fontSize: 12, backgroundColor: "transparent" },
        label: {
          show: true, fontFamily: "Inter", color: "#fff", overflow: "truncate",
          formatter: (p) => (p.data.raw ? `{s|${p.name}}\n{v|${txt(p.data.raw)}}` : p.name),
          rich: { s: { fontSize: 14, fontWeight: 700, color: "#fff", lineHeight: 18 }, v: { fontSize: 11, color: "rgba(255,255,255,.85)", lineHeight: 14 } },
        },
        itemStyle: { borderColor: "#0d0d0d", borderWidth: 1, gapWidth: 1 },
        levels: [
          { itemStyle: { borderColor: "#0d0d0d", borderWidth: 3, gapWidth: 3 } },
          { itemStyle: { borderColor: "#0d0d0d", borderWidth: 1, gapWidth: 1 }, emphasis: { itemStyle: { borderColor: "#f0efec", borderWidth: 2 } } },
        ],
      }],
    });
    chart.on("click", (p) => { if (p.data && p.data.raw && onPick) onPick(p.data.raw.symbol); });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return { destroy() { ro.disconnect(); chart.dispose(); } };
  }

  /** Animated allocation donut. items: [{label, value, color}] */
  function AllocPie(el, items, centerTop, centerBottom) {
    if (!EC) { el.innerHTML = window.TChart.donut(items, 180, centerTop, centerBottom); return { destroy() {} }; }
    const resolve = (c) => (c.startsWith("var(") ? css(c.slice(4, -1)) : c);
    const chart = EC.init(el, null, { renderer: "svg" });
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", "Allocation: " + items.map((it) => it.label).join(", "));
    chart.setOption({
      backgroundColor: "transparent",
      animation: !matchMedia("(prefers-reduced-motion: reduce)").matches,
      tooltip: { trigger: "item", backgroundColor: "#2c2c2a", borderColor: "rgba(255,255,255,.1)", textStyle: { color: "#f0efec", fontFamily: "Inter" }, formatter: "{b}: {d}%" },
      title: { text: centerTop, subtext: centerBottom, left: "center", top: "40%", textStyle: { color: "#f0efec", fontSize: 16, fontFamily: "Inter", fontWeight: 600 }, subtextStyle: { color: "#898781", fontSize: 11 } },
      series: [{
        type: "pie", radius: ["62%", "92%"], top: 0, avoidLabelOverlap: true, label: { show: false },
        itemStyle: { borderColor: css("--surface-1"), borderWidth: 2 },
        emphasis: { scale: true, scaleSize: 6 },
        animationType: "scale", animationEasing: "cubicOut", animationDuration: 900,
        data: items.map((it) => ({ name: it.label, value: it.value, itemStyle: { color: resolve(it.color) } })),
      }],
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return { destroy() { ro.disconnect(); chart.dispose(); } };
  }

  window.ProCharts = { ProChart, MarketMap, AllocPie, countAll, ready: !!(LW && EC) };
})();
