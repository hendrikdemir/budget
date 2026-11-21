# PyInstaller recipe for Budget on Windows (dist/Budget/Budget.exe). Built by packaging/build-windows.ps1.
import sys

sys.path.insert(0, f"{SPECPATH}/..")
from app import VERSION
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

# Name, version and author in Budget.exe's properties; antivirus trusts files without them less.
numbers = tuple(int(n) for n in VERSION.split(".")) + (0,)
strings = {"CompanyName": "Hendrik Demir", "FileDescription": "Budget", "FileVersion": VERSION,
           "InternalName": "Budget", "LegalCopyright": "Hendrik Demir, GPL-3.0",
           "OriginalFilename": "Budget.exe", "ProductName": "Budget", "ProductVersion": VERSION}
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[StringFileInfo([StringTable("040904B0", [StringStruct(k, v) for k, v in strings.items()])]),
          VarFileInfo([VarStruct("Translation", [0x0409, 1200])])])

a = Analysis(["../desktop.py"], pathex=[".."], datas=[("../static", "static")], excludes=["tkinter"],
             hiddenimports=["certifi"])  # trusted certificates for the update check
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Budget", console=False, icon="icon.ico",
          version=version_info)
coll = COLLECT(exe, a.binaries, a.datas, name="Budget")
