#!/usr/bin/env bash
# ============================================================================
# 在浏览器里打开 dsh（网页端）
#
# 为什么不能直接敲 http://127.0.0.1:3080：
#   dsh ≥0.1.5 的 WebUI 要求认证，裸地址会回一张
#   "dsh web authentication required; reopen the URL printed by dsh web." 的页面。
#   正确的入口是 `dsh web` 启动时打印的那条带 token 的地址：
#       dsh web: http://127.0.0.1:3080/?token=xxxxx
#   打开它一次之后，服务端会种下认证 cookie，之后同一个浏览器直接敲裸地址也行。
#
# 本脚本干的事：从日志里翻出**最新**的那条带 token 的地址 → 验证它能用 →
# 交给系统浏览器打开（没有图形环境就只打印出来）。
#
# 用法：
#   bash open-web.sh            # 找地址、验证、并打开浏览器
#   bash open-web.sh --print    # 只打印地址（自己复制到手机/别的浏览器）
#   PREFIX=/path/to/instance bash open-web.sh
# ============================================================================
set -u

MODE="${1:-open}"
say() { printf '%s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---- 找实例前缀（与管理器同一套规则）----
PREFIX="${PREFIX:-}"
if [ -z "$PREFIX" ] && have python3; then
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
if [ -z "$PREFIX" ]; then
    for d in "$HOME/Program"/deepseek-harness* "$HOME/.local/opt"/deepseek-harness*; do
        [ -d "$d" ] && { PREFIX="$d"; break; }
    done
fi
[ -n "$PREFIX" ] || { say "找不到实例目录，用 PREFIX=/path 指定。"; exit 1; }

STATE="${XDG_STATE_HOME:-$HOME/.local/state}/dsh-desktop/logs"
CANDIDATES="
$PREFIX/logs/web.log
$PREFIX/logs/server.out.log
$PREFIX/logs/server.err.log
$PREFIX/logs/desktop.log
$STATE/web.log
$STATE/desktop.log
"

# ---- 取所有日志里最新的一条 ----
BEST_URL=""
BEST_TS=0
BEST_SRC=""
for f in $CANDIDATES; do
    [ -s "$f" ] || continue
    line="$(grep -o 'dsh web: https\?://[^[:space:]]*' "$f" 2>/dev/null | tail -n 1)"
    [ -n "$line" ] || continue
    url="${line#dsh web: }"
    ts="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
    if [ "$ts" -ge "$BEST_TS" ]; then
        BEST_TS="$ts"; BEST_URL="$url"; BEST_SRC="$f"
    fi
done

if [ -z "$BEST_URL" ]; then
    say "日志里没找到带 token 的地址。"
    say ""
    say "两个可能："
    say "  1) 服务不是用 'dsh web --no-open' 起的（比如桌面窗口启动器起的，日志在 $STATE）；"
    say "  2) 日志被清过。"
    say ""
    say "办法：在管理器里对实例点一次「停止服务」再「启动服务」，然后再跑本脚本。"
    say "或者直接看这两处有没有 'dsh web: http://...?token=' 这一行："
    say "  $PREFIX/logs/web.log"
    say "  $STATE/web.log"
    exit 1
fi

say "实例   : $PREFIX"
say "来源   : $BEST_SRC"
say "地址   : $BEST_URL"
say ""

# ---- 验证这条地址现在还能不能用 ----
status="$(python3 - "$BEST_URL" <<'PY' 2>/dev/null
import sys, urllib.request, urllib.error
url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=6) as r:
        print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception as e:
    print('err:%s' % type(e).__name__)
PY
)"

case "${status:-none}" in
    200) say "验证   : HTTP 200，可用" ;;
    none|'') say "验证   : 没有 python3，跳过验证（地址照样给你，打不开再说）" ;;
    401) say "验证   : HTTP 401 —— token 已失效（服务重启过）。"
         say "         在管理器里「停止服务 → 启动服务」拿一个新 token，再跑本脚本。"
         exit 1 ;;
    err:*) say "验证   : 连不上（${status#err:}）—— 服务可能没在跑。"
           say "         管理器里点「启动服务」。"
           exit 1 ;;
    *) say "验证   : HTTP ${status}（不常见，仍然把地址给你）" ;;
esac

if [ "$MODE" = "--print" ]; then
    say ""
    say "$BEST_URL"
    exit 0
fi

if have xdg-open; then
    say ""
    say "正在用系统默认浏览器打开…（如果没有自动打开，把上面那行地址复制到浏览器）"
    xdg-open "$BEST_URL" >/dev/null 2>&1 &
else
    say ""
    say "没有 xdg-open，请手动把这行地址复制到浏览器："
    say "$BEST_URL"
fi

say ""
say "说明：打开一次后服务端会种下认证 cookie，之后同一个浏览器直接敲"
say "      http://127.0.0.1:3080 也能进；换浏览器 / 清过 cookie 就要再来一次。"
say "注意：这条带 token 的地址等价于密码，别贴给别人。"
