#!/usr/bin/env bash
# Kareler + miks + altyazı -> MP4. Proje kökünden çalıştır: bash bolum1/kodla.sh [ana|kisa1..kisa6|hepsi]
set -euo pipefail; cd "$(dirname "$0")/.."; mkdir -p bolum1/cikti; HEDEF=${1:-hepsi}
ana() { ffmpeg -y -v error -stats -framerate 24 -i bolum1/frames/ana/%05d.jpg -i bolum1/audio/ana_mix.wav \
  -vf "ass=bolum1/subs/ana.ass:fontsdir=fonts,format=yuv420p" -c:v libx264 -preset slow -crf 20 -maxrate 10M -bufsize 20M -profile:v high -level 4.1 \
  -c:a aac -aac_coder twoloop -b:a 256k -ar 48000 -movflags +faststart -shortest bolum1/cikti/Sifirdan_Zirveye_Bolum1.mp4; }
kisa() { ffmpeg -y -v error -stats -framerate 30 -i bolum1/frames/kisa$1/%05d.jpg -i bolum1/audio/kisa$1_mix.wav \
  -vf "ass=bolum1/subs/kisa$1.ass:fontsdir=fonts,format=yuv420p" -c:v libx264 -preset slow -crf 19 -maxrate 12M -bufsize 24M -profile:v high -level 4.2 \
  -c:a aac -aac_coder twoloop -b:a 256k -ar 48000 -movflags +faststart -shortest bolum1/cikti/Shorts_0$1.mp4; }
case "$HEDEF" in ana) ana ;; kisa[1-6]) kisa "${HEDEF#kisa}" ;; hepsi) ana; for n in 1 2 3 4 5 6; do kisa $n; done ;; esac
