"""验证「查看 Token」背后的两个函数：入口地址提取 + 有效性判断（不需要 GTK）。

为什么要 gate：token 藏在日志里、日志可能有几百 KB、服务可能起重过好几次——
取错一条就是给用户一个 401 的地址。这里用假日志和本地 HTTP 服务把六种情况跑一遍。

跑法：python dsh-desktop/linux/manager/tools/token-extract-check.py
"""
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dsh_manager.core import Instance  # noqa: E402

OK_URL = 'http://127.0.0.1:3080/?token=NEWNEWNEW'
OLD_URL = 'http://127.0.0.1:3080/?token=OLDOLDOLD'


def make_instance(prefix):
    return Instance(prefix, {'label': 'test', 'port': '3080'})


def write_log(path, text, age_seconds=0.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))


def case_newest_wins(tmp):
    prefix = os.path.join(tmp, 'inst-newest')
    write_log(os.path.join(prefix, 'logs', 'web.log'),
              'noise\ndsh web: %s\n' % OLD_URL, age_seconds=600)
    write_log(os.path.join(prefix, 'logs', 'server.out.log'),
              'booting\ndsh web: %s\n' % OK_URL)
    url, src, note = make_instance(prefix).web_auth_url()
    return [('最新那份日志里的地址胜出', url == OK_URL),
            ('来源指向 server.out.log', src.endswith('server.out.log')),
            ('说明不是错误文案', '没有带 token' not in note)]


def case_state_log_only(tmp):
    prefix = os.path.join(tmp, 'inst-state')   # 自己的 logs/ 什么都没有
    state = os.path.join(tmp, 'state')
    os.environ['XDG_STATE_HOME'] = state
    write_log(os.path.join(state, 'dsh-desktop', 'logs', 'web.log'),
              'dsh web: %s\n' % OK_URL)
    url, src, _note = make_instance(prefix).web_auth_url()
    os.environ.pop('XDG_STATE_HOME', None)
    return [('只有 ~/.local/state 那份日志时也能找到', url == OK_URL),
            ('来源指向 state 目录', os.path.join('dsh-desktop', 'logs') in src)]


def case_none(tmp):
    prefix = os.path.join(tmp, 'inst-empty')
    os.makedirs(os.path.join(prefix, 'logs'), exist_ok=True)
    url, _src, note = make_instance(prefix).web_auth_url()
    return [('没有日志时返回 None', url is None),
            ('给出可操作的原因', '没有带 token' in note and '启动服务' in note)]


def case_big_log(tmp):
    prefix = os.path.join(tmp, 'inst-big')
    filler = ('[noise] a long line to pad the log file ' * 40 + '\n') * 900   # > 256 KB
    write_log(os.path.join(prefix, 'logs', 'web.log'),
              filler + 'dsh web: %s\n' % OK_URL)
    size = os.path.getsize(os.path.join(prefix, 'logs', 'web.log'))
    url, _src, _note = make_instance(prefix).web_auth_url()
    return [('大日志（%d KB）里也能取到末尾那条' % (size // 1024), url == OK_URL)]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):                      # noqa: N802
        if self.path.startswith('/bad'):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'dsh web authentication required')
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'<html>__DSH_BOOT__</html>')

    def log_message(self, *_args):
        pass


def case_status(tmp):
    srv = HTTPServer(('127.0.0.1', 0), Handler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        inst = make_instance(os.path.join(tmp, 'inst-status'))
        ok_state, ok_detail = inst.auth_url_status('http://127.0.0.1:%d/' % port, timeout=3)
        bad_state, bad_detail = inst.auth_url_status('http://127.0.0.1:%d/bad' % port, timeout=3)
    finally:
        srv.shutdown()
        srv.server_close()
    # 关掉之后再问一次：应判"连不上"
    down_state, down_detail = make_instance(
        os.path.join(tmp, 'inst-status')).auth_url_status('http://127.0.0.1:%d/' % port, timeout=2)
    return [
        ('200 → ok', ok_state == 'ok' and '200' in ok_detail),
        ('401 → expired（并提示重启服务）', bad_state == 'expired' and '重启' in bad_detail),
        ('端口关了 → 判连不上', down_state == '' and '连不上' in down_detail),
    ]


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='token-check-') as tmp:
        checks += case_newest_wins(tmp)
        checks += case_state_log_only(tmp)
        checks += case_none(tmp)
        checks += case_big_log(tmp)
        checks += case_status(tmp)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(('  OK   ' if ok else '  FAIL ') + name)
    print('RESULT: %s %d/%d' % ('PASS' if not failed else 'FAIL',
                                len(checks) - len(failed), len(checks)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
