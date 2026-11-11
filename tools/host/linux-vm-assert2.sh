#!/bin/bash
# 真窗口断言：开关控制注入 + 两个右键菜单的实际 DOM 行为
set -u
PREFIX=/home/twinblade/.local/opt/deepseek-harness-2
PORT=3081
CR=$HOME/.config/dsh-manager/settings.json

echo "=== 打开 webPan，重启窗口 ==="
python3 - <<'PY'
import json, os
p = os.path.expanduser('~/.config/dsh-manager/settings.json')
try:
    with open(p, encoding='utf-8') as fh:
        data = json.load(fh)
except Exception:
    data = {}
data['webPan'] = True
data['webDragOut'] = True
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
print('settings ->', json.dumps({k: data.get(k) for k in ('webPan', 'webDragOut')}))
PY

src=$(pgrep -x plasmashell | head -1)
while IFS='=' read -r k v; do
  case "$k" in
    DISPLAY|XAUTHORITY|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|DBUS_SESSION_BUS_ADDRESS) export "$k=$v" ;;
  esac
done < <(tr '\0' '\n' < "/proc/$src/environ")
export GDK_BACKEND=x11

pkill -f "share/dsh-desktop" 2>/dev/null || true
sleep 2
: > "$PREFIX/logs/desktop.log" 2>/dev/null || true
DSH_DESKTOP_DEBUG=1 dsh-manager --headless open --prefix "$PREFIX" 2>&1 | tail -2
sleep 12
grep -a "injected" "$PREFIX/logs/desktop.log" || echo '(none)'

sock="/run/user/$(id -u)/dsh-desktop-$(id -u)-$PORT.sock"

ask () {
  python3 - "$sock" "$1" <<'PY'
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
try:
    s.connect(sys.argv[1])
    s.sendall(('js ' + sys.argv[2]).encode('utf-8'))
    data = b''
    while True:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
    print(data.decode('utf-8', 'replace').strip())
except Exception as exc:
    print('ERR', exc)
finally:
    try:
        s.close()
    except Exception:
        pass
PY
}

echo "=== 注入标志 ==="
for expr in \
  "String(!!window.__dshPan)" \
  "String(!!window.__dshMenu)" \
  "String(!!window.__dshTextMenu)" \
  "String(!!window.__dshDragOutLinux)" \
  "String(typeof window.__DSH_HOST_PATHS__)"; do
  printf '%-42s -> ' "$expr"; ask "$expr"
done

echo "=== 输入框右键菜单（真实 DOM）==="
ask "(function(){var old=document.getElementById('dsh-text-menu');if(old)old.remove();var ta=document.createElement('textarea');ta.value='hello world';ta.style.position='fixed';ta.style.left='10px';ta.style.top='10px';document.body.appendChild(ta);ta.focus();ta.setSelectionRange(0,5);var ev=new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:40,clientY:40});ta.dispatchEvent(ev);var m=document.getElementById('dsh-text-menu');var out={prevented:ev.defaultPrevented,menu:!!m,items:m?Array.prototype.map.call(m.children,function(c){return c.textContent}).join('|'):''};if(m)m.remove();ta.remove();return JSON.stringify(out);})()"

echo "=== 预览右键只在该区域生效 ==="
ask "(function(){var out={};var b=document.getElementById('dsh-menu');if(b)b.remove();var ev1=new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:60,clientY:60});document.body.dispatchEvent(ev1);out.outside={prevented:ev1.defaultPrevented,menu:!!document.getElementById('dsh-menu')};var root=document.createElement('div');root.className='rIfSMq_frame';var inner=document.createElement('div');inner.textContent='C:\\\\tmp\\\\a.png';root.appendChild(inner);document.body.appendChild(root);var ev2=new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:80,clientY:80});inner.dispatchEvent(ev2);var m=document.getElementById('dsh-menu');out.inside={prevented:ev2.defaultPrevented,menu:!!m,items:m?Array.prototype.map.call(m.children,function(c){return c.textContent}).join('|'):''};if(m)m.remove();root.remove();return JSON.stringify(out);})()"

echo "=== 文件夹拖入桥 ==="
ask "(function(){var out={has:typeof window.__DSH_HOST_PATHS__==='object'};try{out.filePath=JSON.stringify(window.__DSH_HOST_PATHS__.pathFor({name:'a.txt'}));}catch(e){out.filePath='ERR '+e.message}return JSON.stringify(out);})()"
