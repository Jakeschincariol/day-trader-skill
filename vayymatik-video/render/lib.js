import * as THREE from 'three';
export const DEG = Math.PI / 180;
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, t) => a + (b - a) * t;
export const sstep = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
export const eio = t => (t = clamp(t), t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const ein = t => (t = clamp(t), t * t * t);
export const eout = t => (t = clamp(t), 1 - Math.pow(1 - t, 3));
export function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
// Küre üzerinde enlem/boylam -> dünya koordinatı (SphereGeometry UV eşlemesiyle uyumlu)
export function ll2v(lat, lon, r = 1) { const p = (lon + 180) * DEG, t = lat * DEG; return new THREE.Vector3(-Math.cos(p) * Math.cos(t) * r, Math.sin(t) * r, Math.sin(p) * Math.cos(t) * r); }
export function vnoise2(seed = 1) {
  const R = rng(seed), P = new Uint8Array(512), V = new Float32Array(256);
  for (let i = 0; i < 256; i++) { P[i] = i; V[i] = R(); }
  for (let i = 255; i > 0; i--) { const j = Math.floor(R() * (i + 1)); [P[i], P[j]] = [P[j], P[i]]; }
  for (let i = 0; i < 256; i++) P[i + 256] = P[i];
  const h = (x, y) => V[P[P[x & 255] + (y & 255)]];
  return (x, y) => { const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi, u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    return lerp(lerp(h(xi, yi), h(xi + 1, yi), u), lerp(h(xi, yi + 1), h(xi + 1, yi + 1), u), v); };
}
const _tc = {};
export function tex(url, srgb = true, rep) {
  const k = url + srgb + rep; if (_tc[k]) return _tc[k];
  const t = _tc[k] = new THREE.TextureLoader().load(url); if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  if (rep) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep, rep); }
  t.anisotropy = 4; return t;
}
export function canvasTex(w, h, draw, srgb = true) { const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); if (srgb) t.colorSpace = THREE.SRGBColorSpace; return t; }
export const softDot = () => canvasTex(128, 128, (g, w) => { const r = g.createRadialGradient(64, 64, 0, 64, 64, 64); r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(.25, 'rgba(255,255,255,.6)'); r.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = r; g.fillRect(0, 0, w, w); });
// Ortam haritası (metal yansımaları için) - basit gradyan küre
export function envFrom(renderer, top, mid, bot, sunUV) {
  const t = canvasTex(512, 256, (g, w, h) => { const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, top); gr.addColorStop(.5, mid); gr.addColorStop(1, bot); g.fillStyle = gr; g.fillRect(0, 0, w, h);
    if (sunUV) { const r = g.createRadialGradient(sunUV[0] * w, sunUV[1] * h, 0, sunUV[0] * w, sunUV[1] * h, 40); r.addColorStop(0, '#fff'); r.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = r; g.fillRect(0, 0, w, h); } });
  t.mapping = THREE.EquirectangularReflectionMapping;
  const pm = new THREE.PMREMGenerator(renderer); const e = pm.fromEquirectangular(t).texture; pm.dispose(); return e;
}
// Parçacık malzemesi: boyut perspektifli, yumuşak disk, katmanlı renk/opaklık
export function particleMat({ color = 0xffffff, size = 1, opacity = 1, additive = true, fogColor = null, fogD = 0, spot = false }) {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    uniforms: { uColor: { value: new THREE.Color(color) }, uSize: { value: size }, uOp: { value: opacity }, uFog: { value: new THREE.Color(fogColor || 0) }, uFogD: { value: fogD },
      uLP: { value: new THREE.Vector3() }, uLD: { value: new THREE.Vector3(0, 0, -1) }, uSpot: { value: spot ? 1 : 0 }, uH: { value: 1920 } },
    vertexShader: `attribute float aS; attribute float aA; uniform float uSize, uH, uSpot; uniform vec3 uLP, uLD; varying float vA; varying float vD; varying float vL;
      void main(){ vec4 mv = modelViewMatrix * vec4(position,1.); gl_Position = projectionMatrix * mv; vD = -mv.z;
        gl_PointSize = min(uSize * aS * projectionMatrix[1][1] * uH / (2.0*max(-mv.z, .05)), 256.0); vA = aA;
        vec3 wp = (modelMatrix*vec4(position,1.)).xyz; vec3 d = wp - uLP; float c = dot(normalize(d), uLD);
        vL = mix(1., smoothstep(.82, .97, c) * 3.0 / (1. + dot(d,d)*0.01) + 0.08, uSpot); }`,
    fragmentShader: `uniform vec3 uColor, uFog; uniform float uOp, uFogD; varying float vA; varying float vD; varying float vL;
      void main(){ vec2 p = gl_PointCoord*2.-1.; float d = dot(p,p); if(d>1.) discard; float a = (1.-d); a*=a;
        float f = exp(-vD*uFogD); gl_FragColor = vec4(mix(uFog, uColor*vL, f), a*uOp*vA*(uFogD>0.? mix(.35,1.,f):1.)); }`
  });
}
export function pointsGeo(n, fn) { const p = new Float32Array(n * 3), s = new Float32Array(n), a = new Float32Array(n); for (let i = 0; i < n; i++) fn(i, p, s, a); const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3)); g.setAttribute('aS', new THREE.BufferAttribute(s, 1)); g.setAttribute('aA', new THREE.BufferAttribute(a, 1)); return g; }
// Kablo üzerindeki veri akışı görselleştirmesi (eklemeli parlayan tüp)
export function flowMat(color = 0x38e8ff, opts = {}) {
  return new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uT: { value: 0 }, uCol: { value: new THREE.Color(color) }, uBase: { value: opts.base ?? .25 }, uFreq: { value: opts.freq ?? 40 }, uSpeed: { value: opts.speed ?? .6 },
      uProg: { value: 1 }, uAmp: { value: 1 }, uFogD: { value: opts.fogD ?? 0 }, uCutU: { value: 2 }, uCutT: { value: 0 }, uDrain: { value: 0 }, uRed: { value: 0 }, uLen: { value: 1 } },
    vertexShader: `varying vec2 vUv; varying float vD; void main(){ vUv=uv; vec4 mv=modelViewMatrix*vec4(position,1.); vD=-mv.z; gl_Position=projectionMatrix*mv; }`,
    fragmentShader: `uniform float uT,uBase,uFreq,uSpeed,uProg,uAmp,uFogD,uCutU,uCutT,uDrain,uRed,uLen; uniform vec3 uCol; varying vec2 vUv; varying float vD;
      void main(){ float u=vUv.x; if(u>uProg) discard;
        float ph = u*uFreq - uT*uSpeed*uFreq; float p = pow(0.5+0.5*cos(6.2831*fract(ph)), 18.0);
        float drained = uDrain>0.5 ? step(uCutT, u) : 1.0;  // kesikten sonra akış boşalır
        float head = smoothstep(uProg-0.02, uProg, u)*2.0*step(uProg,0.995);
        float a = (uBase + p*1.6*drained + head) * uAmp;
        vec3 c = mix(uCol, vec3(1.,.15,.1), uRed*smoothstep(uCutU-0.08, uCutU, u));
        float side = 1.0 - abs(vUv.y-0.5)*0.0;
        gl_FragColor = vec4(c*a*exp(-vD*uFogD), 1.); }` });
}
