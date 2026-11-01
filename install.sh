#!/usr/bin/env bash
# Installs Pengufy for the current user (no root needed).
# Qt and requests come from your distro; the spotifyd sound engine is downloaded from its GitHub release.
set -euo pipefail
cd "$(dirname "$0")"

APP_ID="io.github.htulu07.Pengufy"
PREFIX="${PREFIX:-$HOME/.local}"
LIB="$PREFIX/lib/pengufy"
SPOTIFYD_VERSION="v0.4.2"

distro_hint() {
    local ids=""
    [[ -r /etc/os-release ]] && ids="$(. /etc/os-release; echo "${ID:-} ${ID_LIKE:-}")"
    case " $ids " in
        *" fedora "*|*" rhel "*)   echo "sudo dnf install python3-pyqt6 python3-requests" ;;
        *" debian "*|*" ubuntu "*) echo "sudo apt install python3-pyqt6 python3-pyqt6.qtsvg python3-requests" ;;
        *" arch "*)                echo "sudo pacman -S python-pyqt6 python-requests" ;;
        *" suse "*|*" opensuse "*) echo "sudo zypper install python3-PyQt6 python3-requests" ;;
        *)                         echo "install PyQt6 and python requests with your package manager" ;;
    esac
}

if ! python3 -c "import requests, PyQt6.QtSvg, PyQt6.QtNetwork" 2>/dev/null; then
    echo "Pengufy needs PyQt6 and requests. Install them with:"
    echo "  $(distro_hint)"
    exit 1
fi

case "$(uname -m)" in
    x86_64)  ARCH=x86_64 ;;
    aarch64) ARCH=aarch64 ;;
    armv7l)  ARCH=armv7 ;;
    *) echo "No spotifyd build for $(uname -m)."; exit 1 ;;
esac

mkdir -p "$LIB/bin"
if [[ "$("$LIB/bin/spotifyd" --version 2>/dev/null)" != "spotifyd ${SPOTIFYD_VERSION#v}" ]]; then
    echo "Downloading the spotifyd sound engine ($SPOTIFYD_VERSION, about 8 MB)..."
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    base="https://github.com/Spotifyd/spotifyd/releases/download/$SPOTIFYD_VERSION/spotifyd-linux-$ARCH-full"
    curl -fsSL -o "$tmp/spotifyd.tar.gz" "$base.tar.gz"
    curl -fsSL -o "$tmp/spotifyd.sha512" "$base.sha512"
    (cd "$tmp" && echo "$(cut -d' ' -f1 spotifyd.sha512)  spotifyd.tar.gz" | sha512sum -c --quiet)
    tar xzf "$tmp/spotifyd.tar.gz" -C "$tmp" spotifyd
    install -m755 "$tmp/spotifyd" "$LIB/bin/spotifyd"
fi

rm -rf "$LIB/pengufy"
cp -r pengufy "$LIB/pengufy"
find "$LIB/pengufy" -name __pycache__ -prune -exec rm -rf {} +
install -Dm644 "data/$APP_ID.svg" "$LIB/pengufy/$APP_ID.svg"

mkdir -p "$PREFIX/bin"
printf '#!/bin/sh\nPYTHONPATH="%s" exec python3 -m pengufy "$@"\n' "$LIB" > "$PREFIX/bin/pengufy"
chmod 755 "$PREFIX/bin/pengufy"
install -Dm644 "data/$APP_ID.svg" "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg"
# Absolute path: the desktop session's PATH often lacks ~/.local/bin.
sed "s|^Exec=pengufy|Exec=$PREFIX/bin/pengufy|" "data/$APP_ID.desktop" > "$APP_ID.desktop.tmp"
install -Dm644 "$APP_ID.desktop.tmp" "$PREFIX/share/applications/$APP_ID.desktop"
rm -f "$APP_ID.desktop.tmp"

gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
kbuildsycoca6 >/dev/null 2>&1 || true

echo "Pengufy installed. Open it from your app menu or run: pengufy"
