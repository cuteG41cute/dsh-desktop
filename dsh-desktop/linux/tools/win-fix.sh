#!/usr/bin/env bash
# ============================================================================
# DeepSeek Harness 桌面窗口：现场取证 + 一键复原
#
# 现象（2026-10-30）：窗口上半部分是空白灰块，侧边栏和聊天被挤到下半部分；
# 管理器点「打开窗口」只会「把现有窗口提到前台」，于是坏窗口一直留着。
#
# 本脚本做三件事：
#   1. 取证：窗口进程 / 显卡 / 缩放 / 窗口几何 / 日志 / 控制套接字状态全部进报告，
#      并截一张图；
#   2. 无损尝试：先让现有窗口重绘（新版窗口支持 reload / repaint 命令时优先用它，
#      不支持就跳过），再截图；
#   3. 硬复原：只杀窗口进程（不动服务、不动会话），清掉单实例锁，重新起窗口，
#      等控制套接字应答后截第三张图。
#
# 用法：
#   bash win-fix.sh            # 取证 → 无损尝试 → 硬复原
#   bash win-fix.sh report     # 只取证，不动窗口
#   bash win-fix.sh reset      # 直接硬复原
#
# 报告与截图写到共享盘：$HOME/share/win-<时间戳>/（没有共享盘就写到 $HOME）
# ============================================================================
set -u

MODE="${1:-auto}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
BASE="${SHARE:-$HOME/share}"
[ -d "$BASE" ] || BASE="$HOME"
OUT="$BASE/win-$STAMP"
mkdir -p "$OUT" || { echo "无法创建输出目录 $OUT"; exit 1; }
REPORT="$OUT/report.txt"
: >"$REPORT"

say() { printf '%s\n' "$*" >>"$REPORT"; printf '%s\n' "$*"; }
sec() { say ""; say "===== $* ====="; }
have() { command -v "$1" >/dev/null 2>&1; }

# /dev/dri 存在不代表 GL 可用：虚拟机里常是 virtio_gpu，Mesa 会 ZINK/dri2 screen 失败
dri_driver() {
    local p
    for p in /sys/class/drm/card*/device/driver; do
        [ -e "$p" ] || continue
        basename "$(readlink -f "$p")"
        return 0
    done
    return 1
}

# ---------------------------------------------------------------- 截图（多后端）
# Wayland（KDE）下只有 spectacle / gnome-screenshot 这类走 portal 的工具能截；
# X11 的 import/scrot 在 Wayland 会话里通常截不到东西，所以放在后面。
shot() {
    local name="$1" f="$OUT/$1.png"
    rm -f "$f"
    if have spectacle; then
        spectacle -b -n -o "$f" >/dev/null 2>&1 || true
    elif have gnome-screenshot; then
        gnome-screenshot -f "$f" >/dev/null 2>&1 || true
    elif have grim; then
        grim "$f" >/dev/null 2>&1 || true
    elif have import; then
        import -window root "$f" >/dev/null 2>&1 || true
    elif have scrot; then
        scrot "$f" >/dev/null 2>&1 || true
    fi
    # KDE 自带 DBus 截图接口（Plasma 5 的写法，不需要装任何东西）
    if [ ! -s "$f" ] && have gdbus; then
        gdbus call --session --dest org.kde.KWin --object-path /Screenshot \
            --method org.kde.kwin.Screenshot.screenshotFullscreen "$f" >/dev/null 2>&1 || true
        sleep 1
    fi
    if [ -s "$f" ]; then
        say "[截图] $f"
    else
        say "[截图] $name 失败：这台机器没有可用的截图工具"
        say "        装一个就好（之后报告里就有图了）：sudo apt install -y spectacle"
    fi
}

# ---------------------------------------------------------------- 控制套接字
SOCK="${XDG_RUNTIME_DIR:-/tmp}/dsh-desktop-$(id -u).sock"
sock_cmd() {
    python3 - "$SOCK" "$1" <<'PY' 2>/dev/null
import socket, sys
path, cmd = sys.argv[1], sys.argv[2]
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2.0)
    s.connect(path)
    s.sendall((cmd + '\n').encode())
    print(s.recv(128).decode('utf-8', 'replace').strip())
    s.close()
except Exception:
    print('')
PY
}

# ---------------------------------------------------------------- 找实例前缀
find_prefix() {
    python3 - <<'PY' 2>/dev/null
import json, os
reg = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'),
                   'dsh-manager', 'instances.json')
try:
    with open(reg, 'r', encoding='utf-8') as fh:
        for entry in json.load(fh):
            p = entry.get('prefix') or ''
            if p and os.path.isdir(p):
                print(p)
                break
except Exception:
    pass
PY
}

