"""从 Kimi 的设计稿（design/styles.css）里抽出 7 套主题 × 日/夜 的颜色令牌。

为什么用脚本抽而不是手抄：手抄一定会错一两个色值，而"复刻"这件事最怕的就是
"看着差不多"。抽出结果落到 themes.json，之后 build-gtk-theme.py 用它生成 GTK 主题，
tools/theme-token-check.py 再反过来把生成结果与设计稿逐项比对。

跑法（仓库根目录）：python dsh-desktop/linux/manager/tools/extract-themes.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGER = os.path.dirname(HERE)
DESIGN_CSS = os.path.join(MANAGER, 'design', 'styles.css')
OUT_JSON = os.path.join(MANAGER, 'dsh_manager', 'themes.json')

THEMES = ['frost', 'liquid', 'crystal', 'flat', 'alpine', 'dawn', 'sea']
THEME_NAMES = {
    'frost': ('毛玻璃', '柔和透明'),
    'liquid': ('液态玻璃', '流动高光'),
    'crystal': ('水晶', '清透棱角'),
    'flat': ('扁平化', '简洁高效'),
    'alpine': ('雪山', '纯净凛冽'),
    'dawn': ('晨光', '温暖轻盈'),
    'sea': ('静海', '沉静深邃'),
}

# 生成 GTK 主题真正用得到的令牌（其余只影响网页里的装饰层）
TOKENS = [
    'bg', 'bg2', 'app', 'sidebar', 'topbar', 'card', 'card-solid', 'text',
    'muted', 'subtle', 'border', 'inner-border', 'accent', 'accent2',
    'accent-rgb', 'accent-soft', 'on-accent', 'hover', 'success',
    'success-rgb', 'danger', 'radius', 'app-radius', 'shadow', 'card-shadow',
]

RULE_RE = re.compile(r'([^{}]+)\{([^{}]*)\}')


def parse_rules(css):
    """返回 [(selector, {prop: value})]；按出现顺序。"""
    rules = []
    for match in RULE_RE.finditer(css):
        selector = ' '.join(match.group(1).split())
        decls = {}
        for part in match.group(2).split(';'):
            if ':' not in part:
                continue
            key, value = part.split(':', 1)
            key, value = key.strip(), value.strip()
            if key:
                decls[key] = value
        rules.append((selector, decls))
    return rules


def is_night(selector):
    return 'data-mode="night"' in selector


def theme_of(selector):
    m = re.search(r'data-theme="([a-z]+)"', selector)
    return m.group(1) if m else None


VAR_RE = re.compile(r'var\(\s*--([a-z0-9-]+)\s*\)')


def resolve_vars(tokens, depth=0):
    """把 var(--x) 展开成实际值。

    设计稿里夜间基础块写了 `--accent-soft: rgba(var(--accent-rgb),.16)` —— 令牌之间
    有引用关系，直接抄下来 GTK 是不认 var() 的。这里按引用展开（带环检测）。
    """
    if depth > 8:
        return dict(tokens)

    def expand(value):
        for _ in range(8):
            m = VAR_RE.search(value)
            if m is None:
                return value
            ref = '--' + m.group(1)
            if ref not in tokens:
                return value
            value = value[:m.start()] + tokens[ref] + value[m.end():]
        return value

    out = {key: expand(value) for key, value in tokens.items()}
    if out != tokens:
        return resolve_vars(out, depth + 1)
    return out


def collect(rules):
    """按 CSS 级联顺序算出每个 (theme, mode) 的最终令牌。"""
    base, night = {}, {}
    theme_day, theme_night = {}, {}
    for selector, decls in rules:
        if not selector.startswith(':root') and 'data-mode' not in selector \
                and 'data-theme' not in selector:
            continue
        tokens = {k: v for k, v in decls.items() if k.startswith('--')}
        if not tokens:
            continue
        theme = theme_of(selector)
        if theme is None:
            if is_night(selector):
                night.update(tokens)
            else:
                base.update(tokens)
        elif is_night(selector):
            theme_night.setdefault(theme, {}).update(tokens)
        else:
            theme_day.setdefault(theme, {}).update(tokens)

    out = {}
    for theme in THEMES:
        for mode in ('day', 'night'):
            merged = dict(base)
            if mode == 'night':
                merged.update(night)
            merged.update(theme_day.get(theme, {}))
            if mode == 'night':
                merged.update(theme_night.get(theme, {}))
            merged = resolve_vars(merged)
            values = {}
            for key in TOKENS:
                token = '--' + key
                if token in merged:
                    values[key] = merged[token]
            values['label'], values['hint'] = THEME_NAMES[theme]
            out['%s-%s' % (theme, mode)] = values
    return out


def main():
    with open(DESIGN_CSS, encoding='utf-8') as fh:
        css = fh.read()
    rules = parse_rules(css)
    themes = collect(rules)

    missing = []
    for key, values in sorted(themes.items()):
        for token in TOKENS:
            if token not in values:
                missing.append('%s 缺 --%s' % (key, token))
    if missing:
        for line in missing[:20]:
            print('  FAIL ' + line)
        print('RESULT: FAIL %d 个令牌缺失' % len(missing))
        return 1

    payload = {
        'source': 'design/styles.css',
        'themes': list(THEMES),
        'order': THEMES,
        'tokens': TOKENS,
        'values': themes,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write('\n')
    print('extracted %d combos × %d tokens -> %s'
          % (len(themes), len(TOKENS), os.path.relpath(OUT_JSON, os.path.dirname(MANAGER))))
    for key in ('frost-day', 'flat-night', 'sea-day'):
        sample = themes[key]
        print('  %-12s accent=%s card=%s text=%s radius=%s'
              % (key, sample['accent'], sample['card'], sample['text'], sample['radius']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
