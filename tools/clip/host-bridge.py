#!/usr/bin/env python3
"""Windows 侧：本机剪切板 <-> 虚拟机剪切板（Wayland）双向同步。

原理：两条常驻的 ssh 通道
  * 收（VM -> 本机）：ssh 起 `vm-watch.py`，它盯 `wl-paste`，一变就吐一行
    `<sha1> <base64>`；这里读出来写进 Windows 剪切板。
  * 发（本机 -> VM）：ssh 起 `vm-apply.py`，这里本机剪切板一变就往它 stdin
    写一行，它在虚拟机里用 `wl-copy` 写进 Wayland 剪切板。
两条通道各自有守护线程，断了自己重连。

防回声：两边的文本都按 sha1 去重，只同步「和上次同步过的内容不同」的版本，
所以 A→B 之后不会再 B→A 反弹回来。

只同步**文本**。剪切板里是图片/文件时不发（本机侧的文本也因此不会被顶掉）。
"""
import base64
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------- 配置
VM_HOST = os.environ.get('DSH_CLIP_SSH', 'twinblade@172.22.148.197')
VM_PORT = os.environ.get('DSH_CLIP_PORT', '22')
VM_DIR = os.environ.get('DSH_CLIP_VM_DIR', '.local/share/dsh-clip')
POLL = float(os.environ.get('DSH_CLIP_POLL', '0.15'))
RECONNECT = float(os.environ.get('DSH_CLIP_RECONNECT', '5'))
MAX_BYTES = 4 * 1024 * 1024

STATE_DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                         'dsh-clip')
LOG_PATH = os.path.join(STATE_DIR, 'bridge.log')
os.makedirs(STATE_DIR, exist_ok=True)

CREATE_NO_WINDOW = 0x08000000
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

u32 = ctypes.WinDLL('user32', use_last_error=True)
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
u32.OpenClipboard.argtypes = [wt.HWND]
u32.OpenClipboard.restype = wt.BOOL
u32.CloseClipboard.restype = wt.BOOL
u32.EmptyClipboard.restype = wt.BOOL
u32.GetClipboardData.argtypes = [wt.UINT]
u32.GetClipboardData.restype = wt.HANDLE
u32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
u32.SetClipboardData.restype = wt.HANDLE
u32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
u32.IsClipboardFormatAvailable.restype = wt.BOOL
u32.GetClipboardSequenceNumber.restype = wt.DWORD
k32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
k32.GlobalAlloc.restype = wt.HGLOBAL
k32.GlobalLock.argtypes = [wt.HGLOBAL]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalUnlock.argtypes = [wt.HGLOBAL]
k32.GlobalUnlock.restype = wt.BOOL
k32.GlobalFree.argtypes = [wt.HGLOBAL]
k32.GlobalFree.restype = wt.HGLOBAL


def log(msg):
    line = '%s %s\n' % (time.strftime('%H:%M:%S'), msg)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as fh:
            fh.write(line)
        if os.path.getsize(LOG_PATH) > 512 * 1024:
            data = open(LOG_PATH, 'rb').read()[-256 * 1024:]
            open(LOG_PATH, 'wb').write(data)
    except Exception:
        pass


def _touch(path):
    try:
        mtime = os.path.getmtime(path)
        with open(path, 'a', encoding='utf-8') as fh:
            pass
        os.utime(path, (mtime, mtime))
    except Exception:
        pass


# ---------------------------------------------------------------- 剪切板
def clipboard_seq():
    return u32.GetClipboardSequenceNumber()


def clipboard_text():
    """读文本剪切板；没有文本（图片/文件）返回 None。"""
    if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    for _ in range(20):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.01)
    else:
        return None
    try:
        handle = u32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = k32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            k32.GlobalUnlock(handle)
    finally:
        u32.CloseClipboard()


def set_clipboard_text(text):
    data = text.encode('utf-16-le') + b'\x00\x00'
    handle = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        return False
    ptr = k32.GlobalLock(handle)
    if not ptr:
        k32.GlobalFree(handle)
        return False
    ctypes.memmove(ptr, data, len(data))
    k32.GlobalUnlock(handle)
    try:
        for _ in range(20):
            if u32.OpenClipboard(None):
                break
            time.sleep(0.01)
        else:
            k32.GlobalFree(handle)
            return False
        try:
            u32.EmptyClipboard()
            if not u32.SetClipboardData(CF_UNICODETEXT, handle):
                k32.GlobalFree(handle)
                return False
            handle = None          # 所有权交给系统
            return True
        finally:
            u32.CloseClipboard()
            if handle:
                k32.GlobalFree(handle)
    except Exception as exc:
        log('写剪切板失败：%s' % exc)
        return False


