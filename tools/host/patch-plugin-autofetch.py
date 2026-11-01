"""打开插件对话框时自动拉一次 GitHub，并把"尚未拉取"的提示改准。

上一张截图显示「来源：内置目录（GitHub 上还没有带 dsh-plugin 标签的仓库）」——
其实只是还没拉过（缓存为空），文案误导；而且不该要求用户先点按钮。
"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/gui.py'
PLUG = 'dsh-desktop/linux/manager/dsh_manager/plugins.py'

G_SUBS = [
    ("        fill()\n"
     "        note.set_text('安装后需要重启该实例的服务才会加载：先「停止服务」再「启动服务」。')",
     "        fill()\n"
     "        note.set_text('安装后需要重启该实例的服务才会加载：先「停止服务」再「启动服务」。')\n"
     "        # 打开时自动拉一次（不阻塞界面）：没缓存时列表会先用内置目录，拉到后自动刷新\n"
     "        GLib.timeout_add(200, lambda: (refresh_github(), False)[1])"),
]

P_SUBS = [
    ("    return ('内置目录（GitHub 上还没有带 dsh-plugin 标签的仓库）', '')",
     "    return ('内置目录（尚未从 GitHub 拉取）', '')"),
]


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in G_SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)

    p = io.open(PLUG, encoding='utf-8').read()
    for old, new in P_SUBS:
        if old in p:
            p = p.replace(old, new, 1)
        else:
            missing.append('plugins.py source_info')
    io.open(PLUG, 'w', encoding='utf-8', newline='\n').write(p)
    print('patched, missing: %s' % (missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
