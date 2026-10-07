// 把 tools/preview-probe/preview-tools.js（镜像）同步进 App.cs 的
// PreviewToolsScript() 内嵌 verbatim 字符串（真身）。
//
// 用法（在本目录执行）：
//   node embed.mjs            # 只检查：内嵌副本与镜像是否逐字节一致
//   node embed.mjs --write    # 用镜像覆盖内嵌副本
//   node embed.mjs --expect <文件>   # 额外对比指定文件（例如 git 里的旧版镜像）
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, '..', '..', 'App.cs');
const JS = join(here, 'preview-tools.js');
const args = process.argv.slice(2);
const WRITE = args.includes('--write');
const EXPECT = args.indexOf('--expect') >= 0 ? args[args.indexOf('--expect') + 1] : '';

function fail(msg) { console.error('× ' + msg); process.exit(1); }

const app = readFileSync(APP, 'utf8');
const js = readFileSync(JS, 'utf8');

const fnAt = app.indexOf('private static string PreviewToolsScript()');
if (fnAt < 0) fail('App.cs 里找不到 PreviewToolsScript()');
const litAt = app.indexOf('@"', fnAt);
if (litAt < 0) fail('PreviewToolsScript() 里找不到 @" 起始');
const start = litAt + 2;

let i = start, end = -1;
while (i < app.length) {
  if (app[i] === '"') {
    if (app[i + 1] === '"') { i += 2; continue; }   // "" 是转义后的引号
    end = i; break;
  }
  i++;
}
if (end < 0) fail('找不到 verbatim 字符串的结束引号');

const raw = app.slice(start, end);
const embedded = raw.replace(/""/g, '"');
const reported = embedded.replace(/^\n/, '');       // @" 后面紧跟的换行不属于脚本本体
const normalized = (s) => s.replace(/\r\n/g, '\n').replace(/\s+$/, '');

console.log('App.cs        : ' + APP);
console.log('镜像          : ' + JS + '  (' + js.length + ' 字符, ' + js.split('\n').length + ' 行)');
console.log('内嵌副本      : ' + embedded.length + ' 字符, ' + embedded.split('\n').length + ' 行');

if (EXPECT) {
  const exp = readFileSync(resolve(EXPECT), 'utf8');
  console.log('对比文件      : ' + resolve(EXPECT));
  const ra = normalized(reported), rb = normalized(exp);
  if (ra === rb) console.log('√ 内嵌副本与对比文件一致');
  else {
    console.log('× 内嵌副本与对比文件不一致');
    const a = ra.split('\n'), b = rb.split('\n');
    for (let k = 0; k < Math.max(a.length, b.length); k++) {
      if (a[k] !== b[k]) {
        console.log('  第一处差异: 第 ' + (k + 1) + ' 行 (内嵌 ' + a.length + ' 行 / 对比 ' + b.length + ' 行)');
        console.log('    内嵌: ' + JSON.stringify((a[k] ?? '').slice(0, 120)));
        console.log('    对比: ' + JSON.stringify((b[k] ?? '').slice(0, 120)));
        break;
      }
    }
  }
}

const same = normalized(reported) === normalized(js);
if (!WRITE) {
  if (same) { console.log('√ 内嵌副本与镜像一致，无需同步'); process.exit(0); }
  console.log('× 内嵌副本与镜像不一致；用 --write 同步');
  const a = normalized(reported).split('\n'), b = normalized(js).split('\n');
  for (let k = 0; k < Math.max(a.length, b.length); k++) {
    if (a[k] !== b[k]) {
      console.log('  第一处差异: 第 ' + (k + 1) + ' 行');
      console.log('    内嵌: ' + JSON.stringify((a[k] ?? '').slice(0, 100)));
      console.log('    镜像: ' + JSON.stringify((b[k] ?? '').slice(0, 100)));
      break;
    }
  }
  process.exit(2);
}

const next = '\n' + js.replace(/"/g, '""');
writeFileSync(APP, app.slice(0, start) + next + app.slice(end), 'utf8');
console.log('√ 已把镜像写入 App.cs（' + next.length + ' 字节内嵌）');
