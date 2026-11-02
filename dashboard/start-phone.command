#!/bin/sh
cd "$(dirname "$0")"
echo "Starting TraderDash with iPhone access..."
(sleep 2; open http://127.0.0.1:8212) &
python3 server.py --phone
