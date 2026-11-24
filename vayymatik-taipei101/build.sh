#!/usr/bin/env bash
# VAYYMATİK0 — "Gökdelenin İçindeki 660 Tonluk Dev Top" üretim hattı
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm install                         # three.js + Montserrat
python3 voice/tts.py                                        # Piper tr_TR-fahrettin-medium + kelime zamanları (voice/segs.json)
python3 audio/build_audio.py                                # özgün müzik + efekt + miks (-14 LUFS)
python3 subs/make_subs.py                                   # karaoke ASS + altyazi.srt + altyazi_kelime.srt
node render/render.cjs --w=1080 --workers=3 --out=frames    # 1350 kare (headless Chromium + Three.js)
ffmpeg -y -framerate 30 -i frames/%05d.jpg -i audio/mix.wav \
  -vf "ass=subs/captions.ass:fontsdir=fonts" \
  -c:v libx264 -preset slow -crf 19 -maxrate 12M -bufsize 24M -profile:v high -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart -shortest VAYYMATIK0_DevTop.mp4
ffmpeg -y -i audio/voice_track.wav -c:a libmp3lame -b:a 192k -ar 48000 seslendirme.mp3
