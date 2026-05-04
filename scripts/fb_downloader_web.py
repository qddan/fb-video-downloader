#!/usr/bin/env python3
"""
FB Video Downloader — Flask web UI
Starts a local HTTP server and opens the system browser as the GUI.
No pywebview needed — no JS bridge issues.
"""

import asyncio, csv, json, os, queue, re, shutil, subprocess, sys
import threading, urllib.parse, base64, webbrowser, socket
from pathlib import Path

# ── Fix PATH when running as .app bundle ─────────────────────────────────────
_extra_paths = ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin']
os.environ['PATH'] = ':'.join(_extra_paths) + ':' + os.environ.get('PATH', '')

# ── Fix Playwright browser path ───────────────────────────────────────────────
if 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
    for _p in [
        Path.home() / 'Library' / 'Caches' / 'ms-playwright',
        Path.home() / '.cache' / 'ms-playwright',
    ]:
        if _p.exists():
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(_p)
            break

FFMPEG = shutil.which('ffmpeg') or 'ffmpeg'
CURL   = shutil.which('curl')   or 'curl'

from flask import Flask, jsonify, request, Response
import browser_cookie3
from playwright.async_api import async_playwright


# ── Download helpers ──────────────────────────────────────────────────────────

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


def _quality_score(tag: str, bitrate: int) -> tuple:
    """
    Score a stream for quality comparison.
    Priority: resolution tier first (fhd > hd > sd > unknown), then bitrate.
    Facebook uses vencode_tag values like 'fhd_v', 'hd_v', 'sd_v', 'audio_128' etc.
    """
    t = tag.lower()
    if 'fhd' in t or '1080' in t:
        tier = 4  # Full HD
    elif 'hd' in t or '720' in t:
        tier = 3  # HD
    elif 'sd' in t or '480' in t:
        tier = 2  # SD
    elif t and 'audio' not in t:
        tier = 1  # Unknown video tag
    else:
        tier = 0
    return (tier, bitrate)


async def capture_streams(page, watch_url: str, video_id: str):
    found = []

    def on_response(res):
        u = res.url
        if 'fbcdn.net' in u and '.mp4' in u:
            found.append(u)

    page.on('response', on_response)
    try:
        await page.goto(watch_url, wait_until='domcontentloaded', timeout=120000)
        # Scroll to trigger adaptive bitrate upgrade to highest quality
        try:
            await page.evaluate('window.scrollTo(0, 300)')
            await page.wait_for_timeout(2000)
            await page.evaluate('window.scrollTo(0, 0)')
        except Exception:
            pass
        await page.wait_for_timeout(14000)  # Extended wait for highest quality
    finally:
        try:
            page.remove_listener('response', on_response)
        except Exception:
            pass

    candidates = []
    seen_urls = set()
    for u in found:
        if u in seen_urls:
            continue
        seen_urls.add(u)
        meta = parse_efg(u)
        vid_match = str(meta.get('video_id')) == str(video_id)
        if not vid_match:
            # Fallback: no efg or video_id mismatch — include all fbcdn streams
            # but only if we have no matched candidates yet (processed later)
            candidates.append((u, 0, '', False, False))  # (url, bitrate, tag, is_audio, matched)
            continue
        tag = str(meta.get('vencode_tag') or '')
        bitrate = int(meta.get('bitrate') or 0)
        is_audio = 'audio' in tag.lower()
        candidates.append((u, bitrate, tag, is_audio, True))

    # Prefer matched (efg video_id) streams; fall back to unmatched only if needed
    matched = [c for c in candidates if c[4]]
    unmatched = [c for c in candidates if not c[4]]

    pool = matched if matched else unmatched

    vids = [x for x in pool if not x[3]]
    auds = [x for x in pool if x[3]]

    best_v = max(vids, key=lambda x: _quality_score(x[2], x[1])) if vids else None
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

    log_fn('  Đang tải video stream…')
    subprocess.run([CURL, '-L', '-#', strip_byte_range(best_v[0]), '-o', str(vfile)], check=True)
    if best_a:
        log_fn('  Đang tải audio stream…')
        subprocess.run([CURL, '-L', '-#', strip_byte_range(best_a[0]), '-o', str(afile)], check=True)
        log_fn('  Đang merge…')
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
        log_fn(f'Đã tải {len(cookies)} cookies từ Chrome')
        async with async_playwright() as p:
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
                        raise RuntimeError('Không tìm thấy video ID')
                    log_fn(f'  video_id: {vid}')
                    best_v, best_a = await capture_streams(page, watch, vid)
                    if not best_v:
                        raise RuntimeError('Không tìm thấy video stream — có thể video bị giới hạn quyền xem')
                    # Log chất lượng được chọn
                    if best_v:
                        tag = best_v[2]
                        br = best_v[1]
                        q_label = 'FHD' if 'fhd' in tag.lower() else 'HD' if 'hd' in tag.lower() else 'SD' if 'sd' in tag.lower() else 'Unknown'
                        log_fn(f'  chất lượng: {q_label} (tag={tag}, bitrate={br})')
                    _, status = download_merge(out, title, vid, best_v, best_a, log_fn)
                except Exception as e:
                    status = f'lỗi: {e}'
                log_fn(f'  → {status}')

            await browser.close()
    except Exception as e:
        log_fn(f'\n❌ Lỗi hệ thống: {e}')
    finally:
        done_fn()


