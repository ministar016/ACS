# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AMCS — run from amcs-gui/:  pyinstaller --noconfirm packaging/amcs.spec
# macOS: produces dist/AMCS.app (see packaging/build_macos.sh); elsewhere dist/AMCS/.
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
VERSION = open(os.path.join(ROOT, "packaging", "VERSION")).read().strip()

datas = [
    (os.path.join(ROOT, "AMCSDashboard.qml"), "."),
    (os.path.join(ROOT, "Map3D.qml"), "."),
    (os.path.join(ROOT, "symbols"), "symbols"),
    (os.path.join(ROOT, "icons"), "icons"),
    (os.path.join(ROOT, "sim", "data"), os.path.join("sim", "data")),
    (os.path.join(ROOT, "packaging", "amcs.png"), "packaging"),
]
if os.path.isdir(os.path.join(ROOT, "scenarios")):
    # Seed scenarios (incl. .last_saved) — copied to the user's folder on first start
    datas.append((os.path.join(ROOT, "scenarios"), "scenarios"))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtNetwork",
                   "sim.engine", "sim.terrain"],
    excludes=["tkinter", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineQuick",
              "PyQt6.QtWebEngineWidgets", "PyQt6.QtMultimedia", "PyQt6.Qt3DCore",
              "PyQt6.QtBluetooth", "PyQt6.QtSql", "PyQt6.QtTest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AMCS",
    console=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AMCS")

if sys.platform == "darwin":
    icns = os.path.join(ROOT, "packaging", "AMCS.icns")
    app = BUNDLE(
        coll,
        name="AMCS.app",
        icon=icns if os.path.exists(icns) else None,
        bundle_identifier="com.soca016.amcs",
        version=VERSION,
        info_plist={
            "CFBundleName": "AMCS",
            "CFBundleDisplayName": "AMCS C-UAS",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "LSApplicationCategoryType": "public.app-category.utilities",
        },
    )
