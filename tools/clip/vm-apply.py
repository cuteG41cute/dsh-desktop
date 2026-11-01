#!/usr/bin/env python3
"""虚拟机侧：从 stdin 收「<sha1> <base64>」行，把文本写进 Wayland 剪切板。

宿主那半边用 ssh 起这个脚本，宿主剪切板一变就写一行进来。
写剪切板用 `wl-copy`：它会把内容交给一个常驻子进程持有（Wayland 的
selection 是按客户端持有的），所以必须把它的 stdio 全部重定向掉，
否则 ssh 通道会一直被那个子进程占着、读不到下次输入。
"""
import base64
import os
import subprocess
import sys

ENV = dict(os.environ)
ENV.setdefault('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid())
ENV.setdefault('WAYLAND_DISPLAY', 'wayland-0')
ENV.setdefault('DISPLAY', ':1')


def set_clip(payload):
    try:
        p = subprocess.Popen(['wl-copy'], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env=ENV, start_new_session=True)
        p.communicate(payload, timeout=5)
        return p.returncode == 0
    except Exception as exc:
        sys.stderr.write('[vm-apply] wl-copy 失败：%s\n' % exc)
        sys.stderr.flush()
        return False


def log(msg):
    sys.stderr.write('[vm-apply] %s\n' % msg)
    sys.stderr.flush()


def main():
    log('就绪，等待宿主推送')
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            _, b64 = line.split(' ', 1)
            payload = base64.b64decode(b64)
            text = payload.decode('utf-8')
        except Exception as exc:
            log('收到坏行：%s' % exc)
            continue
        ok = set_clip(text.encode('utf-8'))
        log('%s %d 字节' % ('已写入' if ok else '写入失败', len(payload)))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
