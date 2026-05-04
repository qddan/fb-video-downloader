# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

venv = Path('.venv-ytdlp/lib/python3.14/site-packages')

a = Analysis(
    ['scripts/fb_downloader_web.py'],
    pathex=[],
    binaries=[],
    datas=[
        (str(venv / 'playwright/driver'),  'playwright/driver'),
        (str(venv / 'browser_cookie3'),    'browser_cookie3'),
    ],
    hiddenimports=[
        'browser_cookie3',
        'lz4',
        'lz4.frame',
        'Cryptodome',
        'Cryptodome.Cipher',
        'Cryptodome.Cipher.AES',
        'playwright',
        'playwright.async_api',
        'flask',
        'flask.templating',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'jinja2',
        'click',
        'itsdangerous',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['webview', 'PyObjC', 'objc', 'AppKit', 'Foundation', 'WebKit'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FBDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FBDownloader',
)

app = BUNDLE(
    coll,
    name='FBDownloader.app',
    icon=None,
    bundle_identifier='com.zari.fbdownloader',
    info_plist={
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
        'CFBundleShortVersionString': '2.0.0',
        'LSUIElement': False,
    },
)
