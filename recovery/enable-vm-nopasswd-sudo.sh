#!/usr/bin/env bash
# ============================================================================
# 给 agent 开免密 sudo（可选，跑一次）。跑完我就能在虚拟机里：
#   · apt install（补 xdotool / spectacle / python3-gi-cairo 等）
#   · 直接改 /usr/lib/dsh-manager/ 下的已安装代码（不用每次走 ~/dsh-dev）
#   · systemctl 管实例服务
#
# 风险要说清楚：这等于把 VM 的 root 交给任何拿到 twinblade 账号的人。
# 只在"这是我自己的测试虚拟机"的前提下用；不想用了，删掉那个文件即恢复原状：
#   sudo rm /etc/sudoers.d/90-dsh-agent
#
# 用法（需要输一次密码）：
#   sudo bash ~/share/enable-vm-nopasswd-sudo.sh
#   然后验证：sudo -n true && echo "免密 sudo 已生效"
# ============================================================================
set -eu

[ "$(id -u)" = "0" ] || { echo "请用 sudo 运行：sudo bash $0"; exit 1; }

USER_NAME="${SUDO_USER:-twinblade}"
FILE=/etc/sudoers.d/90-dsh-agent

echo "== 写入 $FILE（用户 $USER_NAME）=="
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$USER_NAME" > "$FILE"
chmod 0440 "$FILE"

# 语法自检：写坏了 sudo 会整体失效，这里先验证再确认
if visudo -cf "$FILE" >/dev/null 2>&1; then
    echo "  语法 OK"
else
    echo "  语法错误，已撤销"
    rm -f "$FILE"
    exit 1
fi

echo "== 验证 =="
if sudo -n -u "$USER_NAME" true 2>/dev/null || true; then :; fi
su -s /bin/sh "$USER_NAME" -c 'sudo -n true' && echo "  免密 sudo 已生效" || echo "  未生效（检查 /etc/sudoers 里更早的规则是否覆盖）"

echo ""
echo "撤销：sudo rm $FILE"
