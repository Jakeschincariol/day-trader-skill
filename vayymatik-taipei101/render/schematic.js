import * as THREE from 'three';
import { DEG, clamp, lerp, sstep, eio, ein, eout, rng, canvasTex, softDot } from './lib.js';
import { towerParts, DAMP_Y, TOP, loft, POLY } from './city.js';
const SWAY_VS = `uniform float uSway; varying vec3 vN; varying vec3 vV; void main(){ vec3 p = position; p.x += uSway * pow(max(p.y,0.)/508., 2.); vec4 mv = modelViewMatrix * vec4(p,1.); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`;
function xmat(U, col, op) { return new THREE.ShaderMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, uniforms: { uSway: U, uCol: { value: new THREE.Color(col) }, uOp: { value: op } }, vertexShader: SWAY_VS,
  fragmentShader: `uniform vec3 uCol; uniform float uOp; varying vec3 vN; varying vec3 vV; void main(){ float f = 1. - abs(dot(normalize(vN), normalize(vV))); gl_FragColor = vec4(uCol * (pow(f, 2.5) * .8 + .05) * uOp, 1.); }` }); }
function lmat(U, col, op) { return new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { uSway: U, uCol: { value: new THREE.Color(col) }, uOp: { value: op } },
  vertexShader: `uniform float uSway; void main(){ vec3 p = position; p.x += uSway * pow(max(p.y,0.)/508., 2.); gl_Position = projectionMatrix * modelViewMatrix * vec4(p,1.); }`, fragmentShader: `uniform vec3 uCol; uniform float uOp; void main(){ gl_FragColor = vec4(uCol*uOp,1.); }` }); }
