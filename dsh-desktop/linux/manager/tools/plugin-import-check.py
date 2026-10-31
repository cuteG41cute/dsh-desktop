"""验证插件本地导入的两处坑（都不会碰网络、不需要 GTK）：

1. **空数组占位符**：新建实例的 `cordis.patch.yml` 里有一个裸 `[]`。
   以前往它后面追加 `- insert:` 会让整份 YAML 变成两个文档，dsh 启动直接报
   "end of the stream or a document separator is expected" —— 实例启不来。
   现在必须把 `[]` 替换掉。

2. **平铺 tar.gz**：包内直接是 `package.json + lib/`（没有顶层目录）时，
   旧代码会错误地把 `lib/` 当包根，报"没找到带 name 的 package.json"。
   两种打包方式都要能装。

跑法：python dsh-desktop/linux/manager/tools/plugin-import-check.py
"""
import os
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dsh_manager import plugins as plug  # noqa: E402
from dsh_manager.core import Instance    # noqa: E402

PATCH_TEMPLATE = """# Your patch layer for this dsh profile
[]
"""


def make_instance(root):
    prefix = os.path.join(root, 'inst')
    profile = os.path.join(prefix, 'dsh-home', 'profiles', 'web')
    os.makedirs(os.path.join(profile, 'node_modules'), exist_ok=True)
    with open(os.path.join(profile, 'cordis.patch.yml'), 'w', encoding='utf-8') as fh:
        fh.write(PATCH_TEMPLATE)
    return Instance(prefix, {'port': '3080', 'label': 'test'})


def make_tarball(root, name, wrapped):
    """wrapped=True 时带顶层目录（GitHub 风格），False 时平铺。"""
    meta = '{"name": "%s", "version": "9.9.9", "type": "module", "main": "lib/index.js"}' % name
    src = os.path.join(root, 'build-' + ('w' if wrapped else 'f'))
    base = os.path.join(src, name) if wrapped else src
    os.makedirs(os.path.join(base, 'lib'), exist_ok=True)
    with open(os.path.join(base, 'package.json'), 'w', encoding='utf-8') as fh:
        fh.write(meta)
    with open(os.path.join(base, 'lib', 'index.js'), 'w', encoding='utf-8') as fh:
        fh.write('export function apply() {}\n')
    tarball = os.path.join(root, ('wrapped' if wrapped else 'flat') + '.tar.gz')
    with tarfile.open(tarball, 'w:gz') as tar:
        tar.add(base, arcname=name if wrapped else '.')
    return tarball


def read_patch(inst):
    path = plug.patch_path(inst)
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='plug-import-') as root:
        inst = make_instance(root)

        # ---- 用例 1：平铺包能装，且不会留下裸 [] ----
        flat = make_tarball(root, 'dsh-demo-flat', wrapped=False)
        ok, msg = plug.install_from_tarball(inst, flat, log=lambda *_: None)
        checks.append(('平铺 tar.gz 能导入（%s）' % (msg[:26] + '…'), ok))
        text = read_patch(inst)
        checks.append(('patch 里没有裸 []（否则 dsh 起不来）',
                       not any(line.strip() == '[]' for line in text.splitlines())))
        checks.append(('patch 里有 - insert:', '- insert:' in text))
        target = os.path.join(plug.profile_dir(inst), 'node_modules', 'dsh-demo-flat')
        checks.append(('包被复制到 node_modules', os.path.isdir(target)))

        # ---- 用例 2：带顶层目录的包也能装，且追加而不是覆盖 ----
        wrapped = make_tarball(root, 'dsh-demo-wrap', wrapped=True)
        ok2, msg2 = plug.install_from_tarball(inst, wrapped, log=lambda *_: None)
        checks.append(('带顶层目录的 tar.gz 能导入（%s）' % (msg2[:26] + '…'), ok2))
        text2 = read_patch(inst)
        checks.append(('两次导入是追加（两条 insert 都在）',
                       text2.count('- insert:') == 2))
        checks.append(('第二个包也在 node_modules',
                       os.path.isdir(os.path.join(plug.profile_dir(inst),
                                                  'node_modules', 'dsh-demo-wrap'))))

        # ---- 用例 3：重复装同一个包不重复写 patch ----
        ok3, _msg3 = plug.install_from_tarball(inst, flat, log=lambda *_: None)
        checks.append(('重复导入不会重复追加 patch', read_patch(inst).count('- insert:') == 2))

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(('  OK   ' if ok else '  FAIL ') + name)
    print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                                len(checks) - len(failed), len(checks)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
