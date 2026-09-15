"""Repository-local .seek-tmp workspace contract tests."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


_REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPER_PATH = _REPO_ROOT / "scripts" / "seek_tmp.py"
_SPEC = importlib.util.spec_from_file_location("seek_tmp_helper", _HELPER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
seek_tmp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seek_tmp)


class RepositoryTemporaryWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = (Path(self.temp_dir.name) / ".seek-tmp").resolve()
        self.now = datetime(2026, 9, 10, 9, 30, 45, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_workspace_uses_fixed_layout_and_manifest(self):
        result = seek_tmp.create_workspace(
            "Review CLI Output",
            root=self.root,
            now=self.now,
            short_id_factory=lambda: "a1b2c3d4",
        )

        run_dir = Path(result["run_dir"])
        self.assertEqual(
            self.root / "runs" / "2026-09-10"
            / "093045Z-review-cli-output-a1b2c3d4",
            run_dir,
        )
        self.assertTrue((self.root / "cache").is_dir())
        for stage in seek_tmp.STAGE_DIRS:
            with self.subTest(stage=stage):
                self.assertTrue((run_dir / stage).is_dir())
                self.assertEqual(str(run_dir / stage), result[stage])

        manifest = json.loads(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, manifest["schema_version"])
        self.assertEqual("review-cli-output", manifest["slug"])
        self.assertEqual("2026-09-10T09:30:45Z", manifest["created_at"])
        self.assertEqual("active", manifest["status"])
        self.assertEqual(
            {stage: stage for stage in seek_tmp.STAGE_DIRS},
            manifest["paths"],
        )
        self.assertEqual([], [path for path in self.root.iterdir() if path.is_file()])

    def test_same_second_and_slug_do_not_overwrite_existing_run(self):
        ids = iter(("aaaaaaaa", "aaaaaaaa", "bbbbbbbb"))
        first = seek_tmp.create_workspace(
            "same task", root=self.root, now=self.now,
            short_id_factory=lambda: next(ids),
        )
        marker = Path(first["work"]) / "keep.txt"
        marker.write_text("keep", encoding="utf-8")

        second = seek_tmp.create_workspace(
            "same task", root=self.root, now=self.now,
            short_id_factory=lambda: next(ids),
        )

        self.assertNotEqual(first["run_dir"], second["run_dir"])
        self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_invalid_slug_does_not_create_workspace(self):
        with self.assertRaisesRegex(ValueError, "ASCII letter or digit"):
            seek_tmp.create_workspace("中文", root=self.root, now=self.now)
        self.assertFalse(self.root.exists())

    def test_manifest_failure_removes_partial_run_directory(self):
        with mock.patch.object(
            seek_tmp, "_write_manifest", side_effect=OSError("disk full")
        ):
            with self.assertRaisesRegex(OSError, "disk full"):
                seek_tmp.create_workspace(
                    "failed-run",
                    root=self.root,
                    now=self.now,
                    short_id_factory=lambda: "deadbeef",
                )

        date_dir = self.root / "runs" / "2026-09-10"
        self.assertEqual([], list(date_dir.iterdir()))

    def test_cli_outputs_machine_readable_json(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(_HELPER_PATH),
                "create",
                "--slug",
                "agent review",
                "--root",
                str(self.root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("ok", payload["status"])
        self.assertTrue(Path(payload["data"]["run_dir"]).is_dir())

    def test_cli_rejects_invalid_slug_without_partial_run(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(_HELPER_PATH),
                "create",
                "--slug",
                "中文",
                "--root",
                str(self.root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("", completed.stdout)
        payload = json.loads(completed.stderr)
        self.assertEqual("error", payload["status"])
        self.assertFalse(self.root.exists())


class RepositoryTemporaryWorkspaceDocumentationTest(unittest.TestCase):
    def test_workspace_is_gitignored(self):
        gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/.seek-tmp/", gitignore.splitlines())

        probe = _REPO_ROOT / ".seek-tmp" / "runs" / "probe.txt"
        completed = subprocess.run(
            ["git", "check-ignore", "-q", str(probe)],
            cwd=_REPO_ROOT,
            check=False,
        )
        self.assertEqual(0, completed.returncode)

    def test_agent_and_readme_document_workspace_boundaries(self):
        agent = (_REPO_ROOT / "AGENT.md").read_text(encoding="utf-8")
        readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for document, text in (("AGENT.md", agent), ("README.md", readme)):
            with self.subTest(document=document):
                self.assertIn("scripts/seek_tmp.py create --slug", text)
                self.assertIn(".seek-tmp/runs/", text)
                self.assertIn("SEEK_HOME", text)
                self.assertIn("manifest.json", text)


if __name__ == "__main__":
    unittest.main()
