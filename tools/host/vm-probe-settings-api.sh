#!/bin/bash
# 0.2.1 的 settings 到底怎么“读”一个命名空间的值？以及 file-history 有没有新版
set -u
export HOME=/home/twinblade
export http_proxy=http://172.22.144.1:7891
export https_proxy=$http_proxy
A="$HOME/Program/deepseek-harness-1/app/node_modules/@deepseek-ai"

echo '== 1. dsh-settings 的完整类型声明'
sed -n '1,140p' "$A/dsh-settings/lib/types/index.d.ts"

echo
echo '== 2. 运行时实际暴露的方法（python 侧不重要，看 js 里的导出）'
grep -nE "^\s*(async )?(get|register|describe|update|replace|mutate|configure|prepareDocument)\b" "$A/dsh-settings/lib/index.js" | head -20

echo
echo '== 3. describe() 返回什么结构（SettingsDescriptor）'
grep -n -A20 'interface SettingsDescriptor\|type SettingsDescriptor' "$A/dsh-settings/lib/types/index.d.ts" | head -40

echo
echo '== 4. settings.yaml 里 file-history 段现在长什么样（插件没激活也可能有旧值）'
for f in "$HOME/.dsh/settings.yaml" "$HOME/Program/deepseek-harness-1/dsh-home/settings.yaml"; do
  [ -f "$f" ] && { echo "  --- $f"; grep -n -A12 'file-history' "$f" | head -20; }
done

echo
echo '== 5. GitHub 上 file-history 的最新 release / main 版本'
curl -s -H 'User-Agent: dsh-manager' https://api.github.com/repos/cuteG41cute/dsh-file-history/releases/latest 2>/dev/null | grep -E '"tag_name"' | head -2 || echo '  （无 release 或请求失败）'
curl -s -H 'User-Agent: dsh-manager' https://raw.githubusercontent.com/cuteG41cute/dsh-file-history/main/package.json 2>/dev/null | grep -E '"version"' | head -2 || echo '  （raw 取不到）'
