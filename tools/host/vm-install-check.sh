#!/bin/bash
set -u
sudo -n dpkg -i /tmp/dsh-manager.deb >/dev/null 2>&1 || true
echo -n "installed="; dpkg-query -W -f='${Version}\n' dsh-manager
echo -n "system_jsaction="; grep -c "startswith('js " /usr/lib/dsh-manager/share/dsh-desktop.py 2>/dev/null || echo 0
echo -n "system_loader="; grep -c "load_web_scripts" /usr/lib/dsh-manager/share/dsh-desktop.py 2>/dev/null || echo 0
