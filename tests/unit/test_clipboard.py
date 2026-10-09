import unittest
from unittest import mock

from odoo_task import clipboard


def which_only(*names):
    return lambda name: f"/usr/bin/{name}" if name in names else None


class Candidates(unittest.TestCase):
    def test_wsl_uses_clip_exe_with_a_byte_order_mark(self):
        with (
            mock.patch("shutil.which", side_effect=which_only("clip.exe", "xclip")),
            mock.patch.dict("os.environ", {"WSL_DISTRO_NAME": "Ubuntu"}),
        ):
            first = clipboard.candidates()[0]
        self.assertEqual(first, (["clip.exe"], "utf-16"))
        self.assertTrue("é".encode("utf-16").startswith((b"\xff\xfe", b"\xfe\xff")))

    def test_wayland_then_x11(self):
        with (
            mock.patch("shutil.which", side_effect=which_only("wl-copy", "xclip", "xsel")),
            mock.patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=True),
        ):
            names = [c[0][0] for c in clipboard.candidates()]
        self.assertEqual(names, ["wl-copy", "xclip", "xsel"])

    def test_nothing_available(self):
        with mock.patch("shutil.which", return_value=None), mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(clipboard.candidates(), [])
            self.assertFalse(clipboard.copy("text"))


class Copy(unittest.TestCase):
    def test_the_text_goes_through_stdin_not_the_command_line(self):
        run = mock.Mock()
        with mock.patch.object(clipboard, "candidates", return_value=[(["xclip", "-selection", "clipboard"], "utf-8")]):
            with mock.patch("subprocess.run", run):
                self.assertTrue(clipboard.copy("secret é text"))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["xclip", "-selection", "clipboard"])
        self.assertEqual(kwargs["input"], "secret é text".encode())
        self.assertNotIn("secret", " ".join(args[0]))

    def test_the_next_program_is_tried_when_one_fails(self):
        calls = []

        def run(command, **_kw):
            calls.append(command[0])
            if command[0] == "first":
                raise OSError("no")

        with mock.patch.object(clipboard, "candidates", return_value=[(["first"], "utf-8"), (["second"], "utf-8")]):
            with mock.patch("subprocess.run", side_effect=run):
                self.assertTrue(clipboard.copy("x"))
        self.assertEqual(calls, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
