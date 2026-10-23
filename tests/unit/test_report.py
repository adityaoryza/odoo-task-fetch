"""What git-shuttle adds to the Customer report: only added, never removed. A fake Odoo, no network."""

import unittest

from odoo_task import report
from odoo_task.client import OdooClient, OdooError

INFO = {
    "branch": "feature/x",
    "pr": {"url": "https://github.example/acme/shop/pull/9", "title": 'Fix "total" <b>', "base": "19.0-staging"},
    "commits": [
        {
            "sha": "a" * 40,
            "subject": "[FIX] sale: round <it>",
            "url": "https://github.example/acme/shop/commit/" + "a" * 40,
        }
    ],
}


class Fake:
    """The few calls the module makes. `keeps` False simulates an Odoo that rewrites the old text."""

    def __init__(self, value="", kind="html", keeps=True):
        self.value, self.kind, self.keeps, self.writes = value, kind, keeps, []

    def fields_get(self, model, attributes=None):
        return {"x_customer_report": {"type": self.kind, "string": "Customer report"}, "name": {"type": "char"}}

    def read(self, model, ids, fields=None):
        return [{"x_customer_report": self.value}]

    def append_custom_field(self, model, record_id, field, value):
        self.writes.append(value)
        self.value = value if self.keeps or len(self.writes) > 1 else "rewritten by odoo"


class Entry(unittest.TestCase):
    def test_html_is_escaped_and_has_the_links(self):
        text = report.entry_html(INFO)
        self.assertIn('<a href="https://github.example/acme/shop/pull/9">Fix &quot;total&quot; &lt;b&gt;</a>', text)
        self.assertIn("round &lt;it&gt;", text)
        self.assertNotIn("<b>", text.replace("<strong>", "").replace("</strong>", ""))
        self.assertIn("/commit/" + "a" * 40, text)

    def test_text_has_the_same_facts(self):
        text = report.entry_text(INFO)
        self.assertIn("https://github.example/acme/shop/pull/9", text)
        self.assertIn("- aaaaaaaa [FIX] sale: round <it>", text)

    def test_a_long_list_of_commits_is_cut(self):
        many = {**INFO, "commits": [{"sha": f"{i:040x}", "subject": "s"} for i in range(40)]}
        self.assertIn("and 10 more", report.entry_text(many))


class Post(unittest.TestCase):
    def test_the_old_html_is_kept_and_the_entry_comes_after_it(self):
        fake = Fake("<p>The PM wrote this.</p>")
        message = report.post(fake, 15493, "x_customer_report", INFO)
        self.assertTrue(fake.value.startswith("<p>The PM wrote this.</p>"))
        self.assertIn("git-shuttle", fake.value)
        self.assertIn("kept", message)

    def test_the_old_text_is_kept_and_a_blank_line_separates(self):
        fake = Fake("line one\nline two", kind="text")
        report.post(fake, 1, "x_customer_report", INFO)
        self.assertTrue(fake.value.startswith("line one\nline two\n\ngit-shuttle"))

    def test_an_empty_field_gets_the_entry_alone(self):
        fake = Fake(False)
        report.post(fake, 1, "x_customer_report", INFO)
        self.assertTrue(fake.value.startswith("<p><strong>git-shuttle"))

    def test_the_same_pull_request_is_not_added_twice(self):
        fake = Fake("")
        report.post(fake, 1, "x_customer_report", INFO)
        again = report.post(fake, 1, "x_customer_report", INFO)
        self.assertEqual(len(fake.writes), 1)
        self.assertIn("Nothing was written", again)

    def test_a_pull_request_that_the_pm_already_linked_is_not_added(self):
        fake = Fake('<p>see <a href="https://github.example/acme/shop/pull/9">this</a></p>')
        report.post(fake, 1, "x_customer_report", INFO)
        self.assertEqual(fake.writes, [])

    def test_when_odoo_changes_the_old_text_it_is_put_back(self):
        fake = Fake("<p>Precious text</p>", keeps=False)
        with self.assertRaises(OdooError) as caught:
            report.post(fake, 1, "x_customer_report", INFO)
        self.assertIn("put back", str(caught.exception))
        self.assertEqual(fake.value, "<p>Precious text</p>")

    def test_only_a_custom_text_or_html_field_is_written(self):
        for field in ("name", "description", "x_Upper", "x_", "x_a b"):
            with self.assertRaises(OdooError):
                report.plan(Fake(), 1, field, INFO)
        with self.assertRaises(OdooError):
            report.plan(Fake(kind="selection"), 1, "x_customer_report", INFO)

    def test_the_preview_writes_nothing(self):
        fake = Fake("old")
        done = report.plan(fake, 1, "x_customer_report", INFO)
        self.assertEqual((fake.writes, done["old"]), ([], "old"))


class Guard(unittest.TestCase):
    def client(self):
        return OdooClient("https://odoo.example", "d", "u", "secret-key-123")

    def test_the_general_execute_stays_read_only(self):
        with self.assertRaises(OdooError):
            self.client().execute("project.task", "write", [[1], {"x_customer_report": "x"}])

    def test_the_narrow_write_refuses_other_fields_and_models(self):
        for model, field in (
            ("res.partner", "x_customer_report"),
            ("project.task", "name"),
            ("project.task", "x_Bad"),
            ("project.task", ""),
        ):
            with self.assertRaises(OdooError):
                self.client().append_custom_field(model, 1, field, "v")
        with self.assertRaises(OdooError):
            self.client().append_custom_field("project.task", "1", "x_customer_report", "v")


if __name__ == "__main__":
    unittest.main()
