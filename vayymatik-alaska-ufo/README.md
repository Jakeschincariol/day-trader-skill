# VAYYMATİK0 — Ahtapot UFO Gizemi

YouTube Shorts / TikTok · 51 sn · 1080×1920 · 30 fps · H.264 + AAC

## Çıktılar
| Dosya | İçerik |
|---|---|
| `VAYYMATIK0_Alaska_UFO.mp4` | Tamamlanmış video (seslendirme, müzik, efekt, kelime kelime altyazı) |
| `seslendirme.mp3` | Türkçe seslendirme, video zaman çizelgesine hizalı (−16 LUFS) |
| `altyazi.srt` / `altyazi_kelime.srt` | Cümle bazlı ve kelime bazlı senkron altyazı |

## Üretim hattı (`build.sh`)
- `render/sky.js` — bulutlu gökyüzü (fiziksel 42° gökkuşağı), Chugach dağları, Anchorage, gizemli cisim, ahtapot uçurtma
- `render/map.js` + `tex/make_map.py` — Natural Earth 1:10m kıyı verisinden Anchorage haritası; çekim yeri, JBER ve görüş hattı (yaklaşık)
- `render/main.js` — zaman çizelgesi, geçişler, son işlem, 2B etiketler; `render.cjs` kareleri headless Chromium ile üretir
- `voice/tts.py` — Piper `tr_TR-fahrettin-medium` (CC0); `audio/build_audio.py` — sentezlenmiş müzik/efekt; `subs/make_subs.py` — karaoke ASS + SRT

## Bilgi kontrolü
- Alaska News: video 15 Haziran'da Doğu Anchorage'da (eski Northway Mall yakını) çekildi; çeken kişi gökkuşağını fotoğraflarken cismi fark ettiğini söyledi. Görüş hattı tepelerde JBER arazisinden geçiyor (~4–6 mil). 3 Kasım'da Instagram'da yeniden paylaşılınca viral oldu.
- Fox News: Sean Kirkpatrick (AARO'nun eski direktörü) hareketin "şeritli bir uçurtmaya" benzediğini söyledi; JBER "ek bilgi yok" dedi. Kesin tanımlama yapılmadı.
- teyit.org sayfası otomatik erişime 403 döndürdü; videoda uçuş yasağı iddiasına hiç yer verilmedi.
- Orijinal video (Peter & Sara Jane Osborn / Storyful) için yeniden kullanım izni bulunamadı; videoda kullanılmadı, tüm görüntüler özgün canlandırmadır ve "TEMSİLİ CANLANDIRMA" olarak işaretlidir.
- Not: Kirkpatrick'in sözü "şeritli/flamalı uçurtma"dır; "ahtapot şeklinde uçurtma" metindeki örnektir.

## Lisanslar
three.js (MIT), world-atlas / Natural Earth (kamu malı), Montserrat (SIL OFL), Piper fahrettin sesi (CC0). Müzik ve efektler bu projede üretilmiştir.
