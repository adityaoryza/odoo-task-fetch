import unittest

from odoo_task.fetch import TaskSummary
from odoo_task.listing import format_tasks

TASKS = [
    TaskSummary(14998, "[CRM] Filter per sales team", "Accounting", "Running", "2026-12-01"),
    TaskSummary(7, "A very long title " * 10, "A project name that is far too long for its column", "To do"),
]


class FormatTasks(unittest.TestCase):
    def test_nothing_to_show(self):
        self.assertEqual(format_tasks([]), [])

    def test_header_and_rows_line_up(self):
        lines = format_tasks(TASKS)
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].lstrip().startswith("ID"))
        self.assertEqual(lines[1].index("Running"), lines[2].index("To do"))  # same column

    def test_long_values_are_cut(self):
        lines = format_tasks(TASKS)
        self.assertLessEqual(len(lines[2]), 14 + 2 + 16 + 2 + 20 + 2 + 10 + 2 + 70 + 5)
        self.assertIn("…", lines[2])

    def test_numbered_for_a_choice(self):
        lines = format_tasks(TASKS, numbered=True)
        self.assertTrue(lines[1].startswith("  1) "))
        self.assertTrue(lines[2].startswith("  2) "))

    def test_a_title_cannot_break_the_table(self):
        weird = [TaskSummary(1, "line one\nline two\t(tab)", "p", "s")]
        self.assertEqual(len(format_tasks(weird)), 2)


if __name__ == "__main__":
    unittest.main()
