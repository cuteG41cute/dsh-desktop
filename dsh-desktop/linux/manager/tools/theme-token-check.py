"""复刻保真度 gate：设计稿 → themes.json → GTK 主题 CSS / 背景图，逐项对得上。

这条 gate 解决的问题是"看着差不多"：手抄色值一定会错一两处，而错了肉眼很难发现。
这里做三件事：
  1. 重新跑一遍 extract-themes 的解析，结果必须与已提交的 themes.json 完全一致
     （设计稿改了而我们没重新生成 → 这里会红）；
  2. 每一份 theme/<主题>-<日/夜>.css 里，每个令牌的值都要以字面量出现
     （颜色、圆角、阴影一个都不许漏），且不能残留未替换的 $(占位符)；
  3. 背景图齐全（14 张，非空），索引里 7 套主题 × 日/夜 = 14 个变体。

跑法：python dsh-desktop/linux/manager/tools/theme-token-check.py
"""
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGER = os.path.dirname(HERE)
PKG = os.path.join(MANAGER, 'dsh_manager')
THEMES_JSON = os.path.join(PKG, 'themes.json')
THEME_DIR = os.path.join(PKG, 'theme')
BG_DIR = os.path.join(PKG, 'backgrounds')


def load_extractor():
    spec = importlib.util.spec_from_file_location('extract_themes',
                                                  os.path.join(HERE, 'extract-themes.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strip_css_comments(text):
    """检查 GTK 不认的属性前，先把 /* */ 注释剥掉（否则注释里的
    `gap:` 之类会被误报成属性）。"""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def main():
    checks = []
    with open(THEMES_JSON, encoding='utf-8') as fh:
        payload = json.load(fh)
    values = payload['values']
    tokens = payload['tokens']

    # ---- 1) 设计稿 ↔ themes.json ----
    extractor = load_extractor()
    with open(extractor.DESIGN_CSS, encoding='utf-8') as fh:
        fresh = extractor.collect(extractor.parse_rules(fh.read()))
    stale = [key for key in values if values[key] != fresh.get(key)]
    missing = [key for key in fresh if key not in values]
    checks.append(('themes.json 与 design/styles.css 一致（14 组）',
                   not stale and not missing))

    # ---- 2) 每份 GTK 主题 CSS ----
    index_path = os.path.join(THEME_DIR, 'index.json')
    checks.append(('主题索引存在', os.path.exists(index_path)))
    index = {}
    if os.path.exists(index_path):
        with open(index_path, encoding='utf-8') as fh:
            index = json.load(fh)
    checks.append(('索引里有 7 套主题 / 14 个变体',
                   len(index.get('order', [])) == 7 and len(index.get('variants', [])) == 14))

    bad = []
    for key, token_values in sorted(values.items()):
        path = os.path.join(THEME_DIR, '%s.css' % key)
        if not os.path.exists(path):
            bad.append('%s: 缺 CSS' % key)
            continue
        with open(path, encoding='utf-8') as fh:
            css = fh.read()
        if '$(' in css:
            bad.append('%s: 残留占位符' % key)
        for token in tokens:
            if token not in token_values:
                continue
            value = token_values[token]
            if value not in css:
                bad.append('%s: 缺 %s=%s' % (key, token, value))
        # 背景图引用必须指向自己的那两张里的一张
        if 'backgrounds/%s.png' % key not in css:
            bad.append('%s: 背景图引用不对' % key)
        # GTK3 不支持的写法：宁可在 gate 里红，也不要在用户桌面上悄悄丢主题
        for banned in ('var(--', 'backdrop-filter:', 'letter-spacing:', 'display: grid',
                       'display:flex', 'display: flex', 'gap:'):
            hit = [line for line in css.splitlines()
                   if banned in line and not line.strip().startswith('*')]
            if hit:
                bad.append('%s: 用了 GTK3 不支持的写法 %s' % (key, banned))
        if re.search(r'font-weight: \d', css):
            bad.append('%s: font-weight 还是数值形态' % key)
        # @define-color 的值必须是颜色：把这行写成 121,104,232 或 20px 会让
        # GTK 判定整份样式表非法 → 界面完全没主题（1.3.0 就是这么裸奔的）
        for line in css.splitlines():
            line = line.strip()
            if not line.startswith('@define-color'):
                continue
            parts = line.rstrip(';').split(None, 2)
            if len(parts) < 3:
                bad.append('%s: @define-color 写法不完整 %s' % (key, line[:40]))
                continue
            name, value = parts[1], parts[2].strip()
            if not re.match(r'^[a-z0-9_]+$', name):
                bad.append('%s: 颜色名不合法 %s' % (key, name))
            if not re.match(r'^(#[0-9a-fA-F]{3,8}|rgba?\(|@)', value):
                bad.append('%s: %s 的值不是颜色：%s' % (key, name, value[:40]))
        if 'transition:' not in css:
            bad.append('%s: 没有 transition（动效丢了）' % key)
        if css.count('{') != css.count('}'):
            bad.append('%s: 花括号不配对' % key)
    checks.append(('14 份主题 CSS 的令牌与背景引用全部对上', not bad))

    # ---- 3) 背景图 ----
    missing_bg = []
    for key in values:
        path = os.path.join(BG_DIR, '%s.png' % key)
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            missing_bg.append(key)
    checks.append(('14 张背景图齐全（每张 > 1KB）', not missing_bg))

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(('  OK   ' if ok else '  FAIL ') + name)
    if bad:
        for line in bad[:10]:
            print('         ' + line)
    if missing_bg:
        print('         缺背景：' + ', '.join(missing_bg))
    print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                                len(checks) - len(failed), len(checks)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
