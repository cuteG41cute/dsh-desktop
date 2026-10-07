#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 dsh-desktop 的 Linux 发行包（deb + 通用 tar.gz）。

在任意平台都能跑（Windows 上也可以，纯 Python 标准库实现 ar/tar）：

    python3 build-linux.py            # 输出到 ../../dist/

目录约定：
    linux/                     源码（启动器 / 窗口 / 安装脚本 / 图标），版本控制的对象
    linux/build/deb/           deb 骨架（DEBIAN 控制脚本、桌面菜单项），版本控制的对象
    linux/build/.stage/        每次构建重建的打包暂存目录（可随时删除）
    linux/icons/hicolor/**     多尺寸图标（deb 用；tarball 里平铺为 icons/<size>x<size>/...）
"""
import hashlib
import io
import os
import shutil
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LINUX = os.path.dirname(HERE)                 # linux/
DEV_ROOT = os.path.dirname(LINUX)             # dsh-desktop/
DIST = os.path.join(DEV_ROOT, 'dist')
SKEL = os.path.join(HERE, 'deb')              # deb 骨架
STAGE = os.path.join(HERE, '.stage')          # 打包暂存
ICONS = os.path.join(LINUX, 'icons', 'hicolor')

VERSION = '1.2.4'
DEB_NAME = f'dsh-desktop_{VERSION}_amd64.deb'
TAR_NAME = f'dsh-desktop-linux-{VERSION}.tar.gz'

# 源文件 -> 安装到 deb 里的路径（相对 deb 根）
INSTALL_MAP = [
    ('dsh-desktop',     'usr/bin/dsh-desktop'),
    ('dsh-desktop.py',  'usr/lib/dsh-desktop/dsh-desktop.py'),
    ('dsh-desktop.png', 'usr/lib/dsh-desktop/dsh-desktop.png'),
    ('README.md',       'usr/share/doc/dsh-desktop/README-linux.md'),
]


def build_stage():
    """把源码与骨架合成为打包用的暂存目录。"""
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)

    # 1) 源码文件
    for src_name, rel in INSTALL_MAP:
        src = os.path.join(LINUX, src_name)
        if not os.path.isfile(src):
            raise SystemExit(f'缺少源文件：{src}')
        dst = os.path.join(STAGE, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)

    # 2) 骨架里的静态内容（DEBIAN 不进 data.tar，单独处理）
    skel_usr = os.path.join(SKEL, 'usr')
    for root, _dirs, files in os.walk(skel_usr):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, SKEL)
            dst = os.path.join(STAGE, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)

    # 3) 多尺寸图标
    for root, _dirs, files in os.walk(ICONS):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, ICONS)          # 16x16/apps/dsh-desktop.png
            dst = os.path.join(STAGE, 'usr', 'share', 'icons', 'hicolor', rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)


def md5_text():
    lines = []
    for root, _dirs, files in os.walk(os.path.join(STAGE, 'usr')):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, STAGE).replace('\\', '/')
            lines.append(f'{hashlib.md5(open(p, "rb").read()).hexdigest()}  {rel}')
    return ('\n'.join(sorted(lines)) + '\n').encode('ascii')


def make_tar(members):
    """members: list of (arcname, src_path_or_bytes, mode, is_file)"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz', format=tarfile.GNU_FORMAT) as tf:
        for arcname, src, mode, is_file in members:
            if is_file:
                data = open(src, 'rb').read() if isinstance(src, str) else src
                ti = tarfile.TarInfo(arcname)
                ti.size = len(data)
            else:
                ti = tarfile.TarInfo(arcname)
                ti.type = tarfile.DIRTYPE
            ti.mode = mode
            ti.uid = 0
            ti.gid = 0
            ti.uname = 'root'
            ti.gname = 'root'
            ti.mtime = int(time.time())
            if is_file:
                tf.addfile(ti, io.BytesIO(data))
            else:
                tf.addfile(ti)
    return buf.getvalue()


def make_ar(out_path, members):
    """members: list of (name, data_bytes, mode)"""
    with open(out_path, 'wb') as f:
        f.write(b'!<arch>\n')
        for name, data, mode in members:
            name_b = name.encode('ascii')
            if len(name_b) > 16:
                raise ValueError('ar name too long')
            header = (
                name_b.ljust(16) +
                str(int(time.time())).encode().ljust(12) +
                b'0'.ljust(6) +
                b'0'.ljust(6) +
                str(oct(mode)[2:]).encode().ljust(8) +
                str(len(data)).encode().ljust(10) +
                b'`\n'
            )
            f.write(header)
            f.write(data)
            if len(data) % 2:
                f.write(b'\n')


def main():
    build_stage()
    os.makedirs(DIST, exist_ok=True)

    # ---------------- data.tar.gz ----------------
    data_members = []
    for root, dirs, files in os.walk(os.path.join(STAGE, 'usr')):
        dirs.sort()
        files.sort()
        arc = os.path.relpath(root, STAGE).replace('\\', '/')
        if arc != '.':
            data_members.append(('./' + arc + '/', None, 0o755, False))
        for f in files:
            p = os.path.join(root, f)
            rel = './' + os.path.relpath(p, STAGE).replace('\\', '/')
            mode = 0o755 if rel.startswith('./usr/bin/') else 0o644
            data_members.append((rel, p, mode, True))
    data_tar = make_tar(data_members)

    # ---------------- control.tar.gz ----------------
    control_files = [
        ('./control', os.path.join(SKEL, 'DEBIAN', 'control'), 0o644),
        ('./postinst', os.path.join(SKEL, 'DEBIAN', 'postinst'), 0o755),
        ('./prerm', os.path.join(SKEL, 'DEBIAN', 'prerm'), 0o755),
        ('./md5sums', md5_text(), 0o644),
    ]
    control_tar = make_tar([(n, s, m, True) for n, s, m in control_files])

    # ---------------- deb ----------------
    deb_path = os.path.join(DIST, DEB_NAME)
    make_ar(deb_path, [
        ('debian-binary', b'2.0\n', 0o644),
        ('control.tar.gz', control_tar, 0o644),
        ('data.tar.gz', data_tar, 0o644),
    ])
    print('DEB:', deb_path, os.path.getsize(deb_path), 'bytes')

    # ---------------- tarball（免 root 通用包） ----------------
    # 结构与 install.sh 的期望一致：README-linux.md + icons/<size>x<size>/apps/…
    tar_path = os.path.join(DIST, TAR_NAME)
    with tarfile.open(tar_path, 'w:gz', format=tarfile.GNU_FORMAT) as tf:
        members = [
            ('dsh-desktop',     os.path.join(LINUX, 'dsh-desktop'),    0o755),
            ('dsh-desktop.py',  os.path.join(LINUX, 'dsh-desktop.py'), 0o644),
            ('dsh-desktop.png', os.path.join(LINUX, 'dsh-desktop.png'), 0o644),
            ('install.sh',      os.path.join(LINUX, 'install.sh'),     0o755),
            ('README-linux.md', os.path.join(LINUX, 'README.md'),      0o644),
        ]
        for arcname, src, mode in members:
            ti = tf.gettarinfo(src, arcname=arcname)
            ti.uid = 0
            ti.gid = 0
            ti.uname = 'root'
            ti.gname = 'root'
            ti.mode = mode
            with open(src, 'rb') as fp:
                tf.addfile(ti, fp)
        for root, _dirs, files in os.walk(ICONS):
            for f in files:
                p = os.path.join(root, f)
                rel = os.path.relpath(p, ICONS).replace('\\', '/')
                ti = tf.gettarinfo(p, arcname='icons/' + rel)
                ti.uid = 0
                ti.gid = 0
                ti.mode = 0o644
                with open(p, 'rb') as fp:
                    tf.addfile(ti, fp)
    print('TAR:', tar_path, os.path.getsize(tar_path), 'bytes')


if __name__ == '__main__':
    main()
