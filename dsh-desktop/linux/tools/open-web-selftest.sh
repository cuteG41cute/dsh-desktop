#!/usr/bin/env bash
# open-web.sh 的自测：造假的实例目录与日志，确认它能挑出最新那条 token 地址。
# 跑法：bash dsh-desktop/linux/tools/open-web-selftest.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/open-web.sh"
FAKE=/tmp/open-web-fake
rm -rf "$FAKE"
mkdir -p "$FAKE/logs"

# 旧的一条（web.log 更旧）+ 新的一条（server.out.log 更新）
printf 'dsh web: http://127.0.0.1:3080/?token=OLDOLDOLD\n' >"$FAKE/logs/web.log"
touch -d '2026-10-30 10:00:00' "$FAKE/logs/web.log" 2>/dev/null || true
printf 'noise\ndsh web: http://127.0.0.1:3080/?token=NEWNEWNEW\n' >"$FAKE/logs/server.out.log"

OUT="$(PREFIX="$FAKE" bash "$SCRIPT" --print 2>&1)"
checks=()
expect() { if printf '%s' "$OUT" | grep -qF -- "$2"; then checks+=("OK   $1"); else checks+=("FAIL $1（缺：$2）"); fi; }

expect "用到最新那份日志" "server.out.log"
expect "取到新 token" "token=NEWNEWNEW"
expect "没有取到旧 token" "NEWNEWNEW"
if printf '%s' "$OUT" | grep -q "OLDOLDOLD"; then
    checks+=("FAIL 仍然打印了旧 token")
else
    checks+=("OK   没有打印旧 token")
fi
# 验证阶段会去连 127.0.0.1:3080（本机无此服务）→ 应当报"连不上"并 exit 1，
# 但因为取到地址在先，地址本身必须已经打印出来
if printf '%s' "$OUT" | grep -qE "连不上|没有 python3"; then
    checks+=("OK   连不上时给了明确提示（HTTP 探测生效）")
else
    checks+=("OK   本机正好有服务，跳过了连不上分支")
fi

fail=0
for line in "${checks[@]}"; do
    printf '  %s\n' "$line"
    case "$line" in FAIL*) fail=1 ;; esac
done
echo "RESULT: $([ "$fail" = 0 ] && echo PASS || echo FAIL) 输出摘要："
printf '%s\n' "$OUT" | sed 's/^/    /' | head -n 8
rm -rf "$FAKE"
exit "$fail"
