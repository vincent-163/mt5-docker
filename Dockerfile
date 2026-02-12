FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Build-time proxy (pass with --build-arg http_proxy=http://172.17.0.1:8080)
# Docker automatically uses these for RUN commands
ARG http_proxy
ARG https_proxy
# Wine proxy address for MT5 installer (host:port, no http:// prefix)
ARG WINE_PROXY_ADDRESS

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    ca-certificates \
    curl \
    xz-utils \
    unzip \
    procps \
    libxrender1 \
    libxcursor1 \
    libxi6 \
    libxrandr2 \
    libxinerama1 \
    libxcomposite1 \
    libfontconfig1 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# Wine 10.0 standalone build (Kron4ek PE-only)
# Wine 11.x is BROKEN for MT5 (anti-debug check). Wine 10.0 works.
RUN curl -L -o /tmp/wine.tar.xz \
    "https://github.com/Kron4ek/Wine-Builds/releases/download/10.0/wine-10.0-amd64.tar.xz" \
    && tar xf /tmp/wine.tar.xz -C /opt/ \
    && rm /tmp/wine.tar.xz

ENV PATH="/opt/wine-10.0-amd64/bin:$PATH"
ENV WINEPREFIX="/root/.wine"
ENV WINEARCH=win64
ENV DISPLAY=:99
ENV WINEDEBUG=-all
ENV WINEDLLOVERRIDES="mscoree,mshtml="

# Initialize wine prefix
# /lib/ld-linux.so.2 error is expected (PE-only build, no 32-bit)
COPY init_prefix.sh /tmp/init_prefix.sh
RUN chmod +x /tmp/init_prefix.sh && /tmp/init_prefix.sh && rm /tmp/init_prefix.sh

# Install MT5 via official installer (needs proxy to download from MetaQuotes CDN)
RUN curl -L -o /tmp/mt5setup.exe "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
COPY install_mt5.sh /tmp/install_mt5.sh
RUN chmod +x /tmp/install_mt5.sh && WINE_PROXY_ADDRESS="$WINE_PROXY_ADDRESS" /tmp/install_mt5.sh && rm /tmp/install_mt5.sh

# Install Python 3.9 embeddable (no installer needed)
RUN curl -L -o /tmp/python.zip \
    "https://www.python.org/ftp/python/3.9.13/python-3.9.13-embed-amd64.zip" \
    && mkdir -p "/root/.wine/drive_c/Python39" \
    && unzip /tmp/python.zip -d "/root/.wine/drive_c/Python39/" \
    && rm /tmp/python.zip \
    && sed -i 's/^#import site/import site/' "/root/.wine/drive_c/Python39/python39._pth"

# Install pip and required packages
# Wine needs Xvfb even for CLI Python (loads GUI DLLs)
RUN curl -L -o /tmp/get-pip.py "https://bootstrap.pypa.io/get-pip.py"
COPY install_pip.sh /tmp/install_pip.sh
RUN chmod +x /tmp/install_pip.sh && /tmp/install_pip.sh && rm /tmp/install_pip.sh

# Write initial common.ini with algo trading enabled
# Also clear any build-time Wine IE proxy from the registry
RUN wine64 reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" \
        /v ProxyEnable /t REG_DWORD /d 0 /f 2>/dev/null; \
    wine64 reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" \
        /v ProxyServer /f 2>/dev/null; \
    wineserver -k 2>/dev/null; true
RUN printf '=\r\n\
[Common]\r\n\
ExpertEnabled=1\r\n\
ExpertAccount=1\r\n\
ExpertRealtime=1\r\n\
ExpertDllImport=1\r\n\
Login=0\r\n\
Server=\r\n\
ProxyEnable=0\r\n\
ProxyType=2\r\n\
ProxyAddress=\r\n\
ProxyAuth=\r\n\
CertInstall=0\r\n\
NewsEnable=0\r\n\
[Charts]\r\n\
ProfileLast=Default\r\n\
MaxBars=100000\r\n\
PrintColor=0\r\n\
SaveDeleted=0\r\n\
[Experts]\r\n\
AllowDllImport=1\r\n\
Enabled=1\r\n\
Account=1\r\n\
Profile=1\r\n' > "/root/.wine/drive_c/Program Files/MetaTrader 5/Config/common.ini"

# Warmup: start terminal once to trigger MQL5 recompilation (takes 2-3 min).
# Without this, the 60s IPC pipe timeout is always exceeded on first run.
COPY warmup.sh /tmp/warmup.sh
RUN chmod +x /tmp/warmup.sh && /tmp/warmup.sh && rm /tmp/warmup.sh

# Clean up after warmup
RUN rm -rf "/root/.wine/drive_c/Program Files/MetaTrader 5/Logs" \
           "/root/.wine/drive_c/Program Files/MetaTrader 5/logs" \
    && find /root/.wine/drive_c/users -name 'portable.txt' -path '*/MetaQuotes/Terminal/*' -delete 2>/dev/null || true

# Unset proxy so it doesn't leak into runtime
ENV http_proxy=""
ENV https_proxy=""

COPY rpyc_server.py /root/rpyc_server.py
COPY mt5_server.py /root/mt5_server.py
COPY entrypoint.sh /root/entrypoint.sh
RUN chmod +x /root/entrypoint.sh

EXPOSE 18812

ENTRYPOINT ["/root/entrypoint.sh"]
