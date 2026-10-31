// 把设计稿里的 27 个 SVG 图标（<symbol id="i-*">）抽成独立文件，供 GTK 侧载入。
//
// 用法（仓库根）：node dsh-desktop/linux/manager/tools/extract-icons.mjs
// 产物：dsh-desktop/linux/manager/dsh_manager/icons/<name>.svg
//       每个文件都把 stroke 写成 currentColor，运行时替换成主题色即可。
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const MANAGER = join(HERE, '..');
const HTML = join(MANAGER, 'design', 'index.html');
const OUT = join(MANAGER, 'dsh_manager', 'icons');

const html = readFileSync(HTML, 'utf8');
// <symbol id="i-plus" viewBox="0 0 24 24">…</symbol>
const re = /<symbol\s+id="i-([a-z0-9-]+)"([^>]*)>([\s\S]*?)<\/symbol>/g;
mkdirSync(OUT, { recursive: true });

let count = 0;
const names = [];
for (const m of html.matchAll(re)) {
  const name = m[1];
  const attrs = m[2] || '';
  const body = (m[3] || '').trim();
  const viewBox = (attrs.match(/viewBox="([^"]+)"/) || [, '0 0 24 24'])[1];
  const svg = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="${viewBox}"`,
    '     fill="none" stroke="currentColor" stroke-width="1.7"',
    '     stroke-linecap="round" stroke-linejoin="round">',
    `  ${body.replace(/\s*\n\s*/g, ' ')}`,
    '</svg>',
    '',
  ].join('\n');
  writeFileSync(join(OUT, `${name}.svg`), svg);
  names.push(name);
  count += 1;
}
console.log(`RESULT: ${count} icons → ${OUT}`);
console.log('names: ' + names.join(' '));
if (count < 20) {
  console.error('FAIL: 抽到的图标太少，检查 index.html 里的 <symbol> 结构');
  process.exit(1);
}
