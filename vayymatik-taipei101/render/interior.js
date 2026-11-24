import * as THREE from 'three';
import { DEG, clamp, lerp, sstep, eio, ein, eout, rng, canvasTex, softDot, envFrom, pointsGeo, particleMat } from './lib.js';
// İç mekân: sönümleyici küre (merkez = 0,0,0). Kat döşemeleri (üst yüzey) 87..92
const at = (m, p) => (m.position.copy(p), m);
export const FL = { 87: -5.4, 88: -1.2, 89: 3.0, 90: 7.2, 91: 11.4, 92: 15.6 }; const R = 2.75;
function seamTex() { // 41 plaka (12,5 cm) dikişleri: y = -2.5625 + k*0.125  ->  v = 0.5 + asin(y/R)/pi
  return canvasTex(64, 2048, (g, w, h) => { g.fillStyle = '#e0ad35'; g.fillRect(0, 0, w, h); const r = rng(2);
    for (let i = 0; i < 300; i++) { g.fillStyle = `rgba(${150 + r() * 80 | 0},${100 + r() * 50 | 0},20,.12)`; g.fillRect(0, r() * h, w, 1 + r() * 4); }
    for (let k = 0; k <= 41; k++) { const y = -2.5625 + k * .125; if (Math.abs(y) >= R) continue; const v = .5 + Math.asin(y / R) / Math.PI; g.fillStyle = 'rgba(70,45,8,.85)'; g.fillRect(0, (1 - v) * h - 1.5, w, 3); } });
}
function slab(y, hole, size = 48) {
  const s = new THREE.Shape(); s.moveTo(-size / 2, -size / 2); s.lineTo(size / 2, -size / 2); s.lineTo(size / 2, size / 2); s.lineTo(-size / 2, size / 2); s.closePath();
  if (hole) { const p = new THREE.Path(); p.absarc(0, 0, hole, 0, Math.PI * 2, true); s.holes.push(p); }
  const g = new THREE.ExtrudeGeometry(s, { depth: .55, bevelEnabled: false, curveSegments: 64 }); g.rotateX(Math.PI / 2); g.translate(0, y, 0); return g;
}
function rod(a, b, r, mat, seg = 12) { const d = b.clone().sub(a), m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, d.length(), seg), mat); m.position.copy(a).add(b).multiplyScalar(.5); m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize()); return m; }
export function interior(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x0b0906); scene.fog = new THREE.FogExp2(0x0b0906, .009);
  scene.environment = envFrom(renderer, '#6b5236', '#1e170f', '#050403', [.5, .3]);
  const gold = new THREE.MeshStandardMaterial({ map: seamTex(), metalness: .72, roughness: .48, color: 0xffffff });
  const sphere = new THREE.Mesh(new THREE.SphereGeometry(R, 160, 120), gold); scene.add(sphere);
  const steel = new THREE.MeshStandardMaterial({ color: 0x5a636b, metalness: .8, roughness: .38 }), dark = new THREE.MeshStandardMaterial({ color: 0x2a2f35, metalness: .6, roughness: .55 });
  const yel = new THREE.MeshStandardMaterial({ color: 0xd9a12b, metalness: .7, roughness: .35 }), chrome = new THREE.MeshStandardMaterial({ color: 0xdde3e8, metalness: 1, roughness: .15 });
  const concrete = new THREE.MeshStandardMaterial({ color: 0xaaa49a, roughness: .9 });
  const cradle = new THREE.Mesh(new THREE.TorusGeometry(2.92, .17, 16, 128), yel); cradle.rotation.x = Math.PI / 2; cradle.position.y = .35; scene.add(cradle);
  // 92 çelik halat: 4 grup x 23
  const cab = new THREE.InstancedMesh(new THREE.CylinderGeometry(.0445, .0445, 1, 8), steel, 92); let ci = 0; const M = new THREE.Matrix4(), Y = new THREE.Vector3(0, 1, 0);
  for (let gq = 0; gq < 4; gq++) { const az = (45 + gq * 90) * DEG, c = Math.cos(az), s = Math.sin(az); scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(.9, .5, .9), yel), new THREE.Vector3(c * 3.05, .45, s * 3.05)));
    for (let i = 0; i < 25 && ci < 92; i++) { if (i === 0 || i === 24) continue; const ox = (i % 5 - 2) * .16, oz = (Math.floor(i / 5) - 2) * .16;
      const a = new THREE.Vector3(c * 3.05 + ox, .7, s * 3.05 + oz), b = new THREE.Vector3(c * 3.45 + ox, FL[92] - .55, s * 3.45 + oz), d = b.clone().sub(a);
      M.compose(a.clone().add(b).multiplyScalar(.5), new THREE.Quaternion().setFromUnitVectors(Y, d.clone().normalize()), new THREE.Vector3(1, d.length(), 1)); cab.setMatrixAt(ci++, M); }
    scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(1.4, .8, 1.4), dark), new THREE.Vector3(c * 3.45, FL[92] - .9, s * 3.45))); }
  scene.add(cab);
  // 8 hidrolik sönümleyici + tampon halkası
  for (let k = 0; k < 8; k++) { const az = (22.5 + k * 45) * DEG, th = -40 * DEG; const a = new THREE.Vector3(Math.cos(az) * Math.cos(th) * R, Math.sin(th) * R - .1, Math.sin(az) * Math.cos(th) * R), b = new THREE.Vector3(Math.cos(az) * 5.8, FL[87] + .6, Math.sin(az) * 5.8);
    const m = a.clone().lerp(b, .45); scene.add(rod(a, m, .075, chrome), rod(m, b, .2, yel, 16)); const cl = new THREE.Mesh(new THREE.SphereGeometry(.16, 12, 8), dark); cl.position.copy(b); scene.add(cl);
    scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(.7, .5, .7), dark), b.clone().setY(FL[87] + .25))); }
  const bump = new THREE.Mesh(new THREE.TorusGeometry(1.95, .2, 14, 80), steel); bump.rotation.x = Math.PI / 2; bump.position.y = -3.25; scene.add(bump);
  const ped = new THREE.Mesh(new THREE.CylinderGeometry(.5, .9, FL[87] + 3.1 - FL[87], 24), dark); ped.position.y = (FL[87] - 3.1) / 2 + .1; scene.add(ped);
  // Katlar, kolonlar, korkuluklar, cephe
  for (const [f, y] of Object.entries(FL)) scene.add(new THREE.Mesh(slab(y, f == 87 || f == 92 ? 0 : (f == 88 ? 4.2 : 6.2)), concrete));
  for (let k = 0; k < 8; k++) { const a = (k * 45 + 22.5) * DEG; scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(1.3, 22, 1.3), dark), new THREE.Vector3(Math.cos(a) * 12, 5, Math.sin(a) * 12))); }
  const rail = new THREE.MeshStandardMaterial({ color: 0x9fb4c0, transparent: true, opacity: .22, roughness: .05, metalness: .2 });
  for (const f of [89, 90, 91]) { const rg = new THREE.CylinderGeometry(6.2, 6.2, 1.1, 64, 1, true); const m = new THREE.Mesh(rg, rail); m.position.y = FL[f] + .55; scene.add(m); const tr = new THREE.Mesh(new THREE.TorusGeometry(6.2, .05, 8, 96), chrome); tr.rotation.x = Math.PI / 2; tr.position.y = FL[f] + 1.1; scene.add(tr); }
  const win = canvasTex(256, 512, (g, w, h) => { const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, '#2a3f63'); gr.addColorStop(.55, '#d98c4c'); gr.addColorStop(1, '#3a2a22'); g.fillStyle = gr; g.fillRect(0, 0, w, h); g.fillStyle = '#121212'; for (let x = 0; x < w; x += 64) g.fillRect(x, 0, 6, h); for (let y = 0; y < h; y += 128) g.fillRect(0, y, w, 14); });
  win.wrapS = win.wrapT = THREE.RepeatWrapping; win.repeat.set(6, 4);
  for (let k = 0; k < 4; k++) { const p = new THREE.Mesh(new THREE.PlaneGeometry(48, 24), new THREE.MeshBasicMaterial({ map: win, color: 0x8a7a70 })); const a = k * Math.PI / 2; p.position.set(Math.sin(a) * 24, 5, Math.cos(a) * 24); p.rotation.y = a + Math.PI; scene.add(p); }
  // Işıklar
  scene.add(new THREE.HemisphereLight(0x6a7a90, 0x1a120a, .35)); const fill = new THREE.DirectionalLight(0xa9bcd6, 0); fill.position.set(-30, 20, -25); scene.add(fill);
  const spots = []; for (let k = 0; k < 4; k++) { const a = (k * 90 + 20) * DEG, s = new THREE.SpotLight(0xffd6a0, 0, 0, .42, .6, 1.6); s.position.set(Math.cos(a) * 9, FL[90] - .8, Math.sin(a) * 9); s.target.position.set(0, 0, 0); scene.add(s, s.target); spots.push(s); }
  const up = new THREE.SpotLight(0xffb070, 0, 0, .6, .7, 1.6); up.position.set(0, FL[87] + .8, -7); up.target.position.set(0, 0, 0); scene.add(up, up.target);
  const rr = rng(5); const dust = new THREE.Points(pointsGeo(900, (i, p, s, a) => { p[i * 3] = (rr() - .5) * 30; p[i * 3 + 1] = -5 + rr() * 20; p[i * 3 + 2] = (rr() - .5) * 30; s[i] = .02 + rr() * .04; a[i] = .2 + rr() * .6; }), particleMat({ color: 0xffd9a0, size: 1, opacity: .35 })); scene.add(dust);
  const cam = new THREE.PerspectiveCamera(55, 1080 / 1920, .05, 400);
  const W = (w, d) => (window.WT && window.WT(w)) ?? d; const T0 = 9.4;
  const tDia = W('5', 13.6) - T0, t87 = W("87'nci", 17.0) - T0, t92 = W("92'nci", 17.7) - T0;
  const keys = [[0, [0, 4.4, -22], [0, 1.4, 0], 62], [2.6, [0, 2.0, -10.5], [0, .2, 0], 50], [4.8, [7.5, 1.4, -7.2], [0, .4, 0], 50], [6.9, [-7.6, -2.0, -6.6], [0, -3.0, 0], 52]];
  const key = (t) => { let i = 0; while (i < keys.length - 2 && t > keys[i + 1][0]) i++; const [a, pa, la, fa] = keys[i], [b, pb, lb, fb] = keys[i + 1], f = eio(clamp((t - a) / (b - a)));
    return [new THREE.Vector3(...pa).lerp(new THREE.Vector3(...pb), f), new THREE.Vector3(...la).lerp(new THREE.Vector3(...lb), f), lerp(fa, fb, f)]; };
  return { scene, cam, update(t, P, O) {
    const L = sstep(.15, .9, t); spots.forEach(s => s.intensity = 115 * L); up.intensity = 70 * L; fill.intensity = 1.6 * sstep(5.4, 6.6, t) * (1 - sstep(8.8, 9.6, t));
    const sw = Math.sin(t * .9) * .03; sphere.position.x = sw; cradle.position.x = sw; sphere.rotation.y = t * .02;
    const [p, l, f] = key(t); cam.position.copy(p); cam.lookAt(l); cam.fov = f; cam.updateProjectionMatrix();
    Object.assign(P, { bloom: [.45, .5, .9], exposure: .95, tone: 'aces', vignette: .55, grain: .035, sat: 1.05, contrast: 1.08 });
    const A = (a, b) => sstep(a, a + .3, t) * (1 - sstep(b, b + .3, t));
    O.dim(new THREE.Vector3(-R, 0, 0).applyMatrix4(sphere.matrixWorld), new THREE.Vector3(R, 0, 0).applyMatrix4(sphere.matrixWorld), cam, 'Ø 5,5 m', A(tDia - .1, 5.9));
    O.label(new THREE.Vector3(.8, 1.6, -2.2), cam, ['660 ton', '41 katman · 12,5 cm çelik'], A(2.3, 4.0), { dx: 120, dy: -330, color: '#ffd23f', yr: [380, 1150] });
    O.label(new THREE.Vector3(-2.4, 9, -2.4), cam, ['92 çelik halat', 'Ø 8,9 cm · 42 m'], A(4.3, 5.9), { dx: 200, dy: -240, color: '#9fe8ff', yr: [380, 1150] });
    O.label(new THREE.Vector3(Math.cos(202 * DEG) * 4.6, FL[87] + 1.6, Math.sin(202 * DEG) * 4.6), cam, ['8 hidrolik sönümleyici'], A(5.6, 7.2), { dx: -60, dy: -420, color: '#ffd23f', yr: [380, 1150] });
  } };
}
