#!/usr/bin/env python3
"""Adversarial tests for Kelvin runtime and dictionary provenance."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


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
                import os
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


if __name__ == "__main__":
    unittest.main()
