#!/bin/bash
set -e

BASE_URL="${BASE_URL:-https://catlogs.wassim.tech}"

if [ "$(id -u)" -ne 0 ]; then
    echo "This installer needs root privileges. Re-running with sudo..."
    exec sudo bash "$0" "$@"
fi

echo "Installing CatLogs..."

mkdir -p /usr/local/bin
mkdir -p /usr/share/icons/hicolor/256x256/apps
mkdir -p /usr/share/applications

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$SCRIPT_DIR/catlogs" ]; then
    cp "$SCRIPT_DIR/catlogs" /usr/local/bin/catlogs
else
    echo "Downloading binary..."
    curl -sSL "$BASE_URL/catlogs" -o /usr/local/bin/catlogs
fi
chmod +x /usr/local/bin/catlogs

if [ -f "$SCRIPT_DIR/icon.png" ]; then
    cp "$SCRIPT_DIR/icon.png" /usr/share/icons/hicolor/256x256/apps/catlogs.png
else
    echo "Downloading icon..."
    curl -sSL "$BASE_URL/icon.png" -o /usr/share/icons/hicolor/256x256/apps/catlogs.png
fi

echo "Creating desktop entry..."
cat > /usr/share/applications/catlogs.desktop << DESKTOP_EOF
[Desktop Entry]
Name=CatLogs
Comment=System Logs
Exec=/usr/local/bin/catlogs
Icon=catlogs
Terminal=false
Type=Application
Categories=System;Monitor;Utility;
StartupWMClass=catlogs
DESKTOP_EOF

echo "CatLogs installed successfully!"
echo "You can find CatLogs in your application menu."
