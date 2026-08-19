#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from paraview.simple import (
    ColorBy,
    CreateRenderView,
    GetAnimationScene,
    GetColorTransferFunction,
    GetOpacityTransferFunction,
    GetScalarBar,
    Hide,
    OpenFOAMReader,
    Outline,
    Render,
    SaveScreenshot,
    SetActiveView,
    Show,
)


def ensure_loader_file(case_dir: Path) -> Path:
    loader = case_dir / "paraview_loader.foam"
    if not loader.exists():
        loader.write_text("")
    return loader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time", type=float, required=True)
    parser.add_argument("--field", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--case-type", default="Decomposed Case")
    parser.add_argument("--view-size-x", type=int, default=1800)
    parser.add_argument("--view-size-y", type=int, default=1200)
    args = parser.parse_args()

    case_dir = args.case_dir.resolve()
    loader_file = ensure_loader_file(case_dir)

    reader = OpenFOAMReader(FileName=str(loader_file))
    reader.CaseType = args.case_type
    reader.MeshRegions = ["internalMesh"]
    reader.CellArrays = [args.field]

    animation_scene = GetAnimationScene()
    animation_scene.UpdateAnimationUsingDataTimeSteps()

    render_view = CreateRenderView()
    SetActiveView(render_view)
    render_view.ViewSize = [args.view_size_x, args.view_size_y]
    render_view.Background = [1.0, 1.0, 1.0]
    render_view.OrientationAxesVisibility = 1
    render_view.CenterAxesVisibility = 0
    render_view.CameraPosition = [170.0, -150.0, 145.0]
    render_view.CameraFocalPoint = [25.0, 25.0, 25.0]
    render_view.CameraViewUp = [0.0, 0.0, 1.0]

    display = Show(reader, render_view)
    display.Representation = "Volume"
    ColorBy(display, ("CELLS", args.field))

    lut = GetColorTransferFunction(args.field)
    pwf = GetOpacityTransferFunction(args.field)
    display.RescaleTransferFunctionToDataRange(True, False)
    lut.RescaleTransferFunctionToDataRange(True, False)
    pwf.RescaleTransferFunctionToDataRange(True, False)
    display.SetScalarBarVisibility(render_view, True)

    scalar_bar = GetScalarBar(lut, render_view)
    scalar_bar.Title = args.field
    scalar_bar.ComponentTitle = ""
    scalar_bar.WindowLocation = "Upper Right Corner"
    scalar_bar.Orientation = "Vertical"

    outline = Outline(Input=reader)
    outline_display = Show(outline, render_view)
    outline_display.Representation = "Surface"
    outline_display.DiffuseColor = [0.25, 0.25, 0.25]
    outline_display.LineWidth = 1.2

    render_view.ViewTime = args.time
    if args.title:
        render_view.UseTexturedBackground = 0

    Render()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    SaveScreenshot(str(args.output), render_view)

    Hide(outline, render_view)
    Hide(reader, render_view)


if __name__ == "__main__":
    main()
