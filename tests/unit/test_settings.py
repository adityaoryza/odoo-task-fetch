import unittest

from odoo_task import settings
from odoo_task.store import Profile


def profile():
    return Profile(name="w", url="https://o.example.com", db="d", user="u")


class Parsers(unittest.TestCase):
    def test_yes_and_no_in_every_usual_spelling(self):
        for text in ("y", "YES", "True", "1", "on", " yes "):
            self.assertTrue(settings.parse_bool(text), text)
        for text in ("n", "No", "FALSE", "0", "off"):
            self.assertFalse(settings.parse_bool(text), text)

    def test_not_a_bool(self):
        for text in ("", "maybe", "2", "yes please"):
            with self.assertRaises(ValueError, msg=text):
                settings.parse_bool(text)

    def test_messages_are_a_small_whole_number(self):
        self.assertEqual(settings.parse_messages("0"), 0)
        self.assertEqual(settings.parse_messages("50"), 50)
        for text in ("", "-1", "1.5", "x", "51", "9999"):
            with self.assertRaises(ValueError, msg=text):
                settings.parse_messages(text)

    def test_a_folder_must_not_be_empty_or_hold_control_characters(self):
        self.assertEqual(settings.parse_folder(" ~/tasks "), "~/tasks")
        for text in ("", "   ", "a\nb", "a\x00b"):
            with self.assertRaises(ValueError, msg=text):
                settings.parse_folder(text)


class ApplySettings(unittest.TestCase):
    def test_values_are_set_and_reported(self):
        p = profile()
        done = settings.apply_settings(p, ["attachments=yes", "prompt=no", "messages=5", "out=~/k"])
        self.assertEqual(done, ["attachments=yes", "prompt=no", "messages=5", "out=~/k"])
        self.assertEqual((p.attachments, p.prompt, p.messages, p.output_dir), (True, False, 5, "~/k"))

    def test_one_bad_item_changes_nothing(self):
        p = profile()
        with self.assertRaises(ValueError):
            settings.apply_settings(p, ["attachments=yes", "messages=999"])
        self.assertFalse(p.attachments)

    def test_unknown_keys_and_missing_equals(self):
        for item in ("bogus=1", "attachments", "=1"):
            with self.assertRaises(ValueError, msg=item):
                settings.apply_settings(profile(), [item])

    def test_the_error_names_the_key(self):
        with self.assertRaises(ValueError) as ctx:
            settings.apply_settings(profile(), ["messages=abc"])
        self.assertIn("messages", str(ctx.exception))

    def test_the_clipboard_is_never_saved(self):
        with self.assertRaises(ValueError) as ctx:
            settings.apply_settings(profile(), ["copy=yes"])
        self.assertIn("--copy", str(ctx.exception))

    def test_keys_are_not_case_sensitive(self):
        p = profile()
        settings.apply_settings(p, ["Attachments=YES"])
        self.assertTrue(p.attachments)


class ExtraFields(unittest.TestCase):
    def test_add_replace_and_remove(self):
        p = profile()
        self.assertEqual(settings.add_extra_field(p, "x_report:Customer report"), "x_report:Customer report")
        settings.add_extra_field(p, "x_ref")
        settings.add_extra_field(p, "x_report:Wishes")  # the same field again: replaced, not duplicated
        self.assertEqual(p.extra_fields, ["x_ref", "x_report:Wishes"])
        self.assertTrue(settings.remove_extra_field(p, "x_ref"))
        self.assertFalse(settings.remove_extra_field(p, "x_ref"))
        self.assertEqual(p.extra_fields, ["x_report:Wishes"])

    def test_a_bad_field_name_is_refused(self):
        for text in ("a;b", "../x", "x y", ""):
            with self.assertRaises(ValueError, msg=text):
                settings.add_extra_field(profile(), text)


class Describe(unittest.TestCase):
    def test_no_secret_in_the_description(self):
        text = "\n".join(settings.describe(profile()))
        self.assertIn("attachments  no", text)
        self.assertNotIn("key", text.lower().replace("keys", ""))


if __name__ == "__main__":
    unittest.main()
