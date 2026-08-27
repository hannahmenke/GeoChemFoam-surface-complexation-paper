#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


provenance = load("figure2_provenance", HERE / "figure2_provenance.py")
geometry = load("generate_2d_raw_geometry", HERE / "generate_2d_raw_geometry.py")
validator = load(
    "validate_item2_outputs",
    HERE.parent.parent / "cases" / "2d_4StraightFractures" / "validate_item2_outputs.py",
)


class Figure2Tests(unittest.TestCase):
    def test_validator_reads_uniform_and_nonuniform_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uniform = root / "uniform"
            uniform.write_text("internalField uniform 2e-7;\n")
            self.assertEqual(validator.field_values(uniform, 2), [2e-7, 2e-7])
            nonuniform = root / "nonuniform"
            nonuniform.write_text(
                "internalField nonuniform List<scalar> 2 (1e-7 3e-7);\n"
            )
            self.assertEqual(validator.field_values(nonuniform, 2), [1e-7, 3e-7])

    def test_log_scale_label_describes_raw_quantity(self):
        label = geometry.log_scale_label("Normalized Pb$^{2+}$")
        self.assertEqual(label, "Normalized Pb$^{2+}$ (log scale)")
        self.assertNotIn("log$_{10}$", label)

    def test_hash_verification_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input"
            path.write_text("original")
            record = {"path": str(path), "sha256": provenance.sha256(path)}
            provenance.verify_file(record, "input")
            path.write_text("changed")
            with self.assertRaises(SystemExit):
                provenance.verify_file(record, "input")

    def test_figure_record_preserves_existing_entries_and_embeds_run_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figure = root / "fig02.png"
            figure.write_bytes(b"png")
            run = {
                "paper": {"commit": "paper"},
                "runtime": {"commit": "runtime"},
                "runtime_artifacts": {"solver": {"sha256": "solver"}},
                "surface": {"sha256": "surface"},
                "intrinsic_surface": {"sha256": "intrinsic"},
                "chemistry": {"files": [{"sha256": "chemistry"}]},
                "realized_transport": {
                    "endTime": 20000,
                    "deltaT": 0.25,
                    "writeInterval": 2000,
                    "control_dict": {"sha256": "control"},
                    "thermo_file": {"sha256": "thermo"},
                    "surface_master_fields": [],
                },
            }
            manifest = root / "run.json"
            manifest.write_text(json.dumps(run))
            output = root / "figures.json"
            output.write_text(json.dumps({"figures": {"existing.png": {"keep": True}}}))
            provenance.record_figure(argparse.Namespace(
                figure=figure, manifest=manifest, time=20000, output=output,
                figure_input=[manifest],
            ))
            recorded = json.loads(output.read_text())
            self.assertTrue(recorded["figures"]["existing.png"]["keep"])
            entry = recorded["figures"]["fig02.png"]
            self.assertEqual(entry["figure_sha256"], provenance.sha256(figure))
            self.assertEqual(entry["output_time_s"], 20000)
            self.assertEqual(entry["runtime"]["commit"], "runtime")
            self.assertEqual(entry["chemistry"]["files"][0]["sha256"], "chemistry")
            self.assertEqual(entry["figure_inputs"][0]["sha256"], provenance.sha256(manifest))


if __name__ == "__main__":
    unittest.main()
