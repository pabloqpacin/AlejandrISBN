# -*- mode: python ; coding: utf-8 -*-
# Build on Windows (or CI windows-latest):
#   pip install -r requirements.txt -r requirements-build.txt
#   pyinstaller alejandrisbn.spec
#
# Output: dist/AlejandrISBN/AlejandrISBN.exe  (+ DLLs)

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas = [("static", "static")]
datas += collect_data_files("certifi")
version_file = Path("VERSION")
if version_file.is_file():
    datas.append((str(version_file), "."))
readme = Path("packaging/windows-seed-README.txt")
if readme.is_file():
    datas.append((str(readme), "packaging"))
seed_dir = Path("seed")
if seed_dir.is_dir():
    for path in seed_dir.iterdir():
        if path.is_file() and (".example." in path.name or path.name == "README.md"):
            datas.append((str(path), "seed"))

a = Analysis(
    ["app/desktop_app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "h11",
        "httpx",
        "anyio",
        "anyio._backends._asyncio",
        "aiosqlite",
        "certifi",
        "app.main",
        "app.db",
        "app.db.config",
        "app.db.common",
        "app.db.runtime",
        "app.db.schema",
        "app.db.postgres",
        "app.db.sqlite",
        "app.database",
        "app.seed",
        "app.schemas",
        "app.services.isbn_lookup",
        "app.services.enrich",
        "app.routers",
        "app.routers.enrich",
        "app.version",
        "app.desktop_app",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["asyncpg", "uvloop"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AlejandrISBN",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AlejandrISBN",
)
