import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fake_odoo
from fake_odoo import LOGIN, SECRET, FakeOdoo
from odoo_task.client import OdooClient, OdooError
from odoo_task.fetch import ExtraField, TaskFetcher, render_markdown, render_prompt


class FetchTask(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def fetcher(self, odoo):
        return TaskFetcher(OdooClient(odoo.url, "testdb", LOGIN, SECRET))

    def test_a_task_becomes_a_markdown_folder(self):
        with FakeOdoo() as odoo:
            result = self.fetcher(odoo).fetch(42, self.out, base_url=odoo.url)
            text = result.markdown.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# Fix the invoice export"))
            self.assertIn("**Project:** Project A", text)
            self.assertIn("**Stage:** In Progress", text)
            self.assertIn("**Assignees:** Dev User", text)
            self.assertIn("**Tags:** bug, export", text)
            self.assertIn("**Customer:** ACME", text)
            self.assertIn("**Deadline:** 2026-12-01", text)
            self.assertIn("Step **one**", text)
            self.assertIn("&model=project.task", text)

    def test_images_are_saved_next_to_the_file_and_linked(self):
        with FakeOdoo() as odoo:
            result = self.fetcher(odoo).fetch(42, self.out)
            self.assertCountEqual(result.images, ["img_b64_1.png", "img_att_77.png"])
            for name in result.images:
                self.assertTrue((result.directory / name).is_file())
            text = result.markdown.read_text(encoding="utf-8")
            self.assertIn("![image](img_b64_1.png)", text)
            self.assertIn("![image](img_att_77.png)", text)

    def test_the_folder_name_cannot_escape_the_output_folder(self):
        with FakeOdoo() as odoo:
            result = self.fetcher(odoo).fetch(42, self.out)
            self.assertEqual(result.directory.parent.resolve(), self.out.resolve())
            self.assertNotIn("..", result.directory.name)

    def test_extra_fields_with_titles_and_unknown_ones_are_skipped(self):
        with FakeOdoo() as odoo:
            extra = [
                ExtraField.parse("x_report:Customer wishes"),
                ExtraField.parse("x_ref"),
                ExtraField.parse("x_nope"),
            ]
            result = self.fetcher(odoo).fetch(42, self.out, extra_fields=extra)
            text = result.markdown.read_text(encoding="utf-8")
            self.assertIn("## Customer wishes", text)
            self.assertIn("Customer says **urgent**.", text)
            self.assertIn("## Reference", text)  # the title falls back to the field label
            self.assertIn("REF-1", text)
            self.assertEqual(result.skipped_fields, ["x_nope"])

    def test_attachments_are_listed_and_only_downloaded_on_request(self):
        with FakeOdoo() as odoo:
            listed = self.fetcher(odoo).fetch(42, self.out / "a")
            self.assertIn("## Attachments", listed.markdown.read_text(encoding="utf-8"))
            self.assertFalse((listed.directory / "attachments").exists())
            downloaded = self.fetcher(odoo).fetch(42, self.out / "b", attachments=True)
            files = [p.name for p in (downloaded.directory / "attachments").iterdir()]
            self.assertIn("78_evil.txt", files)  # the name "../evil.txt" is reduced to its last part
            self.assertFalse((self.out / "b" / "evil.txt").exists())

    def test_an_image_already_in_the_description_is_not_saved_twice(self):
        with FakeOdoo() as odoo:
            result = self.fetcher(odoo).fetch(42, self.out, attachments=True)
            text = result.markdown.read_text(encoding="utf-8")
            self.assertTrue((result.directory / "img_att_77.png").is_file())
            self.assertFalse((result.directory / "attachments" / "77_shot.png").exists())
            self.assertIn("img_att_77.png (image/png", text)
            self.assertEqual(text.count("![image](img_att_77.png)"), 1)  # shown once, in the description
            self.assertIn("attachments/78_evil.txt", text)  # the other attachment is downloaded as before

    def test_other_image_attachments_are_downloaded_and_shown(self):
        import odoo_task.fetch as fetch_module

        with FakeOdoo() as odoo:
            fetcher = self.fetcher(odoo)
            rows = [{"id": 90, "name": "extra.png", "mimetype": "image/png", "file_size": 70}]
            with (
                mock.patch.object(fetcher.client, "search_read", return_value=rows),
                mock.patch.object(fetcher, "_read_attachment", return_value=(fake_odoo.PNG_B64, "image/png")),
            ):
                out = fetcher._attachments(42, self.out, download=True, known={})
            self.assertEqual(out[0][0], "attachments/90_extra.png")
            self.assertTrue((self.out / "attachments" / "90_extra.png").is_file())
            self.assertIn("![90_extra.png](attachments/90_extra.png)", fetch_module.render_markdown("T", [], [], out))

    def test_task_folders_are_private(self):
        with FakeOdoo() as odoo:
            result = self.fetcher(odoo).fetch(42, self.out, attachments=True)
            self.assertEqual(result.directory.stat().st_mode & 0o077, 0)
            self.assertEqual((result.directory / "attachments").stat().st_mode & 0o077, 0)

    def test_latest_messages_in_order(self):
        with FakeOdoo() as odoo:
            result = self.fetcher(odoo).fetch(42, self.out, messages=2)
            text = result.markdown.read_text(encoding="utf-8")
            self.assertLess(text.index("First"), text.index("Second"))

    def test_an_empty_description_is_marked(self):
        with FakeOdoo() as odoo:
            result = self.fetcher(odoo).fetch(43, self.out)
            self.assertIn("_(empty)_", result.markdown.read_text(encoding="utf-8"))

    def test_unknown_task(self):
        with FakeOdoo() as odoo, self.assertRaises(OdooError):
            self.fetcher(odoo).fetch(999, self.out)

    def test_newest_assigned_task(self):
        with FakeOdoo() as odoo:
            self.assertEqual(self.fetcher(odoo).newest_assigned_task_id(), 49)

    def test_nothing_but_reads_was_sent(self):
        with FakeOdoo() as odoo:
            fetcher = self.fetcher(odoo)
            fetcher.fetch(42, self.out, extra_fields=[ExtraField.parse("x_report")], messages=5, attachments=True)
            fetcher.newest_assigned_task_id()
            methods = {m for _model, m in odoo.calls}
            self.assertTrue(methods <= {"read", "search_read", "fields_get"}, methods)

    def test_extra_field_names_are_validated(self):
        for bad in ("a;b", "../x", "x y", ""):
            with self.assertRaises(ValueError):
                ExtraField.parse(bad)


class MyTasks(unittest.TestCase):
    def fetcher(self, odoo):
        return TaskFetcher(OdooClient(odoo.url, "testdb", LOGIN, SECRET))

    def test_only_my_open_tasks_newest_first(self):
        with FakeOdoo() as odoo:
            tasks = self.fetcher(odoo).my_tasks()
            # 44 is closed, 45 is somebody else's, 46 is in a folded stage
            self.assertEqual([t.id for t in tasks], [49, 48, 43, 42])
            self.assertEqual(tasks[3].project, "Project A")
            self.assertEqual(tasks[3].stage, "In Progress")
            self.assertEqual(tasks[3].deadline, "2026-12-01")

    def test_closed_tasks_on_request(self):
        with FakeOdoo() as odoo:
            self.assertEqual([t.id for t in self.fetcher(odoo).my_tasks(include_closed=True)], [49, 48, 46, 44, 43, 42])

    def test_the_limit(self):
        with FakeOdoo() as odoo:
            self.assertEqual([t.id for t in self.fetcher(odoo).my_tasks(limit=1)], [49])
            self.assertEqual(len(self.fetcher(odoo).my_tasks(limit=0)), 1)  # never a nonsense limit

    def test_newest_is_an_open_task(self):
        with FakeOdoo() as odoo:
            self.assertEqual(self.fetcher(odoo).newest_assigned_task_id(), 49)

    def test_a_folded_stage_counts_as_closed_and_no_stage_does_not(self):
        with FakeOdoo() as odoo:
            ids = [t.id for t in self.fetcher(odoo).my_tasks()]
            self.assertNotIn(46, ids)  # stage Done, folded
            self.assertIn(48, ids)  # no stage: never hidden by a stage rule

    def test_stages_the_user_calls_closed(self):
        with FakeOdoo() as odoo:
            fetcher = self.fetcher(odoo)
            self.assertEqual([t.id for t in fetcher.my_tasks(closed_stages=["Shipped"])], [48, 43, 42])
            self.assertEqual(
                [t.id for t in fetcher.my_tasks(closed_stages=["  ", ""])], [49, 48, 43, 42]
            )  # blanks ignored
            self.assertEqual(fetcher.newest_assigned_task_id(closed_stages=["Shipped"]), 48)

    def test_all_includes_the_stage_closed_ones(self):
        with FakeOdoo() as odoo:
            ids = [t.id for t in self.fetcher(odoo).my_tasks(include_closed=True, closed_stages=["Shipped"])]
            self.assertIn(49, ids)
            self.assertIn(46, ids)

    def test_which_domain_keeps_only_open_tasks(self):
        with FakeOdoo() as odoo:
            fetcher = self.fetcher(odoo)
            fetcher._fields = {
                "state": {"type": "selection", "selection": [["a", "A"], ["1_done", "D"], ["1_canceled", "C"]]}
            }
            self.assertEqual(fetcher.closed_domain(), [("state", "not in", ["1_done", "1_canceled"])])
            fetcher._fields = {"is_closed": {"type": "boolean", "searchable": True}}
            self.assertEqual(fetcher.closed_domain(), [("is_closed", "=", False)])
            fetcher._fields = {"is_closed": {"type": "boolean", "searchable": False}}
            self.assertEqual(fetcher.closed_domain(), [])  # cannot be searched: nothing is guessed
            fetcher._fields = {"name": {"type": "char"}}
            self.assertEqual(fetcher.closed_domain(), [])

    def test_only_reads_are_sent(self):
        with FakeOdoo() as odoo:
            self.fetcher(odoo).my_tasks(include_closed=True)
            self.assertTrue({m for _model, m in odoo.calls} <= {"fields_get", "search_read", "read"})


class Sizes(unittest.TestCase):
    def test_human_sizes(self):
        from odoo_task.fetch import _human_size

        self.assertEqual(_human_size(70), "70 B")
        self.assertEqual(_human_size(2048), "2 KB")
        self.assertEqual(_human_size(5 * 1024 * 1024), "5.0 MB")


class Rendering(unittest.TestCase):
    def test_prompt_placeholders_are_filled_once(self):
        text = render_prompt(7, "T {task_content}", "BODY {title}", "id={task_id} t={title} c={task_content}")
        self.assertEqual(text, "id=7 t=T {task_content} c=BODY {title}")

    def test_default_prompt_is_generic(self):
        text = render_prompt(7, "Title", "Body")
        self.assertIn("Task #7: Title", text)
        self.assertIn("Body", text)

    def test_render_markdown_minimal(self):
        self.assertEqual(render_markdown("T", [], [("Description", "")]), "# T\n\n## Description\n\n_(empty)_\n")


if __name__ == "__main__":
    unittest.main()