# ── Flask App ─────────────────────────────────────────────────────────────────

flask_app = Flask(__name__)
_sessions: dict[str, queue.Queue] = {}


def _osascript_pick(script: str) -> str:
    """Run an AppleScript file dialog and return the chosen path."""
    result = subprocess.run(['osascript', '-e', script],
                            capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        return result.stdout.strip().rstrip('/')
    return ''


HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FB Video Downloader</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #F5F0E8;
    --surface:   #FFFFFF;
    --border:    #E8E2D9;
    --border-focus: #C4956A;
    --text:      #1A1814;
    --text-2:    #6B6560;
    --text-3:    #9C9690;
    --accent:    #C4956A;
    --accent-dk: #A87B52;
    --accent-lt: #F5EDE3;
    --green:     #3D7A5C;
    --red:       #C44B3A;
    --blue:      #3B6FA0;
    --shadow:    0 1px 3px rgba(60,45,20,0.08), 0 4px 16px rgba(60,45,20,0.06);
    --shadow-lg: 0 4px 8px rgba(60,45,20,0.08), 0 16px 48px rgba(60,45,20,0.10);
    --radius:    12px;
    --radius-sm: 8px;
  }

  body {
    font-family: 'Inter', -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 32px 16px;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Layout ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 36px;
    width: 100%;
    max-width: 600px;
    box-shadow: var(--shadow-lg);
  }

  /* ── Header ── */
  .header {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border);
  }

  .logo {
    width: 44px; height: 44px;
    background: var(--accent-lt);
    border: 1.5px solid var(--border);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
  }

  h1 {
    font-size: 18px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.3px;
  }

  .subtitle {
    font-size: 13px;
    color: var(--text-2);
    margin-top: 3px;
    font-weight: 400;
  }

  /* ── Tabs ── */
  .tabs {
    display: flex;
    gap: 2px;
    background: var(--bg);
    border-radius: 10px;
    padding: 3px;
    margin-bottom: 24px;
    border: 1px solid var(--border);
  }

  .tab {
    flex: 1;
    padding: 7px 16px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    font-family: inherit;
    color: var(--text-2);
    background: transparent;
    transition: all 0.18s;
  }

  .tab:hover { color: var(--text); }

  .tab.active {
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 1px 3px rgba(60,45,20,0.12);
    font-weight: 600;
  }

  /* ── Panels ── */
  .panel { display: none; }
  .panel.active { display: block; }

  /* ── Form fields ── */
  .field { margin-bottom: 16px; }

  label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-2);
    letter-spacing: 0.4px;
    text-transform: uppercase;
    margin-bottom: 7px;
  }

  input[type=text] {
    width: 100%;
    padding: 10px 13px;
    background: var(--bg);
    border: 1.5px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
    outline: none;
    transition: border-color 0.18s, box-shadow 0.18s, background 0.18s;
  }

  input[type=text]::placeholder { color: var(--text-3); }

  input[type=text]:focus {
    border-color: var(--border-focus);
    background: var(--surface);
    box-shadow: 0 0 0 3px rgba(196,149,106,0.15);
  }

  input[type=text][readonly] {
    cursor: default;
    color: var(--text-2);
  }

  .row { display: flex; gap: 8px; align-items: stretch; }
  .row input { flex: 1; }

  .btn-browse {
    padding: 10px 14px;
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-size: 13px;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.18s, border-color 0.18s;
  }

  .btn-browse:hover {
    background: var(--bg);
    border-color: var(--accent);
  }

  /* ── Divider ── */
  .divider {
    height: 1px;
    background: var(--border);
    margin: 20px 0;
  }

  /* ── Download button ── */
  .btn-dl {
    width: 100%;
    padding: 13px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.18s, transform 0.1s, box-shadow 0.18s;
    box-shadow: 0 2px 8px rgba(196,149,106,0.35);
    letter-spacing: -0.1px;
  }

  .btn-dl:hover:not(:disabled) {
    background: var(--accent-dk);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(196,149,106,0.4);
  }

  .btn-dl:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 1px 4px rgba(196,149,106,0.3);
  }

  .btn-dl:disabled {
    opacity: 0.55;
    cursor: not-allowed;
    transform: none;
  }

  /* ── Log ── */
  #log {
    margin-top: 20px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 12px;
    line-height: 1.65;
    min-height: 150px;
    max-height: 260px;
    overflow-y: auto;
    color: var(--text-2);
    white-space: pre-wrap;
    word-break: break-all;
  }

  #log .ok   { color: var(--green);  font-weight: 500; }
  #log .err  { color: var(--red);    font-weight: 500; }
  #log .info { color: var(--blue); }
  #log .head { color: var(--text);   font-weight: 600; }

  /* ── Status bar ── */
  .status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
    font-size: 12px;
    color: var(--text-3);
  }

  .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--green);
    flex-shrink: 0;
    transition: background 0.3s;
  }

  .dot.running {
    background: var(--accent);
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }

  /* Scrollbar */
  #log::-webkit-scrollbar { width: 5px; }
  #log::-webkit-scrollbar-track { background: transparent; }
  #log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