const swayAt = (s, y) => s * Math.pow(y / 508, 2);
let PARTS = null, EDGES = null;
export function xrayTower(col = 0x4fd8ff, ballScale = 1) {
  PARTS = PARTS || towerParts(); EDGES = EDGES || PARTS.map(([g]) => new THREE.EdgesGeometry(g, 25));
  const U = { value: 0 }, grp = new THREE.Group(); const fm = xmat(U, col, .55), em = lmat(U, col, .5);
  PARTS.forEach(([g], i) => { grp.add(new THREE.Mesh(g, fm)); grp.add(new THREE.LineSegments(EDGES[i], em)); });
  const band = new THREE.Mesh(loft(POLY, 365, 25.3, 387, 25.9, 1, false), xmat(U, 0xffc23a, .7)); grp.add(band);
  const ball = new THREE.Mesh(new THREE.SphereGeometry(2.75 * ballScale, 48, 32), new THREE.MeshBasicMaterial({ color: new THREE.Color(1.5, 1.0, .25) })); grp.add(ball);
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: softDot(), color: 0xffb030, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: .8 })); glow.scale.setScalar(16 * ballScale); grp.add(glow);
  const lines = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0xffe2a0, transparent: true, opacity: .9 })); grp.add(lines);
  const set = (s, rel) => { U.value = s; const bx = swayAt(s, DAMP_Y) + rel, ax = swayAt(s, 386), fx = swayAt(s, 365); ball.position.set(bx, DAMP_Y, 0); glow.position.copy(ball.position);
    const R = 2.75 * ballScale, v = []; for (const z of [-1.6, 1.6]) v.push(bx + (z > 0 ? 1 : -1) * R * .6, DAMP_Y + R * .4, z, ax, 386, z); for (const sx of [-1, 1]) v.push(bx + sx * R * .7, DAMP_Y - R * .7, 0, fx + sx * 7, 365.5, 0);
    lines.geometry.setAttribute('position', new THREE.Float32BufferAttribute(v, 3)); };
  return { grp, set, U, ball, fm, em, band, glow };
}
// Rüzgâr çizgileri (kamera +z'den bakarken xy düzleminde)
function wind(n, seed) {
  const r = rng(seed), d = Array.from({ length: n }, () => ({ x: r() * 900, y: 60 + r() * 480, z: (r() - .5) * 160, l: 25 + r() * 70, v: 140 + r() * 120, w: .5 + r() * 1.1, a: .25 + r() * .6 }));
  const m = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { uI: { value: 0 } }, vertexShader: `attribute float aA; varying vec2 vUv; varying float vA; void main(){ vUv = uv; vA = aA; gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position,1.); }`,
    fragmentShader: `uniform float uI; varying vec2 vUv; varying float vA; void main(){ float a = smoothstep(0.,1.,vUv.x) * (1.-smoothstep(.85,1.,vUv.x)) * (1. - abs(vUv.y-.5)*2.); gl_FragColor = vec4(vec3(.75,.9,1.) * a * vA * uI, 1.); }` });
  const g = new THREE.PlaneGeometry(1, 1); g.setAttribute('aA', new THREE.InstancedBufferAttribute(new Float32Array(d.map(o => o.a)), 1));
  const im = new THREE.InstancedMesh(g, m, n); im.frustumCulled = false; const M = new THREE.Matrix4();
  im.userData.step = (t, I) => { m.uniforms.uI.value = I; d.forEach((o, i) => { const x = ((o.x + t * o.v) % 900) - 450, near = Math.exp(-((x / 45) ** 2)) * Math.max(0, 1 - Math.abs(o.z) / 60);
    M.makeScale(o.l, o.w, 1).setPosition(x, o.y + near * 8 * Math.sign(o.y - 300), o.z + Math.sign(o.z || 1) * near * 30); im.setMatrixAt(i, M); }); im.instanceMatrix.needsUpdate = true; };
  return im;
}
function grid() { const t = canvasTex(512, 512, (g, w) => { g.fillStyle = '#030a14'; g.fillRect(0, 0, w, w); g.strokeStyle = 'rgba(60,140,190,.22)'; g.lineWidth = 2; for (let x = 0; x <= w; x += 64) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, w); g.stroke(); g.beginPath(); g.moveTo(0, x); g.lineTo(w, x); g.stroke(); } });
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(30, 20); const p = new THREE.Mesh(new THREE.PlaneGeometry(3000, 2000), new THREE.MeshBasicMaterial({ map: t })); p.position.set(0, 300, -120); return p; }
const OM = 2 * Math.PI / 2.4;
const hwAt = y => y < 355 ? lerp(21.5, 25.4, (y - 321) / 33.2) : y < 388.2 ? lerp(21.5, 25.4, (y - 355) / 33.2) : lerp(17.5, 16, (y - 389) / 22);
// SAHNE 3B: kürenin asılı olduğu katlar (87–92) – röntgen görünümü
export function floorsScene(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x030a14); scene.add(grid());
  const X = xrayTower(0x4fd8ff, 1); scene.add(X.grp); X.set(0, 0); X.fm.uniforms.uOp.value = .3; X.band.visible = false;
  const rings = {}; for (let f = 84; f <= 95; f++) { const y = f * 4.2, hw = hwAt(y) + .4; const m = new THREE.Mesh(loft(POLY, y, hw, y + .45, hw, 1, false), new THREE.MeshBasicMaterial({ color: 0x4fd8ff, transparent: true, opacity: .5, blending: THREE.AdditiveBlending, depthWrite: false })); scene.add(m); rings[f] = m; }
  const cam = new THREE.PerspectiveCamera(40, 1080 / 1920, 1, 5000); const W = (w, d) => (window.WT && window.WT(w)) ?? d;
  const t87 = W("87'nci", 17.0) - 16.3, t92 = W("92'nci", 17.7) - 16.3;
  return { scene, cam, update(t, P, O) {
    const a = .75 - t * .09, r = lerp(120, 92, eout(clamp(t / 4))); cam.position.set(Math.sin(a) * r, 381, Math.cos(a) * r); cam.lookAt(0, 375, 0); cam.updateProjectionMatrix();
    for (const [f, m] of Object.entries(rings)) { const hot = (f == 87 && t > t87 - .1) || (f == 92 && t > t92 - .1); m.material.color.set(hot ? 0xffc23a : 0x4fd8ff); m.material.opacity = hot ? 1 : (f >= 87 && f <= 92 ? .55 : .25); }
    Object.assign(P, { bloom: [.7, .45, .6], exposure: 1, tone: 'none', vignette: .5, grain: .03, sat: 1.05, contrast: 1.05 });
    const A = (s, e) => sstep(s, s + .3, t) * (1 - sstep(e, e + .3, t));
    for (const f of [87, 88, 89, 90, 91, 92]) { const hot = (f === 87 && t > t87 - .1) || (f === 92 && t > t92 - .1); const y = f * 4.2, hw = hwAt(y) + .4;
      O.tag(new THREE.Vector3(-hw * Math.cos(a) - 2, y + .2, hw * Math.sin(a)).add(new THREE.Vector3(-Math.cos(a) * 6, 0, Math.sin(a) * 6)), cam, `${f}. KAT`, A(.2 + (92 - f) * .07, 4.2) * (hot || f === 87 || f === 92 ? 1 : .55), hot); }
    O.label(X.ball.position, cam, ['Sönümleyici küre', '660 ton · Ø 5,5 m'], A(.5, 4.2), { dx: 140, dy: 300, color: '#ffd23f', yr: [380, 1150] });
  } };
}
// SAHNE 4: rüzgâr, salınım ve kürenin ters yönlü hareketi
export function windScene(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x030a14); scene.add(grid());
  const X = xrayTower(0x4fd8ff, 1.6); scene.add(X.grp); const W = wind(260, 4); scene.add(W);
  const cam = new THREE.PerspectiveCamera(40, 1080 / 1920, 1, 5000);
  const sway = t => 9 * sstep(.3, 2.2, t) * Math.sin(OM * t), rel = t => -6.5 * sstep(.6, 2.6, t) * Math.sin(OM * t - .45);
  return { scene, cam, update(t, P, O) {
    const s = sway(t), r = rel(t); X.set(s, r); W.userData.step(t, sstep(0, 1.2, t)); const cd = cam.position.distanceTo(X.ball.position); X.fm.uniforms.uOp.value = lerp(.1, .55, sstep(70, 420, cd)); X.em.uniforms.uOp.value = lerp(.22, .5, sstep(70, 420, cd)); X.band.material.uniforms.uOp.value = lerp(.25, .7, sstep(70, 420, cd)); X.glow.material.opacity = lerp(.35, .8, sstep(70, 420, cd));
    const u = eio(clamp((t - 2.6) / 3.2)), v = eio(clamp((t - 6.2) / 2.4));
    cam.position.set(lerp(0, swayAt(s, DAMP_Y) * .5, u), lerp(265, DAMP_Y, u), lerp(860, 200, u) - v * 95); cam.lookAt(lerp(0, swayAt(s, DAMP_Y) * .6, u), lerp(265, DAMP_Y + 6, u), 0); cam.updateProjectionMatrix();
    Object.assign(P, { bloom: [.7, .45, .62], exposure: 1, tone: 'none', vignette: .5, grain: .03, sat: 1.05, contrast: 1.05 });
    O.badge('TEMSİLİ CANLANDIRMA · SALINIM ABARTILI', 540, 210, sstep(.1, .4, t), '#4fe3ff');
    const vb = 9 * OM * Math.cos(OM * t), vr = -6.5 * OM * Math.cos(OM * t - .45);
    const top = new THREE.Vector3(swayAt(s, 425), 425, 0), ball = X.ball.position.clone();
    O.arrowW(top, cam, Math.sign(vb) * Math.min(1, Math.abs(vb) / 20), '#ff5a4a', 'BİNA', sstep(1.2, 1.6, t));
    O.arrowW(ball, cam, Math.sign(vr) * Math.min(1, Math.abs(vr) / 14), '#ffc23a', 'KÜRE', sstep(3.6, 4.0, t));
    O.windTag(sstep(.2, .6, t) * (1 - sstep(2.4, 2.8, t)));
    O.label(X.ball.position, cam, ['Salınım sınırı ~150 cm', 'tampon halkası ile'], sstep(6.6, 7.0, t), { dx: 120, dy: 330, color: '#ffd23f', yr: [380, 1150] });
  } };
}
// SAHNE 5: bölünmüş ekran karşılaştırma (şematik)
export function splitScene(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x030a14); scene.add(grid());
  const A = xrayTower(0xff6a5a, 0), B = xrayTower(0x4fffb0, 1.6); A.grp.position.x = -62; B.grp.position.x = 62; A.grp.children.filter(c => c.type === 'Sprite' || c.type === 'LineSegments' && c.material.type === 'LineBasicMaterial').forEach(c => c.visible = false); scene.add(A.grp, B.grp);
  const cam = new THREE.PerspectiveCamera(40, 1080 / 1920, 1, 5000); cam.position.set(0, 318, 600); cam.lookAt(0, 318, 0);
  const g0 = .35, xl = t => t < g0 ? 0 : 15 * Math.exp(-.012 * OM * (t - g0)) * Math.sin(OM * (t - g0)), xr = t => t < g0 ? 0 : 15 * .62 * Math.exp(-.085 * OM * (t - g0)) * Math.sin(OM * (t - g0)), rr = t => t < g0 ? 0 : -1.3 * 15 * .62 * Math.exp(-.06 * OM * (t - g0)) * Math.sin(OM * (t - g0) - .5);
  return { scene, cam, update(t, P, O) {
    A.set(xl(t), 0); B.set(xr(t), rr(t));
    Object.assign(P, { bloom: [.85, .5, .55], exposure: 1, tone: 'none', vignette: .45, grain: .03, sat: 1.05, contrast: 1.05 });
    O.badge('ŞEMATİK KARŞILAŞTIRMA · ÖLÇEKLİ DEĞİLDİR', 540, 210, sstep(0, .3, t), '#9fb3c8');
    O.split(t, xl, xr, 7.6);
  } };
}
