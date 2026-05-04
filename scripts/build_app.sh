#!/usr/bin/env bash
# Build FBDownloader.app for macOS
# Run from the repo root: bash scripts/build_app.sh

set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv-ytdlp"
PYINSTALLER="$VENV/bin/pyinstaller"

echo "==> Checking venv…"
if [[ ! -f "$PYINSTALLER" ]]; then
    echo "PyInstaller not found. Installing…"
    "$VENV/bin/pip" install pyinstaller
fi

echo "==> Cleaning previous build…"
rm -rf build dist

echo "==> Building app…"
"$PYINSTALLER" fb_downloader.spec --noconfirm

echo ""
echo "✅ Done! App is at: dist/FBDownloader.app"
echo "   You can zip and share it:"
echo "   cd dist && zip -r FBDownloader.zip FBDownloader.app"