# ---------------------------------------------------------------- ssh 通道
def ssh_args(script):
    return ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-p', str(VM_PORT), VM_HOST,
            'python3 -u ~/%s/%s' % (VM_DIR, script)]


class Bridge:
    def __init__(self):
        self.synced = None          # 最近一次同步成功的文本 sha1（防回声）
        self.writer = None          # 发通道的 Popen
        self.watch_proc = None
        self.writer_lock = threading.Lock()
        self.stop = threading.Event()

    def shutdown(self):
        """把自己拉起的 ssh 子进程都收掉。

        Windows 上杀掉父进程不会连带子进程，否则 ssh 会留在虚拟机里挂着一对
        vm-watch/vm-apply，下次启动就变成两套通道（脏但无害，排障时很误导）。
        """
        self.stop.set()
        for proc in (self.writer, self.watch_proc):
            try:
                if proc is not None and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass

    # ---- 发：本机 -> 虚拟机 ----
    def _writer_proc(self):
        with self.writer_lock:
            if self.writer is not None and self.writer.poll() is None:
                return self.writer
            log('启动发通道（ssh -> vm-apply.py）')
            self.writer = subprocess.Popen(
                ssh_args('vm-apply.py'), stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=open(LOG_PATH, 'ab'),
                creationflags=CREATE_NO_WINDOW)
            return self.writer

    def push(self, text, digest):
        payload = text.encode('utf-8')
        if len(payload) > MAX_BYTES:
            log('跳过 %d 字节（太大）' % len(payload))
            return
        line = '%s %s\n' % (digest, base64.b64encode(payload).decode('ascii'))
        for attempt in (0, 1):
            try:
                proc = self._writer_proc()
                proc.stdin.write(line.encode('ascii'))
                proc.stdin.flush()
                if attempt == 0:
                    log('已发给虚拟机：%d 字节' % len(payload))
                return True
            except Exception as exc:
                log('发通道出错（第 %d 次）：%s' % (attempt + 1, exc))
                with self.writer_lock:
                    try:
                        self.writer.kill()
                    except Exception:
                        pass
                    self.writer = None
                time.sleep(0.3)
        return False

    # ---- 收：虚拟机 -> 本机 ----
    def _watch_loop(self):
        while not self.stop.is_set():
            proc = None
            try:
                log('启动收通道（ssh <- vm-watch.py）')
                proc = subprocess.Popen(
                    ssh_args('vm-watch.py'), stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=open(LOG_PATH, 'ab'),
                    creationflags=CREATE_NO_WINDOW)
                self.watch_proc = proc
                for raw in proc.stdout:
                    if self.stop.is_set():
                        break
                    line = raw.decode('ascii', 'replace').strip()
                    if not line or ' ' not in line:
                        continue
                    digest, b64 = line.split(' ', 1)
                    try:
                        text = base64.b64decode(b64).decode('utf-8')
                    except Exception as exc:
                        log('收到坏行：%s' % exc)
                        continue
                    if digest == self.synced:
                        continue          # 自己刚推过去的回声
                    if set_clipboard_text(text):
                        self.synced = digest
                        log('已写入本机剪切板：%d 字节' % len(text.encode('utf-8')))
            except Exception as exc:
                log('收通道中断：%s' % exc)
            finally:
                if proc is not None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            if not self.stop.is_set():
                time.sleep(RECONNECT)

    # ---- 主循环：盯本机剪切板 ----
    def run(self):
        log('=== 剪切板桥启动 pid=%d -> %s ===' % (os.getpid(), VM_HOST))
        threading.Thread(target=self._watch_loop, daemon=True).start()
        seen_seq = -1
        while not self.stop.is_set():
            seq = clipboard_seq()
            if seq != seen_seq:
                seen_seq = seq
                text = clipboard_text()
                if text is None:
                    continue
                digest = hashlib.sha1(text.encode('utf-8')).hexdigest()
                if digest != self.synced:
                    if self.push(text, digest):
                        self.synced = digest
            time.sleep(POLL)


def main():
    bridge = Bridge()
    try:
        bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.shutdown()
        log('=== 剪切板桥退出 ===')


if __name__ == '__main__':
    sys.exit(main())
