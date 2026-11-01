#!/bin/bash
# Compare the repo copy of dsh_manager with the live VM source (dsh-build) + installed copy.
set -u
echo "=== hashes"
for f in gui.py core.py plugins.py themes.json; do
  for d in /home/twinblade/dsh-build/linux/manager/dsh_manager \
           /usr/lib/dsh-manager/dsh_manager \
           /home/twinblade/dsh-dev/dsh_manager; do
    if [ -f "$d/$f" ]; then
      printf "%-28s %s  %s\n" "$f" "$(sha256sum "$d/$f" | cut -c1-16)" "$d"
    fi
  done
  echo
done
echo "=== version"
grep -rn -E "VERSION|__version__" /home/twinblade/dsh-build/linux/manager/dsh_manager/__init__.py /home/twinblade/dsh-build/linux/manager/dsh_manager/cli.py 2>/dev/null | head -10
echo
echo "=== sudo?"
sudo -n true 2>&1 && echo "sudo -n OK" || echo "sudo needs password"
echo
echo "=== manager package version + build script"
ls -la /home/twinblade/dsh-build/linux/manager/ | head -20
sed -n '1,40p' /home/twinblade/dsh-build/linux/manager/build-deb.sh 2>/dev/null
