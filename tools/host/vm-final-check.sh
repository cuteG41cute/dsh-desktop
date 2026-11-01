#!/bin/bash
# 收尾检查：没有测试进程残留；运行中的桌面窗口用的是修好的那份；版本号一致。
set -u
echo '== 残留进程'
pgrep -af 'http.server 80(98|99)|dsh-live/dsh-desktop' | grep -v pgrep || echo '  （干净）'
echo '== 桌面窗口'
pgrep -af 'dsh-desktop' | grep -v pgrep | head -5
echo '== 运行中的窗口脚本'
for f in "$HOME/Program/deepseek-harness-1/share/dsh-desktop.py" "$HOME/.local/opt/deepseek-harness-2/share/dsh-desktop.py" /usr/lib/dsh-manager/share/dsh-desktop.py; do
  [ -f "$f" ] && echo "$(stat -c%s "$f") bytes  popup=$(grep -c '__dshPopupClosed' "$f")  $f"
done
echo '== 版本'
grep -n "MANAGER_VERSION = " /usr/lib/dsh-manager/dsh_manager/core.py
dpkg -l dsh-manager 2>/dev/null | tail -1
echo '== Git'
cd "$HOME" 2>/dev/null
