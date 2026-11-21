"""用户级实例的 Linux 围栏：用 bubblewrap 把整个 DSH 进程关进实例目录。

- 系统目录只读挂载（/usr /bin /lib …）；
- /home 用 tmpfs 遮掉，只把实例目录 bind 回来；
- /tmp、/run 私有；
- 允许联网（不 unshare net）。

即使 DSH 内部选「完全权限」，进程也只能看到/写实例目录里的文件。
"""
import os
import shutil
import subprocess

BWRAP = '/usr/bin/bwrap'
SYSTEM_BINDS = ('usr', 'bin', 'sbin', 'lib', 'lib64', 'etc', 'opt', 'var')


def available():
    return bool(shutil.which('bwrap'))


def _parents(path):
    """返回需要提前 --dir 创建的祖先目录（不含路径自身）。"""
    out = []
    cur = os.path.dirname(path)
    while cur and cur != '/':
        out.append(cur)
        cur = os.path.dirname(cur)
    return list(reversed(out))


def _plugin_source():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins', 'dsh-fence')


def ensure_plugin(inst, log=print):
    """把 dsh-fence 装进实例 profile（幂等）。"""
    src = _plugin_source()
    if not os.path.isdir(src):
        log('围栏插件资源缺失：%s' % src)
        return False
    root = os.path.join(inst.dsh_home, 'profiles', 'web')
    dst = os.path.join(root, 'node_modules', 'dsh-fence')
    os.makedirs(os.path.join(dst, 'lib'), exist_ok=True)
    for rel in ('package.json', os.path.join('lib', 'index.js')):
        shutil.copyfile(os.path.join(src, rel), os.path.join(dst, rel))
    patch = os.path.join(root, 'cordis.patch.yml')
    text = ''
    if os.path.exists(patch):
        with open(patch, 'r', encoding='utf-8') as fh:
            text = fh.read()
    if 'id: dsh-fence' not in text:
        # 空 profile 的 patch 可能是「注释 + []」；直接追加 - insert 会变成两个文档、
        # YAML 解析失败。先把占位空数组行去掉。
        lines = [ln for ln in text.splitlines() if ln.strip() != '[]']
        text = '\n'.join(lines)
        if text and not text.endswith('\n'):
            text += '\n'
        text += ("\n# ==== dsh-fence (installed by dsh-manager) ====\n"
                 "- insert:\n"
                 "    - id: dsh-fence\n"
                 "      name: 'dsh-fence'\n"
                 "      inject: [ workspaceRegistry, webServer ]\n")
        os.makedirs(root, exist_ok=True)
        with open(patch, 'w', encoding='utf-8') as fh:
            fh.write(text)
    return True


def build_command(inst):
    """返回 (args, env)：用 bwrap 包住 DSH 启动命令。"""
    if not available():
        raise RuntimeError('系统里没有 bubblewrap（bwrap），无法启动用户级实例')
    fence = os.path.abspath(inst.fence_root or inst.prefix)
    os.makedirs(os.path.join(fence, 'tmp'), exist_ok=True)
    os.makedirs(os.path.join(fence, 'logs'), exist_ok=True)

    args = [BWRAP, '--dev', '/dev', '--proc', '/proc',
            '--tmpfs', '/tmp', '--tmpfs', '/run', '--tmpfs', '/home']
    for d in _parents(fence):
        args += ['--dir', d]
    for name in SYSTEM_BINDS:
        p = '/' + name
        if os.path.exists(p):
            args += ['--ro-bind', p, p]
    args += ['--bind', fence, fence, '--chdir', fence]
    args += ['--setenv', 'HOME', fence,
             '--setenv', 'TMPDIR', os.path.join(fence, 'tmp'),
             '--setenv', 'DSH_FENCE_ROOT', fence,
             '--setenv', 'DSH_PERMISSION_MODE', 'workspace-write']
    env = inst.env()
    env['HOME'] = fence
    env['TMPDIR'] = os.path.join(fence, 'tmp')
    env['DSH_FENCE_ROOT'] = fence
    env['DSH_PERMISSION_MODE'] = 'workspace-write'
    args += [inst.node, inst.entry, 'web', '--no-open', '--port', str(inst.port)]
    return args, env
