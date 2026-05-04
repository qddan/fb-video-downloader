#!/usr/bin/env python3
"""
FB Video Downloader — GUI wrapper (pywebview / WKWebView)
Reads Chrome cookies automatically; downloads FB videos via Playwright.
"""
import asyncio
import csv
import json
import os
import queue
import re
import subprocess
import sys
import threading
import urllib.parse
import base64
from pathlib import Path

# ── Fix PATH and tool paths when running as a bundled .app ─────────────────
# PyInstaller resets env vars, so /opt/homebrew/bin is missing from PATH.
# We restore it so ffmpeg, curl, and Playwright can be found.
import shutil
_extra_paths = ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin']
os.environ['PATH'] = ':'.join(_extra_paths) + ':' + os.environ.get('PATH', '')

# Find ffmpeg and curl absolute paths at startup (works both in dev and .app)
def _find_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(
            f"'{name}' không tìm thấy. Hãy cài đặt bằng: brew install {name}"
        )
    return path

FFMPEG = _find_tool('ffmpeg') if shutil.which('ffmpeg') else 'ffmpeg'
CURL   = _find_tool('curl')   if shutil.which('curl')   else 'curl'

# Fix Playwright browser path
if 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
    _candidates = [
        Path.home() / 'Library' / 'Caches' / 'ms-playwright',  # macOS
        Path.home() / '.cache' / 'ms-playwright',               # Linux fallback
    ]
    for _p in _candidates:
        if _p.exists():
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(_p)
            break

import webview
import browser_cookie3
from playwright.async_api import async_playwright


# ── helpers (same logic as download_lectures_from_list.py) ──────────────────

def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', '_', s).strip()[:180]


def extract_vid(url: str) -> str:
    for pat in [r'/reel/(\d+)', r'[?&]v=(\d+)', r'/videos/(\d+)']:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return ''


def parse_efg(url: str) -> dict:
    qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    efg = qs.get('efg', [None])[0]
    if not efg:
        return {}
    try:
        raw = urllib.parse.unquote(efg)
        raw += '=' * (-len(raw) % 4)
        return json.loads(base64.b64decode(raw).decode('utf-8', 'ignore'))
    except Exception:
        return {}


def strip_byte_range(url: str) -> str:
    sp = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(sp.query, keep_blank_values=True)
    q = [(k, v) for (k, v) in q if k not in ('bytestart', 'byteend')]
    return urllib.parse.urlunsplit((sp.scheme, sp.netloc, sp.path, urllib.parse.urlencode(q), sp.fragment))


def load_cookies():
    cj = browser_cookie3.chrome(domain_name='facebook.com')
    cookies = []
    for c in cj:
        if 'facebook.com' in c.domain:
            cookies.append({
                'name': c.name,
                'value': c.value,
                'domain': c.domain if c.domain.startswith('.') else '.' + c.domain,
                'path': c.path or '/',
                'expires': c.expires if c.expires else -1,
                'httpOnly': False,
                'secure': bool(c.secure),
                'sameSite': 'Lax',
            })
    return cookies


async def resolve_to_watch(page, url: str):
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=120000)
        await page.wait_for_timeout(6000)
        cur = page.url
        vid = extract_vid(cur)
        if vid:
            return vid, f'https://www.facebook.com/watch/?v={vid}'
        hrefs = await page.eval_on_selector_all('a[href]', 'els => els.map(e => e.href)')
        for h in hrefs:
            vid = extract_vid(h or '')
            if vid:
                return vid, f'https://www.facebook.com/watch/?v={vid}'
    except Exception:
        pass
    vid = extract_vid(url)
    return vid, (f'https://www.facebook.com/watch/?v={vid}' if vid else url)


async def capture_streams(page, watch_url: str, video_id: str):
    found = []

    def on_response(res):
        u = res.url
        if 'fbcdn.net' in u and '.mp4' in u:
            found.append(u)

    page.on('response', on_response)
    try:
        await page.goto(watch_url, wait_until='domcontentloaded', timeout=120000)
        await page.wait_for_timeout(12000)
    finally:
        try:
            page.remove_listener('response', on_response)
        except Exception:
            pass

    candidates = []
    for u in found:
        meta = parse_efg(u)
        if str(meta.get('video_id')) == str(video_id):
            tag = str(meta.get('vencode_tag') or '')
            bitrate = int(meta.get('bitrate') or 0)
            is_audio = 'audio' in tag
            candidates.append((u, bitrate, tag, is_audio))

    vids = [x for x in candidates if not x[3]]
    auds = [x for x in candidates if x[3]]
    best_v = max(vids, key=lambda x: x[1]) if vids else None
    best_a = max(auds, key=lambda x: x[1]) if auds else None
    return best_v, best_a


