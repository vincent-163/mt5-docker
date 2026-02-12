#!/bin/bash
# Install MT5 via official installer inside Wine. Run during Docker build.
# Requires WINE_PROXY_ADDRESS env var (host:port) if network needs proxy.
set -e
Xvfb :99 -screen 0 1024x768x24 -ac &
XVFB_PID=$!
sleep 1

# Set Wine IE proxy so the MT5 installer can download files
if [ -n "$WINE_PROXY_ADDRESS" ]; then
    echo "Setting Wine IE proxy: $WINE_PROXY_ADDRESS"
    wine64 reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" \
        /v ProxyEnable /t REG_DWORD /d 1 /f 2>/dev/null
    wine64 reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" \
        /v ProxyServer /t REG_SZ /d "http=$WINE_PROXY_ADDRESS;https=$WINE_PROXY_ADDRESS" /f 2>/dev/null
fi

wine64 /tmp/mt5setup.exe /auto 2>/dev/null &

# Wait for install to complete (drive_c grows to ~630MB)
for i in $(seq 1 300); do
    if [ -f "/root/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; then
        SIZE=$(du -sm "/root/.wine/drive_c/Program Files/MetaTrader 5" 2>/dev/null | cut -f1)
        if [ "$SIZE" -gt 500 ]; then
            echo "MT5 install complete (~${SIZE}MB) at ${i}s"
            break
        fi
    fi
    [ $((i % 30)) -eq 0 ] && echo "  ... ${i}s, waiting for MT5 install"
    sleep 1
done

# Verify installation
if [ ! -f "/root/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; then
    echo "ERROR: MT5 terminal64.exe not found after install!"
    ls -la "/root/.wine/drive_c/Program Files/" 2>/dev/null || echo "Program Files dir doesn't exist"
    exit 1
fi

sleep 10
rm -f /tmp/mt5setup.exe
wineserver -k 2>/dev/null || true
sleep 2
kill $XVFB_PID 2>/dev/null || true
wait $XVFB_PID 2>/dev/null || true
echo "MT5 installation done."
