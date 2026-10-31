#!/bin/bash
# Can Python/GTK load an SVG through GdkPixbuf on this box?
set -u
cat > /tmp/probe-icon.svg <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24"
     fill="none" stroke="#7846ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 5v14M5 12h14"/>
</svg>
SVG

python3 - <<'PY'
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf
try:
    pb = GdkPixbuf.Pixbuf.new_from_file('/tmp/probe-icon.svg')
    print('SVG via GdkPixbuf: OK', pb.get_width(), 'x', pb.get_height(), 'alpha=', pb.get_has_alpha())
except Exception as exc:
    print('SVG via GdkPixbuf: FAIL', type(exc).__name__, exc)
try:
    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale('/tmp/probe-icon.svg', 20, 20, True)
    print('scaled load: OK', pb.get_width(), 'x', pb.get_height())
except Exception as exc:
    print('scaled load: FAIL', type(exc).__name__, exc)
PY

echo "== loader cache"
ls -l /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders/ 2>/dev/null | head
echo "== cairosvg / rsvg CLI?"
command -v rsvg-convert || echo "rsvg-convert missing"
python3 -c "import cairo; print('pycairo', cairo.version)"
