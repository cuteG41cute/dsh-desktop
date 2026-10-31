#!/bin/bash
# Find how the installed dsh-manager starts, and what GUI procs are running.
echo "== entry point"
command -v dsh-manager || echo "no dsh-manager in PATH"
dpkg -L dsh-manager 2>/dev/null | grep -E '/(bin|sbin)/|\.desktop$|\.py$' | head -20
echo "== gui procs"
ps -eo pid,etime,cmd --sort=pid | grep -Ei 'dsh|python3|kwin|plasmashell' | grep -v grep | head -12
echo "== version"
dsh-manager --version 2>&1 | head -3
