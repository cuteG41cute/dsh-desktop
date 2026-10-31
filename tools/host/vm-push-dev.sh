#!/bin/bash
# Unpack the uploaded dev tree into ~/dsh-dev and byte-check that gui.py still parses.
set -e
DEV="$HOME/dsh-dev"
rm -rf "$DEV"
mkdir -p "$DEV"
tar xzf /tmp/manager-dev.tgz -C "$DEV"
python3 - <<'PY'
import ast, io, os
path = os.path.expanduser('~/dsh-dev/dsh_manager/gui.py')
raw = open(path, 'rb').read()
try:
    src = raw.decode('utf-8')
except UnicodeDecodeError as exc:
    raise SystemExit('gui.py is not valid UTF-8: %s' % exc)
ast.parse(src)
print('gui.py parse OK, %d chars, %d bytes' % (len(src), len(raw)))
PY
grep -c '_initials' "$DEV/dsh_manager/gui.py"
