#!/usr/bin/env bash
# Kareler + miks + altyazı -> MP4. Proje kökünden çalıştır: bash bolum1/kodla.sh [ana|kisa1..kisa6|hepsi]
set -euo pipefail; cd "$(dirname "$0")/.."; mkdir -p bolum1/cikti; HEDEF=${1:-hepsi}
DN="hqdn3d=1.5:1.5:2.5:2.5"   # sentetik film greni hafifçe temizlenir (görüntü aynı, dosya ~%40 küçük)
ana() { ffmpeg -y -v error -stats -framerate 24 -i bolum1/frames/ana/%05d.jpg -i bolum1/audio/ana_mix.wav \
  -vf "ass=bolum1/subs/ana.ass:fontsdir=fonts,format=yuv420p" -c:v libx264 -preset slow -crf 18 -profile:v high -level 4.1 \
  -c:a aac -aac_coder twoloop -b:a 256k -aac_pns 0 -aac_is 0 -aac_tns 0 -aac_ms 0 -ar 48000 -movflags +faststart -shortest bolum1/cikti/Sifirdan_Zirveye_Bolum1_CRF18.mp4; }
# (İsteğe bağlı) 100 MB altı kopya: bash bolum1/kodla.sh ana_github — varsayılan çıktı tam kalitedir (CRF 18, gren korunur)
ana_github() { local V="hqdn3d=2:1.5:3:3,ass=bolum1/subs/ana.ass:fontsdir=fonts,format=yuv420p" P=/tmp/x264_ana_github
  ffmpeg -y -v error -stats -framerate 24 -i bolum1/frames/ana/%05d.jpg -vf "$V" -c:v libx264 -preset slow -b:v 850k -pass 1 -passlogfile $P -an -f null /dev/null
  ffmpeg -y -v error -stats -framerate 24 -i bolum1/frames/ana/%05d.jpg -i bolum1/audio/ana_mix.wav -vf "$V" -c:v libx264 -preset slow -b:v 850k -maxrate 2.5M -bufsize 5M -pass 2 -passlogfile $P \
    -c:a aac -aac_coder twoloop -b:a 128k -ar 48000 -movflags +faststart -shortest bolum1/cikti/Sifirdan_Zirveye_Bolum1_github.mp4; }
# 500 MB altı tek dosya (sohbet aktarım sınırı 500 MiB): karelerden 2 geçişli 5000 kbps, ~470 MiB
ana_500() { local V="ass=bolum1/subs/ana.ass:fontsdir=fonts,format=yuv420p" P=/tmp/x264_ana_500
  ffmpeg -y -v error -stats -framerate 24 -i bolum1/frames/ana/%05d.jpg -vf "$V" -c:v libx264 -preset slow -b:v 5000k -profile:v high -level 4.1 -pass 1 -passlogfile $P -an -f null /dev/null
  ffmpeg -y -v error -stats -framerate 24 -i bolum1/frames/ana/%05d.jpg -i bolum1/audio/ana_mix.wav -vf "$V" -c:v libx264 -preset slow -b:v 5000k -maxrate 10M -bufsize 20M -profile:v high -level 4.1 -pass 2 -passlogfile $P \
    -c:a aac -aac_coder twoloop -b:a 256k -aac_pns 0 -aac_is 0 -aac_tns 0 -aac_ms 0 -ar 48000 -movflags +faststart -shortest bolum1/cikti/Sifirdan_Zirveye_Bolum1.mp4; }
kisa() { ffmpeg -y -v error -stats -framerate 30 -i bolum1/frames/kisa$1/%05d.jpg -i bolum1/audio/kisa$1_mix.wav \
  -vf "ass=bolum1/subs/kisa$1.ass:fontsdir=fonts,format=yuv420p" -c:v libx264 -preset slow -crf 18 -profile:v high -level 4.2 \
  -c:a aac -aac_coder twoloop -b:a 256k -aac_pns 0 -aac_is 0 -aac_tns 0 -aac_ms 0 -ar 48000 -movflags +faststart -shortest bolum1/cikti/Shorts_0$1.mp4; }
case "$HEDEF" in ana) ana ;; ana_500) ana_500 ;; ana_github) ana_github ;; kisa[1-6]) kisa "${HEDEF#kisa}" ;; hepsi) ana_500; for n in 1 2 3 4 5 6; do kisa $n; done ;; esac
