import http.server, socketserver, os, json, base64, datetime, threading

ROOT = r"C:\Users\twinblade\Documents\deeepseek harness\vm-serve"
REPORT = r"C:\Users\twinblade\Documents\deeepseek harness\vm-report"

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def do_POST(self):
        if not self.path.startswith("/report"):
            self.send_error(404); return
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            data = json.loads(body.decode('utf-8', 'replace'))
        except Exception:
            data = {"raw": body[:2000].decode('utf-8', 'replace')}
        screen = data.pop("screen", "") or ""
        os.makedirs(REPORT, exist_ok=True)
        with open(os.path.join(REPORT, f"report-{ts}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if screen:
            try:
                with open(os.path.join(REPORT, f"screen-{ts}.png"), "wb") as f:
                    f.write(base64.b64decode(screen))
            except Exception as e:
                print("screen decode failed:", e)
        print(f"[report] {ts} from {self.client_address[0]} host={data.get('host')} installed={data.get('installed')} ver={data.get('version')}")
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} {fmt % args}")

os.makedirs(ROOT, exist_ok=True); os.makedirs(REPORT, exist_ok=True)
socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", 8899), H) as httpd:
    print("serving", ROOT, "on 0.0.0.0:8899")
    httpd.serve_forever()
