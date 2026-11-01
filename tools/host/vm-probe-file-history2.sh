#!/bin/bash
# file-history 还有哪些 0.2.x 相关问题，以及仓库最新版本
set -u
export HOME=/home/twinblade
export http_proxy=http://172.22.144.1:7891
export https_proxy=$http_proxy
F="$HOME/Program/deepseek-harness-1/dsh-home/profiles/web/node_modules/dsh-file-history"

echo '== A. 其它 0.2.x 接口用法'
grep -rn --include='*.js' -e 'session\.events' -e 'snapshotEvents' -e 'eventAt(' -e 'export const Config' -e 'ctx.settings.mutate' "$F/lib" 2>/dev/null | sed "s|$F/||" | head -12

echo
echo '== B. 是否有 Config 导出（0.2.x 走这个拿配置）'
grep -n "export const Config\|export const inject\|export function apply" "$F/lib/index.js" | head -5

echo
echo '== C. 客户端设置面板依赖的 RPC 字段'
grep -n "settings\." "$F/lib/client.js" | head -8
grep -n "getSettings\|currentSettings\|globalEnabled" "$F/lib/index.js" | head -8

echo
echo '== D. GitHub 最新版本'
echo -n '  release: '
curl -s -H 'User-Agent: dsh-manager' https://api.github.com/repos/cuteG41cute/dsh-file-history/releases/latest 2>/dev/null | grep -o '"tag_name": *"[^"]*"' | head -1
echo -n '  main 版本: '
curl -s -H 'User-Agent: dsh-manager' https://raw.githubusercontent.com/cuteG41cute/dsh-file-history/main/package.json 2>/dev/null | grep -o '"version": *"[^"]*"' | head -1
echo -n '  仓库 pushed_at: '
curl -s -H 'User-Agent: dsh-manager' https://api.github.com/repos/cuteG41cute/dsh-file-history 2>/dev/null | grep -o '"pushed_at": *"[^"]*"' | head -1
