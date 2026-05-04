# FB Video Downloader — Project Overview

## Mục đích

Tải video Facebook (Reels, Watch) từ các link private mà chỉ có thể xem khi đã login — dùng session Chrome hiện tại của người dùng.

**Tại sao cần?** Video trên FB Group/Page private không thể tải bằng công cụ online thông thường. Script này dùng Playwright để mô phỏng trình duyệt, intercept network stream, và tải video + audio riêng rồi merge lại.

---

## Kiến trúc

```
zari-entertainment/
├── scripts/
│   ├── download_lectures_from_list.py    ← CLI script tải từ CSV
│   ├── fb_group_batch_downloader.py      ← Crawl toàn bộ group FB
│   ├── fb_downloader_gui.py              ← GUI app (pywebview)
│   └── build_app.sh                      ← Build script cho macOS .app
├── downloads/
│   ├── README.md                         ← Hướng dẫn sử dụng
│   ├── theqk46/
│   │   ├── video_list_input.csv          ← Danh sách video (input)
│   │   ├── download_log.csv              ← Log kết quả (auto-gen)
│   │   ├── video_list.csv                ← Danh sách xử lý (auto-gen)
│   │   └── *.mp4                         ← Video đã tải
│   └── [other-lists]/
│       └── video_list_input.csv
├── .venv-ytdlp/                          ← Python venv
├── fb_downloader.spec                    ← PyInstaller config
├── dist/
│   └── FBDownloader.app                  ← macOS app (sau build)
├── README.md                             ← Repo intro
├── PROJECT.md                            ← File này
└── SETUP.md                              ← Hướng dẫn cài đặt
```

---

## Các thành phần

### 1. **CLI Script** (`scripts/download_lectures_from_list.py`)

**Mục đích:** Tải video từ file CSV danh sách.

**Cách dùng:**
```bash
.venv-ytdlp/bin/python scripts/download_lectures_from_list.py \
  --list downloads/theqk46/video_list_input.csv \
  --out  downloads/theqk46
```

**Input:** CSV file với 2 cột `title`, `url`
```csv
title,url
Bài giảng ngày 1,https://www.facebook.com/reel/3152731058254762
Bài giảng ngày 2,https://www.facebook.com/reel/845320351910326
```

**Output:**
- `download_log.csv` — log chi tiết (title, url, status, file path)
- `video_list.csv` — danh sách đã xử lý
- `*.mp4` — video đã tải

**Cách hoạt động:**
1. Đọc cookies từ Chrome (dùng `browser_cookie3`)
2. Mở Playwright browser headless, inject cookies
3. Với mỗi video:
   - Truy cập URL, resolve thành `watch/?v=VIDEO_ID`
   - Intercept network requests, tìm MP4 streams (video + audio)
   - Download riêng rồi merge bằng ffmpeg
4. Ghi log kết quả

---

### 2. **Group Batch Downloader** (`scripts/fb_group_batch_downloader.py`)

**Mục đích:** Tự động crawl toàn bộ video từ một FB Group.

**Cách hoạt động:**
1. Scroll trang Group, thu thập tất cả link video
2. Tải từng video như CLI script

**Lưu ý:** Hiện tại hardcode `GROUP_VIDEOS_URL` — có thể refactor để nhận CLI args.

---

### 3. **GUI App** (`scripts/fb_downloader_gui.py`)

**Mục đích:** Giao diện đơn giản cho người dùng không quen CLI.

**Công nghệ:** `pywebview` (WKWebView trên macOS) + HTML/CSS/JS

**Tính năng:**
- **Tab 1: Single URL** — paste link, nhập tên tuỳ chọn, chọn folder, bấm tải
- **Tab 2: CSV List** — chọn file CSV, tải hàng loạt
- **Log realtime** — hiển thị tiến độ tải

**Cách chạy:**
```bash
.venv-ytdlp/bin/python scripts/fb_downloader_gui.py
```

---

### 4. **macOS App Bundle** (`dist/FBDownloader.app`)

**Mục đích:** Đóng gói GUI thành `.app` để chia sẻ cho người khác (không cần cài Python).

**Build:**
```bash
bash scripts/build_app.sh
```

**Kết quả:** `dist/FBDownloader.app` (kèm Playwright, dependencies)

**Chia sẻ:**
```bash
cd dist && zip -r FBDownloader.zip FBDownloader.app
```

---

## Dependencies

| Package | Mục đích |
|---------|---------|
| `playwright` | Mô phỏng browser, intercept network |
| `browser_cookie3` | Đọc cookies từ Chrome |
| `pywebview` | GUI (WKWebView macOS) |
| `ffmpeg` | Merge video + audio |
| `curl` | Download streams |

**Cài venv:**
```bash
python3 -m venv .venv-ytdlp
.venv-ytdlp/bin/pip install -r requirements.txt
.venv-ytdlp/bin/playwright install chromium
```

---

## Quy trình sử dụng

### **Cách 1: CLI (nhanh, cho dev)**
```bash
# 1. Tạo CSV danh sách
cat > downloads/my_list/video_list_input.csv << EOF
title,url
Video 1,https://www.facebook.com/reel/123456
Video 2,https://www.facebook.com/reel/789012
EOF

# 2. Tải
.venv-ytdlp/bin/python scripts/download_lectures_from_list.py \
  --list downloads/my_list/video_list_input.csv \
  --out downloads/my_list
```

### **Cách 2: GUI App (cho người dùng)**
```bash
# Chạy GUI
.venv-ytdlp/bin/python scripts/fb_downloader_gui.py

# Hoặc mở .app (sau build)
open dist/FBDownloader.app
```

---

## Lưu ý quan trọng

⚠️ **Yêu cầu:**
- Phải **đang login Facebook trên Chrome** — script tự lấy cookies từ Chrome profile
- Nếu video private, phải có quyền xem (là thành viên group, bạn bè, v.v.)

⚠️ **Bản quyền:**
- Chỉ tải video mà bạn có quyền xem
- Không khuyến khích vi phạm bản quyền

⚠️ **Lỗi thường gặp:**
- `ModuleNotFoundError: No module named 'playwright'` → Cài venv
- `BrowserType.launch: Executable doesn't exist` → Chạy `playwright install chromium`
- `No video stream found` → Video có thể bị mã hóa, hoặc link không hợp lệ

---

## Roadmap

- [ ] Refactor `fb_group_batch_downloader.py` để nhận CLI args
- [ ] Thêm proxy support (cho VPN)
- [ ] Caching cookies để tránh đọc lại mỗi lần
- [ ] Build cho Windows (.exe)
- [ ] Web UI (Flask) thay vì desktop app
- [ ] Support tải từ TikTok, Instagram (mở rộng)

---

## File liên quan

- `@/Users/dansmbp/Workspace/Chat/zari-entertainment/downloads/README.md` — Hướng dẫn sử dụng chi tiết
- `@/Users/dansmbp/Workspace/Chat/zari-entertainment/SETUP.md` — Hướng dẫn cài đặt (nếu có)