</style>
</head>
<body>
<div class="card">

  <div class="header">
    <div class="logo">⬇</div>
    <div>
      <h1>FB Video Downloader</h1>
      <div class="subtitle">Tải video Facebook bằng session Chrome của bạn</div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab(0)">Single URL</button>
    <button class="tab" onclick="switchTab(1)">CSV List</button>
  </div>

  <div id="panel0" class="panel active">
    <div class="field">
      <label>Facebook Video URL</label>
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

  <div class="divider"></div>

  <div class="field">
    <label>Thư mục lưu video</label>
    <div class="row">
      <input type="text" id="out_dir" placeholder="Chọn thư mục…" readonly>
      <button class="btn-browse" onclick="pickOut()">Chọn…</button>
    </div>
  </div>

  <button class="btn-dl" id="btn" onclick="startDownload()">⬇  Tải video</button>

  <div id="log">Sẵn sàng tải.\n</div>

  <div class="status-bar">
    <div class="dot" id="dot"></div>
    <span id="status-text">Sẵn sàng</span>
  </div>

</div>

<script>
let currentTab = 0;
let evtSource = null;

function switchTab(i) {
  currentTab = i;
  document.querySelectorAll('.tab').forEach((t, idx) => t.classList.toggle('active', idx === i));
  document.querySelectorAll('.panel').forEach((p, idx) => p.classList.toggle('active', idx === i));
}

function appendLog(msg, cls) {
  const el = document.getElementById('log');
  if (cls) {
    const span = document.createElement('span');
    span.className = cls;
    span.textContent = msg + '\\n';
    el.appendChild(span);
  } else {
    el.appendChild(document.createTextNode(msg + '\\n'));
  }
  el.scrollTop = el.scrollHeight;
}

function setStatus(running, text) {
  document.getElementById('dot').className = 'dot' + (running ? ' running' : '');
  document.getElementById('status-text').textContent = text;
}

async function pickCsv() {
  const res = await fetch('/api/pick_file');
  const data = await res.json();
  if (data.path) document.getElementById('csv_path').value = data.path;
}

async function pickOut() {
  const res = await fetch('/api/pick_folder');
  const data = await res.json();
  if (data.path) document.getElementById('out_dir').value = data.path;
}

