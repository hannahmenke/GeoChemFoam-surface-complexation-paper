#!/usr/bin/env python3
"""Unit tests for the pinned two-scale runtime identity."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_production_runtime import IDENTITY, load_identity, sha256


class RuntimeIdentityTests(unittest.TestCase):
    def test_committed_identity_is_complete(self) -> None:
        identity = load_identity()
        self.assertEqual(len(identity["runtime_commit"]), 40)
        self.assertEqual(len(identity["runtime_tree"]), 40)
        self.assertEqual(len(identity["phreeqcrm_tree"]), 40)
        self.assertEqual(
            set(identity["artifacts"]),
            {
                "bin/reactiveScalarTransportDBSFoam",
                "lib/libreactionThermophysicalModelsGCFOAM.so",
                "ThirdParty/PhreeqcRM/lib/libPhreeqcRM.so",
            },
        )
        self.assertTrue(all(len(value) == 64 for value in identity["artifacts"].values()))

    def test_rejects_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity.json"
            path.write_text(json.dumps({"schema_version": 99}))
            with self.assertRaisesRegex(SystemExit, "Unsupported runtime identity schema"):
                load_identity(path)

    def test_hashes_binary_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact"
            path.write_bytes(b"reviewed-runtime\x00")
            self.assertEqual(
                sha256(path),
                "d432f665d20878c9fadcdbe0ad7f507a5f969756bfe5e11361d926ef2d85061a",
            )

    def test_identity_path_is_case_local(self) -> None:
        self.assertTrue(IDENTITY.is_file())
        self.assertEqual(IDENTITY.name, "production_runtime_identity.json")


if __name__ == "__main__":
    unittest.main()
