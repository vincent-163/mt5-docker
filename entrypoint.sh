#!/bin/bash
# Entrypoint: starts Xvfb, configures MT5, starts rpyc server.
set -e

PYTHON="C:\\Python39\\python.exe"
MT5_DIR="/root/.wine/drive_c/Program Files/MetaTrader 5"
INI="$MT5_DIR/Config/common.ini"
APPDATA_BASE="/root/.wine/drive_c/users/root/AppData/Roaming/MetaQuotes/Terminal"
export WINEDLLOVERRIDES="mscoree,mshtml="

# Find the AppData terminal hash directory dynamically
find_appdata_ini() {
    local ini=""
    if [ -d "$APPDATA_BASE" ]; then
        ini=$(find "$APPDATA_BASE" -maxdepth 2 -name "common.ini" -path "*/config/*" 2>/dev/null | head -1)
    fi
    echo "$ini"
}

# Update a config file with sed
update_ini() {
    local cfg="$1"
    [ -f "$cfg" ] || return 0

    if [ -n "$MT5_PROXY_ADDRESS" ]; then
        sed -i "s/^ProxyEnable=.*/ProxyEnable=1/" "$cfg"
        sed -i "s/^ProxyType=.*/ProxyType=2/" "$cfg"
        sed -i "s|^ProxyAddress=.*|ProxyAddress=$MT5_PROXY_ADDRESS|" "$cfg"
    fi

    if [ -n "$MT5_LOGIN" ]; then
        sed -i "s/^Login=.*/Login=$MT5_LOGIN/" "$cfg"
    fi
    if [ -n "$MT5_SERVER" ]; then
        sed -i "s/^Server=.*/Server=$MT5_SERVER/" "$cfg"
    fi

    # Ensure algo trading is enabled
    sed -i '/^\[Experts\]/,/^\[/{s/^Enabled=0/Enabled=1/}' "$cfg"
}

# 1. Start Xvfb
XVFB_DISPLAY="${XVFB_DISPLAY:-:99}"
export DISPLAY="$XVFB_DISPLAY"
Xvfb "$XVFB_DISPLAY" -screen 0 1024x768x24 -ac &
XVFB_PID=$!
sleep 1
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "ERROR: Xvfb failed to start"
    exit 1
fi
echo "Xvfb started (PID $XVFB_PID)"

# 2. Configure proxy in Wine registry (for MT5 installer/updater)
if [ -n "$MT5_PROXY_ADDRESS" ]; then
    echo "Configuring IE proxy: $MT5_PROXY_ADDRESS"
    wine64 reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" \
        /v ProxyEnable /t REG_DWORD /d 1 /f 2>/dev/null
    wine64 reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" \
        /v ProxyServer /t REG_SZ /d "http=$MT5_PROXY_ADDRESS;https=$MT5_PROXY_ADDRESS" /f 2>/dev/null
fi

# 3. Configure credentials in common.ini (both install dir and AppData)
echo "Configuring: Login=${MT5_LOGIN:-0} Server=${MT5_SERVER:-}"
update_ini "$INI"

APPDATA_INI=$(find_appdata_ini)
if [ -n "$APPDATA_INI" ]; then
    echo "Found AppData config: $APPDATA_INI"
    update_ini "$APPDATA_INI"
    # Delete accounts.dat to prevent "account changed" detection
    APPDATA_DIR=$(dirname "$APPDATA_INI")
    rm -f "$APPDATA_DIR/accounts.dat"
fi
rm -f "$MT5_DIR/Config/accounts.dat"

# 4. Pre-warm Wine desktop
echo "Pre-warming Wine desktop..."
wine64 explorer /desktop 2>/dev/null &
sleep 3
if pgrep -f 'explorer.exe' >/dev/null 2>&1; then
    echo "Wine desktop ready"
else
    echo "WARNING: explorer.exe not running, terminal may fail to start"
fi

# 5. Explorer.exe reaper (MT5 on Wine 10 spawns hundreds of explorer.exe)
(
    while true; do
        sleep 10
        PIDS=$(pgrep -f 'explorer.exe' 2>/dev/null | sort -n)
        COUNT=$(echo "$PIDS" | wc -w)
        if [ "$COUNT" -gt 2 ]; then
            KEEP=$(echo "$PIDS" | head -1)
            for PID in $PIDS; do
                [ "$PID" != "$KEEP" ] && kill -9 "$PID" 2>/dev/null || true
            done
        fi
    done
) &
echo "Explorer reaper started"

# 6. Pre-launch MT5 terminal if credentials are configured
if [ -n "$MT5_LOGIN" ]; then
    echo "Pre-launching MT5 terminal..."
    wine64 "$MT5_DIR/terminal64.exe" 2>/dev/null &
    MT5_PID=$!

    # Wait for terminal to start (up to 120s)
    echo "Waiting for terminal to initialize..."
    for i in $(seq 1 120); do
        if ! kill -0 $MT5_PID 2>/dev/null; then
            echo "WARNING: Terminal exited at ${i}s"
            break
        fi
        [ $((i % 15)) -eq 0 ] && echo "  ... ${i}s, waiting"
        sleep 1
    done
    echo "Terminal pre-launch wait complete"
fi

# 7. Start rpyc server (foreground)
echo "Starting rpyc server..."
wine64 "$PYTHON" "Z:\\root\\rpyc_server.py" 2>/dev/null &
RPYC_PID=$!

wait $RPYC_PID
