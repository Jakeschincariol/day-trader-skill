import * as THREE from 'three';
import { DEG, clamp, lerp, sstep, eio, ein, eout, rng, vnoise2, canvasTex, softDot, envFrom } from './lib.js';
const dirAz = (az, el = 0) => new THREE.Vector3(Math.sin(az * DEG) * Math.cos(el * DEG), Math.sin(el * DEG), -Math.cos(az * DEG) * Math.cos(el * DEG));
// ---------- Gökyüzü kubbesi: gradyan + güneş + bulut + fiziksel gökkuşağı (42°) + yıldızlar ----------
function skyDome(U) {
  const m = new THREE.ShaderMaterial({ side: THREE.BackSide, depthWrite: false, uniforms: U,
    vertexShader: `varying vec3 vD; void main(){ vD = position; vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.); gl_Position = p.xyww; }`,
    fragmentShader: `uniform vec3 uSun, uHor, uZen, uCC; uniform float uCloud, uT, uRain, uNight, uSunI; varying vec3 vD;
    float h(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
    float n(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f); return mix(mix(h(i),h(i+vec2(1,0)),f.x), mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x), f.y); }
    float fbm(vec2 p){ float s=0., a=.5; for(int i=0;i<6;i++){ s+=a*n(p); p=p*2.03+vec2(1.7,9.2); a*=.5; } return s; }
    vec3 bow(float th){ float x=(th-40.6)/1.9; return vec3(smoothstep(.5,.95,x)*smoothstep(1.2,.92,x), smoothstep(.2,.52,x)*smoothstep(.85,.52,x), smoothstep(-.15,.15,x)*smoothstep(.45,.15,x)); }
    void main(){ vec3 d = normalize(vD); float el = d.y;
      vec3 col = mix(uHor, uZen, pow(clamp(el,0.,1.), .5)); col = mix(col, uHor*.55, smoothstep(0., -.12, el));
      float sd = max(dot(d, uSun), 0.); col += vec3(1.,.72,.42) * (pow(sd, 6.)*.45 + pow(sd, 600.)*6.) * uSunI;
      float th = degrees(acos(clamp(dot(d, -uSun), -1., 1.)));
      col += (bow(th)*.6 + bow(92.5 - th)*.18) * uRain * smoothstep(-.01, .06, el) * (1. - smoothstep(.45, .7, el)) * (.6 + .4*n(d.xz*6.));
      if (el > -.02) { float e2 = max(el, .002); vec2 cp = d.xz / (e2 + .06) * 1.3 + vec2(uT*.025, uT*.012); float c = fbm(cp);
        float cov = smoothstep(1.-uCloud, 1.-uCloud+.3, c) * smoothstep(-.02, .1, el);
        float lit = .5 + .5*pow(max(dot(normalize(vec3(d.x,0.,d.z)), normalize(vec3(uSun.x,0.,uSun.z))), 0.), 1.5);
        vec3 cc = mix(uCC*.45, uCC*1.2, lit) * (.7 + .6*fbm(cp*2.7 + 3.));
        col = mix(col, cc, cov*.92); }
      vec2 sp = d.xz / (abs(el) + .35) * 220.; col += vec3(step(.9972, h(floor(sp)))) * uNight * smoothstep(.02, .25, el) * (.5 + .5*h(floor(sp)+3.));
      gl_FragColor = vec4(col, 1.); }` });
  const s = new THREE.Mesh(new THREE.SphereGeometry(1000, 64, 32), m); s.frustumCulled = false; return s;
}
// ---------- Gizemli cisim: koyu gövde + sarkan, dalgalanan kollar ----------
export function jelly(mat) {
  const g = new THREE.Group(); const pts = [];
  for (let i = 0; i <= 24; i++) { const a = i / 24 * Math.PI * .5; pts.push(new THREE.Vector2(Math.sin(a) * 2.0 * (1 + .12 * Math.sin(a * 2)), Math.cos(a) * 1.5)); }
  pts.push(new THREE.Vector2(2.15, -.15), new THREE.Vector2(1.6, -.35), new THREE.Vector2(.01, -.3));
  const bell = new THREE.Mesh(new THREE.LatheGeometry(pts, 48), mat); g.add(bell);
  const arms = []; const r = rng(4);
  for (let k = 0; k < 9; k++) { const a = k / 9 * 6.283 + r() * .3, ra = k % 3 === 0 ? .6 : 1.6; arms.push({ x: Math.cos(a) * ra, z: Math.sin(a) * ra, L: 7 + r() * 5, w: .16 + r() * .08, ph: r() * 6, f: .8 + r() * .5, m: new THREE.Mesh(new THREE.BufferGeometry(), mat) }); g.add(arms[k].m); }
  g.userData.step = (t, wind = new THREE.Vector3(0, 0, 0), amp = 1) => { for (const A of arms) { const P = [];
      for (let i = 0; i <= 14; i++) { const s = i / 14, w = Math.pow(s, 1.25) * amp; P.push(new THREE.Vector3(A.x * (1 - s * .35) + Math.sin(t * 2.1 * A.f - s * 5 + A.ph) * 1.1 * w + wind.x * s * s, -.25 - s * A.L + Math.abs(wind.x) * s * s * .3, A.z * (1 - s * .35) + Math.cos(t * 1.7 * A.f - s * 4.2 + A.ph) * .9 * w + wind.z * s * s)); }
      A.m.geometry.dispose(); A.m.geometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(P), 56, A.w, 7); const p = A.m.geometry.attributes.position, c = new THREE.CatmullRomCurve3(P);
      for (let i = 0; i <= 56; i++) { const s = i / 56, q = c.getPoint(s), k = 1 - s * .8; for (let j = 0; j <= 7; j++) { const id = i * 8 + j; p.setXYZ(id, q.x + (p.getX(id) - q.x) * k, q.y + (p.getY(id) - q.y) * k, q.z + (p.getZ(id) - q.z) * k); } } p.needsUpdate = true; } };
  return g;
}
// ---------- Ahtapot uçurtma: şişme baş, gözler, 8 şerit bacak, ip ----------
function kite() {
  const g = new THREE.Group(); const fab = new THREE.MeshStandardMaterial({ color: 0xc0306a, roughness: .7, side: THREE.DoubleSide });
  const head = new THREE.Mesh(new THREE.SphereGeometry(2, 40, 24), fab); head.scale.set(1, 1.15, 1); head.position.y = .8; g.add(head);
  for (const s of [-1, 1]) { const e = new THREE.Mesh(new THREE.SphereGeometry(.55, 20, 12), new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: .5 })); e.position.set(s * .8, .5, 1.75); e.scale.z = .4; g.add(e);
    const p = new THREE.Mesh(new THREE.SphereGeometry(.28, 16, 10), new THREE.MeshStandardMaterial({ color: 0x111111 })); p.position.set(s * .8, .45, 1.95); p.scale.z = .4; g.add(p); }
  const legs = []; for (let k = 0; k < 8; k++) { const a = k / 8 * 6.283; const m = new THREE.Mesh(new THREE.BufferGeometry(), fab); g.add(m); legs.push({ a, m, L: 10 + (k % 2) * 2.5, ph: k * .8 }); }
  const line = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial({ color: 0xe8e8e8 })); g.add(line);
  g.userData.fab = fab;
  g.userData.step = (t, wx = 6) => { for (const Lg of legs) { const N = 30, pos = [], idx = []; const c0 = new THREE.Vector3(Math.cos(Lg.a) * 1.5, -.7, Math.sin(Lg.a) * 1.5);
      for (let i = 0; i <= N; i++) { const s = i / N, wv = Math.sin(t * 3.2 - s * 7 + Lg.ph) * 1.1 * s; const cx = c0.x * (1 - s * .5) + wx * s * s + wv * .4, cy = c0.y - s * Lg.L * .75 + wx * s * s * .1, cz = c0.z * (1 - s * .5) + wv;
        const wd = .55 * (1 - s * .6), tx = -Math.sin(Lg.a), tz = Math.cos(Lg.a); pos.push(cx - tx * wd, cy, cz - tz * wd, cx + tx * wd, cy, cz + tz * wd); if (i < N) { const b = i * 2; idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2); } }
      const gg = new THREE.BufferGeometry(); gg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); gg.setIndex(idx); gg.computeVertexNormals(); Lg.m.geometry.dispose(); Lg.m.geometry = gg; }
    line.geometry.dispose(); line.geometry = new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(new THREE.Vector3(0, -.2, 0), new THREE.Vector3(-30, -60, 8), new THREE.Vector3(-90, -260, 20)), 60, .035, 5); };
  return g;
}
// ---------- Ortak sahne: Anchorage, Chugach dağları, gökyüzü ----------
let W = null;
export function world(renderer) {
  if (W) return W;
  const scene = new THREE.Scene(); const U = { uSun: { value: dirAz(315, 6) }, uHor: { value: new THREE.Color() }, uZen: { value: new THREE.Color() }, uCC: { value: new THREE.Color() }, uCloud: { value: .5 }, uT: { value: 0 }, uRain: { value: 0 }, uNight: { value: 0 }, uSunI: { value: 1 } };
  const dome = skyDome(U); scene.add(dome);
  scene.environment = envFrom(renderer, '#6a86a8', '#d9a072', '#2a2a26', [.88, .45]);
  scene.fog = new THREE.FogExp2(0xb89a88, .000055);
  const sunL = new THREE.DirectionalLight(0xffc89a, 2.6), hemi = new THREE.HemisphereLight(0x8aa4c4, 0x3a3226, .8); scene.add(sunL, hemi);
  // Dağlar (doğu)
  const nz = vnoise2(7), tg = new THREE.PlaneGeometry(90000, 90000, 360, 360); tg.rotateX(-Math.PI / 2); const tp = tg.attributes.position, col = [];
  for (let i = 0; i < tp.count; i++) { const x = tp.getX(i) + 30000, z = tp.getZ(i); const rid = 1 - Math.abs(nz(x * .00012, z * .00012) * 2 - 1);
    const r2 = 1 - Math.abs(nz(x * .0004 + 5, z * .0004) * 2 - 1); const h = sstep(5000, 12000, x) * (180 + rid * rid * 900 + r2 * r2 * r2 * 700 + nz(x * .0008, z * .0008) * 250) + nz(x * .002, z * .002) * 25; tp.setXYZ(i, x, h, z);
    const snow = sstep(1250, 1500, h + nz(x * .003, z * .003) * 260), forest = 1 - sstep(250, 650, h); const c = new THREE.Color(0x3e3d38).lerp(new THREE.Color(0x1c2e1b), forest).lerp(new THREE.Color(0xcfd6dc), snow); col.push(c.r, c.g, c.b); }
  tg.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); tg.computeVertexNormals();
  const tm = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .95, envMapIntensity: .4 }); scene.add(new THREE.Mesh(tg, tm));
  // Şehir (alçak binalar) + ağaçlar
  const box = new THREE.BoxGeometry(1, 1, 1); box.translate(0, .5, 0); const r = rng(5), NB = 2600, M = new THREE.Matrix4(), Q = new THREE.Quaternion(), C = new THREE.Color();
  const bm = new THREE.MeshStandardMaterial({ roughness: .8 }), bi = new THREE.InstancedMesh(box, bm, NB);
  for (let k = 0; k < NB; k++) { const x = -6000 + r() * 10500, z = -5000 + r() * 11000, dt = Math.hypot(x + 4200, z + 600) < 900, h = dt ? 15 + r() * 60 : 4 + r() * 9; M.compose(new THREE.Vector3(x, 0, z), Q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), r() * 1.6), new THREE.Vector3(10 + r() * 25, h, 10 + r() * 25)); bi.setMatrixAt(k, M); C.setHSL(r() < .5 ? .02 + r() * .1 : .5 + r() * .15, .15 + r() * .25, .22 + r() * .28); bi.setColorAt(k, C); }
  scene.add(bi);
  const cone = new THREE.ConeGeometry(1, 1, 7); cone.translate(0, .5, 0); const NT = 6000, ti = new THREE.InstancedMesh(cone, new THREE.MeshStandardMaterial({ color: 0x1d3320, roughness: 1 }), NT);
  for (let k = 0; k < NT; k++) { const x = -6000 + r() * 16000, z = -6000 + r() * 13000, s = 4 + r() * 8; M.compose(new THREE.Vector3(x, 0, z), Q.identity(), new THREE.Vector3(s * .35, s * 2.2, s * .35)); ti.setMatrixAt(k, M); }
  scene.add(ti);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(40000, 40000), new THREE.MeshStandardMaterial({ color: 0x3a4232, roughness: 1 })); ground.rotation.x = -Math.PI / 2; ground.position.set(-5000, -.5, 0); scene.add(ground);
  const water = new THREE.Mesh(new THREE.PlaneGeometry(30000, 20000), new THREE.MeshStandardMaterial({ color: 0x2a3a44, roughness: .15, metalness: .6 })); water.rotation.x = -Math.PI / 2; water.position.set(-12000, .2, -14000); scene.add(water);
  // Cisim ve uçurtma
  const dark = new THREE.MeshStandardMaterial({ color: 0x0b0b0e, roughness: .55, metalness: .1, envMapIntensity: .6 });
  const obj = jelly(dark); scene.add(obj); const kt = kite(); scene.add(kt);
  const look = (mode) => { const L = { dusk: [0xe7b48c, 0x4f6f9a, 0xd8c4b4, .55, 1, 0, 1, .00005], storm: [0xc9a58c, 0x56708e, 0x9aa0a6, .62, .55, 0, .7, .00006], night: [0x3a4a78, 0x050a1a, 0x2a3450, .3, 0, .6, .0, .00007] }[mode]; tm.envMapIntensity = mode === 'night' ? .04 : .4;
    U.uHor.value.set(L[0]); U.uZen.value.set(L[1]); U.uCC.value.set(L[2]); U.uCloud.value = L[3]; U.uRain.value = L[4]; U.uNight.value = L[5]; U.uSunI.value = L[6]; scene.fog.density = L[7];
    scene.fog.color.set(L[0]); sunL.intensity = mode === 'night' ? .05 : 2.6; hemi.intensity = mode === 'night' ? .25 : .8; sunL.position.copy(U.uSun.value).multiplyScalar(5000); };
  const frame = (t, cam) => { U.uT.value = t; dome.position.copy(cam.position); };
  return W = { scene, U, look, frame, obj, kt, dark };
}
const cam0 = () => new THREE.PerspectiveCamera(50, 1080 / 1920, .5, 200000);
// Cismin gökyüzündeki konumu (doğu-kuzeydoğu, tepelerin üzerinde)
const OBJ = new THREE.Vector3(5200, 520, -2600);
// S1: viral açılış – hızlı yakınlaşma
export function s1(renderer) { const Wd = world(renderer), cam = cam0();
  return { scene: Wd.scene, cam, update(t, P, O) { Wd.look('storm'); Wd.obj.visible = true; Wd.kt.visible = false; Wd.obj.position.copy(OBJ); Wd.obj.scale.setScalar(6); Wd.obj.userData.step(t + 3, new THREE.Vector3(2, 0, 0));
    const u = eout(clamp(t / 5.2)), p = OBJ.clone().add(new THREE.Vector3(-700, -110, 380)).lerp(OBJ.clone().add(new THREE.Vector3(-230, -30, 130)), u);
    p.x += Math.sin(t * 13) * 1.2 * (1 - u); p.y += Math.sin(t * 17) * .9; cam.position.copy(p); cam.lookAt(OBJ.clone().add(new THREE.Vector3(0, -25 + Math.sin(t * 3) * 3, 0))); cam.fov = lerp(36, 21, u); cam.updateProjectionMatrix(); Wd.frame(t, cam);
    Object.assign(P, { bloom: [.5, .5, .8], exposure: .8, tone: 'aces', vignette: .6, grain: .06, sat: .9, contrast: 1.12, zoom: .45 * (1 - sstep(0, 1.2, t)) + .15 });
    O.badge('TEMSİLİ CANLANDIRMA', 540, 210, 1, '#ff4a3d'); } }; }
