"""Patch 5: 侧栏列表高度按内容、顶栏控件尺寸、卡片高度 205。"""
import io

P = 'dsh-desktop/linux/manager/dsh_manager/gui.py'

SUBS = [
    # 侧栏实例列表：ScrolledWindow 给最小内容高 = 行高 61 + 间隔 5
    ("        self.instance_list.show_all()",
     "        self.instance_list.show_all()\n"
     "        # ScrolledWindow 不给最小内容高就只分到 41px，列表被裁掉只剩第一行\n"
     "        try:\n"
     "            rows = max(1, len(instances))\n"
     "            self.side_sw.set_min_content_height(min(rows, 6) * 66 - 5)\n"
     "        except Exception:\n"
     "            pass"),
    # 顶栏主题触发器：垂直居中（否则被拉成顶栏高度 66）
    ("        trigger = Gtk.MenuButton()\n"
     "        trigger.get_style_context().add_class('theme-trigger')",
     "        trigger = Gtk.MenuButton()\n"
     "        trigger.get_style_context().add_class('theme-trigger')\n"
     "        trigger.set_valign(Gtk.Align.CENTER)"),
    # 两张概览卡都钉到设计稿 205 高
    ("        control.set_size_request(402, -1)   # 设计稿 .control-card 402.25",
     "        control.set_size_request(402, 205)   # 设计稿 .control-card 402.25 x 205"),
    ("        info_card.get_style_context().add_class('instance-card')\n"
     "        info_card.set_hexpand(True)",
     "        info_card.get_style_context().add_class('instance-card')\n"
     "        info_card.set_hexpand(True)\n"
     "        info_card.set_size_request(-1, 205)   # 设计稿 .instance-card 205"),
    # 大头像：垂直居中，避免被拉伸成 48x54
    ("        self.chip_avatar = self._chip('--', 'large-avatar', width=48, height=48)",
     "        self.chip_avatar = self._chip('--', 'large-avatar', width=48, height=48,\n"
     "                                      valign=Gtk.Align.CENTER)"),
    # 运行环境卡：内容别把它撑到 82（设计稿 56）
    ("        runtime.set_size_request(-1, 56)",
     "        runtime.set_size_request(-1, 56)\n"
     "        runtime.set_valign(Gtk.Align.CENTER)"),
]


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:70])
            continue
        s = s.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
