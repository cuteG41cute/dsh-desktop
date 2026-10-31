#!/bin/bash
# Prove the corrected package list resolves (simulation only, needs no root).
set -u
LIST="kde-spectacle imagemagick samba xdotool python3-numpy python3-gi-cairo python3-pil"
echo "== simulate: $LIST"
timeout 120 apt-get -s install -y --no-install-recommends $LIST 2>&1 | tail -12
echo
echo "== how big"
timeout 120 apt-get -s install -y --no-install-recommends $LIST 2>&1 | grep -E '^(Inst|要安装|升级)' | wc -l
echo "== disk free"
df -h / | tail -1
