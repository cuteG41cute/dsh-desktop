#!/usr/bin/env bash
# ============================================================================
# 虚拟机一次性修复（需要 sudo，跑一次即可）：
#   · 装截图/比对工具：spectacle、imagemagick、python3-numpy
#   · 装 Samba，并把 ~/share 共享出来（Windows 上 \\172.22.148.197\share 就能用）
#   · 装 UI 攻坚要用的字体与 SVG 依赖：fonts-inter、fonts-noto-cjk、librsvg2-common
#
# 用法：sudo bash ~/share/fix-vm-sudo.sh
# ============================================================================
set -u
[ "$(id -u)" = "0" ] || { echo "请用 sudo 运行：sudo bash $0"; exit 1; }

USER_NAME="${SUDO_USER:-twinblade}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
SHARE_DIR="$HOME_DIR/share"
mkdir -p "$SHARE_DIR"
chown "$USER_NAME:$USER_NAME" "$SHARE_DIR" 2>/dev/null || true

echo "== 1. 安装工具链 =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || echo "（apt update 有警告，继续）"
apt-get install -y --no-install-recommends \
    samba spectacle imagemagick python3-numpy \
    librsvg2-common fonts-inter fonts-noto-cjk \
    xdotool python3-gi-cairo python3-pil >/dev/null
echo "  已装：$(command -v spectacle || echo 'spectacle 缺')  $(command -v convert || echo 'imagemagick 缺')  $(command -v smbd || echo 'smbd 缺')  $(command -v xdotool || echo 'xdotool 缺')"

echo "== 2. 共享目录（~$USER_NAME/share） =="
cat >/etc/samba/smb.conf <<EOF
[global]
   workgroup = WORKGROUP
   server string = DSH share
   map to guest = Bad User
   server min protocol = SMB2
   disable netbios = yes

[share]
   path = $SHARE_DIR
   browseable = yes
   read only = no
   guest ok = yes
   create mask = 0664
   directory mask = 0775
EOF
systemctl enable --now smbd >/dev/null 2>&1
systemctl restart smbd >/dev/null 2>&1
sleep 1
echo "  smbd: $(systemctl is-active smbd)"
echo "  路径: $SHARE_DIR  文件数: $(ls -1 "$SHARE_DIR" 2>/dev/null | wc -l)"

echo "== 3. 安装 ~/share 里最新的 dsh-manager =="
LATEST="$(ls -1 "$SHARE_DIR"/dsh-manager_*_all.deb 2>/dev/null | sort -V | tail -n 1)"
if [ -n "${LATEST:-}" ]; then
    dpkg -i "$LATEST" >/dev/null 2>&1 || { apt-get install -y -f >/dev/null; dpkg -i "$LATEST" >/dev/null; }
    echo "  已装: $(dpkg-query -W -f='${Version}' dsh-manager 2>/dev/null)  ($LATEST)"
    echo "  提醒：装完请关掉管理器窗口再重新打开"
else
    echo "  ~/share 里没有 deb，跳过"
fi

echo "== 4. 版本自检 =="
echo "  spectacle: $(spectacle --version 2>/dev/null | head -n 1)"
echo "  convert  : $(convert --version 2>/dev/null | head -n 1)"
echo "  samba    : $(smbd --version 2>/dev/null | head -n 1)"
echo ""
echo "完成。Windows 上验证：cmd /c dir \\\\172.22.148.197\\share"
