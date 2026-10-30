# PyInstaller recipe for Budget.app. Built by packaging/build.sh.
VERSION = "1.0.0"

a = Analysis(["../desktop.py"], pathex=[".."], datas=[("../static", "static")], excludes=["tkinter"])
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
