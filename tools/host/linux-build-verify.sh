#!/bin/bash
# Build the Linux deb inside WSL and verify it contains the debug JS control action.
# Usage: linux-build-verify.sh <repo-path-in-wsl> <version>
set -u
REPO="${1:?repo path}"
VERSION="${2:?version}"
cd "$REPO/dsh-desktop/linux/manager" || { echo "BUILD=FAIL no manager dir"; exit 1; }
bash build-deb.sh --version "$VERSION" --out "$REPO/dist/linux" > /tmp/build.log 2>&1
RC=$?
DEB="$REPO/dist/linux/dsh-manager_${VERSION}_all.deb"
if [ ! -f "$DEB" ]; then
  echo "BUILD=FAIL no deb"
  tail -20 /tmp/build.log
  exit 1
fi
echo "BUILD=OK rc=$RC size=$(stat -c %s "$DEB")"
CNT=$(dpkg-deb --fsys-tarfile "$DEB" | tar -xO ./usr/lib/dsh-manager/share/dsh-desktop.py 2>/dev/null | grep -c "startswith('js ")
echo "JSACTION=${CNT:-0}"
CNT2=$(dpkg-deb --fsys-tarfile "$DEB" | tar -xO ./usr/lib/dsh-manager/share/dsh-desktop.py 2>/dev/null | grep -c load_web_scripts)
echo "LOADER=${CNT2:-0}"
for f in image-pan.js preview-menu.js text-menu.js folder-drop.js file-dragout-linux.js; do
  dpkg-deb --fsys-tarfile "$DEB" | tar -t 2>/dev/null | grep -q "share/web/$f" && echo "WEB=$f ok" || echo "WEB=$f MISSING"
done
