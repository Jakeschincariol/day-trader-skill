# VAYYMATİK0 — SIFIRDAN ZİRVEYE (kurgusal finans dizisi)

Her bölüm: 12–15 dk yatay ana video (1920×1080, 24 fps) + 6 dikey Shorts (1080×1920, 30 fps, 30–55 sn).
Hikâye ve kişiler **kurgusaldır**; ekranda kurgu notu gösterilir. Bütün rakamlar tek bir finans veri dosyasından gelir.

## Klasör yapısı

| Yol | İçerik | Yeniden kullanım |
|---|---|---|
| `render/karakter.js` | Stilize 3D karakterler (Emir'in 3 dönem kıyafeti, Kenan Bey, Hasan Usta, baba, anne, Kerem, Murat Aydın, Ahmet Bey, müşteriler, usta) — `insan(ad, donem)`, poz/ifade/ağız animasyonu | Tüm bölümler |
| `render/setler.js` | Setler: kuyumcu (gündüz/akşam/gece/gün batımı, yağmur, kepenk, tabela), çarşı sokağı, ev, muhasebe ofisi, HUD arka planı | Tüm bölümler |
| `render/hud.js` | Yarı saydam finans HUD'u: 7 satırlı panel (kasa, ciro, SMM, giderler, net kâr/zarar, toplam borç, özkaynak), liste, şelale grafiği, çizgi grafik, rozet | Tüm bölümler |
| `render/main.js`, `render/render.cjs` | Three.js motoru + paralel headless Chromium kare kare render (`?bolum=bolumN&mod=ana|kisaN`) | Tüm bölümler |
| `render/bolum1.js` | Bölüm 1 çekim listesi (kamera, oyuncu, dikey `kd` kameraları), HUD zamanlaması, Shorts kanca/kapanış katmanı | Bölüm 2 için kopyalanıp değiştirilir |
| `ortak/ses_uret.py` | Kalıcı VAYYMATİK0 sesi: Chatterbox Multilingual (MIT) + Whisper doğrulama, hızlandırma YOK | Tüm bölümler |
| `ortak/ses_tasarim.py` | Kodla üretilen telifsiz müzik (9 ruh hâli) + efektler (yağmur, kapı zili, yazar kasa, telefon, saat, kalem, kepenk…) + limiter | Tüm bölümler |
| `bolum1/finans.py` → `finans.json` | Bölümün **finans veri dosyası** (tek kaynak) + 59 otomatik muhasebe kontrolü | Şablon |
| `bolum1/senaryo.txt` | Senaryo: `sahne|konuşan|metin {altyazı|okunuş}|çekim|panel|ara` | — |
| `bolum1/kisa/kisaN.txt` | Shorts senaryoları (`@baslik`, `@kanca`, `@son`); ana bölümle aynı satırlar aynı ses kaydını kullanır | — |
| `bolum1/kontrol.py` | Tutarlılık: rakam ↔ okunuş, ekrandaki her TL rakamı finans.json'da, çekim/panel kodları tanımlı, Shorts süresi/kancası | Şablon |
| `bolum1/shorts_metadata.md` | YouTube Shorts + TikTok başlık, açıklama, etiketler | — |
| `bolum1/cikti/` | Bitmiş MP4'ler | — |

## Muhasebe kuralları (tüm bölümlerde)
- Borç almak gelir değildir; anapara ödemek gider değildir — finansman / nakit hareketidir (faiz ve gecikme cezası giderdir).
- Emanet ürün işletmenin stoğu değildir; satılınca bedeli (1 ay vadeyle) tedarikçiye ödenir → "kasa ≠ kullanılabilir para".
- Kasa, ciro, kâr ve servet ayrı gösterilir; ciro kazanç olarak anlatılmaz.
- Kimlik: özkaynak = kasa + duran varlıklar − borç = açılış özkaynağı + dönem net kârı (finans.py her ara durum için kontrol eder).

## Üretim hattı (proje kökünden)
```bash
VP=../vayymatik-alaska-ufo/.venv-tts/bin/python          # Chatterbox + Whisper ortamı
python3 bolum1/finans.py                                   # finans.json + kontroller
$VP bolum1/hazirla_ses.py && $VP bolum1/kisa_hazirla.py    # vuruşlar + TTS parça listeleri (önbellek sırası korunur)
$VP ortak/ses_uret.py bolum1/ses/parcalar.json bolum1/ses/parca
$VP ortak/ses_uret.py bolum1/ses/kisa_parcalar.json bolum1/ses/kisa_parca
$VP bolum1/zaman.py && $VP bolum1/zaman.py --kisa          # zaman çizelgeleri (timeline.json, kisaN.json)
python3 bolum1/kontrol.py                                  # tutarlılık kontrolleri
$VP bolum1/miks.py && $VP bolum1/miks.py --kisa            # ses + müzik + efekt miksleri (-14 LUFS)
$VP bolum1/altyazi.py                                      # SRT + ASS altyazılar
node render/render.cjs --ar=16:9 --fps=24 --workers=4 --to=<kare-1> --out=bolum1/frames/ana
node render/render.cjs --ar=9:16 --fps=30 --mod=kisa1 --workers=4 --to=<kare-1> --out=bolum1/frames/kisa1   # … kisa6
bash bolum1/kodla.sh hepsi && python3 bolum1/dogrula.py    # MP4 + doğrulama
```

## Bölüm 2'ye genişletme
1. `bolum1/` klasörünü `bolum2/` olarak kopyalayın; `finans.py`'de açılış değerlerini Bölüm 1'in yıl sonu durumundan başlatın (kasa 128.000, borç 490.000: satıcı 250.000 · Kerem 160.000 · aile 80.000, özkaynak 530.000, belirsiz talep 240.000).
2. `render/bolum1.js` → `render/bolum2.js`; JSON yollarını `bolum2`ye çevirin, yeni çekimleri `S` tablosuna ekleyin. Karakterler, setler, HUD, ses ve müzik modülleri değişmeden kullanılır.
3. Render: `node render/render.cjs --bolum=bolum2 ...` (motor `render/bolum2.js` modülünü ve `bolum2/*.json` dosyalarını yükler).
