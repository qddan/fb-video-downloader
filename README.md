# FB Video Downloader

Tải video Facebook (Reels, Watch, Group) từ link private — dùng session Chrome của bạn, không cần nhập mật khẩu.

> ⚠️ **Lưu ý pháp lý:** Chỉ tải video mà bạn **có quyền xem**. Sử dụng cookie trình duyệt để tự động hóa có thể vi phạm [ToS Facebook](https://www.facebook.com/terms.php) mục 3.2. **Chỉ dùng cá nhân, không vi phạm bản quyền.**

---

## 📥 Cài đặt cho người dùng (không cần cài Python)

> **Yêu cầu tối thiểu:** macOS 12+, Google Chrome (đã đăng nhập Facebook)

### Cách 1: Installer .pkg ✅ (khuyến nghị)

1. Vào **[Releases](https://github.com/qddan/fb-video-downloader/releases/latest)**
2. Tải file **`FBDownloader.pkg`**
3. Double-click → làm theo hướng dẫn cài đặt
4. Pkg tự cài vào `/Applications` và nhắc cài `ffmpeg` nếu cần

### Cách 2: Portable .zip

1. Tải **`FBDownloader.zip`** từ Releases
2. Giải nén → kéo `FBDownloader.app` vào `/Applications`
3. Cài ffmpeg: `brew install ffmpeg`

### Lần đầu mở bị macOS chặn

```bash
xattr -dr com.apple.quarantine /Applications/FBDownloader.app
```
Hoặc: **System Settings → Privacy & Security → Open Anyway**

### Sử dụng

Double-click **FBDownloader** trong Launchpad → trình duyệt tự mở → paste link → chọn thư mục → **Tải video**.

---

## ✨ Tính năng

- 🔐 Xác thực bằng session Chrome — không nhập mật khẩu
- 🎬 Tự động chọn chất lượng cao nhất: FHD > HD > SD
- 📋 Hỗ trợ tải hàng loạt qua file CSV
- 📡 Log real-time (Server-Sent Events)
- 🖥️ Giao diện web hiện đại, mở trên trình duyệt bất kỳ

---

## 🛠 Chạy từ source code (dành cho developer)

### Yêu cầu

- Python 3.11+, ffmpeg (`brew install ffmpeg`)
- Google Chrome (đã đăng nhập Facebook)

### Cài đặt

```bash
git clone https://github.com/qddan/fb-video-downloader.git
cd fb-video-downloader

python3 -m venv .venv-ytdlp
.venv-ytdlp/bin/pip install -r requirements.txt
.venv-ytdlp/bin/playwright install chromium
```

### Chạy

```bash
# GUI (web)
.venv-ytdlp/bin/python scripts/fb_downloader_web.py

# CLI (batch từ CSV)
.venv-ytdlp/bin/python scripts/download_lectures_from_list.py \
  --list my_list.csv --out ~/Downloads/fb_videos
```

---

## 📦 Build & Release (dành cho maintainer)

```bash
# Chỉ build .app
bash scripts/build_app.sh

# Chỉ tạo .pkg từ .app đã build
bash scripts/create_pkg.sh 1.0.0

# Build + tạo GitHub Release với cả .zip và .pkg (cần gh CLI)
bash scripts/release.sh v1.0.0
```

> **Cài gh CLI:** `brew install gh && gh auth login`

---

## ❓ Troubleshooting

| Lỗi | Fix |
|-----|-----|
| `ffmpeg not found` | `brew install ffmpeg` |
| Không tải được video | Mở Chrome → đăng nhập Facebook |
| App bị macOS chặn | `xattr -dr com.apple.quarantine /Applications/FBDownloader.app` |
| Video private/group | Kiểm tra bạn có quyền xem trên Facebook |