// S2: Alaska – akşam ışığı, gökkuşağı, kamera gökyüzüne yükselir
export function s2(renderer) { const Wd = world(renderer), cam = cam0();
  return { scene: Wd.scene, cam, update(t, P, O) { Wd.look('dusk'); Wd.obj.visible = false; Wd.kt.visible = false;
    const u = eio(clamp(t / 7.5)); cam.position.set(lerp(-2600, -1700, u), lerp(24, 380, u), lerp(900, 650, u)); const d = new THREE.Vector3(Math.sin(100 * DEG), lerp(.03, .4, eio(clamp((t - 2.5) / 5))), -Math.cos(100 * DEG));
    cam.lookAt(cam.position.clone().add(d)); cam.fov = 50; cam.updateProjectionMatrix(); Wd.frame(t + 10, cam);
    Object.assign(P, { bloom: [.55, .5, .8], exposure: .85, tone: 'aces', vignette: .45, grain: .035, sat: 1.1, contrast: 1.05 });
    O.label(new THREE.Vector3(1500, 80, 200), cam, ['Doğu Anchorage, Alaska', '15 Haziran 2026 · akşam'], sstep(.4, .8, t) * (1 - sstep(6.8, 7.2, t)), { dx: -300, dy: -380, color: '#ffd23f', yr: [380, 1150] }); } }; }
