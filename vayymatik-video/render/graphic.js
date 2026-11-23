import * as THREE from 'three';
import { DEG, clamp, lerp, sstep, eio, ein, eout, rng, tex, canvasTex, softDot, envFrom, pointsGeo, flowMat, particleMat } from './lib.js';
import { ROUTES, unwrap } from './routes.js';
// ---------- Harita (Sahne 3 ve 6B) ----------
function mapWorld() {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x01050c);
  const mt = tex('/tex/map_style.jpg'); mt.wrapS = THREE.RepeatWrapping; mt.repeat.set(2, 1); mt.anisotropy = 8;
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(720, 180), new THREE.MeshBasicMaterial({ map: mt, color: 0xbfd6e6 })); plane.position.set(180, 0, 0); scene.add(plane);
  const dotT = softDot(); const routes = {};
  ROUTES.forEach(r => {
    const u = unwrap(r.pts); const pts = u.map(([la, lo]) => new THREE.Vector3(lo, la, .2));
    const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal', .5); const L = curve.getLength();
    const m = flowMat(0x3ee8ff, { base: .45, freq: L / 7, speed: 14 / L });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(80, Math.round(L * 1.5)), .2, 6), m); scene.add(mesh);
    const ends = [u[0], u[u.length - 1]].map(([la, lo]) => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: dotT, color: 0xaef8ff, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })); s.position.set(lo, la, .4); s.scale.setScalar(2.4); scene.add(s); return s; });
    routes[r.id] = { mesh, m, ends, t: r.t, curve };
  });
  return { scene, routes };
}
let MAP = null;
const camPath = (keys, u) => { // keys: [t, [x,y,z], [lx,ly]]
  let i = 0; while (i < keys.length - 2 && u > keys[i + 1][0]) i++; const [t0, p0, l0] = keys[i], [t1, p1, l1] = keys[i + 1]; const f = eio(clamp((u - t0) / (t1 - t0)));
  return [new THREE.Vector3(...p0).lerp(new THREE.Vector3(...p1), f), new THREE.Vector3(l0[0], l0[1], 0).lerp(new THREE.Vector3(l1[0], l1[1], 0), f)]; };
