"""Print the design's CSS variable blocks for the crystal theme (diagnosis helper)."""
import io
import re

S = 'dsh-desktop/linux/manager/design/styles.css'
s = io.open(S, encoding='utf-8').read()

for m in re.finditer(r'body\[data-theme="([a-z]+)"\](?:\[data-mode="(night)"\])?\{([^}]*)\}', s):
    theme, mode, body = m.group(1), m.group(2) or 'day', m.group(3)
    if theme != 'crystal':
        continue
    print('== %s-%s' % (theme, mode))
    for key in ('--card', '--app', '--bg', '--bg2', '--text', '--border', '--card-solid'):
        hit = re.search(re.escape(key) + r':([^;]+);', body)
        print('   %-13s %s' % (key, hit.group(1) if hit else '—'))
    print()

grads = re.findall(r'[^{}]{0,60}\{[^{}]*linear-gradient[^{}]*\}', s)
print('rules containing linear-gradient: %d' % len(grads))
for g in grads[:8]:
    head = g.split('{')[0].strip()
    if 'card' in head or 'app-shell' in head:
        print('  ->', head[:70], '::', g.split('{')[1][:120])
