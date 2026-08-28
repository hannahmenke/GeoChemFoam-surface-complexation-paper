#!/usr/bin/env python3

from __future__ import annotations

import unittest

from estimate_archer_storage import GIB, case_cells, estimate_bytes, required_bytes


class StorageEstimateTests(unittest.TestCase):
    def test_default_dbs_cell_count(self) -> None:
        self.assertEqual(case_cells("dbs-upscaled", {}), 4_320_000)

    def test_ten_checkpoint_dbs_scratch_budget_is_about_206_gib(self) -> None:
        estimate = estimate_bytes("dbs-upscaled", 10, "scratch", "selected", {})
        self.assertEqual(estimate, 221_368_709_120)
        self.assertGreater(estimate, 205 * GIB)
        self.assertLess(estimate, 207 * GIB)

    def test_full_archive_matches_scratch_budget(self) -> None:
        scratch = estimate_bytes("dbs-upscaled", 10, "scratch", "full", {})
        archive = estimate_bytes("dbs-upscaled", 10, "archive", "full", {})
        self.assertEqual(archive, scratch)

    def test_selected_archive_excludes_checkpoint_dumps(self) -> None:
        selected = estimate_bytes("dbs-upscaled", 10, "archive", "selected", {})
        self.assertEqual(selected, 34_118_309_120)

    def test_checkpoint_budget_scales_linearly(self) -> None:
        one = estimate_bytes("dbs-upscaled", 1, "scratch", "metadata", {})
        ten = estimate_bytes("dbs-upscaled", 10, "scratch", "metadata", {})
        self.assertEqual(ten - one, 9 * 4_320_000 * 5000)

    def test_rejects_invalid_geometry(self) -> None:
        with self.assertRaisesRegex(ValueError, "divisible"):
            case_cells(
                "dbs-upscaled",
                {"DBS_CROP_X_MAX": "1199", "DBS_COARSEN_FACTOR": "2"},
            )

    def test_override_may_increase_requirement(self) -> None:
        self.assertEqual(required_bytes(100, "120"), 120)

    def test_override_cannot_reduce_requirement(self) -> None:
        with self.assertRaisesRegex(ValueError, "below modeled"):
            required_bytes(100, "99")

    def test_override_must_be_an_integer(self) -> None:
        with self.assertRaisesRegex(ValueError, "integer"):
            required_bytes(100, "1e3")


if __name__ == "__main__":
    unittest.main()
