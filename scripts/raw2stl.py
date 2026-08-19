#!/usr/bin/env python3

"""Convert a labelled raw image crop to an STL pore/solid interface."""

import argparse
from pathlib import Path

import numpy as np
from scipy import ndimage
from skimage.measure import marching_cubes
from stl import mesh


def parse_args():
    parser = argparse.ArgumentParser()
    for axis in "xyz":
        parser.add_argument(f"--{axis}_min", required=True, type=int)
        parser.add_argument(f"--{axis}_max", required=True, type=int)
        parser.add_argument(f"--{axis}_dim", required=True, type=int)
    parser.add_argument("--pores_value", required=True, type=int)
    parser.add_argument("--solid_value", required=True, type=int)
    parser.add_argument("--image_name", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    image_path = Path(f"{args.image_name}.raw")
    image = np.fromfile(image_path, dtype=np.uint8)
    expected = args.x_dim * args.y_dim * args.z_dim
    if image.size != expected:
        raise ValueError(f"Unexpected raw image size: {image.size} != {expected}")

    image = image.reshape((args.z_dim, args.y_dim, args.x_dim))
    image = image[
        args.z_min : args.z_max,
        args.y_min : args.y_max,
        args.x_min : args.x_max,
    ]
    image = np.pad(image, pad_width=1, mode="constant", constant_values=args.pores_value)
    image = np.swapaxes(image, 0, 2)

    pores = image == args.pores_value
    distance = ndimage.distance_transform_edt(pores)
    crop_shape = np.array(
        [args.x_max - args.x_min, args.y_max - args.y_min, args.z_max - args.z_min]
    )
    margin = int(crop_shape.min() / 4)
    search = distance[
        margin : crop_shape[0] - margin,
        margin : crop_shape[1] - margin,
        margin : crop_shape[2] - margin,
    ]
    pore_index = np.array(np.unravel_index(np.argmax(search), search.shape)) + margin + 1
    for axis, index in zip("xyz", pore_index):
        Path(f"pore_ind{axis}").write_text(str(index))

    vertices, faces, _, _ = marching_cubes(
        image,
        (args.pores_value + args.solid_value) / 2,
        step_size=1,
        allow_degenerate=True,
    )
    output = mesh.Mesh(np.zeros(faces.shape[0], dtype=mesh.Mesh.dtype))
    output.vectors[:] = vertices[faces]
    output.save("Image_meshed.stl")
    output.save("Image_meshed_python.stl")


if __name__ == "__main__":
    main()
