# Hướng dẫn cài đặt

## Yêu cầu

- **macOS** (hiện tại build cho arm64 Apple Silicon)
- **Chrome** (đã cài, đang login Facebook)
- **Python 3.11+** (hoặc dùng Homebrew: `brew install python@3.14`)
- **ffmpeg** (dùng Homebrew: `brew install ffmpeg`)
- **curl** (thường có sẵn)

---

## Bước 1: Clone repo

```bash
git clone <repo-url>
cd zari-entertainment
```

---

## Bước 2: Tạo venv và cài dependencies

```bash
# Tạo venv
python3 -m venv .venv-ytdlp

# Activate
source .venv-ytdlp/bin/activate

# Cài packages
pip install -r requirements.txt

# Download Playwright browsers
.venv-ytdlp/bin/playwright install chromium
```

---

## Bước 3: Đăng nhập Facebook trên Chrome

1. Mở Chrome
2. Vào https://facebook.com
3. Đăng nhập tài khoản của bạn
4. **Giữ Chrome mở** (script sẽ đọc cookies từ Chrome profile)

---

## Bước 4: Chạy

### **Option A: CLI (dòng lệnh)**

```bash
# Tạo danh sách video
cat > downloads/my_videos/video_list_input.csv << EOF
title,url
Bài 1,https://www.facebook.com/reel/123456789
Bài 2,https://www.facebook.com/reel/987654321
EOF

# Tải
.venv-ytdlp/bin/python scripts/download_lectures_from_list.py \
  --list downloads/my_videos/video_list_input.csv \
  --out downloads/my_videos
```

### **Option B: GUI (giao diện)**

```bash
.venv-ytdlp/bin/python scripts/fb_downloader_gui.py
```

Cửa sổ sẽ hiện lên, chọn tab, paste link hoặc chọn CSV, bấm "Tải video".

---

## Bước 5 (tuỳ chọn): Build macOS app

Để chia sẻ cho người khác (không cần họ cài Python):

```bash
# Build
bash scripts/build_app.sh

# Kết quả: dist/FBDownloader.app
# Zip để chia sẻ
cd dist && zip -r FBDownloader.zip FBDownloader.app
```

Người nhận chỉ cần:
1. Giải nén `.zip`
2. Mở `FBDownloader.app`
3. Đăng nhập FB trên Chrome của họ
4. Dùng app

---

## Troubleshooting

### **Lỗi: `ModuleNotFoundError: No module named 'playwright'`**
→ Venv chưa activate hoặc pip install chưa xong
```bash
source .venv-ytdlp/bin/activate
pip install -r requirements.txt
```

### **Lỗi: `BrowserType.launch: Executable doesn't exist`**
→ Playwright browsers chưa download
```bash
.venv-ytdlp/bin/playwright install chromium
```

### **Lỗi: `No video stream found` hoặc `error: cannot_resolve_video_id`**
→ Link không hợp lệ, hoặc video bị mã hóa, hoặc bạn không có quyền xem
- Kiểm tra link có đúng không
- Kiểm tra Chrome có login FB không
- Thử mở link trên Chrome xem có xem được không

### **Lỗi: `browser_cookie3.BrowserCookieError`**
→ Chrome không cài, hoặc không tìm thấy cookies
- Kiểm tra Chrome đã cài chưa
- Kiểm tra Chrome đã login FB chưa
- Thử đóng Chrome rồi mở lại

### **App macOS báo "unidentified developer"**
→ Bình thường trên macOS
- Chuột phải → Open → Open anyway
- Hoặc: `xattr -d com.apple.quarantine dist/FBDownloader.app`

---

## File cấu hình

- `requirements.txt` — Python dependencies
- `fb_downloader.spec` — PyInstaller config (cho build .app)
- `scripts/build_app.sh` — Build script

---

## Cấu trúc thư mục downloads

```
downloads/
  README.md                    ← Hướng dẫn sử dụng
  theqk46/
    video_list_input.csv       ← Danh sách input (bạn tạo)
    download_log.csv           ← Log (auto-gen)
    video_list.csv             ← Danh sách xử lý (auto-gen)
    *.mp4                      ← Video đã tải
  my_videos/
    video_list_input.csv
    ...
```

Mỗi danh sách video nên có folder riêng.

---

## Hỗ trợ

Nếu gặp lỗi:
1. Kiểm tra Chrome login FB chưa
2. Kiểm tra link có đúng format không
3. Xem log output để tìm lỗi cụ thể
4. Thử chạy lại
