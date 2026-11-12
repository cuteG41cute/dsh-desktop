#!/bin/bash
set -u
echo "=== sddm 配置逐份看 ==="
for f in /etc/sddm.conf /etc/sddm.conf.d/*; do
  [ -f "$f" ] || continue
  echo "--- $f"
  sudo -n cat "$f" 2>/dev/null | grep -v '^#' | grep -v '^$'
done

echo "=== 写入 zz-gnome.conf（字母序最后，覆盖前面）==="
sudo -n tee /etc/sddm.conf.d/zz-gnome.conf >/dev/null <<'EOF'
[Autologin]
User=twinblade
Session=ubuntu
Relogin=true

[General]
Session=ubuntu
EOF

echo "=== 重启 sddm ==="
sudo -n systemctl restart sddm
sleep 15

echo "=== 会话 ==="
for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do
  echo "session $s: $(loginctl show-session "$s" -p Type -p Desktop -p Seat -p Active -p Name 2>/dev/null | tr '\n' ' ')"
done
echo "--- gnome-shell ---"
pgrep -a gnome-shell | head -3 || echo '(none)'
echo "--- plasmashell ---"
pgrep -a plasmashell | head -3 || echo '(none)'
echo "--- wayland/xorg ---"
pgrep -a Xwayland | head -2 || true
pgrep -a gnome-session-binary | head -2 || true
