import unittest

from odoo_task.selection import parse_selection


class ParseSelection(unittest.TestCase):
    def test_numbers_ranges_and_separators(self):
        self.assertEqual(parse_selection("2", 5), [2])
        self.assertEqual(parse_selection("1,3", 5), [1, 3])
        self.assertEqual(parse_selection("2-4", 5), [2, 3, 4])
        self.assertEqual(parse_selection("1 3-4, 5", 5), [1, 3, 4, 5])

    def test_order_is_kept_and_repeats_are_dropped(self):
        self.assertEqual(parse_selection("3,1,3,1-2", 5), [3, 1, 2])

    def test_out_of_range(self):
        for text in ("0", "6", "1-9"):
            with self.assertRaises(ValueError, msg=text):
                parse_selection(text, 5)

    def test_not_understood(self):
        for text in ("", "  ", "a", "1-", "-3", "1,x", "3-1", "1.5", "../1"):
            with self.assertRaises(ValueError, msg=text):
                parse_selection(text, 5)


if __name__ == "__main__":
    unittest.main()