PREFIX="${PREFIX:-$(find_prefix)}"
if [ -z "$PREFIX" ]; then
    for d in "$HOME/Program"/deepseek-harness* "$HOME/.local/opt"/deepseek-harness*; do
        [ -d "$d" ] && { PREFIX="$d"; break; }
    done
fi
DESKTOP="${PREFIX:+$PREFIX/bin/dsh-desktop}"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/dsh-desktop/logs"
MGR_LOG="$HOME/.config/dsh-manager/manager.log"

# ---------------------------------------------------------------- 1. 取证
sec "1. 现场"
say "时间      : $STAMP"
say "实例前缀  : ${PREFIX:-（没找到）}"
say "启动器    : ${DESKTOP:-（缺失）} $([ -n "$DESKTOP" ] && [ -x "$DESKTOP" ] && echo '(可执行)' || echo '(不可执行)')"
say "显示      : DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-}"
say "缩放      : GDK_SCALE=${GDK_SCALE:-unset} GDK_DPI_SCALE=${GDK_DPI_SCALE:-unset} QT_SCALE_FACTOR=${QT_SCALE_FACTOR:-unset}"
say "GPU       : /dev/dri $([ -e /dev/dri ] && echo 存在 || echo 不存在)  DRM 驱动=$(dri_driver 2>/dev/null || echo 未知)"
say "          （/dev/dri 存在 ≠ GL 可用：virtio_gpu 上 Mesa 常报 ZINK/dri2 screen 失败，"
say "            那种机器必须 DSH_DESKTOP_GL=off 走软件渲染）"

if have xrandr; then
    sec "1.1 分辨率与缩放（xrandr）"
    xrandr --current 2>/dev/null | grep -E '\*|connected' | head -n 6 | sed 's/^/    /' >>"$REPORT"
elif have xdpyinfo; then
    sec "1.1 显示（xdpyinfo）"
    xdpyinfo 2>/dev/null | grep -E 'dimensions|resolution' | sed 's/^/    /' >>"$REPORT"
fi

sec "1.2 进程"
ps -eo pid,ppid,etime,rss,%cpu,args 2>/dev/null \
    | grep -E 'dsh-desktop|WebKitWebProcess|WebKitNetworkProcess|dsh web|node .*web' \
    | grep -v grep | cut -c1-200 | sed 's/^/    /' >>"$REPORT"

WINPID="$(sock_cmd ping | awk '{print $2}')"
say "控制套接字: $SOCK"
say "窗口 PID  : ${WINPID:-（无应答）}"
if [ -n "$WINPID" ] && [ -r "/proc/$WINPID/environ" ]; then
    sec "1.3 窗口进程的环境（关键项）"
    tr '\0' '\n' <"/proc/$WINPID/environ" \
        | grep -E '^(WEBKIT|LIBGL|GALLIUM|GDK|DSH_DESKTOP|XDG_SESSION_TYPE|DISPLAY|WAYLAND)' \
        | sort | sed 's/^/    /' >>"$REPORT"
    say "命令      : $(tr '\0' ' ' <"/proc/$WINPID/cmdline" | cut -c1-160)"
    say "线程数    : $(ls "/proc/$WINPID/task" 2>/dev/null | wc -l)"
fi

if [ -n "$WINPID" ] && have xwininfo; then
    sec "1.4 窗口几何（xwininfo）"
    for wid in $(xwininfo -root -tree 2>/dev/null | grep -i 'deepseek' | awk '{print $1}'); do
        say "--- 窗口 $wid"
        xwininfo -id "$wid" 2>/dev/null \
            | grep -E 'Absolute|Width|Height|Map State|Override' | sed 's/^/    /' >>"$REPORT"
    done
elif have wmctrl; then
    sec "1.4 窗口列表（wmctrl）"
    wmctrl -lG 2>/dev/null | sed 's/^/    /' >>"$REPORT"
fi

sec "1.5 单实例锁"
for f in /tmp/dsh-desktop.lock /tmp/dsh-desktop.lock.pid; do
    [ -e "$f" ] && say "$f -> $(cat "$f" 2>/dev/null)"
done
[ -d /tmp/dsh-desktop.lock.d ] && say "/tmp/dsh-desktop.lock.d -> $(ls /tmp/dsh-desktop.lock.d 2>/dev/null | tr '\n' ' ')"

sec "1.6 控制套接字"
say "ping  : $(sock_cmd ping)"
say "raise : $(sock_cmd raise)"

sec "1.7 日志尾部"
for f in "$LOG_DIR/desktop.log" "$LOG_DIR/web.log" "$PREFIX/logs/desktop.log" "$PREFIX/logs/web.log" "$MGR_LOG"; do
    [ -s "$f" ] || continue
    say "--- $f（最后 25 行）"
    tail -n 25 "$f" | sed 's/^/    /' >>"$REPORT"
