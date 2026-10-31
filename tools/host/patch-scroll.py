"""Patch 19: 窗口比设计稿窄时允许横向滚动，而不是把内容裁掉。

设计稿画布 1392×852（1440×900 减留白），而虚拟机的屏幕只有 1280×720。
`_fit_to_screen` 会把窗口缩到 1220 宽，但我把卡片宽度按设计稿钉死了
（控制卡 402、实例卡 664），总宽 1392 > 1220，横向 policy=NEVER 就直接裁掉
右半边（实测：截图里「打开窗口」被切、快捷控制卡完全看不见）。

保持设计稿的精确几何（像素门禁要求），同时把"放不下时的退路"打开：
内容区允许横向滚动条出现。
"""
import io

GUI = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    ("        self.dash_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)",
     "        # 布局是按设计稿 1392 宽钉死的；窗口更窄时给横向滚动条，"
     "别把右半边裁掉。\n"
     "        self.dash_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)"),
    ("        self.settings_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)",
     "        self.settings_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)"),
]


def main():
    s = io.open(GUI, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(GUI, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
