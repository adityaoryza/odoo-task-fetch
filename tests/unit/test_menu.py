import contextlib
import io
import os
import unittest
from unittest import mock

from odoo_task import menu

ITEMS = [("a", "First"), ("b", "Second"), ("c", "Third")]


class NumberedMenu(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ODOO_TASK_MENU": "plain"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def choose(self, *answers):
        with (
            mock.patch("builtins.input", side_effect=list(answers)),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            return menu.choose("T", "text", ITEMS), err.getvalue()

    def test_a_number_picks_the_matching_entry(self):
        self.assertEqual(self.choose("3")[0], "c")

    def test_wrong_answers_are_asked_again(self):
        choice, err = self.choose("x", "9", "0", "2")
        self.assertEqual(choice, "b")
        self.assertIn("Please type a number", err)

    def test_q_or_empty_cancels(self):
        self.assertIsNone(self.choose("q")[0])
        self.assertIsNone(self.choose("")[0])

    def test_end_of_input_cancels(self):
        with mock.patch("builtins.input", side_effect=EOFError), contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(menu.choose("T", "", ITEMS))

    def test_whiptail_is_not_used_when_forced_plain(self):
        self.assertFalse(menu._use_whiptail())


if __name__ == "__main__":
    unittest.main()
