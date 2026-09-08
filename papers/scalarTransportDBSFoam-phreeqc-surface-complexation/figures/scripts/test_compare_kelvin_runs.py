#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
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
    class_name, dimensions, _ = comparison.FIELD_SPECS[path.name]
    path.write_text(
        "FoamFile\n{\n format ascii;\n"
        f" class {class_name};\n object {path.name};\n}}\n"
        f"dimensions [{' '.join(str(value) for value in dimensions)}];\n"
        f"internalField uniform {value:.17g};\n"
        "boundaryField\n{\n walls { type zeroGradient; }\n}\n"
    )


def foam_vector(path: Path, value: tuple[float, float, float]) -> None:
    class_name, dimensions, _ = comparison.FIELD_SPECS[path.name]
    path.write_text(
        "FoamFile\n{\n format ascii;\n"
        f" class {class_name};\n object {path.name};\n}}\n"
        f"dimensions [{' '.join(str(component) for component in dimensions)}];\n"
        f"internalField uniform ({value[0]} {value[1]} {value[2]});\n"
        "boundaryField\n{\n walls { type zeroGradient; }\n}\n"
    )


def foam_list(path: Path, class_name: str, entries: list[str]) -> None:
    path.write_text(
        "FoamFile\n{\n format ascii;\n"
        f" class {class_name};\n object {path.name};\n}}\n\n{len(entries)}\n(\n"
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

    def _one_cell_mesh(
        self, root: Path, length: float = 1.0e-5,
        origin: tuple[float, float, float] = (0.0, 0.0, 0.0), address: int = 0,
    ) -> Path:
        mesh = root / "constant/polyMesh"
        mesh.mkdir(parents=True)
        local_points = [
            (0, 0, 0), (length, 0, 0), (length, length, 0), (0, length, 0),
            (0, 0, length), (length, 0, length), (length, length, length),
            (0, length, length),
        ]
        points = [tuple(value + offset for value, offset in zip(point, origin))
                  for point in local_points]
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
        foam_list(mesh / "cellProcAddressing", "labelList", [str(address)])
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

    def test_far_corner_mesh_uses_stable_local_tetrahedral_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            origin = tuple((count - 1) * comparison.CELL_SIZE_M for count in (
                comparison.NX, comparison.NY, comparison.NZ
            ))
            rank = self._one_cell_mesh(
                Path(tmp) / "processor31", origin=origin,
                address=comparison.GLOBAL_CELL_COUNT - 1,
            )
            geometry = comparison.mesh_geometry(rank)
            np.testing.assert_allclose(geometry["volumes"], [comparison.CELL_VOLUME_M3])
            np.testing.assert_allclose(
                geometry["centres"],
                [[comparison.DOMAIN_LENGTH_M - 0.5 * comparison.CELL_SIZE_M] * 3],
            )

    def test_duplicate_global_addressing_is_rejected_before_coverage_update(self) -> None:
        with self.assertRaisesRegex(comparison.ComparisonError, "Duplicate global cells"):
            comparison.add_global_addressing(
                np.zeros(1, dtype=np.uint8), np.array([0, 0]), "processor0"
            )

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
            self.assertTrue(fronts["defined"])
            self.assertEqual(fronts["quantiles"]["x10"]["cell_index"], 0)
            self.assertEqual(fronts["quantiles"]["x50"]["cell_index"], 3)
            self.assertEqual(
                comparison.front_positions(np.zeros(4)),
                {"defined": False, "quantiles": {}},
            )
            with self.assertRaisesRegex(comparison.ComparisonError, "require clipping"):
                comparison.front_positions(np.array([1.0, -2.0, 3.0, 4.0]))
            with self.assertRaisesRegex(comparison.ComparisonError, "negative bins"):
                comparison.front_positions(np.array([-1.0, 2.0, 3.0, 4.0]))

    def test_field_parser_ignores_commented_internal_field_and_checks_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Mn+2"
            foam_scalar(path, 0.001)
            path.write_text("/* internalField uniform 999; */\n" + path.read_text())
            parsed = comparison.read_foam_field(path, 1)
            np.testing.assert_array_equal(parsed["values"], [0.001])
            path.write_text(path.read_text().replace(
                "dimensions [0 -3 0 0 1 0 0];", "dimensions [0 -2 0 0 1 0 0];"
            ))
            with self.assertRaisesRegex(comparison.ComparisonError, "Wrong dimensions"):
                comparison.read_foam_field(path, 1)

    def test_field_parser_rejects_nonfinite_boundary_and_wrong_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Mn+2"
            foam_scalar(path, 0.001)
            path.write_text(path.read_text().replace(
                "type zeroGradient;", "type fixedValue; value uniform nan;"
            ))
            with self.assertRaisesRegex(comparison.ComparisonError, "Non-finite token"):
                comparison.read_foam_field(path, 1)
            foam_scalar(path, 0.001)
            path.write_text(path.read_text().replace("object Mn+2;", "object Mg+2;"))
            with self.assertRaisesRegex(comparison.ComparisonError, "Wrong object"):
                comparison.read_foam_field(path, 1)

    def test_boundary_parser_validates_list_count_and_excludes_it_from_norm_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Mn+2"
            foam_scalar(path, 0.001)
            path.write_text(path.read_text().replace(
                "type zeroGradient;",
                "type fixedValue; value nonuniform List<scalar> 2(0.1 0.2);",
            ))
            parsed = comparison.read_foam_field(path, 1)
            np.testing.assert_array_equal(parsed["boundary_values"], [0.1, 0.2])
            self.assertIn("List<scalar> 2", parsed["boundary_structure"])
            path.write_text(path.read_text().replace("2(0.1 0.2)", "3(0.1 0.2)"))
            with self.assertRaisesRegex(comparison.ComparisonError, "Boundary list count"):
                comparison.read_foam_field(path, 1)

    def test_bounded_record_rejects_parent_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / "allowed"
            external = root / "external"
            allowed.mkdir()
            external.mkdir()
            target = external / "log"
            target.write_text("x")
            (allowed / "link").symlink_to(external, target_is_directory=True)
            record = {"path": str(allowed / "link" / "log"), "sha256": comparison.sha256(target)}
            with self.assertRaisesRegex(comparison.ComparisonError, "noncanonical"):
                comparison.verify_absolute_record(record, "test log", roots=(allowed,))

    def test_endpoint_restart_state_requires_exact_solver_field_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            endpoint = Path(tmp) / "0.5"
            endpoint.mkdir()
            for name in comparison.ENDPOINT_RESTART_STATE_FIELDS:
                _, _, kind = comparison.FIELD_SPECS[name]
                if kind == "cell_vector":
                    foam_vector(endpoint / name, (0.0, 0.0, 0.0))
                else:
                    foam_scalar(endpoint / name, 0.0)
            (endpoint / "phreeqc.dmp").write_bytes(b"checkpoint")
            (endpoint / "phreeqc.complete").write_text("marker\n")
            (endpoint / "uniform").mkdir()
            self.assertEqual(
                comparison.endpoint_state_field_names(endpoint),
                comparison.ENDPOINT_RESTART_STATE_FIELDS,
            )
            (endpoint / "R").unlink()
            with self.assertRaisesRegex(comparison.ComparisonError, r"missing=\['R'\]"):
                comparison.endpoint_state_field_names(endpoint)
            foam_scalar(endpoint / "R", 0.0)
            extra = endpoint / "unexpectedState"
            extra.write_text(
                "FoamFile\n{\n format ascii;\n class volScalarField;\n"
                " object unexpectedState;\n}\n"
            )
            with self.assertRaisesRegex(
                comparison.ComparisonError, r"unexpected=\['unexpectedState'\]"
            ):
                comparison.endpoint_state_field_names(endpoint)


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
            mock.patch.object(
                comparison, "stage_dictionary_contract",
                return_value={"noncontrol_snapshots": [], "canonical_control_contract": "x"},
            ),
            mock.patch.object(
                comparison, "endpoint_state_field_names",
                return_value=comparison.ENDPOINT_RESTART_STATE_FIELDS,
            ),
        )

    def run_chain(self) -> tuple[list[dict], list[dict], dict]:
        patchers = self.patches()
        with (
            patchers[0], patchers[1], patchers[2], patchers[3], patchers[4],
            patchers[5],
        ):
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
    @staticmethod
    def restart_metrics(front_shift: int = 0, hydrogen_difference: float = 0.0) -> dict[str, object]:
        reported_names = (
            comparison.MN_FREE, comparison.MN_SORBED, comparison.MN_REPORTED,
            comparison.MG_FREE, comparison.MG_SORBED, comparison.MG_REPORTED,
            comparison.CL_FREE,
        )
        inventory = {name: 0.0 for name in reported_names}
        state_relative = {name: 0.0 for name in comparison.FIELD_SPECS}
        state_absolute = {name: 0.0 for name in comparison.FIELD_SPECS}
        state_relative["H+"] = hydrogen_difference
        state_absolute["H+"] = hydrogen_difference
        chemistry_fields = {
            name: True for name in comparison.CHEMISTRY_FIELD_TOLERANCES
        }
        chemistry_fields["H+"] = hydrogen_difference <= (
            comparison.AQUEOUS_RESTART_ABSOLUTE_TOLERANCE
            + comparison.AQUEOUS_RESTART_RELATIVE_TOLERANCE
        )
        return {
            "reported_species_amount_kmol": {
                label: {"endpoint": {name: 1.0 for name in reported_names}}
                for label in ("uninterrupted", "restarted")
            },
            "relative_endpoint_reported_species_amount_difference": inventory,
            "absolute_endpoint_reported_species_amount_difference_kmol": inventory.copy(),
            "spatial_relative_L1": {
                comparison.MN_FREE: 0.0, comparison.MN_SORBED: 0.0
            },
            "spatial_absolute_L1_kmol": {
                comparison.MN_FREE: 0.0, comparison.MN_SORBED: 0.0
            },
            "derived_inventory_and_spatial_L1_tolerance_kmol": {
                name: 1.0 for name in reported_names
            },
            "complete_state_fieldwise_symmetric_relative_L1": state_relative,
            "complete_state_fieldwise_maximum_absolute_difference": state_absolute,
            "complete_state_fieldwise_maximum_absolute_magnitude": {
                name: 1.0 for name in comparison.FIELD_SPECS
            },
            "complete_state_boundary_symmetric_relative_L1": {
                name: 0.0 for name in comparison.FIELD_SPECS
            },
            "complete_state_boundary_maximum_absolute_difference": {
                name: 0.0 for name in comparison.FIELD_SPECS
            },
            "complete_state_boundary_maximum_absolute_magnitude": {
                name: 1.0 for name in comparison.FIELD_SPECS
            },
            "complete_state_boundary_structure_equal": {
                name: True for name in comparison.FIELD_SPECS
            },
            "chemistry_fieldwise_combined_tolerance_satisfied": chemistry_fields,
            "chemistry_boundary_combined_tolerance_satisfied": {
                name: True for name in comparison.CHEMISTRY_FIELD_TOLERANCES
            },
            "exact_restart_state_fields_equal": {
                name: True for name in comparison.EXACT_RESTART_STATE_FIELDS
            },
            "exact_restart_state_boundaries_equal": {
                name: True for name in comparison.EXACT_RESTART_STATE_FIELDS
            },
            "front_differences": {
                comparison.MN_FREE: {
                    "defined": True,
                    "quantiles": {"x10": {"cell_index_delta": 0}},
                },
                comparison.MN_SORBED: {
                    "defined": True,
                    "quantiles": {"x90": {"cell_index_delta": front_shift}},
                },
            },
        }

    def _case(
        self, root: Path, suffix: str, mn: float,
        endpoint_sorbed: float | None = None,
        endpoint_r: float = 1.0,
    ) -> Path:
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
            if endpoint_sorbed is not None:
                total = endpoint_sorbed if time_name == "0.5" else 0.0
                values["Surf_sOMn+"] = 0.25 * total
                values["Surf_wOMn+"] = 0.75 * total
            values["R"] = endpoint_r if time_name == "0.5" else 0.0
            for name, (_, _, kind) in comparison.FIELD_SPECS.items():
                if name == "R" and time_name == "0":
                    continue
                if kind == "cell_vector":
                    foam_vector(directory / name, (0.0, 0.0, 0.0))
                else:
                    foam_scalar(directory / name, values.get(name, 1.0))
        return case

    def test_aggregate_tolerances_use_dimensioned_cell_weights(self) -> None:
        left = {
            "eps": np.array([0.5]), "aSurf": np.array([2.0]),
            "Mn+2": np.array([2.0]), "Mg+2": np.array([3.0]),
            "Cl-": np.array([4.0]), "Surf_sOMn+": np.array([0.25]),
            "Surf_wOMn+": np.array([0.75]), "Surf_wOMg+": np.array([0.5]),
        }
        right = {name: values.copy() for name, values in left.items()}
        volumes = np.array([2.0e-15])
        allowed = comparison.inventory_tolerance_arrays(left, right, volumes)
        aqueous = lambda scale: (
            comparison.AQUEOUS_RESTART_ABSOLUTE_TOLERANCE
            + comparison.AQUEOUS_RESTART_RELATIVE_TOLERANCE * scale
        )
        surface = lambda scale: (
            comparison.SURFACE_RESTART_ABSOLUTE_TOLERANCE
            + comparison.SURFACE_RESTART_RELATIVE_TOLERANCE * scale
        )
        self.assertEqual(allowed[comparison.MN_FREE][0], aqueous(2.0) * 1.0e-15)
        self.assertEqual(
            allowed[comparison.MN_SORBED][0],
            (surface(0.25) + surface(0.75)) * 4.0e-15,
        )

    def test_scientific_metrics_use_mesh_volume_and_report_no_false_flux_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = self._case(root, "left", 2.0)
            right = self._case(root, "right", 1.0)
            geometry = {
                "addressing": np.array([0]), "volumes": np.array([2.0e-15]),
                "centres": np.array([[5e-6, 5e-6, 5e-6]]), "x_index": np.array([0]),
                "internal_face_count": 0,
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
                result["reported_species_amount_kmol"]["left"]["endpoint"]
                [comparison.MN_FREE],
                2.0e-15,
            )
            self.assertAlmostEqual(
                result["relative_endpoint_reported_species_amount_difference"]
                [comparison.MN_FREE], 1.0
            )
            self.assertFalse(result["mass_balance_scope"]["boundary_flux_closure_evaluated"])
            self.assertIn("neither complete elemental inventories", result["mass_balance_scope"]["reason"])

    def test_scientific_metrics_accept_both_zero_sorbed_fronts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = self._case(root, "left", 1.0, endpoint_sorbed=0.0)
            right = self._case(root, "right", 1.0, endpoint_sorbed=0.0)
            geometry = {
                "addressing": np.array([0]), "volumes": np.array([2.0e-15]),
                "centres": np.array([[5e-6, 5e-6, 5e-6]]), "x_index": np.array([0]),
                "internal_face_count": 0,
            }
            with (
                mock.patch.object(comparison, "RANK_COUNT", 1),
                mock.patch.object(comparison, "GLOBAL_CELL_COUNT", 1),
                mock.patch.object(comparison, "NX", 1),
                mock.patch.object(comparison, "mesh_geometry", return_value=geometry),
            ):
                result = comparison.scientific_metrics(
                    left, right, 0.5, 0.5, "uninterrupted", "restarted"
                )
            self.assertEqual(
                result["fronts"]["uninterrupted"][comparison.MN_SORBED],
                {"defined": False, "quantiles": {}},
            )
            self.assertEqual(
                result["front_differences"][comparison.MN_SORBED],
                {"defined": False, "quantiles": {}},
            )
            self.assertTrue(all(comparison.evaluate_restart(result)["checks"].values()))

    def test_restart_complete_state_includes_reaction_rate_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = self._case(root, "left", 1.0, endpoint_r=1.0)
            right = self._case(root, "right", 1.0, endpoint_r=2.0)
            geometry = {
                "addressing": np.array([0]), "volumes": np.array([2.0e-15]),
                "centres": np.array([[5e-6, 5e-6, 5e-6]]), "x_index": np.array([0]),
                "internal_face_count": 0,
            }
            with (
                mock.patch.object(comparison, "RANK_COUNT", 1),
                mock.patch.object(comparison, "GLOBAL_CELL_COUNT", 1),
                mock.patch.object(comparison, "NX", 1),
                mock.patch.object(comparison, "mesh_geometry", return_value=geometry),
            ):
                metrics = comparison.scientific_metrics(
                    left, right, 0.5, 0.5, "uninterrupted", "restarted"
                )
            self.assertEqual(
                metrics["complete_state_fieldwise_maximum_absolute_difference"]["R"],
                1.0,
            )
            self.assertFalse(
                comparison.evaluate_restart(metrics)["checks"]
                ["non_chemistry_restart_state_fields_exact"]
            )

    def test_scientific_metrics_reject_one_sided_zero_sorbed_front(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = self._case(root, "left", 1.0, endpoint_sorbed=0.0)
            right = self._case(root, "right", 1.0, endpoint_sorbed=1.0)
            geometry = {
                "addressing": np.array([0]), "volumes": np.array([2.0e-15]),
                "centres": np.array([[5e-6, 5e-6, 5e-6]]), "x_index": np.array([0]),
                "internal_face_count": 0,
            }
            with (
                mock.patch.object(comparison, "RANK_COUNT", 1),
                mock.patch.object(comparison, "GLOBAL_CELL_COUNT", 1),
                mock.patch.object(comparison, "NX", 1),
                mock.patch.object(comparison, "mesh_geometry", return_value=geometry),
                self.assertRaisesRegex(comparison.ComparisonError, "defined in only one"),
            ):
                comparison.scientific_metrics(
                    left, right, 0.5, 0.5, "uninterrupted", "restarted"
                )

    def test_convergence_thresholds_are_strict_and_transparent(self) -> None:
        metrics = {
            "relative_endpoint_reported_species_amount_difference": {
                comparison.MN_FREE: 0.009,
                comparison.MN_SORBED: 0.01,
                comparison.MN_REPORTED: 0.001,
            },
            "spatial_relative_L1": {
                comparison.MN_FREE: 0.001, comparison.MN_SORBED: 0.002
            },
            "front_differences": {
                comparison.MN_FREE: {
                    "defined": True,
                    "quantiles": {"x10": {"cell_index_delta": 0}},
                },
                comparison.MN_SORBED: {
                    "defined": True,
                    "quantiles": {"x90": {"cell_index_delta": 1}},
                },
            },
        }
        result = comparison.evaluate_convergence(metrics)
        self.assertFalse(result["checks"]["Mn_reported_species_amounts_below_1pct"])
        self.assertEqual(
            result["tolerances"]["Mn_reported_species_amount_relative"],
            {"operator": "<", "value": 0.01},
        )
        self.assertTrue(result["checks"]["fronts_within_one_cell"])

    def test_restart_gate_requires_zero_front_shift(self) -> None:
        metrics = self.restart_metrics(front_shift=1)
        result = comparison.evaluate_restart(metrics)
        self.assertFalse(result["checks"]["front_indices_identical"])

    def test_restart_gate_does_not_fabricate_an_empty_front_shift(self) -> None:
        metrics = self.restart_metrics()
        metrics["front_differences"] = {
            phase: {"defined": False, "quantiles": {}}
            for phase in (comparison.MN_FREE, comparison.MN_SORBED)
        }
        result = comparison.evaluate_restart(metrics)
        self.assertIsNone(result["evaluated"]["maximum_front_cell_shift"])
        self.assertTrue(result["checks"]["front_indices_identical"])

    def test_restart_gate_catches_unreported_hydrogen_field_difference(self) -> None:
        metrics = self.restart_metrics(hydrogen_difference=0.5)
        result = comparison.evaluate_restart(metrics)
        self.assertFalse(
            result["checks"]["chemistry_fields_within_dimensioned_tolerances"]
        )

    def test_restart_gate_requires_exact_non_chemistry_state(self) -> None:
        metrics = self.restart_metrics()
        metrics["exact_restart_state_fields_equal"]["p"] = False
        result = comparison.evaluate_restart(metrics)
        self.assertFalse(result["checks"]["non_chemistry_restart_state_fields_exact"])

    def test_restart_near_zero_roundoff_uses_absolute_plus_relative_tolerance(self) -> None:
        scale = 7.25e-10
        boundary = (
            comparison.AQUEOUS_RESTART_ABSOLUTE_TOLERANCE
            + comparison.AQUEOUS_RESTART_RELATIVE_TOLERANCE * scale
        )
        self.assertTrue(comparison.combined_tolerance_satisfied(
            "H+", np.array([scale]), np.array([scale - boundary])
        ))
        self.assertFalse(comparison.combined_tolerance_satisfied(
            "H+", np.array([scale]), np.array([scale - 1.01 * boundary])
        ))

    def test_restart_surface_fields_use_the_approved_surface_tolerance(self) -> None:
        left = np.array([1.0])
        right = np.array([1.0 - 1.0e-4])
        self.assertTrue(comparison.combined_tolerance_satisfied("H+", left, right))
        self.assertFalse(
            comparison.combined_tolerance_satisfied("Surf_sOMn+", left, right)
        )

    def test_restart_near_zero_reported_amount_uses_combined_tolerance(self) -> None:
        metrics = self.restart_metrics()
        for label in ("uninterrupted", "restarted"):
            metrics["reported_species_amount_kmol"][label]["endpoint"][comparison.MN_FREE] = 1e-20
        metrics["relative_endpoint_reported_species_amount_difference"][comparison.MN_FREE] = 5e-5
        metrics["absolute_endpoint_reported_species_amount_difference_kmol"][comparison.MN_FREE] = 5e-25
        metrics["derived_inventory_and_spatial_L1_tolerance_kmol"][comparison.MN_FREE] = 1e-24
        result = comparison.evaluate_restart(metrics)
        self.assertTrue(result["checks"]["reported_species_amounts_within_combined_tolerance"])
        metrics["absolute_endpoint_reported_species_amount_difference_kmol"][comparison.MN_FREE] = 2e-24
        result = comparison.evaluate_restart(metrics)
        self.assertFalse(result["checks"]["reported_species_amounts_within_combined_tolerance"])

    def test_static_field_drift_at_restart_checkpoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rank = Path(tmp) / "processor0"
            mesh = rank / "constant/polyMesh"
            mesh.mkdir(parents=True)
            foam_list(mesh / "cellProcAddressing", "labelList", ["0"])
            for time_name in ("0", "0.0125", "0.025"):
                directory = rank / time_name
                directory.mkdir(parents=True)
                for name in comparison.STATIC_FIELDS:
                    foam_scalar(directory / name, 1.0)
            foam_scalar(rank / "0.0125/eps", 0.9)
            with self.assertRaisesRegex(comparison.ComparisonError, "Static internal field"):
                comparison.verify_static_timepoints([rank], [0.0, 0.0125, 0.025])

    def test_exact_restart_endpoint_is_mandatory(self) -> None:
        with self.assertRaisesRegex(comparison.ComparisonError, "required restart endpoint"):
            comparison.compare_restart(Path("left"), Path("right"), 0.123, Path("accepted.json"))


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
            "realized_initialization_dictionaries": [
                {"source": "system/controlDict", "snapshot": {"sha256": "control"}}
            ],
            "transport_stages": [],
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

    def test_mismatched_realized_initialization_dictionary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left_root, right_root = root / "left", root / "right"
            left_root.mkdir()
            right_root.mkdir()
            left = self.payload(left_root)
            right = self.payload(right_root)
            right["realized_initialization_dictionaries"][0]["snapshot"]["sha256"] = "other"
            with self.assertRaisesRegex(
                comparison.ComparisonError, "Realized initialization dictionaries"
            ):
                comparison.verify_pair_identity(
                    left, right, left_root / "case", right_root / "case"
                )


class ScheduleAndCliTests(unittest.TestCase):
    @staticmethod
    def integrity(delta_t: float, schedule: list[tuple[float, float, bool]]) -> dict[str, object]:
        return {
            "delta_t_s": delta_t,
            "stage_chain": {
                "completed_schedule": [
                    {"start_time_s": start, "end_time_s": end, "restore": restore}
                    for start, end, restore in schedule
                ]
            },
        }

    def test_convergence_rejects_multistage_schedule(self) -> None:
        coarse = self.integrity(
            comparison.COARSE_DT_S, [(0.0, 0.25, False), (0.25, 0.5, True)]
        )
        fine = self.integrity(comparison.FINE_DT_S, [(0.0, 0.5, False)])
        with (
            mock.patch.object(comparison, "validate_case", side_effect=[({}, coarse), ({}, fine)]),
            self.assertRaisesRegex(comparison.ComparisonError, "one uninterrupted"),
        ):
            comparison.compare_convergence(Path("coarse"), Path("fine"))

    def test_restart_rejects_wrong_split_and_timestep(self) -> None:
        uninterrupted = self.integrity(
            comparison.ACCEPTED_DT_S, [(0.0, comparison.RESTART_ENDPOINT_S, False)]
        )
        wrong_split = self.integrity(
            comparison.ACCEPTED_DT_S,
            [(0.0, 0.01, False), (0.01, comparison.RESTART_ENDPOINT_S, True)],
        )
        with (
            mock.patch.object(comparison, "validate_convergence_acceptance", return_value=({}, {})),
            mock.patch.object(
                comparison, "validate_case", side_effect=[({}, uninterrupted), ({}, wrong_split)]
            ),
            self.assertRaisesRegex(comparison.ComparisonError, "required 0-to-0.0125"),
        ):
            comparison.compare_restart(
                Path("uninterrupted"), Path("restarted"), comparison.RESTART_ENDPOINT_S,
                Path("accepted.json"),
            )
        wrong_dt = self.integrity(0.0001, [(0.0, comparison.RESTART_ENDPOINT_S, False)])
        restarted = self.integrity(
            0.0001,
            [(0.0, comparison.RESTART_SPLIT_S, False),
             (comparison.RESTART_SPLIT_S, comparison.RESTART_ENDPOINT_S, True)],
        )
        with (
            mock.patch.object(comparison, "validate_convergence_acceptance", return_value=({}, {})),
            mock.patch.object(comparison, "validate_case", side_effect=[({}, wrong_dt), ({}, restarted)]),
            self.assertRaisesRegex(comparison.ComparisonError, "accepted restart deltaT"),
        ):
            comparison.compare_restart(
                Path("uninterrupted"), Path("restarted"), comparison.RESTART_ENDPOINT_S,
                Path("accepted.json"),
            )

    def test_restart_rejects_identity_different_from_accepted_convergence_pair(self) -> None:
        uninterrupted = self.integrity(
            comparison.ACCEPTED_DT_S,
            [(0.0, comparison.RESTART_ENDPOINT_S, False)],
        )
        restarted = self.integrity(
            comparison.ACCEPTED_DT_S,
            [
                (0.0, comparison.RESTART_SPLIT_S, False),
                (comparison.RESTART_SPLIT_S, comparison.RESTART_ENDPOINT_S, True),
            ],
        )
        with (
            mock.patch.object(
                comparison, "validate_convergence_acceptance",
                return_value=({"pair_identity": {"stack": "convergence"}}, {}),
            ),
            mock.patch.object(
                comparison, "validate_case",
                side_effect=[({}, uninterrupted), ({}, restarted)],
            ),
            mock.patch.object(
                comparison, "verify_pair_identity",
                return_value={"stack": "restart"},
            ),
            self.assertRaisesRegex(comparison.ComparisonError, "pair identity differs"),
        ):
            comparison.compare_restart(
                Path("uninterrupted"), Path("restarted"),
                comparison.RESTART_ENDPOINT_S, Path("accepted.json"),
            )

    def test_restart_requires_a_passing_current_convergence_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "convergence.json"
            path.write_text(json.dumps({
                "schema_version": comparison.SCHEMA_VERSION,
                "comparison": "3d_kelvin_temporal_convergence",
                "pass": False,
            }))
            with self.assertRaisesRegex(comparison.ComparisonError, "not accepted"):
                comparison.validate_convergence_acceptance(path)

    def test_restart_acceptance_binds_recomputed_gate_code_and_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = []
            for name in ("coarse.json", "fine.json"):
                manifest = root / name
                manifest.write_text("{}\n")
                manifests.append(manifest)
            metrics = {
                "relative_endpoint_reported_species_amount_difference": {
                    comparison.MN_FREE: 0.001,
                    comparison.MN_SORBED: 0.001,
                    comparison.MN_REPORTED: 0.001,
                },
                "spatial_relative_L1": {
                    comparison.MN_FREE: 0.001, comparison.MN_SORBED: 0.001,
                },
                "front_differences": {
                    comparison.MN_FREE: {
                        "defined": True,
                        "quantiles": {"x10": {"cell_index_delta": 0}},
                    },
                    comparison.MN_SORBED: {
                        "defined": True,
                        "quantiles": {"x90": {"cell_index_delta": 1}},
                    },
                },
            }
            acceptance = comparison.evaluate_convergence(metrics)
            acceptance["pass"] = all(acceptance["checks"].values())
            artifact = {
                "schema_version": comparison.SCHEMA_VERSION,
                "comparison": "3d_kelvin_temporal_convergence",
                "required_pair": {
                    "coarse_delta_t_s": comparison.COARSE_DT_S,
                    "fine_delta_t_s": comparison.FINE_DT_S,
                    "refinement_ratio": 2.0, "endpoint_s": comparison.END_TIME_S,
                },
                "sources": {
                    "comparator": {"sha256": comparison.sha256(comparison.SCRIPT)},
                    "comparator_tests": {"sha256": comparison.sha256(comparison.TEST_SCRIPT)},
                    "coarse_case": {
                        "case": str((root / "coarse").resolve()),
                        "pass": True, "run_manifest": comparison.file_record(manifests[0])
                    },
                    "fine_case": {
                        "case": str((root / "fine").resolve()),
                        "pass": True, "run_manifest": comparison.file_record(manifests[1])
                    },
                },
                "metrics": metrics, "acceptance": acceptance, "pass": True,
            }
            path = root / "convergence.json"
            path.write_text(json.dumps(artifact))
            with mock.patch.object(comparison, "compare_convergence", return_value=artifact):
                _, record = comparison.validate_convergence_acceptance(path)
            self.assertEqual(record["sha256"], comparison.sha256(path))
            fabricated = json.loads(json.dumps(artifact))
            fabricated["metrics"]["relative_endpoint_reported_species_amount_difference"][
                comparison.MN_FREE
            ] = 0.0
            fabricated_path = root / "fabricated.json"
            fabricated_path.write_text(json.dumps(fabricated))
            with (
                mock.patch.object(comparison, "compare_convergence", return_value=artifact),
                self.assertRaisesRegex(comparison.ComparisonError, "fresh authenticated"),
            ):
                comparison.validate_convergence_acceptance(fabricated_path)

    def test_cli_writes_result_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "comparison.json"
            result = {"pass": True, "comparison": "fixture"}
            with mock.patch.object(comparison, "compare_convergence", return_value=result):
                comparison.main([
                    "convergence", "--coarse-case", "coarse", "--fine-case", "fine",
                    "--output", str(output),
                ])
                self.assertEqual(comparison.load_json(output), result)
                with self.assertRaisesRegex(SystemExit, "Refusing to overwrite"):
                    comparison.main([
                        "convergence", "--coarse-case", "coarse", "--fine-case", "fine",
                        "--output", str(output),
                    ])


class Schema9EndToEndTests(unittest.TestCase):
    @staticmethod
    def control_text(start: float, end: float, delta_t: float, restore: bool) -> str:
        return (
            "application reactiveTransportDBSFoam;\n"
            "startFrom startTime;\n"
            f"startTime {start:.17g};\n"
            "stopAt endTime;\n"
            f"endTime {end:.17g};\n"
            f"deltaT {delta_t:.17g};\n"
            "writeControl adjustableRunTime;\n"
            f"writeInterval {end - start:.17g};\n"
            "purgeWrite 0;\nwriteFormat ascii;\nwritePrecision 16;\n"
            "writeCompression off;\ntimeFormat general;\ntimePrecision 8;\n"
            "runTimeModifiable yes;\nphreeqcRestartCheckpoints true;\n"
            f"phreeqcRestoreCheckpoint {'true' if restore else 'false'};\n"
        )

    @staticmethod
    def snapshots(case: Path, root: Path) -> list[dict[str, object]]:
        records = []
        for source in comparison.provenance.REQUIRED_REALIZED_DICTIONARIES:
            destination = root / source
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(case / source, destination)
            records.append(
                {"source": str(source), "snapshot": comparison.provenance.file_record(destination)}
            )
        return records

    def make_case(
        self, root: Path, delta_t: float = comparison.COARSE_DT_S,
        *, runtime: dict[str, object] | None = None,
        runtime_artifacts: dict[str, object] | None = None,
        paper: dict[str, object] | None = None,
        tracked_template: Path | None = None,
    ) -> Path:
        case = root / "case"
        rank = case / "processor0"
        JsonAndGeometryTests()._one_cell_mesh(rank)
        for time_name in ("0", "0.5"):
            directory = rank / time_name
            directory.mkdir(parents=True)
            for name, (_, _, kind) in comparison.FIELD_SPECS.items():
                if name == "R" and time_name == "0":
                    continue
                if kind == "cell_vector":
                    foam_vector(directory / name, (0.0, 0.0, 0.0))
                else:
                    value = 1.0
                    if name == "Surf_s":
                        value = 2.0e-7
                    elif name == "Surf_w":
                        value = 6.0e-6
                    foam_scalar(directory / name, value)

        for source in comparison.provenance.REQUIRED_REALIZED_DICTIONARIES:
            path = case / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture {source};\n")
        control = case / "system/controlDict"
        control.write_text(self.control_text(0.0, 0.5, delta_t, False))
        template = case / "system/controlDict1"
        template.write_text(
            self.control_text(0.0, 0.5, comparison.COARSE_DT_S, False)
        )

        chemistry = case / "constant/GeoChem.dat"
        chemistry.write_text("SOLUTION 0\nEND\n")
        for filename in ("createASurfReactive.out", "createASurfIntrinsicReactive.out"):
            (case / filename).write_text(
                "mode=occupancyGaussian sigma_vox=0.75 sum(aSurf*V)=1.0e-9\n"
            )

        initial_snapshots = self.snapshots(case, case / "provenance/initialization")
        for record in initial_snapshots:
            if record["source"] == "system/controlDict":
                snapshot_path = Path(str(record["snapshot"]["path"]))
                snapshot_path.write_text(template.read_text())
                record["snapshot"] = comparison.provenance.file_record(snapshot_path)
        stage_id = "0_to_0.5_attempt_001"
        stage_snapshots = self.snapshots(case, case / "provenance/stages" / stage_id)
        initial_records = (
            comparison.provenance.tree_records(rank / "0", case)
            + comparison.provenance.tree_records(rank / "constant/polyMesh", case)
        )
        initial_digest = comparison.provenance.records_digest(initial_records)
        noncontrol_records = [
            {"path": str(source), "sha256": comparison.sha256(case / source)}
            for source in sorted(comparison.provenance.REQUIRED_REALIZED_DICTIONARIES)
            if source != Path("system/controlDict")
        ]
        dictionary_digest = comparison.provenance.records_digest(noncontrol_records)
        control_digest = comparison.provenance.immutable_control_digest(control)

        dump = rank / "0.5/phreeqc.dmp"
        dump.write_bytes(b"schema-9-fixture-checkpoint")
        marker = rank / "0.5/phreeqc.complete"
        marker.write_text(
            "PHREEQCRM and OpenFOAM fields written for time 0.5\n"
        )
        log = case / "solver-stage-001.out"
        log.write_text("Time = 0.5\nEnd\n")
        stage = {
            **comparison.provenance.control_values(control),
            "stage_id": stage_id, "attempt": 1, "status": "completed",
            "chain_relation": "initial", "recorded_utc": "2026-01-01T00:00:00+00:00",
            "rank_count": 1, "decomposition": {"NPX": 1, "NPY": 1, "NPZ": 1},
            "initial_case_identity_sha256": initial_digest,
            "immutable_dictionary_sha256": dictionary_digest,
            "immutable_control_sha256": control_digest,
            "dictionaries": stage_snapshots,
            "surface_master_fields": [
                {
                    "path": str((rank / "0" / name).resolve()),
                    "sha256": comparison.sha256(rank / "0" / name),
                    "value_kmol_m2": value,
                }
                for name, value in (("Surf_s", 2.0e-7), ("Surf_w", 6.0e-6))
            ],
            "selected_start_time_directories": [
                {"rank": "processor0", "path": str((rank / "0").resolve()), "time_name": "0"}
            ],
            "start_rank_inputs": comparison.provenance.tree_records(
                rank / "0", case,
                {"phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp"},
            ),
            "restart_checkpoints": [],
            "completed_utc": "2026-01-01T00:01:00+00:00", "solver_exit_status": 0,
            "solver_log": comparison.provenance.file_record(log),
            "endpoint_time_directories": [
                {"rank": "processor0", "path": str((rank / "0.5").resolve()), "time_name": "0.5"}
            ],
            "endpoint_rank_outputs": comparison.provenance.tree_records(
                rank / "0.5", case,
                {"phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp"},
            ),
            "endpoint_checkpoints": [
                {"rank": "processor0", "time_name": "0.5", **comparison.provenance.checkpoint_record(
                    rank / "0.5", 0.5, case, "processor0"
                )}
            ],
        }
        runtime = runtime or {
            "root": str(case), "commit": "g", "tree": "gt",
            "tracked_diff_sha256": comparison.EMPTY_SHA256, "phreeqcrm_gitlink": "p",
            "phreeqcrm": {
                "root": str(case / "ThirdParty/PhreeqcRM"), "commit": "p", "tree": "pt",
                "tracked_diff_sha256": comparison.EMPTY_SHA256,
            },
        }
        paper = paper or {
            "root": str(case), "commit": "paper", "tree": "paper-tree",
            "tracked_diff_sha256": comparison.EMPTY_SHA256,
        }
        tracked_template = tracked_template or template
        payload = {
            "schema_version": comparison.MANIFEST_SCHEMA_VERSION, "case_id": "3d_kelvin",
            "recorded_utc": "2026-01-01T00:00:00+00:00",
            "paper": paper,
            "transport_control_template": comparison.provenance.file_record(template),
            "tracked_transport_control_template": comparison.provenance.file_record(
                tracked_template
            ),
            "runtime": runtime,
            "runtime_artifacts": runtime_artifacts or {"identity_sha256": "fixture"},
            "surface": comparison.provenance.surface_record(
                case / "createASurfReactive.out", "occupancyGaussian", 0.75
            ),
            "intrinsic_surface": comparison.provenance.surface_record(
                case / "createASurfIntrinsicReactive.out", "occupancyGaussian", 0.75
            ),
            "chemistry": {"files": [comparison.provenance.file_record(chemistry)]},
            "realized_initialization_dictionaries": initial_snapshots,
            "transport_stages": [stage],
            "initial_case": {"sha256": initial_digest, "records": initial_records},
        }
        (case / "run_provenance.json").write_text(json.dumps(payload, indent=2) + "\n")
        return case

    @staticmethod
    def git(root: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout.strip()

    def committed_repo(self, root: Path) -> None:
        root.mkdir(parents=True)
        self.git(root, "init", "-q")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        self.git(root, "config", "user.name", "Fixture")

    def real_identities(
        self, root: Path
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object], Path, dict[str, str]]:
        phreeqcrm = root / "phreeqcrm"
        self.committed_repo(phreeqcrm)
        (phreeqcrm / "README").write_text("fixture PHREEQCRM\n")
        self.git(phreeqcrm, "add", "README")
        self.git(phreeqcrm, "commit", "-qm", "fixture")

        runtime_root = root / "runtime"
        self.committed_repo(runtime_root)
        (runtime_root / "ThirdParty").mkdir()
        subprocess.run(
            [
                "git", "-c", "protocol.file.allow=always", "-C", str(runtime_root),
                "submodule", "add", "-q", str(phreeqcrm), "ThirdParty/PhreeqcRM",
            ],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.git(runtime_root, "commit", "-qam", "fixture runtime")
        binary_dir = runtime_root / "bin"
        binary_dir.mkdir()
        source = root / "solver.cpp"
        source.write_text("int main() { return 0; }\n")
        for name in ("simpleDBSFoam", "reactiveTransportDBSFoam"):
            subprocess.run(
                ["c++", str(source), "-o", str(binary_dir / name)], check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        environment = {key: f"fixture-{key}" for key in comparison.provenance.IDENTITY_ENV}
        environment["PATH"] = str(binary_dir) + os.pathsep + os.environ["PATH"]
        with mock.patch.dict(os.environ, environment, clear=False):
            runtime_commit, runtime_tree = comparison.provenance.commit_tree(runtime_root)
            sub_commit, sub_tree = comparison.provenance.commit_tree(
                runtime_root / "ThirdParty/PhreeqcRM"
            )
            gitlink = self.git(runtime_root, "ls-tree", "HEAD", "ThirdParty/PhreeqcRM").split()[2]
            runtime = comparison.provenance.runtime_git_identity(
                runtime_root, runtime_commit, runtime_tree, gitlink, sub_commit, sub_tree
            )
            artifacts = comparison.provenance.runtime_artifacts(runtime_root)

        paper_root = root / "paper"
        self.committed_repo(paper_root)
        tracked_template = paper_root / comparison.provenance.TRACKED_CONTROL_TEMPLATE
        tracked_template.parent.mkdir(parents=True)
        tracked_template.write_text(
            self.control_text(0.0, 0.5, comparison.COARSE_DT_S, False)
        )
        self.git(paper_root, "add", ".")
        self.git(paper_root, "commit", "-qm", "fixture paper")
        paper = comparison.provenance.paper_identity(paper_root)
        return runtime, artifacts, paper, tracked_template, environment

    def size_patches(self):
        return (
            mock.patch.object(comparison, "RANK_COUNT", 1),
            mock.patch.object(comparison, "DECOMPOSITION", {"NPX": 1, "NPY": 1, "NPZ": 1}),
            mock.patch.object(comparison, "NX", 1),
            mock.patch.object(comparison, "NY", 1),
            mock.patch.object(comparison, "NZ", 1),
            mock.patch.object(comparison, "GLOBAL_CELL_COUNT", 1),
            mock.patch.object(comparison, "DOMAIN_LENGTH_M", comparison.CELL_SIZE_M),
        )

    def patches(self):
        return self.size_patches() + (
            mock.patch.object(comparison.provenance, "validate_recorded_runtime"),
            mock.patch.object(comparison.provenance, "validate_recorded_paper"),
            mock.patch.object(comparison.provenance, "validate_control_template_record"),
        )

    def test_schema9_case_authenticates_end_to_end_and_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            case = self.make_case(Path(tmp))
            patchers = self.patches()
            with (
                patchers[0], patchers[1], patchers[2], patchers[3], patchers[4],
                patchers[5], patchers[6], patchers[7], patchers[8], patchers[9],
            ):
                payload, integrity = comparison.validate_case(case, 0.5)
                self.assertEqual(payload["schema_version"], 9)
                self.assertTrue(integrity["stage_chain"]["all_checkpoint_pairs_valid"])
                self.assertEqual(
                    integrity["static_field_contract"]["times_s"], [0.0, 0.5]
                )
                self.assertIn("R", integrity["endpoint"]["field_statistics"])
                foam_scalar(case / "processor0/0.5/H+", 2.0)
                with self.assertRaisesRegex(comparison.ComparisonError, "Endpoint outputs changed"):
                    comparison.validate_case(case, 0.5)

    def test_unmocked_schema9_cli_traverses_real_identity_and_validation_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, artifacts, paper, tracked_template, environment = self.real_identities(root)
            coarse = self.make_case(
                root / "coarse", comparison.COARSE_DT_S, runtime=runtime,
                runtime_artifacts=artifacts, paper=paper, tracked_template=tracked_template,
            )
            fine = self.make_case(
                root / "fine", comparison.FINE_DT_S, runtime=runtime,
                runtime_artifacts=artifacts, paper=paper, tracked_template=tracked_template,
            )
            output = root / "convergence.json"
            size_patchers = self.size_patches()
            with (
                size_patchers[0], size_patchers[1], size_patchers[2], size_patchers[3],
                size_patchers[4], size_patchers[5], size_patchers[6],
                mock.patch.dict(os.environ, environment, clear=False),
            ):
                comparison.main([
                    "convergence", "--coarse-case", str(coarse),
                    "--fine-case", str(fine), "--output", str(output),
                ])
                rehydrated, _ = comparison.validate_convergence_acceptance(output)
                self.assertTrue(rehydrated["pass"])
            artifact = comparison.load_json(output)
            self.assertTrue(artifact["pass"])
            self.assertTrue(artifact["sources"]["coarse_case"]["pass"])
            self.assertTrue(artifact["sources"]["fine_case"]["pass"])


if __name__ == "__main__":
    unittest.main()
