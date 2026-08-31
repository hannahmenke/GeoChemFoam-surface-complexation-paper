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
    def write_checkpoint(
        directory: Path, time_name: str, checkpoint_contract: str,
        dump: bytes = b"state\n",
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        dump_path = directory / "phreeqc.dmp"
        dump_path.write_bytes(dump)
        prefix = {
            "legacy-v1": "GeoChemFoam-PHREEQCRM-checkpoint 1\n",
            "no-edl-v2": (
                "GeoChemFoam-PHREEQCRM-checkpoint 2\n"
                "surfaceModel NO_EDL\n"
            ),
        }[checkpoint_contract]
        (directory / "phreeqc.complete").write_text(
            prefix + f"time {time_name}\n"
            f"dumpSize {len(dump)}\n"
            f"dumpSHA256 {provenance.sha256(dump_path)}\n"
        )

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

    def test_checkpoint_validation_covers_every_rank_and_write_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            times = provenance.checkpoint_time_names(6000.0, 2000.0)
            self.assertEqual(times, ("2000", "4000", "6000"))
            for rank in range(8):
                for time_name in times:
                    self.write_checkpoint(
                        case / f"processor{rank}" / time_name,
                        time_name,
                        "legacy-v1",
                    )
            provenance.verify_checkpoints(case, times, "legacy-v1")
            (case / "processor3" / "4000" / "phreeqc.dmp").write_bytes(b"other\n")
            with self.assertRaisesRegex(SystemExit, "Checkpoint SHA256 mismatch"):
                provenance.verify_checkpoints(case, times, "legacy-v1")

    def test_checkpoint_validation_rejects_wrong_recorded_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "2000"
            self.write_checkpoint(directory, "2000", "legacy-v1")
            (directory / "phreeqc.dmp").write_bytes(b"longer state\n")
            with self.assertRaisesRegex(SystemExit, "Checkpoint size mismatch"):
                provenance.verify_checkpoint(directory, "2000", "legacy-v1")

    def test_checkpoint_validation_rejects_malformed_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "2000"
            self.write_checkpoint(directory, "2000", "legacy-v1")
            (directory / "phreeqc.complete").write_text("complete\n")
            with self.assertRaisesRegex(SystemExit, "required legacy-v1 contract"):
                provenance.verify_checkpoint(directory, "2000", "legacy-v1")

    def test_checkpoint_validation_rejects_wrong_recorded_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "2000"
            self.write_checkpoint(directory, "4000", "legacy-v1")
            with self.assertRaisesRegex(SystemExit, "Wrong checkpoint time"):
                provenance.verify_checkpoint(directory, "2000", "legacy-v1")

    def test_checkpoint_validation_rejects_pending_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "2000"
            self.write_checkpoint(directory, "2000", "legacy-v1")
            (directory / "phreeqc.complete.tmp").write_text("pending\n")
            with self.assertRaisesRegex(SystemExit, "Incomplete checkpoint marker remains"):
                provenance.verify_checkpoint(directory, "2000", "legacy-v1")

    def test_checkpoint_contract_selection_is_explicit_and_strict(self):
        command_action = next(
            action for action in provenance.parser()._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        for command in ("check-run", "record-figure"):
            contract_action = next(
                action for action in command_action.choices[command]._actions
                if action.dest == "checkpoint_contract"
            )
            self.assertTrue(contract_action.required)
            self.assertEqual(
                set(contract_action.choices), {"legacy-v1", "no-edl-v2"}
            )
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "2000"
            for selected, rejected in (
                ("legacy-v1", "no-edl-v2"),
                ("no-edl-v2", "legacy-v1"),
            ):
                with self.subTest(selected=selected):
                    self.write_checkpoint(directory, "2000", selected)
                    provenance.verify_checkpoint(directory, "2000", selected)
                    with self.assertRaisesRegex(SystemExit, f"required {rejected} contract"):
                        provenance.verify_checkpoint(directory, "2000", rejected)

    def test_no_edl_v2_checkpoint_rejects_surface_contract_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "2000"
            self.write_checkpoint(directory, "2000", "no-edl-v2")
            marker = directory / "phreeqc.complete"
            valid = marker.read_text()
            invalid = (
                valid.replace("NO_EDL", "Donnan"),
                valid.replace("surfaceModel NO_EDL\n", ""),
                valid.replace(
                    "surfaceModel NO_EDL\n",
                    "surfaceModel NO_EDL\nsurfaceModel NO_EDL\n",
                ),
                valid.replace(
                    "surfaceModel NO_EDL\ntime 2000\n",
                    "time 2000\nsurfaceModel NO_EDL\n",
                ),
                valid + "unexpected\n",
                valid.rstrip("\n"),
            )
            for content in invalid:
                marker.write_text(content)
                with self.assertRaisesRegex(SystemExit, "required no-edl-v2 contract"):
                    provenance.verify_checkpoint(directory, "2000", "no-edl-v2")

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
            for rank in range(8):
                for time_name in provenance.checkpoint_time_names(20000, 2000):
                    self.write_checkpoint(
                        case / f"processor{rank}" / time_name,
                        time_name,
                        "legacy-v1",
                    )
            output = root / "figures.json"
            output.write_text(json.dumps({"figures": {"existing.png": {"keep": True}}}))
            args = argparse.Namespace(
                figure=figure, manifest=manifest, time=20000, output=output,
                checkpoint_contract="legacy-v1",
                case_dir=case, paper_root=root, figure_input=[manifest],
                renderer_source=[manifest, manifest, manifest],
                renderer_repository="https://example.test/paper.git",
                renderer_base_commit="a" * 40,
            )
            provenance.record_figure(args)
            recorded = json.loads(output.read_text())
            self.assertEqual(recorded["schema_scope"], "bounded_figure2")
            self.assertTrue(recorded["figures"]["existing.png"]["keep"])
            entry = recorded["figures"]["fig02.png"]
            self.assertEqual(entry["figure_sha256"], provenance.sha256(figure))
            self.assertEqual(entry["output_time_s"], 20000)
            self.assertEqual(entry["checkpoint_contract"], "legacy-v1")
            self.assertEqual(entry["runtime"]["commit"], "runtime")
            self.assertEqual(entry["chemistry"]["files"][0]["sha256"], "chemistry")
            self.assertEqual(entry["figure_inputs"][0]["sha256"], provenance.sha256(manifest))
            self.assertEqual(entry["figure_path"], "${PAPER_REPO}/fig02.png")
            self.assertEqual(entry["run_outputs"]["solver_log"]["path"], "${RUN_CASE_DIR}/reactiveTransportDBSFoamRT.out")
            self.assertEqual(entry["renderer"]["base_commit"], "a" * 40)
            self.assertEqual(entry["renderer"]["source_state"], "curated_dirty_at_base")
            self.assertTrue(entry["renderer"]["source_files_authoritative"])
            self.assertIn("source_files are authoritative", entry["renderer"]["source_authority"])
            self.assertNotIn("commit", entry["renderer"])
            self.write_checkpoint(
                case / "processor0/2000", "2000", "no-edl-v2"
            )
            with self.assertRaisesRegex(SystemExit, "required legacy-v1 contract"):
                provenance.record_figure(args)


if __name__ == "__main__":
    unittest.main()
