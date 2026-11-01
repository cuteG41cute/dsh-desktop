#!/bin/bash
# 在虚拟机上把上传的 linux/ 目录打成 deb（本机 WSL 打不了：localhost 代理没镜像）。
set -e
DEV="$HOME/dsh-build"
rm -rf "$DEV"
mkdir -p "$DEV"
tar xzf /tmp/dsh-linux.tgz -C "$DEV"
ls "$DEV/linux" | head
cd "$DEV/linux/manager"
bash build-deb.sh
echo '== 产物'
ls -l "$DEV"/linux/manager/*.deb
sha256sum "$DEV"/linux/manager/*.deb
echo '== 包内 dsh-desktop.py'
dpkg-deb --contents "$DEV"/linux/manager/*.deb | grep -E 'dsh-desktop(\.py)?$|dsh_manager/core.py'
