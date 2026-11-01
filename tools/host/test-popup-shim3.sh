#!/bin/bash
# 只开一个内置窗口：先看窗口长相，再 raise 主窗口看页面里的日志。
set -u
DIR=/tmp/dsh-popup3
LOG=/tmp/dsh-shim-test.log
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
unset DISPLAY GDK_BACKEND

command -v kscreen-doctor >/dev/null && kscreen-doctor --dpms on >/dev/null 2>&1
pkill -f 'dsh-test/dsh-desktop.py' 2>/dev/null
pkill -f 'http.server 8099' 2>/dev/null
sleep 1
rm -rf "$DIR"; mkdir -p "$DIR"

cat > "$DIR/land.html" <<'HTML'
<!doctype html><meta charset="utf-8"><title>LANDING-OK</title>
<body style="font:30px sans-serif;background:#0b3;color:#003;padding:40px">
LANDING OK <span id="q"></span>
<script>document.getElementById('q').textContent = location.search;</script>
</body>
HTML

cat > "$DIR/index.html" <<'HTML'
<!doctype html><meta charset="utf-8"><title>SHIM-TEST-MAIN</title>
<body style="font:17px monospace;background:#eef;padding:16px">
<h2>window.open 走内置浏览器（模拟 DSH 登录）</h2>
<pre id="log"></pre>
<script>
const out = (m) => {
  document.getElementById('log').textContent += m + "\n";
  console.log('PAGE ' + m);
  document.title = 'SHIM ' + m;
};
window.addEventListener('load', () => {
  setTimeout(() => {
    let p = null;
    try { p = window.open('about:blank', '_blank'); } catch (e) { out('1 open 抛错: ' + e); }
    out('1 open(about:blank) -> ' + (p ? 'OK, id=' + p.__dshPopupId : 'NULL'));
    if (p) {
      try { p.opener = null; out('1b opener=null 成功'); } catch (e) { out('1b opener=null 抛错: ' + e); }
      setTimeout(() => {
        try { p.location.replace('http://127.0.0.1:8099/land.html?from=replace'); out('2 location.replace 已发出'); }
        catch (e) { out('2 location.replace 抛错: ' + e); }
        setTimeout(() => {
          try { out('3 1.5 秒后 closed=' + p.closed); } catch (e) { out('3 抛错: ' + e); }
          out('4 不改窗口，等截图');
        }, 1500);
      }, 1200);
    }
  }, 1200);
  setTimeout(() => { out('5 主窗口仍然活着（这行还在就说明进程没崩）'); }, 6000);
});
</script>
</body>
HTML

mkdir -p /tmp/dsh-test
cp /tmp/dsh-desktop-new.py /tmp/dsh-test/dsh-desktop.py || exit 9

cd "$DIR" && setsid nohup python3 -m http.server 8099 --bind 127.0.0.1 >/tmp/dsh-popup3-http.log 2>&1 &
sleep 1

: > "$LOG"
DSH_SHARE=/home/twinblade/Program/deepseek-harness-1/share \
DSH_DESKTOP_NO_SERVICE=1 DSH_WEB_URL=http://127.0.0.1:8099/ LIBGL_ALWAYS_SOFTWARE=1 \
  setsid nohup python3 -u /tmp/dsh-test/dsh-desktop.py http://127.0.0.1:8099/index.html \
  >>"$LOG" 2>&1 &
sleep 3
python3 /tmp/vm-shot.py /tmp/shim-a.png 2>&1 | tail -1
sleep 3
python3 - <<'PY'
import socket
for p in ('/run/user/1000/dsh-desktop-1000-8099.sock',):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(p)
        s.sendall(b'raise\n')
        print('raise ->', s.recv(64))
        s.close()
    except Exception as exc:
        print('raise 失败:', p, exc)
PY
sleep 2
python3 /tmp/vm-shot.py /tmp/shim-b.png 2>&1 | tail -1
echo '== log'
grep -v -e DeprecationWarning -e '^  ' "$LOG" | head -40
echo '== alive?'
pgrep -af 'dsh-test/dsh-desktop.py' || echo '  (进程已退出)'
pkill -f 'dsh-test/dsh-desktop.py' 2>/dev/null
pkill -f 'http.server 8099' 2>/dev/null
echo '== done'
