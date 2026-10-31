#!/bin/bash
# Find the real package names and check which of the wanted ones actually exist.
set -u
echo "== search spectacle"
apt-cache search 'spectacl' 2>/dev/null | head -10
echo "== policy kde-spectacle"
apt-cache policy kde-spectacle 2>/dev/null | head -4
echo "== section of plasma packages that look like screenshot tools"
apt-cache search 'screenshot' 2>/dev/null | head -15
echo "== existence check"
for p in samba samba-common-bin xdotool imagemagick python3-numpy python3-gi-cairo python3-pil grim wtype ydotool dbus-x11; do
  v=$(apt-cache policy "$p" 2>/dev/null | sed -n 's/^  候选：//p;s/^  Candidate: //p' | head -1)
  printf "  %-20s %s\n" "$p" "${v:-NOT FOUND}"
done
echo "== desktop env group size"
apt-cache search '^plasma-' 2>/dev/null | wc -l
echo "== is kde-spectacle in any suite"
grep -rl 'Package: kde-spectacle' /var/lib/apt/lists/*Packages 2>/dev/null | head -3
grep -rl 'Package: spectacle$' /var/lib/apt/lists/*Packages 2>/dev/null | head -3
