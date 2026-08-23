#!/usr/bin/env python3
"""Minimal ASCII/binary OpenFOAM internal scalar-field reader."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np


_UNIFORM = re.compile(rb"internalField\s+uniform\s+([^\n;]+)\s*;")
_NONUNIFORM = re.compile(
    rb"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\("
)


def _binary_payload_bounds(
    data: bytes, offset: int, byte_count: int, source: str
) -> tuple[int, int]:
    """Locate a binary payload without mistaking scalar bytes for whitespace."""
    starts = [offset]
    # Most OpenFOAM writers put the first binary byte immediately after `(`.
    # Retain support for writers that insert one line ending, but only accept a
    # candidate when the closing parenthesis occurs at the exact payload size.
    if data[offset : offset + 2] == b"\r\n":
        starts.append(offset + 2)
    elif data[offset : offset + 1] in (b"\r", b"\n"):
        starts.append(offset + 1)

    for start in starts:
        stop = start + byte_count
        if stop <= len(data) and data[stop : stop + 1] == b")":
            return start, stop
    raise RuntimeError(f"Invalid binary internal-field payload in {source}")


def _read_internal_scalar_bytes(
    data: bytes, source: str = "<memory>"
) -> float | np.ndarray:
    uniform = _UNIFORM.search(data)
    if uniform:
        return float(uniform.group(1))

    nonuniform = _NONUNIFORM.search(data)
    if not nonuniform:
        raise RuntimeError(f"Unsupported scalar field format in {source}")

    count = int(nonuniform.group(1))
    is_binary = re.search(rb"\bformat\s+binary\s*;", data[: nonuniform.start()])
    if not is_binary:
        end = data.find(b")", nonuniform.end())
        if end < 0:
            raise RuntimeError(f"Unterminated internal field in {source}")
        values = np.fromstring(
            data[nonuniform.end() : end].decode("ascii"),
            sep=" ",
            count=count,
        )
    else:
        arch = re.search(
            rb'arch\s+"(LSB|MSB);label=(?:32|64);scalar=(32|64)"\s*;',
            data[: nonuniform.start()],
        )
        if not arch:
            raise RuntimeError(
                f"Missing or unsupported binary architecture in {source}"
            )
        endian = "<" if arch.group(1) == b"LSB" else ">"
        scalar_bytes = int(arch.group(2)) // 8
        dtype = np.dtype(f"{endian}f{scalar_bytes}")
        start, stop = _binary_payload_bounds(
            data, nonuniform.end(), count * dtype.itemsize, source
        )
        values = np.frombuffer(data, dtype=dtype, count=count, offset=start)
        if not values.dtype.isnative:
            values = values.astype(np.float64)

    if values.size != count:
        raise RuntimeError(
            f"Value count mismatch in {source}: expected {count}, got {values.size}"
        )
    return values


def read_internal_scalar(path: Path) -> float | np.ndarray:
    """Read a uniform or nonuniform volScalarField internal field."""
    return _read_internal_scalar_bytes(path.read_bytes(), str(path))
