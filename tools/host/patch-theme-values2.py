"""Patch #2: GTK3 的 min-height 是**内容盒**，设计稿的 height 是 border-box。

所以凡是设计稿给了 height 的地方，GTK 的 min-height 必须减去 padding 和 border，
否则每个控件都会比设计稿高出 10~28px（实测：实例行 79 vs 61，快捷按钮 110 vs 82）。

另外把顶栏两个控件的尺寸钉到设计稿（theme-trigger 97.5×34、mode-toggle 57×30）。
"""
import io

P = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

SUBS = [
    # 61 = min-height 43 + padding 8*2 + border 1*2
    (".instance-item { min-height: 61px; }   /* 设计稿 61px */",
     ".instance-item { min-height: 43px; padding: 8px 10px; }   /* 设计稿 61px(border-box) */"),
    # 82 = min-height 54 + padding 13*2 + border 1*2
    ("  padding: 13px;\n  min-height: 82px;   /* 设计稿 .quick-action: height 82px */",
     "  padding: 13px;\n  min-height: 54px;   /* 设计稿 82px(border-box) */"),
    # 38 = min-height 36 + border 1*2
    ("  min-height: 38px;\n  padding: 0 15px;   /* 设计稿 .btn: 0 15px */",
     "  min-height: 36px;\n  padding: 0 15px;   /* 设计稿 .btn: 38px border-box */"),
    ("  min-height: 45px; padding: 0 18px; border-bottom: 1px solid $(inner-border); }",
     "  min-height: 44px; padding: 0 18px; border-bottom: 1px solid $(inner-border); }"),
    (".topbar {",
     ".topbar {\n  min-height: 65px;   /* 设计稿 66px 含 1px 下边框 */"),
]


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)

    # 追加一段"尺寸校正"，避免和上面的规则互相覆盖
    tail = """
/* ==========================================================================
 * 尺寸校正（1.4.0 像素复刻）
 * GTK3 的 min-height 是内容盒：设计稿 height 含 padding/border，
 * 所以这里把每个控件的 min-height 补成 height - padding - border。
 * ========================================================================== */
.instance-item { min-height: 43px; padding: 8px 10px; }
.quick-action { min-height: 54px; padding: 13px; }
.side-link { min-height: 38px; padding: 0 11px; font-size: 11.5px; }
.new-instance {
  min-height: 34px;
  padding: 1px 6px;
  font-size: 11px;
  border: 1px dashed $(inner-border);
  border-radius: 11px;
}
.btn { min-height: 36px; padding: 0 15px; }
.btn.compact { min-height: 29px; padding: 0 10px; font-size: 9px; }
.btn.compact image { margin-right: 4px; }
.btn-icon { min-width: 36px; padding: 0; }
.icon-btn { min-width: 36px; min-height: 36px; padding: 0; }
.icon-btn.small { min-width: 25px; min-height: 25px; padding: 0; }
.large-avatar { min-width: 48px; min-height: 48px; padding: 0; }
.runtime-icon { padding: 0; }
.quick-icon { padding: 0; }
.instance-avatar { padding: 0; }
.theme-trigger {
  min-height: 32px;
  min-width: 0;
  padding: 0 10px;
  border: 1px solid $(inner-border);
  border-radius: 10px;
  background-color: $(card);
  font-size: 10.5px;
  font-weight: 550;
}
.mode-toggle {
  min-width: 55px;
  min-height: 28px;
  padding: 0;
  border: 1px solid $(inner-border);
  border-radius: 16px;
  background-color: $(card);
  font-size: 10px;
}
.side-caption { padding: 0 11px 8px; font-size: 10px; font-weight: 600; letter-spacing: .08em; }
.runtime { min-height: 54px; padding: 13px 10px; border-radius: 12px; }
.runtime-title { font-size: 10px; font-weight: 600; }
.runtime-sub { font-size: 8.5px; }
.page-footer { padding-top: 10px; font-size: 8px; }
.instance-name { font-size: 11.5px; font-weight: 600; }
.instance-sub { font-size: 10px; color: $(muted); }
.side-section-title { font-size: 11px; font-weight: 600; }
"""
    if '尺寸校正（1.4.0 像素复刻）' not in s:
        s = s.rstrip('\n') + '\n' + tail
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
