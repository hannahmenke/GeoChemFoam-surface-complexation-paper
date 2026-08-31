#!/usr/bin/env python3
"""Adversarial tests for Kelvin runtime and dictionary provenance."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).with_name("kelvin_provenance.py")
SPEC = importlib.util.spec_from_file_location("kelvin_provenance", MODULE_PATH)
assert SPEC and SPEC.loader
PROVENANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVENANCE)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def commit(root: Path, message: str) -> None:
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", message)


class RuntimeIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "runtime"
        self.submodule = self.root / "ThirdParty" / "PhreeqcRM"
        self.submodule.mkdir(parents=True)
        git(self.submodule, "init")
        (self.submodule / "source.cpp").write_text("first\n")
        git(self.submodule, "add", "source.cpp")
        commit(self.submodule, "adapter base")

        git(self.root, "init")
        (self.root / "solver.C").write_text("solver\n")
        git(self.root, "add", "solver.C", "ThirdParty/PhreeqcRM")
        commit(self.root, "runtime")
        self.runtime_commit, self.runtime_tree = PROVENANCE.commit_tree(self.root)
        self.gitlink = git(self.root, "ls-tree", "HEAD", "ThirdParty/PhreeqcRM").split()[2]

        (self.submodule / "source.cpp").write_text("reviewed stack\n")
        git(self.submodule, "add", "source.cpp")
        commit(self.submodule, "adapter stack")
        self.adapter_commit, self.adapter_tree = PROVENANCE.commit_tree(self.submodule)
        (self.submodule / "lib").mkdir()
        (self.submodule / "lib" / "build-output.so").write_text("untracked build output\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def identity(self, **overrides: str) -> dict[str, object]:
        values = {
            "expected_commit": self.runtime_commit,
            "expected_tree": self.runtime_tree,
            "expected_gitlink": self.gitlink,
            "expected_phreeqcrm_commit": self.adapter_commit,
            "expected_phreeqcrm_tree": self.adapter_tree,
        }
        values.update(overrides)
        return PROVENANCE.runtime_git_identity(self.root, **values)

    def test_intentional_stack_and_untracked_build_outputs_pass(self) -> None:
        identity = self.identity()
        self.assertTrue(identity["phreeqcrm"]["differs_from_gitlink"])
        self.assertEqual(identity["phreeqcrm"]["commit"], self.adapter_commit)

    def test_wrong_independently_expected_identity_fails(self) -> None:
        wrong = "0" * 40
        for key in (
            "expected_commit", "expected_tree", "expected_gitlink",
            "expected_phreeqcrm_commit", "expected_phreeqcrm_tree",
        ):
            with self.subTest(key=key), self.assertRaises(SystemExit):
                self.identity(**{key: wrong})

    def test_tracked_runtime_or_adapter_dirt_fails(self) -> None:
        (self.root / "solver.C").write_text("dirty\n")
        with self.assertRaisesRegex(SystemExit, "GeoChemFoam runtime has tracked"):
            self.identity()
        (self.root / "solver.C").write_text("solver\n")
        self.identity()

        (self.submodule / "source.cpp").write_text("dirty\n")
        with self.assertRaisesRegex(SystemExit, "PHREEQCRM runtime has tracked"):
            self.identity()

    def test_staged_gitlink_change_fails(self) -> None:
        git(self.root, "add", "ThirdParty/PhreeqcRM")
        with self.assertRaisesRegex(SystemExit, "staged PHREEQCRM gitlink"):
            self.identity()


class DependencyTests(unittest.TestCase):
    def test_all_absolute_dependencies_are_hashed_without_addresses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            library = root / "libexample.so"
            loader = root / "loader.so"
            library.write_text("library\n")
            loader.write_text("loader\n")
            first = PROVENANCE.parse_ldd(
                f"linux-vdso.so.1 (0x001)\n"
                f"libexample.so => {library} (0x002)\n{loader} (0x003)\n"
            )
            second = PROVENANCE.parse_ldd(
                f"linux-vdso.so.1 (0x999)\n"
                f"libexample.so => {library} (0x888)\n{loader} (0x777)\n"
            )
            self.assertEqual(first, second)
            resolved = [entry for entry in first if "path" in entry]
            self.assertEqual(len(resolved), 2)
            self.assertTrue(all(entry.get("sha256") for entry in resolved))

    def test_unresolved_or_missing_dependency_fails(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Unresolved solver dependency"):
            PROVENANCE.parse_ldd("libmissing.so => not found\n")
        with self.assertRaisesRegex(SystemExit, "Missing provenance input"):
            PROVENANCE.parse_ldd("libmissing.so => /does/not/exist.so (0x1)\n")
        with self.assertRaisesRegex(SystemExit, "Unparsed ldd dependency"):
            PROVENANCE.parse_ldd("unexpected dependency output\n")


class DictionarySnapshotTests(unittest.TestCase):
    def test_missing_required_dictionary_binding_fails(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Missing required realised dictionaries"):
            PROVENANCE.require_realized_dictionaries([Path("system/controlDict")])

    def test_snapshots_are_complete_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            case = root / "case"
            (case / "system").mkdir(parents=True)
            dictionary = case / "system" / "controlDict"
            dictionary.write_text("endTime 1;\n")
            snapshot = case / "provenance" / "stage"
            old_cwd = Path.cwd()
            try:
                os.chdir(case)
                records = PROVENANCE.snapshot_dictionaries(snapshot, [Path("system/controlDict")])
                self.assertEqual(records[0]["snapshot"]["sha256"], PROVENANCE.sha256(dictionary))
                with self.assertRaisesRegex(SystemExit, "Refusing to overwrite"):
                    PROVENANCE.snapshot_dictionaries(snapshot, [Path("system/controlDict")])
                with self.assertRaisesRegex(SystemExit, "Missing realised dictionary"):
                    PROVENANCE.snapshot_dictionaries(
                        case / "provenance" / "missing", [Path("system/fvSolution")]
                    )
            finally:
                os.chdir(old_cwd)


class StagedRestartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.case = Path(self.temp.name) / "case"
        (self.case / "system").mkdir(parents=True)
        (self.case / "constant").mkdir()
        for name, value in (("NPX", 1), ("NPY", 1), ("NPZ", 1)):
            (self.case / "system" / name).write_text(f"{value}\n")
        dictionaries = {
            "constant/transportProperties": "transport\n",
            "constant/thermoPhysicalProperties": (
                "surfaceMasterDensities { Surf_s 2e-7; Surf_w 6e-6; }\n"
            ),
            "constant/dynamicMeshDict": "dynamic\n",
            "constant/turbulenceProperties": "turbulence\n",
            "system/postProcessDict": "post\n",
            "system/fvSolution": "solution\n",
            "system/fvSchemes": "schemes\n",
        }
        for relative, contents in dictionaries.items():
            (self.case / relative).write_text(contents)
        chemistry = self.case / "constant" / "phreeqcReactions"
        chemistry.write_text("chemistry\n")
        initialization_snapshot = self.case / "initialization.snapshot"
        initialization_snapshot.write_text("initialization\n")
        rank = self.case / "processor0"
        zero = rank / "0"
        mesh = rank / "constant" / "polyMesh"
        zero.mkdir(parents=True)
        mesh.mkdir(parents=True)
        self._write_fields(zero)
        for name in PROVENANCE.REQUIRED_POLYMESH_FILES:
            (mesh / name).write_text(f"{name}\n")
        manifest = {
            "schema_version": PROVENANCE.SCHEMA_VERSION,
            "case_id": "3d_kelvin",
            "runtime": {},
            "runtime_artifacts": {},
            "chemistry": {
                "surface_master_densities_kmol_m2": {"Surf_s": 2e-7, "Surf_w": 6e-6},
                "files": [PROVENANCE.file_record(chemistry)],
            },
            "realized_initialization_dictionaries": [
                {
                    "source": "system/controlDict",
                    "snapshot": PROVENANCE.file_record(initialization_snapshot),
                }
            ],
            "transport_stages": [],
        }
        (self.case / "manifest.json").write_text(json.dumps(manifest) + "\n")
        self._write_control(0.0, 1.0, 0.1, False)
        self.dictionary_paths = list(PROVENANCE.REQUIRED_REALIZED_DICTIONARIES)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write_fields(directory: Path) -> None:
        for name in PROVENANCE.REQUIRED_INITIAL_FIELDS:
            value = "2e-7" if name == "Surf_s" else "6e-6" if name == "Surf_w" else "0"
            (directory / name).write_text(f"internalField uniform {value};\n")

    def _write_control(
        self,
        start: float,
        end: float,
        delta_t: float,
        restore: bool,
        start_from: str = "startTime",
        application: str = "reactiveTransportDBSFoam",
    ) -> None:
        (self.case / "system" / "controlDict").write_text(
            f"application {application};\nstartFrom {start_from};\n"
            f"startTime {start};\nendTime {end};\n"
            f"deltaT {delta_t};\nwriteInterval {end - start};\n"
            "phreeqcRestartCheckpoints true;\n"
            f"phreeqcRestoreCheckpoint {'true' if restore else 'false'};\n"
        )

    def _record_stage(self) -> None:
        args = SimpleNamespace(
            manifest=Path("manifest.json"),
            case=Path("."),
            control=Path("system/controlDict"),
            thermo=Path("constant/thermoPhysicalProperties"),
            snapshot_root=Path("provenance/stages"),
            dictionary=self.dictionary_paths,
        )
        old_cwd = Path.cwd()
        try:
            os.chdir(self.case)
            with mock.patch.object(PROVENANCE, "validate_recorded_runtime"):
                PROVENANCE.run_config(args)
        finally:
            os.chdir(old_cwd)

    def _make_restart(self) -> None:
        restart = self.case / "processor0" / "1"
        restart.mkdir()
        self._write_fields(restart)
        dump = restart / "phreeqc.dmp"
        dump.write_bytes(b"checkpoint-state")
        digest = hashlib.sha256(dump.read_bytes()).hexdigest()
        (restart / "phreeqc.complete").write_text(
            "GeoChemFoam-PHREEQCRM-checkpoint 1\n"
            f"time 1\ndumpSize {dump.stat().st_size}\ndumpSHA256 {digest}\n"
        )
        self._write_control(1.0, 2.0, 0.1, True)

    def test_restart_binds_selected_fields_and_checkpoint(self) -> None:
        self._record_stage()
        self._make_restart()
        self._record_stage()
        payload = json.loads((self.case / "manifest.json").read_text())
        first, restart = payload["transport_stages"]
        self.assertEqual(restart["stage_id"], "1_to_2_attempt_001")
        self.assertEqual(
            restart["selected_start_time_directories"],
            [{
                "rank": "processor0",
                "path": str((self.case / "processor0" / "1").resolve()),
                "time_name": "1",
            }],
        )
        self.assertTrue(all("processor0/1/" in item["path"] for item in restart["start_rank_inputs"]))
        self.assertEqual(restart["restart_checkpoints"][0]["rank"], "processor0")
        self.assertEqual(
            restart["restart_checkpoints"][0]["dump"]["sha256"],
            hashlib.sha256(b"checkpoint-state").hexdigest(),
        )
        self.assertEqual(first["initial_case_identity_sha256"], restart["initial_case_identity_sha256"])

    def test_start_from_checkpoint_and_chain_mutations_fail_closed(self) -> None:
        self._record_stage()
        self._make_restart()
        self._write_control(1.0, 2.0, 0.1, True, "latestTime")
        with self.assertRaisesRegex(SystemExit, "startFrom startTime"):
            self._record_stage()

        self._write_control(1.0, 2.0, 0.2, True)
        with self.assertRaisesRegex(SystemExit, "deltaT changed"):
            self._record_stage()

        self._write_control(1.0, 2.0, 0.1, True)
        self._write_control(1.0, 2.0, 0.1, True, application="wrongSolver")
        with self.assertRaisesRegex(SystemExit, "immutable control settings changed"):
            self._record_stage()

        self._write_control(1.0, 2.0, 0.1, True)
        chemistry = self.case / "constant" / "phreeqcReactions"
        chemistry.write_text("changed\n")
        with self.assertRaisesRegex(SystemExit, "Immutable case input changed"):
            self._record_stage()
        chemistry.write_text("chemistry\n")

        schemes = self.case / "system" / "fvSchemes"
        schemes.write_text("changed\n")
        with self.assertRaisesRegex(SystemExit, "immutable dictionaries changed"):
            self._record_stage()

    def test_bad_or_missing_restart_checkpoint_fails_closed(self) -> None:
        self._record_stage()
        self._make_restart()
        marker = self.case / "processor0" / "1" / "phreeqc.complete"
        marker.write_text(marker.read_text().replace("time 1", "time 9"))
        with self.assertRaisesRegex(SystemExit, "checkpoint time mismatch"):
            self._record_stage()
        marker.unlink()
        with self.assertRaisesRegex(SystemExit, "Incomplete PHREEQCRM checkpoint pair"):
            self._record_stage()


if __name__ == "__main__":
    unittest.main()
