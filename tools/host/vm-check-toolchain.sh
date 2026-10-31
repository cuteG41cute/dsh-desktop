#!/bin/bash
# What the package install actually delivered.
for t in spectacle convert xdotool smbd; do
  printf "%-12s %s\n" "$t" "$(command -v "$t" || echo MISSING)"
done
python3 - <<'PY'
import gi
try:
    gi.require_foreign("cairo")
    print("gi-cairo OK")
except Exception as e:
    print("gi-cairo MISSING:", e)
for m in ("numpy", "PIL", "cairo", "dbus"):
    try:
        mod = __import__(m)
        print(m, getattr(mod, "__version__", "ok"))
    except Exception as e:
        print(m, "MISSING")
PY
echo "== inter font files"
fc-list 2>/dev/null | grep -ci 'inter' || echo 0
echo "== themes count"
ls /home/twinblade/dsh-dev/dsh_manager/theme/*.css 2>/dev/null | wc -l
