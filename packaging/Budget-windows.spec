# PyInstaller recipe for Budget on Windows (dist/Budget/Budget.exe). Built by packaging/build-windows.ps1.
import sys

sys.path.insert(0, f"{SPECPATH}/..")
from app import VERSION  # noqa: F401  (keeps the build failing early if the app can't import)

a = Analysis(["../desktop.py"], pathex=[".."], datas=[("../static", "static")], excludes=["tkinter"],
             hiddenimports=["certifi"])  # trusted certificates for the update check
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Budget", console=False, icon="icon.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="Budget")
