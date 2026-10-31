#!/usr/bin/env bash
# ============================================================================
# 构建 dsh-manager 的 .deb（任何 Debian 系系统都能跑，不需要 dh / dpkg-buildpackage）
#   用法：bash build-deb.sh [--version 1.0.0] [--out <目录>]
#   产出：<out>/dsh-manager_<version>_all.deb
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # dsh-desktop/linux/manager
MANAGER_DIR="$HERE"
LINUX_DIR="$(cd "$HERE/.." && pwd)"                    # dsh-desktop/linux
DESKTOP_DIR="$(cd "$LINUX_DIR/.." && pwd)"             # dsh-desktop
VERSION="1.4.0"
OUT="$HERE"

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --out)     OUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "不认识的参数：$1" >&2; exit 2 ;;
  esac
done

command -v dpkg-deb >/dev/null 2>&1 || { echo "需要 dpkg-deb（Debian/Ubuntu/Deepin 自带）" >&2; exit 1; }
mkdir -p "$OUT"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "== 组装载荷（staging=$STAGE）=="
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/lib/dsh-manager/dsh_manager" \
         "$STAGE/usr/lib/dsh-manager/share" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/256x256/apps" \
         "$STAGE/usr/share/doc/dsh-manager"

# 1) 管理器本体
install -m 0644 "$MANAGER_DIR/dsh_manager/__init__.py" "$STAGE/usr/lib/dsh-manager/dsh_manager/"
install -m 0644 "$MANAGER_DIR/dsh_manager/core.py"     "$STAGE/usr/lib/dsh-manager/dsh_manager/"
install -m 0644 "$MANAGER_DIR/dsh_manager/cli.py"      "$STAGE/usr/lib/dsh-manager/dsh_manager/"
install -m 0644 "$MANAGER_DIR/dsh_manager/gui.py"      "$STAGE/usr/lib/dsh-manager/dsh_manager/"
install -m 0644 "$MANAGER_DIR/dsh_manager/style.css"   "$STAGE/usr/lib/dsh-manager/dsh_manager/"
# 设计稿主题（7 套 × 日/夜）与配套背景图：由 tools/build-gtk-theme.py 生成
install -m 0644 "$MANAGER_DIR/dsh_manager/themes.json" "$STAGE/usr/lib/dsh-manager/dsh_manager/"
mkdir -p "$STAGE/usr/lib/dsh-manager/dsh_manager/theme" "$STAGE/usr/lib/dsh-manager/dsh_manager/backgrounds"
cp -f "$MANAGER_DIR"/dsh_manager/theme/*.css "$MANAGER_DIR"/dsh_manager/theme/index.json \
      "$STAGE/usr/lib/dsh-manager/dsh_manager/theme/"
cp -f "$MANAGER_DIR"/dsh_manager/backgrounds/*.png "$STAGE/usr/lib/dsh-manager/dsh_manager/backgrounds/"
mkdir -p "$STAGE/usr/lib/dsh-manager/dsh_manager/icons"
cp -f "$MANAGER_DIR"/dsh_manager/icons/*.svg "$STAGE/usr/lib/dsh-manager/dsh_manager/icons/"
install -m 0644 "$MANAGER_DIR/dsh_manager/plugins.py"  "$STAGE/usr/lib/dsh-manager/dsh_manager/"
install -m 0755 "$MANAGER_DIR/bin/dsh-manager"         "$STAGE/usr/bin/dsh-manager"

# 2) 随包带的桌面窗口文件（新实例的 share/ 从这里取）
install -m 0755 "$LINUX_DIR/dsh-desktop.py" "$STAGE/usr/lib/dsh-manager/share/dsh-desktop.py"
install -m 0755 "$LINUX_DIR/dsh-desktop"    "$STAGE/usr/lib/dsh-manager/share/dsh-desktop"
PREVIEW="$DESKTOP_DIR/tools/preview-probe/preview-tools.js"
if [ -f "$PREVIEW" ]; then
  install -m 0644 "$PREVIEW" "$STAGE/usr/lib/dsh-manager/share/preview-tools.js"
else
  echo "警告：没找到 preview-tools.js，实例将没有预览增强" >&2
fi
if [ -f "$LINUX_DIR/dsh-desktop.png" ]; then
  install -m 0644 "$LINUX_DIR/dsh-desktop.png" "$STAGE/usr/lib/dsh-manager/share/dsh-desktop.png"
  install -m 0644 "$LINUX_DIR/dsh-desktop.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/dsh-manager.png"
fi

# 3) 桌面项 + 文档
install -m 0644 "$MANAGER_DIR/deb/usr/share/applications/dsh-manager.desktop" \
  "$STAGE/usr/share/applications/dsh-manager.desktop"
if [ -f "$MANAGER_DIR/README.md" ]; then
  install -m 0644 "$MANAGER_DIR/README.md" "$STAGE/usr/share/doc/dsh-manager/README.md"
fi
cat > "$STAGE/usr/share/doc/dsh-manager/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: dsh-desktop
Source: https://github.com/cuteG41cute/dsh-desktop
Files: *
License: MIT
EOF

# 4) 控制文件（版本号在这里替换）
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
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$DEB" | sed 's/^/  sha256: /'
fi
echo "== 包信息 =="
dpkg-deb -I "$DEB" | sed 's/^/  /'
echo "== 内容（前 20 项）=="
dpkg-deb -c "$DEB" | sed -n '1,20p' | sed 's/^/  /'
