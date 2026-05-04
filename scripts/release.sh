#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  scripts/release.sh — Build + tạo GitHub Release tự động
#  Yêu cầu: gh CLI (brew install gh && gh auth login)
#  Dùng:    bash scripts/release.sh v1.0.1
# ─────────────────────────────────────────────────────────────────────────────
set -e

VERSION=${1:-""}
if [[ -z "$VERSION" ]]; then
  echo "❌  Thiếu version. Ví dụ: bash scripts/release.sh v1.0.0"
  exit 1
fi

echo "🔨  Build FBDownloader ${VERSION}..."
bash scripts/build_app.sh

echo ""
echo "📦  Đóng gói FBDownloader.zip..."
cd dist
rm -f FBDownloader.zip
zip -r FBDownloader.zip FBDownloader.app
cd ..

echo ""
echo "📦  Tạo FBDownloader.pkg (macOS installer)..."
bash scripts/create_pkg.sh "${VERSION#v}"   # bỏ chữ "v" ở đầu

echo ""
echo "🚀  Tạo GitHub Release ${VERSION}..."
gh release create "$VERSION" \
  "dist/FBDownloader.zip#FBDownloader.zip — Portable (giải nén rồi kéo vào Applications)" \
  "dist/FBDownloader.pkg#FBDownloader.pkg — Installer tự động (khuyến nghị)" \
  --title "FB Video Downloader ${VERSION}" \
  --notes "## 📥 Cài đặt

### Cách 1: Installer (khuyến nghị) ✅
Tải **FBDownloader.pkg** → double-click → làm theo hướng dẫn.  
Pkg tự cài vào \`/Applications\` và nhắc cài \`ffmpeg\` nếu cần.

### Cách 2: Portable
Tải **FBDownloader.zip** → giải nén → kéo \`FBDownloader.app\` vào \`/Applications\`.

## Yêu cầu
- macOS 12+
- Google Chrome (đã đăng nhập Facebook)
- \`ffmpeg\`: \`brew install ffmpeg\`

## Lần đầu mở bị chặn (Gatekeeper)
\`\`\`bash
xattr -dr com.apple.quarantine /Applications/FBDownloader.app
\`\`\`
Hoặc: **System Settings → Privacy & Security → Open Anyway**

## Thay đổi trong phiên bản này
<!-- Điền changelog tại đây -->"

echo ""
echo "✅  Release ${VERSION} đã được tạo thành công!"
gh release view "$VERSION" --web
