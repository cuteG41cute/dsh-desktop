#!/bin/bash
# Attach to the running KDE session bus and see which screenshot paths work.
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export DISPLAY=:1
export WAYLAND_DISPLAY=wayland-0
export XAUTHORITY=/run/user/1000/xauth_KYiEIz

echo "== python modules"
python3 - <<'PY'
for m in ("gi", "dbus", "PIL", "cairo"):
    try:
        __import__(m)
        print(m, "OK")
    except Exception as e:
        print(m, "MISSING", type(e).__name__)
PY

echo "== portal packages"
dpkg -l 2>/dev/null | grep -E 'xdg-desktop-portal' | awk '{print $2, $3}' | head -10
echo "== portal services on bus"
gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
  --method org.freedesktop.DBus.ListNames 2>&1 | tr ',' '\n' | grep -E 'portal|KWin' | head -10

echo "== try portal Screenshot (interactive=false)"
timeout 40 gdbus call --session \
  --dest org.freedesktop.portal.Desktop \
  --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Screenshot.Screenshot \
  "" '{"interactive": <false>, "modal": <false>}' 2>&1 | head -5
