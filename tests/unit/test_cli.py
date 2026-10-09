import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fake_odoo import LOGIN, SECRET, FakeOdoo
from odoo_task import store
from odoo_task.cli import main


def run(*argv):
    """Run the CLI; return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "cfg"
        self.out = Path(self._tmp.name) / "tasks"
        env = mock.patch.dict(os.environ, {"ODOO_TASK_HOME": str(self.home), store.ENV_SECRET: SECRET})
        env.start()
        self.addCleanup(env.stop)

    def profile(self, odoo, name="work"):
        store.save_profile(store.Profile(name=name, url=odoo.url, db="testdb", user=LOGIN, output_dir=str(self.out)))


class Fetch(CliCase):
    def test_fetch_by_number(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, err = run("fetch", "42")
            self.assertEqual(code, 0, err)
            md = Path(out.strip())
            self.assertTrue(md.is_file())
            self.assertEqual(md.parent.parent, self.out)
            self.assertIn("OK    #42", err)

    def test_fetch_by_url_and_hash(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            self.assertEqual(run("fetch", f"{odoo.url}/odoo/project/5/tasks/42")[0], 0)
            self.assertEqual(run("fetch", "#43")[0], 0)

    def test_newest(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, _ = run("fetch", "--newest")
            self.assertEqual(code, 0)
            self.assertIn("49_Shipped_stage", out)

    def test_out_option_and_extra_field_and_unknown_field_warning(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            elsewhere = Path(self._tmp.name) / "else"
            code, out, err = run(
                "fetch", "42", "--out", str(elsewhere), "--field", "x_report:Wishes", "--field", "x_nope"
            )
            self.assertEqual(code, 0, err)
            self.assertIn("## Wishes", Path(out.strip()).read_text(encoding="utf-8"))
            self.assertIn("field 'x_nope' does not exist", err)

    def test_prompt_with_default_and_custom_template(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, _ = run("fetch", "42", "--prompt")
            self.assertEqual(code, 0)
            prompt = Path(out.strip()).parent / "prompt.md"
            self.assertIn("Task #42:", prompt.read_text(encoding="utf-8"))
            template = Path(self._tmp.name) / "t.md"
            template.write_text("CUSTOM {task_id} / {title}", encoding="utf-8")
            run("fetch", "42", "--prompt", "--prompt-template", str(template))
            self.assertTrue(prompt.read_text(encoding="utf-8").startswith("CUSTOM 42 / Fix the invoice export"))

    def test_bad_reference_is_an_error_not_a_traceback(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _out, err = run("fetch", "../../etc/passwd")
            self.assertEqual(code, 1)
            self.assertIn("odoo-task:", err)

    def test_no_profile(self):
        code, _out, err = run("fetch", "1")
        self.assertEqual(code, 1)
        self.assertIn("odoo-task login", err)

    def test_missing_key_without_a_terminal_names_the_variable(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            with mock.patch.dict(os.environ):
                os.environ.pop(store.ENV_SECRET)
                code, _out, err = run("fetch", "42")
            self.assertEqual(code, 1)
            self.assertIn(store.ENV_SECRET, err)

    def test_the_key_never_reaches_the_output(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            _code, out, err = run("fetch", "42")
            self.assertNotIn(SECRET, out + err)


class OtherCommands(CliCase):
    def test_check(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _out, err = run("check")
            self.assertEqual(code, 0)
            self.assertIn("Odoo 19.0", err)
            self.assertIn("only reads", err)

    def test_check_with_a_wrong_key(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            with mock.patch.dict(os.environ, {store.ENV_SECRET: "nope"}):
                code, _out, err = run("check")
            self.assertEqual(code, 1)
            self.assertIn("Authentication failed", err)

    def test_login_with_flags_then_profiles(self):
        with FakeOdoo() as odoo:
            code, _out, err = run(
                "login",
                "--profile",
                "work",
                "--url",
                odoo.url,
                "--db",
                "testdb",
                "--user",
                LOGIN,
                "--out",
                str(self.out),
            )
            self.assertEqual(code, 0, err)
            code, _out, err = run("profiles")
            self.assertIn("work *", err)  # the only profile is the default
            self.assertIn("asked / env", err)

    def test_login_rejects_a_bad_url_and_a_reserved_name(self):
        self.assertEqual(run("login", "--profile", "w", "--url", "file:///etc", "--db", "d", "--user", "u")[0], 1)
        self.assertEqual(
            run("login", "--profile", "fetch", "--url", "https://x.example.com", "--db", "d", "--user", "u")[0], 1
        )

    def test_forget_key(self):
        store.save_secret("work", "k")
        code, _out, err = run("profiles", "--forget-key", "work")
        self.assertEqual(code, 0)
        self.assertIn("removed", err)

    def test_update_from_a_checkout_points_to_git(self):
        code, _out, err = run("update")
        self.assertEqual(code, 0)
        self.assertIn("source checkout", err)

    def test_version_and_help(self):
        with self.assertRaises(SystemExit) as ctx:
            run("--version")
        self.assertEqual(ctx.exception.code, 0)
        code, _out, err = run()
        self.assertEqual(code, 0)
        self.assertIn("fetch", err)


class Tasks(CliCase):
    def test_the_table_lists_my_open_tasks(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, _err = run("tasks")
            self.assertEqual(code, 0)
            lines = out.strip().splitlines()
            self.assertTrue(lines[0].lstrip().startswith("ID"))
            self.assertEqual(len(lines), 5)  # header + 49, 48, 43, 42
            self.assertIn("Fix the invoice export", out)
            self.assertIn("No stage", out)
            for hidden in ("Closed one", "Not mine", "Folded stage"):
                self.assertNotIn(hidden, out)
            self.assertIn("Open = state not done or cancelled, stage not folded", _err)

    def test_all_includes_closed_ones(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            self.assertIn("Closed one", run("tasks", "--all")[1])

    def test_ids_only_for_a_script(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, _err = run("tasks", "--ids")
            self.assertEqual((code, out.split()), (0, ["49", "48", "43", "42"]))

    def test_limit_is_validated(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            for bad in ("0", "-1", "100000"):
                code, _out, err = run("tasks", "--limit", bad)
                self.assertEqual(code, 1, bad)
                self.assertIn("--limit", err)

    def test_the_ids_feed_fetch(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            ids = run("tasks", "--ids")[1].split()
            code, out, _err = run("fetch", *ids)
            self.assertEqual(code, 0)
            self.assertEqual(len(out.strip().splitlines()), 4)

    def test_exclude_stage_hides_a_stage_for_this_run(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            self.assertIn("Shipped stage", run("tasks")[1])
            code, out, err = run("tasks", "--exclude-stage", "Shipped")
            self.assertEqual(code, 0)
            self.assertNotIn("Shipped stage", out)
            self.assertIn("nor in stage Shipped", err)

    def test_closed_stages_saved_in_the_profile(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _out, err = run("profiles", "--closed-stages", "Shipped, Done")
            self.assertEqual(code, 0, err)
            self.assertEqual(store.load_profile("work").closed_stages, ["Shipped", "Done"])
            self.assertNotIn("Shipped stage", run("tasks")[1])
            self.assertIn("48_No_stage", run("fetch", "--newest")[1])  # newest respects it too
            run("profiles", "--closed-stages", "")
            self.assertEqual(store.load_profile("work").closed_stages, [])
            self.assertIn("Shipped stage", run("tasks")[1])


class Preferences(CliCase):
    def saved(self, odoo, *assignments):
        self.profile(odoo)
        code, _out, err = run("profiles", "--set", *assignments)
        self.assertEqual(code, 0, err)

    def test_set_and_show(self):
        with FakeOdoo() as odoo:
            self.saved(odoo, "attachments=yes", "prompt=yes", "messages=2")
            loaded = store.load_profile("work")
            self.assertEqual((loaded.attachments, loaded.prompt, loaded.messages), (True, True, 2))
            _code, _out, err = run("profiles", "--show")
            self.assertIn("attachments  yes", err)
            self.assertIn("messages     2", err)
            self.assertNotIn(SECRET, err)

    def test_bad_values_are_refused_and_nothing_is_saved(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            for bad in ("attachments=maybe", "messages=-1", "messages=999", "bogus=1", "copy=yes", "attachments"):
                code, _out, err = run("profiles", "--set", "prompt=yes", bad)
                self.assertEqual(code, 1, bad)
                self.assertIn("odoo-task:", err)
            self.assertFalse(store.load_profile("work").prompt)

    def test_a_fetch_follows_the_profile(self):
        with FakeOdoo() as odoo:
            self.saved(odoo, "attachments=yes", "prompt=yes", "messages=2")
            code, out, err = run("fetch", "42")
            self.assertEqual(code, 0, err)
            folder = Path(out.strip()).parent
            self.assertTrue((folder / "prompt.md").is_file())
            self.assertTrue((folder / "attachments" / "78_evil.txt").is_file())
            self.assertIn("Latest messages", (folder / "task.md").read_text(encoding="utf-8"))

    def test_a_flag_wins_over_the_profile(self):
        with FakeOdoo() as odoo:
            self.saved(odoo, "attachments=yes", "prompt=yes", "messages=2")
            code, out, err = run("fetch", "42", "--no-attachments", "--no-prompt", "--messages", "0")
            self.assertEqual(code, 0, err)
            folder = Path(out.strip()).parent
            self.assertFalse((folder / "prompt.md").exists())
            self.assertFalse((folder / "attachments").exists())
            self.assertNotIn("Latest messages", (folder / "task.md").read_text(encoding="utf-8"))

    def test_without_preferences_nothing_extra_is_done(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            _code, out, _err = run("fetch", "42")
            folder = Path(out.strip()).parent
            self.assertFalse((folder / "prompt.md").exists())
            self.assertFalse((folder / "attachments").exists())

    def test_the_saved_output_folder_is_used(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            elsewhere = Path(self._tmp.name) / "elsewhere"
            run("profiles", "--set", f"out={elsewhere}")
            _code, out, _err = run("fetch", "42")
            self.assertTrue(Path(out.strip()).is_relative_to(elsewhere))

    def test_extra_fields_can_be_saved_and_used(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _out, err = run("profiles", "--extra-field", "x_report:Customer wishes", "--extra-field", "x_ref")
            self.assertEqual(code, 0, err)
            self.assertEqual(store.load_profile("work").extra_fields, ["x_report:Customer wishes", "x_ref"])
            text = Path(run("fetch", "42")[1].strip()).read_text(encoding="utf-8")
            self.assertIn("## Customer wishes", text)
            self.assertIn("REF-1", text)
            run("profiles", "--remove-extra-field", "x_ref")
            self.assertEqual(store.load_profile("work").extra_fields, ["x_report:Customer wishes"])

    def test_a_bad_extra_field_is_refused(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _out, err = run("profiles", "--extra-field", "a;b")
            self.assertEqual(code, 1)
            self.assertIn("Not a valid field name", err)

    def test_the_menu_uses_the_profile_as_its_defaults(self):
        with FakeOdoo() as odoo:
            self.saved(odoo, "attachments=yes", "prompt=yes", "messages=2")
            # every answer is just Enter: the saved preferences apply
            code, err, _opened = MenuFlow.drive(self, odoo, ["42", "", "", "", "", ""], ["ref", "done"])
            self.assertEqual(code, 0, err)
            folder = next(self.out.iterdir())
            self.assertTrue((folder / "prompt.md").is_file())
            self.assertTrue((folder / "attachments").is_dir())
            self.assertIn("Latest messages", (folder / "task.md").read_text(encoding="utf-8"))


class FetchSeveral(CliCase):
    def test_several_tasks_each_path_on_stdout(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, _err = run("fetch", "42", "43", f"{odoo.url}/odoo/project/5/tasks/42")
            self.assertEqual(code, 0)
            self.assertEqual(len(out.strip().splitlines()), 2)  # 42 twice is fetched once

    def test_one_failing_task_does_not_stop_the_others(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, err = run("fetch", "42", "999", "43")
            self.assertEqual(code, 1)
            self.assertEqual(len(out.strip().splitlines()), 2)
            self.assertIn("ERROR #999", err)

    def test_a_bad_reference_stops_before_any_request(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _out, err = run("fetch", "42", "nope")
            self.assertEqual(code, 1)
            self.assertIn("Not a task number", err)
            self.assertEqual(odoo.calls, [])
            self.assertFalse(self.out.exists())

    def test_a_task_of_another_company_can_be_fetched(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, out, err = run("fetch", "30")
            self.assertEqual(code, 0, err)
            self.assertIn("30_Other_company", out)

    def test_copy_needs_a_single_task(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _out, err = run("fetch", "42", "43", "--copy")
            self.assertEqual(code, 1)
            self.assertIn("one task at a time", err)

    def test_copy_puts_the_prompt_on_the_clipboard(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            with mock.patch("odoo_task.clipboard.copy", return_value=True) as copied:
                code, _out, err = run("fetch", "42", "--copy")
            self.assertEqual(code, 0)
            self.assertIn("Task #42:", copied.call_args.args[0])
            self.assertIn("on the clipboard", err)

    def test_copy_without_a_clipboard_program_still_writes_the_prompt(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            with mock.patch("odoo_task.clipboard.copy", return_value=False):
                code, _out, err = run("fetch", "42", "--copy")
            self.assertEqual(code, 0)
            self.assertIn("no clipboard program", err)
            self.assertTrue((next(self.out.iterdir()) / "prompt.md").is_file())


class MenuFlow(CliCase):
    """The menu with a terminal: the answers and the choices are scripted."""

    def drive(self, odoo, answers, choices):
        answers, choices, opened = iter(answers), iter(choices), []
        with (
            mock.patch("odoo_task.cli.interactive", return_value=True),
            mock.patch("builtins.input", side_effect=lambda *_a: next(answers)),
            mock.patch("odoo_task.menu.choose", side_effect=lambda *_a, **_k: next(choices)),
            mock.patch(
                "odoo_task.opener.open_path",
                side_effect=lambda path, folder=False: opened.append((path.name, folder)) or True,
            ),
        ):
            code, _out, err = run()
        return code, err, opened

    def test_options_are_asked_and_the_result_can_be_opened(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            # answers: task, folder, attachments?, prompt?, copy?, messages
            # choices: menu entry, open file, open folder, back, quit
            code, err, opened = self.drive(odoo, ["42", "", "y", "y", "n", "2"], ["ref", "file"])
            self.assertEqual(code, 0, err)
            folder = next(self.out.iterdir())
            self.assertTrue((folder / "prompt.md").is_file())
            self.assertIn("Latest messages", (folder / "task.md").read_text(encoding="utf-8"))
            self.assertTrue((folder / "attachments" / "78_evil.txt").is_file())
            self.assertEqual(opened, [("task.md", False)])

    def test_defaults_fetch_only_the_task(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _err, opened = self.drive(odoo, ["42", "", "n", "n", "0"], ["ref", "done"])
            self.assertEqual(code, 0)
            folder = next(self.out.iterdir())
            self.assertFalse((folder / "prompt.md").exists())
            self.assertFalse((folder / "attachments").exists())
            self.assertEqual(opened, [])

    def test_the_menu_ends_after_one_action(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            # a second call of menu.choose would raise StopIteration: the menu must not come back
            code, err, _opened = self.drive(odoo, [], ["check"])
            self.assertEqual(code, 0, err)
            self.assertIn("server reachable", err)

    def test_the_exit_code_is_the_one_of_the_action(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            with mock.patch.dict(os.environ, {store.ENV_SECRET: "nope"}):
                code, err, _opened = self.drive(odoo, [], ["check"])
            self.assertEqual(code, 1)
            self.assertIn("Authentication failed", err)

    def test_one_open_action_then_the_program_ends(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _err, opened = self.drive(odoo, ["42", "", "n", "n", "0"], ["ref", "folder"])
            self.assertEqual(code, 0)
            self.assertEqual(opened, [(next(self.out.iterdir()).name, True)])

    def test_done_ends_without_opening_anything(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _err, opened = self.drive(odoo, ["42", "", "n", "n", "0"], ["ref", "done"])
            self.assertEqual((code, opened), (0, []))

    def test_pick_from_my_tasks(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            # answers: which ones, folder, attachments?, prompt?, messages   (two tasks: no copy question)
            code, err, opened = self.drive(odoo, ["1,2", "", "n", "n", "0"], ["pick", "folder"])
            self.assertEqual(code, 0, err)
            self.assertEqual(sorted(p.name[:2] for p in self.out.iterdir()), ["48", "49"])
            self.assertEqual(opened, [(self.out.name, True)])  # several tasks: the folder that holds them

    def test_pick_with_a_wrong_choice_is_reported(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, err, _opened = self.drive(odoo, ["7"], ["pick"])
            self.assertEqual(code, 1)
            self.assertIn("not in the list", err)
            self.assertFalse(self.out.exists())

    def test_the_prompt_can_be_copied_from_the_menu(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            # one task, prompt yes, copy no at the question, then copy from the menu
            with mock.patch("odoo_task.clipboard.copy", return_value=True) as copied:
                code, _err, _opened = self.drive(odoo, ["42", "", "n", "y", "n", "0"], ["ref", "copy"])
            self.assertEqual(code, 0)
            self.assertIn("Task #42:", copied.call_args.args[0])

    def test_newest_does_not_ask_for_a_number(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, _err, _opened = self.drive(odoo, ["", "n", "n", "0"], ["newest", "done"])
            self.assertEqual(code, 0)
            self.assertTrue(next(self.out.iterdir()).name.startswith("49_"))

    def test_the_folder_can_be_chosen(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            chosen = Path(self._tmp.name) / "my" / "place"
            code, _err, _opened = self.drive(odoo, ["42", str(chosen), "n", "n", "0"], ["ref", "done"])
            self.assertEqual(code, 0)
            self.assertTrue((next(chosen.iterdir()) / "task.md").is_file())
            self.assertFalse(self.out.exists())  # the profile's folder was not used

    def test_an_unwritable_folder_is_reported_and_the_menu_ends(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            blocker = Path(self._tmp.name) / "a-file"
            blocker.write_text("x")
            code, err, opened = self.drive(odoo, ["42", str(blocker / "sub"), "n", "n", "0"], ["ref"])
            self.assertEqual(code, 1)
            self.assertIn("odoo-task:", err)
            self.assertEqual(opened, [])

    def test_an_empty_task_answer_returns_to_the_menu(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, err, _opened = self.drive(odoo, [""], ["ref"])
            self.assertEqual(code, 0)
            self.assertNotIn("odoo-task:", err)
            self.assertFalse(self.out.exists())

    def test_a_bad_task_is_reported_and_the_menu_ends(self):
        with FakeOdoo() as odoo:
            self.profile(odoo)
            code, err, opened = self.drive(odoo, ["abc", "", "n", "n", "0"], ["ref"])
            self.assertEqual(code, 1)
            self.assertIn("Not a task number", err)
            self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
