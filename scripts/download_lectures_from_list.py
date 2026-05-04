#!/usr/bin/env python3
import argparse
import asyncio
import csv
import os
import re
import subprocess
import urllib.parse
import base64
import json
from pathlib import Path

import browser_cookie3
from playwright.async_api import async_playwright


def load_items(csv_path: Path) -> list[tuple[str, str]]:
    items = []
    with csv_path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            title = row.get('title', '').strip()
            url = row.get('url', '').strip()
            if title and url:
                items.append((title, url))
    return items


def parse_args():
    parser = argparse.ArgumentParser(description='Download FB videos from a CSV list')
    parser.add_argument('--list', required=True, metavar='CSV',
                        help='Path to input CSV file (columns: title, url)')
    parser.add_argument('--out', required=True, metavar='DIR',
                        help='Output directory for downloaded videos')
    return parser.parse_args()


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


async def resolve_to_watch(page, url: str) -> tuple[str, str]:
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


def download_merge(out: Path, title: str, vid: str, best_v, best_a):
    base = safe_name(title)
    vfile = out / f'{base} [{vid}].video.mp4'
    afile = out / f'{base} [{vid}].audio.mp4'
    ofile = out / f'{base} [{vid}].mp4'

    if ofile.exists() and ofile.stat().st_size > 0:
        return str(ofile), 'skipped_exists'

    if not best_v:
        return '', 'no_video_stream'

    subprocess.run(['curl', '-L', strip_byte_range(best_v[0]), '-o', str(vfile)], check=True)
    if best_a:
        subprocess.run(['curl', '-L', strip_byte_range(best_a[0]), '-o', str(afile)], check=True)
        subprocess.run(['ffmpeg', '-y', '-i', str(vfile), '-i', str(afile), '-c', 'copy', str(ofile)], check=True)
        if vfile.exists():
            vfile.unlink(missing_ok=True)
        if afile.exists():
            afile.unlink(missing_ok=True)
    else:
        os.replace(vfile, ofile)

    return str(ofile), 'ok'


async def main():
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / 'download_log.csv'
    lst = out / 'video_list.csv'

    items = load_items(Path(args.list))
    print(f'Loaded {len(items)} items from {args.list}')

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

    with lst.open('w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(['video_id', 'watch_url', 'title', 'source_url'])

    with log.open('w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(['title', 'source_url', 'video_id', 'watch_url', 'status', 'output_file'])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        for i, (title, url) in enumerate(items, start=1):
            try:
                vid, watch = await resolve_to_watch(page, url)
                if not vid:
                    raise RuntimeError('cannot_resolve_video_id')
                best_v, best_a = await capture_streams(page, watch, vid)
                output, status = download_merge(out, title, vid, best_v, best_a)
            except Exception as e:
                vid = extract_vid(url)
                watch = f'https://www.facebook.com/watch/?v={vid}' if vid else ''
                status = f'error: {e}'
                output = ''

            with lst.open('a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([vid, watch, title, url])

            with log.open('a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([title, url, vid, watch, status, output])

            print(f'[{i}/{len(items)}] {title} => {status}')

        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
