#!/bin/bash
# 让虚拟机走本机代理：环境变量 + apt + git + GUI(systemd user env)
# 代理地址 = 宿主机的 Hyper-V 网卡 172.22.144.1:7891（本机中继 → 127.0.0.1:7890）
set -u
export HOME=/home/twinblade
PROXY="http://172.22.144.1:7891"
NO_PROXY="localhost,127.0.0.1,::1,172.22.144.1,172.22.148.197,.local"

echo '== 0. 先确认代理真的能用（不通就别写配置，免得把 apt/curl 弄坏）'
code=$(timeout 20 curl -s -o /dev/null -w '%{http_code}' -x "$PROXY" https://api.github.com 2>/dev/null)
echo "  proxy 探测: ${code:-失败}"
if [ "$code" != "200" ]; then
  echo '  代理不通，放弃写入配置。'
  exit 3
fi

echo '== 1. 环境变量（~/.config/dsh-proxy.env，.bashrc/.profile 里 source 它）'
mkdir -p "$HOME/.config"
cat > "$HOME/.config/dsh-proxy.env" <<EOF
# 本机代理中继（宿主机 Hyper-V 网卡 :7891 → 127.0.0.1:7890）
export http_proxy="$PROXY"
export https_proxy="$PROXY"
export HTTP_PROXY="$PROXY"
export HTTPS_PROXY="$PROXY"
export no_proxy="$NO_PROXY"
export NO_PROXY="$NO_PROXY"
EOF
chmod 600 "$HOME/.config/dsh-proxy.env"
for rc in "$HOME/.bashrc" "$HOME/.profile"; do
  [ -f "$rc" ] || : > "$rc"
  if ! grep -q 'dsh-proxy.env' "$rc"; then
    printf '\n# dsh：走本机代理（由 dsh-manager 写入，删掉这段即恢复直连）\n[ -f "$HOME/.config/dsh-proxy.env" ] && . "$HOME/.config/dsh-proxy.env"\n' >> "$rc"
    echo "  已写入 $rc"
  else
    echo "  $rc 里已有"
  fi
done

echo '== 2. apt'
sudo tee /etc/apt/apt.conf.d/95proxy >/dev/null <<EOF
// 由 dsh-manager 写入：走宿主机的代理中继
Acquire::http::Proxy "$PROXY";
Acquire::https::Proxy "$PROXY";
EOF
echo '  /etc/apt/apt.conf.d/95proxy 已写'

echo '== 3. git（全局）'
git config --global http.proxy "$PROXY"
git config --global https.proxy "$PROXY"
echo "  git http.proxy = $(git config --global --get http.proxy)"

echo '== 4. GUI 应用（Plasma/Wayland 从 systemd user session 继承环境）'
mkdir -p "$HOME/.config/environment.d"
cat > "$HOME/.config/environment.d/95-dsh-proxy.conf" <<EOF
http_proxy=$PROXY
https_proxy=$PROXY
HTTP_PROXY=$PROXY
HTTPS_PROXY=$PROXY
no_proxy=$NO_PROXY
NO_PROXY=$NO_PROXY
EOF
echo '  ~/.config/environment.d/95-dsh-proxy.conf 已写（下次登录生效）'

echo '== 5. 当前 systemd user 会话也导入一份（新起的进程立刻能用）'
systemctl --user set-environment http_proxy="$PROXY" https_proxy="$PROXY" \
  HTTP_PROXY="$PROXY" HTTPS_PROXY="$PROXY" no_proxy="$NO_PROXY" NO_PROXY="$NO_PROXY" 2>&1 \
  || systemctl --user import-environment http_proxy https_proxy 2>&1 || echo '  （systemd user 不可用，跳过）'

echo
echo '== 验证：新开一个 shell 里 curl / git / npm 是否都走代理'
bash -lc 'echo "  http_proxy=$http_proxy"; curl -s -o /dev/null -w "  curl github: %{http_code}\n" https://api.github.com; curl -s -o /dev/null -w "  curl raw: %{http_code}\n" https://raw.githubusercontent.com/cuteG41cute/dsh-memory-db/main/static/package.json'
echo "  apt 配置: $(grep -c Proxy /etc/apt/apt.conf.d/95proxy) 行"
