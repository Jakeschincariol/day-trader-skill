/* Canvas charts for Trader Dashboard. No dependencies. */
(function () {
  "use strict";
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmt = (x, d) => (x == null ? "–" : Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const fmtVol = (v) => (v >= 1e9 ? (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(v));
  const day = (t) => new Date(t * 1000);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function niceTicks(lo, hi, n) {
    const span = hi - lo || 1;
    const step0 = span / n;
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
    return { ticks: out, step };
  }

  /**
   * Price chart.
   * s: series {t,o,h,l,c,v,sma20,sma50,sma200,rsi}
   * opts: {bars: number of bars to show, plan: {entry,stop,target1,target2}, decimals}
   */
  function PriceChart(box, s, opts) {
    const canvas = document.createElement("canvas");
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    tip.hidden = true;
    box.innerHTML = "";
    box.appendChild(canvas);
    box.appendChild(tip);
    canvas.setAttribute("role", "img");
    const ctx = canvas.getContext("2d");
    let W = 0, H = 0, hover = -1, geom = null;
    const n = s.c.length;
    const start = Math.max(0, n - (opts.bars || 126));
    const dec = opts.decimals != null ? opts.decimals : s.c[n - 1] < 2 ? 4 : 2;
    const C = {
      up: css("--good"), down: css("--bad"), grid: css("--grid"), axis: css("--axis"), muted: css("--text-muted"),
      text: css("--text-secondary"), primary: css("--text-primary"), surface: css("--surface-1"),
      s20: css("--series-2"), s50: css("--series-1"), s200: css("--series-5"), accent: css("--accent"),
      rsi: css("--series-7"), warn: css("--warning"),
    };
    canvas.setAttribute("aria-label", "Daily candlestick chart, last " + (n - start) + " sessions, close " + fmt(s.c[n - 1], dec));

    function draw() {
      const dpr = window.devicePixelRatio || 1;
      W = box.clientWidth; H = box.clientHeight;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.font = "11px " + css("--mono");

      const right = 62, left = 6, top = 8, xAxisH = 20;
      const rsiH = Math.max(60, Math.round(H * 0.2));
      const gap = 14;
      const priceH = H - top - xAxisH - rsiH - gap;
      const plotW = W - left - right;
      const count = n - start;
      const bw = plotW / count;
      const x = (i) => left + (i - start + 0.5) * bw;

      let lo = Infinity, hi = -Infinity;
      for (let i = start; i < n; i++) { lo = Math.min(lo, s.l[i]); hi = Math.max(hi, s.h[i]); }
      for (const k of ["sma20", "sma50", "sma200"]) for (let i = start; i < n; i++) if (s[k][i] != null) { lo = Math.min(lo, s[k][i]); hi = Math.max(hi, s[k][i]); }
      const p = opts.plan;
      if (p) for (const k of ["entry", "stop", "target1"]) if (p[k] != null) { lo = Math.min(lo, p[k]); hi = Math.max(hi, p[k]); }
      const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
      const y = (v) => top + (hi - v) / (hi - lo) * priceH;

      // grid + y labels
      const { ticks } = niceTicks(lo, hi, 6);
      ctx.strokeStyle = C.grid; ctx.lineWidth = 1; ctx.fillStyle = C.muted; ctx.textAlign = "left"; ctx.textBaseline = "middle";
      for (const t of ticks) {
        const yy = Math.round(y(t)) + 0.5;
        ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + plotW, yy); ctx.stroke();
        ctx.fillText(fmt(t, dec > 2 ? dec : t < 10 ? 2 : t < 1000 ? 1 : 0), left + plotW + 6, yy);
      }

      // volume (bottom 18% of price panel)
      let vmax = 0;
      for (let i = start; i < n; i++) vmax = Math.max(vmax, s.v[i]);
      const vH = priceH * 0.18, vBase = top + priceH;
      for (let i = start; i < n; i++) {
        const h = vmax ? s.v[i] / vmax * vH : 0;
        ctx.fillStyle = s.c[i] >= s.o[i] ? "rgba(12,163,12,.28)" : "rgba(208,59,59,.28)";
        ctx.fillRect(x(i) - Math.max(1, bw * 0.35), vBase - h, Math.max(1, bw * 0.7), h);
      }

      // candles
      const cw = Math.max(1, Math.min(10, bw * 0.62));
      for (let i = start; i < n; i++) {
        const upBar = s.c[i] >= s.o[i];
        ctx.strokeStyle = ctx.fillStyle = upBar ? C.up : C.down;
        const xx = Math.round(x(i)) + 0.5;
        ctx.beginPath(); ctx.moveTo(xx, y(s.h[i])); ctx.lineTo(xx, y(s.l[i])); ctx.stroke();
        const y1 = y(Math.max(s.o[i], s.c[i])), y2 = y(Math.min(s.o[i], s.c[i]));
        ctx.fillRect(xx - cw / 2, y1, cw, Math.max(1, y2 - y1));
      }

      // moving averages, 2px
      const line = (arr, color, from, to, yf, width) => {
        ctx.strokeStyle = color; ctx.lineWidth = width || 2; ctx.lineJoin = "round"; ctx.beginPath();
        let on = false;
        for (let i = from; i < to; i++) {
          if (arr[i] == null) { on = false; continue; }
          on ? ctx.lineTo(x(i), yf(arr[i])) : ctx.moveTo(x(i), yf(arr[i]));
          on = true;
        }
        ctx.stroke();
      };
      line(s.sma200, C.s200, start, n, y);
      line(s.sma50, C.s50, start, n, y);
      line(s.sma20, C.s20, start, n, y);

      // plan lines with labels
      if (p) {
        const lines = [["Entry", p.entry, C.accent], ["Stop", p.stop, C.down], ["Target 1", p.target1, C.up], ["Target 2", p.target2, C.up]];
        ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5;
        for (const [label, v, color] of lines) {
          if (v == null || v < lo || v > hi) continue;
          const yy = Math.round(y(v)) + 0.5;
          ctx.strokeStyle = color; ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + plotW, yy); ctx.stroke();
          ctx.setLineDash([]);
          const txt = label + " " + fmt(v, dec);
          const tw = ctx.measureText(txt).width + 10;
          ctx.fillStyle = C.surface; ctx.fillRect(left + plotW - tw - 4, yy - 9, tw, 18);
          ctx.strokeStyle = color; ctx.strokeRect(left + plotW - tw - 4 + 0.5, yy - 8.5, tw - 1, 17);
          ctx.fillStyle = C.primary; ctx.textAlign = "left"; ctx.fillText(txt, left + plotW - tw + 1, yy);
          ctx.setLineDash([5, 4]);
        }
        ctx.setLineDash([]);
      }

      // last price tag
      const lastY = y(s.c[n - 1]);
      ctx.fillStyle = s.c[n - 1] >= s.c[n - 2] ? C.up : C.down;
      ctx.fillRect(left + plotW + 1, lastY - 9, right - 2, 18);
      ctx.fillStyle = "#fff"; ctx.textAlign = "left";
      ctx.fillText(fmt(s.c[n - 1], dec), left + plotW + 5, lastY);

      // RSI panel
      const rTop = top + priceH + gap, ry = (v) => rTop + (100 - v) / 100 * rsiH;
      ctx.fillStyle = "rgba(255,255,255,.03)"; ctx.fillRect(left, ry(70), plotW, ry(30) - ry(70));
      ctx.strokeStyle = C.grid; ctx.lineWidth = 1;
      for (const lv of [30, 50, 70]) {
        const yy = Math.round(ry(lv)) + 0.5;
        ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + plotW, yy); ctx.stroke();
        ctx.fillStyle = C.muted; ctx.fillText(String(lv), left + plotW + 6, yy);
      }
      ctx.strokeStyle = C.axis; ctx.strokeRect(left + 0.5, rTop + 0.5, plotW - 1, rsiH - 1);
      line(s.rsi, C.rsi, start, n, ry);
      ctx.fillStyle = C.text; ctx.fillText("RSI 14", left + 6, rTop + 10);

      // x axis: month labels
      ctx.fillStyle = C.muted; ctx.textAlign = "center"; ctx.textBaseline = "top";
      let lastM = -1, lastX = -100;
      for (let i = start; i < n; i++) {
        const d = day(s.t[i]);
        const m = d.getMonth();
        if (m !== lastM && x(i) - lastX > 44) {
          const label = m === 0 ? String(d.getFullYear()) : MONTHS[m];
          ctx.fillText(label, Math.min(Math.max(x(i), left + 14), left + plotW - 14), rTop + rsiH + 5);
          lastX = x(i);
        }
        lastM = m;
      }

      // crosshair
      if (hover >= start && hover < n) {
        const xx = Math.round(x(hover)) + 0.5;
        ctx.strokeStyle = "rgba(240,239,236,.35)"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, rTop + rsiH); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = C.primary; ctx.strokeStyle = C.surface; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(xx, y(s.c[hover]), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
      geom = { left, plotW, bw, start, x };
    }

    function showTip(i, px, py) {
      const d = day(s.t[i]);
      const chg = i > 0 ? (s.c[i] / s.c[i - 1] - 1) * 100 : 0;
      const row = (k, v, cls) => `<div class="row"><span class="muted">${k}</span><span class="num ${cls || ""}">${v}</span></div>`;
      tip.innerHTML = `<div style="font-weight:600;margin-bottom:2px">${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</div>` +
        row("Open", fmt(s.o[i], dec)) + row("High", fmt(s.h[i], dec)) + row("Low", fmt(s.l[i], dec)) +
        row("Close", fmt(s.c[i], dec) + ` (${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%)`, chg >= 0 ? "up" : "down") +
        row("Volume", fmtVol(s.v[i])) + row("SMA 20 / 50", fmt(s.sma20[i], dec) + " / " + fmt(s.sma50[i], dec)) +
        row("SMA 200", fmt(s.sma200[i], dec)) + row("RSI", s.rsi[i] == null ? "–" : s.rsi[i].toFixed(1));
      tip.hidden = false;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let lx = px + 16; if (lx + tw > W) lx = px - tw - 16;
      tip.style.left = Math.max(0, lx) + "px";
      tip.style.top = Math.max(0, Math.min(H - th, py - th / 2)) + "px";
    }

    function onMove(ev) {
      if (!geom) return;
      const rect = canvas.getBoundingClientRect();
      const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
      const py = (ev.touches ? ev.touches[0].clientY : ev.clientY) - rect.top;
      const i = Math.floor((px - geom.left) / geom.bw) + geom.start;
      if (i < geom.start || i >= n) return onLeave();
      if (i !== hover) { hover = i; draw(); }
      showTip(i, px, py);
    }
    function onLeave() { hover = -1; tip.hidden = true; draw(); }
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("touchmove", onMove, { passive: true });
    canvas.addEventListener("mouseleave", onLeave);
    canvas.addEventListener("touchend", onLeave);
    const ro = new ResizeObserver(() => draw());
    ro.observe(box);
    draw();
    return { destroy() { ro.disconnect(); } };
  }

  /** Tiny inline sparkline (SVG string) of the last closes. */
  function sparkline(values, w, h) {
    w = w || 90; h = h || 28;
    const v = values.filter((x) => x != null);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v);
    const pts = v.map((y, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - 2 - (y - lo) / (hi - lo || 1) * (h - 4)).toFixed(1)}`).join(" ");
    const color = v[v.length - 1] >= v[0] ? "var(--good)" : "var(--bad)";
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" points="${pts}"/></svg>`;
  }

  /**
   * Donut (SVG). items: [{label, value, color}] - caller folds anything past 8 into "Other".
   * 2px surface gap between segments.
   */
  function donut(items, size, centerTop, centerBottom) {
    size = size || 180;
    const total = items.reduce((a, b) => a + b.value, 0) || 1;
    const r = size / 2 - 4, inner = r * 0.64, cx = size / 2, cy = size / 2;
    let a0 = -Math.PI / 2, paths = "";
    for (const it of items) {
      const frac = it.value / total;
      const a1 = a0 + frac * Math.PI * 2;
      if (frac >= 0.999) {
        paths += `<circle cx="${cx}" cy="${cy}" r="${(r + inner) / 2}" fill="none" stroke="${it.color}" stroke-width="${r - inner}"><title>${it.label}: ${(frac * 100).toFixed(1)}%</title></circle>`;
      } else {
        const large = a1 - a0 > Math.PI ? 1 : 0;
        const p = (rad, a) => `${(cx + rad * Math.cos(a)).toFixed(2)},${(cy + rad * Math.sin(a)).toFixed(2)}`;
        paths += `<path d="M${p(r, a0)} A${r},${r} 0 ${large} 1 ${p(r, a1)} L${p(inner, a1)} A${inner},${inner} 0 ${large} 0 ${p(inner, a0)} Z" fill="${it.color}" stroke="var(--surface-1)" stroke-width="2"><title>${it.label}: ${(frac * 100).toFixed(1)}%</title></path>`;
      }
      a0 = a1;
    }
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="Allocation chart">${paths}` +
      `<text x="${cx}" y="${cy - 4}" text-anchor="middle" fill="var(--text-primary)" font-size="16" font-weight="600">${centerTop || ""}</text>` +
      `<text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="var(--text-muted)" font-size="11">${centerBottom || ""}</text></svg>`;
  }

  window.TChart = { PriceChart, sparkline, donut, fmt, fmtVol };
})();
