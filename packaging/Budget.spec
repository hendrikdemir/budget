# PyInstaller recipe for Budget.app. Built by packaging/build.sh.
import sys

sys.path.insert(0, f"{SPECPATH}/..")
from app import VERSION

a = Analysis(["../desktop.py"], pathex=[".."], datas=[("../static", "static")], excludes=["tkinter"],
             hiddenimports=["certifi"])  # trusted certificates for the update check
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Budget", console=False, target_arch=None)
coll = COLLECT(exe, a.binaries, a.datas, name="Budget")
app = BUNDLE(
    coll,
    name="Budget.app",
    icon="icon.icns",
    bundle_identifier="nl.hendrikdemir.budget",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Budget",
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.finance",
        "NSHumanReadableCopyright": "Your data stays on this Mac.",
    },
)
