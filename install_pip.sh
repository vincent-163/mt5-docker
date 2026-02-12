#!/bin/bash
# Install pip and Python packages inside Wine. Run during Docker build.
set -e
Xvfb :99 -screen 0 1024x768x24 -ac &
XVFB_PID=$!
sleep 1

wine64 "C:\\Python39\\python.exe" /tmp/get-pip.py 2>/dev/null
wine64 "C:\\Python39\\python.exe" -m pip install \
    MetaTrader5==5.0.4424 numpy==1.26.4 rpyc==6.0.2 pywin32==311 2>/dev/null

rm -f /tmp/get-pip.py
wineserver -k 2>/dev/null || true
sleep 2
kill $XVFB_PID 2>/dev/null || true
wait $XVFB_PID 2>/dev/null || true
echo "Python packages installed."
