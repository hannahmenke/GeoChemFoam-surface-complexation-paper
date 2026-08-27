#!/usr/bin/env python3
"""Focused fail-closed tests for the matched reconstruction analyzer."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_matched_reconstruction_pair import (
    ValidationError,
    acceptance_checks,
    select_checkpoints,
    validate_provenance_pair,
    verify_clean_completion,
)


def provenance(label: str, mode: str, surface_hash: str) -> dict[str, object]:
    return {
        "reconstruction_label": label,
        "surface_mode": mode,
        "paper_source_commit": "paper-commit",
        "runtime": {
            "commit": "runtime-commit",
            "phreeqcrm": {"commit": "phreeqcrm-commit"},
        },
        "solver": {"sha256": "solver-hash"},
        "resolved_libraries": [{"name": "libexample.so", "sha256": "lib-hash"}],
        "run_config": {
            "ASURF_SURFACE_MODE": mode,
            "SURFACE_RECONSTRUCTION_LABEL": label,
            "RT_TIMESTEP": "0.1",
            "RT_TOTAL_TIME": "100",
            "RT_CHECKPOINT_COUNT": "10",
        },
        "initial": {
            "surface_log_modes": [mode],
            "matched_input_files": [
                {
                    "path": "dbs-upscaled/constant/input",
                    "bytes": 10,
                    "sha256": "input",
                }
            ],
            "surface_field_files": [
                {
                    "path": "dbs-upscaled/processor0/0/aSurf",
                    "bytes": 20,
                    "sha256": surface_hash,
                }
            ],
        },
        "final": {},
    }


class ProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.supported = provenance("supported", "supported-mode", "supported-hash")
        self.legacy = provenance("legacy-reference", "legacy-mode", "legacy-hash")

    def test_accepts_sole_surface_difference(self) -> None:
        validate_provenance_pair(self.supported, self.legacy)

    def test_rejects_non_surface_input_difference(self) -> None:
        self.legacy["initial"]["matched_input_files"][0]["sha256"] = "different"
        with self.assertRaisesRegex(ValidationError, "Non-surface input"):
            validate_provenance_pair(self.supported, self.legacy)

    def test_rejects_same_surface_mode(self) -> None:
        self.legacy["surface_mode"] = "supported-mode"
        self.legacy["initial"]["surface_log_modes"] = ["supported-mode"]
        with self.assertRaisesRegex(ValidationError, "same reconstruction mode"):
            validate_provenance_pair(self.supported, self.legacy)

    def test_rejects_runtime_difference(self) -> None:
        self.legacy["solver"]["sha256"] = "different"
        with self.assertRaisesRegex(ValidationError, "Runtime, solver"):
            validate_provenance_pair(self.supported, self.legacy)


class CheckpointTests(unittest.TestCase):
    def test_selects_all_ten_expected_checkpoints(self) -> None:
        times = [(float(value), str(value)) for value in range(10, 101, 10)]
        selected = select_checkpoints(
            times,
            copy.deepcopy(times),
            {
                "RT_TIMESTEP": "0.1",
                "RT_TOTAL_TIME": "100",
                "RT_CHECKPOINT_COUNT": "10",
            },
            10,
            False,
        )
        self.assertEqual(len(selected), 10)
        self.assertEqual(selected[-1]["time_s"], 100.0)

    def test_rejects_missing_checkpoint(self) -> None:
        times = [(float(value), str(value)) for value in range(10, 100, 10)]
        with self.assertRaisesRegex(ValidationError, "No checkpoint"):
            select_checkpoints(
                times,
                copy.deepcopy(times),
                {
                    "RT_TIMESTEP": "0.1",
                    "RT_TOTAL_TIME": "100",
                    "RT_CHECKPOINT_COUNT": "10",
                },
                10,
                False,
            )

    def test_rejects_incomplete_final_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValidationError, "partition count"):
                verify_clean_completion(
                    Path(directory) / "dbs-upscaled",
                    {"final": {"partitions": 0}},
                    {"partitions": 1},
                    "100",
                    False,
                )


class AcceptanceTests(unittest.TestCase):
    def test_rejects_field_l2_above_one_percent(self) -> None:
        comparison = {
            "reactive_area_relative_difference": 0.0001,
            "aqueous_li_inventory_relative_difference": 0.001,
            "sorbed_li_inventory_relative_difference": 0.001,
            "aqueous_li_normalized_l1": 0.001,
            "sorbed_li_normalized_l1": 0.001,
            "aqueous_li_field_relative_l2": 0.001,
            "sorbed_li_field_relative_l2": 0.0101,
            "aqueous_li_cosine": 0.999,
            "sorbed_li_cosine": 0.999,
            "aqueous_front_shift_m": {"x10": 0.0, "x50": 0.0, "x90": 5e-6},
            "sorbed_front_shift_m": {"x10": 0.0, "x50": 0.0, "x90": 0.0},
        }
        checks = acceptance_checks(comparison, 5e-6)
        self.assertTrue(checks["all_front_shifts_within_one_cell"])
        self.assertFalse(checks["sorbed_field_l2_below_1_percent"])
        self.assertFalse(all(checks.values()))


if __name__ == "__main__":
    unittest.main()
