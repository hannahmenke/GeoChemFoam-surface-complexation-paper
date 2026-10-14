#!/usr/bin/env python3
"""Regression tests for the minimal OpenFOAM scalar-field reader."""

from __future__ import annotations

import struct
import unittest

import numpy as np

from openfoam_field_io import _read_internal_scalar_bytes


HEADER = b'''FoamFile
{
    format binary;
    arch "LSB;label=32;scalar=64";
}
internalField nonuniform List<scalar>
2
('''


class OpenFoamFieldIoTests(unittest.TestCase):
    def test_payload_byte_that_looks_like_carriage_return_is_not_skipped(self) -> None:
        first = bytes.fromhex("0d75e3c3d127713e")
        payload = first + struct.pack("<d", 1.0)
        values = _read_internal_scalar_bytes(HEADER + payload + b");\n")
        self.assertTrue(np.array_equal(values.view(np.uint8)[:8], np.frombuffer(first, dtype=np.uint8)))
        self.assertEqual(values[1], 1.0)

    def test_writer_with_line_ending_before_payload_is_supported(self) -> None:
        expected = np.array([0.25, 1.0], dtype="<f8")
        values = _read_internal_scalar_bytes(
            HEADER + b"\n" + expected.tobytes() + b");\n"
        )
        np.testing.assert_array_equal(values, expected)

    def test_uniform_scalar(self) -> None:
        value = _read_internal_scalar_bytes(b"internalField uniform 0.125;\n")
        self.assertEqual(value, 0.125)


if __name__ == "__main__":
    unittest.main()
