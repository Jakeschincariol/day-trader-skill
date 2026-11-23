#!/usr/bin/env bash
# VAYYMATİK0 — "Ahtapot UFO Gizemi" üretim hattı
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm install                         # three.js, world-atlas (Natural Earth 1:10m), Montserrat
python3 tex/make_map.py                                     # Anchorage bölge haritası dokusu
python3 voice/tts.py                                        # Piper tr_TR-fahrettin-medium + kelime zamanları
python3 audio/build_audio.py                                # özgün müzik + efekt + miks (-14 LUFS)
python3 subs/make_subs.py                                   # karaoke ASS + altyazi.srt + altyazi_kelime.srt
node render/render.cjs --w=1080 --workers=3 --to=1529 --out=frames   # 1530 kare (51 sn)
ffmpeg -y -framerate 30 -i frames/%05d.jpg -i audio/mix.wav \
  -vf "ass=subs/captions.ass:fontsdir=fonts" \
  -c:v libx264 -preset slow -crf 19 -maxrate 12M -bufsize 24M -profile:v high -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart -shortest VAYYMATIK0_Alaska_UFO.mp4
ffmpeg -y -i audio/voice_track.wav -c:a libmp3lame -b:a 192k -ar 48000 seslendirme.mp3
