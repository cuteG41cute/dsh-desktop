#!/bin/bash
# Linux VM 环境盘点（给 Windows 宿主用 SSH 跑）
echo "=== os ==="
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"
echo "=== kernel ==="
uname -sr
echo "=== gtk ==="
python3 - <<'PY' 2>&1 | tail -3
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    print('gtk', Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())
except Exception as exc:
    print('gtk FAIL', exc)
PY
echo "=== webkit ==="
python3 - <<'PY' 2>&1 | tail -3
for ver in ('4.1', '4.0'):
    try:
        import gi
        gi.require_version('WebKit2', ver)
        from gi.repository import WebKit2
        print('webkit2 ' + ver + ' ok')
        break
    except Exception as exc:
        print('webkit2 ' + ver + ' FAIL ' + str(exc))
PY
echo "=== manager ==="
dpkg-query -W -f='${Version}\n' dsh-manager 2>/dev/null || echo "(not installed)"
command -v dsh-manager || true
echo "=== tools ==="
for t in xdotool spectacle grim import convert python3-pil; do
  command -v "$t" >/dev/null 2>&1 && echo "$t: present" || echo "$t: missing"
done
python3 -c 'import PIL; print("pillow", PIL.__version__)' 2>/dev/null || echo "pillow: missing"
echo "=== session ==="
echo "DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-} WAYLAND_SOCKET=${WAYLAND_SOCKET:-}"
ls -l /tmp/.X11-unix 2>/dev/null | head -3
loginctl list-sessions --no-legend 2>/dev/null | head -3
echo "=== running manager ==="
pgrep -a -f 'dsh-manager' | head -3 || echo "(no dsh-manager process)"
echo "=== sudo ==="
sudo -n true 2>/dev/null && echo "sudo-nopasswd: yes" || echo "sudo-nopasswd: no"
echo "=== share dir ==="
ls -d ~/share 2>/dev/null || echo "(no ~/share)"
