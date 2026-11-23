// SIFIRDAN ZİRVEYE — yeniden kullanılabilir setler: kuyumcu + çarşı, ev, ofis, finans uzayı
import * as THREE from 'three';
import { rng, canvasTex, envFrom, softDot, pointsGeo, particleMat } from './lib.js';
const M = {}; export const mat = (c, r = .7, m = 0, o) => { const k = `${c}|${r}|${m}|${JSON.stringify(o || 0)}`; return M[k] || (M[k] = new THREE.MeshStandardMaterial({ color: c, roughness: r, metalness: m, ...(o || {}) })); };
const BOX = new THREE.BoxGeometry(1, 1, 1), CYL = new THREE.CylinderGeometry(1, 1, 1, 24);
export const kutu = (g, m, x, y, z, w, h, d, ry = 0) => { const o = new THREE.Mesh(BOX, m); o.position.set(x, y, z); o.scale.set(w, h, d); o.rotation.y = ry; g.add(o); return o; };
const silindir = (g, m, x, y, z, r, h) => { const o = new THREE.Mesh(CYL, m); o.position.set(x, y, z); o.scale.set(r, h, r); g.add(o); return o; };
export function yaziTex(metin, { w = 1024, h = 256, renk = '#e8c46a', zemin = '#141414', font = '900 120px Mont', golge = 'rgba(255,200,90,.6)' } = {}) {
  return canvasTex(w, h, (g) => { g.fillStyle = zemin; g.fillRect(0, 0, w, h); g.font = font; g.textAlign = 'center'; g.textBaseline = 'middle'; if (golge) { g.shadowColor = golge; g.shadowBlur = 24; } g.fillStyle = renk; g.fillText(metin, w / 2, h / 2 + 6); });
}
const mermer = () => { const t = canvasTex(512, 512, (g, w) => { const r = rng(3); g.fillStyle = '#d9d2c6'; g.fillRect(0, 0, w, w); for (let i = 0; i < 70; i++) { g.strokeStyle = `rgba(${120 + r() * 60 | 0},${110 + r() * 50 | 0},${100 + r() * 40 | 0},${.08 + r() * .15})`; g.lineWidth = .6 + r() * 2.5; g.beginPath(); let x = r() * w, y = r() * w; g.moveTo(x, y); for (let k = 0; k < 6; k++) { x += (r() - .5) * 160; y += (r() - .3) * 120; g.lineTo(x, y); } g.stroke(); }
  g.strokeStyle = 'rgba(80,70,60,.35)'; g.lineWidth = 2; g.strokeRect(0, 0, w, w); }); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(6, 8); return t; };
