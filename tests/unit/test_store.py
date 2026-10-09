import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from odoo_task import store


class Store(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"ODOO_TASK_HOME": self._tmp.name}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(store.ENV_SECRET, None)
        self.addCleanup(self._tmp.cleanup)

    def profile(self, name="work"):
        return store.Profile(name=name, url="https://o.example.com", db="d", user="u@example.com")

    def test_profile_round_trip_and_modes(self):
        path = store.save_profile(self.profile())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        loaded = store.load_profile("work")
        self.assertEqual((loaded.url, loaded.db, loaded.user), ("https://o.example.com", "d", "u@example.com"))

    def test_preferences_round_trip(self):
        p = self.profile()
        p.attachments, p.prompt, p.messages = True, True, 7
        p.closed_stages, p.extra_fields = ["Done"], ["x_report:Report"]
        store.save_profile(p)
        loaded = store.load_profile("work")
        self.assertEqual((loaded.attachments, loaded.prompt, loaded.messages), (True, True, 7))
        self.assertEqual((loaded.closed_stages, loaded.extra_fields), (["Done"], ["x_report:Report"]))

    def test_a_profile_saved_by_an_older_version_still_loads(self):
        path = store.save_profile(self.profile())
        path.write_text('{"url": "https://o.example.com", "db": "d", "user": "u@example.com"}\n')
        loaded = store.load_profile("work")
        self.assertEqual(
            (loaded.attachments, loaded.prompt, loaded.messages, loaded.closed_stages), (False, False, 0, [])
        )

    def test_no_secret_is_ever_in_a_profile(self):
        text = store.save_profile(self.profile()).read_text()
        self.assertNotIn("password", text.lower())
        self.assertNotIn("secret", text.lower())

    def test_names_are_validated(self):
        for bad in ("", "../x", "a b", "fetch", "login", "x" * 80):
            self.assertFalse(store.valid_profile_name(bad), bad)
            with self.assertRaises(ValueError):
                store.save_profile(self.profile(bad))

    def test_default_profile(self):
        self.assertIsNone(store.default_profile_name())
        store.save_profile(self.profile("a"))
        self.assertEqual(store.default_profile_name(), "a")  # the only one
        store.save_profile(self.profile("b"))
        self.assertIsNone(store.default_profile_name())  # ambiguous
        store.set_default_profile("b")
        self.assertEqual(store.default_profile_name(), "b")

    def test_missing_profile_lists_the_known_ones(self):
        store.save_profile(self.profile("a"))
        with self.assertRaises(FileNotFoundError) as ctx:
            store.load_profile("nope")
        self.assertIn("a", str(ctx.exception))

    def test_secret_order_env_then_file(self):
        self.assertIsNone(store.read_secret("work"))
        store.save_secret("work", "from-file")
        self.assertEqual(store.read_secret("work"), "from-file")
        with mock.patch.dict(os.environ, {store.ENV_SECRET: "from-env"}):
            self.assertEqual(store.read_secret("work"), "from-env")

    def test_saved_secret_is_private_and_a_loose_one_is_refused(self):
        path = store.save_secret("work", "k")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        path.chmod(0o644)
        with self.assertRaises(PermissionError):
            store.read_secret("work")

    def test_forget_key(self):
        store.save_secret("work", "k")
        self.assertTrue(store.delete_secret("work"))
        self.assertFalse(store.delete_secret("work"))
        self.assertFalse(Path(self._tmp.name, "secrets", "work").exists())


if __name__ == "__main__":
    unittest.main()