// S3: cisim yakından – sinematik canlandırma
export function s3(renderer) { const Wd = world(renderer), cam = cam0(); const T0 = 13.5, WT = (w, d) => (window.WT && window.WT(w)) ?? d;
  const tg = WT('gövde…', 14.9) - T0, ta = WT('kollar!', 18.6) - T0;
  return { scene: Wd.scene, cam, update(t, P, O) { Wd.look('storm'); Wd.obj.visible = true; Wd.kt.visible = false; Wd.obj.position.copy(OBJ); Wd.obj.scale.setScalar(1); Wd.obj.userData.step(t + 8, new THREE.Vector3(1.5, 0, 0));
    const a = -1.9 + t * .09, rad = lerp(34, 26, eio(clamp(t / 9))); cam.position.copy(OBJ).add(new THREE.Vector3(Math.cos(a) * rad, lerp(-2, -6, t / 9), Math.sin(a) * rad)); cam.lookAt(OBJ.clone().add(new THREE.Vector3(0, lerp(-3, -5, t / 9), 0))); cam.fov = 42; cam.updateProjectionMatrix(); Wd.frame(t + 20, cam);
    Object.assign(P, { bloom: [.5, .5, .8], exposure: .8, tone: 'aces', vignette: .55, grain: .045, sat: .95, contrast: 1.1 });
    O.badge('TEMSİLİ CANLANDIRMA', 540, 210, 1, '#ff4a3d');
    O.label(OBJ.clone().add(new THREE.Vector3(0, 1, 0)), cam, ['Koyu renkli gövde'], sstep(tg - .5, tg - .2, t) * (1 - sstep(6.8, 7.1, t)), { dx: 120, dy: -300, color: '#ffd23f', yr: [380, 1150] });
    O.label(OBJ.clone().add(new THREE.Vector3(0, -8, 0)), cam, ['Sarkan, hareket eden kollar', 'görüntülerde dikkat çeken özellik'], sstep(ta - 2.2, ta - 1.9, t) * (1 - sstep(8.4, 8.7, t)), { dx: -330, dy: 260, color: '#9fe8ff', yr: [380, 1150] }); } }; }
