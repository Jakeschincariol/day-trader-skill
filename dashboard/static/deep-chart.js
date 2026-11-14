/* "Dig deeper" chart on the stock page: candles with a fast and a slow average, the high of the period,
   earnings report markers, a momentum-waves oscillator (WaveTrend) and MACD, all time-synced,
   plus a plain-English reading of what they say right now. Standard public indicators only. */
(function () {
  "use strict";
  const LW = window.LightweightCharts;
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const fmt = (x, d) => (x == null ? "–" : Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));

  // ------------------------------------------------------------ indicators (pure, unit-testable)
  function ema(xs, n) {
    const out = new Array(xs.length).fill(null), k = 2 / (n + 1);
    let prev = null, sum = 0, cnt = 0;
    for (let i = 0; i < xs.length; i++) {
      const x = xs[i];
      if (x == null) continue;
      if (prev == null) { sum += x; cnt++; if (cnt === n) { prev = sum / n; out[i] = prev; } continue; }
      prev = x * k + prev * (1 - k); out[i] = prev;
    }
    return out;
  }
  function sma(xs, n) {
    const out = new Array(xs.length).fill(null);
    let s = 0, c = 0;
    const q = [];
    for (let i = 0; i < xs.length; i++) {
      const x = xs[i];
      if (x == null) { q.push(null); continue; }
      q.push(x); s += x; c++;
      while (q.length > n) { const y = q.shift(); if (y != null) { s -= y; c--; } }
      if (c === n) out[i] = s / n;
    }
    return out;
  }
  /** WaveTrend (channel length 10, average length 21): wt1 fast wave, wt2 its 4-bar average. */
  function waveTrend(h, l, c, n1 = 10, n2 = 21) {
    const ap = c.map((x, i) => (h[i] + l[i] + x) / 3);
    const esa = ema(ap, n1);
    const dev = ema(ap.map((x, i) => (esa[i] == null ? null : Math.abs(x - esa[i]))), n1);
    const ci = ap.map((x, i) => (esa[i] == null || !dev[i] ? null : (x - esa[i]) / (0.015 * dev[i])));
    const wt1 = ema(ci, n2);
    const wt2 = sma(wt1, 4);
    return { wt1, wt2 };
  }
  function macd(c, f = 12, s = 26, sig = 9) {
    const a = ema(c, f), b = ema(c, s);
    const line = c.map((_, i) => (a[i] == null || b[i] == null ? null : a[i] - b[i]));
    const signal = ema(line, sig);
    const hist = line.map((x, i) => (x == null || signal[i] == null ? null : x - signal[i]));
    return { line, signal, hist };
  }
  /** Crossings of wt1 over wt2 in the extreme zones: up below -53 (oversold turning up), down above 53. */
  function waveSignals(wt1, wt2, lvl = 53) {
    const out = [];
    for (let i = 1; i < wt1.length; i++) {
      if ([wt1[i], wt2[i], wt1[i - 1], wt2[i - 1]].some((x) => x == null)) continue;
      const up = wt1[i - 1] <= wt2[i - 1] && wt1[i] > wt2[i], down = wt1[i - 1] >= wt2[i - 1] && wt1[i] < wt2[i];
      if (up && wt1[i] < -lvl) out.push({ i, kind: "buy" });
      else if (down && wt1[i] > lvl) out.push({ i, kind: "sell" });
    }
    return out;
  }

  /** Plain-English reading of the last bar. */
  function reading(d, ind, unit) {
    const n = d.c.length, i = n - 1, px = d.c[i];
    const lines = [];
    const f = ind.fast[i], s = ind.slow[i];
    if (f != null && s != null) {
      const t = px > f && px > s ? ["up", "Uptrend: the price is above both averages."]
        : px < f && px < s ? ["down", `Downtrend: the price is below both averages${f < s ? " and the fast one is under the slow one" : ""}.`]
          : ["flat", "Mixed: the price sits between the fast and the slow average."];
      lines.push({ tone: t[0], k: "Trend", text: t[1] });
    }
    const w1 = ind.wt.wt1[i], w2 = ind.wt.wt2[i];
    if (w1 != null) {
      const last = ind.sig.length ? ind.sig[ind.sig.length - 1] : null;
      const ago = last ? n - 1 - last.i : null;
      let text = w1 <= -60 ? "Deeply oversold: selling has been heavy." : w1 <= -53 ? "Oversold." : w1 >= 60 ? "Deeply overbought: buying has been heavy." : w1 >= 53 ? "Overbought." : "In the normal range.";
      text += w2 != null ? (w1 > w2 ? " The fast wave is above the slow one: momentum turning up." : " The fast wave is below the slow one: momentum still down.") : "";
      if (last && ago <= 6) text += ` ${last.kind === "buy" ? "Green dot" : "Red dot"} ${ago === 0 ? "on the last " + unit : ago + " " + unit + (ago === 1 ? "" : "s") + " ago"}: ${last.kind === "buy" ? "turned up from oversold" : "turned down from overbought"}.`;
      lines.push({ tone: w1 > (w2 ?? w1) ? "up" : "down", k: "Momentum waves", text });
    }
    const m = ind.md.line[i], sg = ind.md.signal[i], hs = ind.md.hist;
    if (m != null && sg != null) {
      const rising = hs[i] != null && hs[i - 1] != null && hs[i] > hs[i - 1];
      const text = (m > sg ? "Above its signal line: buyers in control" : "Below its signal line: sellers in control") +
        (m > sg ? (rising ? ", and getting stronger." : ", but fading.") : (rising ? ", but the selling is slowing." : ", and getting stronger.")) +
        (m < 0 ? " Still below zero." : "");
      lines.push({ tone: m > sg ? "up" : rising ? "flat" : "down", k: "MACD", text });
    }
    const hiIdx = d.h.reduce((b, x, j) => (x > d.h[b] ? j : b), 0);
    const off = 100 * (px / d.h[hiIdx] - 1);
    lines.push({ tone: off > -10 ? "up" : off > -25 ? "flat" : "down", k: "From the high", text: `${Math.abs(off).toFixed(1)}% below the high of ${fmt(d.h[hiIdx], 2)} (${new Date(d.t[hiIdx] * 1000).toLocaleDateString(undefined, { month: "short", year: "numeric" })}).` });
    if (d.next) lines.push({ tone: d.next.days <= 7 ? "flat" : "up", k: "Next results", text: `${d.next.date} (in ${d.next.days} day${d.next.days === 1 ? "" : "s"})${d.next.days <= 7 ? ": expect a big move around that day." : "."}` });
    return lines;
  }

  // ------------------------------------------------------------ the chart
  function DeepChart(box, d, opts) {
    opts = opts || {};
    if (!LW) { box.innerHTML = `<p class="muted">The chart library did not load.</p>`; return { destroy() {} }; }
    const C = { up: css("--good"), down: css("--bad"), grid: css("--grid"), axis: css("--axis"), muted: css("--text-muted"),
      fast: "#ec835a", slow: "#f0efec", wave: "#3987e5", wave2: css("--series-7") || "#9085e9", mLine: "#3987e5", mSig: "#ec835a", warn: css("--warning") };
    const n = d.c.length;
    const unit = d.tf === "w" ? "week" : "day";
    const ind = { fast: ema(d.c, 21), slow: sma(d.c, 50), wt: waveTrend(d.h, d.l, d.c), md: macd(d.c) };
    ind.sig = waveSignals(ind.wt.wt1, ind.wt.wt2);
    const narrow = box.clientWidth < 520;
    box.innerHTML = `<div class="dc-pane dc-main"><div class="lw-legend" id="dcLeg"></div></div>
      <div class="dc-pane dc-wave"><span class="lw-tag">Momentum waves</span></div>
      <div class="dc-pane dc-macd"><span class="lw-tag">MACD 12 · 26 · 9</span></div>`;
    const day = (ts) => new Date(ts * 1000).toISOString().slice(0, 10);
    const T = d.t.map(day);
    const base = {
      autoSize: true,
      layout: { background: { type: "solid", color: "transparent" }, textColor: C.muted, fontFamily: css("--mono") || "monospace", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
      rightPriceScale: { borderColor: C.axis, minimumWidth: narrow ? 56 : 84 },
      timeScale: { borderColor: C.axis, rightOffset: 3 },
      crosshair: { mode: 0, vertLine: { color: "rgba(240,239,236,.35)", labelBackgroundColor: "#2c2c2a" }, horzLine: { color: "rgba(240,239,236,.35)", labelBackgroundColor: "#2c2c2a" } },
    };
    const sub = (el, fmtFn) => LW.createChart(el, Object.assign({}, base, { timeScale: Object.assign({}, base.timeScale, { visible: false }), localization: { priceFormatter: fmtFn } }));
    const main = LW.createChart(box.querySelector(".dc-main"), Object.assign({}, base, { localization: { priceFormatter: (p) => fmt(p, d.c[n - 1] < 2 ? 4 : 2) } }));
    const wave = sub(box.querySelector(".dc-wave"), (v) => v.toFixed(0));
    const mac = sub(box.querySelector(".dc-macd"), (v) => v.toFixed(2));
    const line = (ch, color, extra) => ch.addLineSeries(Object.assign({ color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }, extra || {}));
    const ld = (arr) => arr.map((v, i) => (v == null ? { time: T[i] } : { time: T[i], value: v }));

    const candles = main.addCandlestickSeries({ upColor: C.up, downColor: C.down, borderVisible: false, wickUpColor: C.up, wickDownColor: C.down });
    candles.setData(d.c.map((c, i) => ({ time: T[i], open: d.o[i], high: d.h[i], low: d.l[i], close: c })));
    line(main, C.slow).setData(ld(ind.slow));
    line(main, C.fast).setData(ld(ind.fast));
    const hiIdx = d.h.reduce((b, x, j) => (x > d.h[b] ? j : b), 0);
    candles.createPriceLine({ price: d.h[hiIdx], color: C.muted, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: narrow ? "" : "High" });
    // earnings markers on the bar that holds the report day
    const marks = [];
    (d.earnings || []).forEach((e) => {
      const ts = e.ts || Date.parse(e.date) / 1000;
      let j = -1;
      for (let k = 0; k < n; k++) { if (d.t[k] <= ts + 43200) j = k; else break; }
      if (j >= 0 && (d.tf === "w" ? ts - d.t[j] < 8 * 86400 : ts - d.t[j] < 2 * 86400)) marks.push({ time: T[j], position: "belowBar", color: "#199e70", shape: "circle", text: "E" });
    });
    marks.sort((a, b) => (a.time < b.time ? -1 : 1));
    if (marks.length) candles.setMarkers(marks);
    candles.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.1 } });

    const w1 = wave.addBaselineSeries({ baseValue: { type: "price", price: 0 }, topLineColor: C.wave, bottomLineColor: C.wave, topFillColor1: "rgba(57,135,229,.5)", topFillColor2: "rgba(57,135,229,.15)",
      bottomFillColor1: "rgba(57,135,229,.15)", bottomFillColor2: "rgba(57,135,229,.5)", lineWidth: 1, priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false });
    w1.setData(ld(ind.wt.wt1));
    const w2 = line(wave, C.wave2, { lineWidth: 1.5 });
    w2.setData(ld(ind.wt.wt2));
    [60, 53, 0, -53, -60].forEach((lv) => w1.createPriceLine({ price: lv, color: lv === 0 ? C.axis : Math.abs(lv) === 60 ? "rgba(240,239,236,.35)" : "rgba(240,239,236,.18)", lineWidth: 1, lineStyle: lv === 0 ? 0 : 2, axisLabelVisible: false }));
    w2.setMarkers(ind.sig.map((x) => ({ time: T[x.i], position: x.kind === "buy" ? "belowBar" : "aboveBar", color: x.kind === "buy" ? "#3fcf3f" : "#ff7a7a", shape: "circle" })));

    const hist = mac.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
    hist.setData(ind.md.hist.map((v, i) => (v == null ? { time: T[i] } : { time: T[i], value: v,
      color: v >= 0 ? (i && v >= (ind.md.hist[i - 1] ?? v) ? "rgba(12,163,12,.8)" : "rgba(12,163,12,.4)") : (i && v <= (ind.md.hist[i - 1] ?? v) ? "rgba(208,59,59,.8)" : "rgba(208,59,59,.4)") })));
    line(mac, C.mLine).setData(ld(ind.md.line));
    line(mac, C.mSig).setData(ld(ind.md.signal));

    // keep the three panes on the same bars
    const subs = [wave, mac];
    main.timeScale().subscribeVisibleLogicalRangeChange((r) => { if (r) subs.forEach((c) => c.timeScale().setVisibleLogicalRange(r)); });
    const leg = box.querySelector("#dcLeg");
    const showLeg = (i) => {
      if (i == null || i < 0 || i >= n) i = n - 1;
      const ch = i ? (d.c[i] / d.c[i - 1] - 1) * 100 : 0;
      leg.innerHTML = `<span>${new Date(d.t[i] * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</span>` +
        `<span>C <b style="color:${ch >= 0 ? "var(--good-text)" : "var(--bad-text)"}">${fmt(d.c[i], 2)} (${ch >= 0 ? "+" : ""}${ch.toFixed(1)}%)</b></span>` +
        `<span style="color:${C.fast}">EMA 21 <b>${fmt(ind.fast[i], 2)}</b></span><span>SMA 50 <b>${fmt(ind.slow[i], 2)}</b></span>` +
        (ind.wt.wt1[i] != null ? `<span>Waves <b>${ind.wt.wt1[i].toFixed(0)}</b></span>` : "");
    };
    main.subscribeCrosshairMove((p) => {
      const i = p && p.logical != null && p.time ? Math.round(p.logical) : null;
      showLeg(i);
      if (i != null && i >= 0 && i < n) subs.forEach((c, k) => { try { c.setCrosshairPosition([ind.wt.wt1, ind.md.line][k][i] ?? 0, T[i], k ? hist : w1); } catch (e) { /* older library */ } });
      else subs.forEach((c) => { try { c.clearCrosshairPosition(); } catch (e) { /* ignore */ } });
    });
    showLeg(n - 1);
    const show = Math.min(n, opts.bars || (d.tf === "w" ? 156 : 252));
    main.timeScale().setVisibleLogicalRange({ from: n - show - 0.5, to: n + 2 });
    return { reading: reading(d, ind, unit), destroy() { try { main.remove(); wave.remove(); mac.remove(); } catch (e) { /* ignore */ } } };
  }

  window.DeepChart = { DeepChart, ema, sma, waveTrend, macd, waveSignals, reading };
})();
