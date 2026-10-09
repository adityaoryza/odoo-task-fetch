import unittest

from odoo_task.taskref import parse_task_ref, slugify, task_folder_name


class ParseTaskRef(unittest.TestCase):
    def test_numbers(self):
        for text, expected in (("123", 123), ("#123", 123), ("  45  ", 45)):
            self.assertEqual(parse_task_ref(text), expected)

    def test_urls(self):
        cases = {
            "http://localhost:8069/odoo/projects/12/3/tasks/70524": 70524,
            "https://x.example.com/odoo/project/12/tasks/987": 987,
            "https://x.example.com/web#id=555&model=project.task&view_type=form": 555,
            "https://x.example.com/odoo/action-1412/321": 321,
        }
        for url, expected in cases.items():
            self.assertEqual(parse_task_ref(url), expected, url)

    def test_other_model_in_url_is_not_a_task(self):
        with self.assertRaises(ValueError):
            parse_task_ref("https://x.example.com/web#id=5&model=res.partner")

    def test_garbage(self):
        for text in ("", "abc", "12abc", "ftp://x/y/1", "../../1"):
            with self.assertRaises(ValueError):
                parse_task_ref(text)


class Slug(unittest.TestCase):
    def test_folder_names_are_safe(self):
        name = task_folder_name(42, "Fix ../../etc/passwd & <script>")
        self.assertNotIn("/", name)
        self.assertNotIn("..", name)
        self.assertTrue(name.startswith("42_"))

    def test_never_empty(self):
        self.assertEqual(slugify("///"), "task")
        self.assertEqual(slugify(""), "task")

    def test_length_is_capped(self):
        self.assertLessEqual(len(slugify("a" * 500)), 60)


if __name__ == "__main__":
    unittest.main()
