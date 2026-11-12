#!/bin/bash
# Switch the VM's default graphical session back to GNOME (ubuntu.desktop) with sddm.
set -u
echo "=== before ==="
systemctl is-active sddm || true
sudo -n grep -h '^Session=' /etc/sddm.conf.d/*.conf /etc/sddm.conf 2>/dev/null || true
sudo -n cat /var/lib/sddm/state.conf 2>/dev/null | grep '^Session=' || true

echo "=== write sddm config (default session = ubuntu/GNOME, autologin on) ==="
sudo -n tee /etc/sddm.conf.d/60-gnome-default.conf >/dev/null <<'EOF'
[Autologin]
User=twinblade
Session=ubuntu
Relogin=true

[General]
Session=ubuntu
EOF
sudo -n tee /etc/sddm.conf.d/61-gnome-state.conf >/dev/null <<'EOF'
EOF
# state.conf 里记的是上次登录用的会话，sddm 会优先用它 → 直接改成 GNOME
sudo -n sed -i 's#^Session=.*#Session=/usr/share/wayland-sessions/ubuntu.desktop#' /var/lib/sddm/state.conf 2>/dev/null || true
grep -n '^Session=' /var/lib/sddm/state.conf 2>/dev/null || sudo -n grep -n '^Session=' /var/lib/sddm/state.conf || true

echo "=== restart sddm ==="
sudo -n systemctl restart sddm
sleep 12

echo "=== after ==="
systemctl is-active sddm || true
loginctl list-sessions --no-legend || true
for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do
  info=$(loginctl show-session "$s" -p Type -p Desktop -p Seat -p Active 2>/dev/null | tr '\n' ' ')
  echo "session $s: $info"
done
echo "--- gnome-shell ---"
pgrep -a gnome-shell | head -3 || echo '(no gnome-shell yet)'
echo "--- plasma 是否还在 ---"
pgrep -a plasmashell | head -3 || echo '(no plasmashell)'
