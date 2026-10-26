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
        return [{(fields or ["x_customer_report"])[0]: self.value}]

    def append_custom_field(self, model, record_id, field, value, allow_plain=False):
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

    def test_a_missing_field_names_the_fields_that_look_like_it(self):
        fake = Fake()
        fake.fields_get = lambda model, attributes=None: {
            "x_studio_customer_report": {"type": "html", "string": "Customer report"},
            "x_rapport_client": {"type": "text", "string": "Rapport"},
            "x_priority_note": {"type": "char", "string": "Priority report"},
            "name": {"type": "char", "string": "Name"},
        }
        with self.assertRaises(OdooError) as caught:
            report.plan(fake, 1, "x_customer_report", INFO)
        message = str(caught.exception)
        self.assertIn("x_studio_customer_report (Customer report)", message)
        self.assertIn("x_rapport_client (Rapport)", message)
        self.assertNotIn("x_priority_note", message, "a field of another type is not offered")
        self.assertIn("git config shuttle.odoo-task.report-field", message)

    def test_a_missing_field_with_no_look_alike_says_how_to_find_the_name(self):
        fake = Fake()
        fake.fields_get = lambda model, attributes=None: {"name": {"type": "char", "string": "Name"}}
        with self.assertRaises(OdooError) as caught:
            report.plan(fake, 1, "x_customer_report", INFO)
        self.assertIn("technical name", str(caught.exception))

    def test_only_a_custom_text_or_html_field_is_written(self):
        for field in ("name", "description", "x_Upper", "x_", "x_a b"):
            with self.assertRaises(OdooError):
                report.plan(Fake(), 1, field, INFO)
        with self.assertRaises(OdooError):
            report.plan(Fake(kind="selection"), 1, "x_customer_report", INFO)

    def test_a_field_of_your_own_module_is_written_only_when_it_was_named_on_purpose(self):
        fake = Fake("<p>old</p>")
        fake.fields_get = lambda model, attributes=None: {
            "report_details": {"type": "html", "string": "Report Details"}
        }
        with self.assertRaises(OdooError) as caught:
            report.plan(fake, 1, "report_details", INFO)
        self.assertIn("report-field-allow report_details", str(caught.exception))
        done = report.plan(fake, 1, "report_details", INFO, allow_plain=True)
        self.assertTrue(done["new"].startswith("<p>old</p>"))

    def test_the_fields_that_hold_the_task_are_never_written(self):
        for field in ("description", "name", "state", "stage_id"):
            with self.assertRaises(OdooError):
                report.plan(Fake(), 1, field, INFO, allow_plain=True)

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

    def test_a_plain_field_needs_the_flag_and_a_protected_one_is_refused_even_with_it(self):
        with self.assertRaises(OdooError):
            self.client().append_custom_field("project.task", 1, "report_details", "v")
        for field in ("description", "name"):
            with self.assertRaises(OdooError):
                self.client().append_custom_field("project.task", 1, field, "v", allow_plain=True)

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


PHASES = [
    {
        "title": "Started",
        "when": "2026-10-26T02:13:00Z",
        "items": [
            {"text": "branch 19.0-feature/x", "ref": "19.0-feature/x"},
            {"text": "Project: Preaucess", "ref": "Project: Preaucess"},
        ],
    },
    {
        "title": "Commits",
        "when": "2026-10-26T04:37:00Z",
        "items": [
            {
                "text": "0578368a [FEAT] sale: cancel",
                "url": "https://github.example/a/b/commit/0578368a",
                "ref": "0578368a",
            },
            {
                "text": "8e1f0e85 [FEAT] planning: name",
                "url": "https://github.example/a/b/commit/8e1f0e85",
                "ref": "8e1f0e85",
            },
        ],
    },
    {
        "title": "Pull request",
        "when": "2026-10-26T04:37:00Z",
        "items": [
            {
                "text": "Feedback -> 19.0-staging",
                "url": "https://github.example/a/b/pull/286",
                "ref": "https://github.example/a/b/pull/286",
            }
        ],
    },
]


