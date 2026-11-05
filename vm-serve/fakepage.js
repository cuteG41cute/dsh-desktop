const http = require("http");
const fs = require("fs");
const path = require("path");

const LOG = "C:\\Users\\User\\fakepage.log";
const CMD = "C:\\Users\\User\\fakepage.cmd.txt";
const DIR = "C:\\Users\\User\\fakepage";
try { fs.mkdirSync(DIR, { recursive: true }); } catch (e) {}

const fileA = path.join(DIR, "a.txt");
const fileB = path.join(DIR, "b.txt");
if (!fs.existsSync(fileA)) fs.writeFileSync(fileA, "hello from fake page\n");
if (!fs.existsSync(fileB)) fs.writeFileSync(fileB, "second file\n");

function jsPath(p) { return p.replace(/\\/g, "\\\\"); }

const page = `<!doctype html><meta charset="utf-8">
<title>fake dsh page</title>
<style>
  html,body{margin:0;font-family:Segoe UI,Microsoft YaHei;}
  #wrap{display:flex;height:100vh}
  .rIfSMq_frame{height:100%;min-height:0;position:relative;overflow:hidden;flex:1}
  .rIfSMq_scrollport{height:100%;overflow:auto;background:#eef}
  .rIfSMq_surface{max-width:none;width:max-content}
  #im{width:2000px;height:2000px;display:block;image-rendering:pixelated}
  ul{width:280px;margin:0;padding:8px;list-style:none;background:#fafafa;overflow:auto}
  li{border:1px solid #ccc;border-radius:6px;padding:8px;margin:6px 0;cursor:grab;background:#fff}
</style>
<div id="wrap">
  <div class="rIfSMq_frame" data-document-zoom-mode="fixed" style="--document-zoom:1;--document-zoom-width:2000px">
    <div class="rIfSMq_scrollport" id="sp">
      <div class="rIfSMq_surface" id="sf"><img id="im" src="/big.png" draggable="false"></div>
    </div>
  </div>
  <ul id="files">
    <li data-files-entry="file" data-files-path="${jsPath(fileA)}">a.txt</li>
    <li data-files-entry="file" data-files-path="${jsPath(fileB)}">b.txt</li>
    <li data-files-entry="directory" data-files-path="${jsPath(DIR)}">fakepage/</li>
  </ul>
</div>
<script>
const sp = document.getElementById('sp');
const im = document.getElementById('im');
function log(q){ try { fetch('/log?' + q); } catch(e){} }
sp.addEventListener('scroll', () => log('sl=' + Math.round(sp.scrollLeft) + '&st=' + Math.round(sp.scrollTop)));
log('loaded=1&w=' + sp.clientWidth + '&sw=' + sp.scrollWidth);

let last = '';
setInterval(async () => {
  try {
    const r = await fetch('/cmd', { cache: 'no-store' });
    const cmd = (await r.text()).trim();
    if (!cmd || cmd === last) return;
    last = cmd;
    log('event=cmd&raw=' + encodeURIComponent(cmd));
    const parts = cmd.split(/\\s+/);
    if (parts[0] === 'pan') {
      const x1 = Number(parts[1]), y1 = Number(parts[2]), x2 = Number(parts[3]), y2 = Number(parts[4]);
      const before = Math.round(sp.scrollLeft) + ',' + Math.round(sp.scrollTop);
      const fire = (type, x, y) => {
        const ev = new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: 1, pointerId: 1, isPrimary: true, pointerType: 'mouse' });
        (type === 'pointerdown' ? im : document).dispatchEvent(ev);
      };
      fire('pointerdown', x1, y1);
      for (let i = 1; i <= 8; i++) fire('pointermove', x1 + (x2 - x1) * i / 8, y1 + (y2 - y1) * i / 8);
      fire('pointerup', x2, y2);
      log('event=pan-done&before=' + before + '&after=' + Math.round(sp.scrollLeft) + ',' + Math.round(sp.scrollTop));
    } else if (parts[0] === 'rowdrag') {
      const li = document.querySelector('li[data-files-entry="file"]');
      if (li) {
        const r = li.getBoundingClientRect();
        const cx = Math.round(r.left + 20), cy = Math.round(r.top + 10);
        li.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: cx, clientY: cy, button: 0, buttons: 1 }));
        for (let i = 1; i <= 6; i++) {
          document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: cx - i * 6, clientY: cy - i * 4, buttons: 1 }));
        }
        log('event=rowdrag-done&x=' + cx + '&y=' + cy);
      } else {
        log('event=rowdrag-noli');
      }
    }
  } catch (e) {}
}, 700);
</script>`;

const bigPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64"
);

http.createServer((req, res) => {
  const u = new URL(req.url, "http://127.0.0.1");
  if (u.pathname === "/log") {
    try { fs.appendFileSync(LOG, new Date().toISOString() + " " + u.search + "\n"); } catch (e) {}
    res.writeHead(200); res.end("ok"); return;
  }
  if (u.pathname === "/cmd") {
    let c = "";
    try { if (fs.existsSync(CMD)) c = fs.readFileSync(CMD, "utf8"); } catch (e) {}
    res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" });
    res.end(c); return;
  }
  if (u.pathname === "/big.png") {
    res.writeHead(200, { "Content-Type": "image/png" });
    res.end(bigPng); return;
  }
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(page);
}).listen(3081, "127.0.0.1", () => {
  try { fs.appendFileSync(LOG, new Date().toISOString() + " server started\n"); } catch (e) {}
});
