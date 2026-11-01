#!/usr/bin/env bash
# Removes Pengufy. Pass --purge to also delete your sign-in and settings.
set -euo pipefail
APP_ID="io.github.htulu07.Pengufy"
PREFIX="${PREFIX:-$HOME/.local}"
pkill -f "$PREFIX/lib/pengufy/bin/spotifyd" 2>/dev/null || true
rm -rf "$PREFIX/lib/pengufy"
rm -f "$PREFIX/bin/pengufy" \
      "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg" \
      "$PREFIX/share/applications/$APP_ID.desktop"
if [[ "${1:-}" == "--purge" ]]; then
    rm -rf "$HOME/.local/share/pengufy" "$HOME/.cache/pengufy" "$HOME/.config/pengufy"
fi
kbuildsycoca6 >/dev/null 2>&1 || true
echo "Pengufy removed."