async function startDownload() {
  const btn = document.getElementById('btn');
  const outDir = document.getElementById('out_dir').value.trim();
  if (!outDir) { appendLog('⚠ Hãy chọn thư mục lưu!', 'err'); return; }

  let payload;
  if (currentTab === 0) {
    const url = document.getElementById('url').value.trim();
    const title = document.getElementById('title').value.trim();
    if (!url) { appendLog('⚠ Hãy nhập URL!', 'err'); return; }
    payload = { mode: 'single', url, title, out: outDir };
  } else {
    const csvPath = document.getElementById('csv_path').value.trim();
    if (!csvPath) { appendLog('⚠ Hãy chọn file CSV!', 'err'); return; }
    payload = { mode: 'csv', csv: csvPath, out: outDir };
  }

  btn.disabled = true;
  btn.textContent = 'Đang tải…';
  document.getElementById('log').textContent = '';
  setStatus(true, 'Đang tải…');

  if (evtSource) { evtSource.close(); evtSource = null; }

  const res = await fetch('/api/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const { session_id } = await res.json();

  evtSource = new EventSource('/api/stream/' + session_id);
  evtSource.onmessage = function(e) {
    const item = JSON.parse(e.data);
    if (item.type === 'ping') return;
    if (item.type === 'done') {
      evtSource.close();
      btn.disabled = false;
      btn.textContent = '⬇  Tải video';
      appendLog('\\n✅ Hoàn thành!', 'ok');
      setStatus(false, 'Hoàn thành');
      return;
    }
    const msg = item.msg || '';
    let cls = '';
    if (msg.includes('→ ok') || msg.includes('✅') || msg.includes('Hoàn thành')) cls = 'ok';
    else if (msg.includes('lỗi') || msg.includes('❌') || msg.includes('Lỗi') || msg.includes('⚠')) cls = 'err';
    else if (msg.startsWith('\\n[')) cls = 'head';
    else if (msg.includes('video_id') || msg.includes('cookies') || msg.includes('chất lượng')) cls = 'info';
    appendLog(msg, cls);
  };
  evtSource.onerror = function() {
    evtSource.close();
    btn.disabled = false;
    btn.textContent = '⬇  Tải video';
    setStatus(false, 'Lỗi kết nối');
  };
}
</script>
</body>
</html>"""



@flask_app.route('/')
def index():
    return HTML


@flask_app.route('/api/pick_folder')
def api_pick_folder():
    path = _osascript_pick(
        'POSIX path of (choose folder with prompt "Chọn thư mục lưu video:")'
    )
    return jsonify({'path': path.rstrip('/')})


@flask_app.route('/api/pick_file')
def api_pick_file():
    path = _osascript_pick(
        'POSIX path of (choose file with prompt "Chọn file CSV:")'
    )
    return jsonify({'path': path.rstrip('/')})


@flask_app.route('/api/download', methods=['POST'])
def api_download():
    data = request.json
    session_id = os.urandom(8).hex()

    out = Path(data['out'])
    out.mkdir(parents=True, exist_ok=True)

    if data['mode'] == 'single':
        url = data['url']
        title = data.get('title') or f'fb_video_{extract_vid(url) or "unknown"}'
        items = [(title, url)]
    else:
        items = []
        try:
            with open(data['csv'], newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    t = row.get('title', '').strip()
                    u = row.get('url', '').strip()
                    if t and u:
                        items.append((t, u))
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    q: queue.Queue = queue.Queue()
    _sessions[session_id] = q

    def log(msg):
        q.put({'type': 'log', 'msg': msg})

    def done():
        q.put({'type': 'done'})

    def worker():
        asyncio.run(run_download(items, out, log, done))

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({'status': 'started', 'session_id': session_id})


@flask_app.route('/api/stream/<session_id>')
def api_stream(session_id):
    q = _sessions.get(session_id)

    def generate():
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'msg': 'Session không tìm thấy'})}\n\n"
            return
        while True:
            try:
                item = q.get(timeout=30)
                yield f"data: {json.dumps(item)}\n\n"
                if item.get('type') == 'done':
                    _sessions.pop(session_id, None)
                    break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@flask_app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    threading.Thread(target=lambda: os.kill(os.getpid(), 15), daemon=True).start()
    return jsonify({'status': 'ok'})


# ── Entry point ───────────────────────────────────────────────────────────────

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    port = find_free_port()
    url = f'http://127.0.0.1:{port}'

    def open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f'FB Downloader running at {url}')
    flask_app.run(host='127.0.0.1', port=port, debug=False,
                  use_reloader=False, threaded=True)


if __name__ == '__main__':
    main()
