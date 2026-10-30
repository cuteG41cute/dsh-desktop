"""验证「一个实例一套控制套接字 / 一把锁」——多实例时只开得出第一个窗口的根因。

以前套接字是 `dsh-desktop-<uid>.sock`、锁是 `/tmp/dsh-desktop.lock`，都是**全局唯一**：
开第二个实例时管理器 ping 到的是第一个实例的窗口，于是永远只把第一个窗口提到前台，
第二个实例的窗口根本没被打开（用户实测：两个实例只显示第一个）。

这里把两侧的命名规则都真跑一遍：
  - 管理器侧 Instance.control_socket()
  - 窗口侧 dsh-desktop.py 的 instance_port() / control_socket_path()
  - 启动器的锁名（从源码里取，确保跟 dsh-desktop-<port>.lock 对得上）

跑法：python dsh-desktop/linux/tools/socket-name-check.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LINUX = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LINUX, 'manager'))
from dsh_manager.core import Instance  # noqa: E402


def load_desktop_module():
    """导入 dsh-desktop.py（文件名带连字符，只能走 importlib）。"""
    saved = sys.argv[:]
    sys.argv = ['dsh-desktop.py']            # 别让它把测试脚本的参数当成窗口 URL
    try:
        spec = importlib.util.spec_from_file_location('dsh_desktop_app',
                                                      os.path.join(LINUX, 'dsh-desktop.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.argv = saved


def main():
    checks = []
    app = load_desktop_module()

    # ---- 管理器侧：同一个 prefix、不同端口 → 不同套接字 ----
    a = Instance('/tmp/inst-a', {'port': '3080'})
    b = Instance('/tmp/inst-b', {'port': '3081'})
    sa, sb = a.control_socket(), b.control_socket()
    checks.append(('管理器：套接字按端口命名', sa.endswith('-3080.sock') and sb.endswith('-3081.sock')))
    checks.append(('管理器：两个实例的套接字不同', sa != sb))
    uid = os.getuid() if hasattr(os, 'getuid') else 0
    checks.append(('管理器：路径里不再只有 uid', '-%d-' % uid in sa))

    # ---- 窗口侧：环境变量指定的端口优先 ----
    os.environ['DSH_DESKTOP_PORT'] = '3081'
    try:
        checks.append(('窗口：DSH_DESKTOP_PORT 生效', app.instance_port() == 3081))
        path = app.control_socket_path()
        checks.append(('窗口：套接字与端口对应', path.endswith('-3081.sock')))
        checks.append(('窗口/管理器：两侧命名完全一致', path == sb))
    finally:
        os.environ.pop('DSH_DESKTOP_PORT', None)

    # ---- 窗口侧：没有环境变量时从 URL 解析 ----
    app.WEB_URL = 'http://127.0.0.1:3099'
    checks.append(('窗口：没有环境变量时从 URL 取端口', app.instance_port() == 3099))
    checks.append(('窗口：URL 无端口时退回 3080',
                   (setattr(app, 'WEB_URL', 'http://127.0.0.1') or app.instance_port() == 3080)))

    # ---- 锁：按端口区分（读源码，确保三处写法一致） ----
    with open(os.path.join(LINUX, 'dsh-desktop'), encoding='utf-8') as fh:
        launcher = fh.read()
    checks.append(('启动器：锁按端口命名', 'LOCK="/tmp/dsh-desktop-${PORT_TAG}.lock"' in launcher))
    checks.append(('启动器：从 URL 推端口', 'PORT_TAG="$(printf' in launcher))
    checks.append(('启动器：把端口导出给窗口进程', 'export DSH_DESKTOP_PORT="$PORT_TAG"' in launcher))

    with open(os.path.join(LINUX, 'manager', 'dsh_manager', 'core.py'), encoding='utf-8') as fh:
        core = fh.read()
    checks.append(('管理器：清锁时也认按端口的锁名', "'/tmp/dsh-desktop-%d.lock' % port" in core))
    checks.append(('管理器：把端口传给窗口进程', "env['DSH_DESKTOP_PORT'] = str(self.port)" in core))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(('  OK   ' if ok else '  FAIL ') + n)
    print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                                len(checks) - len(failed), len(checks)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
