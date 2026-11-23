// Kare kare render: yerel HTTP sunucu + paralel headless Chromium (SwiftShader WebGL)
const { chromium } = require('playwright'); const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');
const A = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v] = a.replace(/^--/, '').split('='); return [k, v ?? '1']; }));
const AR = A.ar || '16:9', W = +(A.w || (AR === '16:9' ? 1920 : 1080)), HH = AR === '16:9' ? Math.round(W * 9 / 16) : Math.round(W * 16 / 9), FPS = +(A.fps || 24), MOD = A.mod || 'ana', BOL = A.bolum || 'bolum1', OUT = path.resolve(A.out || path.join(ROOT, 'frames')), N = +(A.workers || 2);
const list = A.frames ? A.frames.split(',').map(Number) : Array.from({ length: Math.floor((+(A.to ?? 1349) - +(A.from ?? 0)) / +(A.step || 1)) + 1 }, (_, i) => +(A.from ?? 0) + i * +(A.step || 1));
fs.mkdirSync(OUT, { recursive: true });
const MIME = { '.js': 'text/javascript', '.html': 'text/html', '.jpg': 'image/jpeg', '.png': 'image/png', '.ttf': 'font/ttf', '.json': 'application/json' };
const srv = http.createServer((q, s) => { const f = path.join(ROOT, decodeURIComponent(q.url.split('?')[0])); if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { s.writeHead(404); return s.end(); } s.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(s); });
const name = f => path.join(OUT, String(f).padStart(5, '0') + '.jpg');
(async () => {
  await new Promise(r => srv.listen(0, '127.0.0.1', r)); const port = srv.address().port;
  const todo = list.filter(f => A.force || !fs.existsSync(name(f))); const t0 = Date.now(); let done = 0;
  const chunks = Array.from({ length: N }, (_, k) => todo.filter((_, i) => Math.floor(i * N / todo.length) === k));
  await Promise.all(chunks.map(async (ch, k) => { if (!ch.length) return;
    const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
    const p = await b.newPage({ viewport: { width: W, height: HH } });
    p.on('console', m => { if (['error', 'warning'].includes(m.type())) console.log(`[w${k}]`, m.text().slice(0, 300)); }); p.on('pageerror', e => console.log(`[w${k}] HATA`, e.message));
    await p.goto(`http://127.0.0.1:${port}/render/index.html?w=${W}&ar=${AR}&fps=${FPS}&mod=${MOD}&bolum=${BOL}`); await p.waitForFunction(() => window.READY === true, null, { timeout: 180000 });
    for (const f of ch) { const d = await p.evaluate(f => window.renderFrame(f), f); fs.writeFileSync(name(f) + '.tmp', Buffer.from(d.split(',')[1], 'base64')); fs.renameSync(name(f) + '.tmp', name(f)); if (++done % 25 === 0) console.log(`${done}/${todo.length}  ${((Date.now() - t0) / done).toFixed(0)} ms/kare`); }
    await b.close(); }));
  srv.close(); console.log('BİTTİ', done, 'kare,', ((Date.now() - t0) / 1000).toFixed(1), 's');
})().catch(e => { console.error(e); process.exit(1); });
