import * as THREE from 'three';
import { DEG, clamp, lerp, sstep, eio, ein, eout, rng, vnoise2, tex, canvasTex, softDot, envFrom, particleMat, pointsGeo, flowMat } from './lib.js';
const CAUSTIC = `
vec2 ch2(vec2 p){ p=vec2(dot(p,vec2(127.1,311.7)),dot(p,vec2(269.5,183.3))); return fract(sin(p)*43758.5453); }
float vedge(vec2 x,float t){ vec2 n=floor(x),f=fract(x); float d1=8.,d2=8.;
  for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){ vec2 g=vec2(float(i),float(j)); vec2 o=ch2(n+g); o=.5+.42*sin(t+6.2831*o); float d=length(g+o-f); if(d<d1){d2=d1;d1=d;}else if(d<d2)d2=d; }
  return d2-d1; }
float caustics(vec2 p,float t){ return exp(-vedge(p,t)*9.)+exp(-vedge(p*1.37+vec2(4.1,2.3),t*1.13+2.)*9.)*.8; }`;
function seabedMat(color, rep, caustic) {
  const m = new THREE.MeshStandardMaterial({ map: tex('/tex/seabed_albedo.jpg', true, rep), normalMap: tex('/tex/seabed_normal.png', false, rep), normalScale: new THREE.Vector2(1.3, 1.3), roughness: .96, color });
  m.userData.u = { uT: { value: 0 }, uCa: { value: caustic } };
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, m.userData.u);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP;').replace('#include <project_vertex>', '#include <project_vertex>\nvWP=(modelMatrix*vec4(transformed,1.)).xyz;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP; uniform float uT,uCa;\n' + CAUSTIC)
      .replace('#include <opaque_fragment>', 'outgoingLight += diffuseColor.rgb * caustics(vWP.xz*.42, uT*1.3) * uCa;\n#include <opaque_fragment>');
  };
  return m;
}
function terrain(w, d, sw, sd, cx, cz, H) { const g = new THREE.PlaneGeometry(w, d, sw, sd); g.rotateX(-Math.PI / 2); const p = g.attributes.position; for (let i = 0; i < p.count; i++) { const x = p.getX(i) + cx, z = p.getZ(i) + cz; p.setXYZ(i, x, H(x, z), z); } g.computeVertexNormals(); return g; }
// Kamera etrafında sarılan "deniz karı" parçacıkları
function snow(n, box, seed, color, size) {
  const r = rng(seed);
  const geo = pointsGeo(n, (i, p, s, a) => { p[i * 3] = r() * box[0]; p[i * 3 + 1] = r() * box[1]; p[i * 3 + 2] = r() * box[2]; s[i] = .4 + r() * r() * 2.6; a[i] = .25 + r() * .75; });
  const m = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uCam: { value: new THREE.Vector3() }, uBox: { value: new THREE.Vector3(...box) }, uT: { value: 0 }, uDrift: { value: new THREE.Vector3(.08, -.1, .05) }, uSize: { value: size }, uCol: { value: new THREE.Color(color) },
      uAmb: { value: .2 }, uLP: { value: new THREE.Vector3() }, uLD: { value: new THREE.Vector3(0, 0, -1) }, uLI: { value: 0 }, uFogD: { value: .06 }, uH: { value: 1920 } },
    vertexShader: `attribute float aS; attribute float aA; uniform vec3 uCam,uBox,uDrift,uLP,uLD; uniform float uT,uSize,uH,uLI,uAmb,uFogD; varying float vA;
      void main(){ vec3 p=position+uDrift*uT+vec3(sin(uT*.7+position.y*3.)*.15,0.,cos(uT*.6+position.x*3.)*.15);
        p=uCam+mod(p-uCam+uBox*.5,uBox)-uBox*.5; vec4 mv=viewMatrix*vec4(p,1.); gl_Position=projectionMatrix*mv; float dz=-mv.z;
        gl_PointSize=clamp(uSize*aS*projectionMatrix[1][1]*uH/(2.*max(dz,.05)),1.,48.);
        vec3 d=p-uLP; float c=dot(normalize(d),uLD); float L=uLI*smoothstep(.8,.97,c)/(1.+dot(d,d)*.03);
        vA=aA*(uAmb+L)*exp(-dz*uFogD)*smoothstep(.1,.5,dz); }`,
    fragmentShader: `uniform vec3 uCol; varying float vA; void main(){ vec2 p=gl_PointCoord*2.-1.; float d=dot(p,p); if(d>1.)discard; float a=1.-d; gl_FragColor=vec4(uCol*vA*a*a,1.);}` });
  return new THREE.Points(geo, m);
}
function rays(n, seed, top, len, area) {
  const r = rng(seed), g = new THREE.Group();
  const m = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: { uT: { value: 0 }, uI: { value: 1 }, uCol: { value: new THREE.Color(0x8fe2ff) } },
    vertexShader: `varying vec2 vUv; varying float vD; void main(){ vUv=uv; vec4 mv=modelViewMatrix*vec4(position,1.); vD=-mv.z; gl_Position=projectionMatrix*mv;} `,
    fragmentShader: `uniform float uT,uI; uniform vec3 uCol; varying vec2 vUv; varying float vD; void main(){ float x=vUv.x; float e=smoothstep(0.,.4,x)*smoothstep(1.,.6,x);
      float s=.5+.5*sin(x*19.+uT*.8)*sin(x*7.3-uT*.5+vUv.y*2.); float f=pow(vUv.y,1.8)*smoothstep(0.,4.,vD);
      gl_FragColor=vec4(uCol*e*s*f*uI*.16,1.);}` });
  for (let i = 0; i < n; i++) { const w = 3 + r() * 7, p = new THREE.Mesh(new THREE.PlaneGeometry(w, len), m); p.position.set((r() - .5) * area, top - len / 2, (r() - .5) * area); p.rotation.y = r() * 3.14; p.rotation.z = (r() - .5) * .25; g.add(p); }
  g.userData.m = m; return g;
}
function surface(y, size) {
  const m = new THREE.ShaderMaterial({ uniforms: { uT: { value: 0 }, uI: { value: 1 }, uFog: { value: new THREE.Color(0x0b4f63) }, uFD: { value: .02 } }, side: THREE.DoubleSide, depthWrite: false,
    vertexShader: `varying vec3 vW; void main(){ vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform float uT,uI,uFD; uniform vec3 uFog; varying vec3 vW; void main(){ vec3 v=normalize(vW-cameraPosition); float up=clamp(v.y,0.,1.);
      vec2 p=vW.xz*.22; float w=(sin(p.x*3.+uT*1.3+sin(p.y*2.+uT))*.5+.5)*(sin(p.y*4.-uT*1.1+sin(p.x*3.))*.5+.5);
      float sn=smoothstep(.45,.9,up); vec3 c=mix(vec3(.04,.30,.40)*.9,vec3(.75,.95,1.)*1.45,sn)*(.72+.5*w);
      float d=length(vW-cameraPosition); c=mix(c,uFog,1.-exp(-pow(d*uFD,2.)));
      gl_FragColor=vec4(c*uI,1.);}` });
  const s = new THREE.Mesh(new THREE.PlaneGeometry(size, size, 1, 1), m); s.rotation.x = Math.PI / 2; s.position.y = y; return s;
}
function bubbles(n, seed, center, spread) {
  const r = rng(seed); const ring = canvasTex(64, 64, (g) => { g.strokeStyle = 'rgba(255,255,255,.9)'; g.lineWidth = 2.5; g.beginPath(); g.arc(32, 32, 27, 0, 7); g.stroke(); const rg = g.createRadialGradient(24, 22, 0, 24, 22, 10); rg.addColorStop(0, 'rgba(255,255,255,.9)'); rg.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = rg; g.fillRect(0, 0, 64, 64); });
  const data = Array.from({ length: n }, () => ({ x: (r() - .5) * spread, y: (r() - .2) * spread * .6, z: (r() - .5) * spread, s: .015 + r() * r() * .07, v: .8 + r() * 2.6, ph: r() * 6 }));
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3)); geo.setAttribute('aS', new THREE.BufferAttribute(new Float32Array(data.map(d => d.s)), 1)); geo.setAttribute('aA', new THREE.BufferAttribute(new Float32Array(n).fill(1), 1));
  const m = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { map: { value: ring }, uH: { value: 1920 }, uO: { value: 1 } },
    vertexShader: `attribute float aS; uniform float uH; void main(){ vec4 mv=modelViewMatrix*vec4(position,1.); gl_Position=projectionMatrix*mv; gl_PointSize=min(aS*projectionMatrix[1][1]*uH/(2.*max(-mv.z,.05)),200.); }`,
    fragmentShader: `uniform sampler2D map; uniform float uO; void main(){ gl_FragColor=texture2D(map,gl_PointCoord)*vec4(.8,.95,1.,uO)*uO*.8; }` });
  const pts = new THREE.Points(geo, m); pts.frustumCulled = false;
  pts.userData.step = (t) => { const p = geo.attributes.position; data.forEach((d, i) => p.setXYZ(i, center.x + d.x + Math.sin(t * 6 + d.ph) * .05, center.y + d.y + t * d.v, center.z + d.z + Math.cos(t * 5 + d.ph) * .05)); p.needsUpdate = true; };
  return pts;
}
function cone(color, len, rad) {
  const g = new THREE.ConeGeometry(rad, len, 32, 1, true); g.translate(0, -len / 2, 0);
  const m = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: { uI: { value: 1 }, uC: { value: new THREE.Color(color) } },
    vertexShader: `varying float vY; varying vec3 vN; varying vec3 vV; void main(){ vY=-position.y/${len.toFixed(2)}; vN=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }`,
    fragmentShader: `uniform float uI; uniform vec3 uC; varying float vY; varying vec3 vN; varying vec3 vV; void main(){ float f=pow(abs(dot(normalize(vN),normalize(vV))),1.5); gl_FragColor=vec4(uC*f*pow(1.-vY,2.)*smoothstep(0.,.05,vY)*uI*.12,1.);} ` });
  return new THREE.Mesh(g, m);
}
function aim(obj, from, dir) { obj.position.copy(from); obj.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), dir.clone().normalize()); }
const tube = (pts, r, seg = 200, rs = 10) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), seg, r, rs);
// ---------- SAHNE 2: dalış ve derin deniz tabanındaki kablo ----------
export function scene2(renderer) {
  const scene = new THREE.Scene(); const fog = new THREE.FogExp2(0x02141c, .05); scene.fog = fog; scene.background = new THREE.Color();
  const N = vnoise2(5), SEA = -60;
  const H = (x, z) => SEA + (N(x * .04, z * .04) - .5) * 3.2 + (N(x * .15 + 7, z * .15) - .5) * .9 + (N(x * .6, z * .6 + 3) - .5) * .18;
  const bed = new THREE.Mesh(terrain(160, 300, 200, 360, 0, -110, H), seabedMat(0x7d6f5c, 1, 0)); bed.material.normalScale.set(.55, .55); scene.add(bed);
  bed.material.map.repeat.set(26, 48); bed.material.normalMap.repeat.set(26, 48);
  const cxz = z => 1.2 * Math.sin(z * .02) + .5 * Math.sin(z * .07);
  const cp = []; for (let z = 40; z >= -260; z -= 4) { const x = cxz(z); cp.push(new THREE.Vector3(x, H(x, z) + .012, z)); }
  const cable = new THREE.Mesh(tube(cp, .024, 1600, 10), new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: .42 })); scene.add(cable);
  const flow = new THREE.Mesh(tube(cp, .034, 1600, 8), flowMat(0x35e0ff, { base: .1, freq: 300 / 5, speed: 3 / 300, fogD: .045 })); scene.add(flow);
  const cp2 = cp.map(p => new THREE.Vector3(p.x + 9 + Math.sin(p.z * .03) * 2, 0, p.z)).map(p => (p.y = H(p.x, p.z) + .012, p));
  scene.add(new THREE.Mesh(tube(cp2, .024, 1200, 8), cable.material));
  const r = rng(9), rockMat = new THREE.MeshStandardMaterial({ color: 0x3a3a3a, roughness: 1 });
  for (let i = 0; i < 70; i++) { const g = new THREE.IcosahedronGeometry(1, 2), p = g.attributes.position; for (let k = 0; k < p.count; k++) { const s = .7 + N(p.getX(k) * 2 + i, p.getY(k) * 2) * .6; p.setXYZ(k, p.getX(k) * s, p.getY(k) * s * .6, p.getZ(k) * s); } g.computeVertexNormals();
    const m = new THREE.Mesh(g, rockMat), x = (r() - .5) * 30, z = 30 - r() * 200; if (Math.abs(x - 1.2 * Math.sin(z * .02)) < 1.2) continue; m.position.set(x, H(x, z), z); m.scale.setScalar(.15 + r() * r() * 1.3); m.rotation.y = r() * 6; scene.add(m); }
  const hemi = new THREE.HemisphereLight(0x5fb0d0, 0x020406, 1); scene.add(hemi);
  const spot = new THREE.SpotLight(0xe0f4ff, 0, 0, .52, .75, 1.6); scene.add(spot, spot.target);
  const sn = snow(5000, [30, 22, 40], 4, 0xa8dcea, .045); scene.add(sn);
  const ry = rays(14, 3, 0, 40, 40); scene.add(ry);
  const surf = surface(0, 400); scene.add(surf);
  const bub = bubbles(420, 6, new THREE.Vector3(0, -6, 20), 9); scene.add(bub);
  const beamC = cone(0xcfefff, 22, 6.5); beamC.visible = false; scene.add(beamC);
  const cam = new THREE.PerspectiveCamera(50, 1080 / 1920, .05, 400);
  const deep = new THREE.Color(0x021520), shallow = new THREE.Color(0x0b5468);
  return { scene, cam, update(t, P, O) {
    // 0-0.7: yüzeyin hemen altı, 0.7-2.6: hızlı iniş, 2.6+: kablo boyunca süzülme
    const dsc = eio(clamp((t - .45) / 1.55)), glide = clamp((t - 2.0) / 4.1);
    const zc = lerp(24, 16.5, dsc) - glide * 7.5 - t * .4;
    const xc = lerp(0, 1.15, dsc) + Math.sin(t * .7) * .08;
    const ground = H(xc, zc);
    const y = lerp(-2.5 - t * 2, ground + 1.05, dsc);
    cam.position.set(xc, y, zc);
    const pitch = lerp(lerp(22, -70, eio(clamp(t / .8))), -20, sstep(1.2, 2.1, t)) * DEG;
    const fwd = new THREE.Vector3(-.12 * Math.sin(t * .4), Math.sin(pitch), -Math.cos(pitch)).normalize();
    cam.up.set(Math.sin(t * .9) * .03, 1, 0); cam.lookAt(cam.position.clone().add(fwd)); cam.fov = lerp(60, 50, dsc); cam.updateProjectionMatrix();
    const depth = clamp(-y / 50);
    fog.color.copy(shallow).lerp(deep, Math.pow(depth, .6)); scene.background.copy(fog.color); fog.density = lerp(.03, .058, depth);
    hemi.intensity = lerp(2.2, .05, Math.pow(depth, .5));
    const li = sstep(1.05, 1.25, t) * 70; spot.intensity = li;
    spot.position.copy(cam.position).add(new THREE.Vector3(.35, .25, 0)); spot.target.position.copy(cam.position).addScaledVector(fwd, 10).add(new THREE.Vector3(0, -1.5, 0));
    const ld = spot.target.position.clone().sub(spot.position).normalize();
    aim(beamC, spot.position.clone().add(new THREE.Vector3(.6, .2, 0)), ld); beamC.material.uniforms.uI.value = li / 85 * .8;
    const su = sn.material.uniforms; su.uCam.value.copy(cam.position); su.uT.value = t; su.uLP.value.copy(spot.position); su.uLD.value.copy(ld); su.uLI.value = li / 25; su.uAmb.value = lerp(.6, .1, depth); su.uFogD.value = fog.density * 1.2;
    ry.userData.m.uniforms.uT.value = t; ry.userData.m.uniforms.uI.value = 1 - depth;
    surf.material.uniforms.uT.value = t; surf.material.uniforms.uI.value = 1 - sstep(.2, .9, depth);
    bub.userData.step(t); bub.material.uniforms.uO.value = 1 - sstep(.7, 1.3, t);
    const fu = flow.material.uniforms; fu.uT.value = t; fu.uAmp.value = .75 * sstep(3.3, 4.4, t); fu.uFogD.value = fog.density * .8;
    Object.assign(P, { bloom: [.75, .5, .7], exposure: lerp(1.15, 1.2, depth), tone: 'aces', vignette: .6, grain: .05, sat: 1.0, contrast: 1.05, tint: [lerp(1, .86, depth), 1, lerp(1, 1.08, depth)] });
    const lz = zc - 3.4, lp = new THREE.Vector3(cxz(lz), H(cxz(lz), lz) + .03, lz);
    O.label(lp, cam, ['Fiber optik kablo', 'bahçe hortumu kalınlığında'], sstep(3.3, 3.7, t) * (1 - sstep(5.75, 6.05, t)), { dx: -250, dy: -330, color: '#4fe3ff', yr: [420, 1120] });
  } };
}
// ---------- Sığ deniz ortamı (Sahne 5 & 6A) ----------
function shallowEnv(renderer, scene, seed) {
  const fog = new THREE.FogExp2(0x0b4f63, .042); scene.fog = fog; scene.background = new THREE.Color(0x0b4f63);
  scene.environment = envFrom(renderer, '#9fe6ff', '#1a6f86', '#04161d');
  const N = vnoise2(seed); const H = (x, z) => (N(x * .07, z * .07) - .5) * .7 + (N(x * .3 + 3, z * .3) - .5) * .18;
  const bed = new THREE.Mesh(terrain(220, 220, 260, 260, 0, 0, H), seabedMat(0xb8b09a, 1, .55)); bed.material.map.repeat.set(30, 30); bed.material.normalMap.repeat.set(30, 30); scene.add(bed);
  scene.add(new THREE.HemisphereLight(0x9fe6ff, 0x1b2a22, 1.6));
  const sunL = new THREE.DirectionalLight(0xcff6ff, 1.6); sunL.position.set(5, 30, 8); scene.add(sunL);
  const ry = rays(22, seed + 1, 25, 34, 60); scene.add(ry);
  const surf = surface(25, 500); scene.add(surf);
  const sn = snow(3500, [30, 26, 40], seed + 2, 0xd8f4ff, .04); scene.add(sn);
  const r = rng(seed + 3), rockMat = new THREE.MeshStandardMaterial({ color: 0x55574f, roughness: 1 });
  for (let i = 0; i < 40; i++) { const g = new THREE.DodecahedronGeometry(1, 1), m = new THREE.Mesh(g, rockMat), x = (r() - .5) * 60, z = (r() - .5) * 60; if (Math.abs(z) < 2.5) continue; m.position.set(x, H(x, z) - .1, z); m.scale.set(.2 + r() * .7, .12 + r() * .35, .2 + r() * .7); m.rotation.y = r() * 6; scene.add(m); }
  // Deniz otları (basit şeritler)
  const weedM = new THREE.MeshStandardMaterial({ color: 0x2f5a2a, roughness: .9, side: THREE.DoubleSide });
  const weeds = []; for (let i = 0; i < 90; i++) { const x = (r() - .5) * 40, z = (r() - .5) * 40; if (Math.abs(z) < 3 || Math.abs(x) < 3 || z < 2) continue; const h = .6 + r() * 1.6; const g = new THREE.PlaneGeometry(.12, h, 1, 8); g.translate(0, h / 2, 0); const m = new THREE.Mesh(g, weedM); m.position.set(x, H(x, z), z); m.rotation.y = r() * 3; m.userData.ph = r() * 6; m.userData.g0 = g.attributes.position.array.slice(); scene.add(m); weeds.push(m); }
  const step = (t, cam) => {
    bed.material.userData.u.uT.value = t; ry.userData.m.uniforms.uT.value = t; surf.material.uniforms.uT.value = t;
    const su = sn.material.uniforms; su.uCam.value.copy(cam.position); su.uT.value = t; su.uAmb.value = .32; su.uFogD.value = .05;
    weeds.forEach(m => { const a = m.geometry.attributes.position, g0 = m.userData.g0; for (let k = 0; k < a.count; k++) { const yy = g0[k * 3 + 1]; a.setX(k, g0[k * 3] + Math.sin(t * 1.3 + m.userData.ph + yy) * .12 * yy); } a.needsUpdate = true; });
  };
  return { H, step, fog };
}
function anchorModel(mat) {
  const g = new THREE.Group();
  const shank = new THREE.Mesh(new THREE.BoxGeometry(.28, 2.5, .22), mat); shank.position.y = 1.35; g.add(shank);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(.2, .06, 10, 24), mat); ring.position.y = 2.75; g.add(ring);
  const crown = new THREE.Mesh(new THREE.BoxGeometry(1.0, .34, .44), mat); crown.position.y = .12; g.add(crown);
  const sh = new THREE.Shape(); sh.moveTo(-.24, 0); sh.lineTo(.24, 0); sh.lineTo(.17, .95); sh.lineTo(0, 1.5); sh.lineTo(-.17, .95); sh.closePath();
  const fg = new THREE.ExtrudeGeometry(sh, { depth: .14, bevelEnabled: true, bevelThickness: .03, bevelSize: .03, bevelSegments: 2 }); fg.translate(0, 0, -.07);
  for (const s of [-1, 1]) { const f = new THREE.Mesh(fg, mat); f.position.set(s * .42, .05, 0); f.rotation.z = -s * .62; g.add(f); }
  return g;
}
function chain(mat, n) {
  const g = new THREE.TorusGeometry(.13, .042, 6, 14); g.scale(1, 1.55, 1);
  const m = new THREE.InstancedMesh(g, mat, n); m.frustumCulled = false;
  const M = new THREE.Matrix4(), X = new THREE.Vector3(), Y = new THREE.Vector3(), Z = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  m.userData.set = (curve) => { const L = curve.getLength(), k = Math.min(n, Math.floor(L / .34)); for (let i = 0; i < n; i++) { if (i >= k) { M.makeScale(0, 0, 0); m.setMatrixAt(i, M); continue; }
    const u = i / (k - 1 || 1), p = curve.getPointAt(u); Y.copy(curve.getTangentAt(u)); X.crossVectors(up, Y).normalize(); if (X.lengthSq() < .01) X.set(1, 0, 0); Z.crossVectors(X, Y);
    if (i % 2) { const tx = X.clone(); X.copy(Z); Z.copy(tx).negate(); } M.makeBasis(X, Y, Z).setPosition(p); m.setMatrixAt(i, M); } m.instanceMatrix.needsUpdate = true; };
  return m;
}
function hullModel(len, wid) {
  const mat = new THREE.ShaderMaterial({ uniforms: { uFog: { value: new THREE.Color(0x0b4f63) } }, vertexShader: `varying vec3 vW; void main(){ vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
    fragmentShader: `uniform vec3 uFog; varying vec3 vW; void main(){ float d=length(vW-cameraPosition); gl_FragColor=vec4(mix(vec3(.004,.02,.026),uFog,1.-exp(-d*.016)),1.); }` });
  const g = new THREE.Group(); const cg = new THREE.CapsuleGeometry(wid / 2, len, 8, 20); cg.scale(1, 1, .5); cg.rotateX(Math.PI / 2);
  g.add(new THREE.Mesh(cg, mat));
  const keel = new THREE.Mesh(new THREE.BoxGeometry(.4, 1.0, len * .7), mat); keel.position.y = -wid * .25; g.add(keel);
  const rud = new THREE.Mesh(new THREE.BoxGeometry(.3, 2.2, 1.4), mat); rud.position.set(0, -1, -len / 2 - .5); g.add(rud);
  return g;
}
function puffs(n, color) {
  const geo = pointsGeo(n, (i, p, s, a) => { s[i] = 1; a[i] = 0; }); const m = particleMat({ color, size: 1, opacity: .32, additive: false, fogColor: 0x0b4f63, fogD: .045 });
  const p = new THREE.Points(geo, m); p.frustumCulled = false; return p;
}
// SAHNE 5: çapa kabloyu koparır (temsili)
export function scene5(renderer) {
  const scene = new THREE.Scene(); const E = shallowEnv(renderer, scene, 21); const H = E.H;
  const steel = new THREE.MeshStandardMaterial({ color: 0x4a4744, metalness: .75, roughness: .55 });
  const anchor = anchorModel(steel); scene.add(anchor);
  const ch = chain(steel, 150); scene.add(ch);
  const ship = hullModel(40, 9); ship.rotation.y = Math.PI / 2; scene.add(ship);
  const cabM = new THREE.MeshStandardMaterial({ color: 0x1b1d20, roughness: .5 });
  const L = new THREE.Mesh(new THREE.BufferGeometry(), cabM), Rr = new THREE.Mesh(new THREE.BufferGeometry(), cabM), FL = new THREE.Mesh(new THREE.BufferGeometry(), flowMat(0x38e8ff, { base: .18, freq: 14, speed: .12, fogD: .05 })), FR = new THREE.Mesh(new THREE.BufferGeometry(), flowMat(0x38e8ff, { base: .18, freq: 14, speed: .12, fogD: .05 }));
  scene.add(L, Rr, FL, FR);
  const pf = puffs(260, 0x8f8a78); scene.add(pf);
  const cam = new THREE.PerspectiveCamera(52, 1080 / 1920, .05, 400);
  const TC = 1.9, TS = 2.75, CR = .07;
  const az = (u) => u < TC ? lerp(-9, 0, u / TC) : u < TS ? lerp(0, 3.0, eio((u - TC) / (TS - TC)) * .6 + (u - TC) / (TS - TC) * .4) : 3.0 + (u - TS) * 2.0;
  const rr = rng(77); const pd = Array.from({ length: 260 }, (_, i) => ({ b: i < 180 ? .3 + i * (6.8 / 180) : (i < 225 ? TS + (i - 180) * .004 : 99), o: new THREE.Vector3((rr() - .5) * .9, rr() * .3, (rr() - .5) * .9), v: new THREE.Vector3((rr() - .5), rr() * .6 + .2, (rr() - .5)).multiplyScalar(i < 180 ? .45 : 1.6), s: .4 + rr() * .5 }));
  const disp = (x, u) => { // kablonun çapa tarafından sürüklenmesi
    if (u < TC) return [0, 0]; const zA = az(Math.min(u, TS)); const Ls = 1.6 + (Math.min(u, TS) - TC) * 5.5; const b = Math.pow(Math.max(0, 1 - (x / Ls) ** 2), 2);
    let dz = zA * b, dy = .35 * b * sstep(TC, TC + .3, u); if (u > TS) { const k = (u - TS); const damp = .42 + .58 * Math.exp(-2.6 * k) * Math.cos(9 * k); dz *= damp; dy *= Math.exp(-3 * k); } return [dz, dy]; };
  const build = (side, u) => { const pts = []; for (let i = 0; i <= 40; i++) { const gap = u > TS ? .02 + .55 * eout((u - TS) / .6) : .02; const x = side < 0 ? lerp(-38, -gap, i / 40) : lerp(gap * 1.4, 38, i / 40); const [dz, dy] = disp(x, u); const z = dz, y = H(x, z) + CR + dy; pts.push(new THREE.Vector3(x, y, z)); } return pts; };
  return { scene, cam, update(t, P, O) {
    const u = t; E.step(u, cam);
    const z = az(u); const cx = .2, crownY = H(cx, z) + .18;
    // Çapa yönelimi: gövde zincire doğru (+z ve yukarı)
    const Y = new THREE.Vector3(0, .42, .91).normalize(), X = new THREE.Vector3(1, 0, 0), Z = new THREE.Vector3().crossVectors(X, Y);
    anchor.matrixAutoUpdate = true; anchor.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(X, Y, Z)); anchor.rotateY(Math.sin(u * 2.1) * .04); anchor.position.set(cx, crownY - .05 + Math.sin(u * 9) * .015 * (u < 6 ? 1 : 0), z);
    anchor.updateMatrixWorld(); const shackle = new THREE.Vector3(0, 2.75, 0).applyMatrix4(anchor.matrixWorld);
    const shipZ = 26 + u * 1.6; ship.position.set(10, 24.4, shipZ); const hawse = new THREE.Vector3(-8.5, 22.6, shipZ - 1);
    const c = new THREE.CubicBezierCurve3(shackle, shackle.clone().add(new THREE.Vector3(-.6, .15, 5)), hawse.clone().add(new THREE.Vector3(2, -14, -5)), hawse); ch.userData.set(c);
    const tl = build(-1, u), tr = build(1, u);
    for (const [m, pts, r] of [[L, tl, CR], [Rr, tr, CR], [FL, tl, CR * 1.3], [FR, tr, CR * 1.3]]) { m.geometry.dispose(); m.geometry = tube(pts, r, 220, 10); }
    for (const m of [FL, FR]) { const f = m.material.uniforms; f.uT.value = u; f.uAmp.value = 1; }
    const cut = u > TS; FL.material.uniforms.uRed.value = cut ? (.6 + .4 * Math.sin(u * 14)) : 0; FL.material.uniforms.uCutU.value = 1.0;
    FR.material.uniforms.uDrain.value = cut ? 1 : 0; FR.material.uniforms.uCutT.value = (u - TS) * .12; FR.material.uniforms.uRed.value = 0;
    FR.material.uniforms.uBase.value = cut ? .18 * Math.max(0, 1 - (u - TS) * .8) : .18;
    // Tortu bulutları
    const pa = pf.geometry.attributes.position, ps = pf.geometry.attributes.aS, pA = pf.geometry.attributes.aA;
    pd.forEach((d, i) => { const age = u - d.b; if (age < 0 || age > 5) { pA.setX(i, 0); return; } const src = i < 180 ? new THREE.Vector3(cx, H(cx, az(d.b)) + .1, az(d.b)) : new THREE.Vector3(0, H(0, 3) + .2, az(TS));
      pa.setXYZ(i, src.x + d.o.x + d.v.x * age * .6, src.y + d.o.y + d.v.y * Math.sqrt(age), src.z + d.o.z + d.v.z * age * .6); ps.setX(i, d.s * (.8 + age * .8)); pA.setX(i, Math.min(age / .25, 1) * Math.exp(-age * .55) * (i < 180 ? (d.b > TS + 1.5 ? .4 : 1) : 1.2)); });
    pa.needsUpdate = ps.needsUpdate = pA.needsUpdate = true;
    // Kamera: önce gemi+zincir (yukarı bakış), sonra çapayı takip, kopmada sarsıntı
    const sh = u > TS ? Math.exp(-(u - TS) * 3.5) * .12 : 0; const shk = new THREE.Vector3(Math.sin(u * 47) * sh, Math.sin(u * 61) * sh, 0);
    const follow = new THREE.Vector3(2.8 - Math.max(0, u - TS) * .12, 1.45 - Math.max(0, u - TS) * .06, az(Math.min(u, TS + .3)) - 6.8 + Math.max(0, u - TS) * .45);
    const p0 = new THREE.Vector3(3.2, 1.2, -13.5);
    cam.position.copy(p0.lerp(follow, eio(clamp((u - .45) / 1.35)))).add(new THREE.Vector3(1.2, 1.1, -2.2).multiplyScalar(eio(clamp((u - TS - .3) / 2.5)))).add(shk);
    const lookUp = new THREE.Vector3(-1.5, 15, 13), lookA = new THREE.Vector3(-.4, .55, az(Math.min(u, TS + .3)) + 2.6);
    cam.lookAt(lookUp.lerp(lookA, eio(clamp((u - .3) / 1.3))).lerp(new THREE.Vector3(.2, .25, .9), eio(clamp((u - TS - .2) / 1.6))));
    cam.fov = 52 - sstep(TS, 7.2, u) * 8; cam.updateProjectionMatrix();
    const fl = u > TS && u < TS + .25 ? 1 - (u - TS) / .25 : 0;
    Object.assign(P, { bloom: [.8, .5, .72], exposure: .95, tone: 'aces', vignette: .52, grain: .04, sat: 1.0, contrast: 1.06, flash: [1, .25, .2, fl * .35], glitch: u > TS && u < TS + .35 ? 1 : 0, ca: u > TS && u < TS + .5 ? 3 : 0 });
    O.badge('TEMSİLİ CANLANDIRMA', 540, 210, sstep(.1, .4, u));
    O.label(new THREE.Vector3(7, 22.5, shipZ), cam, ['Gemi'], sstep(.15, .4, u) * (1 - sstep(1.0, 1.25, u)), { dx: -260, dy: 120, color: '#ffd23f' });
    O.label(shackle.clone().lerp(new THREE.Vector3(cx, crownY, z), .5), cam, ['Çapa'], sstep(1.15, 1.4, u) * (1 - sstep(2.5, 2.75, u)), { dx: -300, dy: -260, color: '#ffd23f' });
    if (u > TS) O.warn('VERİ AKIŞI KESİLDİ', 540, 360, sstep(TS, TS + .15, u) * (1 - sstep(TS + 1.0, TS + 1.25, u)), u);
  } };
}
// SAHNE 6A: onarım gemisi kabloyu yüzeye çeker
function rovModel() {
  const g = new THREE.Group(); const y = new THREE.MeshStandardMaterial({ color: 0xff7a00, roughness: .45 }), d = new THREE.MeshStandardMaterial({ color: 0x15181b, roughness: .6, metalness: .4 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.6, .7, 1.2), y); body.position.y = .5; g.add(body);
  const skid = new THREE.Mesh(new THREE.BoxGeometry(1.7, .12, 1.3), d); g.add(skid);
  for (const [x, z] of [[-.75, -.5], [.75, -.5], [-.75, .5], [.75, .5]]) { const th = new THREE.Mesh(new THREE.CylinderGeometry(.15, .15, .32, 16), d); th.position.set(x, .95, z); g.add(th); }
  for (const x of [-.45, .45]) { const l = new THREE.Mesh(new THREE.SphereGeometry(.08, 12, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(6, 6, 5.5) })); l.position.set(x, .45, .62); g.add(l); }
  const arm = new THREE.Mesh(new THREE.BoxGeometry(.1, .1, .9), d); arm.position.set(.3, .2, .95); arm.rotation.x = .4; g.add(arm);
  return g;
}
export function scene6(renderer) {
  const scene = new THREE.Scene(); const E = shallowEnv(renderer, scene, 33); const H = E.H;
  const ship = hullModel(46, 11); ship.rotation.y = Math.PI / 2 - .25; ship.position.set(5, 25.5, 11); scene.add(ship);
  const cabM = new THREE.MeshStandardMaterial({ color: 0x1b1d20, roughness: .5 });
  const C = new THREE.Mesh(new THREE.BufferGeometry(), cabM), Cl = new THREE.Mesh(new THREE.BufferGeometry(), cabM); scene.add(C, Cl);
  const rope = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshStandardMaterial({ color: 0xd8c9a0, roughness: .8 })); scene.add(rope);
  const hook = new THREE.Mesh(new THREE.TorusGeometry(.22, .05, 8, 16, 4.2), new THREE.MeshStandardMaterial({ color: 0x777777, metalness: .8, roughness: .4 })); scene.add(hook);
  const rov = rovModel(); scene.add(rov);
  const sp1 = new THREE.SpotLight(0xfff6e0, 60, 0, .45, .6, 1.5), sp2 = sp1.clone(); scene.add(sp1, sp1.target, sp2, sp2.target);
  const b1 = cone(0xfff2d8, 9, 2.6), b2 = cone(0xfff2d8, 9, 2.6); scene.add(b1, b2);
  const cam = new THREE.PerspectiveCamera(54, 1080 / 1920, .05, 400);
  const top = new THREE.Vector3(2.5, 22.8, 9.5);
  return { scene, cam, update(t, P, O) {
    const u = t; E.step(u + 10, cam);
    const p = eio(clamp((u - .15) / 3.4)) * .72; // kaldırma ilerlemesi
    const end0 = new THREE.Vector3(.1, H(.1, 0) + .07, 0); const G = end0.clone().lerp(top, p);
    const td = 1 + p * 16; // kablonun yerden ayrıldığı nokta
    const pts = []; for (let i = 0; i <= 30; i++) { const x = lerp(38, td, i / 30); pts.push(new THREE.Vector3(x, H(x, 0) + .07, 0)); }
    const tdP = pts[pts.length - 1]; const mid = new THREE.Vector3(lerp(tdP.x, G.x, .55), lerp(tdP.y, G.y, .25), lerp(tdP.z, G.z, .5));
    const cur = new THREE.QuadraticBezierCurve3(tdP, mid, G); for (let i = 1; i <= 24; i++) pts.push(cur.getPoint(i / 24));
    C.geometry.dispose(); C.geometry = tube(pts, .07, 260, 10);
    const lp = []; for (let i = 0; i <= 20; i++) { const x = lerp(-38, -.15, i / 20); lp.push(new THREE.Vector3(x, H(x, 0) + .07, 0)); } Cl.geometry.dispose(); Cl.geometry = tube(lp, .07, 80, 10);
    rope.geometry.dispose(); rope.geometry = tube([G.clone().add(new THREE.Vector3(0, .25, 0)), G.clone().lerp(top, .5).add(new THREE.Vector3(.3, 0, 0)), top.clone().add(new THREE.Vector3(0, 2.5, 0))], .03, 60, 6);
    hook.position.copy(G).add(new THREE.Vector3(0, .1, 0)); hook.rotation.set(0, 0, u * .3);
    const rp = new THREE.Vector3(G.x + 2.4, Math.min(G.y, 5.5) - .4 + Math.sin(u * 1.7) * .12, G.z - 1.2); rov.position.copy(rp); rov.lookAt(G.x, rp.y, G.z);
    rov.updateMatrixWorld();
    const lw = [new THREE.Vector3(-.45, .45, .62), new THREE.Vector3(.45, .45, .62)].map(v => v.applyMatrix4(rov.matrixWorld)); const ld = G.clone().sub(rp).normalize().add(new THREE.Vector3(0, -.25, 0)).normalize();
    [[sp1, b1, lw[0]], [sp2, b2, lw[1]]].forEach(([s, b, w]) => { s.position.copy(w); s.target.position.copy(w).addScaledVector(ld, 6); aim(b, w, ld); });
    cam.position.set(-9 + u * .35, 1.8 + u * .4, -11); cam.lookAt(new THREE.Vector3(2, lerp(5.5, 9, eio(u / 4)), 4));
    Object.assign(P, { bloom: [.8, .5, .72], exposure: .95, tone: 'aces', vignette: .52, grain: .04, sat: 1.0, contrast: 1.06 });
    O.badge('TEMSİLİ CANLANDIRMA', 540, 210, 1);
    O.label(new THREE.Vector3(4, 23.5, 10), cam, ['Kablo onarım gemisi'], sstep(.2, .5, u) * (1 - sstep(3.7, 4.0, u)), { dx: -230, dy: 170, color: '#ffd23f', yr: [290, 1100] });
    O.label(G.clone().lerp(tdP, .35), cam, ['Kablo yüzeye çekiliyor'], sstep(1.0, 1.3, u) * (1 - sstep(3.7, 4.0, u)), { dx: -330, dy: 260, color: '#4fe3ff', yr: [380, 1180] });
  } };
}