// S5: Kirkpatrick'in açıklaması ve ahtapot uçurtma karşılaştırması
export function s5(renderer) { const Wd = world(renderer), cam = cam0(); const KP = OBJ.clone().add(new THREE.Vector3(-40, -10, 30));
  return { scene: Wd.scene, cam, update(t, P, O) { const kph = t > 4.1; Wd.look('dusk'); Wd.obj.visible = !kph; Wd.kt.visible = kph;
    if (!kph) { Wd.obj.position.copy(OBJ); Wd.obj.scale.setScalar(1); Wd.obj.userData.step(t + 30, new THREE.Vector3(1.5, 0, 0)); cam.position.copy(OBJ).add(new THREE.Vector3(-30, -8, 22)); cam.lookAt(OBJ.clone().add(new THREE.Vector3(6, -4, 0))); cam.fov = 46; }
    else { const k = t - 4.1, sil = sstep(3.6, 6.2, k); Wd.kt.position.copy(KP); Wd.kt.rotation.set(0, -.5 + Math.sin(k * .8) * .1, Math.sin(k * 1.3) * .05); Wd.kt.userData.step(k + 5);
      Wd.kt.userData.fab.color.set(0xc0306a).lerp(new THREE.Color(0x0b0b0e), sil); const a = .55 + k * .07, rad = lerp(26, 48, sil);
      cam.position.copy(KP).add(new THREE.Vector3(Math.cos(a) * rad, lerp(-3, -10, sil), Math.sin(a) * rad)); cam.lookAt(KP.clone().add(new THREE.Vector3(2, lerp(-3, -5, sil), 0))); cam.fov = 44; }
    cam.updateProjectionMatrix(); Wd.frame(t + 40, cam);
    Object.assign(P, { bloom: [.5, .5, .8], exposure: .85, tone: 'aces', vignette: .5, grain: .04, sat: 1.05, contrast: 1.06 });
    O.badge('TEMSİLİ CANLANDIRMA', 540, 210, 1, '#ff4a3d');
    O.quote(sstep(.2, .5, t) * (1 - sstep(3.8, 4.1, t)));
    if (kph) { const k = t - 4.1; O.label(KP.clone().add(new THREE.Vector3(-8, -16, 2)), cam, ['Uçurtma ipi'], sstep(.6, .9, k) * (1 - sstep(3.4, 3.7, k)), { dx: -300, dy: 200, color: '#ffd23f', yr: [380, 1150] });
      O.label(KP, cam, ['Kesin tanımlama yapılmadı', 'JBER: "ek bilgimiz yok"'], sstep(4.0, 4.3, k), { dx: 120, dy: 300, color: '#ff6a5a', yr: [380, 1150] }); } } }; }
