"""One-shot patch: align theme template CSS numbers with design/styles.css.

Run from the repo root: python tools/host/patch-theme-values.py
Prints which replacements did not match (so a silent drift can't happen).
"""
import io

P = 'dsh-desktop/linux/manager/tools/gtk-theme-template.css.in'

# (old, new) — every value copied from design/styles.css with its selector noted.
SUBS = [
    (".card {\n  background-color: $(card);\n  border: 1px solid $(border);\n"
     "  border-radius: $(radius);\n  box-shadow: $(card-shadow);\n  padding: 16px 18px;\n}",
     ".card {\n  background-color: $(card);\n  border: 1px solid $(border);\n"
     "  border-radius: $(radius);\n  box-shadow: $(card-shadow);\n"
     "  padding: 18px 20px;   /* 设计稿 .card: 18px 20px */\n}"),
    ("  font-weight: 600;\n  min-height: 38px;\n  padding: 0 14px;\n}",
     "  font-weight: 600;\n  min-height: 38px;\n  padding: 0 15px;   /* 设计稿 .btn: 0 15px */\n}"),
    (".subtle-tag {\n  border-radius: 6px;\n  background-color: $(accent-soft);\n"
     "  color: $(muted);\n  font-size: 9px;\n  padding: 2px 7px;\n}",
     ".subtle-tag {\n  border-radius: 6px;\n  background-color: $(accent-soft);\n"
     "  color: $(muted);\n  font-size: 8px;   /* 设计稿 .subtle-tag */\n  padding: 3px 7px;\n}"),
    ("  color: $(muted);\n  font-size: 9px;\n  padding: 2px 7px;\n}\n"
     ".metric-label { font-size: 9px; color: $(muted); }",
     "  color: $(muted);\n  font-size: 8px;   /* 设计稿 .version-pills span */\n  padding: 3px 7px;\n}\n"
     ".metric-label { font-size: 8.5px; color: $(muted); }"),
    (".control-sub { font-size: 9px; color: $(muted); }",
     ".control-sub { font-size: 8.5px; color: $(muted); }"),
    (".quick-action {\n  background-color: $(card);\n  border: 1px solid $(border);\n"
     "  border-radius: 15px;\n  box-shadow: $(card-shadow);\n  padding: 12px;\n  min-height: 60px;\n}",
     ".quick-action {\n  background-color: $(card);\n  border: 1px solid $(border);\n"
     "  border-radius: 15px;\n  box-shadow: $(card-shadow);\n  padding: 13px;\n"
     "  min-height: 82px;   /* 设计稿 .quick-action: height 82px */\n}"),
    (".quick-title { font-size: 11px; font-weight: 600; color: $(text); }\n"
     ".quick-sub { font-size: 9px; color: $(muted); }",
     ".quick-title { font-size: 10.5px; font-weight: 600; color: $(text); }\n"
     ".quick-sub { font-size: 8px; color: $(muted); }"),
    (".log-header { border-bottom: 1px solid $(inner-border); padding-bottom: 10px; }",
     ".log-header { min-height: 45px; padding: 0 18px;"
     " border-bottom: 1px solid $(inner-border); }"),
    ('.log-line {\n  font-family: Consolas, "DejaVu Sans Mono", monospace;\n'
     "  font-size: 9px;\n  color: $(text);\n}",
     '.log-line {\n  font-family: Consolas, "DejaVu Sans Mono", monospace;\n'
     "  font-size: 8.5px;\n  min-height: 27px;\n  color: $(text);\n}"),
    (".page-footer { color: $(subtle); font-size: 9px; }",
     ".page-footer { color: $(subtle); font-size: 8px; padding-top: 12px; }"),
    (".instance-item { min-height: 57px; }",
     ".instance-item { min-height: 61px; }   /* 设计稿 61px */"),
    (".sidebar { padding: 24px 16px 18px; }",
     ".sidebar { padding: 26px 16px 18px; }   /* 设计稿 .sidebar */"),
]


def main():
    s = io.open(P, encoding='utf-8').read()
    missing = []
    for old, new in SUBS:
        if old not in s:
            missing.append(old.split('\n')[0][:60])
            continue
        s = s.replace(old, new, 1)
    io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
    print('patched %d/%d; missing: %s' % (len(SUBS) - len(missing), len(SUBS),
                                         missing if missing else 'none'))
    return 0 if not missing else 1


if __name__ == '__main__':
    raise SystemExit(main())
