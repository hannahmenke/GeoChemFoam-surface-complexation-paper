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

    def test_each_solver_or_dependency_mutation_invalidates_runtime(self) -> None:
        runtime = {
            "root": "/runtime",
            "commit": "commit",
            "tree": "tree",
            "phreeqcrm_gitlink": "gitlink",
            "phreeqcrm": {"commit": "adapter", "tree": "adapter-tree"},
        }
        artifacts = {
            "solvers": {
                name: {
                    "executable": {"path": f"/runtime/bin/{name}", "sha256": f"{name}-hash"},
                    "resolved_dependencies": [
                        {"name": "lib.so", "path": "/lib.so", "sha256": f"{name}-lib"}
                    ],
                }
                for name in ("simpleDBSFoam", "reactiveTransportDBSFoam")
            }
        }
        payload = {"runtime": runtime, "runtime_artifacts": artifacts}
        for name in artifacts["solvers"]:
            for target in ("executable", "dependency"):
                changed = json.loads(json.dumps(artifacts))
                if target == "executable":
                    changed["solvers"][name]["executable"]["sha256"] = "changed"
                else:
                    changed["solvers"][name]["resolved_dependencies"][0]["sha256"] = "changed"
                with self.subTest(solver=name, target=target), mock.patch.object(
                    PROVENANCE, "runtime_git_identity", return_value=runtime
                ), mock.patch.object(PROVENANCE, "runtime_artifacts", return_value=changed), self.assertRaisesRegex(
                    SystemExit, "Runtime binary, library"
                ):
                    PROVENANCE.validate_recorded_runtime(payload)


