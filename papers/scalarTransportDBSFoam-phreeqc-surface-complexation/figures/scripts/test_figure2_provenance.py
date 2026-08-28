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
    @staticmethod
    def populate_run_outputs(case: Path) -> None:
        case.mkdir(parents=True, exist_ok=True)
        (case / "reactiveTransportDBSFoamRT.out").write_text("Time = 20000\nEnd\n")
        for rank in range(8):
            for time_name, names in (
                ("20000", provenance.FINAL_FIELDS),
                ("0", provenance.SUPPORT_FIELDS),
            ):
                directory = case / f"processor{rank}" / time_name
                directory.mkdir(parents=True, exist_ok=True)
                for name in names:
                    (directory / name).write_text(f"{rank} {time_name} {name}\n")

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

    def test_portable_paths_fail_closed_outside_declared_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "case" / "field"
            child.parent.mkdir()
            child.write_text("field")
            roots = {"CASE": root / "case"}
            self.assertEqual(provenance.portable_path(child, roots), "${CASE}/field")
            with self.assertRaises(SystemExit):
                provenance.portable_path(root / "elsewhere", roots)

    def test_run_output_record_covers_every_rank_field_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case"
            self.populate_run_outputs(case)
            records = provenance.collect_run_outputs(case, "20000", {"CASE": case})
            self.assertEqual(len(records["final_rank_fields"]), 48)
            self.assertEqual(len(records["support_rank_fields"]), 32)
            self.assertEqual(records["solver_log"]["path"], "${CASE}/reactiveTransportDBSFoamRT.out")
            self.assertEqual(
                records["final_rank_fields_sha256"],
                provenance.records_sha256(records["final_rank_fields"]),
            )

    def test_figure_record_preserves_existing_entries_and_embeds_run_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            figure = root / "fig02.png"
            figure.write_bytes(b"png")
            case = root / "run" / "case"
            self.populate_run_outputs(case)
            run = {
                "paper": {"root": str(root / "run-paper"), "commit": "paper"},
                "runtime": {"root": str(root / "runtime"), "commit": "runtime"},
                "runtime_artifacts": {"solver": {"path": str(root / "runtime" / "solver"), "sha256": "solver"}},
                "surface": {"path": str(case / "surface.log"), "sha256": "surface"},
                "intrinsic_surface": {"path": str(case / "intrinsic.log"), "sha256": "intrinsic"},
                "chemistry": {"files": [{"path": str(case / "chemistry"), "sha256": "chemistry"}]},
                "realized_transport": {
                    "endTime": 20000,
                    "deltaT": 0.25,
                    "writeInterval": 2000,
                    "control_dict": {"path": str(case / "controlDict"), "sha256": "control"},
                    "thermo_file": {"path": str(case / "thermo"), "sha256": "thermo"},
                    "surface_master_fields": [],
                },
            }
            manifest = root / "run.json"
            manifest.write_text(json.dumps(run))
            output = root / "figures.json"
            output.write_text(json.dumps({"figures": {"existing.png": {"keep": True}}}))
            provenance.record_figure(argparse.Namespace(
                figure=figure, manifest=manifest, time=20000, output=output,
                case_dir=case, paper_root=root, figure_input=[manifest],
                renderer_source=[manifest, manifest, manifest],
                renderer_repository="https://example.test/paper.git",
                renderer_commit="a" * 40,
            ))
            recorded = json.loads(output.read_text())
            self.assertTrue(recorded["figures"]["existing.png"]["keep"])
            entry = recorded["figures"]["fig02.png"]
            self.assertEqual(entry["figure_sha256"], provenance.sha256(figure))
            self.assertEqual(entry["output_time_s"], 20000)
            self.assertEqual(entry["runtime"]["commit"], "runtime")
            self.assertEqual(entry["chemistry"]["files"][0]["sha256"], "chemistry")
            self.assertEqual(entry["figure_inputs"][0]["sha256"], provenance.sha256(manifest))
            self.assertEqual(entry["figure_path"], "${PAPER_REPO}/fig02.png")
            self.assertEqual(entry["run_outputs"]["solver_log"]["path"], "${RUN_CASE_DIR}/reactiveTransportDBSFoamRT.out")
            self.assertEqual(entry["renderer"]["commit"], "a" * 40)


if __name__ == "__main__":
    unittest.main()
