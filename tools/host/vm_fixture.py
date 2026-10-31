"""Fixture data shared by the GTK render/dump tools (uploaded to /tmp/dsh-vm on the VM).

The numbers here are copied from design/index.html so the GTK window shows exactly the
same strings the design reference does — otherwise a pixel diff measures the data, not
the layout.
"""
import os
import time

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
    def __init__(self, spec=None):
        self.spec = spec or DESIGN
        self.root = "/home/twinblade/.local/opt"
        self.latest_dsh_version = self.spec["dsh"]
        self.latest_node_version = self.spec["node"]
        self.available_dsh_versions = [self.spec["dsh"]]
        self.available_node_versions = [self.spec["node"]]
        self.instances = [
            FakeInstance(label, prefix, port, running, pid, self.spec["dsh"], self.spec["node"])
            for label, prefix, port, running, pid in self.spec["instances"]
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
    from gi.repository import Gtk
    end = time.time() + ms / 1000.0
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.005)


def inject_logs(win):
    """把设计稿那 3 行日志塞进去（时间用设计稿里的，而不是当前时间）。"""
    real = time.strftime
    try:
        for stamp, level, text in reversed(DESIGN["logs"]):
            time.strftime = lambda fmt, *a, _s=stamp: _s if fmt == "%H:%M:%S" else real(fmt, *a)
            prefix = {"success": "✔ ", "danger": "✘ ", "muted": "—— "}.get(level, "")
            suffix = " ——" if level == "muted" else ""
            try:
                win._push_recent_log(prefix + text + suffix)
            except Exception as exc:
                print("log inject failed:", exc)
    finally:
        time.strftime = real
