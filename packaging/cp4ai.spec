# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Copy 4 AI macOS app."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
VERSION = os.environ.get("CP4AI_VERSION", "3.0.0")
SRC = ROOT / "src"
NATIVE = ROOT / "packaging" / "native"
RESOURCES = SRC / "cp4ai" / "resources"

datas = []
hiddenimports = [
    "AppKit",
    "Foundation",
    "objc",
    "Vision",
    "Quartz",
    "CoreML",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
]

for package in (
    "pymupdf",
    "pymupdf4llm",
    "ocrmac",
    "tiktoken",
    "psutil",
    "yaml",
    "onnxruntime",
    "ftfy",
):
    package_datas, _package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    hiddenimports += package_hidden

hiddenimports += collect_submodules("tiktoken_ext")

for path in sorted((NATIVE / "bin").iterdir()):
    datas.append((str(path), "bin"))
for directory in ("tiktoken", "etc"):
    source = NATIVE / directory
    if source.exists():
        datas.append((str(source), directory))
if (RESOURCES / "quickaction").is_dir():
    datas.append((str(RESOURCES / "quickaction"), "quickaction"))

notices = ROOT / "THIRD_PARTY_NOTICES.md"
if notices.exists():
    datas.append((str(notices), "."))

a = Analysis(
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Copy 4 AI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Copy 4 AI",
)

app = BUNDLE(
    coll,
    name="Copy 4 AI.app",
    icon=str(ROOT / "branding" / "CP4AI.icns"),
    bundle_identifier="com.titusng0110.cp4ai",
    info_plist={
        "CFBundleName": "Copy 4 AI",
        "CFBundleDisplayName": "Copy 4 AI",
        "CFBundleIdentifier": "com.titusng0110.cp4ai",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "LSMinimumSystemVersion": "15.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "NSHumanReadableCopyright": "MIT License",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "PDF document",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["com.adobe.pdf"],
            },
            {
                "CFBundleTypeName": "Word document",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": [
                    "org.openxmlformats.wordprocessingml.document"
                ],
            },
            {
                "CFBundleTypeName": "PowerPoint presentation",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": [
                    "org.openxmlformats.presentationml.presentation"
                ],
            },
        ],
    },
)
