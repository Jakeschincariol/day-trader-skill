---
name: vayymatik0-seslendirme-chatterbox
description: VAYYMATİK0 videolarının Türkçe seslendirmesini Chatterbox Multilingual (MIT, ücretsiz, yerel) ile doğal belgesel anlatıcısı tonunda üretirken kullan; Piper fahrettin'in yerine geçer (kullanıcı onayı 23 Kasım 2026).
---

# VAYYMATİK0 seslendirme (Chatterbox)

Piper (tr_TR-fahrettin-medium) artık kullanılmaz: robotik tını, yanlış vurgu. Onaylanan sistem: **Chatterbox Multilingual 0.1.7** (Resemble AI, MIT lisansı, ticari kullanım serbest), CPU'da yerel çalışır.

## Sabit ses
- Referans tını: `ref_ses.wav` (onaylı örnekten türetilmiş sentetik ses; gerçek kişi sesi klonlanmaz). İzinsiz gerçek kişi sesi kullanma.
- Ayarlar: exaggeration ≤ 0.5, cfg_weight 0.68, temperature 0.5. Her parça 5 denemeye kadar üretilir; Whisper-small transkripti metne ≥ 0.95 benzerse kabul, değilse en iyisi seçilir.
- İşleme: 70 Hz HPF, 260 Hz −2,5 dB, 3,6 kHz +2,5 dB, tiz uyarıcı (s/ş netliği), 7,5 kHz raf; iç duraklamalar ≤ 0,25 sn; baş/son Whisper kelime sınırından kesilir.

## Dosyalar
`ref_ses.wav`, `ses_uret.py`, `ses_miks.py` → byskybrisem/day-trader-skill deposu, `claude/gracious-hawking-i6dd9s` dalı, `vayymatik-ses/` klasörü. Oturumda yoksa:
`git fetch origin claude/gracious-hawking-i6dd9s && git checkout FETCH_HEAD -- vayymatik-ses`

## Kurulum (oturumda yoksa)
```
uv venv .venv-tts --python 3.12
uv pip install --python .venv-tts/bin/python torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv-tts/bin/python chatterbox-tts==0.1.7 --no-deps
uv pip install --python .venv-tts/bin/python "numpy<2" librosa==0.11.0 s3tokenizer transformers==5.2.0 diffusers==0.29.0 resemble-perth conformer==0.3.2 safetensors==0.5.3 pykakasi==2.3.0 pyloudnorm omegaconf soundfile
```
Model ağırlıkları Hugging Face'ten iner (ResembleAI/chatterbox, openai/whisper-small).

## Metin kuralları
- Sayıları yazıyla yaz ("On beş Haziran iki bin yirmi altı"); altyazıda rakam kalır (`cap` alanı).
- Yabancı adları okunuşuyla yaz (Sean Kirkpatrick → "Şon Kırkpatrik", UFO → "ufo").
- Gereksiz virgül koyma: Chatterbox virgülde uzun durur. Bilinçli gerilim duraklaması için "..." kullan.
- Uzun cümleyi iki parçaya böl (ikinci parça `t: 0`, `gap: 0.2–0.3`).

## Adımlar
1. `metin.json` yaz: `[{"seg","t","gap","say","cap","ex"}]` (t = sahneye göre hedef başlangıç, 0 = öncekinin ardından).
2. Üret: `.venv-tts/bin/python ses_uret.py metin.json parcalar/` (önbellekli; hatalı parçanın .json/.wav'ını silip yeniden çalıştır).
3. Miksle: `.venv-tts/bin/python ses_miks.py parcalar/ SURE muzik_stem.wav efekt_stem.wav audio/` → `segs.json` (kelime zamanları), `voice_track.wav` (−16 LUFS), `mix.wav` (−14 LUFS, −3,2 dBTP; müzik −27 LUFS + konuşmada %55 kısma). Müzik/efekt stem'leri konuşmaya göre önceden kısılmamış olmalı.
4. **ASLA zaman esnetme (time-stretch) yapma**: phase vocoder sesi yankılı/metalik yapar. Sığmazsa araları kısalt veya final sahnesini uzat.
5. Altyazı: `segs.json`'dan karaoke ASS + SRT.
6. Kodlama: `-c:a aac -aac_coder twoloop -b:a 256k` (varsayılan AAC kodlayıcı tepe taşması yapar).
7. Doğrula: Whisper transkripti, LUFS/tepe (≤ −1,5 dBTP), `ffmpeg -v error -i video.mp4 -f null -`, konuşma bitişinden sonra ≥ 1 sn pay. Sesi dinleyemediğini söyle, kullanıcıdan kontrol iste.
