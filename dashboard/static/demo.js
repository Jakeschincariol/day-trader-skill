/* Demo mode (start-demo.bat): an example portfolio, no account links, and neutral wording instead of
   buy/sell language, so screenshots and videos show the tool without looking like investment advice. */
(function () {
  "use strict";
  // longest phrases first; whole words only
  const WORDS = [
    ["Strong Buys & Best Entries", "Strongest trends"], ["Top Strong Buys", "Strongest trends"], ["All Strong Buys", "All strong trends"],
    ["Strong Buy signals", "Strong-trend signals"], ["Strong Buys", "Strong trends"], ["Strong Buy", "Very strong"], ["Strong Sell", "Very weak"],
    ["Buy zone: pullback", "Pullback"], ["Buy zone: breakout", "Breakout"], ["Buy zone", "In range"], ["Buy now", "In range now"],
    ["in a buy zone right now", "in range right now"], ["Quality on sale", "Quality below usual price"],
    ["Good business on sale: a good month to add a bit more than usual.", "Good business trading below its usual price."],
    ["Fair price: keep your regular monthly buy.", "Trading near its usual price."],
    ["Price ran ahead of the business: keep buying small, no need to rush.", "Price is above its usual range compared with the business."],
    ["Weak fundamentals or history: keep it a small satellite position, or research first.", "Weak fundamentals or history."],
    ["On sale: a good month to add", "Below its usual price"], ["Price stretched: no rush to add", "Price above its usual range"],
    ["Keep the regular buy", "Near its usual price"], ["check the story still holds", "low score"],
    ["Accumulate+", "Below usual price"], ["Accumulate", "Near usual price"], ["Review thesis", "Low score"],
    ["Your Trading 212 account (read-only), Revolut statement and manual holdings", "An example portfolio (EUR 500 a month since 2022)"],
    ["Your Trading 212 account (read-only), Revolut statement and any holdings you add by hand", "An example portfolio (EUR 500 a month since 2022)"],
    ["Link Trading 212 or Revolut →", "Example portfolio"],
    ["what to accumulate, hold or trim, your monthly plan, diversification and dividends", "a score for each holding, diversification and the 10-year plan"],
    ["with a live rating and exit check on every position", "with a live score on every position"],
    ["link Trading 212 to see cash", "example portfolio"], ["To trim or review", "Flagged holdings"], ["Example portfolio", "Example portfolio"],
    ["This site reads your Trading 212 account or Revolut statement and never places orders.", "This demo uses an example portfolio and never places orders."],
    ["On sale now", "Below usual price"], ["Buy-zone", "In-range"], ["Positions needing attention", "Flagged positions"],
    [" Breakouts work best bought the same day, not chased days later.", ""], [" Buying the dip near support keeps the stop close.", ""],
    ["Wait: extended", "Extended"], ["Wait: earnings", "Earnings soon"], ["Watch: market weak", "Market weak"],
  ];
  const SINGLE = [[/\bTrim\b/g, "Above target"], [/\bBuy\b(?! date| an\b| price| or\b)/g, "Strong"], [/\bSell\b/g, "Weak"], [/\bHold\b(?! up)/g, "Neutral"]];
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const RX = WORDS.map(([a, b]) => [new RegExp("(^|[^A-Za-z])" + esc(a) + "(?![A-Za-z+])", "g"), b]);
  const BADGE = /badge|pill|tag|seg|b-|tabs|chip|nb/;

  function fix(node) {
    let t = node.nodeValue, o = t;
    for (const [rx, to] of RX) t = t.replace(rx, (m, pre) => pre + to);
    // single words only inside labels, badges and buttons, never in free text like "Buy date"
    const el = node.parentElement;
    if (el && (BADGE.test(el.className || "") || /^(BUTTON|TH|B|LABEL)$/.test(el.tagName) || (el.closest && el.closest(".badge, .seg, .tabs")))) {
      for (const [rx, to] of SINGLE) t = t.replace(rx, to);
    }
    if (t !== o) node.nodeValue = t;
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { fix(root); return; }
    if (root.nodeType !== 1 || /^(SCRIPT|STYLE|TEXTAREA|INPUT|SELECT|OPTION)$/.test(root.tagName)) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) { if (!n.parentElement.closest("input, textarea, script, style")) fix(n); }
  }

  async function start() {
    let st = {};
    try { st = await (await fetch("/api/t212/status")).json(); } catch (e) { return; }
    if (!st.demo) return;
    document.body.classList.add("demo");
    document.body.insertAdjacentHTML("afterbegin", `<div class="demo-banner" role="note"><b>Demo</b> · example portfolio, not a real account · for illustration only, not investment advice</div>`);
    document.title = "TraderDash · Demo";
    walk(document.body);
    new MutationObserver((ms) => { for (const m of ms) { if (m.type === "characterData") fix(m.target); else m.addedNodes.forEach(walk); } })
      .observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
  window.Demo = { fix, walk };
})();
