#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PANEL_X_RANGES = [(145, 891), (1897, 2643), (2773, 3520)]
ROW_Y_RANGES = [(56, 802), (928, 1675), (1801, 2547), (2674, 3420)]
CBAR_X_RANGE = (3596, 3763)

LEFT_MARGIN = 160
RIGHT_MARGIN = 28
TOP_MARGIN = 86
BOTTOM_MARGIN = 28
X_GAP = 38
Y_GAP = 42
CBAR_GAP = 26

COLUMN_TITLES = [
    "snappyHexMesh",
    "DBS file",
    r"DBS $|\nabla \varepsilon|$",
]

ROW_TITLES = [
    r"Aqueous Sr/$C_{\mathrm{in}}$",
    "Sorbed Surf_aSr+",
    r"$\Delta$(Sr/$C_{\mathrm{in}}$) vs DBS file",
    r"$\Delta$(Surf_aSr+) vs DBS file",
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def add_centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill) -> None:
    left, top, right, bottom = box
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    x = left + (right - left - text_w) / 2
    y = top + (bottom - top - text_h) / 2
    draw.text((x, y), text, font=font, fill=fill)


def add_rotated_label(canvas: Image.Image, center: tuple[int, int], text: str, font, fill) -> None:
    scratch = Image.new("RGBA", (900, 150), (255, 255, 255, 0))
    draw = ImageDraw.Draw(scratch)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    draw.text(((900 - text_w) / 2, (150 - text_h) / 2), text, font=font, fill=fill)
    rotated = scratch.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
    x = int(center[0] - rotated.width / 2)
    y = int(center[1] - rotated.height / 2)
    canvas.alpha_composite(rotated, (x, y))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = Image.open(args.source).convert("RGBA")

    panel_width = PANEL_X_RANGES[0][1] - PANEL_X_RANGES[0][0]
    panel_height = ROW_Y_RANGES[0][1] - ROW_Y_RANGES[0][0]
    cbar_width = CBAR_X_RANGE[1] - CBAR_X_RANGE[0]

    canvas_width = LEFT_MARGIN + 3 * panel_width + 2 * X_GAP + CBAR_GAP + cbar_width + RIGHT_MARGIN
    canvas_height = TOP_MARGIN + 4 * panel_height + 3 * Y_GAP + BOTTOM_MARGIN
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))

    title_font = load_font(46, bold=True)
    row_font = load_font(40, bold=False)

    x_positions = [
        LEFT_MARGIN,
        LEFT_MARGIN + panel_width + X_GAP,
        LEFT_MARGIN + 2 * (panel_width + X_GAP),
    ]
    cbar_x = LEFT_MARGIN + 3 * panel_width + 2 * X_GAP + CBAR_GAP

    for row, y_range in enumerate(ROW_Y_RANGES):
        y0 = TOP_MARGIN + row * (panel_height + Y_GAP)
        for col, x_range in enumerate(PANEL_X_RANGES):
            crop = source.crop((x_range[0], y_range[0], x_range[1], y_range[1]))
            canvas.paste(crop, (x_positions[col], y0))

        cbar_crop = source.crop((CBAR_X_RANGE[0], y_range[0], CBAR_X_RANGE[1], y_range[1]))
        canvas.paste(cbar_crop, (cbar_x, y0))

    draw = ImageDraw.Draw(canvas)
    for col, title in enumerate(COLUMN_TITLES):
        add_centered_text(
            draw,
            (
                x_positions[col],
                12,
                x_positions[col] + panel_width,
                TOP_MARGIN - 8,
            ),
            title,
            title_font,
            fill=(0, 0, 0, 255),
        )

    for row, label in enumerate(ROW_TITLES):
        y_center = TOP_MARGIN + row * (panel_height + Y_GAP) + panel_height // 2
        add_rotated_label(canvas, (68, y_center), label, row_font, (0, 0, 0, 255))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(args.output, dpi=(220, 220))


if __name__ == "__main__":
    main()