class Steps(unittest.TestCase):
    def info(self, phases=PHASES):
        return {"branch": "19.0-feature/x", "pr": {}, "commits": [], "phases": [dict(p) for p in phases]}

    def test_every_step_is_written_with_its_title_and_its_links_after_the_old_text(self):
        fake = Fake("<p>PM text</p>")
        report.post(fake, 1, "x_customer_report", self.info())
        self.assertTrue(fake.value.startswith("<p>PM text</p>"))
        for text in (
            "<strong>Started</strong>",
            "<strong>Commits</strong>",
            "<strong>Pull request</strong>",
            'href="https://github.example/a/b/commit/0578368a"',
        ):
            self.assertIn(text, fake.value)
        self.assertLess(fake.value.index("Started"), fake.value.index("Commits"))
        self.assertLess(fake.value.index("Commits"), fake.value.index("Pull request"))

    def test_a_step_that_is_in_the_field_is_not_written_again_and_a_new_one_is_added(self):
        fake = Fake("")
        report.post(fake, 1, "x_customer_report", self.info())
        again = report.post(fake, 1, "x_customer_report", self.info())
        self.assertEqual(len(fake.writes), 1)
        self.assertIn("every step", again)
        more = self.info(
            PHASES
            + [
                {
                    "title": "Merged",
                    "when": "2026-10-26T04:38:00Z",
                    "items": [
                        {
                            "text": "merged into 19.0-staging",
                            "url": "https://github.example/a/b/commit/3e5f6695",
                            "ref": "3e5f6695",
                        }
                    ],
                }
            ]
        )
        report.post(fake, 1, "x_customer_report", more)
        self.assertEqual(len(fake.writes), 2)
        written = fake.value[len(fake.writes[0]) :]
        self.assertIn("Merged", written)
        self.assertNotIn("Commits", written, "only the new step is added")

    def test_a_new_commit_alone_is_added_to_a_report_that_has_the_others(self):
        fake = Fake("")
        report.post(fake, 1, "x_customer_report", self.info())
        later = [
            dict(PHASES[1], items=PHASES[1]["items"] + [{"text": "abcdef12 [FIX] sale: round", "ref": "abcdef12"}])
        ]
        report.post(fake, 1, "x_customer_report", self.info(later))
        added = fake.value[len(fake.writes[0]) :]
        self.assertIn("abcdef12", added)
        self.assertNotIn("0578368a", added)

    def test_the_preview_is_the_plain_text_of_what_is_new(self):
        done = report.plan(Fake(""), 1, "x_customer_report", self.info())
        self.assertIn("Commits - ", done["preview"])
        self.assertIn("- 0578368a [FEAT] sale: cancel (https://github.example/a/b/commit/0578368a)", done["preview"])
        self.assertEqual(done["count"], 5)

    def test_text_and_html_differ_only_in_the_markup_and_the_text_field_gets_a_blank_line(self):
        fake = Fake("line one", kind="text")
        report.post(fake, 1, "x_customer_report", self.info())
        self.assertTrue(fake.value.startswith("line one\n\ngit-shuttle - the steps of the task"))
        self.assertNotIn("<p>", fake.value)

    def test_the_text_of_a_step_is_escaped_in_html(self):
        phases = [
            {
                "title": "Commits",
                "when": "2026-10-26T04:37:00Z",
                "items": [{"text": "a1b2c3d4 <script>alert(1)</script>", "ref": "a1b2c3d4"}],
            }
        ]
        fake = Fake("")
        report.post(fake, 1, "x_customer_report", self.info(phases))
        self.assertNotIn("<script>", fake.value)
        self.assertIn("&lt;script&gt;", fake.value)


class StepTimes(unittest.TestCase):
    def test_a_step_with_a_time_shows_it_in_your_time_and_each_time_is_a_step_of_its_own(self):
        phase = {
            "title": "Deployed",
            "when": "2026-10-26T04:43:00Z",
            "items": [{"text": "to staging (branch 19.0-staging)", "at": "2026-10-26T04:43:00Z"}],
        }
        info = {"phases": [phase]}
        fake = Fake("")
        report.post(fake, 1, "x_customer_report", info)
        self.assertRegex(
            fake.value, r"to staging \(branch 19\.0-staging\) &middot; |to staging \(branch 19\.0-staging\) · "
        )
        self.assertIn("· 2026-10-26", fake.value)
        report.post(fake, 1, "x_customer_report", info)
        self.assertEqual(len(fake.writes), 1, "the same deploy is not written twice")
        later = {
            "phases": [dict(phase, items=[{"text": "to staging (branch 19.0-staging)", "at": "2026-10-27T09:00:00Z"}])]
        }
        report.post(fake, 1, "x_customer_report", later)
        self.assertEqual(len(fake.writes), 2, "a deploy at another time is another step")
