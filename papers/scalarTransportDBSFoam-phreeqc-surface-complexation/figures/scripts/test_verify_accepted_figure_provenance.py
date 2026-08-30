#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import io
import importlib.util
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "accepted_figure_verifier", HERE / "verify_accepted_figure_provenance.py"
)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AcceptedFigureProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.contents = {
            "data.json": b"{}\n",
            "figure.png": b"PNG!",
            "provenance.json": b'{"schema_version":1}\n',
            "renderer.py": b"print('render')\n",
        }
        for name, data in self.contents.items():
            (self.repo / name).write_bytes(data)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        bindings = []
        for binding_id, path, role, media_type in (
            ("data", "data.json", "material_data", "application/json"),
            ("figure", "figure.png", "figure", "image/png"),
            ("provenance", "provenance.json", "provenance_record", "application/json"),
            ("renderer", "renderer.py", "renderer_source", "text/x-python"),
        ):
            data = self.contents[path]
            bindings.append(
                {
                    "id": binding_id,
                    "media_type": media_type,
                    "path": path,
                    "role": role,
                    "sha256": digest(data),
                    "size_bytes": len(data),
                }
            )
        self.payload = {
            "bindings": bindings,
            "figures": [
                {
                    "artifact_binding_id": "figure",
                    "case": {
                        "id": "case-one",
                        "label": "Case one",
                        "provenance_semantics": "A bounded synthetic test record.",
                    },
                    "claim_role": "Tests a real numerical-to-reference comparison.",
                    "comparison": {
                        "method_roles": [
                            {"id": "numerical", "label": "Numerical", "role": "primary method"},
                            {"id": "reference", "label": "Reference", "role": "reference method"},
                        ],
                        "quantity_roles": ["concentration"],
                        "reference_basis": "Matched coordinates and time.",
                    },
                    "figure_id": "figure-01",
                    "manuscript_number": 1,
                    "material_binding_ids": ["data"],
                    "provenance": [
                        {
                            "binding_id": "provenance",
                            "record_kind": "bounded-run-record",
                            "semantics": "Interpreted only within its own schema.",
                        }
                    ],
                    "renderer": {
                        "command": "python renderer.py",
                        "environment": {
                            "availability": "not_recorded",
                            "description": "No renderer package record survives.",
                            "reference_binding_ids": [],
                        },
                        "source_binding_ids": ["renderer"],
                    },
                }
            ],
            "schema": verifier.SCHEMA,
            "schema_version": verifier.SCHEMA_VERSION,
            "scope": {
                "description": "Synthetic accepted artifacts.",
                "expected_figure_ids": ["figure-01"],
                "id": "synthetic-accepted",
            },
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def schema(self, payload: object | None = None):
        return verifier.verify_schema(self.payload if payload is None else payload)

    def commit_fixture(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=Worktree Test",
                "-c",
                "user.email=worktree@example.invalid",
                "commit",
                "-q",
                "-m",
                "worktree fixture",
            ],
            check=True,
        )

    def create_linked_worktree(self) -> Path:
        self.commit_fixture()
        linked = Path(self.temporary.name) / "linked-worktree"
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "-q", "--detach", str(linked), "HEAD"],
            check=True,
        )
        return linked

    def test_valid_manifest_and_bindings_pass(self) -> None:
        bindings = self.schema()
        self.assertTrue(verifier.verify_bound_files(self.repo, bindings))

    def test_legitimate_linked_worktree_enforces_tracking(self) -> None:
        linked = self.create_linked_worktree()
        self.assertTrue(verifier.verify_bound_files(linked, self.schema()))

    def test_copied_linked_worktree_pointer_cannot_claim_tracking(self) -> None:
        linked = self.create_linked_worktree()
        fake = Path(self.temporary.name) / "copied-pointer-root"
        fake.mkdir()
        for name, data in self.contents.items():
            (fake / name).write_bytes(data)
        shutil.copyfile(linked / ".git", fake / ".git")
        reported_top = subprocess.run(
            ["git", "-C", str(fake), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(Path(reported_top).resolve(), fake.resolve())
        with self.assertRaisesRegex(verifier.VerificationError, "backlink does not authenticate this root"):
            verifier.verify_bound_files(fake, self.schema())

    def test_bool_is_not_accepted_as_integer_version(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["schema_version"] = True
        with self.assertRaisesRegex(verifier.VerificationError, "must be int, got bool"):
            self.schema(payload)

    def test_unknown_key_is_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["figures"][0]["note"] = "not in schema"
        with self.assertRaisesRegex(verifier.VerificationError, "keys differ"):
            self.schema(payload)

    def test_path_escape_and_absolute_path_are_rejected(self) -> None:
        for bad_path in ("../figure.png", "/tmp/figure.png", "nested//figure.png"):
            with self.subTest(path=bad_path):
                payload = copy.deepcopy(self.payload)
                payload["bindings"][1]["path"] = bad_path
                with self.assertRaises(verifier.VerificationError):
                    self.schema(payload)

    def test_duplicate_binding_id_and_path_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["bindings"][1]["id"] = "data"
        with self.assertRaisesRegex(verifier.VerificationError, "Duplicate binding id"):
            self.schema(payload)
        payload = copy.deepcopy(self.payload)
        payload["bindings"][1]["path"] = "data.json"
        with self.assertRaisesRegex(verifier.VerificationError, "Duplicate binding path"):
            self.schema(payload)

    def test_missing_and_unexpected_binding_references_are_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["figures"][0]["material_binding_ids"] = ["missing"]
        with self.assertRaisesRegex(verifier.VerificationError, "Missing binding referenced"):
            self.schema(payload)
        payload = copy.deepcopy(self.payload)
        payload["figures"][0]["material_binding_ids"] = []
        with self.assertRaisesRegex(verifier.VerificationError, "must not be empty"):
            self.schema(payload)

    def test_hash_tampering_is_rejected(self) -> None:
        (self.repo / "figure.png").write_bytes(b"EVIL")
        with self.assertRaisesRegex(verifier.VerificationError, "SHA-256 mismatch"):
            verifier.verify_bound_files(self.repo, self.schema())

    def test_size_tampering_is_rejected(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["bindings"][1]["size_bytes"] += 1
        with self.assertRaisesRegex(verifier.VerificationError, "Size mismatch"):
            verifier.verify_bound_files(self.repo, self.schema(payload))

    def test_untracked_binding_is_rejected(self) -> None:
        data = b"untracked\n"
        (self.repo / "untracked.json").write_bytes(data)
        payload = copy.deepcopy(self.payload)
        payload["bindings"][0].update(
            path="untracked.json", sha256=digest(data), size_bytes=len(data)
        )
        with self.assertRaisesRegex(verifier.VerificationError, "not Git-tracked"):
            verifier.verify_bound_files(self.repo, self.schema(payload))

    def test_real_archive_nested_in_unrelated_checkout_uses_archive_mode(self) -> None:
        installed_verifier = self.repo / verifier.SCRIPT_RELATIVE_PATH
        installed_verifier.parent.mkdir(parents=True)
        shutil.copyfile(HERE / "verify_accepted_figure_provenance.py", installed_verifier)
        installed_manifest = self.repo / verifier.DEFAULT_MANIFEST_RELATIVE_PATH
        installed_manifest.parent.mkdir(parents=True, exist_ok=True)
        installed_manifest.write_text(verifier.canonical_json(self.payload), encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=Archive Test",
                "-c",
                "user.email=archive@example.invalid",
                "commit",
                "-q",
                "-m",
                "archive fixture",
            ],
            check=True,
        )
        archive_bytes = subprocess.run(
            ["git", "-C", str(self.repo), "archive", "--format=tar", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout

        unrelated = Path(self.temporary.name) / "unrelated-parent"
        unrelated.mkdir()
        subprocess.run(["git", "init", "-q", str(unrelated)], check=True)
        extracted = unrelated / "release"
        extracted.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
            archive.extractall(extracted, filter="data")
        self.assertFalse((extracted / ".git").exists())
        discovered_ancestor = subprocess.run(
            ["git", "-C", str(extracted), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(Path(discovered_ancestor).resolve(), unrelated.resolve())

        result = subprocess.run(
            ["python3", str(extracted / verifier.SCRIPT_RELATIVE_PATH)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("archive mode", result.stdout)
        self.assertEqual(
            verifier.default_repo_root(extracted / verifier.SCRIPT_RELATIVE_PATH),
            extracted.resolve(),
        )

    def test_broken_checkout_metadata_does_not_fall_back_to_archive_mode(self) -> None:
        broken = Path(self.temporary.name) / "broken-checkout"
        broken.mkdir()
        for name, data in self.contents.items():
            (broken / name).write_bytes(data)
        (broken / ".git").write_text("gitdir: /definitely/missing/worktree/metadata\n")
        with self.assertRaisesRegex(verifier.VerificationError, "Cannot resolve linked-worktree gitdir"):
            verifier.verify_bound_files(broken, self.schema())

    def test_malformed_and_relative_worktree_pointers_are_rejected(self) -> None:
        broken = Path(self.temporary.name) / "malformed-checkout"
        broken.mkdir()
        for name, data in self.contents.items():
            (broken / name).write_bytes(data)
        metadata = broken / ".git"
        for pointer, message in (
            ("gitdir: /tmp/example\nextra\n", "Malformed linked-worktree metadata"),
            ("gitdir: relative/admin\n", "gitdir must be absolute"),
        ):
            with self.subTest(pointer=pointer):
                metadata.write_text(pointer)
                with self.assertRaisesRegex(verifier.VerificationError, message):
                    verifier.verify_bound_files(broken, self.schema())

    def test_symlink_binding_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_bytes(b"outside\n")
        os.symlink(outside, self.repo / "linked.json")
        subprocess.run(["git", "-C", str(self.repo), "add", "linked.json"], check=True)
        payload = copy.deepcopy(self.payload)
        payload["bindings"][0].update(
            path="linked.json",
            sha256=digest(outside.read_bytes()),
            size_bytes=outside.stat().st_size,
        )
        with self.assertRaisesRegex(verifier.VerificationError, "Symlink is forbidden"):
            verifier.verify_bound_files(self.repo, self.schema(payload))

    def test_noncanonical_and_duplicate_json_keys_are_rejected(self) -> None:
        manifest = self.repo / "manifest.json"
        manifest.write_text('{"schema_version": 1}\n')
        with self.assertRaisesRegex(verifier.VerificationError, "not canonical JSON"):
            verifier.load_manifest(manifest)
        manifest.write_text('{"schema":1,"schema":1}\n')
        with self.assertRaisesRegex(verifier.VerificationError, "Duplicate JSON object key"):
            verifier.load_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
