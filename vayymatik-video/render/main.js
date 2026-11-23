import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { clamp, lerp, sstep, ein, eout } from './lib.js';
import { scene1, scene7 } from './space.js';
import { scene2, scene5, scene6 } from './water.js';
import { scene3, scene6b, scene4a, scene4b } from './graphic.js';
const W = +(new URLSearchParams(location.search).get('w') || 1080), H = Math.round(W * 16 / 9), SC = W / 1080;
const loaded = new Promise(r => { THREE.DefaultLoadingManager.onLoad = r; }); THREE.DefaultLoadingManager.onError = u => console.error('YÜKLENEMEDİ', u);
const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true }); renderer.setPixelRatio(1); renderer.setSize(W, H); document.body.appendChild(renderer.domElement);
renderer.outputColorSpace = THREE.SRGBColorSpace;
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 })); composer.setPixelRatio(1); composer.setSize(W, H);
const rp = new RenderPass(new THREE.Scene(), new THREE.PerspectiveCamera()); composer.addPass(rp);
const bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 1, .5, .7); composer.addPass(bloom);
composer.addPass(new OutputPass());
const fin = new ShaderPass({
  uniforms: { tDiffuse: { value: null }, tOverlay: { value: null }, uTime: { value: 0 }, uZoom: { value: 0 }, uCA: { value: 0 }, uGlitch: { value: 0 }, uFlash: { value: new THREE.Vector4() }, uFade: { value: 0 }, uVig: { value: .5 }, uGrain: { value: .04 }, uSat: { value: 1 }, uCon: { value: 1 }, uTint: { value: new THREE.Vector3(1, 1, 1) } },
  vertexShader: `varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
  fragmentShader: `uniform sampler2D tDiffuse,tOverlay; uniform float uTime,uZoom,uCA,uGlitch,uFade,uVig,uGrain,uSat,uCon; uniform vec4 uFlash; uniform vec3 uTint; varying vec2 vUv;
  float h(vec2 p){ return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453); }
  vec3 samp(vec2 uv,float ca){ vec2 d=(uv-.5)*ca*.006; return vec3(texture2D(tDiffuse,uv+d).r,texture2D(tDiffuse,uv).g,texture2D(tDiffuse,uv-d).b); }
  void main(){ vec2 uv=vUv; float fr=floor(uTime*30.+.5);
    if(uGlitch>0.){ float band=floor(uv.y*28.); if(h(vec2(band,fr))>.72) uv.x+=(h(vec2(band,fr+7.))-.5)*.09*uGlitch; }
    float ca=uCA+uZoom*2.+.35; vec3 col;
    if(uZoom>.002){ vec3 acc=vec3(0.); float tw=0.; for(int i=0;i<14;i++){ float f=float(i)/13.; float w=1.-f*.6; acc+=samp(.5+(uv-.5)*(1.-uZoom*.12*f),ca)*w; tw+=w; } col=acc/tw; } else col=samp(uv,ca);
    col*=uTint; float l=dot(col,vec3(.2126,.7152,.0722)); col=mix(vec3(l),col,uSat); col=(col-.5)*uCon+.5;
    vec2 q=(vUv-.5)*vec2(1.,1.25); col*=1.-uVig*smoothstep(.25,.85,length(q));
    vec4 o=texture2D(tOverlay,vUv); col=mix(col,o.rgb,o.a);
    col=mix(col,uFlash.rgb,uFlash.a); col*=1.-uFade;
    col+=(h(vUv*vec2(1080.,1920.)+fr*.37)-.5)*uGrain;
    gl_FragColor=vec4(clamp(col,0.,1.),1.); }` });
composer.addPass(fin);
// ---------- 2B katman: etiketler, uyarılar, logo ----------
const oc = document.createElement('canvas'); oc.width = W; oc.height = H; const ctx = oc.getContext('2d');
const otex = new THREE.CanvasTexture(oc); otex.colorSpace = THREE.NoColorSpace; fin.uniforms.tOverlay.value = otex;
const rr = (x, y, w, h, r) => { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); };
const toS = (v, cam) => { const p = v.clone().project(cam); return [(p.x + 1) / 2 * 1080, (1 - p.y) / 2 * 1920, p.z]; };
const O = {
  label(v, cam, lines, a, o = {}) { if (a <= .003) return; const [x, y, z] = toS(v, cam); if (z > 1) return; const col = o.color || '#4fe3ff';
    ctx.save(); ctx.globalAlpha = Math.min(1, a * 1.2);
    ctx.font = '800 44px Mont'; const w1 = ctx.measureText(lines[0]).width; ctx.font = '600 32px Mont'; const w2 = lines[1] ? ctx.measureText(lines[1]).width : 0;
    const bw = Math.max(w1, w2) + 58, bh = lines[1] ? 112 : 74;
    let bx = o.dx >= 0 ? x + o.dx : x + o.dx - bw, by = y + o.dy - bh / 2; bx = clamp(bx, 36, 1044 - bw); by = clamp(by, o.yr ? o.yr[0] : 150, (o.yr ? o.yr[1] : 1770) - bh);
    const ax = clamp(x + o.dx, bx, bx + bw), ay = by + bh / 2; const k = clamp(a * 1.5);
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 3; ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 8;
    ctx.beginPath(); ctx.arc(x, y, 8, 0, 7); ctx.fill(); ctx.beginPath(); ctx.arc(x, y, 15 + 10 * (1 - a), 0, 7); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(lerp(x, ax, k), lerp(y, ay, k)); ctx.stroke();
    ctx.globalAlpha = a; ctx.shadowBlur = 18; ctx.fillStyle = 'rgba(2,12,22,.8)'; rr(bx, by, bw, bh, 16); ctx.fill(); ctx.shadowBlur = 0;
    ctx.fillStyle = col; rr(bx, by, 9, bh, [16, 0, 0, 16]); ctx.fill();
    ctx.fillStyle = '#ffffff'; ctx.font = '800 44px Mont'; ctx.textBaseline = 'middle'; ctx.fillText(lines[0], bx + 32, by + (lines[1] ? 38 : bh / 2 + 2));
    if (lines[1]) { ctx.fillStyle = '#bfe6f5'; ctx.font = '600 32px Mont'; ctx.fillText(lines[1], bx + 32, by + 82); }
    ctx.restore(); },
  badge(text, x, y, a, col = '#ff4a3d') { if (a <= .003) return; ctx.save(); ctx.globalAlpha = a; ctx.font = '800 30px Mont'; ctx.letterSpacing = '4px'; const w = ctx.measureText(text).width + 56;
    ctx.fillStyle = 'rgba(0,0,0,.5)'; rr(x - w / 2, y - 30, w, 60, 30); ctx.fill(); ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = col; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, x + 2, y + 2); ctx.restore(); },
  warn(text, x, y, a, t) { if (a <= .003) return; ctx.save(); ctx.globalAlpha = a * (.78 + .22 * Math.sin(t * 13)); ctx.font = '900 50px Mont'; const w = ctx.measureText(text).width + 150;
    ctx.shadowColor = 'rgba(255,40,30,.9)'; ctx.shadowBlur = 40; ctx.fillStyle = '#e0251b'; rr(x - w / 2, y - 48, w, 96, 20); ctx.fill(); ctx.shadowBlur = 0;
    ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.moveTo(x - w / 2 + 40, y + 28); ctx.lineTo(x - w / 2 + 72, y - 30); ctx.lineTo(x - w / 2 + 104, y + 28); ctx.closePath(); ctx.fill();
    ctx.fillStyle = '#e0251b'; ctx.font = '900 40px Mont'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', x - w / 2 + 72, y + 8);
    ctx.fillStyle = '#fff'; ctx.font = '900 50px Mont'; ctx.fillText(text, x + 50, y + 3); ctx.restore(); },
  xmark(v, cam, a, t) { if (a <= .003) return; const [x, y] = toS(v, cam); ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = '#ff3b30'; ctx.lineWidth = 12; ctx.lineCap = 'round'; ctx.shadowColor = '#ff3b30'; ctx.shadowBlur = 25;
    const s = 26; ctx.beginPath(); ctx.moveTo(x - s, y - s); ctx.lineTo(x + s, y + s); ctx.moveTo(x + s, y - s); ctx.lineTo(x - s, y + s); ctx.stroke();
    ctx.lineWidth = 4; ctx.globalAlpha = a * (1 - (t * 1.5 % 1)); ctx.beginPath(); ctx.arc(x, y, 30 + (t * 1.5 % 1) * 60, 0, 7); ctx.stroke(); ctx.restore(); },
  logo(a, t, b) { if (a <= .003) return; ctx.save(); const y = 520, txt = 'VAYYMATİK0'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    let fs = 150; ctx.font = `900 ${fs}px Mont`; ctx.letterSpacing = '6px'; const mw = ctx.measureText(txt).width; fs = Math.min(fs, fs * 930 / mw); ctx.font = `900 ${fs}px Mont`;
    const w = 1080 * eout(a); ctx.beginPath(); ctx.rect(540 - w / 2, y - 200, w, 400); ctx.clip();
    ctx.globalAlpha = Math.min(1, a * 1.5); ctx.shadowColor = 'rgba(40,210,255,.95)'; ctx.shadowBlur = 60; ctx.fillStyle = '#bff6ff'; ctx.fillText(txt, 540, y);
    ctx.shadowBlur = 0; const g = ctx.createLinearGradient(0, y - fs / 2, 0, y + fs / 2); g.addColorStop(0, '#ffffff'); g.addColorStop(.55, '#e8fbff'); g.addColorStop(1, '#6fe6ff'); ctx.fillStyle = g; ctx.fillText(txt, 540, y);
    const sx = -300 + ((t * 900) % 1700); const sg = ctx.createLinearGradient(sx - 120, 0, sx + 120, 0); sg.addColorStop(0, 'rgba(255,255,255,0)'); sg.addColorStop(.5, 'rgba(255,255,255,.85)'); sg.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.globalCompositeOperation = 'source-atop'; ctx.fillStyle = sg; ctx.fillRect(0, y - fs, 1080, fs * 2); ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#4fe3ff'; ctx.fillRect(540 - 330 * eout(a), y + fs * .62, 660 * eout(a), 6);
    ctx.restore();
    if (b > .003) { ctx.save(); ctx.globalAlpha = b; const s = .9 + .1 * eout(b); ctx.translate(540, y + 175); ctx.scale(s, s); ctx.font = '800 44px Mont'; ctx.letterSpacing = '3px'; const tw = ctx.measureText('TAKİP ET').width + 120;
      ctx.shadowColor = 'rgba(255,40,80,.8)'; ctx.shadowBlur = 30; ctx.fillStyle = '#ff2d55'; rr(-tw / 2, -44, tw, 88, 44); ctx.fill(); ctx.shadowBlur = 0;
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.moveTo(-tw / 2 + 42, -18); ctx.lineTo(-tw / 2 + 42, 18); ctx.lineTo(-tw / 2 + 72, 0); ctx.closePath(); ctx.fill();
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('TAKİP ET', 22, 3); ctx.restore(); }
  }
};
// ---------- Zaman çizelgesi ----------
const TL = [[0, 3.5, scene1], [3.5, 9.6, scene2], [9.6, 16.4, scene3], [16.4, 19.6, scene4a], [19.6, 23.4, scene4b], [23.4, 30.6, scene5], [30.6, 34.6, scene6], [34.6, 37.6, scene6b], [37.6, 45.01, scene7]]
  .map(([t0, t1, f]) => ({ t0, t1, o: f(renderer) }));
const TR = [[3.5, .6, .35, 1.4, [.85, .97, 1], 1], [9.6, .3, .25, 1, [.3, .9, 1], .55], [16.4, .3, .25, 1, [.4, .9, 1], .5], [19.6, .35, .3, 1.2, [.9, 1, 1], 1], [23.4, .4, .3, 1.2, [.9, 1, 1], .9], [34.6, .25, .25, .9, [.4, .9, 1], .45], [37.6, .3, .3, 1, [.85, .97, 1], .6]];
function transitions(t, P) {
  for (const [T, pre, post, z, c, fa] of TR) {
    if (t >= T - pre && t < T) { P.zoom += z * ein((t - T + pre) / pre); const f = fa * sstep(T - pre * .5, T, t); if (f > P.flash[3]) P.flash = [...c, f]; }
    else if (t >= T && t < T + post) { P.zoom += z * .6 * (1 - eout((t - T) / post)); const f = fa * (1 - sstep(T, T + post, t)); if (f > P.flash[3]) P.flash = [...c, f]; }
  }
  if (t > 30.35 && t < 30.85) P.fade = Math.max(P.fade, t < 30.6 ? sstep(30.35, 30.6, t) * .9 : (1 - sstep(30.6, 30.85, t)) * .9);
  if (t < .25) P.fade = Math.max(P.fade, 1 - t / .25);
}
window.renderFrame = (f) => {
  const t = f / 30; const seg = TL.find(s => t >= s.t0 && t < s.t1) || TL[TL.length - 1];
  const P = { bloom: [1, .5, .7], exposure: 1, tone: 'aces', vignette: .5, grain: .04, sat: 1, contrast: 1, flash: [1, 1, 1, 0], fade: 0, zoom: 0, ca: 0, glitch: 0, tint: [1, 1, 1] };
  ctx.setTransform(SC, 0, 0, SC, 0, 0); ctx.clearRect(0, 0, 1080, 1920);
  seg.o.update(t - seg.t0, P, O); transitions(t, P);
  rp.scene = seg.o.scene; rp.camera = seg.o.cam;
  [bloom.strength, bloom.radius, bloom.threshold] = P.bloom;
  renderer.toneMapping = P.tone === 'none' ? THREE.NoToneMapping : THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = P.exposure;
  const u = fin.uniforms; u.uTime.value = t; u.uZoom.value = P.zoom; u.uCA.value = P.ca; u.uGlitch.value = P.glitch; u.uFlash.value.set(...P.flash); u.uFade.value = P.fade; u.uVig.value = P.vignette; u.uGrain.value = P.grain; u.uSat.value = P.sat; u.uCon.value = P.contrast; u.uTint.value.set(...P.tint);
  otex.needsUpdate = true; composer.render();
  return renderer.domElement.toDataURL('image/jpeg', .94);
};
const fonts = [['900', 'Montserrat_900Black'], ['800', 'Montserrat_800ExtraBold'], ['700', 'Montserrat_700Bold'], ['600', 'Montserrat_600SemiBold']].map(([w, f]) => new FontFace('Mont', `url(/fonts/${f}.ttf)`, { weight: w }).load().then(ff => document.fonts.add(ff)));
Promise.all([loaded, ...fonts]).then(() => { window.READY = true; });
