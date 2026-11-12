#!/bin/bash
# Purge dsh-manager from the VM, then reinstall the deb downloaded from our GitHub release.
set -u

echo "=== 1) 停止运行中的管理器 ==="
pkill -f '/usr/bin/dsh-manager' 2>/dev/null || true
sleep 2
pgrep -af 'dsh-manager' | head -3 || echo '(已停止)'

echo "=== 2) 卸载包（purge）==="
sudo -n dpkg -P dsh-manager 2>&1 | tail -5
echo "--- 包状态 ---"
dpkg -l dsh-manager 2>/dev/null | tail -2 || echo '(not installed)'

echo "=== 3) 清理残留文件 ==="
sudo -n rm -rf /usr/lib/dsh-manager /usr/bin/dsh-manager
rm -rf "$HOME/.config/dsh-manager" "$HOME/.cache/dsh-manager"
sudo -n rm -f /usr/share/applications/dsh-manager.desktop
sudo -n rm -f /usr/share/icons/hicolor/*/apps/dsh-manager.png
echo "--- 残留检查 ---"
for p in /usr/lib/dsh-manager /usr/bin/dsh-manager "$HOME/.config/dsh-manager" /usr/share/applications/dsh-manager.desktop; do
  [ -e "$p" ] && echo "STILL: $p" || echo "gone: $p"
done
echo "--- 保留的实例目录（不动）---"
ls -d "$HOME"/.local/opt/deepseek-harness-* "$HOME"/Program/deepseek-harness-* 2>/dev/null || true

echo "=== 4) 从 GitHub 下载 deb ==="
URL="https://github.com/cuteG41cute/dsh-desktop/releases/download/v3.0.3/dsh-manager_3.0.3_all.deb"
cd /tmp || exit 1
rm -f dsh-manager-github.deb
if command -v curl >/dev/null; then
  curl -sSL --retry 3 --max-time 300 -o dsh-manager-github.deb "$URL"
else
  wget -q -O dsh-manager-github.deb "$URL"
fi
echo "download rc=$?"
ls -l dsh-manager-github.deb 2>/dev/null || echo '(download failed)'
echo "--- sha256 ---"
sha256sum dsh-manager-github.deb 2>/dev/null || true
echo "期望: 9be8d10ef367b49abf886e6584f32789371fd2e0413353f9a7302fc0b1a2a1f6"

echo "=== 5) 安装 ==="
sudo -n dpkg -i dsh-manager-github.deb 2>&1 | tail -6
sudo -n apt-get -f install -y >/dev/null 2>&1 || true
dpkg-query -W -f='installed=%{Version}\n' dsh-manager 2>/dev/null || echo '(install failed)'
