"""Validate release synchronization against local Git repositories only."""

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sync_demo.sh"


class SyncDemoTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.remote = root / "remote.git"
        self.checkout = root / "checkout"
        subprocess.run(
            ["git", "init", "--bare", str(self.remote)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "clone", str(self.remote), str(self.checkout)],
            check=True,
            capture_output=True,
        )
        self.git("config", "user.name", "Release test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("checkout", "-b", "main")
        self.initial = self.commit("Initial")
        self.git("push", "origin", "main")
        self.git("push", "origin", "HEAD:demo")

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.checkout, stderr=subprocess.DEVNULL, text=True
        ).strip()

    def commit(self, message):
        self.git("commit", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def sync(self, sha):
        return subprocess.run(
            ["bash", str(SCRIPT), sha],
            cwd=self.checkout,
            capture_output=True,
            text=True,
        )

    def demo(self):
        return self.git("ls-remote", "origin", "refs/heads/demo").split()[0]

    def test_demo_receives_exact_main_commit_and_retry_is_safe(self):
        release = self.commit("Feature")
        self.git("push", "origin", "main")
        self.assertEqual(0, self.sync(release).returncode)
        self.assertEqual(release, self.demo())
        self.assertEqual(0, self.sync(release).returncode)
        self.assertEqual(release, self.demo())

    def test_old_run_does_not_overwrite_newer_release(self):
        old = self.commit("Old")
        release = self.commit("Latest")
        self.git("push", "origin", "main")
        self.assertEqual(0, self.sync(release).returncode)
        self.assertEqual(0, self.sync(old).returncode)
        self.assertEqual(release, self.demo())

    def test_exclusive_demo_commits_are_preserved_until_integration(self):
        self.git("checkout", "-b", "demo")
        exclusive = self.commit("Demo only")
        self.git("push", "origin", "demo")
        self.git("checkout", "main")
        release = self.commit("Feature")
        self.git("push", "origin", "main")
        self.assertNotEqual(0, self.sync(release).returncode)
        self.assertEqual(exclusive, self.demo())
        self.git("merge", "--no-edit", "demo")
        integrated = self.git("rev-parse", "HEAD")
        self.git("push", "origin", "main")
        self.assertEqual(0, self.sync(integrated).returncode)
        self.assertEqual(integrated, self.demo())


if __name__ == "__main__":
    unittest.main()
