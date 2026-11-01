#!/usr/bin/env python3
"""虚拟机侧：盯着 Wayland 剪切板，一变就把内容用 base64 打给宿主（stdout）。

宿主那半边（tools/clip/host-bridge.py）用 ssh 起这个脚本，读它的 stdout。
只处理文本：`wl-paste` 拿不到文本（比如剪切板里是图片）就什么都不发。
"""
import hashlib
import os
import subprocess
import sys
import time

POLL = float(os.environ.get('DSH_CLIP_POLL', '0.35'))
ENV = dict(os.environ)
# SSH 会话里没有桌面环境变量，这里补齐（uid 按当前用户算）
ENV.setdefault('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid())
ENV.setdefault('WAYLAND_DISPLAY', 'wayland-0')
ENV.setdefault('DISPLAY', ':1')


def read_clip():
    try:
        p = subprocess.run(['wl-paste', '--no-newline'], capture_output=True,
                           timeout=3, env=ENV)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    try:
        return p.stdout.decode('utf-8')
    except UnicodeDecodeError:
        return None


def log(msg):
    sys.stderr.write('[vm-watch] %s\n' % msg)
    sys.stderr.flush()


def main():
    log('启动，轮询 %.2fs' % POLL)
    last = None
    while True:
        text = read_clip()
        if text is None or text == '':
            time.sleep(POLL)
            continue
        digest = hashlib.sha1(text.encode('utf-8')).hexdigest()
        if digest != last:
            last = digest
            payload = text.encode('utf-8')
            if len(payload) > 4 * 1024 * 1024:
                log('跳过 %d 字节的文本（太大）' % len(payload))
            else:
                import base64
                try:
                    sys.stdout.write('%s %s\n' % (digest, base64.b64encode(payload).decode('ascii')))
                    sys.stdout.flush()
                except (BrokenPipeError, OSError):
                    # 宿主把通道关了（正常退出），安静收工
                    return
        time.sleep(POLL)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
