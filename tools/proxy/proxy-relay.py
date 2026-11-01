#!/usr/bin/env python3
"""把只监听 127.0.0.1 的代理，转发成虚拟机可用的地址（本机侧一个小中继）。

为什么需要它：本机的代理（wandacloudCore.exe）只监听 `127.0.0.1:7890`，
虚拟机里的进程连不到 127.0.0.1 —— 那个 loopback 是虚拟机自己的。
又不想去改代理软件的「允许局域网」开关（那是它的配置，升级/重置会丢），
所以在本机的 Hyper-V 网卡地址上开一个端口，纯 TCP 转发到 127.0.0.1:7890。

用法：
    python proxy-relay.py                     # 默认 172.22.144.1:7891 -> 127.0.0.1:7890
    python proxy-relay.py --listen 0.0.0.0:7891
    python proxy-relay.py --target 127.0.0.1:7890 --listen 172.22.144.1:7891 -v
"""
import argparse
import socket
import sys
import threading
import time

LOG = True


def log(msg):
    if LOG:
        sys.stderr.write('[proxy-relay] %s %s\n' % (time.strftime('%H:%M:%S'), msg))
        sys.stderr.flush()


def pump(src, dst, tag):
    """单向搬运；任何一端关闭就一起收摊。"""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass


def handle(client, addr, target, verbose):
    try:
        client.settimeout(None)
        upstream = socket.create_connection(target, timeout=10)
    except Exception as exc:
        log('连不上目标 %s：%s' % (target, exc))
        try:
            client.close()
        except Exception:
            pass
        return
    if verbose:
        log('%s:%d 已连接' % addr[:2])
    t1 = threading.Thread(target=pump, args=(client, upstream, 'up'), daemon=True)
    t2 = threading.Thread(target=pump, args=(upstream, client, 'down'), daemon=True)
    t1.start()
    t2.start()


def parse_addr(text):
    host, _, port = text.rpartition(':')
    if not host:
        raise argparse.ArgumentTypeError('地址要写成 host:port：%r' % text)
    return host, int(port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--listen', type=parse_addr, default=parse_addr('172.22.144.1:7891'),
                    help='本机对外监听地址（默认 Hyper-V 网卡地址 172.22.144.1:7891）')
    ap.add_argument('--target', type=parse_addr, default=parse_addr('127.0.0.1:7890'),
                    help='真正的代理地址（默认 127.0.0.1:7890）')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(args.listen)
    except OSError as exc:
        log('绑定 %s:%d 失败：%s' % (args.listen[0], args.listen[1], exc))
        return 1
    srv.listen(64)
    log('监听 %s:%d → 转发到 %s:%d' % (args.listen[0], args.listen[1],
                                       args.target[0], args.target[1]))
    try:
        while True:
            client, addr = srv.accept()
            threading.Thread(target=handle, args=(client, addr, args.target, args.verbose),
                             daemon=True).start()
    except KeyboardInterrupt:
        log('退出')
    finally:
        srv.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
