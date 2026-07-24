# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

speech_datas, speech_binaries, speech_hiddenimports = collect_all("faster_whisper")
raw_datas, raw_binaries, raw_hiddenimports = collect_all("rawpy")
heif_datas, heif_binaries, heif_hiddenimports = collect_all("pillow_heif")
for package in ("ctranslate2", "onnxruntime", "av"):
    speech_binaries += collect_dynamic_libs(package)
raw_binaries += collect_dynamic_libs("rawpy")
heif_binaries += collect_dynamic_libs("pillow_heif")
speech_hiddenimports += [
    "ctranslate2",
    "tokenizers",
    "onnxruntime",
    "av",
]

a = Analysis(
    ["beacon_app.py"],
    pathex=[".."],
    binaries=speech_binaries + raw_binaries + heif_binaries,
    datas=speech_datas + raw_datas + heif_datas + [
        ("../beacon/qml", "beacon/qml"),
        ("README_APP.txt", "."),
    ],
    hiddenimports=(
        speech_hiddenimports
        + raw_hiddenimports
        + heif_hiddenimports
        + ["PIL.Image"]
    ),
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "pydantic",
        "pydantic_core",
    ],
    noarchive=False,
    optimize=0,
)

blocked_qt_capabilities = (
    "data_visualization",
    "datavisualization",
    "qtcharts",
    "qtpdf",
    "qtquick3d",
    "qtvirtualkeyboard",
    "qtwebengine",
    "virtualkeyboard",
    "webengine",
)


def keep_beacon_qt_entry(entry):
    searchable = " ".join(str(value).lower() for value in entry[:2])
    return not any(name in searchable for name in blocked_qt_capabilities)


a.binaries = [entry for entry in a.binaries if keep_beacon_qt_entry(entry)]
a.datas = [entry for entry in a.datas if keep_beacon_qt_entry(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ATLAS Beacon",
    icon="beacon.ico",
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
    version="version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ATLAS Beacon",
)
