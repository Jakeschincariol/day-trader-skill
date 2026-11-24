# VAYYMATİK0 — Gökdelenin İçindeki 660 Tonluk Dev Top

YouTube Shorts / TikTok · 45 sn · 1080×1920 · 30 fps · H.264 + AAC

## Çıktılar
| Dosya | İçerik |
|---|---|
| `VAYYMATIK0_DevTop.mp4` | Tamamlanmış video (seslendirme, müzik, efekt, kelime kelime altyazı) |
| `seslendirme.mp3` | Türkçe seslendirme, video zaman çizelgesine hizalı (−16 LUFS) |
| `altyazi.srt` / `altyazi_kelime.srt` | Cümle bazlı ve kelime bazlı senkron altyazı |

## Üretim hattı (`build.sh`)
- `render/city.js` — Taipei 101 modeli (8 modül, çentikli köşeler, kule), şehir, gökyüzü; dış sahneler
- `render/interior.js` — 660 tonluk küre (41 plaka dikişi), 92 halat, 8 hidrolik sönümleyici, tampon halkası
- `render/schematic.js` — 87–92. katlar, rüzgâr/salınım canlandırması, bölünmüş ekran karşılaştırma
- `render/main.js` — zaman çizelgesi, geçişler, son işlem ve 2B etiket katmanı; `render.cjs` kareleri üretir
- `voice/tts.py` — Piper `tr_TR-fahrettin-medium` (CC0); kelime zamanları sessizlik tespiti + izole kelime süreleriyle
- `audio/build_audio.py` — müzik ve efektler sıfırdan sentezlenir (telif yok); `subs/make_subs.py` — karaoke ASS + SRT

Model dosyası depoya eklenmedi (63 MB): `aaskinkk-cloud/okur` → `ses/tr_TR-fahrettin-medium.onnx(.json)` → `voice/models/`.

## Bilgi kontrolü (taipei-101.com.tw/en/observatory/feature/damper)
- ≈5,5 m çap; 41 katman 12,5 cm çelik plaka; 660 metrik ton ✔
- 92 çelik halat (Ø 8,9 cm, 42 m); 8 hidrolik viskoz sönümleyici; tampon halkası salınımı ~150 cm ile sınırlar ✔
- Amaç: şiddetli rüzgârda salınımı azaltmak (ayarlı kütle sönümleyici) ✔ — resmî sayfada yüzde değer yok; videoda sayısal azalma iddiası yok.
- "87.–92. katlar arası" bilgisi resmî sayfada geçmiyor (sayfa yalnızca 89. kat gözlem katını anar); metin kullanıcıdan alındığı gibi korundu.
- Rüzgâr ve bölünmüş ekran sahneleri temsilidir: salınım abartılıdır, karşılaştırma ölçekli değildir; bina sönümleyiciyle de sallanmaya devam eder.

## Lisanslar
three.js (MIT), Montserrat (SIL OFL), Piper fahrettin sesi (CC0). Müzik ve efektler bu projede üretilmiştir.