const ALTIN = () => mat(0xd9aa3e, .22, 1, { envMapIntensity: 1.4 }), KADIFE = () => mat(0x5a0f1e, 1);
function mucevherTepsi(g, x, y, z, w, d, r) { // bilezik, yüzük, kolye, çeyrek altın
  kutu(g, KADIFE(), x, y, z, w, .03, d);
  const ti = new THREE.InstancedMesh(new THREE.TorusGeometry(.04, .006, 8, 28), ALTIN(), 40), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(); let n = 0;
  for (let i = 0; i < 40; i++) { const tip = (i + Math.floor(r() * 3)) % 4, px = x - w / 2 + .06 + (i % 10) * (w - .12) / 9, pz = z - d / 2 + .06 + Math.floor(i / 10) * (d - .12) / 3;
    const s = tip === 0 ? 1 : tip === 1 ? .32 : tip === 2 ? .6 : .38; q.setFromEuler(new THREE.Euler(tip === 3 ? Math.PI / 2 : Math.PI / 2 - .5, r() * 3, 0)); m4.compose(new THREE.Vector3(px, y + .02 + s * .02, pz), q, new THREE.Vector3(s, s, tip === 3 ? 4 : s)); ti.setMatrixAt(n++, m4); }
  g.add(ti);
}
// ---------- KUYUMCU + ÇARŞI (tek dünya: iç z∈[-4,4], vitrin z=4, sokak z>4) ----------
export function dukkanDunyasi(renderer) {
  const scene = new THREE.Scene(), g = new THREE.Group(); scene.add(g); const r = rng(11);
  const envGun = envFrom(renderer, '#d8e4f0', '#c9a77a', '#3a2a1e', [.5, .3]), envGece = envFrom(renderer, '#1a2234', '#4a3420', '#0a0806', [.5, .4]);
  // iç mekân
  const zemin = new THREE.Mesh(new THREE.PlaneGeometry(6, 8), new THREE.MeshStandardMaterial({ map: mermer(), roughness: .18, metalness: .05 })); zemin.rotation.x = -Math.PI / 2; g.add(zemin);
  const duvar = mat(0xb8a482, .9), ahsap = mat(0x3e2414, .55), tavan = mat(0xc8c0b0, .95);
  kutu(g, duvar, 0, 1.6, -4, 6, 3.2, .1); kutu(g, duvar, -3, 1.6, 0, .1, 3.2, 8); kutu(g, duvar, 3, 1.6, 0, .1, 3.2, 8); kutu(g, tavan, 0, 3.2, 0, 6, .08, 8);
  kutu(g, ahsap, -2.94, .5, 0, .04, 1, 8); kutu(g, ahsap, 2.94, .5, 0, .04, 1, 8);
  for (let i = 0; i < 6; i++) { const s = new THREE.Mesh(new THREE.CircleGeometry(.09, 20), new THREE.MeshBasicMaterial({ color: 0xfff2d8 })); s.rotation.x = Math.PI / 2; s.position.set(i % 2 ? 1.2 : -1.2, 3.15, -3 + Math.floor(i / 2) * 2.4); g.add(s); }
  // tezgâhlar (L): ana tezgâh z=-1.2, yan tezgâh x=-2.4
  const cam = new THREE.MeshStandardMaterial({ color: 0xdfefff, transparent: true, opacity: .16, roughness: .04, metalness: .2, depthWrite: false });
  const tezgah = (x, z, w, d, ry) => { const t = new THREE.Group(); t.position.set(x, 0, z); t.rotation.y = ry; g.add(t);
    kutu(t, ahsap, 0, .42, 0, w, .84, d); kutu(t, mat(0xc9a24a, .3, 1), 0, .85, d / 2, w, .02, .02); kutu(t, cam, 0, 1.0, 0, w, .3, d); kutu(t, mat(0xfff0cc, .4, 0, { emissive: 0xffd28a, emissiveIntensity: .45 }), 0, .865, 0, w - .05, .01, d - .1);
    mucevherTepsi(t, 0, .87, 0, w - .2, d - .16, r); return t; };
  tezgah(-.4, -1.2, 4, .62, 0); tezgah(-2.4, .6, 2.9, .62, Math.PI / 2);
  // arka duvar vitrinleri + tabela + ayna + çelik kasa
  for (const x of [-2, -.2, 1.6]) { kutu(g, ahsap, x, 1.55, -3.82, 1.5, 2.3, .3); kutu(g, mat(0x6a4a2a, .5, 0, { emissive: 0xc8904a, emissiveIntensity: .28 }), x, 1.55, -3.66, 1.4, 2.1, .01);
    for (let k = 0; k < 4; k++) { kutu(g, mat(0xe8dcc0, .3, .5), x, .75 + k * .5, -3.7, 1.36, .015, .2); mucevherTepsi(g, x, .77 + k * .5, -3.72, 1.2, .16, r); } }
  const tabelaM = new THREE.MeshBasicMaterial({ map: yaziTex('HASAN KUYUMCULUK') }); kutu(g, tabelaM, -.2, 2.95, -3.6, 2.6, .35, .02);
  kutu(g, mat(0xffffff, .03, 1), 2.6, 1.7, -2.2, .02, 1.4, .9);
  const kasa = kutu(g, mat(0x3a3e44, .45, .6), 2.45, .55, -3.35, .75, 1.1, .7); silindir(g, mat(0xc0c4c8, .3, 1), 2.45, .7, -2.99, .08, .03).rotation.x = Math.PI / 2;
  kutu(g, mat(0x1a1a1e, .4, .3), 1.25, 1.21, -1.3, .2, .1, .26); kutu(g, mat(0x2a2a2a, .3, .2), .8, 1.18, -1.3, .16, .04, .2); kutu(g, mat(0xdfefff, .05, .2, { transparent: true, opacity: .25 }), .8, 1.26, -1.3, .14, .12, .14); // POS + terazi (tezgâh üstü)
  // güvenlik kameraları
  for (const [x, z] of [[-2.8, -3.8], [2.8, 3.6], [2.8, -3.8]]) { const c = new THREE.Group(); c.position.set(x, 3.0, z); g.add(c); kutu(c, mat(0xf2f2f2, .5), 0, 0, 0, .1, .1, .2); silindir(c, mat(0x111111, .2), 0, 0, .11, .035, .02).rotation.x = Math.PI / 2; kutu(c, mat(0xff2020, .5, 0, { emissive: 0xff0000, emissiveIntensity: 2 }), .03, .04, .08, .015, .015, .015); c.lookAt(0, 1, 0); }
  // görüşme masası + sandalyeler
  const masa = new THREE.Group(); masa.position.set(1.7, 0, 1.3); g.add(masa); kutu(masa, mat(0x2a1a10, .4), 0, .74, 0, 1.0, .05, .7); silindir(masa, mat(0x8a7a5a, .3, 1), 0, .37, 0, .04, .74);
  const sandalye = (x, z, ry) => { const s = new THREE.Group(); s.position.set(x, 0, z); s.rotation.y = ry; g.add(s); kutu(s, mat(0x6a1a22, .8), 0, .45, 0, .46, .08, .46); kutu(s, mat(0x6a1a22, .8), 0, .85, -.21, .46, .7, .06); for (const [a, b] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) kutu(s, mat(0x1a1a1a, .4, .5), a * .2, .22, b * .2, .03, .44, .03); };
  sandalye(1.7, .68, 0); sandalye(1.7, 1.92, Math.PI); sandalye(.4, 0.0, Math.PI); // müşteri sandalyesi tezgâh önü
  const defter = kutu(g, mat(0x1e2a44, .7), 1.6, .78, 1.3, .3, .02, .22); const kalem = kutu(g, mat(0xd0b060, .3, 1), 1.82, .785, 1.3, .14, .008, .008, .4);
  // vitrin cephesi (z=4)
  const cerceve = mat(0x1a1612, .4, .4);
  kutu(g, cerceve, -3, 1.6, 4, .12, 3.2, .12); kutu(g, cerceve, 3, 1.6, 4, .12, 3.2, .12); kutu(g, cerceve, 0, 2.62, 4, 6, .1, .12); kutu(g, cerceve, .6, 1.3, 4, .06, 2.6, .1); kutu(g, cerceve, 1.8, 1.3, 4, .06, 2.6, .1);
  kutu(g, mat(0xc9d6e0, .05, .3, { transparent: true, opacity: .12, depthWrite: false }), 0, 1.3, 4.0, 6, 2.6, .02); kutu(g, duvar, 0, 2.95, 4, 6, .6, .1);
  const levha = new THREE.Mesh(new THREE.PlaneGeometry(1.1, .75), new THREE.MeshBasicMaterial({ map: canvasTex(512, 350, (c, w, h) => { c.fillStyle = '#fafaf4'; c.fillRect(0, 0, w, h); c.fillStyle = '#c41e1e'; c.font = '900 96px Mont'; c.textAlign = 'center'; c.fillText('DEVREN', w / 2, 140); c.fillText('SATILIK', w / 2, 250); c.font = '700 34px Mont'; c.fillStyle = '#222'; c.fillText('0532 ••• •• ••', w / 2, 315); }) }));
  levha.position.set(-1.3, 1.5, 4.04); g.add(levha);
  // dış cephe tabelası (z=4 dışı) + kepenk
  const dTabela = new THREE.Mesh(new THREE.PlaneGeometry(4.6, .75), new THREE.MeshBasicMaterial({ map: yaziTex('HASAN KUYUMCULUK', { w: 1600, h: 260 }) })); dTabela.position.set(0, 3.0, 4.07); g.add(dTabela);
  const ledTabela = new THREE.Mesh(new THREE.PlaneGeometry(4.6, .75), new THREE.MeshBasicMaterial({ map: yaziTex('EMİR KUYUMCULUK', { w: 1600, h: 260, renk: '#ffe6a0', zemin: '#0c0c10', golge: 'rgba(255,190,80,1)' }), color: new THREE.Color(1.6, 1.5, 1.3) })); ledTabela.position.set(0, 3.0, 4.075); g.add(ledTabela);
  const kepenk = kutu(g, mat(0x8a8e94, .5, .7), 0, 1.3, 4.12, 6, 2.6, .03);
  // sokak: kaldırım, yol, karşı cepheler, lambalar, park etmiş araçlar
  const yolM = mat(0x2c2c2e, .55); kutu(g, mat(0x9a948a, .7), 0, -.05, 6, 60, .1, 4); kutu(g, yolM, 0, -.08, 12, 60, .06, 8);
  const cephe = (x, z, w, ry, renk, ad) => { const c = new THREE.Group(); c.position.set(x, 0, z); c.rotation.y = ry; g.add(c); kutu(c, mat(renk, .85), 0, 3, 0, w, 6, .3); kutu(c, mat(0x1a2430, .1, .4, { emissive: 0x3a2a1a, emissiveIntensity: .25 }), 0, 1.3, .16, w - .6, 2.2, .02);
    const tb = new THREE.Mesh(new THREE.PlaneGeometry(w - .8, .55), new THREE.MeshBasicMaterial({ map: yaziTex(ad, { w: 1024, h: 180, renk: '#f4f0e6', zemin: '#2a3a4a', font: '800 92px Mont', golge: null }) })); tb.position.set(0, 2.85, .17); c.add(tb);
    kutu(c, mat(r() < .5 ? 0x7a2a2a : 0x2a5a4a, .8), 0, 2.45, .5, w - .4, .06, .8); };
  cephe(-6, 4.15, 5.6, 0, 0xb8a88c, 'TERZİ ŞAHİN'); cephe(6, 4.15, 5.6, 0, 0xa89a8a, 'SAATÇİ'); cephe(-12, 4.15, 5.6, 0, 0xc4b49a, 'BAKKAL'); cephe(12, 4.15, 5.6, 0, 0xb0a48e, 'ÇİÇEKÇİ');
  cephe(-6, 16.5, 7, Math.PI, 0xbcae94, 'ECZANE'); cephe(2, 16.5, 7, Math.PI, 0xa89c88, 'KIRTASİYE'); cephe(10, 16.5, 7, Math.PI, 0xc2b296, 'FIRIN');
  const lambalar = []; for (const x of [-9, 3, 15]) { silindir(g, mat(0x222222, .4, .6), x, 2.2, 7.6, .05, 4.4); const b = new THREE.Mesh(new THREE.SphereGeometry(.18, 12, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(4, 3, 1.6) })); b.position.set(x, 4.4, 7.6); g.add(b); const pl = new THREE.PointLight(0xffb060, 0, 14, 1.5); pl.position.set(x, 4.2, 7.6); g.add(pl); lambalar.push([b, pl]); }
  const araba = (x, z, renk, ry = 0) => { const a = new THREE.Group(); a.position.set(x, 0, z); a.rotation.y = ry; g.add(a); const gv = mat(renk, .25, .6);
    kutu(a, gv, 0, .55, 0, 4.2, .6, 1.8); kutu(a, gv, -.15, 1.05, 0, 2.3, .5, 1.6); kutu(a, mat(0x1a2a3a, .05, .6), -.15, 1.06, 0, 2.2, .44, 1.62); kutu(a, mat(0x1a2a3a, .05, .6), -.15, 1.06, 0, 2.32, .44, 1.5);
    for (const [u, v] of [[-1.35, -.9], [1.35, -.9], [-1.35, .9], [1.35, .9]]) { const t = silindir(a, mat(0x111111, .8), u, .34, v, .34, .26); t.rotation.x = Math.PI / 2; }
    kutu(a, mat(0xfff8e0, .2, 0, { emissive: 0xffffff, emissiveIntensity: .6 }), 2.1, .62, .6, .04, .12, .3); kutu(a, mat(0xfff8e0, .2, 0, { emissive: 0xffffff, emissiveIntensity: .6 }), 2.1, .62, -.6, .04, .12, .3); return a; };
  araba(-8, 10, 0x8a2020); araba(9, 13.8, 0xd8d8d8, Math.PI);
  const emirAraba = araba(-20, 9.6, 0x2a4a7a); const satilik = new THREE.Mesh(new THREE.PlaneGeometry(.7, .45), new THREE.MeshBasicMaterial({ map: canvasTex(400, 260, (c, w, h) => { c.fillStyle = '#ffd400'; c.fillRect(0, 0, w, h); c.fillStyle = '#111'; c.font = '900 88px Mont'; c.textAlign = 'center'; c.fillText('SATILIK', w / 2, 120); c.font = '700 40px Mont'; c.fillText('Sahibinden', w / 2, 200); }) }));
  satilik.position.set(-20.2, 1.08, 10.42); g.add(satilik); kutu(g, mat(0x9a948a, .7), -20, -.05, 6, 1, .1, 1);
  // gökyüzü + yağmur + ışıklar
  const gok = new THREE.Mesh(new THREE.SphereGeometry(200, 32, 16), new THREE.ShaderMaterial({ side: THREE.BackSide, depthWrite: false, uniforms: { a: { value: new THREE.Color() }, b: { value: new THREE.Color() } }, vertexShader: 'varying vec3 v; void main(){ v=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }', fragmentShader: 'uniform vec3 a,b; varying vec3 v; void main(){ float h=clamp(normalize(v).y*2.,0.,1.); gl_FragColor=vec4(mix(a,b,h),1.); }' })); scene.add(gok);
  const yg = pointsGeo(2500, (i, p, s, al) => { p[i * 3] = -10 + r() * 20; p[i * 3 + 1] = r() * 6; p[i * 3 + 2] = 4.4 + r() * 10; s[i] = .5 + r(); al[i] = .3 + r() * .6; });
  const yagmur = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x9fb4cc, transparent: true, opacity: .35 })); scene.add(yagmur); const yp = yg.attributes.position.array;
  const hemi = new THREE.HemisphereLight(0xfff4e0, 0x3a2a1a, .6), gunes = new THREE.DirectionalLight(0xfff0d8, 2.0); gunes.position.set(-6, 10, 18); scene.add(hemi, gunes);
  const spotlar = []; for (const [x, z] of [[-1.5, -1.2], [.7, -1.2], [-2.4, .6], [-.2, -3.4], [1.7, 1.3]]) { const s = new THREE.SpotLight(0xffe0b0, 0, 9, .55, .7, 1.2); s.position.set(x, 3.1, z); s.target.position.set(x, 0, z); scene.add(s, s.target); spotlar.push(s); }
  const lamba = new THREE.PointLight(0xffc070, 0, 4, 1.5); lamba.position.set(2.15, 1.35, 1.3); scene.add(lamba); // masa lambası: iki sandalyeye eşit uzaklıkta
  const ayar = (o) => { const gece = o.mod === 'gece', aks = o.mod === 'aksam' || o.mod === 'gunbatimi';
    scene.environment = gece ? envGece : envGun; gok.material.uniforms.a.value.set(gece ? 0x0a1220 : aks ? 0xf0a060 : 0xcfe0ee); gok.material.uniforms.b.value.set(gece ? 0x02040a : aks ? 0x3a4a78 : 0x6a9ad0);
    hemi.intensity = gece ? .1 : aks ? .32 : .42; gunes.intensity = gece ? .0 : aks ? 1.0 : 1.8; gunes.color.set(aks ? 0xff9a50 : 0xfff0d8); gunes.position.set(aks ? -20 : -6, aks ? 4 : 10, 18);
    spotlar.forEach(s => s.intensity = o.ic === false ? 0 : gece ? 4.5 : 6.5); lamba.intensity = gece ? 2.2 : 0; lambalar.forEach(([b, pl]) => { pl.intensity = gece || aks ? 22 : 0; b.visible = gece || aks; });
    levha.visible = !!o.devren; dTabela.visible = o.tabela === 'hasan'; ledTabela.visible = o.tabela === 'emir'; tabelaM.map = o.tabela === 'hasan' || o.devren ? tabelaM.map : (tabelaM.userData.emir || (tabelaM.userData.emir = yaziTex('EMİR KUYUMCULUK')));
    kepenk.position.y = 1.3 + (o.kepenk != null ? o.kepenk : 1) * 2.4; kepenk.visible = kepenk.position.y < 3.6; emirAraba.visible = satilik.visible = !!o.araba;
    yagmur.visible = !!o.yagmur; if (o.yagmur) { const pts = []; for (let i = 0; i < yp.length; i += 3) { const y = ((yp[i + 1] - (o.t || 0) * 9) % 6 + 6) % 6; pts.push(yp[i], y, yp[i + 2], yp[i] - .02, y + .35, yp[i + 2]); } yagmur.geometry.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3)); }
    zemin.material.roughness = .18; };
  return { scene, ayar, defter, kalem };
}
// ---------- EV (oturma odası) ----------
export function evDunyasi(renderer) {
  const scene = new THREE.Scene(), g = new THREE.Group(); scene.add(g); scene.environment = envFrom(renderer, '#f0d8b0', '#8a6a4a', '#2a1e14', [.3, .4]); scene.background = new THREE.Color(0x1a1410);
  const hali = new THREE.Mesh(new THREE.PlaneGeometry(3, 2.2), new THREE.MeshStandardMaterial({ map: canvasTex(512, 380, (c, w, h) => { c.fillStyle = '#7a2a22'; c.fillRect(0, 0, w, h); c.strokeStyle = '#d8b070'; c.lineWidth = 10; c.strokeRect(20, 20, w - 40, h - 40); c.strokeStyle = '#2a3a5a'; c.lineWidth = 6; for (let i = 0; i < 6; i++) { c.beginPath(); c.ellipse(w / 2, h / 2, 40 + i * 25, 25 + i * 18, 0, 0, 7); c.stroke(); } }), roughness: 1 }));
  hali.rotation.x = -Math.PI / 2; hali.position.set(0, .01, .3); g.add(hali);
  kutu(g, mat(0x8a6a4a, .6), 0, 0, 0, 7, .02, 7); kutu(g, mat(0xd8c8a8, .9), 0, 1.4, -3, 7, 2.8, .1); kutu(g, mat(0xcfbe9e, .9), -3.4, 1.4, 0, .1, 2.8, 7); kutu(g, mat(0xcfbe9e, .9), 3.4, 1.4, 0, .1, 2.8, 7);
  const kanepe = mat(0x5a6a5a, .9); kutu(g, kanepe, 0, .25, -1.9, 2.4, .5, .9); kutu(g, kanepe, 0, .72, -2.28, 2.4, .6, .2); kutu(g, kanepe, -1.15, .45, -1.9, .2, .5, .9); kutu(g, kanepe, 1.15, .45, -1.9, .2, .5, .9);
  const koltuk = new THREE.Group(); koltuk.position.set(2.1, 0, .2); koltuk.rotation.y = -Math.PI / 2; g.add(koltuk); kutu(koltuk, mat(0x7a5a3a, .9), 0, .25, 0, 1, .5, .9); kutu(koltuk, mat(0x7a5a3a, .9), 0, .75, -.38, 1, .6, .18);
  kutu(g, mat(0x5a3a24, .5), 0, .22, .1, 1.2, .06, .6); for (const s of [-.3, .1, .4]) { const b = new THREE.Mesh(new THREE.CylinderGeometry(.03, .022, .09, 12), mat(0xb03a10, .1, 0, { transparent: true, opacity: .8 })); b.position.set(s, .3, .1); g.add(b); }
  kutu(g, mat(0x2a1e16, .5), 0, .25, 2.9, 2, .5, .4); kutu(g, mat(0x0a0a0c, .2, .5, { emissive: 0x16243a, emissiveIntensity: .6 }), 0, .95, 2.95, 1.4, .8, .05);
  kutu(g, mat(0xf0e6c8, .9, 0, { emissive: 0x3a4a6a, emissiveIntensity: .5 }), -3.34, 1.5, -.5, .02, 1.3, 1.6); for (const s of [-1, 1]) kutu(g, mat(0x8a3a3a, 1), -3.3, 1.5, -.5 + s * .95, .05, 1.8, .4);
  for (const x of [-1.2, .3, 1.5]) kutu(g, mat(0x3a2a1a, .4), x, 1.8, -2.94, .5, .38, .03);
  const lamba = new THREE.PointLight(0xffb870, 8, 8, 1.4); lamba.position.set(-1.6, 1.9, -1.4); scene.add(lamba, new THREE.HemisphereLight(0xffe8c8, 0x2a1a10, .5));
  const ay = new THREE.DirectionalLight(0x8aa0d0, .5); ay.position.set(-5, 3, 1); scene.add(ay);
  const laptop = new THREE.Group(); laptop.position.set(-.3, .25, .05); g.add(laptop); kutu(laptop, mat(0x8a8e94, .3, .7), 0, 0, 0, .34, .015, .24); const ekran = kutu(laptop, mat(0x111111, .2, .3, { emissive: 0x6a8ab0, emissiveIntensity: .9 }), 0, .12, -.11, .34, .23, .01); ekran.rotation.x = -.25;
  const kagit = kutu(g, mat(0xf4f0e6, .9), .25, .26, .12, .21, .003, .3);
  return { scene, laptop, kagit, ayar: (o) => { lamba.intensity = o.gece ? 5 : 8; laptop.visible = !!o.laptop; kagit.visible = !!o.kagit; } };
}
// ---------- MUHASEBE OFİSİ ----------
export function ofisDunyasi(renderer) {
  const scene = new THREE.Scene(), g = new THREE.Group(); scene.add(g); scene.environment = envFrom(renderer, '#e8eef4', '#9aa4ae', '#2a2e34', [.4, .3]); scene.background = new THREE.Color(0x20242a);
  kutu(g, mat(0x6a5e50, .6), 0, 0, 0, 8, .02, 8); kutu(g, mat(0xd2d6d8, .9), 0, 1.5, -3, 8, 3, .1); kutu(g, mat(0xc8ccce, .9), -3.5, 1.5, 0, .1, 3, 8);
  const masa = mat(0x3a2a1e, .45); kutu(g, masa, 0, .74, -.6, 1.8, .05, .85); kutu(g, masa, -.8, .37, -.6, .05, .72, .8); kutu(g, masa, .8, .37, -.6, .05, .72, .8);
  for (let i = 0; i < 4; i++) for (let k = 0; k < 7; k++) kutu(g, mat([0x2a4a7a, 0x7a2a2a, 0x2a6a4a, 0xc8a040][(i + k) % 4], .7), -2.6 + k * .2, .75 + i * .45, -2.85, .14, .38, .26);
  for (let i = 0; i < 4; i++) kutu(g, mat(0x4a3a2a, .5), -2, .55 + i * .45, -2.85, 1.6, .03, .32);
  const laptop = new THREE.Group(); laptop.position.set(.35, .77, -.7); laptop.rotation.y = -.3; g.add(laptop); kutu(laptop, mat(0x2a2a2e, .3, .6), 0, 0, 0, .36, .015, .25); const ek = kutu(laptop, mat(0x111111, .2, .3, { emissive: 0xc8d8e8, emissiveIntensity: .7 }), 0, .12, -.12, .36, .24, .01); ek.rotation.x = -.25;
  for (let i = 0; i < 3; i++) kutu(g, mat(0xf6f4ee, .9), -.35 + i * .04, .78 + i * .004, -.5 + i * .03, .21, .003, .3, i * .1);
  const lamba = new THREE.PointLight(0xfff0d8, 6, 7, 1.3); lamba.position.set(-.6, 1.6, -.3); scene.add(lamba, new THREE.HemisphereLight(0xeef4ff, 0x3a3430, .7));
  const pencere = kutu(g, mat(0xdde8f0, .9, 0, { emissive: 0x9ab4cc, emissiveIntensity: .8 }), 2.2, 1.7, -2.94, 1.6, 1.4, .02); for (let i = 0; i < 9; i++) kutu(g, mat(0xe8e8e8, .6), 2.2, 1.06 + i * .155, -2.9, 1.62, .025, .03);
  const sandalye = (x, z, ry) => { const s = new THREE.Group(); s.position.set(x, 0, z); s.rotation.y = ry; g.add(s); kutu(s, mat(0x1a1a1e, .6), 0, .46, 0, .5, .08, .5); kutu(s, mat(0x1a1a1e, .6), 0, .85, -.22, .5, .7, .06); };
  sandalye(0, -1.35, 0); sandalye(0, .25, Math.PI);
  return { scene };
}
// ---------- FİNANS UZAYI (HUD arka planı) ----------
export function hudDunyasi(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x03070e); scene.environment = envFrom(renderer, '#2a3a52', '#0a1220', '#000000', [.5, .2]);
  const r = rng(5), coin = new THREE.InstancedMesh(new THREE.CylinderGeometry(.5, .5, .06, 40), mat(0xd9aa3e, .25, 1), 60), m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
  const veri = Array.from({ length: 60 }, () => ({ p: new THREE.Vector3((r() - .5) * 26, (r() - .5) * 14, -6 - r() * 18), e: new THREE.Euler(r() * 6, r() * 6, 0), w: (r() - .5) * .6 })); scene.add(coin);
  const grid = new THREE.GridHelper(80, 80, 0x1a4a6a, 0x0c2236); grid.position.y = -6; scene.add(grid);
  const nok = new THREE.Points(pointsGeo(600, (i, p, s, a) => { p[i * 3] = (r() - .5) * 40; p[i * 3 + 1] = (r() - .5) * 20; p[i * 3 + 2] = -2 - r() * 30; s[i] = .05 + r() * .12; a[i] = .2 + r() * .6; }), particleMat({ color: 0xffd28a, size: 1, opacity: .5 })); scene.add(nok);
  scene.add(new THREE.HemisphereLight(0x8ab4ff, 0x0a0a0a, .6)); const d = new THREE.DirectionalLight(0xffe0b0, 2.2); d.position.set(4, 6, 8); scene.add(d);
  return { scene, ayar: (o) => { veri.forEach((v, i) => { q.setFromEuler(new THREE.Euler(v.e.x + o.t * v.w, v.e.y + o.t * v.w * .7, 0)); m4.compose(v.p.clone().add(new THREE.Vector3(0, Math.sin(o.t * .3 + i) * .3, 0)), q, new THREE.Vector3(1, 1, 1)); coin.setMatrixAt(i, m4); }); coin.instanceMatrix.needsUpdate = true; } };
}
