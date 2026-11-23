// SIFIRDAN ZİRVEYE — yeniden kullanılabilir karakter sistemi (stilize sinematik 3D insanlar)
// insan(spec) -> { g, poz(p) }   p: { x, z, yaw, otur, bas:[yaw,pitch], egil, kolL, kolR, yuru, agiz, ifade, kirp, t }
import * as THREE from 'three';
const M = {}; const mat = (c, r = .7, m = 0, o) => { const k = `${c}|${r}|${m}|${o}`; return M[k] || (M[k] = new THREE.MeshStandardMaterial({ color: c, roughness: r, metalness: m, ...(o || {}) })); };
const mesh = (g, m, p, s, r) => { const o = new THREE.Mesh(g, m); if (p) o.position.set(...p); if (s) o.scale.set(...s); if (r) o.rotation.set(...r); return o; };
const SP = new THREE.SphereGeometry(1, 28, 20), CYL = new THREE.CylinderGeometry(1, 1, 1, 20), BOX = new THREE.BoxGeometry(1, 1, 1);
const cap = (r, L) => new THREE.CapsuleGeometry(r, L, 6, 14);
export const KARAKTER = {
  emir: { boy: 1.78, ten: 0xd8a47a, sac: 0x22160f, sacTip: 'kisa', sakal: 'kirli', kiyafet: { ev: ['kapsonlu', 0x6c7076, 0x2c3542], dukkan: ['gomlek', 0x203452, 0x2a2f38], gelecek: ['ceket', 0x16161a, 0x1e2026, 0xf2f2ee] }, ayakkabi: 0x1e1e1e },
  kenan: { boy: 1.80, ten: 0xd0a07a, sac: 0x9a9a98, sacTip: 'geri', sakal: 'tam', sakalRenk: 0x5e5c5a, kiyafet: { _: ['takim', 0x131418, 0x131418, 0xf4f4f4, 0x6a1c2a] }, saat: 0xd8b04a, ayakkabi: 0x0d0d0d },
  hasan: { boy: 1.70, ten: 0xcf9d76, sac: 0xe9e5dc, sacTip: 'kel', sakal: 'biyik', gozluk: 0x3a3028, kiyafet: { _: ['hirka', 0x6b5a46, 0x4a4842, 0xd9d1c2] }, ayakkabi: 0x3a2a1e },
  baba: { boy: 1.74, ten: 0xcc9970, sac: 0x5a544e, sacTip: 'kisa', sakal: 'biyik', kiyafet: { _: ['kazak', 0xb49d78, 0x3e3a34] }, ayakkabi: 0x2a2018 },
  anne: { boy: 1.62, ten: 0xd8a882, sac: 0x7a4a5a, sacTip: 'basortu', kiyafet: { _: ['uzun', 0x55687c, 0x343844] }, ayakkabi: 0x2a2a2a },
  kerem: { boy: 1.81, ten: 0xd6a37a, sac: 0x15100c, sacTip: 'kisa', sakal: 'kirli', kiyafet: { _: ['mont', 0x3c5a3e, 0x26282e] }, ayakkabi: 0xe8e8e8 },
  murat: { boy: 1.76, ten: 0xd2a27c, sac: 0x241e1a, sacTip: 'geri', kiyafet: { _: ['takim', 0x2b3850, 0x2b3850, 0xe9eef4, 0x8c7a4a] }, saat: 0xc8ccd2, ayakkabi: 0x3a2416 },
  ahmet: { boy: 1.72, ten: 0xd4a37e, sac: 0x4a4038, sacTip: 'geri', gozluk: 0x1a1a1a, kiyafet: { _: ['yelek', 0x575c64, 0x3a3e46, 0xe6ebf0, 0x233552] }, ayakkabi: 0x1a1a1a },
  musteri: { boy: 1.75, ten: 0xc89868, sac: 0x2a2622, sacTip: 'kisa', sakal: 'tam', kiyafet: { _: ['mont', 0x6a4a36, 0x33343a] }, ayakkabi: 0x2a1e16 },
  musteri2: { boy: 1.64, ten: 0xdcae88, sac: 0x5a3a24, sacTip: 'uzun', kiyafet: { _: ['uzun', 0x8a3a4c, 0x2a2a30] }, ayakkabi: 0x3a1a1a },
  alici: { boy: 1.77, ten: 0xcf9f74, sac: 0x3a2e26, sacTip: 'kisa', sakal: 'kirli', kiyafet: { _: ['gomlek', 0x8aa2bc, 0x3a3e48] }, ayakkabi: 0x2a2a2a },
  usta: { boy: 1.72, ten: 0xc99a70, sac: 0x3a342e, sacTip: 'kisa', sakal: 'tam', gozluk: 0x2a2a2a, kiyafet: { _: ['onluk', 0x4a4e56, 0x30323a, 0x7a5a3a] }, ayakkabi: 0x2a2a2a }
};
export function insan(ad, donem = '_') {
  const S = KARAKTER[ad], k = S.boy / 1.78, K = S.kiyafet[donem] || S.kiyafet._ || Object.values(S.kiyafet)[0];
  const [tip, ust, alt, ic, kravat] = K, ten = mat(S.ten, .55), U = mat(ust, .78), A = mat(alt, .8), sacM = mat(S.sac, .85);
  const kol = tip === 'yelek' ? mat(ic, .7) : U;
  const g = new THREE.Group(), kok = new THREE.Group(); g.add(kok); kok.scale.setScalar(k);
  // bacaklar
  const bacak = (s) => { const kalca = new THREE.Group(); kalca.position.set(s * .1, .93, 0); const diz = new THREE.Group(); diz.position.y = -.45;
    kalca.add(mesh(cap(.078, .32), A, [0, -.22, 0])); diz.add(mesh(cap(.062, .34), A, [0, -.22, 0])); diz.add(mesh(BOX, mat(S.ayakkabi, .5), [0, -.43, .045], [.1, .07, .27])); kalca.add(diz); kok.add(kalca); return [kalca, diz]; };
  const [kL, dL] = bacak(-1), [kR, dR] = bacak(1);
  // gövde
  const govde = new THREE.Group(); govde.position.y = .95; kok.add(govde);
  govde.add(mesh(cap(.17, .3), U, [0, .27, 0], [1.16, 1, .74]));
  govde.add(mesh(cap(.16, .12), tip === 'yelek' ? mat(ic, .7) : A, [0, .02, 0], [1.08, 1, .72]));
  if (tip === 'uzun') govde.add(mesh(new THREE.CylinderGeometry(.2, .3, .62, 20, 1, true), mat(ust, .8, 0, { side: THREE.DoubleSide }), [0, -.22, 0]));
  const on = (geo, m, p, s, r) => govde.add(mesh(geo, m, p, s, r));
  if (tip === 'takim' || tip === 'ceket' || tip === 'yelek') { on(BOX, mat(ic, .6), [0, .38, .118], [.11, .2, .02]); if (kravat) on(BOX, mat(kravat, .5), [0, .33, .132], [.035, .2, .012]);
    for (const s of [-1, 1]) on(BOX, tip === 'yelek' ? mat(ust, .7) : U, [s * .07, .36, .125], [.05, .26, .02], [0, 0, s * .32]); }
  if (tip === 'gomlek') { for (const s of [-1, 1]) on(BOX, U, [s * .045, .5, .1], [.06, .03, .05], [0, 0, s * .5]); for (let i = 0; i < 4; i++) on(SP, mat(0xe8e8e8, .4), [0, .44 - i * .09, .127], [.007, .007, .004]); }
  if (tip === 'kapsonlu') { on(new THREE.TorusGeometry(.1, .04, 10, 20, Math.PI), U, [0, .5, -.05], null, [Math.PI * .35, 0, 0]); for (const s of [-1, 1]) on(CYL, mat(0xdddddd, .6), [s * .03, .4, .125], [.004, .14, .004]); }
  if (tip === 'hirka') { on(BOX, mat(ic, .7), [0, .33, .118], [.09, .34, .02]); for (let i = 0; i < 4; i++) on(SP, mat(0x2a2218, .5), [.055, .43 - i * .08, .128], [.009, .009, .005]); }
  if (tip === 'mont') { on(new THREE.TorusGeometry(.095, .035, 10, 20), U, [0, .5, 0], null, [Math.PI / 2, 0, 0]); on(BOX, mat(0x222222, .4, .6), [0, .3, .127], [.006, .38, .006]); }
  if (tip === 'kazak') on(new THREE.TorusGeometry(.085, .025, 10, 20), U, [0, .51, 0], null, [Math.PI / 2, 0, 0]);
  if (tip === 'onluk') on(BOX, mat(ic, .8), [0, .15, .125], [.26, .62, .02]);
  // kollar
  const kolYap = (s) => { const om = new THREE.Group(); om.position.set(s * .215, .45, 0); const dir = new THREE.Group(); dir.position.y = -.3;
    om.add(mesh(cap(.052, .22), kol, [0, -.14, 0])); dir.add(mesh(cap(.044, .2), kol, [0, -.12, 0])); const el = mesh(SP, ten, [0, -.28, .01], [.042, .052, .03]); dir.add(el);
    if (S.saat && s < 0) dir.add(mesh(CYL, mat(S.saat, .25, 1), [0, -.21, 0], [.048, .025, .048])); om.add(dir); govde.add(om); return [om, dir, el]; };
  const [oL, eL, elL] = kolYap(-1), [oR, eR, elR] = kolYap(1);
  // boyun + baş
  govde.add(mesh(CYL, ten, [0, .56, 0], [.052, .1, .052]));
  const bas = new THREE.Group(); bas.position.y = .7; govde.add(bas);
  bas.add(mesh(SP, ten, [0, 0, 0], [.094, .118, .104]));
  for (const s of [-1, 1]) bas.add(mesh(SP, ten, [s * .094, 0, -.005], [.014, .026, .02]));
  bas.add(mesh(cap(.012, .02), ten, [0, -.012, .1], null, [.25, 0, 0]));
  const gozler = [], kapak = [], kas = [];
  for (const s of [-1, 1]) { const gz = new THREE.Group(); gz.position.set(s * .035, .018, .083); bas.add(gz);
    gz.add(mesh(SP, mat(0xf4f1ea, .3), [0, 0, 0], [.017, .015, .01])); const ir = mesh(SP, mat(0x2a1a10, .2), [0, 0, .008], [.0085, .0085, .005]); gz.add(ir); gz.add(mesh(SP, mat(0x000000, .1), [0, 0, .0118], [.0045, .0045, .002])); gozler.push(ir);
    const kp = mesh(new THREE.SphereGeometry(1, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), ten, [s * .035, .018, .084], [.019, .017, .013], [-.4, 0, 0]); bas.add(kp); kapak.push(kp);
    const ks = mesh(BOX, mat(S.sacTip === 'basortu' ? 0x3a2a20 : S.sac, .9), [s * .036, .05, .095], [.034, .0065, .009]); bas.add(ks); kas.push(ks); }
  const agizG = new THREE.Group(); agizG.position.set(0, -.052, .094); bas.add(agizG);
  const ic_ = mesh(SP, mat(0x3a1414, .6), [0, 0, 0], [.02, .006, .006]); agizG.add(ic_);
  const dudak = mesh(new THREE.TorusGeometry(.021, .0038, 6, 16, Math.PI), mat(0xa8615a, .5), [0, .004, .003], [1, .35, 1], [0, 0, Math.PI]); agizG.add(dudak);
  // saç / sakal / gözlük
  const kabuk = (t0, t1, m, sc = [1.06, 1.05, 1.06], rot = [0, 0, 0], p = [0, 0, 0]) => bas.add(mesh(new THREE.SphereGeometry(1, 28, 16, 0, Math.PI * 2, t0, t1), m, p, [.094 * sc[0], .118 * sc[1], .104 * sc[2]], rot));
  if (S.sacTip === 'kisa') { kabuk(0, Math.PI * .44, sacM, [1.07, 1.07, 1.1], [-.35, 0, 0], [0, .006, -.004]); bas.add(mesh(SP, sacM, [0, .09, .045], [.08, .03, .05])); }
  if (S.sacTip === 'geri') kabuk(0, Math.PI * .42, sacM, [1.06, 1.06, 1.08], [-.5, 0, 0], [0, .004, -.006]);
  if (S.sacTip === 'kel') bas.add(mesh(new THREE.TorusGeometry(.085, .022, 8, 24, Math.PI * 1.3), sacM, [0, .01, -.01], [1.1, 1, 1.15], [Math.PI / 2, 0, Math.PI * -.15 + Math.PI]));
  if (S.sacTip === 'uzun') { kabuk(0, Math.PI * .5, sacM, [1.09, 1.08, 1.12], [-.3, 0, 0]); bas.add(mesh(cap(.09, .16), sacM, [0, -.1, -.06], [1.1, 1, .6])); }
  if (S.sacTip === 'basortu') { kabuk(0, Math.PI * .68, sacM, [1.16, 1.12, 1.16], [-.62, 0, 0], [0, -.004, -.012]); bas.add(mesh(new THREE.ConeGeometry(.17, .26, 20, 1, true), mat(S.sac, .8, 0, { side: THREE.DoubleSide }), [0, -.18, -.03])); }
  if (S.sakal === 'kirli') kabuk(Math.PI * .56, Math.PI * .4, mat(0x2a1e16, .9, 0, { transparent: true, opacity: .38 }), [1.012, 1.01, 1.012]);
  if (S.sakal === 'tam') { kabuk(Math.PI * .58, Math.PI * .4, mat(S.sakalRenk || S.sac, .95), [1.05, 1.06, 1.1]); agizG.position.z = .109; } // ağız sakalın önünde kalsın
  if (S.sakal === 'biyik' || S.sakal === 'tam') bas.add(mesh(BOX, mat(S.sakalRenk || S.sac, .9), [0, -.035, S.sakal === 'tam' ? .111 : .1], [.045, .012, .012]));
  if (S.gozluk) { const gm = mat(S.gozluk, .3, .5); for (const s of [-1, 1]) bas.add(mesh(new THREE.TorusGeometry(.021, .0025, 6, 20), gm, [s * .035, .018, .101])); bas.add(mesh(BOX, gm, [0, .02, .102], [.02, .003, .003])); }
  const telefon = mesh(BOX, mat(0x111114, .3, .4), [0, -.33, .03], [.035, .075, .009]); telefon.visible = false; eR.add(telefon);
  const IF = { notr: [0, 0, .15, 0], mutlu: [.004, .12, .55, 0], endise: [.006, -.35, -.2, 0], kizgin: [-.004, .35, -.35, 0], sasir: [.012, 0, 0, .55], uzgun: [.002, -.4, -.45, 0], ciddi: [-.002, .1, -.05, 0] };
  const KOL = { yan: [0, .1, -.12], masa: [-.75, .12, -.75], tel: [-.35, .5, -2.45], isaret: [-1.0, .18, -.5], kavus: [-.55, -.25, -1.9], uzat: [-1.15, .05, -.15], cep: [.12, .22, .35], kalem: [-.85, .05, -.95], yuz: [-.6, .3, -2.2], bel: [.1, .55, -1.4] };
  const ac = (v) => Array.isArray(v) ? v : (KOL[v] || KOL.yan);
  function poz(p) {
    const t = p.t || 0; g.position.set(p.x || 0, 0, p.z || 0); g.rotation.y = p.yaw || 0;
    let yr = 0; if (p.yuru != null) { const f = p.yuru; kL.rotation.x = Math.sin(f) * .45; kR.rotation.x = -Math.sin(f) * .45; dL.rotation.x = Math.max(0, -Math.sin(f + 1.2)) * .7; dR.rotation.x = Math.max(0, Math.sin(f + 1.2)) * .7; yr = Math.abs(Math.cos(f)) * .02; }
    else if (p.otur) { kL.rotation.x = kR.rotation.x = -1.52; dL.rotation.x = dR.rotation.x = 1.5; } else { kL.rotation.x = kR.rotation.x = dL.rotation.x = dR.rotation.x = 0; }
    kok.position.y = (p.otur ? -.43 : 0) + yr;
    govde.rotation.x = p.egil || 0; govde.scale.y = 1 + Math.sin(t * 1.6) * .006;
    const [lx, lz, le] = ac(p.kolL), [rx, rz, re] = ac(p.kolR), sal = p.yuru != null ? Math.sin(p.yuru) * .35 : 0, kc = p.konus ? Math.sin(t * 3.1) * .08 : 0;
    oL.rotation.set(lx - sal, 0, -lz); eL.rotation.x = le; oR.rotation.set(rx + sal + kc, 0, rz); eR.rotation.x = re + kc * .5;
    telefon.visible = p.kolR === 'tel';
    const [by, bp] = p.bas || [0, 0]; bas.rotation.set(bp + (p.konus ? Math.sin(t * 2.3) * .025 : 0), by + Math.sin(t * .7) * .02, 0);
    const [ky, kr, gul, acik] = IF[p.ifade || 'notr'];
    kas.forEach((m, i) => { m.position.y = .05 + ky + acik * .012; m.rotation.z = (i ? -1 : 1) * kr; });
    const a = Math.min(1, (p.agiz || 0) + acik * .4); ic_.scale.set(.02 - a * .004, .004 + a * .02, .006); dudak.rotation.z = gul >= 0 ? Math.PI : 0; dudak.scale.y = .2 + Math.abs(gul) * .6; dudak.position.y = gul >= 0 ? .004 : -.006;
    const kir = p.kirp != null ? p.kirp : ((t * .37 + (S.boy * 7)) % 1 < .045 ? 1 : 0); kapak.forEach(m => m.rotation.x = -.4 + kir * 1.15 + (p.ifade === 'uzgun' ? .35 : 0));
    gozler.forEach(m => m.position.x = (p.bak || 0) * .004);
  }
  return { g, poz, bas };
}