def download_merge(out: Path, title: str, vid: str, best_v, best_a, log_fn):
    base = safe_name(title)
    vfile = out / f'{base} [{vid}].video.mp4'
    afile = out / f'{base} [{vid}].audio.mp4'
    ofile = out / f'{base} [{vid}].mp4'

    if ofile.exists() and ofile.stat().st_size > 0:
        return str(ofile), 'skipped_exists'

    if not best_v:
        return '', 'no_video_stream'

    log_fn(f'  Downloading video stream…')
    subprocess.run([CURL, '-L', '-#', strip_byte_range(best_v[0]), '-o', str(vfile)], check=True)
    if best_a:
        log_fn(f'  Downloading audio stream…')
        subprocess.run([CURL, '-L', '-#', strip_byte_range(best_a[0]), '-o', str(afile)], check=True)
        log_fn(f'  Merging…')
        subprocess.run([FFMPEG, '-y', '-i', str(vfile), '-i', str(afile), '-c', 'copy', str(ofile)],
                       check=True, capture_output=True)
        vfile.unlink(missing_ok=True)
        afile.unlink(missing_ok=True)
    else:
        os.replace(vfile, ofile)

    return str(ofile), 'ok'


async def run_download(items: list, out: Path, log_fn, done_fn):
    try:
        cookies = load_cookies()
        async with async_playwright() as p:
            # When packaged, playwright might not find the browser binary. 
            # We can log any error that happens here.
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
            )
            await ctx.add_cookies(cookies)
            page = await ctx.new_page()

            for i, (title, url) in enumerate(items, start=1):
                log_fn(f'\n[{i}/{len(items)}] {title}')
                try:
                    vid, watch = await resolve_to_watch(page, url)
                    if not vid:
                        raise RuntimeError('cannot_resolve_video_id')
                    best_v, best_a = await capture_streams(page, watch, vid)
                    _, status = download_merge(out, title, vid, best_v, best_a, log_fn)
                except Exception as e:
                    status = f'error: {e}'
                log_fn(f'  → {status}')

            await browser.close()
    except Exception as e:
        log_fn(f'\nLỗi hệ thống: {str(e)}')
    finally:
        done_fn()


