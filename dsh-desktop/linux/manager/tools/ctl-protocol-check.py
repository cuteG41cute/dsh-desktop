"""验证管理器 ↔ 窗口进程的控制协议（不需要 GTK，也不需要真窗口）。

两部分：
  A. 映射与顺序（任何平台都跑）：把 `_sock_request` 换成假的，检查
     window_alive / raise_window / reload_page / repaint_window 的判定，
     以及"唤起成功后必须顺手补一次 repaint"这条新行为。
  B. 真实套接字往返（需要 AF_UNIX）：起一个按协议应答的假窗口，跑一遍 ping /
     raise / repaint / reload；Windows 的 CPython 没有 socket.AF_UNIX 时跳过。

跑法（仓库根目录）：python dsh-desktop/linux/manager/tools/ctl-protocol-check.py
"""
import os
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dsh_manager.core import Instance  # noqa: E402

TMPDIR = tempfile.mkdtemp(prefix='ctl-test-')


class FakeInstance(Instance):
    def __init__(self, path=''):
        Instance.__init__(self, TMPDIR, {'label': 'test', 'port': '1'})
        self._path = path

    def control_socket(self):
        return self._path


def part_a(checks):
    """映射与顺序：不过套接字，直接给回复。"""
    inst = FakeInstance()
    script = []
    replies = {'ping': '', 'raise': 'raised', 'repaint': 'repainted', 'reload': 'reloaded'}

    def fake(cmd, timeout=1.5):
        script.append(cmd)
        return replies.get(cmd.split()[0], '')

    inst._sock_request = fake

    replies['raise'] = ''            # 先模拟"窗口没应答"
    checks.append(('没有应答时 window_alive() == 0', inst.window_alive() == 0))
    checks.append(('没有应答时 raise_window() 为 False', inst.raise_window() is False))

    replies['ping'] = 'ok 4242'
    replies['raise'] = 'raised'
    checks.append(('ok <pid> 解析出 PID', inst.window_alive() == 4242))

    script.clear()
    checks.append(('raise 应答 raised → raise_window() 为 True', inst.raise_window() is True))
    checks.append(('唤起后补发 repaint', script == ['raise', 'repaint']))

    script.clear()
    checks.append(('reload 应答 reloaded → True', inst.reload_page() is True))
    checks.append(('reload 只发一条命令', script == ['reload']))

    script.clear()
    checks.append(('repaint 应答 repainted → True', inst.repaint_window() is True))
    checks.append(('repaint 只发一条命令', script == ['repaint']))

    replies['reload'] = 'unknown'
    checks.append(('旧版窗口回 unknown → reload_page() 为 False', inst.reload_page() is False))


def serve(path, stop_flag, calls):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(8)
    srv.settimeout(0.3)
    while not stop_flag.is_set():
        try:
            conn, _addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            data = conn.recv(64).decode('utf-8', 'replace').strip()
            calls.append(data)
            if data.startswith('ping'):
                conn.sendall(('ok %d\n' % os.getpid()).encode())
            elif data.startswith('raise'):
                conn.sendall(b'raised\n')
            elif data.startswith('repaint'):
                conn.sendall(b'repainted\n')
            elif data.startswith('reload'):
                conn.sendall(b'reloaded\n')
            else:
                conn.sendall(b'unknown\n')
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
    srv.close()
    try:
        os.unlink(path)
    except OSError:
        pass


def part_b(checks, notes):
    """真实套接字往返；没有 AF_UNIX 就跳过（Windows 上的 CPython 就是这种）。"""
    if getattr(socket, 'AF_UNIX', None) is None:
        notes.append('SKIP 真实套接字往返：本平台没有 socket.AF_UNIX（在 Linux 里跑即可验证）')
        return
    path = os.path.join(TMPDIR, 'dsh-desktop-test.sock')
    inst = FakeInstance(path)
    stop = threading.Event()
    calls = []
    thread = threading.Thread(target=serve, args=(path, stop, calls), daemon=True)
    thread.start()
    for _ in range(60):
        if os.path.exists(path):
            break
        time.sleep(0.05)

    checks.append(('真实套接字：window_alive() 拿到 PID', inst.window_alive() == os.getpid()))
    calls.clear()
    checks.append(('真实套接字：raise_window() 成功', inst.raise_window() is True))
    checks.append(('真实套接字：ping → raise → repaint 顺序正确',
                   calls == ['ping', 'raise', 'repaint']))
    checks.append(('真实套接字：reload_page() 成功', inst.reload_page() is True))
    checks.append(('真实套接字：repaint_window() 成功', inst.repaint_window() is True))

    stop.set()
    thread.join(timeout=3)
    time.sleep(0.2)
    checks.append(('真实套接字：窗口关掉后 window_alive() == 0', inst.window_alive() == 0))


def main():
    checks = []
    notes = []
    part_a(checks)
    part_b(checks, notes)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(('  OK   ' if ok else '  FAIL ') + name)
    for note in notes:
        print('  ' + note)
    print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                                len(checks) - len(failed), len(checks)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