class DictionarySnapshotTests(unittest.TestCase):
    def test_missing_required_dictionary_binding_fails(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Realised dictionary set differs"):
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


class PreparedRunnerTests(unittest.TestCase):
    def test_prepared_controls_are_preserved_and_nonzero_solver_is_not_finalised(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            case = (
                root / "tutorials" / "reactiveTransport" / "reactiveTransportDBSFoam"
                / "3DKelvinSurfaceComplexation"
            )
            case.mkdir(parents=True)
            shutil.copyfile(MODULE_PATH.with_name("runCaseReactiveTransport.sh"), case / "run.sh")
            (case / "run.sh").chmod(0o755)
            (case / "system").mkdir()
            control = case / "system" / "controlDict"
            solution = case / "system" / "fvSolution"
            control.write_bytes(b"prepared-control\n")
            solution.write_bytes(b"prepared-solution\n")
            before = (control.read_bytes(), solution.read_bytes())

            configure = (
                root / "papers" / "scalarTransportDBSFoam-phreeqc-surface-complexation"
                / "cases" / "configure_runtime.sh"
            )
            configure.parent.mkdir(parents=True)
            configure.write_text('export PATH="$FAKE_BIN:$PATH"\n')
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            calls = root / "python.calls"
            fake_python = fake_bin / "python"
            fake_python.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FAKE_PYTHON_CALLS"\n')
            fake_python.chmod(0o755)
            solver = fake_bin / "reactiveTransportDBSFoam"
            solver.write_text('#!/usr/bin/env bash\nprintf "Time = 1\\n\\nEnd\\n"\n')
            solver.chmod(0o755)
            environment = {
                **os.environ,
                "FAKE_BIN": str(fake_bin),
                "FAKE_PYTHON_CALLS": str(calls),
                "KELVIN_USE_PREPARED_CONTROL": "true",
                "KELVIN_SOLVER_LOG": "solver.out",
            }
            subprocess.run(["bash", "run.sh"], cwd=case, env=environment, check=True)
            self.assertEqual(before, (control.read_bytes(), solution.read_bytes()))
            invoked = calls.read_text().splitlines()
            self.assertIn("record-run", invoked[0])
            self.assertIn("finalise-run", invoked[1])

            calls.write_text("")
            solver.write_text("#!/usr/bin/env bash\nexit 7\n")
            solver.chmod(0o755)
            failed = subprocess.run(["bash", "run.sh"], cwd=case, env=environment, check=False)
            self.assertEqual(failed.returncode, 7)
            invoked = calls.read_text().splitlines()
            self.assertEqual(len(invoked), 1)
            self.assertIn("record-run", invoked[0])


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
        rank = self.case / "processor0"
        zero = rank / "0"
        mesh = rank / "constant" / "polyMesh"
        zero.mkdir(parents=True)
        mesh.mkdir(parents=True)
        self._write_fields(zero)
        for name in PROVENANCE.REQUIRED_POLYMESH_FILES:
            (mesh / name).write_text(f"{name}\n")
        self._write_control(
            0.0, 1.0, 1.0, False, application="simpleDBSFoam"
        )
        initialization_records = []
        for relative in PROVENANCE.REQUIRED_REALIZED_DICTIONARIES:
            snapshot = self.case / "initialization" / relative
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.case / relative, snapshot)
            initialization_records.append(
                {"source": str(relative), "snapshot": PROVENANCE.file_record(snapshot)}
            )
        manifest = {
            "schema_version": PROVENANCE.SCHEMA_VERSION,
            "case_id": "3d_kelvin",
            "runtime": {},
            "runtime_artifacts": {},
            "chemistry": {
                "surface_master_densities_kmol_m2": {"Surf_s": 2e-7, "Surf_w": 6e-6},
                "files": [PROVENANCE.file_record(chemistry)],
            },
            "realized_initialization_dictionaries": initialization_records,
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
            f"application {application};\nstartFrom {start_from};\nstopAt endTime;\n"
            f"startTime {start};\nendTime {end};\n"
            f"deltaT {delta_t};\nwriteInterval {end - start};\n"
            "writeControl adjustableRunTime;\npurgeWrite 0;\n"
            "writeFormat ascii;\nwritePrecision 16;\nwriteCompression off;\n"
            "timeFormat general;\ntimePrecision 8;\nrunTimeModifiable yes;\n"
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

    def _make_checkpoint(self, time: float, rank: str = "processor0") -> Path:
        restart = self.case / rank / f"{time:g}"
        restart.mkdir()
        self._write_fields(restart)
        dump = restart / "phreeqc.dmp"
        dump.write_bytes(f"checkpoint-state-{time:g}".encode())
        digest = hashlib.sha256(dump.read_bytes()).hexdigest()
        (restart / "phreeqc.complete").write_text(
            "GeoChemFoam-PHREEQCRM-checkpoint 1\n"
            f"time {time:g}\ndumpSize {dump.stat().st_size}\ndumpSHA256 {digest}\n"
        )
        return restart

    def _finalise_stage(self, endpoint: float, *, clean_log: bool = True) -> None:
        log = self.case / "solver.log"
        log.write_text(
            f"Time = {endpoint:g}\n\n{'End' if clean_log else 'stopped'}\n"
        )
        args = SimpleNamespace(
            manifest=Path("manifest.json"),
            case=Path("."),
            control=Path("system/controlDict"),
            solver_log=Path("solver.log"),
        )
        old_cwd = Path.cwd()
        try:
            os.chdir(self.case)
            with mock.patch.object(PROVENANCE, "validate_recorded_runtime"):
                PROVENANCE.finalise_run(args)
        finally:
            os.chdir(old_cwd)

    def _complete_initial_stage(self) -> None:
        self._record_stage()
        self._make_checkpoint(1.0)
        self._finalise_stage(1.0)

    def test_restart_binds_selected_fields_and_checkpoint(self) -> None:
        self._complete_initial_stage()
        self._write_control(1.0, 2.0, 0.1, True)
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
            hashlib.sha256(b"checkpoint-state-1").hexdigest(),
        )
        self.assertEqual(first["status"], "completed")
        self.assertEqual(restart["status"], "attempted")
        self.assertEqual(first["initial_case_identity_sha256"], restart["initial_case_identity_sha256"])

    def test_start_from_checkpoint_and_chain_mutations_fail_closed(self) -> None:
        self._complete_initial_stage()
        self._write_control(1.0, 2.0, 0.1, True)
        self._write_control(1.0, 2.0, 0.1, True, "latestTime")
        with self.assertRaisesRegex(SystemExit, "startFrom startTime"):
            self._record_stage()

        self._write_control(1.0, 2.0, 0.2, True)
        with self.assertRaisesRegex(SystemExit, "deltaT changed"):
            self._record_stage()

        self._write_control(1.0, 2.0, 0.1, True)
        self._write_control(1.0, 2.0, 0.1, True, application="wrongSolver")
        with self.assertRaisesRegex(SystemExit, "application reactiveTransportDBSFoam"):
            self._record_stage()

        self._write_control(1.0, 2.0, 0.1, True)
        chemistry = self.case / "constant" / "phreeqcReactions"
        chemistry.write_text("changed\n")
        with self.assertRaisesRegex(SystemExit, "Immutable case input changed"):
            self._record_stage()
        chemistry.write_text("chemistry\n")

        schemes = self.case / "system" / "fvSchemes"
        schemes.write_text("changed\n")
        with self.assertRaisesRegex(SystemExit, "drifted from initialization"):
            self._record_stage()

    def test_bad_or_missing_restart_checkpoint_fails_closed(self) -> None:
        self._complete_initial_stage()
        self._write_control(1.0, 2.0, 0.1, True)
        marker = self.case / "processor0" / "1" / "phreeqc.complete"
        marker.write_text(marker.read_text().replace("time 1", "time 9"))
        with self.assertRaisesRegex(SystemExit, "checkpoint time mismatch"):
            self._record_stage()
        marker.unlink()
        with self.assertRaisesRegex(SystemExit, "Incomplete PHREEQCRM checkpoint pair"):
            self._record_stage()

    def test_initialization_drift_and_noncontiguous_ranks_fail_closed(self) -> None:
        solution = self.case / "system" / "fvSolution"
        solution.write_text("changed before first stage\n")
        with self.assertRaisesRegex(SystemExit, "drifted from initialization"):
            self._record_stage()
        solution.write_text("solution\n")

        (self.case / "processor0").rename(self.case / "processor1")
        with self.assertRaisesRegex(SystemExit, "not contiguous"):
            self._record_stage()

    def test_flow_control_snapshot_allows_first_transport_anchor(self) -> None:
        self._record_stage()
        stage = json.loads((self.case / "manifest.json").read_text())["transport_stages"][0]
        self.assertEqual(stage["deltaT"], 0.1)
        self.assertEqual(
            stage["immutable_control_sha256"],
            PROVENANCE.immutable_control_digest(self.case / "system" / "controlDict"),
        )

    def test_write_interval_must_span_stage(self) -> None:
        control = self.case / "system" / "controlDict"
        control.write_text(control.read_text().replace("writeInterval 1.0", "writeInterval 0.5"))
        with self.assertRaisesRegex(SystemExit, "writeInterval must equal"):
            self._record_stage()

    def test_interrupted_attempt_rejects_fabricated_intermediate_state(self) -> None:
        self._complete_initial_stage()
        self._write_control(1.0, 5.0, 0.1, True)
        self._record_stage()
        self._make_checkpoint(3.0)
        (self.case / "processor0" / "3" / "Mn+2").write_text(
            "internalField uniform 99;\n"
        )
        self._write_control(3.0, 5.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "permits only an exact retry"):
            self._record_stage()

    def test_recovery_cannot_change_interrupted_target(self) -> None:
        self._complete_initial_stage()
        self._write_control(1.0, 5.0, 0.1, True)
        self._record_stage()
        self._make_checkpoint(3.0)
        self._write_control(3.0, 10.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "permits only an exact retry"):
            self._record_stage()

    def test_continuation_rejects_substituted_field_or_checkpoint(self) -> None:
        self._complete_initial_stage()
        field = self.case / "processor0" / "1" / "Mn+2"
        original_field = field.read_bytes()
        field.write_text("internalField uniform 9;\n")
        self._write_control(1.0, 2.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "start fields do not match"):
            self._record_stage()
        field.write_bytes(original_field)

        dump = self.case / "processor0" / "1" / "phreeqc.dmp"
        marker = self.case / "processor0" / "1" / "phreeqc.complete"
        dump.write_bytes(b"self-consistent-replacement")
        digest = hashlib.sha256(dump.read_bytes()).hexdigest()
        marker.write_text(
            "GeoChemFoam-PHREEQCRM-checkpoint 1\n"
            f"time 1\ndumpSize {dump.stat().st_size}\ndumpSHA256 {digest}\n"
        )
        with self.assertRaisesRegex(SystemExit, "start checkpoint does not match"):
            self._record_stage()

    def test_attempted_stage_allows_exact_authenticated_retry(self) -> None:
        self._complete_initial_stage()
        self._write_control(1.0, 2.0, 0.1, True)
        self._record_stage()
        field = self.case / "processor0" / "1" / "Mn+2"
        original = field.read_bytes()
        field.write_text("internalField uniform 88;\n")
        with self.assertRaisesRegex(SystemExit, "start fields do not match"):
            self._record_stage()
        field.write_bytes(original)
        self._record_stage()
        stages = json.loads((self.case / "manifest.json").read_text())["transport_stages"]
        self.assertEqual(stages[-1]["chain_relation"], "retry")
        self.assertEqual(stages[-1]["start_rank_inputs"], stages[-2]["start_rank_inputs"])
        self.assertEqual(
            PROVENANCE.checkpoint_chain_identity(stages[-1]["restart_checkpoints"]),
            PROVENANCE.checkpoint_chain_identity(stages[-2]["restart_checkpoints"]),
        )

    def test_uncompleted_endpoint_outside_interval_and_backtrack_fail(self) -> None:
        self._complete_initial_stage()
        self._write_control(1.0, 5.0, 0.1, True)
        self._record_stage()
        self._make_checkpoint(5.0)
        self._write_control(5.0, 6.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "permits only an exact retry"):
            self._record_stage()

        self._make_checkpoint(6.0)
        self._write_control(6.0, 7.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "permits only an exact retry"):
            self._record_stage()

    def test_first_transport_control_contract_fails_closed(self) -> None:
        control = self.case / "system" / "controlDict"
        original = control.read_text()
        mutations = {
            "wrong application": original.replace(
                "application reactiveTransportDBSFoam;", "application wrongSolver;"
            ),
            "wrong purge": original.replace("purgeWrite 0;", "purgeWrite 1;"),
            "wrong write control": original.replace(
                "writeControl adjustableRunTime;", "writeControl timeStep;"
            ),
            "adjust time step": original + "adjustTimeStep true;\n",
            "max Co": original + "maxCo 99;\n",
            "duplicate application": original + "application reactiveTransportDBSFoam;\n",
            "nonfinite timestep": original.replace("deltaT 0.1;", "deltaT 1e999;"),
        }
        for label, text in mutations.items():
            with self.subTest(label=label):
                control.write_text(text)
                with self.assertRaises(SystemExit):
                    self._record_stage()
        control.write_text(original)

    def test_checkpoint_handoff_rejects_fabricated_historical_paths(self) -> None:
        self._complete_initial_stage()
        manifest = self.case / "manifest.json"
        original = json.loads(manifest.read_text())
        payload = json.loads(json.dumps(original))
        checkpoint = payload["transport_stages"][0]["endpoint_checkpoints"][0]
        checkpoint["dump"]["path"] = "/fabricated/dump"
        checkpoint["marker"]["path"] = "/fabricated/marker"
        manifest.write_text(json.dumps(payload) + "\n")
        self._write_control(1.0, 2.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "noncanonical path"):
            self._record_stage()

        payload = json.loads(json.dumps(original))
        payload["transport_stages"][0]["endpoint_checkpoints"].append(
            json.loads(json.dumps(payload["transport_stages"][0]["endpoint_checkpoints"][0]))
        )
        manifest.write_text(json.dumps(payload) + "\n")
        with self.assertRaisesRegex(SystemExit, "duplicate rank or path"):
            self._record_stage()

    def test_symlinked_rank_time_or_checkpoint_fails_closed(self) -> None:
        rank = self.case / "processor0"
        backing = self.case / "rank-backing"
        rank.rename(backing)
        rank.symlink_to(backing, target_is_directory=True)
        with self.assertRaisesRegex(SystemExit, "processor directories must not be symlinks"):
            self._record_stage()
        rank.unlink()
        backing.rename(rank)

        target = self.case / "time-target"
        target.mkdir()
        self._write_fields(target)
        (rank / "2").symlink_to(target, target_is_directory=True)
        self._write_control(2.0, 3.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "time directory must not be a symlink"):
            self._record_stage()
        (rank / "2").unlink()

        self._make_checkpoint(2.0)
        marker = rank / "2" / "phreeqc.complete"
        marker_backing = rank / "2" / "marker-backing"
        marker.rename(marker_backing)
        marker.symlink_to(marker_backing.name)
        with self.assertRaisesRegex(SystemExit, "checkpoint artifact must not be a symlink"):
            self._record_stage()

    def test_completed_stage_rejects_backtrack(self) -> None:
        self._complete_initial_stage()
        self._write_control(0.0, 0.5, 0.1, False)
        with self.assertRaisesRegex(SystemExit, "backtracks or skips"):
            self._record_stage()

    def test_finalisation_binds_clean_endpoint_and_rejects_unclean_log(self) -> None:
        self._record_stage()
        self._make_checkpoint(1.0)
        with self.assertRaisesRegex(SystemExit, "no clean End"):
            self._finalise_stage(1.0, clean_log=False)
        payload = json.loads((self.case / "manifest.json").read_text())
        self.assertEqual(payload["transport_stages"][-1]["status"], "attempted")

        self._finalise_stage(1.0)
        stage = json.loads((self.case / "manifest.json").read_text())["transport_stages"][-1]
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(len(stage["endpoint_checkpoints"]), 1)
        self.assertTrue(stage["endpoint_rank_outputs"])
        self.assertEqual(stage["solver_log"]["sha256"], PROVENANCE.sha256(self.case / "solver.log"))

    def test_multirank_recovery_rejects_missing_rank_checkpoint(self) -> None:
        (self.case / "system" / "NPX").write_text("2\n")
        shutil.copytree(self.case / "processor0", self.case / "processor1")
        self._record_stage()
        self._make_checkpoint(1.0)
        self._make_checkpoint(1.0, "processor1")
        self._finalise_stage(1.0)
        self._write_control(1.0, 5.0, 0.1, True)
        self._record_stage()
        self._make_checkpoint(3.0)
        self._write_control(3.0, 5.0, 0.1, True)
        with self.assertRaisesRegex(SystemExit, "Expected one time directory"):
            self._record_stage()


if __name__ == "__main__":
    unittest.main()
