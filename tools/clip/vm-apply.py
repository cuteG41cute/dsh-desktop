#!/usr/bin/env python3
"""虚拟机侧：从 stdin 收「<sha1> <base64>」行，把文本写进剪贴板。

早期版本每条都起一次 `wl-copy`：它会 fork 一个常驻进程去持有 selection，
再叠加 vm-watch 的轮询，等于每隔几百毫秒就在 KWin 里制造一次剪贴板所有权变更 ——
用户实测这会让桌面/应用的弹出菜单「闪一下就没了」。现在改走 Plasma 的
Klipper（DBus `setClipboardContents`）：一次方法调用，不创建任何 Wayland 客户端。

非 Plasma 环境退回 `wl-copy`（stdio 全部重定向，避免占住 ssh 通道）。
"""
import base64
import os
import shutil
import subprocess
import sys

KLIPPER_DEST = 'org.kde.klipper'
KLIPPER_PATH = '/klipper'
KLIPPER_IFACE = 'org.kde.klipper.klipper'


def log(msg):
    sys.stderr.write('[vm-apply] %s\n' % msg)
    sys.stderr.flush()


class Applier:
    def __init__(self):
        self.proxy = None
        self.backend = 'wl'
        try:
            import gi
            gi.require_version('Gio', '2.0')
            from gi.repository import Gio, GLib
            os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS',
                                  'unix:path=/run/user/%d/bus' % os.getuid())
            self._Gio = Gio
            self._GLib = GLib
            self.proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_AUTO_START, None,
                KLIPPER_DEST, KLIPPER_PATH, KLIPPER_IFACE, None)
            self.backend = 'klipper'
        except Exception as exc:
            log('Klipper 不可用（%s），退回 wl-copy' % exc)
        self.current = None

    def read_current(self):
        if self.backend != 'klipper':
            return None
        try:
            res = self.proxy.call_sync('getClipboardContents', None,
                                       self._Gio.DBusCallFlags.NONE, 3000, None)
            return res.unpack()[0]
        except Exception:
            return None

    def set_text(self, text):
        if text == self.current:
            return True                      # 已经是这个内容，别再动剪贴板
        if self.backend == 'klipper':
            try:
                self.proxy.call_sync('setClipboardContents',
                                     self._GLib.Variant('(s)', (text,)),
                                     self._Gio.DBusCallFlags.NONE, 5000, None)
                self.current = text
                return True
            except Exception as exc:
                log('Klipper 写入失败：%s' % exc)
                return False
        return self._wl_copy(text)

    def _wl_copy(self, text):
        env = dict(os.environ)
        env.setdefault('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid())
        env.setdefault('WAYLAND_DISPLAY', 'wayland-0')
        try:
            p = subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 env=env, start_new_session=True)
            p.communicate(text.encode('utf-8'), timeout=5)
            ok = p.returncode == 0
            if ok:
                self.current = text
            return ok
        except Exception as exc:
            log('wl-copy 失败：%s' % exc)
            return False


def main():
    applier = Applier()
    log('就绪（后端：%s）' % applier.backend)
    for line in sys.stdin:
        line = line.strip()
        if not line or ' ' not in line:
            continue
        try:
            _, b64 = line.split(' ', 1)
            text = base64.b64decode(b64).decode('utf-8')
        except Exception as exc:
            log('收到坏行：%s' % exc)
            continue
        ok = applier.set_text(text)
        log('%s %d 字节' % ('已写入' if ok else '写入失败', len(text.encode('utf-8'))))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
