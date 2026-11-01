#!/bin/bash
# 端到端：在真实 DSH 页面上自动点「登录」，看内置浏览器是否接住 OAuth 授权页。
#
# 手法：不动程序，只把注入脚本换成 /tmp/dsh-share/preview-tools.js（原件 + 尾部补一段自动点击），
# 这样点「登录」走的完全是 DSH 自己的 startSignIn → authorizeUrl → popup.location.replace。
set -u
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
export WAYLAND_DISPLAY=wayland-0
export HOME=/home/twinblade
XA=$(ls /run/user/1000/xauth_* 2>/dev/null | head -1)
[ -n "${XA:-}" ] && export XAUTHORITY="$XA"
unset DISPLAY GDK_BACKEND

SHARE="$HOME/Program/deepseek-harness-1/share"
LOG=/tmp/dsh-login-e2e.log

mkdir -p /tmp/dsh-share /tmp/dsh-live
cp -f "$SHARE/preview-tools.js" /tmp/dsh-share/preview-tools.js
cat >> /tmp/dsh-share/preview-tools.js <<'JS'

/* ---- 测试专用：自动点「登录」（只在这个 /tmp 副本里有） ---- */
(function () {
  var tried = 0;
  var timer = setInterval(function () {
    tried++;
    if (tried > 40) { clearInterval(timer); return; }
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      var t = (btns[i].textContent || '').trim();
      if (t === '登录') {
        clearInterval(timer);
        console.log('AUTOCLICK 登录');
        btns[i].click();
        return;
      }
    }
  }, 500);
})();
JS
cp -f /tmp/new-dsh-desktop.py /tmp/dsh-live/dsh-desktop.py

pkill -f 'dsh-live/dsh-desktop.py' 2>/dev/null
sleep 1
kscreen-doctor --dpms on >/dev/null 2>&1
: > "$LOG"
URL="$(grep -o 'http://127.0.0.1:3080/?token=[A-Za-z0-9_-]*' /tmp/dsh-desktop-live.log 2>/dev/null | head -1)"
echo "== 用认证 URL: ${URL:-（没找到 token，退回裸地址）}"
DSH_HOME="$HOME/Program/deepseek-harness-1/dsh-home" \
DSH_DESKTOP_PORT=3099 DSH_SHARE=/tmp/dsh-share DSH_DESKTOP_NO_SERVICE=1 LIBGL_ALWAYS_SOFTWARE=1 \
  setsid nohup python3 -u /tmp/dsh-live/dsh-desktop.py "${URL:-http://127.0.0.1:3080}" \
  >>"$LOG" 2>&1 &
sleep 12
python3 /tmp/vm-shot.py /tmp/login-1.png 2>&1 | tail -1
sleep 6
python3 /tmp/vm-shot.py /tmp/login-2.png 2>&1 | tail -1
sleep 6
echo '== 日志'
grep -v -e DeprecationWarning -e '^  ' "$LOG" | head -40
echo '== 进程'
pgrep -af 'dsh-live/dsh-desktop.py' || echo '  (已退出)'
echo '== 还没关，留给下一轮排查（要关：pkill -f dsh-live/dsh-desktop.py）'
