"""Release, install and update, entirely on this machine: releases are read from a folder (file://), HOME is a temporary
directory, nothing is downloaded."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sh(cmd, env, **kw):
    return subprocess.run(cmd, env=env, capture_output=True, text=True, check=False, **kw)  # noqa: S603


class ReleaseCycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="odoo-task-release-"))
        cls.home = cls.tmp / "home"
        cls.home.mkdir()
        (cls.home / ".bashrc").write_text("")
        cls.base = cls.tmp / "base"
        cls.env = {
            "HOME": str(cls.home),
            "SHELL": "/bin/bash",
            "PATH": "/usr/bin:/bin",
            "ODOO_TASK_RELEASE_BASE": f"file://{cls.base}",
            "ODOO_TASK_PREFIX": str(cls.tmp / "share"),
        }
        cls.cmd = cls.home / ".local" / "bin" / "odoo-task"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def version_of(tree):
        text = (tree / "src" / "odoo_task" / "__init__.py").read_text()
        return re.search(r'__version__ = "([^"]+)"', text).group(1)

    def publish(self, tree, version):
        dist = self.tmp / f"dist-{version}"
        result = sh([str(tree / "scripts" / "release.sh"), str(dist)], self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.base / f"v{version}"
        shutil.copytree(dist, target)
        (self.base / "latest").write_text(f"v{version}\n")
        return dist

    def test_full_cycle(self):
        current = self.version_of(ROOT)
        dist = self.publish(ROOT, current)
        self.assertTrue((dist / "SHA256SUMS").stat().st_size > 0)

        # The archive carries the tool but not the tests.
        listing = sh(["tar", "-tzf", str(dist / f"odoo-task-fetch-v{current}.tar.gz")], self.env).stdout
        self.assertIn("/RELEASE", listing)
        self.assertIn("/src/odoo_task/cli.py", listing)
        self.assertNotIn("/tests/", listing)

        # One-line install, from a pipe.
        installer = (ROOT / "scripts" / "install.sh").read_text()
        out = subprocess.run(["bash"], input=installer, env=self.env, capture_output=True, text=True, check=False)  # noqa: S603
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("checksum OK", out.stderr)
        self.assertEqual(sh([str(self.cmd), "--version"], self.env).stdout.strip(), f"odoo-task {current}")
        self.assertIn(">>> odoo-task >>>", (self.home / ".bashrc").read_text())

        # Installing again changes nothing.
        again = sh(["bash", str(ROOT / "scripts" / "install.sh"), "remote"], self.env)
        self.assertIn("already up to date", again.stderr)

        # A newer release appears.
        newer = self.tmp / "newer"
        shutil.copytree(ROOT, newer, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__"))
        init = newer / "src" / "odoo_task" / "__init__.py"
        init.write_text(re.sub(r'__version__ = "[^"]+"', '__version__ = "9.9.9"', init.read_text()))
        self.publish(newer, "9.9.9")

        check = sh([str(self.cmd), "update", "--check"], self.env)
        self.assertIn(f"update available: {current} -> 9.9.9", check.stderr)
        self.assertEqual(sh([str(self.cmd), "--version"], self.env).stdout.strip(), f"odoo-task {current}")
        done = sh([str(self.cmd), "update"], self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sh([str(self.cmd), "--version"], self.env).stdout.strip(), "odoo-task 9.9.9")
        self.assertTrue((self.tmp / "share" / f"v{current}").is_dir())  # the previous release is kept

        # A tampered archive is refused and the installation is left alone.
        bad = self.tmp / "bad" / "v9.9.10"
        shutil.copytree(self.base / "v9.9.9", bad)
        (bad / "odoo-task-fetch-v9.9.9.tar.gz").rename(bad / "odoo-task-fetch-v9.9.10.tar.gz")
        sums = (bad / "SHA256SUMS").read_text().replace("v9.9.9", "v9.9.10")
        (bad / "SHA256SUMS").write_text(sums)
        with open(bad / "odoo-task-fetch-v9.9.10.tar.gz", "ab") as fh:
            fh.write(b"tampered")
        (self.tmp / "bad" / "latest").write_text("v9.9.10\n")
        env = dict(self.env, ODOO_TASK_RELEASE_BASE=f"file://{self.tmp / 'bad'}")
        refused = sh([str(self.cmd), "update"], env)
        self.assertIn("CHECKSUM MISMATCH", refused.stderr)
        self.assertEqual(sh([str(self.cmd), "--version"], self.env).stdout.strip(), "odoo-task 9.9.9")

        # Uninstall removes the command and the PATH lines.
        gone = sh(["bash", str(ROOT / "scripts" / "install.sh"), "uninstall"], self.env)
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse(self.cmd.exists() or self.cmd.is_symlink())
        self.assertNotIn("odoo-task", (self.home / ".bashrc").read_text())

    def test_the_command_runs_from_a_checkout(self):
        result = sh([str(ROOT / "bin" / "odoo-task"), "--version"], dict(os.environ))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("odoo-task "))


if __name__ == "__main__":
    unittest.main()
