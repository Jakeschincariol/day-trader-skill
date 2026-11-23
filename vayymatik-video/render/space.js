import * as THREE from 'three';
import { DEG, clamp, lerp, sstep, eio, ein, eout, rng, ll2v, tex, canvasTex, softDot, envFrom, pointsGeo, flowMat } from './lib.js';
import { ROUTES } from './routes.js';
const VS = `varying vec2 vUv; varying vec3 vN; varying vec3 vW; void main(){ vUv=uv; vN=normalize(mat3(modelMatrix)*normal); vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`;
const R = 10;
let EARTH = null;
function earth() {
  if (EARTH) return EARTH;
  const g = new THREE.Group();
  const U = { tDay: { value: tex('/tex/earth_day.jpg') }, tSpec: { value: tex('/tex/earth_spec.png', false) }, tCl: { value: tex('/tex/earth_clouds.png', false) },
    uSun: { value: new THREE.Vector3(1, 0, 0) }, uCS: { value: 0 }, uT: { value: 0 }, uR: { value: R }, uA: { value: 1 } };
  g.add(new THREE.Mesh(new THREE.SphereGeometry(R, 256, 160), new THREE.ShaderMaterial({ uniforms: U, vertexShader: VS, fragmentShader: `
    uniform sampler2D tDay,tSpec,tCl; uniform vec3 uSun; uniform float uCS,uT; varying vec2 vUv; varying vec3 vN; varying vec3 vW;
    float hs(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
    float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hs(i),hs(i+vec2(1,0)),f.x),mix(hs(i+vec2(0,1)),hs(i+vec2(1,1)),f.x),f.y);}
    void main(){
      vec3 n=normalize(vN), v=normalize(cameraPosition-vW); float ndl=dot(n,uSun), dif=max(ndl,0.);
      vec3 day=texture2D(tDay,vUv).rgb; float oc=texture2D(tSpec,vUv).r;
      float det=smoothstep(4.,.35,length(cameraPosition-vW));
      vec2 q=vUv*vec2(9000.,4500.); float w=vn(q+uT*vec2(.9,.3))*.6+vn(q*2.7-uT*vec2(.4,1.1))*.4;
      vec3 nn=normalize(n+(vec3(w,1.-w,w*.5)-.5)*.5*det*oc);
      vec3 col=day*(.012+1.15*dif); col*=mix(1.,.82+.36*w,det*oc);
      vec3 hv=normalize(uSun+v); float sp=pow(max(dot(nn,hv),0.),mix(70.,160.,det));
      col+=oc*sp*vec3(1.,.92,.78)*(.32+det*.9)*step(0.,ndl);
      float cs=texture2D(tCl,vUv+vec2(uCS-.0015,.001)).r; col*=1.-cs*.45*dif;
      float fr=pow(1.-max(dot(n,v),0.),2.2);
      col=mix(col,vec3(.30,.55,1.)*(dif*1.1+.02),fr*.6*smoothstep(-.25,.35,ndl));
      gl_FragColor=vec4(col,1.);
    }` })));
  const cl = new THREE.Mesh(new THREE.SphereGeometry(R * 1.006, 192, 120), new THREE.ShaderMaterial({ uniforms: U, vertexShader: VS, transparent: true, depthWrite: false, fragmentShader: `
    uniform sampler2D tCl; uniform vec3 uSun; uniform float uCS; varying vec2 vUv; varying vec3 vN; varying vec3 vW;
    void main(){ vec3 n=normalize(vN); float ndl=dot(n,uSun); float a=texture2D(tCl,vUv+vec2(uCS,0.)).r;
      vec3 c=vec3(.97,.98,1.)*(.015+.95*max(ndl,0.)); c*=mix(vec3(1.),vec3(1.,.72,.5),smoothstep(.3,0.,ndl)*step(-.05,ndl));
      gl_FragColor=vec4(c,a*smoothstep(.04,.5,length(cameraPosition-vW)));}` }));
  g.add(cl);
  g.add(new THREE.Mesh(new THREE.SphereGeometry(R * 1.05, 128, 80), new THREE.ShaderMaterial({ uniforms: U, transparent: true, depthWrite: false, side: THREE.BackSide, blending: THREE.AdditiveBlending,
    vertexShader: VS, fragmentShader: `uniform vec3 uSun; uniform float uR,uA; varying vec3 vW;
    void main(){ vec3 v=normalize(vW-cameraPosition); vec3 c=cameraPosition; float tca=dot(-c,v); vec3 p=c+v*max(tca,0.); float b=length(p);
      float Ra=uR*1.05; float g=clamp((Ra-b)/(Ra-uR),0.,1.); float I=b<uR?0.:pow(g,2.2);
      float s=dot(normalize(p),uSun); float l=smoothstep(-.35,.25,s);
      vec3 col=mix(vec3(1.,.42,.18),vec3(.35,.62,1.),smoothstep(-.12,.3,s));
      gl_FragColor=vec4(col*I*l*1.7*uA,1.);}` })));
  // Yıldızlar ve güneş
  const r = rng(11);
  const stars = new THREE.Points(pointsGeo(9000, (i, p, s, a) => { const u = r() * 2 - 1, th = r() * 6.2832, q = Math.sqrt(1 - u * u); p[i * 3] = q * Math.cos(th) * 900; p[i * 3 + 1] = u * 900; p[i * 3 + 2] = q * Math.sin(th) * 900; s[i] = 1.2 + Math.pow(r(), 7) * 4; a[i] = .25 + r() * .75; }),
    new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexShader: `attribute float aS; attribute float aA; varying float vA; void main(){ vA=aA; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); gl_PointSize=aS; }`,
      fragmentShader: `varying float vA; void main(){ vec2 p=gl_PointCoord*2.-1.; float d=dot(p,p); if(d>1.)discard; gl_FragColor=vec4(vec3(.9,.95,1.)*vA*(1.-d)*(1.-d)*1.4,1.);}` }));
  g.add(stars);
  const sun = new THREE.Sprite(new THREE.SpriteMaterial({ map: softDot(), color: 0xfff0d0, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  sun.scale.setScalar(160); g.add(sun);
  const setSun = (d) => { U.uSun.value.copy(d).normalize(); sun.position.copy(U.uSun.value).multiplyScalar(880); };
  return EARTH = { g, U, setSun };
}
// ---------- Uydu modeli ----------
function satellite(env) {
  const PANEL = canvasTex(512, 168, (g, w, h) => { g.fillStyle = '#0b1830'; g.fillRect(0, 0, w, h); for (let x = 0; x < w; x += 32) for (let y = 0; y < h; y += 42) { const gr = g.createLinearGradient(x, y, x + 30, y + 40); gr.addColorStop(0, '#24508f'); gr.addColorStop(1, '#0d2450'); g.fillStyle = gr; g.fillRect(x + 2, y + 2, 28, 38); } g.strokeStyle = '#9aa7b4'; g.lineWidth = 3; g.strokeRect(1, 1, w - 2, h - 2); });
  const FOIL = canvasTex(256, 256, (g, w, h) => { const r = rng(3); g.fillStyle = '#c8962c'; g.fillRect(0, 0, w, h); for (let i = 0; i < 500; i++) { const b = 140 + r() * 115 | 0; g.fillStyle = `rgba(${b},${b * .74 | 0},${b * .3 | 0},.55)`; g.beginPath(); const x = r() * w, y = r() * h; g.moveTo(x, y); g.lineTo(x + r() * 40 - 20, y + r() * 40 - 20); g.lineTo(x + r() * 40 - 20, y + r() * 40 - 20); g.fill(); } });
  const foil = new THREE.MeshStandardMaterial({ map: FOIL, metalness: 1, roughness: .33, envMap: env, envMapIntensity: 1.3 });
  const silver = new THREE.MeshStandardMaterial({ color: 0xcfd3d6, metalness: 1, roughness: .25, envMap: env });
  const white = new THREE.MeshStandardMaterial({ color: 0xe6e6e6, metalness: .1, roughness: .45, envMap: env, side: THREE.DoubleSide });
  const panel = new THREE.MeshStandardMaterial({ map: PANEL, metalness: .85, roughness: .26, envMap: env, envMapIntensity: 1.6 });
  const g = new THREE.Group();
  g.add(new THREE.Mesh(new THREE.BoxGeometry(.6, .6, .9), foil));
  const top = new THREE.Mesh(new THREE.BoxGeometry(.64, .08, .94), white); top.position.y = .34; g.add(top);
  for (const s of [-1, 1]) {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(.025, .025, .7, 8), silver); arm.rotation.z = Math.PI / 2; arm.position.x = s * .65; g.add(arm);
    const p = new THREE.Mesh(new THREE.BoxGeometry(2.6, .03, .85), panel); p.position.x = s * 2.3; g.add(p);
  }
  const dish = new THREE.Mesh(new THREE.SphereGeometry(.42, 32, 10, 0, 6.2832, 0, 1.0), white); dish.rotation.x = -Math.PI / 2; dish.position.z = .75; g.add(dish);
  const led = new THREE.Mesh(new THREE.SphereGeometry(.05, 8, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(8, .6, .4) })); led.position.set(0, .42, -.4); g.add(led);
  g.userData.led = led; return g;
}
function beam() {
  const m = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: { uT: { value: 0 }, uI: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);} `,
    fragmentShader: `uniform float uT,uI; varying vec2 vUv; void main(){ float s=.2+.8*pow(.5+.5*sin(vUv.y*16.+uT*9.),14.); float e=smoothstep(0.,.08,vUv.y)*smoothstep(1.,.85,vUv.y);
      gl_FragColor=vec4(vec3(.45,.85,1.)*s*e*uI*.5,1.);}` });
  const geo = new THREE.CylinderGeometry(.012, .07, 1, 16, 1, true); geo.translate(0, -.5, 0);
  return new THREE.Mesh(geo, m);
}
function aimBeam(b, from, to) { const d = to.clone().sub(from); b.position.copy(from); b.scale.set(1, d.length(), 1); b.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), d.normalize()); }
// ---------- SAHNE 1: Uzay -> okyanusa dalış ----------
export function scene1(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  const E = earth();
  const cam = new THREE.PerspectiveCamera(42, 1080 / 1920, .01, 3000);
  const env = envFrom(renderer, '#000000', '#0a1630', '#1d4a8a', [.62, .42]);
  const key = new THREE.DirectionalLight(0xfff4e0, 3.2); scene.add(key); scene.add(new THREE.AmbientLight(0x1a2a44, .35));
  const satA = satellite(env), satB = satellite(env), satC = satellite(env); satB.scale.setScalar(.5); satC.scale.setScalar(.45); scene.add(satA, satB, satC);
  const bB = beam(), bC = beam(); scene.add(bB, bC);
  const SUN = ll2v(10, -5, 1), T0 = ll2v(14, -60, 1), T1 = ll2v(31, -36, 1);
  const camPos = (t) => { const s = clamp(t / 3.5); const f = Math.pow(s, 2.35); const d = new THREE.Vector3().copy(T0).lerp(T1, eio(clamp(t / 3.2))).normalize(); return d.multiplyScalar(lerp(31, 10.16, f)); };
  const P0 = camPos(0), F0 = P0.clone().multiplyScalar(-1).normalize(), RT0 = new THREE.Vector3().crossVectors(F0, new THREE.Vector3(0, 1, 0)).normalize(), UP0 = new THREE.Vector3().crossVectors(RT0, F0);
  return { scene, cam, update(t, P, O) {
    scene.add(E.g); E.setSun(SUN); key.position.copy(SUN).multiplyScalar(100);
    E.U.uT.value = t; E.U.uCS.value = t * .0008; E.U.uA.value = sstep(10.6, 11.6, camPos(t).length());
    const p = camPos(t); cam.position.copy(p);
    const s = eio(clamp((t - .9) / 2.3));
    const look = new THREE.Vector3(0, 7.5, 0).lerp(T1.clone().multiplyScalar(R), s);
    cam.up.set(0, 1, 0); cam.lookAt(look);
    cam.fov = lerp(42, 64, ein(clamp((t - 1.6) / 1.9))); cam.updateProjectionMatrix();
    // Uydular: kahraman uydu ön planda süzülür
    satA.position.copy(P0).addScaledVector(F0, 7.6).addScaledVector(UP0, 2.0 - t * .12).addScaledVector(RT0, -.15 + t * .45);
    satA.lookAt(0, 0, 0); satA.rotateZ(.35 + t * .05); satA.rotateX(-.25);
    satB.position.copy(ll2v(36 + t * 1.5, -47 + t * 2.2, 13.2)); satB.lookAt(0, 0, 0);
    satC.position.copy(ll2v(6 - t, -44 + t * 2, 13.8)); satC.lookAt(0, 0, 0); satC.rotateZ(1.2);
    for (const s of [satA, satB, satC]) s.userData.led.visible = (Math.floor(t * 2.2) % 2) === 0;
    const bi = sstep(.25, .7, t) * (1 - sstep(2.0, 2.6, t));
    aimBeam(bB, satB.position, ll2v(42, -50, R)); aimBeam(bC, satC.position, ll2v(18, -50, R));
    bB.material.uniforms.uT.value = bC.material.uniforms.uT.value = t; bB.material.uniforms.uI.value = bC.material.uniforms.uI.value = bi;
    Object.assign(P, { bloom: [1.0, .55, .72], exposure: 1.05, tone: 'aces', vignette: .45, grain: .035, sat: 1.08, contrast: 1.06 });
  } };
}
// ---------- SAHNE 7: okyanustan uzaklaş, ışıyan bağlantılar, logo ----------
export function scene7(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  const E = earth();
  const cam = new THREE.PerspectiveCamera(40, 1080 / 1920, .01, 3000);
  const routes = new THREE.Group(); scene.add(routes);
  const dots = [];
  const dotTex = softDot();
  ROUTES.forEach((r) => {
    const pts = []; for (let i = 0; i < r.pts.length - 1; i++) { const [a1, o1] = r.pts[i], [a2, o2] = r.pts[i + 1]; let d = o2 - o1; if (d > 180) d -= 360; if (d < -180) d += 360; for (let k = 0; k < 8; k++) { const f = k / 8; pts.push(ll2v(a1 + (a2 - a1) * f, o1 + d * f, R * 1.0035)); } }
    const [la, lo] = r.pts[r.pts.length - 1]; pts.push(ll2v(la, lo, R * 1.0035));
    const curve = new THREE.CatmullRomCurve3(pts); const L = curve.getLength();
    const m = flowMat(0x46eaff, { base: .55, freq: L / 1.6, speed: 2.2 / L });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(60, pts.length * 6), .028, 6), m); mesh.userData.t0 = r.t * .45; routes.add(mesh);
    for (const e of [r.pts[0], r.pts[r.pts.length - 1]]) { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: dotTex, color: 0x9ff6ff, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })); s.position.copy(ll2v(e[0], e[1], R * 1.006)); s.scale.setScalar(.32); s.userData.t0 = r.t * .45; scene.add(s); dots.push(s); }
  });
  const SUN = ll2v(12, 32, 1);
  const D0 = ll2v(36, -28, 1), D1 = ll2v(24, -14, 1), D2 = ll2v(20, 2, 1);
  return { scene, cam, update(t, P, O) {
    scene.add(E.g); E.setSun(SUN); E.U.uT.value = t + 40; E.U.uCS.value = .02 + t * .0008;
    const a = eout(clamp(t / 4.2)), b = eio(clamp((t - 1.5) / 5.9));
    const dir = D0.clone().lerp(D1, a).lerp(D2, b * .6).normalize();
    const dist = lerp(10.35, 44, a) + b * 3;
    cam.position.copy(dir).multiplyScalar(dist);
    E.U.uA.value = sstep(10.6, 11.6, dist);
    const look = D0.clone().multiplyScalar(R).lerp(new THREE.Vector3(0, 6.2, 0).add(dir.clone().multiplyScalar(-2)), eout(clamp(t / 3.6)));
    cam.up.set(0, 1, 0); cam.lookAt(look);
    cam.fov = lerp(55, 40, eout(clamp(t / 3))); cam.updateProjectionMatrix();
    routes.children.forEach(m => { const u = m.material.uniforms; u.uT.value = t; u.uProg.value = eout(clamp((t - .6 - m.userData.t0) / 1.6)); u.uAmp.value = 1 + .4 * sstep(4.6, 5.4, t); });
    dots.forEach(s => { const k = sstep(1.6 + s.userData.t0, 2.2 + s.userData.t0, t); s.material.opacity = k * (.75 + .25 * Math.sin(t * 5 + s.position.x)); });
    Object.assign(P, { bloom: [1.05, .6, .72], exposure: .92, tone: 'aces', vignette: .5, grain: .03, sat: 1.1, contrast: 1.06 });
    // Logo
    O.logo(sstep(4.75, 5.35, t), t - 4.75, sstep(5.35, 5.6, t));
  } };
}
