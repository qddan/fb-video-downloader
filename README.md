# FB Video Downloader

Tải video Facebook (Reels, Watch, Group) từ link private — dùng session Chrome của bạn.

> ⚠️ **Lưu ý pháp lý:** Công cụ này chỉ truy cập nội dung mà bạn **đã có quyền xem** thông qua tài khoản của chính mình. Việc sử dụng cookies từ trình duyệt để tự động hóa có thể vi phạm [Điều khoản dịch vụ của Facebook](https://www.facebook.com/terms.php) (mục 3.2). **Chỉ dùng cho mục đích cá nhân, không vi phạm bản quyền.**

---

## ✨ Tính năng

- 🔐 Tự động lấy session từ Chrome (không cần nhập mật khẩu)
- 🎬 Tải video chất lượng cao nhất (FHD > HD > SD tự động chọn)
- 📋 Hỗ trợ tải hàng loạt qua file CSV
- 🖥️ Giao diện web chạy trên máy (localhost), mở bằng trình duyệt bất kỳ
- 📦 Đóng gói thành `.app` cho macOS (không cần cài Python)

---

## 🚀 Cài đặt & Chạy nhanh

### Yêu cầu

- **macOS** (Apple Silicon hoặc Intel)
- **Google Chrome** (đã đăng nhập Facebook)
- **Python 3.11+** (`brew install python`)
- **ffmpeg** (`brew install ffmpeg`)

### Cài đặt

```bash
# Clone repo
git clone https://github.com/your-username/zari-entertainment.git
cd zari-entertainment

# Tạo virtualenv và cài dependencies
python3 -m venv .venv-ytdlp
.venv-ytdlp/bin/pip install -r requirements.txt

# Cài Playwright browser (Chromium)
.venv-ytdlp/bin/playwright install chromium
```

### Chạy GUI (Web)

```bash
.venv-ytdlp/bin/python scripts/fb_downloader_web.py
```

App sẽ tự mở trình duyệt tại `http://127.0.0.1:<port>`.

### Chạy CLI (hàng loạt)

```bash
# Tạo file CSV danh sách
cat > my_list.csv << EOF
title,url
Video ngày 1,https://www.facebook.com/reel/123456
Video ngày 2,https://www.facebook.com/reel/789012
EOF

# Tải
.venv-ytdlp/bin/python scripts/download_lectures_from_list.py \
  --list my_list.csv \
  --out ~/Downloads/fb_videos
```

---

## 📦 Build macOS App (.app)

Người dùng có thể đóng gói thành file `.app` để chạy mà không cần cài Python.

### Yêu cầu build

```bash
# Cài PyInstaller (đã có trong requirements.txt)
.venv-ytdlp/bin/pip install pyinstaller
```

### Build

```bash
bash scripts/build_app.sh
```

Kết quả: `dist/FBDownloader.app`

### Chia sẻ

```bash
cd dist && zip -r FBDownloader.zip FBDownloader.app
```

> 💡 **Người nhận cần:** macOS 12+, Chrome (đã login FB), và ffmpeg (`brew install ffmpeg`).  
> Playwright Chromium được bundle sẵn trong app, **không cần cài thêm**.  
> ffmpeg **không được bundle** vì quá nặng (~100MB) — người dùng cần cài riêng.

---

## 🔒 Vấn đề pháp lý khi push lên GitHub

| Vấn đề | Đánh giá | Khuyến nghị |
|--------|----------|-------------|
| Dùng cookies Chrome | ⚠️ Vi phạm ToS Facebook (mục 3.2) nếu tự động hóa | Ghi rõ "chỉ dùng cá nhân" |
| Tải video private | ⚠️ Có thể vi phạm bản quyền tác giả | Chỉ tải video bạn có quyền |
| Chia sẻ code trên GitHub | ✅ Code là công cụ, không vi phạm pháp luật | Thêm disclaimer vào README |
| Playwright/browser_cookie3 | ✅ Đây là thư viện open-source hợp pháp | Không vấn đề gì |

**Kết luận:** Push code lên GitHub là hợp pháp — đây là code mở, không phải nội dung vi phạm. Tuy nhiên hãy:
1. Ghi rõ disclaimer trong README (đã có ở trên)
2. Không upload file `.cookie` hay dữ liệu cá nhân
3. `.gitignore` đã loại `downloads/`, `dist/`, `.venv-ytdlp/`

---

## 🗂️ Cấu trúc dự án

```
zari-entertainment/
├── scripts/
│   ├── fb_downloader_web.py     ← GUI chính (Flask web)
│   ├── fb_downloader_gui.py     ← GUI cũ (pywebview, deprecated)
│   ├── download_lectures_from_list.py  ← CLI batch downloader
│   └── build_app.sh             ← Build script macOS
├── fb_downloader.spec           ← PyInstaller config
├── requirements.txt
├── README.md
├── PROJECT.md                   ← Tổng quan kiến trúc chi tiết
└── SETUP.md                     ← Hướng dẫn cài đặt
```

---

## ❓ Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|-----|------------|-----|
| `ffmpeg not found` | chưa cài ffmpeg | `brew install ffmpeg` |
| `No cookies found` | chưa login Chrome | Mở Chrome, login Facebook |
| `No video stream` | video bị giới hạn hoặc link sai | Kiểm tra quyền xem video |
| `Playwright not found` | chưa cài browser | `.venv-ytdlp/bin/playwright install chromium` |
