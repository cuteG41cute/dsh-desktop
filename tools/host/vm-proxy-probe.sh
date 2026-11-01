#!/bin/bash
# 从虚拟机测：能不能连到本机中继、能不能通过它访问 GitHub（对比直连）
set -u
HOST_IP=172.22.144.1
PORT=7891
export HOME=/home/twinblade

echo '== 0. 虚拟机自己的网络'
ip route 2>/dev/null | head -3
echo "  本机(宿主)地址取自默认网关之外，按约定用 $HOST_IP"

echo
echo '== 1. TCP 可达性（能不能连上中继端口）'
timeout 6 python3 - "$HOST_IP" "$PORT" <<'PY'
import socket, sys, time
host, port = sys.argv[1], int(sys.argv[2])
t0 = time.time()
try:
    s = socket.create_connection((host, port), timeout=5)
    s.close()
    print('  OK  %.0f ms' % ((time.time() - t0) * 1000))
except Exception as exc:
    print('  FAIL', exc)
PY

echo
echo '== 2. 通过代理访问（-x）'
for u in https://api.github.com https://raw.githubusercontent.com https://codeload.github.com; do
  code=$(timeout 25 curl -s -o /dev/null -w '%{http_code} %{time_total}s' -x "http://$HOST_IP:$PORT" "$u" 2>/dev/null)
  echo "  proxy  $u -> ${code:-超时/失败}"
done

echo
echo '== 3. 不走代理直连（对照）'
for u in https://api.github.com https://raw.githubusercontent.com https://codeload.github.com; do
  code=$(timeout 20 curl -s -o /dev/null -w '%{http_code} %{time_total}s' --noproxy '*' "$u" 2>/dev/null)
  echo "  direct $u -> ${code:-超时/失败}"
done

echo
echo '== 4. 换一个真实文件试试（memory-db 的 raw package.json 走代理）'
timeout 25 curl -s -x "http://$HOST_IP:$PORT" -o /tmp/mem-pkg.json -w '  code=%{http_code} size=%{size_download}\n' \
  https://raw.githubusercontent.com/cuteG41cute/dsh-memory-db/main/static/package.json 2>/dev/null
head -c 80 /tmp/mem-pkg.json 2>/dev/null; echo
