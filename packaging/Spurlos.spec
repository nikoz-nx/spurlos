# -*- mode: python -*-
# Bauplan für Spurlos.app (PyInstaller). Aufruf: python -m PyInstaller packaging/Spurlos.spec
import re
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "spurlos" / "__init__.py").read_text()).group(1)
ICON = ROOT / "packaging" / "Spurlos.icns"

a = Analysis(
    [str(ROOT / "packaging" / "run_desktop.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "spurlos" / "web"), "spurlos/web"),
        (str(ROOT / "spurlos" / "data"), "spurlos/data"),
    ],
    hiddenimports=["keyring.backends.macOS", "webview.platforms.cocoa"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Spurlos",
    console=False,
    codesign_identity=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Spurlos")
app = BUNDLE(
    coll,
    name="Spurlos.app",
    icon=str(ICON) if ICON.exists() else None,
    bundle_identifier="io.github.nikoz-nx.spurlos",
    version=VERSION,
    info_plist={
        "CFBundleName": "Spurlos",
        "CFBundleDisplayName": "Spurlos",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "12.0",
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Freie Software unter der GNU GPL v3",
    },
)
