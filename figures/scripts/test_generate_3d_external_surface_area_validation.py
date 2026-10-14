#!/usr/bin/env python3
"""Portability checks for the external-surface figure renderer.

Set GCF_EXTERNAL_SURFACE_CASE_ROOT to a completed case outside this repository
to exercise the renderer against non-bundled raw outputs.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "generate_3d_external_surface_area_validation.py"
REPO_ROOT = SCRIPT.parents[2]
SPEC = importlib.util.spec_from_file_location("external_surface_renderer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class ExternalSurfaceRendererTests(unittest.TestCase):
    def test_recorded_path_is_relative_only_inside_the_repository(self) -> None:
        self.assertEqual(renderer.recorded_path(REPO_ROOT / "figures"), "figures")
        with tempfile.TemporaryDirectory() as temporary:
            external = Path(temporary) / "output.png"
            self.assertEqual(renderer.recorded_path(external), str(external.resolve()))

    @unittest.skipUnless(
        os.environ.get("GCF_EXTERNAL_SURFACE_CASE_ROOT"),
        "set GCF_EXTERNAL_SURFACE_CASE_ROOT to a completed out-of-tree case to render",
    )
    def test_out_of_tree_case_and_outputs_render(self) -> None:
        case_root = Path(os.environ["GCF_EXTERNAL_SURFACE_CASE_ROOT"]).resolve()
        try:
            case_root.relative_to(REPO_ROOT)
        except ValueError:
            pass
        else:
            self.fail("GCF_EXTERNAL_SURFACE_CASE_ROOT must be outside this repository")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "render" / "external.png"
            metrics = Path(temporary) / "metrics" / "external.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--case-root", str(case_root),
                    "--output", str(output),
                    "--metrics-json", str(metrics),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertGreater(output.stat().st_size, 0)
            payload = json.loads(metrics.read_text())
            self.assertEqual(payload["case_root"], str(case_root))
            self.assertEqual(payload["output"], str(output.resolve()))


if __name__ == "__main__":
    unittest.main()
