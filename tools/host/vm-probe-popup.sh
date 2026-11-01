#!/bin/bash
# 搭一个最小页面 + 最小 WebKit 宿主，验证 window.open / opener=null / location.replace。
set -u
DIR=/tmp/dsh-probe
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
unset DISPLAY GDK_BACKEND

command -v kscreen-doctor >/dev/null && kscreen-doctor --dpms on >/dev/null 2>&1
pkill -f 'http.server 8098' 2>/dev/null
pkill -f 'vm-popup-probe.py' 2>/dev/null
sleep 1
rm -rf "$DIR"; mkdir -p "$DIR"

cat > "$DIR/index.html" <<'HTML'
<!doctype html><meta charset="utf-8"><title>PROBE-MAIN</title>
<body style="font:18px monospace;background:#eef;padding:20px">
<h3>最小复现：window.open(about:blank) 后再 location.replace</h3>
<pre id="log"></pre>
<script>
const out = (m) => {
  document.getElementById('log').textContent += m + "\n";
  console.log('PAGE ' + m);
  document.title = 'PROBE ' + m;
};
window.addEventListener('load', () => {
  setTimeout(() => {
    let p = null;
    try { p = window.open('about:blank', '_blank'); } catch (e) { out('open 抛错: ' + e); }
    out('open(about:blank) -> ' + (p ? 'OK' : 'NULL(被拦)'));
    if (p) {
      try { p.opener = null; out('opener=null 成功'); } catch (e) { out('opener=null 抛错: ' + e); }
      setTimeout(() => {
        try { out('closed=' + p.closed); } catch (e) { out('读 closed 抛错: ' + e); }
        try { p.location.replace('http://127.0.0.1:8098/land.html?from=replace'); out('location.replace 成功'); }
        catch (e) { out('location.replace 抛错: ' + e); }
        setTimeout(() => { try { out('2 秒后 closed=' + p.closed); } catch (e) { out('再读 closed 抛错: ' + e); } }, 2000);
      }, 1200);
    }
  }, 800);
});
</script>
</body>
HTML

cat > "$DIR/land.html" <<'HTML'
<!doctype html><meta charset="utf-8"><title>LANDING-OK</title>
<body style="font:30px sans-serif;background:#0b3;color:#003;padding:40px">
LANDING OK <span id="q"></span>
<script>document.getElementById('q').textContent = location.search; console.log('LANDING ' + location.search);</script>
</body>
HTML

cd "$DIR" && setsid nohup python3 -m http.server 8098 --bind 127.0.0.1 >/tmp/dsh-probe-http.log 2>&1 &
sleep 1
curl -s -o /dev/null -w 'http: %{http_code}\n' http://127.0.0.1:8098/index.html

LIBGL_ALWAYS_SOFTWARE=1 setsid nohup python3 -u /tmp/vm-popup-probe.py >/tmp/vm-popup-probe.log 2>&1 &
sleep 8
python3 /tmp/vm-shot.py /tmp/probe-1.png 2>&1 | tail -2
sleep 5
echo '== log'
cat /tmp/vm-popup-probe.log
pkill -f 'vm-popup-probe.py' 2>/dev/null
pkill -f 'http.server 8098' 2>/dev/null
echo '== done'
