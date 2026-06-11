#!/usr/bin/env bash
# Install Cocos Creator for Linux CLI builds (requires Xvfb).
# Usage: bash ops/scripts/install-cocos-creator-linux.sh [install_dir]
set -euo pipefail

INSTALL_DIR="${1:-/opt/CocosCreator}"
VERSION="${COCOS_CREATOR_VERSION:-3.8.3}"
ARCHIVE="CocosCreator-v${VERSION}-linux-x86_64.tar.xz"
URL="https://download.cocos.com/CocosCreator/v${VERSION}/${ARCHIVE}"

echo "==> Installing dependencies (xvfb)"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y xvfb libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 xdg-utils libatspi2.0-0 libdrm2 libgbm1
fi

mkdir -p "$(dirname "$INSTALL_DIR")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Downloading ${URL}"
if ! curl -fL "$URL" -o "$TMP/$ARCHIVE"; then
  echo "Download failed. Install Cocos Creator manually and set GAMECENTER_COCOS_CREATOR_BIN." >&2
  exit 1
fi

echo "==> Extracting to ${INSTALL_DIR}"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
tar -xJf "$TMP/$ARCHIVE" -C "$INSTALL_DIR" --strip-components=1 2>/dev/null || tar -xJf "$TMP/$ARCHIVE" -C "$INSTALL_DIR"

BIN=""
for candidate in \
  "$INSTALL_DIR/CocosCreator" \
  "$INSTALL_DIR/CocosCreator/CocosCreator" \
  "$INSTALL_DIR/CocosCreator/CocosCreator/CocosCreator"; do
  if [[ -f "$candidate" ]]; then
    BIN="$candidate"
    break
  fi
done

if [[ -z "$BIN" ]]; then
  BIN="$(find "$INSTALL_DIR" -maxdepth 4 -type f -name CocosCreator | head -1 || true)"
fi

if [[ -z "$BIN" ]]; then
  echo "CocosCreator binary not found under ${INSTALL_DIR}" >&2
  exit 1
fi

chmod +x "$BIN"
echo "==> Installed: $BIN"
echo "Add to mchat .env:"
echo "GAMECENTER_COCOS_CREATOR_BIN=$BIN"
