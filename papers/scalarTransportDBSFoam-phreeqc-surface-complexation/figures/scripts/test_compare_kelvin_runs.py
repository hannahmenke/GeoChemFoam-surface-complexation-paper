#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


MODULE_PATH = Path(__file__).with_name("compare_kelvin_runs.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("compare_kelvin_runs", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def foam_scalar(path: Path, value: float) -> None:
    path.write_text(
        "FoamFile\n{\n format ascii;\n class volScalarField;\n}\n"
        f"internalField uniform {value:.17g};\n"
    )


def foam_list(path: Path, class_name: str, entries: list[str]) -> None:
    path.write_text(
        "FoamFile\n{\n format ascii;\n"
        f" class {class_name};\n}}\n\n{len(entries)}\n(\n"
        + "\n".join(entries)
        + "\n)\n"
    )


class JsonAndGeometryTests(unittest.TestCase):
    def test_json_rejects_duplicate_keys_nonfinite_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "record.json"
            path.write_text('{"a": 1, "a": 2}\n')
            with self.assertRaisesRegex(comparison.ComparisonError, "Duplicate JSON key"):
                comparison.load_json(path)
            path.write_text('{"a": NaN}\n')
            with self.assertRaisesRegex(comparison.ComparisonError, "Non-finite JSON"):
                comparison.load_json(path)
            path.write_text('{"a": 1}\n')
            link = root / "link.json"
            link.symlink_to(path)
            with self.assertRaisesRegex(comparison.ComparisonError, "Missing regular JSON"):
                comparison.load_json(link)

    def _one_cell_mesh(self, root: Path, length: float = 1.0e-5) -> Path:
        mesh = root / "constant/polyMesh"
        mesh.mkdir(parents=True)
        points = [
            (0, 0, 0), (length, 0, 0), (length, length, 0), (0, length, 0),
            (0, 0, length), (length, 0, length), (length, length, length),
            (0, length, length),
        ]
        foam_list(mesh / "points", "vectorField", [f"({x} {y} {z})" for x, y, z in points])
        foam_list(
            mesh / "faces",
            "faceList",
            [
                "4(0 3 2 1)", "4(4 5 6 7)", "4(0 1 5 4)",
                "4(1 2 6 5)", "4(2 3 7 6)", "4(3 0 4 7)",
            ],
        )
        foam_list(mesh / "owner", "labelList", ["0"] * 6)
        foam_list(mesh / "neighbour", "labelList", [])
        foam_list(mesh / "cellProcAddressing", "labelList", ["0"])
        return root

    def test_mesh_volume_and_centre_are_derived_from_polymesh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rank = self._one_cell_mesh(Path(tmp) / "processor0")
            geometry = comparison.mesh_geometry(rank)
            np.testing.assert_allclose(geometry["volumes"], [1.0e-15], rtol=1e-12)
            np.testing.assert_allclose(geometry["centres"], [[5e-6, 5e-6, 5e-6]])
            np.testing.assert_array_equal(geometry["x_index"], [0])

    def test_mesh_with_wrong_physical_volume_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rank = self._one_cell_mesh(Path(tmp) / "processor0", 2.0e-5)
            with self.assertRaisesRegex(comparison.ComparisonError, "geometry/global addressing"):
                comparison.mesh_geometry(rank)

    def test_negative_values_are_reported_without_clipping(self) -> None:
        statistics: dict[str, dict[str, object]] = {}
        comparison.update_statistics(
            statistics, "Mn+2", np.array([-1.0e-12, 0.0, 2.0])
        )
        self.assertEqual(statistics["Mn+2"]["minimum"], -1.0e-12)
        self.assertEqual(statistics["Mn+2"]["negative_count"], 1)
        self.assertEqual(statistics["Mn+2"]["below_negative_tolerance_count"], 0)
        with self.assertRaisesRegex(comparison.ComparisonError, "below"):
            comparison.update_statistics(
                statistics, "Mn+2", np.array([-1.0000001e-12])
            )

    def test_front_quantiles_use_raw_monotone_inventory(self) -> None:
        with mock.patch.object(comparison, "NX", 4):
            fronts = comparison.front_positions(np.array([1.0, 1.0, 2.0, 6.0]))
            self.assertEqual(fronts["x10"]["cell_index"], 0)
            self.assertEqual(fronts["x50"]["cell_index"], 3)
            with self.assertRaisesRegex(comparison.ComparisonError, "require clipping"):
                comparison.front_positions(np.array([1.0, -2.0, 3.0, 4.0]))


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.case = Path(self.temporary.name)
        self.ranks = []
        for number in range(comparison.RANK_COUNT):
            rank = self.case / f"processor{number}"
            self.ranks.append(rank)
            for time_name in ("0", "0.5"):
                directory = rank / time_name
                directory.mkdir(parents=True)
                foam_scalar(directory / "Surf_s", 2e-7)
                foam_scalar(directory / "Surf_w", 6e-6)
            (rank / "constant/polyMesh").mkdir(parents=True)
        self.log = self.case / "solver.out"
        self.log.write_text("Time = 0.5\nEnd\n")
        self.payload = {"initial_case": {"sha256": "identity", "records": []}}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def stage(self, status: str = "completed", attempt: int = 1) -> dict[str, object]:
        stage: dict[str, object] = {
            "application": "reactiveTransportDBSFoam",
            "startFrom": "startTime", "startTime": 0.0,
            "stopAt": "endTime", "endTime": 0.5,
            "deltaT": comparison.COARSE_DT_S,
            "writeControl": "adjustableRunTime", "writeInterval": 0.5,
            "purgeWrite": 0, "writeFormat": "ascii", "writePrecision": 16,
            "writeCompression": "off", "timeFormat": "general", "timePrecision": 8,
            "runTimeModifiable": "yes", "phreeqcRestartCheckpoints": True,
            "phreeqcRestoreCheckpoint": False,
            "stage_id": f"0_to_0.5_attempt_{attempt:03d}", "attempt": attempt,
            "status": status, "chain_relation": "initial" if attempt == 1 else "retry",
            "recorded_utc": "2026-01-01T00:00:00+00:00",
            "rank_count": comparison.RANK_COUNT,
            "decomposition": comparison.DECOMPOSITION,
            "initial_case_identity_sha256": "identity",
            "immutable_dictionary_sha256": "dictionary",
            "immutable_control_sha256": "control",
            "dictionaries": [], "selected_start_time_directories": [],
            "start_rank_inputs": [], "restart_checkpoints": [],
            "surface_master_fields": [],
        }
        for rank in self.ranks:
            stage["selected_start_time_directories"].append(
                {"rank": rank.name, "path": str((rank / "0").resolve()), "time_name": "0"}
            )
            for name, value in (("Surf_s", 2e-7), ("Surf_w", 6e-6)):
                path = rank / "0" / name
                stage["surface_master_fields"].append(
                    {"path": str(path.resolve()), "sha256": comparison.sha256(path),
                     "value_kmol_m2": value}
                )
        if status == "completed":
            stage.update(
                {
                    "completed_utc": "2026-01-01T00:01:00+00:00",
                    "solver_exit_status": 0,
                    "solver_log": {
                        "path": str(self.log.resolve()), "sha256": comparison.sha256(self.log)
                    },
                    "endpoint_time_directories": [
                        {"rank": rank.name, "path": str((rank / "0.5").resolve()),
                         "time_name": "0.5"}
                        for rank in self.ranks
                    ],
                    "endpoint_rank_outputs": [],
                    "endpoint_checkpoints": [{"rank": rank.name} for rank in self.ranks],
                }
            )
        return stage

    def patches(self):
        return (
            mock.patch.object(comparison.provenance, "tree_records", return_value=[]),
            mock.patch.object(comparison.provenance, "records_digest", return_value="identity"),
            mock.patch.object(comparison.provenance, "verify_dictionary_snapshots"),
            mock.patch.object(
                comparison, "checkpoint_record",
                side_effect=lambda case, rank, value: {"rank": rank.name},
            ),
        )

    def run_chain(self) -> tuple[list[dict], list[dict], dict]:
        patchers = self.patches()
        with patchers[0], patchers[1], patchers[2], patchers[3]:
            return comparison.verify_stage_chain(
                self.payload, self.case, self.ranks, 0.5
            )

    def test_completed_stage_is_recomputed_and_accepted(self) -> None:
        self.payload["transport_stages"] = [self.stage()]
        completed, attempts, summary = self.run_chain()
        self.assertEqual(len(completed), 1)
        self.assertEqual(attempts, [])
        self.assertTrue(summary["all_checkpoint_pairs_valid"])

    def test_trailing_attempt_is_rejected_as_partial(self) -> None:
        stage = self.stage(status="attempted")
        self.payload["transport_stages"] = [stage]
        with self.assertRaisesRegex(comparison.ComparisonError, "incomplete"):
            self.run_chain()

    def test_exact_completed_retry_supersedes_failed_attempt(self) -> None:
        self.payload["transport_stages"] = [
            self.stage(status="attempted", attempt=1),
            self.stage(status="completed", attempt=2),
        ]
        completed, attempts, summary = self.run_chain()
        self.assertEqual(len(completed), 1)
        self.assertEqual(attempts[0]["stage_id"], "0_to_0.5_attempt_001")
        self.assertEqual(attempts[0]["superseded_by"], "0_to_0.5_attempt_002")
        self.assertEqual(summary["superseded_attempt_count"], 1)

    def test_unrecorded_numeric_time_is_rejected_as_stale(self) -> None:
        self.payload["transport_stages"] = [self.stage()]
        for rank in self.ranks:
            (rank / "0.25").mkdir()
        with self.assertRaisesRegex(comparison.ComparisonError, "stale"):
            self.run_chain()

    def test_wrong_checkpoint_rank_set_is_rejected(self) -> None:
        stage = self.stage()
        stage["endpoint_checkpoints"] = stage["endpoint_checkpoints"][:-1]
        self.payload["transport_stages"] = [stage]
        with self.assertRaisesRegex(comparison.ComparisonError, "Endpoint checkpoints"):
            self.run_chain()


class ScientificGateTests(unittest.TestCase):
    def _case(self, root: Path, suffix: str, mn: float) -> Path:
        case = root / suffix
        rank = case / "processor0"
        for time_name in ("0", "0.5"):
            directory = rank / time_name
            directory.mkdir(parents=True)
            values = {
                "eps": 0.5, "aSurf": 2.0, "aSurfIntrinsic": 3.0, "Kinv": 4.0,
                "Mn+2": mn if time_name == "0.5" else 1.0,
                "Mg+2": 3.0, "Cl-": 4.0, "Surf_sOMn+": 0.25,
                "Surf_wOMn+": 0.75, "Surf_wOMg+": 0.5,
            }
            for name, value in values.items():
                foam_scalar(directory / name, value)
        return case

    def test_scientific_metrics_use_mesh_volume_and_report_no_false_flux_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = self._case(root, "left", 2.0)
            right = self._case(root, "right", 1.0)
            geometry = {
                "addressing": np.array([0]), "volumes": np.array([2.0e-15]),
                "centres": np.array([[5e-6, 5e-6, 5e-6]]), "x_index": np.array([0]),
            }
            with (
                mock.patch.object(comparison, "RANK_COUNT", 1),
                mock.patch.object(comparison, "GLOBAL_CELL_COUNT", 1),
                mock.patch.object(comparison, "NX", 1),
                mock.patch.object(comparison, "mesh_geometry", return_value=geometry),
            ):
                result = comparison.scientific_metrics(
                    left, right, 0.5, 0.5, "left", "right"
                )
            self.assertAlmostEqual(
                result["inventory_kmol"]["left"]["endpoint"]["Mn_aqueous"],
                2.0e-15,
            )
            self.assertAlmostEqual(
                result["relative_endpoint_inventory_difference"]["Mn_aqueous"], 1.0
            )
            self.assertFalse(result["mass_balance_scope"]["boundary_flux_closure_evaluated"])
            self.assertIn("not mislabeled", result["mass_balance_scope"]["reason"])

    def test_convergence_thresholds_are_strict_and_transparent(self) -> None:
        metrics = {
            "relative_endpoint_inventory_difference": {
                "Mn_aqueous": 0.009, "Mn_sorbed": 0.01, "Mn_total": 0.001
            },
            "spatial_relative_L1": {"Mn_aqueous": 0.001, "Mn_sorbed": 0.002},
            "front_differences": {
                "Mn_aqueous": {"x10": {"cell_index_delta": 0}},
                "Mn_sorbed": {"x90": {"cell_index_delta": 1}},
            },
        }
        result = comparison.evaluate_convergence(metrics)
        self.assertFalse(result["checks"]["Mn_inventories_below_1pct"])
        self.assertEqual(
            result["tolerances"]["Mn_inventory_relative"],
            {"operator": "<", "value": 0.01},
        )
        self.assertTrue(result["checks"]["fronts_within_one_cell"])

    def test_restart_gate_requires_zero_front_shift(self) -> None:
        inventory = {
            name: 0.0 for name in (
                "Mn_aqueous", "Mn_sorbed", "Mn_total", "Mg_aqueous",
                "Mg_sorbed", "Mg_total", "Cl_total"
            )
        }
        metrics = {
            "relative_endpoint_inventory_difference": inventory,
            "spatial_relative_L1": {"Mn_aqueous": 0.0, "Mn_sorbed": 0.0},
            "front_differences": {
                "Mn_aqueous": {"x10": {"cell_index_delta": 0}},
                "Mn_sorbed": {"x90": {"cell_index_delta": 1}},
            },
        }
        result = comparison.evaluate_restart(metrics)
        self.assertFalse(result["checks"]["front_indices_identical"])


class PairIdentityTests(unittest.TestCase):
    def payload(self, root: Path, runtime_commit: str = "g") -> dict[str, object]:
        case = root / "case"
        paper = root / "paper"
        case.mkdir(exist_ok=True)
        paper.mkdir(exist_ok=True)
        return {
            "runtime": {
                "root": "/runtime", "commit": runtime_commit, "tree": "gt",
                "tracked_diff_sha256": comparison.EMPTY_SHA256,
                "phreeqcrm_gitlink": "link",
                "phreeqcrm": {
                    "root": "/runtime/ThirdParty/PhreeqcRM", "commit": "p",
                    "tree": "pt", "tracked_diff_sha256": comparison.EMPTY_SHA256,
                },
            },
            "runtime_artifacts": {"identity_sha256": "artifacts"},
            "paper": {
                "root": str(paper), "commit": "paper", "tree": "paper-tree",
                "tracked_diff_sha256": comparison.EMPTY_SHA256,
            },
            "chemistry": {
                "files": [{"path": str(case / "constant/input"), "sha256": "h"}]
            },
            "initial_case": {"sha256": "initial", "records": []},
            "surface": {"path": str(case / "surface.log"), "sha256": "s"},
            "intrinsic_surface": {
                "path": str(case / "intrinsic.log"), "sha256": "i"
            },
        }

    def test_mismatched_runtime_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left_root = root / "left"
            right_root = root / "right"
            left_root.mkdir()
            right_root.mkdir()
            left = self.payload(left_root)
            right = self.payload(right_root, runtime_commit="different")
            with self.assertRaisesRegex(comparison.ComparisonError, "identities differ"):
                comparison.verify_pair_identity(
                    left, right, left_root / "case", right_root / "case"
                )


if __name__ == "__main__":
    unittest.main()
