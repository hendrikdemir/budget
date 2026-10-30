#!/bin/bash
# Builds dist/Budget.app and dist/Budget.dmg. Needs python.org Python 3 and internet the first time.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv-build ] || python3 -m venv .venv-build
.venv-build/bin/pip install --quiet pyinstaller pywebview pillow
[ -f packaging/icon.icns ] || .venv-build/bin/python packaging/make_icon.py

.venv-build/bin/pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/Budget.spec

# The installer: the app next to a shortcut to Applications, to drag it onto.
rm -rf build/dmg dist/Budget.dmg
mkdir -p build/dmg
cp -R dist/Budget.app build/dmg/
ln -s /Applications build/dmg/Applications
hdiutil create -quiet -volname Budget -srcfolder build/dmg -format UDZO dist/Budget.dmg

echo "Built dist/Budget.app and dist/Budget.dmg"
