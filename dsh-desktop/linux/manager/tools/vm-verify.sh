#!/usr/bin/env bash
# ============================================================================
# 虚拟机侧一键自检：跑全部 gate、构建 deb、打印 sha256。
#
# 布局假设（与本包一致）：
#   <包根>/project/dsh-desktop/linux/{dsh-desktop, dsh-desktop.py, manager/, tools/}
#
# 用法：
#   bash tools/vm-verify.sh              # 跑 gate + 构建 deb
#   bash tools/vm-verify.sh --no-build   # 只跑 gate
#
# 任何一项红了都会以非零退出；完整输出写进 tools/vm-verify.log
# ============================================================================
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="$ROOT/project"
LOG="$ROOT/tools/vm-verify.log"
: >"$LOG"

say() { printf '%s\n' "$*" | tee -a "$LOG"; }
fail=0

run() {  # $1 = 名字, 其余 = 命令（在 $PROJ 下执行）
    local name="$1"; shift
    local out
    if out="$( cd "$PROJ" && "$@" 2>&1 )"; then
        say "  OK   $name  $(printf '%s' "$out" | grep -E 'RESULT|OK:' | tail -n 1)"
    else
        say "  FAIL $name"
        printf '%s\n' "$out" | tail -n 25 | sed 's/^/         /' | tee -a "$LOG" >/dev/null
        printf '%s\n' "$out" | tail -n 6 | sed 's/^/         /'
        fail=1
    fi
}

say "== 1. 编译 / 导入 / 主题 / 协议 =="
run "py_compile"            python3 -m py_compile \
                                dsh-desktop/linux/dsh-desktop.py \
                                dsh-desktop/linux/manager/dsh_manager/core.py \
                                dsh-desktop/linux/manager/dsh_manager/gui.py \
                                dsh-desktop/linux/manager/dsh_manager/cli.py
run "gi-scope"              python3 dsh-desktop/linux/tools/gi-scope-check.py
run "gui-import-check"      python3 dsh-desktop/linux/manager/tools/gui-import-check.py \
                                dsh-desktop/linux/manager/dsh_manager
run "theme-token-check"     python3 dsh-desktop/linux/manager/tools/theme-token-check.py
run "ctl-protocol-check"    python3 dsh-desktop/linux/manager/tools/ctl-protocol-check.py
run "token-extract-check"   python3 dsh-desktop/linux/manager/tools/token-extract-check.py
run "screenshot-bridge"     python3 dsh-desktop/linux/tools/screenshot-bridge-check.py
run "socket-name-check"     python3 dsh-desktop/linux/tools/socket-name-check.py
run "gl-detect-check"       python3 dsh-desktop/linux/tools/gl-detect-check.py

say ""
say "== 2. 构建 deb =="
if [ "${1:-}" = "--no-build" ]; then
    say "  （按参数跳过构建）"
else
    if out="$( cd "$PROJ/dsh-desktop/linux/manager" && bash build-deb.sh 2>&1 )"; then
        deb="$(ls -1t "$PROJ"/dsh-desktop/linux/manager/dsh-manager_*_all.deb 2>/dev/null | head -n 1)"
        if [ -n "${deb:-}" ]; then
            say "  deb：$deb"
            say "  大小：$(stat -c %s "$deb") 字节"
            say "  sha256：$(sha256sum "$deb" | awk '{print $1}')"
            say "  包内主题/背景文件数：$(dpkg-deb --fsys-tarfile "$deb" | tar -t | grep -cE 'theme/.*\.css|backgrounds/.*\.png')"
        else
            say "  FAIL 没找到构建产物"; fail=1
        fi
    else
        say "  FAIL 构建失败"
        printf '%s\n' "$out" | tail -n 20 | sed 's/^/         /'
        fail=1
    fi
fi

say ""
if [ "$fail" = 0 ]; then say "RESULT: PASS（完整输出：$LOG）"; else say "RESULT: FAIL（完整输出：$LOG）"; fi
exit "$fail"
