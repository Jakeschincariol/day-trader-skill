import * as THREE from 'three';
import { clamp, lerp, sstep, eio, eout, tex } from './lib.js';
// Anchorage bölgesi haritası: çekim yeri (yaklaşık), JBER (yaklaşık alan), görüş hattı
const LAT0 = 61.25, LON0 = -149.75, KX = Math.cos(LAT0 * Math.PI / 180) * 111.32, KY = 110.57;
const P = (la, lo) => new THREE.Vector3((lo - LON0) * KX, (la - LAT0) * KY, .05);
export function mapScene(renderer) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x020812);
  const t = tex('/tex/anc_map.jpg'); t.anisotropy = 8;
  const W = .8 * KX, H = .4 * KY; const pl = new THREE.Mesh(new THREE.PlaneGeometry(W, H), new THREE.MeshBasicMaterial({ map: t })); pl.position.set((-149.75 - LON0) * KX, (61.25 - LAT0) * KY, 0); scene.add(pl);
  const cam = new THREE.PerspectiveCamera(45, 1080 / 1920, .1, 1000);
  const DT = P(61.2176, -149.8997), FS = P(61.2150, -149.80), SE = P(61.2617, -149.6625);
  const JB = [[61.235, -149.95], [61.30, -149.95], [61.33, -149.85], [61.33, -149.62], [61.29, -149.55], [61.245, -149.62], [61.228, -149.75]].map(([a, b]) => P(a, b));
  return { scene, cam, update(t, P_, O) {
    const u = eio(clamp(t / 7.8)); cam.position.set(1.3, lerp(-5.6, -5.2, u), lerp(49, 47, u)); cam.lookAt(1.3, .5, 0); cam.updateProjectionMatrix();
    Object.assign(P_, { bloom: [.6, .45, .6], exposure: 1, tone: 'none', vignette: .5, grain: .03, sat: 1.05, contrast: 1.05 });
    O.poly(JB, cam, '#ff6a5a', sstep(.6, 1.2, t) * .9, ['Joint Base Elmendorf-Richardson', 'askerî üs · yaklaşık alan']);
    O.pin(DT, cam, 'Anchorage', '', '#9fb3c8', sstep(.2, .5, t), 'b');
    O.pin(FS, cam, 'Çekim yeri', 'Doğu Anchorage · yaklaşık', '#ffd23f', sstep(1.4, 1.8, t));
    O.dash(FS, SE, cam, '#ffd23f', sstep(2.4, 2.7, t), eout(clamp((t - 2.4) / 1.4)), 'görüş hattı · tepelerde JBER arazisinden geçiyor (~6–10 km)');
    O.qmark(SE, cam, sstep(3.8, 4.2, t), t);
    O.note('Cismin konumu ve mesafesi kesin değildir.', 'Kaynak: Alaska News, Fox News', sstep(4.4, 4.8, t));
  } };
}