# ── HTML UI ─────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FB Video Downloader</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f5f5f7; color: #1d1d1f; padding: 24px; }
  h1 { font-size: 20px; font-weight: 700; margin-bottom: 20px; color: #1877F2; }
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; }
  .tab { padding: 8px 18px; border-radius: 8px; cursor: pointer;
         background: #e0e0e5; font-size: 14px; border: none; }
  .tab.active { background: #1877F2; color: white; font-weight: 600; }
  .panel { display: none; } .panel.active { display: block; }
  label { display: block; font-size: 13px; font-weight: 600;
          margin-bottom: 4px; color: #444; }
  input[type=text] { width: 100%; padding: 9px 12px; border-radius: 8px;
    border: 1.5px solid #d0d0d5; font-size: 14px; outline: none;
    transition: border 0.2s; background: white; }
  input[type=text]:focus { border-color: #1877F2; }
  .row { display: flex; gap: 8px; align-items: center; }
  .row input { flex: 1; }
  button { padding: 9px 16px; border-radius: 8px; border: none;
           cursor: pointer; font-size: 13px; font-weight: 600; }
  .btn-browse { background: #e0e0e5; color: #333; }
  .btn-browse:hover { background: #d0d0d5; }
  .field { margin-bottom: 14px; }
  .btn-dl { width: 100%; padding: 12px; font-size: 16px; font-weight: 700;
            background: #1877F2; color: white; border-radius: 10px;
            margin-top: 6px; transition: background 0.2s; }
  .btn-dl:hover { background: #1558b0; }
  .btn-dl:disabled { background: #8ab4f8; cursor: not-allowed; }
  #log { margin-top: 16px; background: #1e1e1e; color: #d4d4d4;
         border-radius: 10px; padding: 14px; font-family: 'Menlo', monospace;
         font-size: 12px; min-height: 180px; max-height: 320px;
         overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
</style>
</head>
<body>
<h1>⬇ FB Video Downloader</h1>

<div class="tabs">
  <button class="tab active" onclick="switchTab(0)">Single URL</button>
  <button class="tab" onclick="switchTab(1)">CSV List</button>
</div>

<div id="panel0" class="panel active">
  <div class="field">
    <label>Facebook video URL</label>
    <input type="text" id="url" placeholder="https://www.facebook.com/reel/...">
  </div>
  <div class="field">
    <label>Tên file (tuỳ chọn)</label>
    <input type="text" id="title" placeholder="Để trống = tự đặt theo video ID">
  </div>
</div>

<div id="panel1" class="panel">
  <div class="field">
    <label>File CSV (cột: title, url)</label>
    <div class="row">
      <input type="text" id="csv_path" placeholder="Chọn file CSV…" readonly>
      <button class="btn-browse" onclick="pickCsv()">Chọn…</button>
    </div>
  </div>
</div>

<div class="field">
  <label>Thư mục lưu video</label>
  <div class="row">
    <input type="text" id="out_dir" placeholder="Chọn thư mục…" readonly>
    <button class="btn-browse" onclick="pickOut()">Chọn…</button>
  </div>
</div>

<button class="btn-dl" id="btn" onclick="startDownload()" disabled style="background:#8ab4f8;cursor:not-allowed">⬇  Đang khởi động...</button>
<div id="log">Sẵn sàng. Đang khởi động...</div>

<script>
let currentTab = 0;
let _apiReady = false;

// Poll every 300ms until window.pywebview.api is truly ready.
// pywebviewready event is unreliable in PyInstaller .app bundles.
var _readyTimer = setInterval(function() {
  if (typeof window.pywebview !== 'undefined' && window.pywebview.api) {
    clearInterval(_readyTimer);
    _apiReady = true;
    var btn = document.getElementById('btn');
    btn.disabled = false;
    btn.style.background = '';
    btn.style.cursor = '';
    btn.textContent = '\u2b07  T\u1ea3i video';
    document.getElementById('log').textContent = 'S\u1eb5n s\u00e0ng.\n';
  }
}, 300);

function switchTab(i) {
  currentTab = i;
  document.querySelectorAll('.tab').forEach((t, idx) => t.classList.toggle('active', idx === i));
  document.querySelectorAll('.panel').forEach((p, idx) => p.classList.toggle('active', idx === i));
}

function appendLog(msg) {
  const el = document.getElementById('log');
  el.textContent += msg + '\n';
  el.scrollTop = el.scrollHeight;
}

async function pickCsv() {
  if (!_apiReady) { appendLog('⚠ App chưa sẵn sàng, thử lại...'); return; }
  const p = await window.pywebview.api.pick_file();
  if (p) document.getElementById('csv_path').value = p;
}

async function pickOut() {
  if (!_apiReady) { appendLog('⚠ App chưa sẵn sàng, thử lại...'); return; }
  const p = await window.pywebview.api.pick_folder();
  if (p) document.getElementById('out_dir').value = p;
}

async function startDownload() {
  if (!_apiReady) { appendLog('⚠ App chưa sẵn sàng, thử lại...'); return; }
  const btn = document.getElementById('btn');
  const outDir = document.getElementById('out_dir').value.trim();
  if (!outDir) { appendLog('⚠ Hãy chọn thư mục lưu!'); return; }

  let payload;
  if (currentTab === 0) {
    const url = document.getElementById('url').value.trim();
    const title = document.getElementById('title').value.trim();
    if (!url) { appendLog('⚠ Hãy nhập URL!'); return; }
    payload = { mode: 'single', url, title, out: outDir };
  } else {
    const csvPath = document.getElementById('csv_path').value.trim();
    if (!csvPath) { appendLog('⚠ Hãy chọn file CSV!'); return; }
    payload = { mode: 'csv', csv: csvPath, out: outDir };
  }

  btn.disabled = true;
  btn.textContent = 'Đang tải\u2026';
  document.getElementById('log').textContent = '';
  await window.pywebview.api.start_download(JSON.stringify(payload));
}

function onLog(msg) { appendLog(msg); }

function onDone() {
  const btn = document.getElementById('btn');
  btn.disabled = false;
  btn.textContent = '\u2b07  T\u1ea3i video';
  appendLog('\n\u2705 Ho\u00e0n th\u00e0nh!');
}
</script>
</body>
</html>"""


# ── pywebview API ────────────────────────────────────────────────────────────

class Api:
    def __init__(self):
        self._window = None

    def set_window(self, w):
        self._window = w

    def pick_file(self):
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('CSV Files (*.csv)', 'All files (*.*)')
        )
        return result[0] if result else ''

    def pick_folder(self):
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else ''

    def start_download(self, payload_json: str):
        payload = json.loads(payload_json)
        out = Path(payload['out'])
        out.mkdir(parents=True, exist_ok=True)

        if payload['mode'] == 'single':
            url = payload['url']
            title = payload.get('title') or f'fb_video_{extract_vid(url) or "unknown"}'
            items = [(title, url)]
        else:
            items = []
            with open(payload['csv'], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    t = row.get('title', '').strip()
                    u = row.get('url', '').strip()
                    if t and u:
                        items.append((t, u))

        def log(msg):
            self._window.evaluate_js(f'onLog({json.dumps(msg)})')

        def done():
            self._window.evaluate_js('onDone()')

        def worker():
            asyncio.run(run_download(items, out, log, done))

        threading.Thread(target=worker, daemon=True).start()


# ── entry point ──────────────────────────────────────────────────────────────

def main():
    api = Api()
    w = webview.create_window(
        'FB Video Downloader',
        html=HTML,
        js_api=api,
        width=680,
        height=700,
        min_size=(500, 500),
    )
    api.set_window(w)
    webview.start(debug=False)


if __name__ == '__main__':
    main()
