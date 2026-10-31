#!/bin/bash
# Why did the package install do nothing? Diagnose apt reachability without root.
set -u
echo "== sudo state"
sudo -n true 2>/dev/null && echo "  passwordless sudo: YES" || echo "  passwordless sudo: NO (needs password)"

echo "== already installed?"
for p in spectacle imagemagick samba xdotool python3-gi-cairo xdotool wtype ydotool; do
  printf "  %-16s %s\n" "$p" "$(dpkg-query -W -f='${Status} ${Version}' "$p" 2>/dev/null || echo 'not installed')"
done

echo "== apt sources"
ls /etc/apt/sources.list.d/ 2>/dev/null
grep -hE '^(deb|URIs|Suites)' /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list 2>/dev/null | head -20

echo "== proxy config"
env | grep -iE 'proxy' || echo "  no proxy env"
grep -rhi proxy /etc/apt/apt.conf.d/ 2>/dev/null | head -5 || true

echo "== candidate versions (simulation, no root needed)"
apt-cache policy spectacle imagemagick xdotool 2>/dev/null | head -30

echo "== simulate install"
timeout 60 apt-get -s install -y --no-install-recommends spectacle xdotool 2>&1 | tail -8

echo "== network reachability"
for u in http://archive.ubuntu.com/ubuntu/ http://cn.archive.ubuntu.com/ubuntu/ https://mirrors.aliyun.com/ubuntu/ https://mirrors.tuna.tsinghua.edu.cn/ubuntu/; do
  code=$(timeout 12 curl -s -o /dev/null -w '%{http_code}' -I "$u" 2>/dev/null)
  echo "  $u -> ${code:-fail}"
done
echo "== dns"
getent hosts archive.ubuntu.com | head -2 || echo "  no A record"
echo "== apt lists age"
ls -l /var/lib/apt/lists/*Release 2>/dev/null | head -3 || echo "  no lists (apt-get update never succeeded)"
