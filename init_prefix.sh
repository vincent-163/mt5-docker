#!/bin/bash
# Initialize wine prefix. Run during Docker build.
set -e
Xvfb :99 -screen 0 1024x768x24 -ac &
XVFB_PID=$!
sleep 1
wine64 wineboot --init 2>&1 || true
sleep 5
wineserver -k 2>/dev/null || true
kill $XVFB_PID 2>/dev/null || true
wait $XVFB_PID 2>/dev/null || true
sleep 1
echo "Wine prefix initialized."
