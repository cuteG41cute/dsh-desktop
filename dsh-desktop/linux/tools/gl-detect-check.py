"""跑一遍启动器里的「要不要走软件渲染」判据（真的执行那段 shell，不是读文本猜）。

为什么需要这个 gate：判据以前只看 /dev/dri 在不在，结果 KVM 虚拟机里
/dev/dri 是 virtio_gpu、Mesa 却选不到 pdev（ZINK / dri2 screen 报错），
照样开了 GPU 路径 → 窗口上半截是一块没画过的灰板（2026-10-30 实测）。

做法：从 dsh-desktop 里把 GL_POLICY_BEGIN/GL_POLICY_END 之间那段原样剪出来，
把 /dev/dri 指到临时目录、驱动名用 DRM_DRIVER 注入，用 bash 真跑，检查 SOFT_REASON。

跑法（仓库根目录）：python dsh-desktop/linux/tools/gl-detect-check.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(os.path.dirname(HERE), 'dsh-desktop')
BEGIN = '# ---- GL_POLICY_BEGIN ----'
END = '# ---- GL_POLICY_END ----'


def load_policy():
    with open(LAUNCHER, encoding='utf-8') as fh:
        lines = fh.read().splitlines()
    try:
        start = lines.index(BEGIN) + 1
        stop = lines.index(END)
    except ValueError:
        raise SystemExit('FAIL: 启动器里找不到 GL_POLICY_BEGIN/END 标记')
    return '\n'.join(lines[start:stop])


def wsl_path(path):
    """Windows 上跑时，bash 是 WSL，得把 C:\\... 换成 /mnt/c/...（Linux 上原样返回）。"""
    if os.name != 'nt':
        return path
    drive, rest = os.path.splitdrive(path)
    return '/mnt/' + drive.rstrip(':').lower() + rest.replace('\\', '/')


def run_case(policy, root, gl_mode, driver='', dri=True):
    """在临时目录里造一个假的 /dev/dri，用 bash 跑判据，返回 SOFT_REASON 与 DRV。"""
    os.makedirs(root, exist_ok=True)
    dev = os.path.join(root, 'dri')
    if dri:
        os.makedirs(dev, exist_ok=True)
    script = (
        'log() { :; }\n'
        'GL_MODE=%s\nDEV_DRI=%s\nSYSFS_DRM=%s\nDRM_DRIVER=%s\n'
        '%s\n'
        'printf "SOFT=%%s\\nDRV=%%s\\n" "$SOFT_REASON" "$DRV"\n'
        % (gl_mode, wsl_path(dev), wsl_path(os.path.join(root, 'drm')), driver, policy)
    )
    # 写成文件再交给 bash：Windows 上 bash 是 WSL，用 -c 传多行脚本会被参数转义搞坏
    script_path = os.path.join(root, 'case.sh')
    with open(script_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(script)
    out = subprocess.run(['bash', wsl_path(script_path)], capture_output=True, text=True,
                         encoding='utf-8', errors='replace')
    if out.returncode != 0:
        raise SystemExit('FAIL: 判据脚本没跑通（exit %d）：%s'
                         % (out.returncode, (out.stderr or '').strip()[:400]))
    result = {}
    for line in out.stdout.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            result[key] = value
    return result


def main():
    policy = load_policy()
    checks = []
    with tempfile.TemporaryDirectory(prefix='gl-policy-') as tmp:
        # 1) 这台虚拟机的真实情况：/dev/dri 在，驱动 virtio_gpu → 必须软件渲染
        r = run_case(policy, os.path.join(tmp, 'virtio'), 'auto', driver='virtio_gpu')
        checks.append(('virtio_gpu + /dev/dri 存在 → 走软件渲染', '虚拟显卡' in r.get('SOFT', '')))

        # 2) 同类半虚拟驱动
        for drv in ('vmwgfx', 'qxl', 'bochs', 'vboxvideo', 'vkms'):
            r = run_case(policy, os.path.join(tmp, 'drv-' + drv), 'auto', driver=drv)
            checks.append(('%s → 走软件渲染' % drv, '虚拟显卡' in r.get('SOFT', '')))

        # 3) 真显卡：i915 → 不强制软件渲染
        r = run_case(policy, os.path.join(tmp, 'i915'), 'auto', driver='i915')
        checks.append(('i915 → 不强制软件渲染', r.get('SOFT', '') == ''))
        r = run_case(policy, os.path.join(tmp, 'amdgpu'), 'auto', driver='amdgpu')
        checks.append(('amdgpu → 不强制软件渲染', r.get('SOFT', '') == ''))

        # 4) 没有 /dev/dri → 软件渲染（哪怕驱动是真显卡）
        r = run_case(policy, os.path.join(tmp, 'nodri'), 'auto', driver='i915', dri=False)
        checks.append(('/dev/dri 不存在 → 走软件渲染', '/dev/dri' in r.get('SOFT', '')))

        # 5) 没有 DRM 信息也没有 /dev/dri（老虚拟机）
        r = run_case(policy, os.path.join(tmp, 'bare'), 'auto', driver='', dri=False)
        checks.append(('既没有 DRM 也没有 /dev/dri → 走软件渲染', r.get('SOFT', '') != ''))

        # 6) 用户强制关 → 即使真显卡也软件渲染
        r = run_case(policy, os.path.join(tmp, 'forced'), 'off', driver='i915')
        checks.append(('DSH_DESKTOP_GL=off 覆盖真显卡', 'DSH_DESKTOP_GL=off' in r.get('SOFT', '')))

        # 7) 用户强制开 → 判据不插手（交给窗口内的 GL 上下文探测兜底）
        r = run_case(policy, os.path.join(tmp, 'forced-on'), 'on', driver='', dri=False)
        checks.append(('DSH_DESKTOP_GL=on 时判据不插手', r.get('SOFT', '') == ''))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(('  OK   ' if ok else '  FAIL ') + name)
    print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                                len(checks) - len(failed), len(checks)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
