# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

backend_root = Path(SPECPATH).parent
sys.path.insert(0, str(backend_root))


def safe_collect_data(package_name: str):
    try:
        return collect_data_files(package_name)
    except Exception:
        return []


def safe_collect_binaries(package_name: str):
    try:
        return collect_dynamic_libs(package_name)
    except Exception:
        return []


def safe_collect_submodules(package_name: str):
    try:
        return collect_submodules(package_name)
    except Exception:
        return []


def safe_copy_metadata(package_name: str):
    try:
        return copy_metadata(package_name)
    except Exception:
        return []


local_packages = [
    "agent",
    "api",
    "db",
    "exceptions",
    "schemas",
    "services",
    "utils",
]

runtime_packages = [
    "aspose",
    "fitz",
    "onnxruntime",
    "rapidocr_onnxruntime",
]

metadata_packages = [
    "fastapi",
    "langchain",
    "langchain-core",
    "langchain-deepseek",
    "langchain-google-genai",
    "langchain-mcp-adapters",
    "langchain-openai",
    "langgraph",
    "pydantic",
    "sqlalchemy",
    "starlette",
    "uvicorn",
]

datas = [
    (str(backend_root / "config.example.yaml"), "."),
    (str(backend_root / "sql"), "sql"),
]
binaries = []
hiddenimports = [
    "main",
    "aiosqlite",
    "aspose.words",
    "fitz",
    "uvicorn.lifespan.on",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
]

for package_name in local_packages + runtime_packages:
    hiddenimports += safe_collect_submodules(package_name)

for package_name in runtime_packages:
    datas += safe_collect_data(package_name)
    binaries += safe_collect_binaries(package_name)

for package_name in metadata_packages:
    datas += safe_copy_metadata(package_name)

a = Analysis(
    [str(backend_root / "scripts" / "electron_api_entry.py")],
    pathex=[str(backend_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="offer-pilot-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="offer-pilot-api",
)
