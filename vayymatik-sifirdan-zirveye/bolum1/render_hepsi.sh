#!/usr/bin/env bash
# Tüm kareleri sırayla render eder (kaldığı yerden devam eder): ana bölüm 1920x1080@24, Shorts 1080x1920@30. Proje kökünden: bash bolum1/render_hepsi.sh [isçi]
set -euo pipefail; cd "$(dirname "$0")/.."; W=${1:-4}
kare() { python3 -c "import json,math; print(math.ceil(json.load(open('$1'))['sure']*$2)-1)"; }
node render/render.cjs --ar=16:9 --fps=24 --workers=$W --to=$(kare bolum1/timeline.json 24) --out=bolum1/frames/ana
for n in 1 2 3 4 5 6; do node render/render.cjs --ar=9:16 --fps=30 --mod=kisa$n --workers=$W --to=$(kare bolum1/kisa$n.json 30) --out=bolum1/frames/kisa$n; done
echo RENDER_BITTI
