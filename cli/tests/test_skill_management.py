"""Skill installation management regression tests."""

import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from seek_cli.commands import skill


class SkillManagementTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.old_dirs = skill._SKILL_DIRS
        self.old_root = skill._SEEK_ROOT
        self.old_file = skill._SKILL_FILE
        self.old_version = skill.__version__
        skill._SEEK_ROOT = self.root / "source"
        skill._SEEK_ROOT.mkdir()
        skill._SKILL_FILE = skill._SEEK_ROOT / "SKILL.md"
        skill._SKILL_FILE.write_text(
            "---\nskill_doc_version: 1.2.3\ncli_version_ref: 0.3.5\n---\n",
            encoding="utf-8",
        )
        skill._SKILL_DIRS = [self.root / "qoder", self.root / "qoderwork"]

    def tearDown(self):
        skill._SKILL_DIRS = self.old_dirs
        skill._SEEK_ROOT = self.old_root
        skill._SKILL_FILE = self.old_file
        skill.__version__ = self.old_version
        self.temp_dir.cleanup()

    def _args(self, directory=None):
        return SimpleNamespace(dir=str(directory) if directory else None)

    def test_install_and_uninstall_manage_all_default_locations(self):
        installed = skill.cmd_skill_install(self._args())
        self.assertEqual(2, installed["data"]["installed"])
        for directory in skill._SKILL_DIRS:
            self.assertTrue((directory / "seek").is_symlink())

        removed = skill.cmd_skill_uninstall(self._args())
        self.assertEqual(2, removed["data"]["removed"])
        for directory in skill._SKILL_DIRS:
            self.assertFalse((directory / "seek").exists())

    def test_relative_link_to_source_is_current(self):
        directory = skill._SKILL_DIRS[0]
        directory.mkdir()
        link = directory / "seek"
        os.symlink(os.path.relpath(skill._SEEK_ROOT, directory), link)

        result = skill.cmd_skill_status(self._args(directory))
        self.assertTrue(result["data"]["installed"])
        self.assertEqual("up_to_date", result["data"]["locations"][0]["status"])

    def test_update_backs_up_legacy_directory_before_migration(self):
        directory = skill._SKILL_DIRS[0]
        legacy = directory / "seek"
        legacy.mkdir(parents=True)
        (legacy / "SKILL.md").write_text("legacy", encoding="utf-8")
        (legacy / "notes.txt").write_text("preserve", encoding="utf-8")

        result = skill.cmd_skill_update(self._args(directory))
        entry = result["data"]["results"][0]
        self.assertEqual("migrated", entry["status"])
        self.assertTrue((directory / "seek").is_symlink())
        backup = Path(entry["backup"])
        self.assertTrue(backup.is_file())
        with tarfile.open(backup, "r:gz") as archive:
            self.assertIn("seek/notes.txt", archive.getnames())

    def test_status_identifies_foreign_and_broken_links(self):
        directory = skill._SKILL_DIRS[0]
        directory.mkdir()
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "SKILL.md").write_text("foreign", encoding="utf-8")
        os.symlink(str(foreign), directory / "seek")
        self.assertEqual("foreign", skill.cmd_skill_status(self._args(directory))["data"]["locations"][0]["status"])

        (directory / "seek").unlink()
        os.symlink("missing", directory / "seek")
        self.assertEqual("broken", skill.cmd_skill_status(self._args(directory))["data"]["locations"][0]["status"])

    def _set_source_frontmatter(self, skill_doc_version, cli_version_ref):
        lines = ["---", f"skill_doc_version: {skill_doc_version}"]
        if cli_version_ref is not None:
            lines.append(f"cli_version_ref: {cli_version_ref}")
        lines.append("---")
        skill._SKILL_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_update_detects_cli_version_ref_mismatch(self):
        directory = skill._SKILL_DIRS[0]
        directory.mkdir()
        os.symlink(str(skill._SEEK_ROOT), str(directory / "seek"))
        self._set_source_frontmatter("1.2.3", "9.9.9")
        skill.__version__ = "0.4.0"

        result = skill.cmd_skill_update(self._args())
        self.assertEqual("ok", result["status"])
        consistency = result["data"]["version_consistency"]
        self.assertIs(False, consistency["consistent"])
        self.assertEqual("9.9.9", consistency["declared_cli_version"])
        self.assertEqual("0.4.0", consistency["actual_cli_version"])
        self.assertIn("版本声明不匹配", result["message"])
        self.assertIn("≠ 实际", result["data"]["results"][0]["note"])

    def test_update_silent_when_versions_consistent(self):
        directory = skill._SKILL_DIRS[0]
        directory.mkdir()
        os.symlink(str(skill._SEEK_ROOT), str(directory / "seek"))
        self._set_source_frontmatter("1.2.3", "0.4.0")
        skill.__version__ = "0.4.0"

        result = skill.cmd_skill_update(self._args())
        self.assertIs(True, result["data"]["version_consistency"]["consistent"])
        self.assertNotIn("版本声明不匹配", result["message"])

    def test_update_treats_missing_cli_version_ref_as_unknown(self):
        directory = skill._SKILL_DIRS[0]
        directory.mkdir()
        os.symlink(str(skill._SEEK_ROOT), str(directory / "seek"))
        self._set_source_frontmatter("1.2.3", None)

        result = skill.cmd_skill_update(self._args())
        consistency = result["data"]["version_consistency"]
        self.assertIsNone(consistency["declared_cli_version"])
        self.assertIsNone(consistency["consistent"])
        self.assertNotIn("版本声明不匹配", result["message"])

    def test_update_isolates_per_directory_failures(self):
        first = skill._SKILL_DIRS[0]
        first.mkdir(parents=True)
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "SKILL.md").write_text("foreign", encoding="utf-8")
        os.symlink(str(foreign), str(first / "seek"))
        blocked = self.root / "blocked"
        blocked.mkdir()
        os.chmod(blocked, 0o500)
        try:
            skill._SKILL_DIRS = [first, blocked / "skills"]
            result = skill.cmd_skill_update(self._args())
        finally:
            os.chmod(blocked, 0o700)
        self.assertEqual("ok", result["status"])
        entries = result["data"]["results"]
        self.assertEqual(2, len(entries))
        self.assertEqual("fixed", entries[0]["status"])
        self.assertEqual(str(skill._SEEK_ROOT), os.readlink(first / "seek"))
        self.assertEqual("error", entries[1]["status"])
        self.assertFalse(entries[1]["valid"])
        self.assertIn("error", entries[1])
        self.assertEqual(1, result["data"]["updated"])

    def test_update_labels_migration_failed_with_backup_path(self):
        directory = skill._SKILL_DIRS[0]
        legacy = directory / "seek"
        legacy.mkdir(parents=True)
        (legacy / "SKILL.md").write_text("legacy", encoding="utf-8")
        os.chmod(legacy, 0o500)  # 内容可读（备份可写）但不可删除
        try:
            result = skill.cmd_skill_update(self._args(directory))
        finally:
            os.chmod(legacy, 0o700)
        entry = result["data"]["results"][0]
        self.assertEqual("migration_failed", entry["status"])
        self.assertFalse(entry["valid"])
        self.assertTrue(Path(entry["backup"]).is_file())
        self.assertEqual(0, result["data"]["updated"])

    def test_status_accepts_dir_argument(self):
        directory = self.root / "custom"
        directory.mkdir()
        result = skill.cmd_skill_status(self._args(directory))
        self.assertEqual(1, len(result["data"]["locations"]))
        self.assertEqual(str(directory), result["data"]["locations"][0]["dir"])

    def test_source_info_reports_dirty_working_tree(self):
        source = self.root / "gitsource"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nskill_doc_version: 2.0.0\n---\n", encoding="utf-8")
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)

        def git(*git_args):
            subprocess.run(("git",) + git_args, cwd=str(source), check=True,
                           capture_output=True, env=env)

        try:
            git("init", "-q")
            git("add", "-A")
            git("-c", "user.email=t@example.com", "-c", "user.name=test",
                "commit", "-qm", "init")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.skipTest(f"git unavailable: {exc}")
        skill._SEEK_ROOT = source
        skill._SKILL_FILE = source / "SKILL.md"
        self.assertIs(False, skill._get_source_info()["source_dirty"])
        (source / "NEW.md").write_text("untracked\n", encoding="utf-8")
        self.assertIs(True, skill._get_source_info()["source_dirty"])


if __name__ == "__main__":
    unittest.main()
