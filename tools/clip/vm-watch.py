#!/usr/bin/env python3
"""虚拟机侧：盯剪贴板变化，变了就把内容用 base64 打给宿主（stdout）。

**不再反复起 wl-paste 进程**：早期版本每 0.35 秒执行一次 `wl-paste`，会在
KWin 里不停创建/销毁 Wayland 客户端、不停向合成器请求剪贴板数据 —— 用户实测
这会让桌面/应用里的弹出菜单「闪一下就没了」。现在改成走 Plasma 自带的剪贴板
服务 Klipper（DBus）：一个常驻进程、零 Wayland 客户端、只在真的变化时读一次。

Klipper 是 Plasma 的剪贴板历史服务（org.kde.klipper / /klipper），
`clipboardHistoryUpdated` 信号就是「剪贴板变了」。

拿不到 Klipper（非 Plasma 桌面）时，退回 `wl-paste --watch`（也是事件驱动，
只占一个长期客户端，不再轮询）。
"""
import base64
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time

POLL = float(os.environ.get('DSH_CLIP_POLL', '0.35'))
MAX_BYTES = 4 * 1024 * 1024

KLIPPER_DEST = 'org.kde.klipper'
KLIPPER_PATH = '/klipper'
KLIPPER_IFACE = 'org.kde.klipper.klipper'


def log(msg):
    sys.stderr.write('[vm-watch] %s\n' % msg)
    sys.stderr.flush()


def emit(text, state):
    if text is None or text == '':
        return
    payload = text.encode('utf-8')
    if len(payload) > MAX_BYTES:
        log('跳过 %d 字节（太大）' % len(payload))
        return
    digest = hashlib.sha1(payload).hexdigest()
    if digest == state.get('last'):
        return
    state['last'] = digest
    try:
        sys.stdout.write('%s %s\n' % (digest, base64.b64encode(payload).decode('ascii')))
        sys.stdout.flush()
    except (BrokenPipeError, OSError):
        os._exit(0)


# ---------------------------------------------------------------- Klipper 后端
def run_klipper(state):
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib

    os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS',
                          'unix:path=/run/user/%d/bus' % os.getuid())
    proxy = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_AUTO_START, None,
        KLIPPER_DEST, KLIPPER_PATH, KLIPPER_IFACE, None)
    log('使用 Klipper DBus（常驻，不轮询）')

    def read():
        try:
            res = proxy.call_sync('getClipboardContents', None,
                                  Gio.DBusCallFlags.NONE, 3000, None)
            return res.unpack()[0]
        except Exception as exc:
            log('读剪贴板失败：%s' % exc)
            return None

    def on_signal(_proxy, _sender, signal_name, _params):
        if signal_name == 'clipboardHistoryUpdated':
            emit(read(), state)

    proxy.connect('g-signal', on_signal)
    emit(read(), state)          # 先报一次当前内容
    loop = GLib.MainLoop()
    loop.run()
    return 0


# ---------------------------------------------------------------- wl 兜底后端
def run_wl(state):
    if not shutil.which('wl-paste'):
        log('既没有 Klipper 也没有 wl-paste，放弃')
        return 2
    log('退回 wl-paste --watch（事件驱动）')
    env = dict(os.environ)
    env.setdefault('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid())
    env.setdefault('WAYLAND_DISPLAY', 'wayland-0')
    proc = subprocess.Popen(['wl-paste', '--watch', 'cat'], stdout=subprocess.PIPE, env=env)
    try:
        for raw in proc.stdout:
            emit(raw.decode('utf-8', 'replace').rstrip('\n'), state)
    except KeyboardInterrupt:
        pass
    return 0


def main():
    state = {'last': None}
    try:
        return run_klipper(state)
    except Exception as exc:
        log('Klipper 不可用（%s），改用 wl-paste' % exc)
        return run_wl(state)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
