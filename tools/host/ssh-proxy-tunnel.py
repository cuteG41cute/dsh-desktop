#!/usr/bin/env python3
"""SSH ProxyCommand：让 ssh 走本地 HTTP 代理（CONNECT 隧道）。

Windows 上 git 不读系统代理，SSH 更是完全不看 HTTPS_PROXY，所以直连 github.com:443
会超时。这个脚本把 ssh 的 TCP 连接转成一个 HTTP CONNECT 隧道。

用法（git 会自己填 %h %p）：

    set GIT_SSH_COMMAND=ssh -o ProxyCommand="python C:/path/ssh-proxy-tunnel.py 127.0.0.1:7890 %h %p"
    git push

代理端口按需改（本机是 127.0.0.1:7890）。
"""
import os
import socket
import sys
import threading

if os.name == 'nt':
    import msvcrt

    msvcrt.setmode(0, os.O_BINARY)
    msvcrt.setmode(1, os.O_BINARY)


def main():
    if len(sys.argv) < 4:
        sys.stderr.write('usage: ssh-proxy-tunnel.py HOST:PORT TARGET_HOST TARGET_PORT\n')
        return 2
    proxy_host, proxy_port = sys.argv[1].rsplit(':', 1)
    target, target_port = sys.argv[2], int(sys.argv[3])

    sock = socket.create_connection((proxy_host, int(proxy_port)), timeout=25)
    req = ('CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\nProxy-Connection: keep-alive\r\n\r\n'
           % (target, target_port, target, target_port))
    sock.sendall(req.encode())

    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            sys.stderr.write('proxy closed the connection\n')
            return 3
        buf += chunk
    head, _, rest = buf.partition(b'\r\n\r\n')
    status = head.split(b'\r\n', 1)[0]
    if b' 200' not in status:
        sys.stderr.write('proxy refused: %s\n' % status.decode('latin-1'))
        return 3

    out = sys.stdout.buffer
    if rest:
        out.write(rest)
        out.flush()

    def upstream():
        """local stdin → proxy"""
        stdin = sys.stdin.buffer
        try:
            while True:
                data = stdin.read1(65536) if hasattr(stdin, 'read1') else stdin.read(65536)
                if not data:
                    break
                sock.sendall(data)
        except Exception:
            pass
        try:
            sock.shutdown(socket.SHUT_WR)
        except Exception:
            pass

    threading.Thread(target=upstream, daemon=True).start()
    try:
        while True:
            data = sock.recv(65536)
            if not data:
                break
            out.write(data)
            out.flush()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
