#!/bin/bash
# Warmup: start MT5 terminal once during Docker build to trigger MQL5 recompilation.
# The terminal compiles 131+ MQL5 files on first run, taking 2+ minutes —
# far exceeding the 60-second IPC pipe timeout. Pre-warming ensures
# the pipe is created quickly on subsequent runs.
set -e

MT5_DIR="/root/.wine/drive_c/Program Files/MetaTrader 5"

# Start Xvfb
Xvfb :99 -screen 0 1024x768x24 -ac &
XVFB_PID=$!
sleep 1

echo "=== Warmup: starting MT5 terminal for MQL5 pre-compilation ==="

# Start terminal (suppress explorer.exe spam)
wine64 "$MT5_DIR/terminal64.exe" 2>/dev/null &
MT5_PID=$!

# Wait for MQL5 compilation to finish (up to 240s)
WAIT_SECS=240
echo "Waiting up to ${WAIT_SECS}s for terminal initialization..."

for i in $(seq 1 $WAIT_SECS); do
    if ! kill -0 $MT5_PID 2>/dev/null; then
        echo "Terminal exited early at ${i}s"
        break
    fi
    if [ $((i % 30)) -eq 0 ]; then
        echo "  ... ${i}s elapsed, terminal still running"
        RECENT=$(find "$MT5_DIR/MQL5" -name "*.ex5" -mmin -1 2>/dev/null | wc -l)
        echo "  ... recently compiled .ex5 files: $RECENT"
    fi
    sleep 1
done

echo "=== Warmup complete, killing terminal ==="

kill $MT5_PID 2>/dev/null || true
sleep 2
pkill -9 -f terminal64 2>/dev/null || true
pkill -9 -f explorer.exe 2>/dev/null || true
pkill -9 -f wineserver 2>/dev/null || true
pkill -9 -f winedevice 2>/dev/null || true
sleep 2
kill $XVFB_PID 2>/dev/null || true

EX5_COUNT=$(find "$MT5_DIR/MQL5" -name "*.ex5" 2>/dev/null | wc -l)
echo "Warmup done. .ex5 files in prefix: $EX5_COUNT"
