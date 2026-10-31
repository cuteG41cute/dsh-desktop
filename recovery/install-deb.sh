#!/usr/bin/env bash
# ============================================================================
# 在虚拟机里装/升级 dsh-manager（自动挑共享目录里版本最高的那个 deb）。
#
# 用法：
#   cd ~/share && bash install-deb.sh
#   cd ~/share && bash install-deb.sh /path/to/dsh-manager_x.y.z_all.deb
#
# 做的事：挑 deb → 检查包完整性（dpkg-deb -I）→ 安装 → 打印版本 → 提示重开窗口。
# 不碰实例目录、不碰 ~/.dsh，卸载/回滚见 rollback.sh。
# ============================================================================
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEB="${1:-}"

if [ -z "$DEB" ]; then
    # 按版本号排序挑最新的（不用 ls -t，mtime 会被拷贝顺序骗）
    DEB="$(ls -1 "$DIR"/dsh-manager_*_all.deb 2>/dev/null | sort -V | tail -n 1)"
fi

if [ -z "${DEB:-}" ] || [ ! -f "$DEB" ]; then
    echo "✘ 找不到 deb：$DIR/dsh-manager_*_all.deb" >&2
    exit 1
fi

echo "包：$DEB"
echo "大小：$(stat -c %s "$DEB") 字节"
echo "sha256：$(sha256sum "$DEB" | awk '{print $1}')"

if ! dpkg-deb -I "$DEB" >/dev/null 2>&1; then
    echo "✘ 这不是有效的 deb 包（可能传输时被截断），重新拷一次。" >&2
    exit 1
fi
echo "包信息：$(dpkg-deb -f "$DEB" Package Version | tr '\n' ' ')"

# 正在运行的管理器不会自动换代码，提醒用户
if pgrep -f 'dsh-manager' >/dev/null 2>&1; then
    echo "⚠ 管理器正在运行：装完请**关掉窗口再重新打开**，否则跑的还是旧代码。"
fi

sudo dpkg -i "$DEB" || { echo "✘ 安装失败，试：sudo apt --fix-broken install"; exit 1; }
echo "✔ 已安装：$(dpkg-query -W -f='${Version}' dsh-manager 2>/dev/null)"
echo "   启动：dsh-manager    （或点应用菜单里的 DeepSeek Harness 管理器）"
