#!/usr/bin/env python3
"""Render the manager window offscreen at a chosen size, with fixture data that
matches design/index.html, so it can be diffed against the design reference.

  vm-gtk-shot.py OUTDIR [WxH] [combos] [pages]

  combos : comma list of theme:mode (default: every theme, day+night)
  pages  : comma list of dashboard,settings

No compositor involved: the window's child is moved into a Gtk.OffscreenWindow,
so any size works even though the VM screen is only 1280x720.
"""
import os
import sys
import time

RUNTIME = "/run/user/%d" % os.getuid()
os.environ.setdefault("XDG_RUNTIME_DIR", RUNTIME)
os.environ.setdefault("DISPLAY", ":1")
os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=%s/bus" % RUNTIME)
for _entry in os.listdir(RUNTIME):
    if _entry.startswith("xauth_"):
        os.environ.setdefault("XAUTHORITY", os.path.join(RUNTIME, _entry))
sys.path.insert(0, os.path.expanduser("~/dsh-dev"))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

DESIGN = {
    "instances": [
        # (label, prefix, port, running, pid)
        ("dsh", "/home/twinblade/.local/opt/dsh", 3079, False, None),
        ("deepseek-harness-1", "/home/twinblade/Program/deepseek-harness-1", 3080, True, 90837),
        ("deepseek-harness-2", "/home/twinblade/.local/opt/deepseek-harness-2", 3081, False, None),
    ],
    "selected": "/home/twinblade/Program/deepseek-harness-1",
    "dsh": "0.2.1-rc.5",
    "node": "26.13.0",
    "logs": [
        # (时间, 级别, 文本) —— 顺序与设计稿一致：最新在最上
        ("14:32:08", "success", "已把现有窗口提到前台 (PID 87972)"),
        ("14:31:56", "info", "窗口程序已更新，重建窗口后新功能即可生效"),
        ("14:31:42", "muted", "实例服务运行正常，监听端口 3080"),
    ],
}


class FakeInstance:
    def __init__(self, label, prefix, port, running, pid, dsh, node):
        self.label = label
        self.prefix = prefix
        self.port = port
        self.dsh_version = dsh
        self.node_version = node
        self._running = running
        self._pid = pid
        self.dsh_home = os.path.join(prefix, "dsh-home")

    def status(self):
        return "running" if self._running else "stopped"

    def running_pid(self):
        return self._pid

    def installed(self):
        return True

    def serving(self):
        return "3080" if self._running else ""

    def window_alive(self):
        return bool(self._running)

    def web_auth_url(self):
        return (None, "", "（fixture：不查日志）")

    def auth_url_status(self, url, timeout=4.0):
        return "", "（fixture）"

    def start(self, wait=90):
        return False, "（fixture）"

    def stop(self):
        return False, "（fixture）"

    def reload_page(self):
        return False, "（fixture）"

    def open_window(self, settle=8.0, rebuild=False):
        return False, "（fixture）"

    def url(self):
        return "http://127.0.0.1:%d" % self.port


class FakeManager:
    def __init__(self, spec):
        self.spec = spec
        self.root = "/home/twinblade/.local/opt"
        self.latest_dsh_version = spec["dsh"]
        self.latest_node_version = spec["node"]
        self.available_dsh_versions = [spec["dsh"]]
        self.available_node_versions = [spec["node"]]
        self.instances = [
            FakeInstance(label, prefix, port, running, pid, spec["dsh"], spec["node"])
            for label, prefix, port, running, pid in spec["instances"]
        ]

    def list_instances(self):
        return list(self.instances)

    def instance_at(self, prefix):
        for inst in self.instances:
            if inst.prefix == prefix:
                return inst
        return None

    def next_port(self):
        return 3082

    def take_log(self):
        return []

    def install(self, *a, **k):
        return False, "（fixture）"

    def update(self, *a, **k):
        return False, "（fixture）"

    def repair(self, *a, **k):
        return False, "（fixture）"

    def uninstall(self, *a, **k):
        return False, "（fixture）"

    def open_window(self, *a, **k):
        return False, "（fixture）"


def pump(ms=300):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.005)


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gtk"
    size = sys.argv[2] if len(sys.argv) > 2 else "1432x892"
    width, height = (int(v) for v in size.lower().split("x"))
    combos = sys.argv[3] if len(sys.argv) > 3 else ""
    pages = (sys.argv[4] if len(sys.argv) > 4 else "dashboard,settings").split(",")
    os.makedirs(outdir, exist_ok=True)

    from dsh_manager import gui as g

    if not combos:
        combos = ",".join("%s:%s" % (t, m) for t in g.theme_index().get("order", [])
                          for m in ("day", "night"))

    win = g.ManagerWindow(manager=FakeManager(DESIGN))
    win.set_default_size(width, height)
    win.show_all()
    pump(700)
    # 选中设计稿里那个"正在运行"的实例
    try:
        win.selected = win.manager.instance_at(DESIGN["selected"])
        win.refresh()
    except Exception as exc:
        print("select failed:", exc)
    pump(500)

    # 喂日志（设计稿有 3 行）：_push_recent_log 用 time.strftime 记时间，
    # 这里临时把它换成设计稿里的时间，让两边的文字逐字一致。
    import time as _time
    _real_strftime = _time.strftime
    for stamp, level, text in reversed(DESIGN["logs"]):
        _time.strftime = lambda fmt, *a, _s=stamp: _s if fmt == "%H:%M:%S" else _real_strftime(fmt, *a)
        prefix = {"success": "✔ ", "danger": "✘ ", "muted": "—— "}.get(level, "")
        suffix = " ——" if level == "muted" else ""
        try:
            win._push_recent_log(prefix + text + suffix)
        except Exception as exc:
            print("log inject failed:", exc)
    _time.strftime = _real_strftime
    pump(300)

    child = win.get_child()
    win.remove(child)
    off = Gtk.OffscreenWindow()
    off.set_default_size(width, height)
    off.set_size_request(width, height)
    off.add(child)
    off.show_all()
    off.resize(width, height)
    child.set_size_request(width, height)
    pump(200)
    off.resize(width, height)
    pump(600)
    print("offscreen alloc: %dx%d" % (off.get_allocated_width(), off.get_allocated_height()))

    wrote = 0
    for combo in [c for c in combos.split(",") if c.strip()]:
        theme, mode = combo.split(":") if ":" in combo else (combo, "day")
        ok = win.apply_theme(theme, mode, persist=False)
        pump(400)
        for page in pages:
            try:
                win._show_page(page.strip())
            except Exception as exc:
                print("page %s unsupported: %s" % (page, exc))
                continue
            pump(400)
            pb = off.get_pixbuf()
            if pb is None:
                print("FAIL: offscreen pixbuf is None")
                return 1
            path = os.path.join(outdir, "%s-%s-%s.png" % (theme, mode, page.strip()))
            pb.savev(path, "png", [], [])
            wrote += 1
            print("wrote %s %dx%d bytes=%d theme_ok=%s err=%s"
                  % (path, pb.get_width(), pb.get_height(), os.path.getsize(path),
                     ok, g.last_theme_error()))
    print("total %d images" % wrote)
    return 0


if __name__ == "__main__":
    sys.exit(main())
