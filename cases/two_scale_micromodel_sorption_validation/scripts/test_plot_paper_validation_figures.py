#!/usr/bin/env python3
"""Focused tests for the two-scale publication sweep figure."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_paper_validation_figures import plot_error_summary
from reproduce_paper_validation import publication_pngs


class FigureNineTests(unittest.TestCase):
    def test_publication_sweep_has_two_panels_and_retains_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs: list[str] = []
            for pe in (0.1, 1.0, 3.0, 10.0):
                path = root / f"pe{pe:g}.json"
                path.write_text(
                    json.dumps(
                        {
                            "dbs_vs_resolved": {
                                "aqueous_li_inventory_density_relative_difference": -0.0055,
                                "sorbed_li_inventory_density_relative_difference": 0.0040,
                                "aqueous_li_profile_normalized_l1_100_bins": 0.0056,
                                "sorbed_li_profile_normalized_l1_100_bins": 0.04745,
                                "aqueous_li_macro_map_cosine": 0.998,
                                "sorbed_li_macro_map_cosine": 0.997,
                            }
                        }
                    )
                )
                specs.append(f"{pe:g}={path}")

            captured = []

            def capture(figure, stem):
                captured.append((figure, stem))

            with patch("plot_paper_validation_figures.save_figure", side_effect=capture):
                records = plot_error_summary(specs, root, 1.25)

            self.assertEqual(len(captured), 1)
            figure, stem = captured[0]
            self.assertEqual(stem.name, "paper_error_vs_peclet")
            self.assertEqual(len(figure.axes), 2)
            self.assertEqual(
                [axis.get_title() for axis in figure.axes],
                ["Integrated inventory", "Streamwise profile shape"],
            )
            self.assertEqual([record["pe"] for record in records], [0.1, 1.0, 3.0, 10.0])
            self.assertIn("aqueous_map_dissimilarity", records[0])
            self.assertIn("sorbed_map_dissimilarity", records[0])
            csv_text = (root / "paper_error_vs_peclet.csv").read_text()
            self.assertIn("aqueous_map_dissimilarity", csv_text)

    def test_publish_targets_include_figure_nine_and_pe1_fields(self) -> None:
        self.assertEqual(
            publication_pngs("pe1_fields"),
            (
                ("pe1_fields.png", "fig10_two_scale_pe1_fields.png"),
                ("paper_error_vs_peclet.png", "fig09_two_scale_error_vs_peclet.png"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
