"""桌面壳 ↔ 截图插件的原生截屏桥：能在本机验证的部分，全部真跑一遍。

背景（Linux 侧实测）：WebKitGTK 的 getDisplayMedia 在 KDE Wayland 上必死——
kwin 的截屏流广播"可变帧率"，WebKitGTK 的 GStreamer 胶囊协商断言失败：
    gst_value_collect_int_range: assertion
    'collect_values[0].v_int < collect_values[1].v_int' failed
所以改成"桌面壳通过 xdg-desktop-portal 一次性拿 PNG"，页面只换取画面这一步。

本机（无 GTK/D-Bus）能验证的：
  1. load_png_data_url() 真读文件、真 base64、真还原字节（含中文/空格路径）；
  2. 壳侧协议齐全：消息分支、__dshShotReply、先订阅再调用、30 秒兜底；
  3. 插件侧协议齐全：nativeCapture / 注册表与回传函数分开命名 /
     grabFrame 里原生通道排在 getDisplayMedia 之前 / 有超时兜底。

跑法：python dsh-desktop/linux/tools/screenshot-bridge-check.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LINUX = os.path.dirname(HERE)                      # dsh-desktop/linux
REPO = os.path.dirname(os.path.dirname(LINUX))     # 仓库根
SHELL_PY = os.path.join(LINUX, 'dsh-desktop.py')
PLUGIN_JS = os.path.join(REPO, 'dsh-screenshot', 'static', 'lib', 'client.js')

# 一个最小的合法 PNG（1x1 透明）
PNG_BYTES = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6300010000050001' '0d0a2db4' '0000000049454e44ae426082')


def load_shell_module():
    import importlib.util
    saved = sys.argv[:]
    sys.argv = ['dsh-desktop.py']
    try:
        spec = importlib.util.spec_from_file_location('dsh_desktop_bridge', SHELL_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.argv = saved


def main():
    checks = []
    app = load_shell_module()

    # ---- 1) data URL 转换：真读文件、真还原字节 ----
    with tempfile.TemporaryDirectory(prefix='shot-bridge-') as tmp:
        folder = os.path.join(tmp, '图片 目录')          # 中文 + 空格，验证 unquote
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, 'Screenshot_1.png')
        with open(path, 'wb') as fh:
            fh.write(PNG_BYTES)
        import pathlib
        uri = pathlib.Path(path).as_uri()             # portal 给的就是 file:// URI（含 %20）
        data_url = app.load_png_data_url(uri)
        checks.append(('中文+空格路径的 file:// 能读出来', isinstance(data_url, str)
                       and data_url.startswith('data:image/png;base64,')))
        if isinstance(data_url, str):
            import base64
            decoded = base64.b64decode(data_url.split(',', 1)[1])
            checks.append(('base64 还原后字节完全一致', decoded == PNG_BYTES))
        else:
            checks.append(('base64 还原后字节完全一致', False))
        missing = app.load_png_data_url('file:///no/such/file.png')
        checks.append(('文件不存在时返回 None', missing is None))

    # ---- 2) 壳侧协议 ----
    with open(SHELL_PY, encoding='utf-8') as fh:
        shell = fh.read()
    checks.append(("壳侧有 dsh-screenshot 消息分支", "mtype == 'dsh-screenshot'" in shell))
    checks.append(('壳侧调用 portal Screenshot（interactive=false）',
                   'org.freedesktop.portal.Screenshot' in shell and "'interactive': GLib.Variant('b', False)" in shell))
    sub_at = shell.find("bus.signal_subscribe(")
    call_at = shell.find("bus.call_sync('org.freedesktop.portal.Desktop'")
    checks.append(('先订阅 Response 再调用（避免竞态）', 0 <= sub_at < call_at))
    checks.append(('回传用 window.__dshShotReply', 'window.__dshShotReply' in shell))
    checks.append(('30 秒兜底超时存在', 'portal 截屏超时（30 秒）' in shell))
    checks.append(('variant 内联字典（踩过的 KeyError: 0）',
                   "GLib.Variant('(sa{sv})', ('', options))" in shell))

    # ---- 3) 插件侧协议 ----
    with open(PLUGIN_JS, encoding='utf-8') as fh:
        plugin = fh.read()
    checks.append(('插件有 nativeCapture', 'function nativeCapture()' in plugin))
    checks.append(('注册表与回传函数分开命名', 'window.__dshShot = ' in plugin
                   and 'window.__dshShotReply = ' in plugin))
    body_start = plugin.find('async function grabFrame()')
    body_end = plugin.find('function pickRegion(')
    body = plugin[body_start:body_end] if 0 <= body_start < body_end else ''
    native_at = body.find('const native = await nativeCapture()')
    gdm_at = body.find('navigator.mediaDevices.getDisplayMedia')
    checks.append(('grabFrame 里原生通道排在 getDisplayMedia 之前',
                   0 <= native_at < gdm_at if gdm_at >= 0 else native_at >= 0))
    checks.append(('原生通道有自己的超时兜底', 'NATIVE_CAPTURE_TIMEOUT_MS' in plugin))
    checks.append(('插件版本 >= 1.3.1', "const VERSION = '1.3.1'" in plugin))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(('  OK   ' if ok else '  FAIL ') + n)
    print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                                len(checks) - len(failed), len(checks)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
