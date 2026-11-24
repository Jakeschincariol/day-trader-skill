# VAYYMATİK0 — İnternet Aslında Denizin Altından Geçiyor!

YouTube Shorts / TikTok · 45 sn · 1080×1920 · 30 fps · H.264 + AAC

## Çıktılar
| Dosya | İçerik |
|---|---|
| `VAYYMATIK0_Internet.mp4` | Tamamlanmış video (seslendirme + müzik + efekt + yakılmış altyazı) |
| `seslendirme.mp3` | Türkçe seslendirme, video zaman çizelgesine hizalı (−16 LUFS, 192 kbps) |
| `altyazi.srt` | Seslendirmeyle senkronize altyazı |

## Üretim hattı (`build.sh`)
- `tex/make_textures.py` — Natural Earth kara verisinden (world-atlas) Dünya, bulut, stilize harita ve deniz tabanı dokuları
- `render/` — Three.js sahneleri (`space.js`, `water.js`, `graphic.js`), son işlem (bloom, renk, geçişler) ve 2B etiket katmanı (`main.js`); `render.cjs` kareleri headless Chromium ile üretir
- `voice/tts.py` — Piper `tr_TR-fahrettin-medium` (CC0) ile cümle cümle seslendirme; metin: `voice/metin.json`
- `audio/build_audio.py` — müzik ve efektler sıfırdan sentezlenir (telif yok), ducking, −14 LUFS / −1.5 dBTP mastering
- `subs/make_subs.py` — SRT ve anahtar kelime vurgulu ASS altyazı

Model dosyası depoya eklenmedi (63 MB): `aaskinkk-cloud/okur` deposundaki `ses/tr_TR-fahrettin-medium.onnx(.json)` → `voice/models/`.

## Bilimsel kontrol
- Deniz altı kabloları uluslararası veri trafiğinin %99'undan fazlasını taşır — ITU (Digital Resilience: Submarine cables). Videoda istatistik "uluslararası veri trafiği" olarak verilir, "internetin tamamı" denmez.
- Derin sularda kablo kalınlığı ≈ bahçe hortumu; yılda ≈200 arıza, ⅔'ü balıkçılık ve çapa kaynaklı — TeleGeography Submarine Cable FAQ (ICPC verisi).
- Işığın cam lifteki hızı ≈ c / 1,47 ≈ 200.000 km/sn.
- Kablo güzergâhları ve arıza/onarım sahneleri şematik/temsilidir; ekranda "Temsili" olarak işaretlenmiştir.

## Lisanslar
three.js (MIT), world-atlas / Natural Earth (kamu malı), Montserrat (SIL OFL), Piper fahrettin sesi (CC0). Müzik ve efektler bu projede üretilmiştir.
