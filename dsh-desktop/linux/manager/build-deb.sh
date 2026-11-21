#!/usr/bin/env bash
# 构建 dsh-manager 的 .deb（不依赖 dh / dpkg-buildpackage）
# 用法：bash build-deb.sh [--version 3.8.0] [--out <目录>]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_DIR="$HERE"
LINUX_DIR="$(cd "$HERE/.." && pwd)"
DESKTOP_DIR="$(cd "$LINUX_DIR/.." && pwd)"
VERSION="${DSH_MANAGER_VERSION:-3.8.0}"
OUT="$HERE"

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --out)     OUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "不认识的参数：$1" >&2; exit 2 ;;
  esac
done

command -v dpkg-deb >/dev/null 2>&1 || { echo "需要 dpkg-deb" >&2; exit 1; }
RUNNING_AS="root"; command -v sudo >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ] && RUNNING_AS="user"

mkdir -p "$OUT"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "== 组装载荷 =="
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/lib/dsh-manager" \
         "$STAGE/usr/lib/dsh-manager/share" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/256x256/apps" \
         "$STAGE/usr/share/doc/dsh-manager"

# 1) 管理器全部代码（含 sandbox.py、project_catalog/migration、插件）
cp -a "$MANAGER_DIR/dsh_manager/." "$STAGE/usr/lib/dsh-manager/dsh_manager/"
find "$STAGE/usr/lib/dsh-manager/dsh_manager" -name '__pycache__' -type d -prune -exec rm -rf {} +
install -m 0755 "$MANAGER_DIR/bin/dsh-manager" "$STAGE/usr/bin/dsh-manager"

# 2) 桌面窗口文件（实例 share/ 的来源）
install -m 0755 "$LINUX_DIR/dsh-desktop.py" "$STAGE/usr/lib/dsh-manager/share/dsh-desktop.py"
install -m 0755 "$LINUX_DIR/dsh-desktop"    "$STAGE/usr/lib/dsh-manager/share/dsh-desktop"
PREVIEW="$DESKTOP_DIR/tools/preview-probe/preview-tools.js"
[ -f "$PREVIEW" ] && install -m 0644 "$PREVIEW" "$STAGE/usr/lib/dsh-manager/share/preview-tools.js" || true
if [ -f "$LINUX_DIR/dsh-desktop.png" ]; then
  install -m 0644 "$LINUX_DIR/dsh-desktop.png" "$STAGE/usr/lib/dsh-manager/share/dsh-desktop.png"
  install -m 0644 "$LINUX_DIR/dsh-desktop.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/dsh-manager.png"
fi

# 3) 桌面项 + 文档
install -m 0644 "$MANAGER_DIR/deb/usr/share/applications/dsh-manager.desktop" \
  "$STAGE/usr/share/applications/dsh-manager.desktop"
[ -f "$MANAGER_DIR/README.md" ] && install -m 0644 "$MANAGER_DIR/README.md" \
  "$STAGE/usr/share/doc/dsh-manager/README.md" || true

# 4) 控制文件
sed "s/^Version: .*/Version: $VERSION/" "$MANAGER_DIR/deb/DEBIAN/control" > "$STAGE/DEBIAN/control"
install -m 0755 "$MANAGER_DIR/deb/DEBIAN/postinst" "$STAGE/DEBIAN/postinst"
install -m 0755 "$MANAGER_DIR/deb/DEBIAN/prerm"    "$STAGE/DEBIAN/prerm"
SIZE_KB=$(du -sk --exclude=DEBIAN "$STAGE" | awk '{print $1}')
sed -i "s/^Installed-Size: .*/Installed-Size: $SIZE_KB/" "$STAGE/DEBIAN/control"

# 5) 打包
DEB="$OUT/dsh-manager_${VERSION}_all.deb"
rm -f "$DEB"
echo "== 打 deb =="
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
echo "✔ $DEB"
ls -l "$DEB" | awk '{print "  大小:", $5, "字节"}'
command -v sha256sum >/dev/null 2>&1 && sha256sum "$DEB" | sed 's/^/  sha256: /'
dpkg-deb -c "$DEB" | grep -E 'sandbox.py|plugins/dsh-fence' | sed 's/^/  /'
