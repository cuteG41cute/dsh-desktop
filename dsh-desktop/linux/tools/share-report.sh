#!/usr/bin/env bash
# ============================================================================
# 两件事一起查：
#   A. win-fix.sh 已经跑成功了，但它在 ~/share 里建的 win-<时间戳>/ 在 Windows
#      那边的「share」里看不到 —— 到底是"没写进共享目录"还是"写进去了但 SMB 端
#      看不见"（权限 / samba 配置 / 根本不是同一个目录）。
#   B. 装了 1.1.3 却"没有用" —— 到底装上了没有、实例里跑的窗口程序是不是新版、
#      新旧版本的按钮各自回了什么。
#
# 结果同时写到 ~/share/share-report.txt（共享目录根下的普通文件，那边能看见）。
# 只需要：bash share-report.sh
# ============================================================================
set -u

S="${SHARE:-$HOME/share}"
R="$S/share-report.txt"
: >"$R" 2>/dev/null || R="$HOME/share-report.txt"
say() { printf '%s\n' "$*" | tee -a "$R"; }
sec() { say ""; say "===== $* ====="; }
have() { command -v "$1" >/dev/null 2>&1; }

sec "0. 我是谁 / 共享目录在哪"
say "时间   : $(date '+%Y-%m-%d %H:%M:%S %Z')"
say "用户   : $(id)"
say "umask  : $(umask)"
say "HOME   : $HOME"
say "S      : $S  $([ -d "$S" ] && echo '(存在)' || echo '(不存在)')"
stat -c '  %A %U:%G %n' "$S" 2>/dev/null | tee -a "$R" >/dev/null
say "挂载点 : $(findmnt -n -o TARGET,SOURCE,FSTYPE -T "$S" 2>/dev/null || echo '（findmnt 不可用）')"
say "所在盘 : $(df -h "$S" 2>/dev/null | tail -n 1)"

sec "1. win-* 目录到底在哪"
for d in "$S"/win-*; do
    [ -e "$d" ] || continue
    say "--- $d"
    stat -c '  %A %U:%G  %n' "$d" 2>/dev/null | tee -a "$R" >/dev/null
    ls -la "$d" 2>/dev/null | sed 's/^/    /' >>"$R"
done
say ""
say "整机搜索（前 10 个）："
find "$HOME" -maxdepth 4 -type d -name 'win-2*' 2>/dev/null | head -n 10 | sed 's/^/    /' >>"$R"
say "$(find "$HOME" -maxdepth 4 -type d -name 'win-2*' 2>/dev/null | head -n 10 | tr '\n' ' ')"

sec "2. 共享目录根能不能被 SMB 端读到"
say "根目录条目数 : $(ls -1 "$S" 2>/dev/null | wc -l)"
ls -la "$S" 2>/dev/null | head -n 30 | sed 's/^/    /' >>"$R"

sec "3. 修权限（让 SMB 端一定能读）"
if compgen -G "$S/win-*" >/dev/null 2>&1; then
    chmod 755 "$S" 2>/dev/null
    chmod -R a+rX "$S"/win-* 2>/dev/null
    say "已执行: chmod 755 $S; chmod -R a+rX $S/win-*"
    for d in "$S"/win-*; do
        stat -c '  现在: %A %U:%G  %n' "$d" 2>/dev/null | tee -a "$R" >/dev/null
    done
else
    say "没有匹配到 $S/win-*，跳过 chmod"
fi

sec "4. samba 配置（决定"看不看得见"）"
if have testparm; then
    testparm -s 2>/dev/null | sed -n '/^\[share\]/,/^\[/p' | sed 's/^/    /' >>"$R"
else
    say "（没有 testparm）"
fi
for k in 'hide unreadable' 'force user' 'force group' 'read only' 'create mask' 'directory mask' 'guest ok' 'valid users' 'browseable'; do
    grep -hE "^\s*$k" /etc/samba/smb.conf 2>/dev/null | sed 's/^/    /' >>"$R"
done
say "smbd: $(systemctl is-active smbd 2>/dev/null || echo '未知')"

sec "5. 1.1.3 装上了吗"
say "dpkg 版本 : $(dpkg-query -W -f='${Version}' dsh-manager 2>/dev/null || echo '（没装）')"
say "CLI 版本  : $(dsh-manager --version 2>&1 | head -n 2 | tr '\n' ' ')"
say "deb 列表  : $(dpkg -L dsh-manager 2>/dev/null | grep -E 'dsh_manager/(core|gui)\.py' | tr '\n' ' ')"

sec "6. 实例里的窗口程序是新版还是旧版"
PREFIX=""
if have python3; then
    PREFIX="$(python3 - <<'PY' 2>/dev/null
import json, os
reg = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'),
                   'dsh-manager', 'instances.json')
try:
    for entry in json.load(open(reg, encoding='utf-8')):
        p = entry.get('prefix') or ''
        if p and os.path.isdir(p):
            print(p); break
except Exception:
    pass
PY
)"
fi
[ -n "$PREFIX" ] || for d in "$HOME/Program"/deepseek-harness*; do [ -d "$d" ] && { PREFIX="$d"; break; }; done
say "实例     : ${PREFIX:-（没找到）}"
for f in "$PREFIX/share/dsh-desktop.py" "$PREFIX/bin/dsh-desktop.py" "$PREFIX/bin/dsh-desktop" \
         /usr/lib/dsh-manager/share/dsh-desktop.py; do
    [ -f "$f" ] || continue
    say "--- $f"
    stat -c '  大小 %s  修改 %y' "$f" | tee -a "$R" >/dev/null
    say "  repaint 出现次数: $(grep -c 'repaint' "$f" 2>/dev/null)"
    say "  reload  出现次数: $(grep -c 'reload' "$f" 2>/dev/null)"
done

sec "7. 控制套接字现在怎么答"
SOCK="${XDG_RUNTIME_DIR:-/tmp}/dsh-desktop-$(id -u).sock"
for cmd in ping raise repaint reload; do
    out="$(python3 - "$SOCK" "$cmd" <<'PY' 2>/dev/null
import socket, sys
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2.0); s.connect(sys.argv[1])
    s.sendall((sys.argv[2] + '\n').encode())
    print(s.recv(128).decode('utf-8', 'replace').strip())
    s.close()
except Exception:
    print('')
PY
)"
    say "$cmd → ${out:-（无应答）}"
done

sec "8. 管理器日志尾部"
for f in "$HOME/.config/dsh-manager/manager.log"; do
    [ -s "$f" ] || continue
    say "--- $f"
    tail -n 30 "$f" | sed 's/^/    /' >>"$R"
done

sec "9. 相关进程"
ps -eo pid,etime,args 2>/dev/null \
    | grep -E 'dsh-desktop|WebKitWebProcess|bin\.js web' | grep -v grep \
    | cut -c1-150 | sed 's/^/    /' >>"$R"

sec "完成"
say "报告：$R"
say "下一步：在 Windows 上执行  cmd /c dir \\\\172.22.148.197\\share  ，看 win-* 目录是否出现。"
