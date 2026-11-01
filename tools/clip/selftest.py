#!/usr/bin/env python3
"""剪切板桥自检：起一份桥，双向各推一条文本，验证对面真的读到了。

用法（在仓库根目录）：
    python tools/clip/selftest.py
退出码 0 = 双向都通。
"""
import base64
import importlib.util
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# Windows 控制台默认是 GBK，打印 ✓ / 箭头会直接抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


BRIDGE = os.path.join(HERE, 'host-bridge.py')
VM_HOST = os.environ.get('DSH_CLIP_SSH', 'twinblade@172.22.148.197')
CREATE_NO_WINDOW = 0x08000000


def load_bridge():
    spec = importlib.util.spec_from_file_location('host_bridge', BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ssh(cmd, timeout=20):
    return subprocess.run(['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                           '-p', '22', VM_HOST, cmd],
                          capture_output=True, timeout=timeout)


def vm_clip():
    p = ssh('wl-paste --no-newline 2>/dev/null | base64 -w0')
    if p.returncode != 0 or not p.stdout.strip():
        return None
    try:
        return base64.b64decode(p.stdout.strip()).decode('utf-8')
    except Exception:
        return None


def set_vm_clip(text):
    payload = base64.b64encode(text.encode('utf-8')).decode('ascii')
    p = ssh("printf '%%s' %s | base64 -d | wl-copy >/dev/null 2>&1; echo ok" % payload)
    return b'ok' in p.stdout


def main():
    bridge_mod = load_bridge()
    print('启动桥：%s' % BRIDGE)
    proc = subprocess.Popen([sys.executable, BRIDGE], cwd=HERE,
                            creationflags=CREATE_NO_WINDOW,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = True
    try:
        time.sleep(3.5)

        text_a = 'host→vm 测试 A ✓ 中文与换行\n第二行'
        print('本机 -> 虚拟机：%r' % text_a)
        bridge_mod.set_clipboard_text(text_a)
        time.sleep(3.5)
        got = vm_clip()
        if got == text_a:
            print('  PASS 虚拟机读到的完全一致')
        else:
            ok = False
            print('  FAIL 虚拟机读到：%r' % got)

        text_b = 'vm→host 测试 B 中文\n末行'
        print('虚拟机 -> 本机：%r' % text_b)
        set_vm_clip(text_b)
        time.sleep(3.5)
        got = bridge_mod.clipboard_text()
        if got == text_b:
            print('  PASS 本机读到的完全一致')
        else:
            ok = False
            print('  FAIL 本机读到：%r' % got)

        text_c = 'A' * 20000
        print('大文本（20KB）本机 -> 虚拟机')
        bridge_mod.set_clipboard_text(text_c)
        time.sleep(4.0)
        got = vm_clip()
        print('  %s 长度 %s' % ('PASS' if got == text_c else 'FAIL', len(got or '')))
        ok = ok and got == text_c

        log_path = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'dsh-clip', 'bridge.log')
        print('\n== 桥日志末尾（%s）' % log_path)
        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as fh:
                for line in fh.readlines()[-12:]:
                    sys.stdout.write('  ' + line)
        except Exception as exc:
            print('  读不到日志：%s' % exc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print('\n结果：%s' % ('全部通过' if ok else '有失败项'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
