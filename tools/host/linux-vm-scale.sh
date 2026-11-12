#!/bin/bash
# Persist a 200% scale for the Hyper-V virtual display, then restart the session.
set -u
HOME_DIR=/home/twinblade
CFG=$HOME_DIR/.config/monitors.xml
mkdir -p "$HOME_DIR/.config"
cat > "$CFG" <<'EOF'
<monitors version="2">
  <configuration>
    <logicalmonitor>
      <x>0</x>
      <y>0</y>
      <scale>2</scale>
      <primary>yes</primary>
      <monitor>
        <monitorspec>
          <connector>Virtual-1</connector>
          <vendor>unknown</vendor>
          <product>unknown</product>
          <serial>unknown</serial>
        </monitorspec>
        <mode>
          <width>1920</width>
          <height>1080</height>
          <rate>60.000</rate>
        </mode>
      </monitor>
    </logicalmonitor>
  </configuration>
</monitors>
EOF
chown twinblade:twinblade "$CFG"
echo "=== monitors.xml 写入完成 ==="
cat "$CFG"

echo "=== 重启 sddm ==="
sudo -n systemctl restart sddm
sleep 22

echo "=== 会话 ==="
for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do
  echo "session $s: $(loginctl show-session "$s" -p Type -p Desktop -p Active 2>/dev/null | tr '\n' ' ')"
done
echo "=== gnome-shell ==="
pgrep -af 'gnome-shell --mode' | head -2 || echo '(none)'

echo "=== 回读 scale ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
gdbus call --session --dest org.gnome.Mutter.DisplayConfig \
  --object-path /org/gnome/Mutter/DisplayConfig \
  --method org.gnome.Mutter.DisplayConfig.GetCurrentState 2>/dev/null \
  | tr ',' '\n' | grep -m3 '1920x1080' || echo '(no reply)'
