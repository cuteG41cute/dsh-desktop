#!/usr/bin/env bash
# ============================================================================
# 虚拟机一次性修复（需要 sudo，跑一次即可）
#
#   · 装工具链：kde-spectacle（Ubuntu 26.04 里它就叫这个名，不叫 spectacle）、
#     imagemagick、xdotool、python3-numpy / python3-gi-cairo / python3-pil
#   · 装 Samba，把 ~/share 共享出来（可选；不装也能用 scp 传文件）
#   · 装 ~/share 里最新的 dsh-manager deb
#
# 用法：sudo bash ~/share/fix-vm-sudo.sh
#
# 2026-10-31 更正：上一版把包名写成 `spectacle`，Ubuntu 26.04 的 universe 里没有这个名字，
# apt 直接报 “无法定位软件包 spectacle” 并**整批中止**，于是 samba/imagemagick/xdotool 也一个没装。
# 现在改成：包名用 kde-spectacle，逐个安装、逐个报错，一个失败不影响其它。
# ============================================================================
set -u

[ "$(id -u)" = "0" ] || { echo "请用 sudo 运行：sudo bash $0"; exit 1; }

USER_NAME="${SUDO_USER:-twinblade}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
SHARE_DIR="$HOME_DIR/share"
mkdir -p "$SHARE_DIR"
chown "$USER_NAME:$USER_NAME" "$SHARE_DIR" 2>/dev/null || true

export DEBIAN_FRONTEND=noninteractive

echo "== 0. apt 索引 =="
apt-get update -qq || echo "  （apt update 有警告，继续）"

echo "== 1. 工具链（逐个装，失败只影响自己） =="
PKGS="kde-spectacle imagemagick xdotool python3-numpy python3-gi-cairo python3-pil"
FAILED=""
for p in $PKGS; do
    if dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed'; then
        echo "  [已装] $p"
        continue
    fi
    if apt-get install -y --no-install-recommends "$p" >/tmp/apt-$p.log 2>&1; then
        echo "  [装好] $p"
    else
        echo "  [失败] $p  —— 最后几行："
        tail -4 "/tmp/apt-$p.log" | sed 's/^/         /'
        FAILED="$FAILED $p"
    fi
done

echo "== 2. 自检 =="
printf "  %-16s %s\n" "spectacle" "$(command -v spectacle || echo '缺')"
printf "  %-16s %s\n" "convert"   "$(command -v convert || echo '缺')"
printf "  %-16s %s\n" "xdotool"   "$(command -v xdotool || echo '缺')"
printf "  %-16s %s\n" "smbd"      "$(command -v smbd || echo '缺')"
[ -n "$FAILED" ] && echo "  仍缺：$FAILED"

echo "== 3. Samba 共享（可选） =="
if command -v smbd >/dev/null 2>&1; then
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
    echo "  smbd: $(systemctl is-active smbd)   路径: $SHARE_DIR   文件数: $(ls -1 "$SHARE_DIR" 2>/dev/null | wc -l)"
else
    echo "  samba 没装上，跳过（用 scp 传文件即可：scp -P 22 文件 twinblade@<VM IP>:/home/twinblade/share/）"
fi

echo "== 4. 安装 ~/share 里最新的 dsh-manager =="
LATEST="$(ls -1 "$SHARE_DIR"/dsh-manager_*_all.deb 2>/dev/null | sort -V | tail -n 1)"
if [ -n "${LATEST:-}" ]; then
    echo "  候选：$LATEST"
    if dpkg -i "$LATEST" >/tmp/dpkg-manager.log 2>&1; then
        echo "  已装: $(dpkg-query -W -f='${Version}' dsh-manager 2>/dev/null)"
    else
        apt-get install -y -f >>/tmp/dpkg-manager.log 2>&1
        dpkg -i "$LATEST" >>/tmp/dpkg-manager.log 2>&1 && \
            echo "  已装（补依赖后）: $(dpkg-query -W -f='${Version}' dsh-manager 2>/dev/null)" || {
            echo "  安装失败，日志 /tmp/dpkg-manager.log："; tail -6 /tmp/dpkg-manager.log | sed 's/^/    /'; }
    fi
    echo "  提醒：装完把管理器窗口关掉再重新打开"
else
    echo "  ~/share 里没有 deb，跳过"
fi

echo ""
echo "完成。"
echo "  · Windows 共享盘（如果 samba 装上了）：cmd /c dir \\\\172.22.148.197\\share"
echo "  · 截图（不装 spectacle 也能拍）：python3 /tmp/vm-shot.py /tmp/a.png"
