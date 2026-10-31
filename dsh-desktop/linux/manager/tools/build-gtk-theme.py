"""把 themes.json（从设计稿抽出的令牌）灌进 GTK 主题模板，生成 14 份主题 CSS。

生成的产物是 `dsh_manager/theme/<主题>-<日/夜>.css`，管理器按设置加载其中一份。
为什么不手写 14 份：手抄必错色值，而"复刻"最怕"看着差不多"。
再配 tools/theme-token-check.py 反向校验：生成结果里的每个色值都要能在设计稿里找到。

跑法：python dsh-desktop/linux/manager/tools/build-gtk-theme.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGER = os.path.dirname(HERE)
THEMES_JSON = os.path.join(MANAGER, 'dsh_manager', 'themes.json')
TEMPLATE = os.path.join(HERE, 'gtk-theme-template.css.in')
OUT_DIR = os.path.join(MANAGER, 'dsh_manager', 'theme')

# 模板里 $(name) → 令牌名；两处特殊：$(bg-image) 指向渲染好的背景 PNG、$(radius)/(app-radius)
PLACEHOLDERS = [
    'bg', 'bg2', 'app', 'sidebar', 'topbar', 'card', 'card-solid', 'text',
    'muted', 'subtle', 'border', 'inner-border', 'accent', 'accent2',
    'accent-rgb', 'accent-soft', 'on-accent', 'hover', 'success', 'success-rgb', 'danger',
    'radius', 'app-radius', 'shadow', 'card-shadow',
]

HEADER = """/* 自动生成，请勿手改：来源 design/styles.css（{theme} / {mode}）
 * 生成脚本：tools/build-gtk-theme.py    校验：tools/theme-token-check.py
 */
"""


def load_themes():
    with open(THEMES_JSON, encoding='utf-8') as fh:
        return json.load(fh)


# 只有这些令牌是"颜色"，才能写进 @define-color；
# 其余（radius / shadow / *-rgb）写进去会让 GTK 解析整份样式表失败（踩过：
#   @define-color dsh_accent_rgb 121,104,232;  → 整个文件被拒，界面全裸奔）。
COLOR_TOKENS = ['bg', 'bg2', 'app', 'sidebar', 'topbar', 'card', 'card-solid',
                'text', 'muted', 'subtle', 'border', 'inner-border', 'accent',
                'accent2', 'accent-soft', 'on-accent', 'hover', 'success', 'danger']

# ---------------------------------------------------------------------------
# 主题专属"皮肤"：设计稿里除了色板，还有几条按主题写死的装饰规则。
# 原来 GTK 侧一律纯色，于是 crystal（水晶）主题差得最远 —— 它的卡片是
# `linear-gradient(135deg, rgba(255,255,255,.62), var(--card))` 加内嵌高光。
# 这里按主题追加到生成文件末尾（后写覆盖前面），色值仍走令牌替换。
THEME_SKINS = {
    'crystal': [
        ('.card, .quick-action', [
            # 设计稿用的是 background 简写（渐变直接盖掉底色）；GTK 里两者同时存在时
            # 渐变会**叠在** background-color 上，半透明色被算两次 → 卡片明显偏亮。
            # 所以必须先把底色清掉。
            'background-color: transparent;',
            'background-image: linear-gradient(135deg, rgba(255, 255, 255, .62), $(card));',
            'box-shadow: inset 2px 2px 0 rgba(255, 255, 255, .35), $(card-shadow);',
        ]),
    ],
}


def render(template, key, values, all_values=None):
    css = HEADER.format(theme=values.get('label', key), mode=values.get('hint', key))
    body = template
    if '*/' in body:                      # 模板头注释是给维护者看的，不进产物
        body = body.split('*/', 1)[1]
    body = body.replace('$(bg-image)', 'url("../backgrounds/%s.png")' % key)
    for name in PLACEHOLDERS:
        if name not in values:
            raise SystemExit('FAIL: %s 缺少令牌 %s' % (key, name))
        body = body.replace('$(%s)' % name, values[name])
    leftover = [piece for piece in body.split('$(') if piece[:1].isalpha() and ')' in piece[:40]]
    if leftover:
        raise SystemExit('FAIL: %s 模板里还有没替换的占位符：%s'
                         % (key, ['$(' + piece.split(')')[0] + ')' for piece in leftover[:5]]))
    # GTK3 的 font-weight 只有 normal/bold 两档（数值权重取决于字体家族，Pango 会自己取整）；
    # 设计稿里的 550/600/650/680/750 统一归到 bold / normal，避免解析器对数值形态挑剔。
    def _weight(match):
        return 'font-weight: bold' if int(match.group(1)) >= 600 else 'font-weight: normal'

    body = re.sub(r'font-weight: (\d{3})', _weight, body)
    palette = ['/* 调色板：设计稿里属于"颜色"的令牌（其余是长度/阴影，见下方注释） */']
    for name in PLACEHOLDERS:
        if name in COLOR_TOKENS:
            palette.append('@define-color dsh_%s %s;' % (name.replace('-', '_'), values[name]))
    palette.append('/* 非颜色令牌（供核对，不能写进 @define-color）： */')
    for name in PLACEHOLDERS:
        if name not in COLOR_TOKENS:
            palette.append('/*   %s = %s */' % (name, values[name]))
    # 主题菜单里的色点要显示"每套主题自己的强调色"，所以把 7 套的 day 强调色都写进来
    swatches = ['/* 主题菜单色点（每套主题 day 的强调色） */']
    for name, values_day in sorted((all_values or {}).items()):
        if not name.endswith('-day'):
            continue
        swatches.append('.swatch-%s { background-color: %s; }'
                        % (name[:-4], values_day.get('accent', '#888888')))
    # 主题专属皮肤（最后追加，覆盖前面的纯色规则）
    skin = THEME_SKINS.get(key.split('-')[0])
    if skin:
        extra = ['', '/* 主题专属皮肤：对应 design/styles.css 里 body[data-theme="%s"] 的规则 */'
                 % key.split('-')[0]]
        for sel, decls in skin:
            extra.append('%s {' % sel)
            for decl in decls:
                extra.append('  ' + decl.replace('$(card)', values['card'])
                                        .replace('$(card-shadow)', values['card-shadow']))
            extra.append('}')
        body = body.rstrip('\n') + '\n' + '\n'.join(extra) + '\n'
    return css + '\n'.join(palette) + '\n\n' + '\n'.join(swatches) + '\n\n' + body


def main():
    payload = load_themes()
    with open(TEMPLATE, encoding='utf-8') as fh:
        template = fh.read()
    os.makedirs(OUT_DIR, exist_ok=True)
    written = []
    for key, values in sorted(payload['values'].items()):
        css = render(template, key, values, payload['values'])
        path = os.path.join(OUT_DIR, '%s.css' % key)
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(css)
        written.append((key, len(css)))
    # 附带一份索引，管理器用它列出可选主题（顺序 = 设计稿顺序）
    index = {
        'order': payload['order'],
        'variants': sorted(payload['values'].keys()),
        'labels': {key: [payload['values'][key]['label'], payload['values'][key]['hint']]
                   for key in payload['values']},
    }
    with open(os.path.join(OUT_DIR, 'index.json'), 'w', encoding='utf-8') as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write('\n')
    print('generated %d theme files in %s' % (len(written), os.path.relpath(OUT_DIR, MANAGER)))
    for key, size in written[:3] + written[-2:]:
        print('  %-14s %6d bytes' % (key, size))
    return 0


if __name__ == '__main__':
    sys.exit(main())