// S6: final – karanlık gök, silüet, yavaş yakınlaşma
export function s6(renderer) { const Wd = world(renderer), cam = cam0();
  return { scene: Wd.scene, cam, update(t, P, O) { Wd.look('night'); Wd.obj.visible = true; Wd.kt.visible = false; Wd.obj.position.copy(OBJ); Wd.obj.scale.setScalar(1); Wd.obj.userData.step(t + 50, new THREE.Vector3(1.2, 0, 0), .8);
    const u = eio(clamp(t / 9.4)); cam.position.copy(OBJ).add(new THREE.Vector3(lerp(-70, -42, u), lerp(-9, -6, u), lerp(40, 24, u))); cam.lookAt(OBJ.clone().add(new THREE.Vector3(0, lerp(-1, -4, u), 0))); cam.fov = 40; cam.updateProjectionMatrix(); Wd.frame(t + 60, cam);
    Object.assign(P, { bloom: [.6, .5, .7], exposure: 1.0, tone: 'aces', vignette: .6, grain: .05, sat: .95, contrast: 1.1 });
    O.badge('TEMSİLİ CANLANDIRMA', 540, 210, 1 - sstep(6.4, 6.8, t), '#ff4a3d');
    O.logo(sstep(6.8, 7.4, t), t - 6.8, sstep(7.5, 7.8, t)); } }; }
