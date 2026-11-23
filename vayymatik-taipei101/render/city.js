import * as THREE from 'three';
import { Sky } from 'three/addons/objects/Sky.js';
import { DEG, clamp, lerp, sstep, eio, ein, eout, rng, vnoise2, canvasTex } from './lib.js';
// ---------- Taipei 101 geometrisi (şematik ölçüler, metre) ----------
export const TOP = 508, DAMP_Y = 372;
const N = .14;
export const POLY = [[-1+2*N,-1],[1-2*N,-1],[1-2*N,-1+N],[1-N,-1+N],[1-N,-1+2*N],[1,-1+2*N],[1,1-2*N],[1-N,1-2*N],[1-N,1-N],[1-2*N,1-N],[1-2*N,1],[-1+2*N,1],[-1+2*N,1-N],[-1+N,1-N],[-1+N,1-2*N],[-1,1-2*N],[-1,-1+2*N],[-1+N,-1+2*N],[-1+N,-1+N],[-1+2*N,-1+N]];
export function loft(poly, y0, s0, y1, s1, vrep = 1, caps = true) {
  const pos = [], uv = [], n = poly.length; let per = 0; const cum = [0];
  for (let i = 0; i < n; i++) { const a = poly[i], b = poly[(i + 1) % n]; per += Math.hypot(b[0] - a[0], b[1] - a[1]) * (s0 + s1) / 2; cum.push(per); }
  const tri = (A, B, C, ua, ub, uc, out) => { const e1 = new THREE.Vector3().subVectors(B, A), e2 = new THREE.Vector3().subVectors(C, A); const nn = e1.cross(e2); if (nn.dot(out) < 0) { [B, C] = [C, B]; [ub, uc] = [uc, ub]; } pos.push(...A.toArray(), ...B.toArray(), ...C.toArray()); uv.push(...ua, ...ub, ...uc); };
  for (let i = 0; i < n; i++) { const a = poly[i], b = poly[(i + 1) % n];
    const A = new THREE.Vector3(a[0] * s0, y0, a[1] * s0), B = new THREE.Vector3(b[0] * s0, y0, b[1] * s0), C = new THREE.Vector3(b[0] * s1, y1, b[1] * s1), D = new THREE.Vector3(a[0] * s1, y1, a[1] * s1);
    const out = new THREE.Vector3((a[0] + b[0]) / 2, 0, (a[1] + b[1]) / 2); const u0 = cum[i] / 12, u1 = cum[i + 1] / 12;
    tri(A, B, C, [u0, 0], [u1, 0], [u1, vrep], out); tri(A, C, D, [u0, 0], [u1, vrep], [u0, vrep], out); }
  const tris = THREE.ShapeUtils.triangulateShape(poly.map(p => new THREE.Vector2(p[0], p[1])), []);
  if (caps) for (const [y, s, up] of [[y1, s1, 1], [y0, s0, -1]]) for (const t of tris) { const P = t.map(k => new THREE.Vector3(poly[k][0] * s, y, poly[k][1] * s)); tri(P[0], P[1], P[2], [0, 0], [0, 0], [0, 0], new THREE.Vector3(0, up, 0)); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); g.computeVertexNormals(); return g;
}
// Kule parçaları: [geometri, tür]  tür: 'g' cam, 'f' çerçeve, 'o' süs
export function towerParts() {
  const P = [];
  P.push([loft(POLY, 0, 31, 112, 24.5, 26 / 8), 'g']);
  P.push([loft(POLY, 112, 25.6, 117, 25.6, .2), 'f']);
  for (let i = 0; i < 8; i++) { const y0 = 117 + i * 34; P.push([loft(POLY, y0, 21.5, y0 + 33.2, 25.4, 1), 'g']); P.push([loft(POLY, y0 + 33.2, 26.1, y0 + 34, 26.1, .1), 'f']); }
  P.push([loft(POLY, 389, 17.5, 411, 16, 5 / 8), 'g']); P.push([loft(POLY, 411, 16.8, 413, 16.8, .1), 'f']);
  P.push([loft(POLY, 413, 13.5, 432, 12.5, 4 / 8), 'g']); P.push([loft(POLY, 432, 13.2, 434, 13.2, .1), 'f']);
  P.push([loft(POLY, 434, 10, 449, 9, 3 / 8), 'g']);
  const sp = new THREE.CylinderGeometry(4.5, 5.5, 12, 24); sp.translate(0, 455, 0); P.push([sp, 'f']);
  const sp2 = new THREE.CylinderGeometry(.45, 2.3, 48, 16); sp2.translate(0, 485, 0); P.push([sp2, 'f']);
  for (const y of [466, 474, 482]) { const r = new THREE.CylinderGeometry(2.6 - (y - 466) * .05, 2.6 - (y - 466) * .05, 1.2, 16); r.translate(0, y, 0); P.push([r, 'f']); }
  for (let k = 0; k < 4; k++) { const d = new THREE.TorusGeometry(5.2, 1.0, 12, 32); const a = k * Math.PI / 2; d.rotateY(a); d.translate(Math.sin(a) * 25.2, 108, Math.cos(a) * 25.2); P.push([d, 'o']); }
  return P;
}
// ---------- Doku üreticileri ----------
function facade(night) {
  const r = rng(night ? 8 : 7);
  return canvasTex(512, 1024, (g, w, h) => {
    for (let f = 0; f < 8; f++) for (let p = 0; p < 8; p++) { const x = p * 64, y = f * 128, k = .82 + r() * .3;
      if (night) { const lit = r() < .6; g.fillStyle = lit ? `rgba(255,${200 + r() * 40 | 0},${130 + r() * 50 | 0},${.45 + r() * .5})` : '#000'; g.fillRect(x, y, 64, 112); }
      else { const gr = g.createLinearGradient(x, y, x + 64, y + 128); gr.addColorStop(0, `rgb(${70 * k | 0},${118 * k | 0},${118 * k | 0})`); gr.addColorStop(1, `rgb(${34 * k | 0},${72 * k | 0},${82 * k | 0})`); g.fillStyle = gr; g.fillRect(x, y, 64, 128); } }
    g.fillStyle = night ? '#000' : '#203033'; for (let f = 0; f < 8; f++) g.fillRect(0, f * 128 + 112, w, 16);
    g.fillStyle = night ? '#000' : '#a9b7bb'; for (let p = 0; p < 8; p++) g.fillRect(p * 64, 0, 3, h);
  });
}
// ---------- Gökyüzü + şehir + kule ----------
let CITY = null;
export function city(renderer) {
  if (CITY) return CITY;
  const scene = new THREE.Scene();
  const sky = new Sky(); sky.scale.setScalar(40000); scene.add(sky);
  const su = sky.material.uniforms; su.turbidity.value = 7; su.rayleigh.value = 1.5; su.mieCoefficient.value = .006; su.mieDirectionalG.value = .86;
  const sunDir = new THREE.Vector3(), setSun = (el, az) => { sunDir.setFromSphericalCoords(1, (90 - el) * DEG, az * DEG); su.sunPosition.value.copy(sunDir); };
  const pm = new THREE.PMREMGenerator(renderer), envScene = new THREE.Scene(); envScene.add(sky.clone());
  setSun(9, 235); const envDay = pm.fromScene(envScene).texture; setSun(-1.5, 245); const envDusk = pm.fromScene(envScene).texture;
  scene.fog = new THREE.FogExp2(0xd8b89a, .00021);
  const sunL = new THREE.DirectionalLight(0xffd2a0, 3.0); scene.add(sunL); const hemi = new THREE.HemisphereLight(0x9ab8d8, 0x4a3a2a, .7); scene.add(hemi);
  // Zemin
  const road = canvasTex(512, 512, (g, w) => { g.fillStyle = '#3b3b3a'; g.fillRect(0, 0, w, w); g.fillStyle = '#545350'; g.fillRect(28, 28, w - 56, w - 56); g.fillStyle = '#4a4a48'; for (let i = 0; i < 40; i++) g.fillRect(40 + (i * 97) % 420, 40 + (i * 61) % 420, 30, 30); g.fillStyle = '#d9d2b0'; for (let x = 0; x < w; x += 32) g.fillRect(x, 12, 14, 2); });
  road.wrapS = road.wrapT = THREE.RepeatWrapping; road.repeat.set(150, 150);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(30000, 30000), new THREE.MeshStandardMaterial({ map: road, roughness: .95, color: 0x77736e })); ground.rotation.x = -Math.PI / 2; scene.add(ground);
  const plaza = new THREE.Mesh(new THREE.CircleGeometry(110, 64), new THREE.MeshStandardMaterial({ color: 0x8a8378, roughness: .8 })); plaza.rotation.x = -Math.PI / 2; plaza.position.y = .2; scene.add(plaza);
  const mall = new THREE.Mesh(new THREE.BoxGeometry(150, 36, 70), new THREE.MeshStandardMaterial({ color: 0x5d6b70, roughness: .35, metalness: .5 })); mall.position.set(-20, 18, 75); scene.add(mall);
  // Şehir blokları (pencereler dünya koordinatından prosedürel)
  const box = new THREE.BoxGeometry(1, 1, 1); box.translate(0, .5, 0);
  const cm = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: .6, metalness: .25 }); const U = { uNight: { value: 0 } };
  cm.onBeforeCompile = (sh) => { Object.assign(sh.uniforms, U);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP; varying vec3 vWN; varying float vSeed;').replace('#include <project_vertex>', `#include <project_vertex>
      mat4 imx = modelMatrix * instanceMatrix; vWP = (imx * vec4(transformed,1.)).xyz; vWN = normalize(mat3(imx) * objectNormal); vec4 o = imx * vec4(0.,0.,0.,1.); vSeed = fract(sin(dot(o.xz, vec2(12.9898,78.233)))*43758.5453);`);
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP; varying vec3 vWN; varying float vSeed; uniform float uNight; float W_;')
      .replace('#include <map_fragment>', `#include <map_fragment>
      vec3 an = abs(normalize(vWN)); float roof = step(.6, an.y); float hu = an.x > an.z ? vWP.z : vWP.x; vec2 cell = vec2(hu / 3.2, vWP.y / 3.6); vec2 ff = fract(cell);
      W_ = step(.14, ff.x) * step(ff.x, .86) * step(.24, ff.y) * step(ff.y, .86) * (1. - roof) * step(2.5, vWP.y);
      float hh = fract(sin(dot(floor(cell) + vSeed * 91., vec2(127.1, 311.7))) * 43758.5453);
      diffuseColor.rgb = mix(diffuseColor.rgb, vec3(.1,.13,.16) + .12 * hh, W_ * .85);`)
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
      totalEmissiveRadiance += vec3(1., .74, .42) * W_ * step(.45, fract(hh * 7.3)) * uNight * 1.3;`); };
  const r = rng(3), NB = 1400, inst = new THREE.InstancedMesh(box, cm, NB); const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), C = new THREE.Color();
  let k = 0; while (k < NB) { const a = r() * 6.283, d = 140 + Math.pow(r(), 1.6) * 4200, x = Math.cos(a) * d, z = Math.sin(a) * d; if (Math.abs(x % 120) < 14 || Math.abs(z % 120) < 14) continue;
    const near = Math.max(0, 1 - d / 1400), h = 12 + Math.pow(r(), 2.2) * (60 + near * 190) + (r() < .04 * near ? 120 : 0), w = 18 + r() * 34, dd = 18 + r() * 34;
    M.compose(new THREE.Vector3(x, 0, z), Q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.round(r()) * .0), new THREE.Vector3(w, h, dd)); inst.setMatrixAt(k, M);
    C.setHSL(.06 + r() * .5, .06 + r() * .14, .2 + r() * .26); inst.setColorAt(k, C); k++; }
  scene.add(inst);
  // Dağlar
  const nz = vnoise2(4), mg = new THREE.RingGeometry(4500, 16000, 240, 10); mg.rotateX(-Math.PI / 2); const mp = mg.attributes.position;
  for (let i = 0; i < mp.count; i++) { const x = mp.getX(i), z = mp.getZ(i), d = Math.hypot(x, z); mp.setY(i, sstep(4500, 7000, d) * (nz(x * .0006, z * .0006) * 900 + nz(x * .002, z * .002) * 250) * (.6 + .4 * Math.sin(Math.atan2(z, x) * 2 + 1))); }
  mg.computeVertexNormals(); scene.add(new THREE.Mesh(mg, new THREE.MeshStandardMaterial({ color: 0x334434, roughness: 1 })));
  // Kule
  const glass = new THREE.MeshStandardMaterial({ map: facade(false), emissiveMap: facade(true), emissive: 0xffffff, emissiveIntensity: 0, metalness: .6, roughness: .13, envMapIntensity: 1.5 });
  glass.map.wrapS = glass.map.wrapT = glass.emissiveMap.wrapS = glass.emissiveMap.wrapT = THREE.RepeatWrapping;
  const frame = new THREE.MeshStandardMaterial({ color: 0x46565b, metalness: .75, roughness: .35 }), orn = new THREE.MeshStandardMaterial({ color: 0xc9a24a, metalness: 1, roughness: .3 });
  const tower = new THREE.Group(); for (const [g, t] of towerParts()) tower.add(new THREE.Mesh(g, t === 'g' ? glass : t === 'f' ? frame : orn)); scene.add(tower);
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(.9, 12, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(8, 1, .6) })); beacon.position.y = TOP + .5; scene.add(beacon);
  const look = (mode) => { const d = mode === 'sunset'; setSun(d ? 3.2 : 9, d ? 242 : 235); scene.environment = envDay; sunL.position.copy(sunDir).multiplyScalar(2000); sunL.intensity = d ? 2.4 : 3.0; sunL.color.set(d ? 0xffb070 : 0xffd2a0); hemi.intensity = d ? .55 : .7;
    scene.fog.color.set(d ? 0xd89a7a : 0xd8b89a); U.uNight.value = 0; glass.emissiveIntensity = 0; };
  return CITY = { scene, tower, look, glass, beacon };
}
const camAt = (cam, p, l, fov) => { cam.position.copy(p); cam.lookAt(l); if (fov) cam.fov = fov; cam.updateProjectionMatrix(); };
const path = (pts, u) => new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p))).getPoint(clamp(u));
// SAHNE 1: sokaktan hızlı yükseliş
export function scene1(renderer) {
  const C = city(renderer), cam = new THREE.PerspectiveCamera(70, 1080 / 1920, 1, 40000);
  return { scene: C.scene, cam, update(t, P, O) { C.look('day');
    const u = eout(clamp(t / 4.6)), a = .55 + u * 1.25, rad = lerp(62, 165, u), y = lerp(3, 470, u);
    camAt(cam, new THREE.Vector3(Math.cos(a) * rad, y, Math.sin(a) * rad), new THREE.Vector3(0, lerp(250, 430, u), 0), lerp(78, 46, u));
    C.beacon.visible = Math.floor(t * 2) % 2 === 0;
    Object.assign(P, { bloom: [.55, .5, .85], exposure: .52, tone: 'aces', vignette: .5, grain: .03, sat: 1.16, contrast: 1.13, zoom: .35 * (1 - sstep(0, 1.6, t)) });
  } };
}
// SAHNE 2: üst katlara yaklaş, cam cepheye dal
export function scene2(renderer) {
  const C = city(renderer), cam = new THREE.PerspectiveCamera(50, 1080 / 1920, .5, 40000);
  const pts = [[150, 330, -150], [95, 360, -105], [35, 372, -62], [3, 374, -27.5]], lks = [[0, 395, 0], [0, 385, 0], [0, 376, -10], [0, 374, 0]];
  return { scene: C.scene, cam, update(t, P, O) { C.look('day');
    const u = eio(clamp(t / 4.2)); camAt(cam, path(pts, u), path(lks, u), lerp(48, 62, sstep(3.2, 4.2, t)));
    Object.assign(P, { bloom: [.55, .5, .85], exposure: .55, tone: 'aces', vignette: .45, grain: .03, sat: 1.08, contrast: 1.06 });
    O.label(new THREE.Vector3(0, TOP - 8, 0), cam, ['Taipei 101', '508 m · Tayvan'], sstep(.6, 1.0, t) * (1 - sstep(2.8, 3.1, t)), { dx: -260, dy: 220, color: '#ffd23f', yr: [380, 1160] });
  } };
}
// SAHNE 6: alacakaranlıkta geri çekil + logo
export function scene6(renderer) {
  const C = city(renderer), cam = new THREE.PerspectiveCamera(45, 1080 / 1920, 1, 40000);
  return { scene: C.scene, cam, update(t, P, O) { C.look('sunset');
    const u = eout(clamp(t / 6.5)), a = 2.2 + t * .06, rad = lerp(70, 900, u);
    camAt(cam, new THREE.Vector3(Math.cos(a) * rad, lerp(380, 520, u), Math.sin(a) * rad), new THREE.Vector3(0, lerp(375, 250, u), 0), lerp(55, 42, u));
    C.beacon.visible = Math.floor(t * 2) % 2 === 0;
    Object.assign(P, { bloom: [.6, .5, .82], exposure: .55, tone: 'aces', vignette: .5, grain: .03, sat: 1.1, contrast: 1.05 });
    O.logo(sstep(2.6, 3.2, t), t - 2.6, sstep(3.3, 3.6, t));
  } };
}
