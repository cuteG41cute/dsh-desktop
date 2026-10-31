"""Print every design rule that paints a gradient/decorative background on cards or shell.

这些是"主题专属皮肤"（水晶的斜面高光、液态玻璃的流动高光等），GTK 侧原来全是纯色，
所以 crystal/liquid 这些主题的像素差特别大。
"""
import io
import re

S = 'dsh-desktop/linux/manager/design/styles.css'
s = io.open(S, encoding='utf-8').read()

rules = re.findall(r'([^{}]+)\{([^{}]*)\}', s)
for sel, body in rules:
    if 'gradient' not in body:
        continue
    sel = ' '.join(sel.split())
    if not any(k in sel for k in ('.card', '.quick-action', '.app-shell', '.topbar',
                                  '.sidebar', '.btn', '.runtime', '.instance-item',
                                  '.log-card', '.meta-main', '.brand')):
        continue
    print('SELECTOR: %s' % sel[:110])
    for decl in body.split(';'):
        if 'gradient' in decl or 'shadow' in decl or 'filter' in decl or decl.strip().startswith('background'):
            print('    %s' % decl.strip()[:150])
    print()
