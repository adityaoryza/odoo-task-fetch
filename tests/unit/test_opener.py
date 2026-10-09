import unittest
from pathlib import Path
from unittest import mock

from odoo_task import opener


def which_only(*names):
    return lambda name: f"/usr/bin/{name}" if name in names else None


class Candidates(unittest.TestCase):
    def test_vscode_comes_first(self):
        with mock.patch("shutil.which", side_effect=which_only("code", "xdg-open")):
            self.assertEqual(opener.candidates(Path("/t/task.md"), folder=False)[0], ["code", "/t/task.md"])

    def test_falls_back_to_the_desktop_opener(self):
        with mock.patch("shutil.which", side_effect=which_only("xdg-open")):
            self.assertEqual(opener.candidates(Path("/t"), folder=True), [["xdg-open", "/t"]])

    def test_nothing_available(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(opener.candidates(Path("/t"), folder=True), [])
            self.assertFalse(opener.open_path(Path("/t"), folder=True))

    def test_windows_explorer_from_wsl_for_a_folder(self):
        fake_run = mock.Mock(return_value=mock.Mock(stdout="\\\\wsl$\\Ubuntu\\t\n"))
        with (
            mock.patch("shutil.which", side_effect=which_only("explorer.exe", "wslpath")),
            mock.patch.dict("os.environ", {"WSL_DISTRO_NAME": "Ubuntu"}),
            mock.patch("subprocess.run", fake_run),
        ):
            self.assertEqual(opener.candidates(Path("/t"), folder=True), [["explorer.exe", "\\\\wsl$\\Ubuntu\\t"]])

    def test_the_next_program_is_tried_when_one_fails_to_start(self):
        started = []

        def popen(command, **_kw):
            if command[0] == "code":
                raise OSError("broken")
            started.append(command)

        with (
            mock.patch("shutil.which", side_effect=which_only("code", "xdg-open")),
            mock.patch("subprocess.Popen", side_effect=popen),
        ):
            self.assertTrue(opener.open_path(Path("/t/task.md")))
        self.assertEqual(started, [["xdg-open", "/t/task.md"]])


if __name__ == "__main__":
    unittest.main()
