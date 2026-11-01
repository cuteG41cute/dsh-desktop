#!/bin/bash
# Which copy of dsh_manager is the live source of truth? Compare versions and sizes.
set -u
for d in /usr/lib/dsh-manager/dsh_manager \
         /home/twinblade/dsh-build/linux/manager/dsh_manager \
         /home/twinblade/dsh-dev/dsh_manager; do
  echo "=== $d"
  if [ -d "$d" ]; then
    ls -la "$d" | head -20
    echo "--- version strings"
    grep -rh -m3 -E "VERSION *=|__version__|1\.[0-9]+\.[0-9]+" "$d"/__init__.py "$d"/cli.py 2>/dev/null | head -6
    echo "--- git?"
    if [ -d "$d/../.git" ] || [ -d "$d/../../.git" ]; then
      ( cd "$d" && git log --oneline -3 2>/dev/null; git status --short 2>/dev/null | head -10 )
    else
      echo "no git here"
    fi
  else
    echo "missing"
  fi
  echo
done
echo "=== sizes of gui.py/core.py/plugins.py/themes.json (all copies)"
find /usr/lib/dsh-manager /home/twinblade/dsh-build /home/twinblade/dsh-dev -maxdepth 5 -name gui.py -o -maxdepth 5 -name core.py -o -maxdepth 5 -name plugins.py -o -maxdepth 5 -name themes.json 2>/dev/null \
  | xargs -r ls -la 2>/dev/null
echo
echo "=== what the running manager uses"
ps -o cmd= -p 181800
cat /usr/bin/dsh-manager 2>/dev/null | head -20
