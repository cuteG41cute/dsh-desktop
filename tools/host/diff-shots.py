#!/usr/bin/env python3
"""Compare a design reference PNG against a GTK render.

  python tools/host/diff-shots.py REF.png ACT.png OUTPREFIX [--grid 8x6]

Outputs
  OUTPREFIX-side.png   reference | actual, side by side
  OUTPREFIX-diff.png   per-pixel |delta| as a heat map (dark = identical)
  stdout               JSON-ish summary: sizes, MAE, %pixels over threshold,
                       worst grid cells, and the worst rows/columns

Meant to be the gate for "pixel-level replication": the number to drive down is
MAE (mean absolute error, 0-255) plus the fraction of pixels that differ by more
than 16 levels. Text antialiasing always costs something; layout errors cost a lot.
"""
import json
import sys

import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)


def heatmap(delta, path):
    """0 error → near-black, large error → red/white."""
    d = delta.astype(np.float32)
    g = np.clip(d.mean(axis=2) * 3.0, 0, 255).astype(np.uint8)
    rgb = np.zeros(delta.shape, dtype=np.uint8)
    rgb[..., 0] = g
    rgb[..., 1] = (g // 3).astype(np.uint8)
    rgb[..., 2] = (g // 6).astype(np.uint8)
    Image.fromarray(rgb).save(path)


def side_by_side(ref, act, path):
    h = max(ref.shape[0], act.shape[0])
    w = ref.shape[1] + act.shape[1] + 8
    canvas = Image.new("RGB", (w, h), (24, 24, 28))
    canvas.paste(Image.fromarray(ref.astype(np.uint8)), (0, 0))
    canvas.paste(Image.fromarray(act.astype(np.uint8)), (ref.shape[1] + 8, 0))
    canvas.save(path)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    ref_path, act_path, prefix = sys.argv[1:4]
    grid = "8x6"
    if "--grid" in sys.argv:
        grid = sys.argv[sys.argv.index("--grid") + 1]
    gx, gy = (int(v) for v in grid.split("x"))

    ref = load(ref_path)
    act = load(act_path)
    if ref.shape != act.shape:
        print(json.dumps({
            "ok": False,
            "reason": "size mismatch",
            "reference": list(ref.shape[1::-1]),
            "actual": list(act.shape[1::-1]),
        }, ensure_ascii=False, indent=2))
        return 1

    delta = np.abs(ref - act)
    overall = delta.mean()
    per_pixel_max = delta.max(axis=2)
    frac16 = float((per_pixel_max > 16).mean() * 100)
    frac48 = float((per_pixel_max > 48).mean() * 100)

    h, w = per_pixel_max.shape
    cells = []
    for cy in range(gy):
        for cx in range(gx):
            y0, y1 = cy * h // gy, (cy + 1) * h // gy
            x0, x1 = cx * w // gx, (cx + 1) * w // gx
            cells.append({
                "cell": [cx, cy],
                "x": [x0, x1], "y": [y0, y1],
                "mae": round(float(delta[y0:y1, x0:x1].mean()), 2),
                "pct16": round(float((per_pixel_max[y0:y1, x0:x1] > 16).mean() * 100), 2),
            })
    cells.sort(key=lambda c: -c["mae"])

    row_err = delta.mean(axis=(1, 2))
    col_err = delta.mean(axis=(0, 2))
    worst_rows = np.argsort(row_err)[-8:][::-1].tolist()
    worst_cols = np.argsort(col_err)[-8:][::-1].tolist()

    heatmap(delta, prefix + "-diff.png")
    side_by_side(ref, act, prefix + "-side.png")

    summary = {
        "ok": True,
        "size": [w, h],
        "mae": round(float(overall), 2),
        "rmse": round(float(np.sqrt((delta.astype(np.float64) ** 2).mean())), 2),
        "pct_pixels_over_16": round(frac16, 2),
        "pct_pixels_over_48": round(frac48, 2),
        "worst_cells": cells[:6],
        "worst_rows": worst_rows,
        "worst_cols": worst_cols,
        "outputs": {"side": prefix + "-side.png", "diff": prefix + "-diff.png"},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
