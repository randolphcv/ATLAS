# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["beacon_app.py"],
    pathex=[".."],
    binaries=[],
    datas=[
        ("../beacon/qml", "beacon/qml"),
        ("README_APP.txt", "."),
    ],
    hiddenimports=[],
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
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
