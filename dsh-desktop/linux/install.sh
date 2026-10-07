#!/usr/bin/env bash
# ============================================================================
# DeepSeek Harness 桌面版（Linux） - 免 root 安装脚本
#   安装到 ~/.local/share/dsh-desktop/，并创建桌面与应用程序菜单项。
#   卸载：bash uninstall.sh（或删除 ~/.local/share/dsh-desktop 与对应 .desktop 文件）
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${DEST:-$HOME/.local/share/dsh-desktop}"
BIN="$HOME/.local/bin"
APP="$HOME/.local/share/applications"
ICON_DEST="$HOME/.local/share/icons/hicolor/256x256/apps"

echo "==> 安装 DeepSeek Harness 桌面版到 $DEST"

mkdir -p "$DEST" "$BIN" "$APP" "$ICON_DEST"

# 1) 程序文件
install -m 0755 "$HERE/dsh-desktop"      "$DEST/dsh-desktop"
install -m 0644 "$HERE/dsh-desktop.py"   "$DEST/dsh-desktop.py"
install -m 0644 "$HERE/dsh-desktop.png"  "$DEST/dsh-desktop.png" 2>/dev/null || true
install -m 0644 "$HERE/README-linux.md"  "$DEST/README-linux.md" 2>/dev/null || true

# 2) 图标（多尺寸）
for s in 16 32 48 64 128 256; do
    if [ -f "$HERE/icons/${s}x${s}/apps/dsh-desktop.png" ]; then
        mkdir -p "$HOME/.local/share/icons/hicolor/${s}x${s}/apps"
        install -m 0644 "$HERE/icons/${s}x${s}/apps/dsh-desktop.png" \
            "$HOME/.local/share/icons/hicolor/${s}x${s}/apps/dsh-desktop.png"
    fi
done

# 3) 启动器与菜单项
ln -sf "$DEST/dsh-desktop" "$BIN/dsh-desktop"

cat > "$APP/dsh-desktop.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.2.2
Name=DeepSeek Harness
Name[zh_CN]=DeepSeek Harness 桌面版
GenericName=DeepSeek Harness Desktop
Comment=DeepSeek Harness WebUI in a native window
Exec=$BIN/dsh-desktop
Icon=dsh-desktop
Terminal=false
Categories=Utility;Network;Development;
EOF

# 4) 卸载脚本
cat > "$DEST/uninstall.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
echo "==> 卸载 DeepSeek Harness 桌面版"
rm -f "$BIN/dsh-desktop" "$APP/dsh-desktop.desktop"
for s in 16 32 48 64 128 256; do
    rm -f "\$HOME/.local/share/icons/hicolor/\${s}x\${s}/apps/dsh-desktop.png"
done
rm -rf "$DEST"
echo "==> 已卸载。"
EOF
chmod +x "$DEST/uninstall.sh"

# 5) 刷新图标/桌面缓存（失败可忽略）
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
update-desktop-database "$APP" 2>/dev/null || true

echo "==> 安装完成！"
echo "    启动：$BIN/dsh-desktop  （或从应用程序菜单打开 DeepSeek Harness）"
echo "    卸载：$DEST/uninstall.sh"
echo ""
echo "依赖检查（缺失请先安装）："
for c in python3 node npm curl; do
    if command -v "$c" >/dev/null 2>&1; then
        echo "  [OK] $c"
    else
        echo "  [缺失] $c"
    fi
done
python3 - <<'PYEOF' 2>/dev/null || echo "  [缺失] python3-gi / gir1.2-webkit2-4.1(或4.0)（apt install python3-gi gir1.2-webkit2-4.1）"
import gi
gi.require_version('Gtk','3.0')
try:
    gi.require_version('WebKit2','4.1')
except Exception:
    gi.require_version('WebKit2','4.0')
print("  [OK] python3-gi + WebKitGTK")
PYEOF