export function scene3(renderer) {
  MAP = MAP || mapWorld(); const cam = new THREE.PerspectiveCamera(45, 1080 / 1920, .5, 3000);
  const keys = [[0, [-44, -6, 62], [-38, 36]], [2.2, [-10, -2, 80], [-8, 34]], [4.3, [40, -22, 150], [42, 22]], [6.8, [22, -24, 430], [22, 36]]];
  return { scene: MAP.scene, cam, update(t, P, O) {
    const [p, l] = camPath(keys, t); cam.position.copy(p); cam.up.set(0, 1, 0); cam.lookAt(l); cam.updateProjectionMatrix();
    Object.values(MAP.routes).forEach(r => { const u = r.m.uniforms; u.uT.value = t; u.uProg.value = eout(clamp((t - r.t * 1.25) / 1.7)); u.uAmp.value = 1; u.uRed.value = 0; u.uCol.value.set(0x3ee8ff); u.uBase.value = .45;
      r.ends.forEach((s, k) => s.material.opacity = sstep(r.t * 1.25 + (k ? 1.5 : 0), r.t * 1.25 + (k ? 1.8 : .3), t) * (.8 + .2 * Math.sin(t * 6 + s.position.x))); });
    Object.assign(P, { bloom: [1.0, .4, .4], exposure: 1, tone: 'none', vignette: .55, grain: .03, sat: 1.05, contrast: 1.05 });
    O.badge('TEMSİLİ GÜZERGÂHLAR', 540, 210, sstep(.4, .8, t) * (1 - sstep(6.5, 6.8, t)), '#4fe3ff');
  } };
}
export function scene6b(renderer) {
  MAP = MAP || mapWorld(); const cam = new THREE.PerspectiveCamera(45, 1080 / 1920, .5, 3000);
  const brk = MAP.routes['ny-uk'].curve.getPointAt(.78);
  return { scene: MAP.scene, cam, update(t, P, O) {
    cam.position.set(lerp(-34, -30, t / 3), lerp(14, 18, t / 3), lerp(128, 104, eout(t / 3))); cam.up.set(0, 1, 0); cam.lookAt(-32, 40, 0); cam.updateProjectionMatrix();
    Object.entries(MAP.routes).forEach(([id, r]) => { const u = r.m.uniforms; u.uT.value = t + 20; u.uProg.value = 1; u.uRed.value = 0; r.ends.forEach(s => s.material.opacity = .8);
      if (id === 'ny-uk') { u.uCol.value.set(0xff3b30); u.uBase.value = .5; u.uAmp.value = .7 + .3 * Math.sin(t * 10); }
      else if (id === 'marea' || id === 'amitie') { u.uCol.value.set(0x3dffa0); u.uBase.value = .4; u.uAmp.value = 1 + .3 * sstep(.4, 1.2, t); }
      else { u.uCol.value.set(0x3ee8ff); u.uBase.value = .3; u.uAmp.value = .45; } });
    Object.assign(P, { bloom: [.8, .4, .45], exposure: 1, tone: 'none', vignette: .55, grain: .03, sat: 1.05, contrast: 1.05 });
    O.xmark(brk, cam, sstep(.05, .3, t), t);
    O.label(MAP.routes['marea'].curve.getPointAt(.45), cam, ['Alternatif güzergâh'], sstep(.6, .9, t), { dx: -60, dy: 330, color: '#3dffa0' });
    O.label(brk, cam, ['Arızalı hat'], sstep(.2, .5, t), { dx: 40, dy: -300, color: '#ff4a3d' });
  } };
}
// ---------- Sahne 4A: kablonun kesit görünümü ----------
function shell(g, rIn, rOut, x0, x1, mat, capMat) {
  const len = x1 - x0, cx = (x0 + x1) / 2;
  const o = new THREE.CylinderGeometry(rOut, rOut, len, 96, 1, true); o.rotateZ(-Math.PI / 2); const mo = new THREE.Mesh(o, mat); mo.position.x = cx; g.add(mo);
  const i = new THREE.CylinderGeometry(rIn, rIn, len, 96, 1, true); i.rotateZ(-Math.PI / 2); const mi = new THREE.Mesh(i, mat.clone()); mi.material.side = THREE.BackSide; mi.position.x = cx; g.add(mi);
  const c = new THREE.RingGeometry(rIn, rOut, 96, 1); c.rotateY(Math.PI / 2); const mc = new THREE.Mesh(c, capMat || mat); mc.position.x = x1; g.add(mc);
}
export function scene4a(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x071a2b); scene.fog = new THREE.FogExp2(0x071a2b, .03);
  scene.environment = envFrom(renderer, '#5d86a6', '#10222f', '#010305', [.3, .22]);
  const pe = new THREE.MeshStandardMaterial({ color: 0x1c2026, roughness: .3, envMapIntensity: 1.6 }), peCap = new THREE.MeshStandardMaterial({ color: 0x3a3f47, roughness: .65 });
  const cu = new THREE.MeshStandardMaterial({ color: 0xd07a3c, roughness: .3, metalness: 1 }), st = new THREE.MeshStandardMaterial({ color: 0xc6ccd2, roughness: .22, metalness: 1 });
  const g = new THREE.Group(); scene.add(g);
  shell(g, .72, 1.0, -40, -2.3, pe, peCap);
  shell(g, .6, .7, -40, -1.45, cu);
  for (let k = 0; k < 16; k++) { const ph = k / 16 * Math.PI * 2, pts = []; for (let x = -40; x <= -.75; x += .25) { const a = ph + x * Math.PI * 2 / 7; pts.push(new THREE.Vector3(x, Math.cos(a) * .47, Math.sin(a) * .47)); } g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 400, .068, 10), st)); }
  shell(g, .25, .33, -40, -.2, st);
  const cols = [0x1f5fff, 0xff7a1a, 0x22b04a, 0x8a5a2b, 0x8a96a0, 0xf2f2f2, 0xe3242b, 0x2a2a2a]; const tips = [];
  const dotT = softDot();
  cols.forEach((c, k) => { const a = k / 8 * Math.PI * 2 + .2, r0 = .13, r1 = .2 + (k % 2) * .05, tx = .75 + (k % 3) * .12;
    const pts = [new THREE.Vector3(-40, Math.cos(a) * r0, Math.sin(a) * r0), new THREE.Vector3(-.5, Math.cos(a) * r0, Math.sin(a) * r0), new THREE.Vector3(.1, Math.cos(a) * (r0 + .03), Math.sin(a) * (r0 + .03)), new THREE.Vector3(tx, Math.cos(a) * r1, Math.sin(a) * r1)];
    const cv = new THREE.CatmullRomCurve3(pts); g.add(new THREE.Mesh(new THREE.TubeGeometry(cv, 200, .03, 10), new THREE.MeshStandardMaterial({ color: c, roughness: .35 })));
    const tip = cv.getPoint(1); const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: dotT, color: 0xbff6ff, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })); s.position.copy(tip); s.scale.setScalar(.1); scene.add(s); tips.push(s);
    const core = new THREE.Mesh(new THREE.SphereGeometry(.018, 10, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(1.3, 2.8, 3.2) })); core.position.copy(tip); scene.add(core); });
  const key = new THREE.DirectionalLight(0xffffff, 4.2); key.position.set(3, 5, 6); scene.add(key); const k2 = new THREE.DirectionalLight(0xffe2c4, 2.0); k2.position.set(-2, -3, 5); scene.add(k2);
  const rim = new THREE.DirectionalLight(0x4fc3ff, 3.5); rim.position.set(-5, 2, -4); scene.add(rim);
  scene.add(new THREE.HemisphereLight(0x29435a, 0x000000, .7));
  const r = rng(12); const bok = new THREE.Points(pointsGeo(260, (i, p, s, a) => { p[i * 3] = -12 + r() * 16; p[i * 3 + 1] = (r() - .5) * 12; p[i * 3 + 2] = -3 - r() * 12; s[i] = .03 + r() * .06; a[i] = .2 + r() * .6; }), particleMat({ color: 0x5fd0ff, size: 1, opacity: .3 })); scene.add(bok);
  const cam = new THREE.PerspectiveCamera(40, 1080 / 1920, .01, 200);
  const P0 = [new THREE.Vector3(3.6, 2.2, 7.4), new THREE.Vector3(-3.0, 0, 0)], P1 = [new THREE.Vector3(2.7, 1.3, 2.6), new THREE.Vector3(-.6, .05, 0)], P2 = [tips[1].position.clone().add(new THREE.Vector3(.42, .02, .03)), tips[1].position.clone()];
  return { scene, cam, update(t, P, O) {
    const a = eio(clamp(t / 2.1)), b = ein(clamp((t - 2.1) / 1.1));
    const pos = P0[0].clone().lerp(P1[0], a).lerp(P2[0], b), look = P0[1].clone().lerp(P1[1], a).lerp(P2[1], b);
    cam.position.copy(pos); cam.lookAt(look); cam.fov = 40 + b * 18; cam.updateProjectionMatrix();
    g.rotation.x = t * .08; tips.forEach((s, k) => s.material.opacity = .45 + .2 * Math.sin(t * 9 + k));
    Object.assign(P, { bloom: [.55, .4, .85], exposure: 1.1, tone: 'aces', vignette: .5, grain: .035, sat: 1.05, contrast: 1.08 });
    const A = (t0) => sstep(t0, t0 + .3, t) * (1 - sstep(2.15, 2.45, t));
    O.label(new THREE.Vector3(-4.2, .98, .2), cam, ['Polietilen yalıtım'], A(.25), { dx: -40, dy: -300, color: '#9fb3c8' });
    O.label(new THREE.Vector3(-1.9, .7, .1), cam, ['Bakır iletken'], A(.6), { dx: -360, dy: -170, color: '#ff9a52' });
    O.label(new THREE.Vector3(-1.05, .44, .2), cam, ['Çelik teller'], A(.95), { dx: -380, dy: 220, color: '#d8e0e8' });
    O.label(tips[3].position, cam, ['Optik lifler'], A(1.3), { dx: 60, dy: 300, color: '#4fe3ff' });
  } };
}
// ---------- Sahne 4B: fiberin içinde ışık sinyalleri ----------
export function scene4b(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x00040a); scene.fog = new THREE.FogExp2(0x00040a, .085);
  const g = new THREE.Group(); g.rotation.z = 1.05; scene.add(g);
  const clad = new THREE.CylinderGeometry(1, 1, 240, 96, 1, true); clad.rotateZ(-Math.PI / 2);
  const cladM = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide, uniforms: { uT: { value: 0 } },
    vertexShader: `varying vec3 vN; varying vec3 vV; varying vec3 vP; varying float vD; void main(){ vP=position; vN=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.); vV=normalize(-mv.xyz); vD=-mv.z; gl_Position=projectionMatrix*mv; }`,
    fragmentShader: `uniform float uT; varying vec3 vN; varying vec3 vV; varying vec3 vP; varying float vD; void main(){ float f=1.-abs(dot(normalize(vN),normalize(vV))); float fr=pow(f,2.5);
      float streak=pow(max(0.,sin(atan(vP.z,vP.y)*1.0+.6)),60.)*.22; float ring=.5+.5*sin(vP.x*1.3);
      float face=gl_FrontFacing?1.:.25; float fog=exp(-vD*.085);
      vec3 c=(vec3(.35,.75,1.)*(pow(f,4.)*1.2+.03)+vec3(.8,.95,1.)*streak*(.6+.4*ring))*face;
      gl_FragColor=vec4(c,clamp(pow(f,4.)*.55+.02+streak*.3,0.,1.)*face*fog);}` });
  g.add(new THREE.Mesh(clad, cladM));
  const core = new THREE.CylinderGeometry(.16, .16, 240, 32, 1, true); core.rotateZ(-Math.PI / 2);
  g.add(new THREE.Mesh(core, new THREE.MeshBasicMaterial({ color: new THREE.Color(.05, .35, .5), transparent: true, opacity: .35, blending: THREE.AdditiveBlending, depthWrite: false })));
  const pulseG = new THREE.CapsuleGeometry(.1, .9, 6, 12); pulseG.rotateZ(Math.PI / 2);
  const NP = 110, pulses = new THREE.InstancedMesh(pulseG, new THREE.MeshBasicMaterial({ color: new THREE.Color(1.6, 4.2, 5) }), NP); pulses.frustumCulled = false; g.add(pulses);
  const halos = []; const dotT = softDot(); for (let i = 0; i < NP; i++) { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: dotT, color: 0x4fe8ff, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: .55 })); s.scale.setScalar(.6); g.add(s); halos.push(s); }
  const bits = [1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1]; const SP = 2.0, SPEED = 15;
  const r = rng(5); const bok = new THREE.Points(pointsGeo(500, (i, p, s, a) => { p[i * 3] = -150 + r() * 300; p[i * 3 + 1] = (r() - .5) * 40; p[i * 3 + 2] = -6 - r() * 30; s[i] = .1 + r() * .4; a[i] = .1 + r() * .5; }), particleMat({ color: 0x3f9fff, size: 1, opacity: .6 })); g.add(bok);
  const cam = new THREE.PerspectiveCamera(46, 1080 / 1920, .01, 600);
  const M = new THREE.Matrix4(); const tmp = new THREE.Object3D();
  return { scene, cam, update(t, P, O) {
    cladM.uniforms.uT.value = t;
    for (let i = 0; i < NP; i++) { const x = ((i * SP + t * SPEED) % (NP * SP)) - NP * SP / 2 + (-8 + t * 6); const on = bits[i % bits.length]; tmp.position.set(x, 0, 0); tmp.scale.setScalar(on ? 1 : 0); tmp.updateMatrix(); pulses.setMatrixAt(i, tmp.matrix); halos[i].position.set(x, 0, 0); halos[i].visible = !!on; halos[i].material.opacity = .2; }
    pulses.instanceMatrix.needsUpdate = true;
    // Kamera: yandan takip -> lif ekseni boyunca tünel görünümü
    const k = eio(clamp((t - 2.0) / 1.6)); const xc = -8 + t * 6;
    const lp = new THREE.Vector3(xc, lerp(.8, .55, k), lerp(4.6, .12, k)), ll = new THREE.Vector3(xc + lerp(3, 30, k), lerp(0, .3, k), 0);
    g.updateMatrixWorld(); cam.position.copy(lp.applyMatrix4(g.matrixWorld)); cam.up.set(0, 1, 0).applyAxisAngle(new THREE.Vector3(0, 0, 1), k * .4); cam.lookAt(ll.applyMatrix4(g.matrixWorld)); cam.fov = lerp(46, 75, k); cam.updateProjectionMatrix();
    Object.assign(P, { bloom: [lerp(.75, .5, k), .4, .62], exposure: .92, tone: 'aces', vignette: .55, grain: .03, sat: 1.1, contrast: 1.05, zoom: k * .35 });
    const A = sstep(.2, .5, t) * (1 - sstep(1.8, 2.1, t));
    const nearPulse = new THREE.Vector3(xc + 2.5 - ((xc + 2.5 + t * SPEED) % SP), 0, 0).applyMatrix4(g.matrixWorld);
    O.label(new THREE.Vector3(xc + 1, .85, .45).applyMatrix4(g.matrixWorld), cam, ['Cam lif', 'saç teli kalınlığında'], A, { dx: -380, dy: -300, color: '#9fe8ff', yr: [640, 1120] });
    O.label(new THREE.Vector3(xc + 4, .05, .1).applyMatrix4(g.matrixWorld), cam, ['Işık sinyalleri'], A, { dx: 40, dy: 330, color: '#4fe3ff', yr: [640, 1120] });
  } };
}
