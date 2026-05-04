#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  scripts/create_pkg.sh — Đóng gói FBDownloader.pkg (macOS installer)
#  Yêu cầu: Xcode Command Line Tools (xcode-select --install)
#  Input:   dist/FBDownloader.app  (phải build trước)
#  Output:  dist/FBDownloader.pkg
# ─────────────────────────────────────────────────────────────────────────────
set -e

APP_SRC="dist/FBDownloader.app"
PKG_OUT="dist/FBDownloader.pkg"
PKG_ID="com.zari.fbdownloader"
VERSION="${1:-1.0.0}"   # Truyền vào: bash scripts/create_pkg.sh 1.0.0

echo "📦  Tạo macOS installer (.pkg) — v${VERSION}"

# ── Kiểm tra .app đã build chưa ──────────────────────────────────────────────
if [ ! -d "$APP_SRC" ]; then
  echo "❌  Chưa build app. Chạy trước: bash scripts/build_app.sh"
  exit 1
fi

# ── Tạo thư mục staging ───────────────────────────────────────────────────────
TMPROOT=$(mktemp -d)
PAYLOAD="$TMPROOT/payload"
SCRIPTS="$TMPROOT/scripts"
mkdir -p "$PAYLOAD/Applications" "$SCRIPTS"

# Copy .app vào payload (ánh xạ tới /Applications/)
cp -r "$APP_SRC" "$PAYLOAD/Applications/"

# ── Post-install script ───────────────────────────────────────────────────────
# Chạy sau khi cài xong — xóa quarantine và nhắc cài ffmpeg nếu cần
cat > "$SCRIPTS/postinstall" << 'EOF'
#!/bin/bash

# 1. Xóa quarantine để app mở ngay không bị macOS chặn
xattr -dr com.apple.quarantine /Applications/FBDownloader.app 2>/dev/null || true

# 2. Kiểm tra ffmpeg — hiện dialog nếu chưa có
if ! command -v ffmpeg &>/dev/null \
   && ! [ -f /opt/homebrew/bin/ffmpeg ] \
   && ! [ -f /usr/local/bin/ffmpeg ]; then
  osascript <<APPLESCRIPT
display dialog "✅ FBDownloader đã cài thành công!

⚠️  Còn thiếu ffmpeg (dùng để ghép video + âm thanh).
Mở Terminal và chạy lệnh sau:

    brew install ffmpeg

Nếu chưa có Homebrew:
    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"" \
  with title "FBDownloader" buttons {"OK"} default button "OK" \
  with icon note
APPLESCRIPT
fi

exit 0
EOF
chmod +x "$SCRIPTS/postinstall"

# ── Build component package (.pkg) ────────────────────────────────────────────
pkgbuild \
  --root       "$PAYLOAD" \
  --scripts    "$SCRIPTS" \
  --identifier "$PKG_ID" \
  --version    "$VERSION" \
  --install-location "/" \
  "$PKG_OUT"

# ── Cleanup ───────────────────────────────────────────────────────────────────
rm -rf "$TMPROOT"

echo ""
echo "✅  Tạo xong: $PKG_OUT"
echo "   Kích thước: $(du -sh $PKG_OUT | cut -f1)"
echo ""
echo "   Người dùng chỉ cần double-click file .pkg để cài!"
echo "   (Sau cài xong: /Applications/FBDownloader.app)"
