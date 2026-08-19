#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace the bottom-right panel in a 3200x3200 binary Estaillades figure."
    )
    parser.add_argument("--base-figure", type=Path, required=True)
    parser.add_argument("--panel-d", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base = Image.open(args.base_figure).convert("RGB")
    panel = Image.open(args.panel_d).convert("RGB")
    if base.size != (3200, 3200):
        raise RuntimeError(f"Expected 3200x3200 base figure, got {base.size}")
    if panel.size != (1600, 1600):
        raise RuntimeError(f"Expected 1600x1600 panel image, got {panel.size}")

    out = base.copy()
    out.paste(panel, (1600, 1600))

    draw = ImageDraw.Draw(out)
    draw.line([(1600, 1600), (3199, 1600)], fill="black", width=2)
    draw.line([(1600, 1600), (1600, 3199)], fill="black", width=2)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.save(args.output)


if __name__ == "__main__":
    main()