done

sec "1.8 已装的外部插件"
# 实例的 profile 在 <前缀>/dsh-home 里，不是 ~/.dsh（踩过：这里查错了目录，永远是空的）
for d in "${PREFIX:-/nonexistent}/dsh-home/profiles/web/node_modules" "$HOME"/.dsh/profiles/*/node_modules; do
    [ -d "$d" ] || continue
    say "--- $d"
    ls "$d" 2>/dev/null | grep -E '^dsh-' | sed 's/^/    /' >>"$REPORT"
    break
done

sec "1.9 截图（修复前）"
shot before

if [ "$MODE" = report ]; then
    sec "结论"
    say "只取证，没动窗口。报告：$REPORT"
    exit 0
fi

# ---------------------------------------------------------------- 2. 无损尝试
sec "2. 无损尝试：让现有窗口重绘"
R1="$(sock_cmd reload)"
R2="$(sock_cmd repaint)"
R3="$(sock_cmd raise)"
say "reload 命令应答 : ${R1:-（无应答）}"
say "repaint 命令应答: ${R2:-（无应答）}"
say "raise 命令应答  : ${R3:-（无应答）}"
if [ "$R1" = "unknown" ] || [ "$R2" = "unknown" ]; then
    say ""
    say "说明：这个窗口进程只认识旧的 ping/raise/quit（repaint/reload 回 unknown），"
    say "      说明它还是旧版程序。这种情况只能重开窗口 —— 下面第 3 步就是。"
    say "      重开后（新版程序）以后就能用「重载页面 / 重建窗口」按钮自救。"
fi
sleep 2
shot after-raise

# ---------------------------------------------------------------- 3. 硬复原
sec "3. 硬复原：关掉窗口进程，重新开一个干净的"
say "注意：窗口里还没发出去的输入会丢；会话内容在服务端，不会丢。"

mapfile -t PIDS < <(
    ps -eo pid,args 2>/dev/null | grep -E 'dsh-desktop(\.py)?( |$)' \
        | grep -v grep | awk -v p="$PREFIX" '{ if (p == "" || index($0, p) > 0) print $1 }'
)
if [ "${#PIDS[@]}" -gt 0 ]; then
    say "要结束的进程: ${PIDS[*]}"
    for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
    for _ in $(seq 1 20); do
        alive=0
        for pid in "${PIDS[@]}"; do [ -e "/proc/$pid" ] && alive=1; done
        [ "$alive" = 0 ] && break
        sleep 0.25
    done
    for pid in "${PIDS[@]}"; do
        [ -e "/proc/$pid" ] && { say "强制结束 $pid"; kill -9 "$pid" 2>/dev/null || true; }
    done
else
    say "没有发现窗口进程（可能已经不在）"
fi

rm -f /tmp/dsh-desktop.lock /tmp/dsh-desktop.lock.pid 2>/dev/null
rm -rf /tmp/dsh-desktop.lock.d 2>/dev/null
rm -f "$SOCK" 2>/dev/null
say "已清理 /tmp/dsh-desktop.lock* 与 $SOCK"

if [ -z "$DESKTOP" ] || [ ! -x "$DESKTOP" ]; then
    say "错误：找不到可执行的启动器 ${DESKTOP:-（前缀没找到）}"
    exit 1
fi
NEW_LOG="$OUT/desktop-restart.log"
say "启动: DSH_DESKTOP_FORCE=1 DSH_DESKTOP_GL=off $DESKTOP"
if have setsid; then
    ( DSH_DESKTOP_FORCE=1 DSH_DESKTOP_GL=off setsid "$DESKTOP" >"$NEW_LOG" 2>&1 & ) || true
else
    ( DSH_DESKTOP_FORCE=1 DSH_DESKTOP_GL=off nohup "$DESKTOP" >"$NEW_LOG" 2>&1 & ) || true
fi

ok=0
for _ in $(seq 1 60); do
    if [ -n "$(sock_cmd ping | awk '{print $2}')" ]; then ok=1; break; fi
    sleep 0.5
done
say "控制套接字: $(sock_cmd ping)"
if [ "$ok" = 1 ]; then say "窗口进程已就绪"; else say "窗口进程没起来，日志见 $NEW_LOG"; fi
sleep 4
shot after-restart

sec "结论"
say "报告目录: $OUT"
say "  report.txt            现场 + 日志尾部"
say "  before.png            修复前"
say "  after-raise.png       无损尝试后"
say "  after-restart.png     重开窗口后"
say "  desktop-restart.log   本次启动日志"
say ""
if [ -s "$OUT/after-restart.png" ]; then
    say "把 win-$STAMP 整个目录（或 before / after-restart 两张图）发我，我按图定位。"
else
    say "没截到图，请把 desktop-restart.log 发我。"
fi
