#!/bin/bash
# Load and run a KWin scripting API script (KWin 6 / Plasma 6).
#   vm-kwin-script.sh /path/to/script.js
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
JS="${1:?usage: vm-kwin-script.sh script.js}"

ID=$(gdbus call --session --dest org.kde.KWin --object-path /Scripting \
      --method org.kde.kwin.Scripting.loadScript "$JS" 2>&1)
echo "loadScript -> $ID"
NUM=$(echo "$ID" | grep -oE '[0-9]+' | head -1)
if [ -z "${NUM:-}" ]; then
  echo "could not parse script id"
  exit 1
fi
gdbus call --session --dest org.kde.KWin --object-path "/Scripting/Script$NUM" \
  --method org.kde.kwin.Script.run 2>&1
sleep 1
gdbus call --session --dest org.kde.KWin --object-path "/Scripting/Script$NUM" \
  --method org.kde.kwin.Script.stop 2>&1
echo "--- script output (journal not used; check kwin log if needed) ---"
