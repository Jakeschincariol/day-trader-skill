// SIFIRDAN ZİRVEYE — render motoru (yatay ana bölüm + dikey Shorts). ?w=1920&ar=16:9&fps=24&bolum=bolum1&mod=ana|short1..6
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
const Q = new URLSearchParams(location.search), AR = Q.get('ar') || '16:9', DIK = AR === '9:16', LW = DIK ? 1080 : 1920, LH = DIK ? 1920 : 1080;
const W = +(Q.get('w') || LW), H = Math.round(W * LH / LW), FPS = +(Q.get('fps') || 24), SC = W / LW;
const fonts = [['900', 'Montserrat_900Black'], ['800', 'Montserrat_800ExtraBold'], ['700', 'Montserrat_700Bold'], ['600', 'Montserrat_600SemiBold']].map(([w, f]) => new FontFace('Mont', `url(/fonts/${f}.ttf)`, { weight: w }).load().then(ff => document.fonts.add(ff)));
await Promise.all(fonts);
const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true }); renderer.setPixelRatio(1); renderer.setSize(W, H); document.body.appendChild(renderer.domElement);
renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping;
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 })); composer.setPixelRatio(1); composer.setSize(W, H);
const rp = new RenderPass(new THREE.Scene(), new THREE.PerspectiveCamera()); composer.addPass(rp);
const bloom = new UnrealBloomPass(new THREE.Vector2(W, H), .4, .5, .85); composer.addPass(bloom); composer.addPass(new OutputPass());
const fin = new ShaderPass({ uniforms: { tDiffuse: { value: null }, tOverlay: { value: null }, uTime: { value: 0 }, uFade: { value: 0 }, uVig: { value: .45 }, uGrain: { value: .02 }, uSat: { value: 1 }, uCon: { value: 1 }, uTint: { value: new THREE.Vector3(1, 1, 1) }, uFlash: { value: new THREE.Vector4() }, uBlur: { value: 0 } },
  vertexShader: `varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`,
  fragmentShader: `uniform sampler2D tDiffuse,tOverlay; uniform float uTime,uFade,uVig,uGrain,uSat,uCon,uBlur; uniform vec3 uTint; uniform vec4 uFlash; varying vec2 vUv;
  float h(vec2 p){ return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453); }
  void main(){ vec3 col=texture2D(tDiffuse,vUv).rgb; if(uBlur>0.){ vec3 a=vec3(0.); for(int i=0;i<8;i++){ float an=float(i)*.785; a+=texture2D(tDiffuse,vUv+vec2(cos(an),sin(an))*uBlur*.004).rgb; } col=mix(col,a/8.,.85); }
    col*=uTint; float l=dot(col,vec3(.2126,.7152,.0722)); col=mix(vec3(l),col,uSat); col=(col-.5)*uCon+.5;
    vec2 q=vUv-.5; col*=1.-uVig*smoothstep(.3,.95,length(q*vec2(1.15,1.)));
    vec4 o=texture2D(tOverlay,vUv); col=mix(col,uFlash.rgb,uFlash.a); col*=1.-uFade; col=mix(col,o.rgb,o.a);
    col+=(h(vUv*vec2(1920.,1080.)+floor(uTime*24.)*.37)-.5)*uGrain; gl_FragColor=vec4(clamp(col,0.,1.),1.); }` });
composer.addPass(fin);
const oc = document.createElement('canvas'); oc.width = W; oc.height = H; const ctx = oc.getContext('2d'); const otex = new THREE.CanvasTexture(oc); otex.colorSpace = THREE.NoColorSpace; fin.uniforms.tOverlay.value = otex;
const BOL = Q.get('bolum') || 'bolum1', ep = await import(`./${BOL}.js`);
const E = await ep.kur(renderer, { DIK, LW, LH, mod: Q.get('mod') || 'ana', FPS });
window.renderFrame = (f) => {
  const t = f / FPS, P = { bloom: [.4, .5, .85], exposure: 1, vignette: .45, grain: .02, sat: 1.05, contrast: 1.04, tint: [1, 1, 1], fade: 0, flash: [1, 1, 1, 0], blur: 0 };
  ctx.setTransform(SC, 0, 0, SC, 0, 0); ctx.clearRect(0, 0, LW, LH);
  const { scene, cam } = E.update(t, P, ctx); rp.scene = scene; rp.camera = cam;
  [bloom.strength, bloom.radius, bloom.threshold] = P.bloom; renderer.toneMappingExposure = P.exposure;
  const u = fin.uniforms; u.uTime.value = t; u.uFade.value = P.fade; u.uVig.value = P.vignette; u.uGrain.value = P.grain; u.uSat.value = P.sat; u.uCon.value = P.contrast; u.uTint.value.set(...P.tint); u.uFlash.value.set(...P.flash); u.uBlur.value = P.blur;
  otex.needsUpdate = true; composer.render(); return renderer.domElement.toDataURL('image/jpeg', .93);
};
window.TOPLAM = E.sure; window.READY = true;
