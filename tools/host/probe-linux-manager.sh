#!/bin/bash
# Probe the Linux manager install on the VM: package version, source location, running processes.
set -u
echo "=== host"
uname -a
hostname
echo
echo "=== dsh-manager package"
dpkg -l dsh-manager 2>/dev/null | tail -n +6
echo
echo "=== installed files"
if command -v dsh-manager >/dev/null 2>&1; then
  echo "bin: $(command -v dsh-manager)"
fi
ls -la /usr/lib/dsh-manager 2>/dev/null | head -40
echo
echo "=== source dirs"
ls -d ~/Program/* 2>/dev/null
find ~ -maxdepth 4 -type d -name dsh_manager 2>/dev/null | head -20
echo
echo "=== running processes"
ps -eo pid,etimes,cmd | grep -i -E "dsh-manager|dsh-desktop|python3 .*manager" | grep -v grep | head -20
echo
echo "=== displays"
echo "DISPLAY=$DISPLAY WAYLAND_DISPLAY=$WAYLAND_DISPLAY XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
who
