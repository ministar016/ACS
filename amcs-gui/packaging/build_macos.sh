#!/usr/bin/env bash
# Build AMCS.app and a drag-to-install DMG on macOS.
#
#   cd amcs-gui && bash packaging/build_macos.sh
#
# Output: dist/AMCS.app and dist/AMCS-<version>-macOS-<arch>.dmg
# The app is ad-hoc signed (not notarised): on first launch use
# right-click → Open, or:  xattr -dr com.apple.quarantine /Applications/AMCS.app
set -euo pipefail
cd "$(dirname "$0")/.."

[[ "$(uname)" == "Darwin" ]] || { echo "build_macos.sh must run on macOS" >&2; exit 1; }

PY=${PYTHON:-python3}
VERSION=$(cat packaging/VERSION)
ARCH=$(uname -m)

echo "[amcs] build venv"
"$PY" -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt pyinstaller -q

echo "[amcs] icon"
python packaging/make_icon.py packaging/amcs.png
ICONSET=build/AMCS.iconset
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
    sips -z "$s" "$s" packaging/amcs.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s * 2)) $((s * 2)) packaging/amcs.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o packaging/AMCS.icns

echo "[amcs] pyinstaller"
pyinstaller --noconfirm --clean packaging/amcs.spec
codesign --force --deep --sign - dist/AMCS.app          # ad-hoc signature (required on Apple Silicon)

echo "[amcs] dmg"
STAGE=build/dmg
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R dist/AMCS.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="dist/AMCS-${VERSION}-macOS-${ARCH}.dmg"
rm -f "$DMG"
hdiutil create -volname "AMCS ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
echo "[amcs] done: dist/AMCS.app  $DMG"
