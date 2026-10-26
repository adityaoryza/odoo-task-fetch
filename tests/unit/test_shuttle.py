"""The add-on of git-shuttle: what it says, from the task folders written by `odoo-task fetch`. No Odoo, no network."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from odoo_task import shuttle, store

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "bin" / "git-shuttle-odoo-task"

TASK_MD = """# [Sales] Keep manual Order Date on confirmation

- **Project:** Confort et eau
- **Stage:** Running
- **Assignees:** Aditya Oryza Mahendra
- **Tags:** whatsapp request
- **Link:** https://odoo.example/web#id=15607&model=project.task&view_type=form

## Description

When a quotation is confirmed, the Order Date must stay equal to the Quotation Date entered by the user.

It must not be replaced with the confirmation date.

## Attachments

- attachments/1_image.png (image/png, 1 KB)
"""


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="odoo-task-shuttle-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tasks = self.tmp / "tasks"
        self.tasks.mkdir()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        # a connection whose folder is the folder of the tasks, as odoo-task makes it
        self.config = self.tmp / "config"
        env = {
            "XDG_CONFIG_HOME": str(self.config),
            "HOME": str(self.tmp),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        store.save_profile(
            store.Profile(name="work", url="https://odoo.example", db="d", user="u", output_dir=str(self.tasks))
        )
        store.set_default_profile("work")
        self.ctx = {
            "protocol": 1,
            "hook": "start",
            "repo": {"root": str(self.repo), "name": "repo"},
            "args": {"task": "15607"},
        }

    def task(self, task_id=15607, text=TASK_MD, name="Keep_manual_Order_Date"):
        folder = self.tasks / f"{task_id}_{name}"
        folder.mkdir()
        (folder / "task.md").write_text(text, encoding="utf-8")
        return folder


class Manifest(unittest.TestCase):
    def test_it_says_what_it_is_and_what_it_asks_for(self):
        m = shuttle.manifest()
        self.assertEqual((m["protocol"], m["name"]), (1, "odoo-task"))
        self.assertEqual(m["hooks"], ["start", "pr", "status", "tasks", "setup", "report"])
        self.assertEqual(m["flags"], {"start": ["--task"]})
        self.assertEqual(
            m["env"],
            ["ODOO_TASK_API_KEY"],
            "the only variable it may read: the key, to fetch a task that is not there yet",
        )

    def test_the_launcher_answers_the_same(self):
        command = [str(LAUNCHER), "--shuttle-manifest"]
        out = subprocess.run(command, capture_output=True, text=True, check=True)  # noqa: S603
        self.assertEqual(json.loads(out.stdout)["name"], "odoo-task")

    def test_anything_else_is_odoo_task_itself(self):
        out = subprocess.run([str(LAUNCHER), "--version"], capture_output=True, text=True)  # noqa: S603
        self.assertEqual(out.returncode, 0)
        self.assertTrue(out.stdout.startswith("odoo-task "))


class Start(Base):
    def test_the_branch_comes_from_the_title_without_its_tags(self):
        self.task()
        answer = shuttle.hook_start(self.ctx)
        self.assertEqual(answer["branch"], "Keep manual Order Date on confirmation")
        reference = {k: v for k, v in answer["reference"].items() if k != "details"}
        self.assertEqual(
            reference,
            {
                "id": "15607",
                "title": "[Sales] Keep manual Order Date on confirmation",
                "link": "https://odoo.example/web#id=15607&model=project.task&view_type=form",
            },
        )
        self.assertIn("15607", answer["note"])

    def test_the_task_can_be_given_as_a_number_a_hash_or_an_address(self):
        self.task()
        for given in (
            "15607",
            "#15607",
            "https://odoo.example/web#id=15607&model=project.task&view_type=form",
            "https://odoo.example/odoo/project/5/tasks/15607",
        ):
            self.ctx["args"]["task"] = given
            self.assertEqual(shuttle.hook_start(self.ctx)["reference"]["id"], "15607", given)

    def test_several_tags_and_a_title_that_is_only_a_tag(self):
        self.task(1, TASK_MD.replace("[Sales] Keep manual", "[Sales][Bug] Keep manual"), "a")
        self.ctx["args"]["task"] = "1"
        self.assertEqual(shuttle.hook_start(self.ctx)["branch"], "Keep manual Order Date on confirmation")
        self.task(2, "# [Only a tag]\n", "b")
        self.ctx["args"]["task"] = "2"
        self.assertEqual(shuttle.hook_start(self.ctx)["branch"], "task 2")

    def test_a_task_that_is_not_there_is_fetched_once_and_its_failure_is_the_message(self):
        self.ctx["args"]["task"] = "99"
        failed = subprocess.CompletedProcess([], 1, "", "Odoo said: no key. Set ODOO_TASK_API_KEY")
        with mock.patch("odoo_task.shuttle.subprocess.run", return_value=failed) as run:
            with self.assertRaises(shuttle.Problem) as caught:
                shuttle.hook_start(self.ctx)
        fetch_call = [c for c in run.call_args_list if "fetch" in c.args[0]]
        self.assertEqual(len(fetch_call), 1, "one fetch")
        self.assertIn("fetch 99", " ".join(fetch_call[0].args[0]))
        self.assertIn("--profile", fetch_call[0].args[0], "with the connection of this repository")
        self.assertIn("task 99 is not fetched yet", str(caught.exception))
        self.assertIn("no key", str(caught.exception))

    def test_a_task_that_is_fetched_by_the_call_is_used(self):
        self.ctx["args"]["task"] = "15607"

        def fetch(argv, **kwargs):
            if "fetch" in argv:
                self.task()
                return subprocess.CompletedProcess(argv, 0, "OK", "")
            return subprocess.CompletedProcess(argv, 1, "", "")

        with mock.patch("odoo_task.shuttle.subprocess.run", side_effect=fetch):
            self.assertEqual(shuttle.hook_start(self.ctx)["reference"]["id"], "15607")

    def test_a_value_that_is_not_a_task(self):
        self.ctx["args"]["task"] = "not a task"
        with self.assertRaises(ValueError):
            shuttle.hook_start(self.ctx)

    def test_a_long_title_is_cut_to_what_the_protocol_takes(self):
        self.task(5, "# " + "Very long " * 60 + "\n", "long")
        self.ctx["args"]["task"] = "5"
        answer = shuttle.hook_start(self.ctx)
        self.assertLessEqual(len(answer["branch"]), 120)
        self.assertLessEqual(len(answer["reference"]["title"]), 200)
        self.assertLessEqual(len(answer["note"]), 500)

    def test_the_newest_folder_wins_when_a_title_changed(self):
        old = self.task(7, "# Old title\n", "Old_title")
        os.utime(old / "task.md", (1, 1))
        self.task(7, "# New title\n", "New_title")
        self.ctx["args"]["task"] = "7"
        self.assertEqual(shuttle.hook_start(self.ctx)["branch"], "New title")

    def test_the_folder_comes_from_the_connection_unless_the_repository_says_otherwise(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "15607_x").mkdir()
        (elsewhere / "15607_x" / "task.md").write_text("# From elsewhere\n", encoding="utf-8")
        self.task()
        self.assertEqual(shuttle.hook_start(self.ctx)["branch"], "Keep manual Order Date on confirmation")
        git(self.repo, "config", "shuttle.odoo-task.dir", str(elsewhere))
        self.assertEqual(shuttle.hook_start(self.ctx)["branch"], "From elsewhere")

    def test_a_connection_can_be_chosen_for_the_repository(self):
        other = self.tmp / "other"
        other.mkdir()
        (other / "15607_y").mkdir()
        (other / "15607_y" / "task.md").write_text("# Other connection\n", encoding="utf-8")
        store.save_profile(
            store.Profile(name="second", url="https://two.example", db="d", user="u", output_dir=str(other))
        )
        git(self.repo, "config", "shuttle.odoo-task.profile", "second")
        self.assertEqual(shuttle.hook_start(self.ctx)["branch"], "Other connection")
        git(self.repo, "config", "shuttle.odoo-task.profile", "missing")
        with self.assertRaises(shuttle.Problem):
            shuttle.hook_start(self.ctx)

    def test_without_a_connection_it_says_how_to_make_one(self):
        shutil.rmtree(self.config)
        with self.assertRaises(shuttle.Problem) as caught:
            shuttle.hook_start(self.ctx)
        self.assertIn("odoo-task login", str(caught.exception))

    def test_several_connections_and_no_default_is_said(self):
        store.save_profile(
            store.Profile(name="second", url="https://two.example", db="d", user="u", output_dir=str(self.tasks))
        )
        (self.config / "odoo-task" / "config.json").unlink(missing_ok=True)
        with self.assertRaises(shuttle.Problem) as caught:
            shuttle.hook_start(self.ctx)
        self.assertIn("several connections", str(caught.exception))


class Status(Base):
    def card_ctx(self, **extra):
        return {**self.ctx, "hook": "status", "ref-addon": "odoo-task", "ref-id": "15607", **extra}

    def test_the_card_of_the_task_of_the_branch(self):
        self.task()
        card = shuttle.hook_status(self.card_ctx())["cards"][0]
        self.assertEqual(card["title"], "[Sales] Keep manual Order Date on confirmation")
        self.assertEqual(card["subtitle"], "Running")
        self.assertEqual(card["link"], "https://odoo.example/web#id=15607&model=project.task&view_type=form")
        fields = {f["label"]: f["value"] for f in card["fields"]}
        self.assertEqual(
            {k: v for k, v in fields.items() if k not in ("Fetched", "Files", "Folder")},
            {"Project": "Confort et eau", "Assignees": "Aditya Oryza Mahendra", "Tags": "whatsapp request"},
        )
        self.assertRegex(fields["Fetched"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$", "when the task was read, in your time")
        self.assertIn("must stay equal", card["text"])
        self.assertNotIn("Attachments", card["text"], "only the description")

    def test_a_branch_that_is_not_for_one_of_its_tasks_has_no_card(self):
        self.task()
        self.assertEqual(shuttle.hook_status(self.card_ctx(**{"ref-addon": "jira"})), {"cards": []})
        self.assertEqual(shuttle.hook_status(self.card_ctx(**{"ref-id": ""})), {"cards": []})
        self.assertEqual(shuttle.hook_status(self.card_ctx(**{"ref-id": "abc"})), {"cards": []})

    def test_a_task_that_is_not_fetched_any_more_is_said_not_fetched_again(self):
        with mock.patch("odoo_task.shuttle.subprocess.run") as run:
            with self.assertRaises(shuttle.Problem):
                shuttle.hook_status(self.card_ctx())
        self.assertFalse([c for c in run.call_args_list if "fetch" in c.args[0]], "a card never goes to Odoo")

    def test_a_link_that_is_not_http_is_left_out_and_texts_are_cut(self):
        self.task(
            3,
            "# T\n\n- **Link:** javascript:alert(1)\n- **Stage:** "
            + "S" * 500
            + "\n\n## Description\n\n"
            + "word " * 400,
            "t",
        )
        card = shuttle.hook_status(self.card_ctx(**{"ref-id": "3"}))["cards"][0]
        self.assertNotIn("link", card)
        self.assertLessEqual(len(card["subtitle"]), 200)
        self.assertLessEqual(len(card["text"]), 5000, "the limit of the protocol")


class PullRequest(Base):
    def pr_ctx(self, commits):
        return {**self.ctx, "hook": "pr", "ref-addon": "odoo-task", "ref-id": "15607", "commits": commits}

    def test_the_description_in_the_style_of_the_repository(self):
        self.task()
        answer = shuttle.hook_pr(
            self.pr_ctx(
                "a1b2c3d [FIX] sale_documents: keep the order date\n9f8e7d6 [IMP] custom_planning: show it on the card"
            )
        )
        self.assertEqual(answer["title"], "[Sales] Keep manual Order Date on confirmation")
        body = answer["body"]
        lines = body.splitlines()
        self.assertEqual(lines[0], "## Description")
        self.assertIn("must stay equal to the Quotation Date", lines[1])
        self.assertIn("Task #15607: https://odoo.example/web#id=15607", body)
        self.assertIn("## Commits & Changes", body)
        self.assertIn("### 1. `sale_documents`: keep the order date (a1b2c3d)", body)
        self.assertIn("### 2. `custom_planning`: show it on the card (9f8e7d6)", body)
        self.assertIn("## Verification", body)
        self.assertLess(body.index("## Description"), body.index("## Commits & Changes"))
        self.assertLess(body.index("## Commits & Changes"), body.index("## Verification"))

    def test_a_commit_that_does_not_follow_the_pattern_is_kept_as_it_is(self):
        self.task()
        body = shuttle.hook_pr(self.pr_ctx("a1b2c3d fix the thing"))["body"]
        self.assertIn("### 1. fix the thing (a1b2c3d)", body)

    def test_no_commit_yet(self):
        self.task()
        self.assertIn("(no commit yet)", shuttle.hook_pr(self.pr_ctx(""))["body"])

    def test_a_branch_that_is_not_for_one_of_its_tasks_proposes_nothing(self):
        self.assertEqual(shuttle.hook_pr({**self.pr_ctx(""), "ref-addon": "jira"}), {})

    def test_the_answer_stays_inside_the_limits(self):
        self.task(9, "# T\n\n## Description\n\n" + "paragraph " * 500, "t")
        answer = shuttle.hook_pr(
            {**self.pr_ctx("\n".join(f"a{i:06d} [FIX] m: s{i}" for i in range(50))), "ref-id": "9"}
        )
        self.assertLessEqual(len(answer["title"]), 200)
        self.assertLessEqual(len(answer["body"]), 20000)


class Protocol(Base):
    def test_the_hooks_are_called_through_the_launcher_with_json(self):
        self.task()
        env = dict(os.environ, PATH="/usr/bin:/bin")
        out = subprocess.run(
            [str(LAUNCHER), "hook", "start"], input=json.dumps(self.ctx), capture_output=True, text=True, env=env
        )  # noqa: S603
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["reference"]["id"], "15607")

    def test_a_problem_is_a_message_and_a_failure_not_a_traceback(self):
        self.ctx["args"]["task"] = "404"
        env = dict(os.environ, PATH="/usr/bin:/bin")
        with mock.patch.dict(os.environ, {"ODOO_TASK_NO_MENU": "1"}):
            out = subprocess.run(
                [str(LAUNCHER), "hook", "start"],
                input=json.dumps(self.ctx),
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )  # noqa: S603
        self.assertEqual(out.returncode, 1)
        self.assertIn("task 404 is not fetched yet", out.stderr)
        self.assertNotIn("Traceback", out.stderr)

    def test_bad_input_is_a_message_too(self):
        command = [str(LAUNCHER), "hook", "start"]
        out = subprocess.run(command, input="not json", capture_output=True, text=True)  # noqa: S603
        self.assertEqual(out.returncode, 1)
        self.assertNotIn("Traceback", out.stderr)

    def test_git_shuttle_accepts_it(self):
        """The contract: `git shuttle addon check` is the referee (set GIT_SHUTTLE to its bin/git-shuttle)."""
        referee = os.environ.get("GIT_SHUTTLE")
        if not referee or not Path(referee).is_file():
            self.skipTest("set GIT_SHUTTLE to the bin/git-shuttle of a copy of git-shuttle that has add-ons")
        self.task()
        env = dict(os.environ, GIT_SHUTTLE_ADDON_PATH=str(ROOT / "bin"), PATH=os.environ.get("PATH", "/usr/bin:/bin"))
        out = subprocess.run(
            [referee, "addon", "check", "odoo-task"],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )  # noqa: S603
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("follows protocol 1", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()


class Tasks(Base):
    def live(self, *items):
        return mock.patch("odoo_task.cli.load_tasks", return_value=list(items))

    def test_your_open_tasks_come_first_and_the_fetched_ones_that_are_not_open_follow(self):
        from odoo_task.fetch import TaskSummary

        self.task()  # 15607 is fetched, and open
        self.task(7, "# [Old] A task fetched before\n\n- **Project:** Old\n- **Stage:** Done\n", "Old")
        with self.live(
            TaskSummary(15607, "[Sales] Keep manual Order Date", "Confort", "Running", "2026-12-01"),
            TaskSummary(99, "Not fetched", "P", "To do"),
        ):
            answer = shuttle.hook_tasks({**self.ctx, "hook": "tasks"})
        by_id = {t["id"]: t for t in answer["tasks"]}
        self.assertEqual(
            [t["id"] for t in answer["tasks"]][:2], ["15607", "99"], "the open tasks of Odoo, in its order"
        )
        self.assertIn("7", by_id, "a task fetched before is offered too")
        self.assertEqual(answer["tasks"][0]["subtitle"], "Running")
        fields = {f["label"]: f["value"] for f in answer["tasks"][0]["fields"]}
        self.assertEqual((fields["Project"], fields["Deadline"], fields["Fetched"]), ("Confort", "2026-12-01", "yes"))
        self.assertEqual({f["label"]: f["value"] for f in by_id["99"]["fields"]}["Fetched"], "no")
        self.assertEqual(answer["note"], "")

    def test_when_odoo_does_not_answer_the_fetched_tasks_are_listed_and_the_reason_is_said(self):
        self.task()
        with mock.patch("odoo_task.cli.load_tasks", side_effect=RuntimeError("No API key: set ODOO_TASK_API_KEY")):
            answer = shuttle.hook_tasks({**self.ctx, "hook": "tasks"})
        self.assertEqual([t["id"] for t in answer["tasks"]], ["15607"])
        self.assertIn("No API key", answer["note"])
        self.assertLessEqual(len(answer["note"]), 300)

    def test_nothing_at_all_is_an_empty_list_not_a_failure(self):
        with mock.patch("odoo_task.cli.load_tasks", side_effect=RuntimeError("down")):
            answer = shuttle.hook_tasks({**self.ctx, "hook": "tasks"})
        self.assertEqual(answer["tasks"], [])

    def test_the_list_is_cut_and_every_text_is_inside_the_limits_of_the_protocol(self):
        from odoo_task.fetch import TaskSummary

        many = [TaskSummary(i, "T" * 400, "P" * 400, "S" * 400, "D" * 400) for i in range(1, 100)]
        with self.live(*many):
            answer = shuttle.hook_tasks({**self.ctx, "hook": "tasks"})
        self.assertLessEqual(len(answer["tasks"]), 60)
        for task in answer["tasks"]:
            self.assertLessEqual(len(task["title"]), 200)
            self.assertLessEqual(len(task["subtitle"]), 200)
            self.assertTrue(all(len(f["value"]) <= 300 for f in task["fields"]))

    def test_the_start_reference_carries_what_is_known_of_the_task(self):
        self.task()
        details = {d["label"]: d["value"] for d in shuttle.hook_start(self.ctx)["reference"]["details"]}
        self.assertEqual(
            details,
            {
                "Project": "Confort et eau",
                "Stage": "Running",
                "Assignees": "Aditya Oryza Mahendra",
                "Tags": "whatsapp request",
            },
        )


class Setup(Base):
    def ctx_for(self, action, values=None):
        return {**self.ctx, "hook": "setup", "action": action, **({"values": values} if values is not None else {})}

    def test_status_shows_what_is_saved_and_never_the_key(self):
        store.save_secret("work", "sekret-key-123")
        out = shuttle.hook_setup(self.ctx_for("status"))
        fields = {f["key"]: f for f in out["fields"]}
        self.assertEqual(
            (fields["url"]["value"], fields["db"]["value"], fields["user"]["value"]), ("https://odoo.example", "d", "u")
        )
        self.assertTrue(fields["api_key"]["set"])
        self.assertNotIn("sekret-key-123", json.dumps(out))
        self.assertTrue(out["ready"])

    def test_without_a_key_it_is_not_ready(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("ODOO_TASK_API_KEY", None)
            out = shuttle.hook_setup(self.ctx_for("status"))
        self.assertFalse(out["ready"])
        self.assertFalse({f["key"]: f for f in out["fields"]}["api_key"]["set"])

    def test_a_key_that_does_not_connect_is_not_saved(self):
        from odoo_task.client import OdooError

        with mock.patch("odoo_task.client.OdooClient.connect", side_effect=OdooError("Authentication failed")):
            out = shuttle.hook_setup(self.ctx_for("save", {"api_key": "bad-key-999"}))
        self.assertFalse(out["ok"])
        self.assertIn("Nothing was saved", out["message"])
        self.assertNotIn("bad-key-999", out["message"])
        self.assertFalse(store.has_saved_secret("work"))

    def test_a_key_that_connects_is_saved_privately_and_the_profile_is_changed(self):
        with mock.patch("odoo_task.client.OdooClient.connect", return_value=7):
            out = shuttle.hook_setup(
                self.ctx_for("save", {"api_key": "good-key-123", "db": "other", "url": "odoo.example.org"})
            )
        self.assertTrue(out["ok"], out)
        self.assertEqual(store.read_secret("work"), "good-key-123")
        self.assertEqual(store._secret_path("work").stat().st_mode & 0o777, 0o600)
        profile = store.load_profile("work")
        self.assertEqual((profile.db, profile.url, profile.user), ("other", "https://odoo.example.org", "u"))
        self.assertNotIn("good-key-123", json.dumps(out))

    def test_an_empty_value_keeps_what_is_saved(self):
        store.save_secret("work", "kept-key-123")
        with mock.patch("odoo_task.client.OdooClient.connect", return_value=7):
            out = shuttle.hook_setup(self.ctx_for("save", {"url": "", "api_key": ""}))
        self.assertTrue(out["ok"], out)
        self.assertEqual(store.read_secret("work"), "kept-key-123")
        self.assertEqual(store.load_profile("work").url, "https://odoo.example")

    def test_a_url_that_is_not_http_is_refused(self):
        out = shuttle.hook_setup(self.ctx_for("save", {"url": "javascript:alert(1)"}))
        self.assertFalse(out["ok"])

    def test_a_first_connection_is_made_from_nothing(self):
        for name in store.list_profiles():
            (store.config_home() / "profiles" / f"{name}.json").unlink()
        with mock.patch("odoo_task.client.OdooClient.connect", return_value=7):
            out = shuttle.hook_setup(
                self.ctx_for(
                    "save", {"url": "https://new.example", "db": "d", "user": "me", "api_key": "first-key-123"}
                )
            )
        self.assertTrue(out["ok"], out)
        self.assertEqual(store.default_profile_name(), "default")


class TasksAll(Base):
    def test_closed_tasks_are_asked_for_only_when_the_user_wants_them(self):
        with mock.patch("odoo_task.cli.load_tasks", return_value=[]) as load:
            shuttle.hook_tasks({**self.ctx, "hook": "tasks", "args": {}})
            shuttle.hook_tasks({**self.ctx, "hook": "tasks", "args": {"all": "1"}})
        self.assertEqual([c.args[2] for c in load.call_args_list], [False, True])


class BranchText(unittest.TestCase):
    def test_quotes_and_signs_of_a_title_are_dropped_from_the_proposed_name(self):
        self.assertEqual(
            shuttle.branch_text('Copy "Export to Cigolog" to Accounting ($5?)'),
            "Copy Export to Cigolog to Accounting ( 5 )",
        )
        self.assertEqual(shuttle.branch_text("Keep manual Order Date"), "Keep manual Order Date")


class ReportHook(Base):
    def ctx_for(self, action):
        pr = {"url": "https://github.example/a/b/pull/1", "title": "T", "base": "main"}
        return {
            **self.ctx,
            "hook": "report",
            "action": action,
            "ref_id": "15493",
            "branch": "feature/x",
            "pr": pr,
            "commits": [{"sha": "b" * 40, "subject": "s", "url": "https://github.example/a/b/commit/" + "b" * 40}],
        }

    def fake(self, value=""):
        from tests.unit.test_report import Fake

        return Fake(value)

    def test_preview_says_what_will_be_added_and_writes_nothing(self):
        fake = self.fake("<p>PM text</p>")
        with mock.patch("odoo_task.cli.connect", return_value=fake), mock.patch("odoo_task.cli.resolve_profile"):
            out = shuttle.hook_report(self.ctx_for("preview"))
        self.assertTrue(out["ok"])
        self.assertIn("the text is kept", out["message"])
        self.assertIn("https://github.example/a/b/pull/1", out["text"])
        self.assertEqual(fake.writes, [])

    def test_post_adds_after_the_old_text(self):
        fake = self.fake("<p>PM text</p>")
        with mock.patch("odoo_task.cli.connect", return_value=fake), mock.patch("odoo_task.cli.resolve_profile"):
            out = shuttle.hook_report(self.ctx_for("post"))
        self.assertTrue(out["ok"], out)
        self.assertTrue(fake.value.startswith("<p>PM text</p>"))

    def test_a_problem_is_an_answer_not_a_crash(self):
        from odoo_task.client import OdooError

        with (
            mock.patch("odoo_task.cli.connect", side_effect=OdooError("Authentication failed")),
            mock.patch("odoo_task.cli.resolve_profile"),
        ):
            out = shuttle.hook_report(self.ctx_for("post"))
        self.assertEqual((out["ok"], out["message"]), (False, "Authentication failed"))

    def test_a_field_without_x_is_written_only_when_it_is_named_twice(self):
        git(self.repo, "config", "shuttle.odoo-task.report-field", "report_details")
        fake = self.fake()
        fake.fields_get = lambda model, attributes=None: {
            "report_details": {"type": "html", "string": "Report Details"}
        }
        with mock.patch("odoo_task.cli.connect", return_value=fake), mock.patch("odoo_task.cli.resolve_profile"):
            refused = shuttle.hook_report(self.ctx_for("post"))
            git(self.repo, "config", "shuttle.odoo-task.report-field-allow", "report_details")
            done = shuttle.hook_report(self.ctx_for("post"))
        self.assertFalse(refused["ok"])
        self.assertIn("report-field-allow", refused["message"])
        self.assertTrue(done["ok"], done)

    def test_the_field_can_be_chosen_per_repository_but_only_a_custom_one(self):
        git(self.repo, "config", "shuttle.odoo-task.report-field", "name")
        with mock.patch("odoo_task.cli.connect", return_value=self.fake()), mock.patch("odoo_task.cli.resolve_profile"):
            out = shuttle.hook_report(self.ctx_for("post"))
        self.assertFalse(out["ok"])
        self.assertIn("custom field", out["message"])


class PullRequestImages(Base):
    def test_an_image_that_is_a_local_file_is_not_in_the_description_and_the_next_paragraph_is(self):
        self.task(
            text=TASK_MD.replace(
                "When a quotation is confirmed", "![image](img_att_1.png)\n\nWhen a quotation is confirmed"
            )
        )
        ctx = {**self.ctx, "hook": "pr", "ref-addon": "odoo-task", "ref-id": "15607", "commits": ""}
        body = shuttle.hook_pr(ctx)["body"]
        self.assertNotIn("img_att_1.png", body)
        self.assertIn("When a quotation is confirmed", body)


class StatusRefresh(Base):
    def ctx_for(self, refresh=False):
        args = {"refresh": "1"} if refresh else {}
        return {**self.ctx, "hook": "status", "ref-addon": "odoo-task", "ref-id": "15607", "args": args}

    def card(self, ctx):
        return shuttle.hook_status(ctx)["cards"][0]

    def test_a_look_at_the_card_does_not_fetch(self):
        self.task()
        with mock.patch.object(shuttle, "fetch_missing") as fetch:
            card = self.card(self.ctx_for())
        fetch.assert_not_called()
        self.assertEqual([f["label"] for f in card["fields"] if f["label"] in ("Fetched", "Refresh")], ["Fetched"])

    def test_a_refresh_fetches_again_with_the_latest_messages_and_says_what_changed(self):
        folder = self.task()

        def fetch(task_id, ctx, messages=0, timeout=0, attachments=False):
            (folder / "task.md").write_text(
                TASK_MD + "\n## Latest messages\n\n**Sam**, 2026-10-26\n\nThe client wrote back.\n", encoding="utf-8"
            )

        with mock.patch.object(shuttle, "fetch_missing", side_effect=fetch) as fetched:
            card = self.card(self.ctx_for(refresh=True))
        fetched.assert_called_once()
        self.assertEqual(fetched.call_args.kwargs["messages"], shuttle.REFRESH_MESSAGES)
        fields = {f["label"]: f["value"] for f in card["fields"]}
        self.assertEqual(fields["Refresh"], "the task changed since the last fetch")
        self.assertIn("The client wrote back.", card["text"])
        self.assertIn("Latest messages", card["text"])
        self.assertNotIn("**", card["text"])

    def test_a_refresh_that_brings_nothing_new_says_so(self):
        self.task()
        with mock.patch.object(shuttle, "fetch_missing"):
            card = self.card(self.ctx_for(refresh=True))
        self.assertEqual({f["label"]: f["value"] for f in card["fields"]}["Refresh"], "no change since the last fetch")

    def test_a_refresh_that_fails_keeps_the_card_and_says_why(self):
        self.task()
        with mock.patch.object(shuttle, "fetch_missing", side_effect=shuttle.Problem("Odoo did not answer")):
            card = self.card(self.ctx_for(refresh=True))
        self.assertIn("Odoo did not answer", {f["label"]: f["value"] for f in card["fields"]}["Refresh"])
        self.assertTrue(card["title"])

    def test_an_empty_description_says_so_instead_of_showing_a_marker(self):
        self.task(text=TASK_MD.split("## Description")[0] + "## Description\n\n_(empty)_\n")
        card = self.card(self.ctx_for())
        self.assertEqual(card["text"], "(no description in Odoo)")

    def test_a_local_image_is_not_in_the_card_and_a_long_description_is_kept_whole(self):
        long_text = "word " * 300
        self.task(
            text=TASK_MD.split("## Description")[0] + f"## Description\n\n![image](img_att_1.png)\n\n{long_text}\n"
        )
        card = self.card(self.ctx_for())
        self.assertNotIn("img_att_1.png", card["text"])
        self.assertGreater(len(card["text"]), 1000)
        self.assertLessEqual(len(card["text"]), 5000)


class FetchMissing(Base):
    def argv_of(self, **kwargs):
        with mock.patch.object(shuttle.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            shuttle.fetch_missing(15607, self.ctx, **kwargs)
        return run.call_args.args[0]

    def test_the_first_fetch_lists_the_attachments_and_does_not_download_them(self):
        argv = self.argv_of()
        self.assertIn("--no-attachments", argv)
        self.assertNotIn("--attachments", argv)

    def test_a_refresh_downloads_the_files_and_the_images_and_brings_the_messages(self):
        argv = self.argv_of(messages=10, attachments=True)
        self.assertIn("--attachments", argv)
        self.assertEqual(argv[argv.index("--messages") + 1], "10")

    def test_the_card_names_the_files_and_the_folder(self):
        folder = self.task()
        (folder / "attachments").mkdir()
        (folder / "attachments" / "img_att_1.png").write_bytes(b"x")
        (folder / "attachments" / "img_att_2.png").write_bytes(b"x")
        ctx = {**self.ctx, "hook": "status", "ref-addon": "odoo-task", "ref-id": "15607"}
        fields = {f["label"]: f["value"] for f in shuttle.hook_status(ctx)["cards"][0]["fields"]}
        self.assertEqual(fields["Files"], "2 saved: img_att_1.png, img_att_2.png")
        self.assertEqual(fields["Folder"], str(folder))

    def test_files_that_are_listed_but_not_downloaded_say_how_to_get_them(self):
        self.task()  # TASK_MD lists one attachment and the folder has none
        ctx = {**self.ctx, "hook": "status", "ref-addon": "odoo-task", "ref-id": "15607"}
        fields = {f["label"]: f["value"] for f in shuttle.hook_status(ctx)["cards"][0]["fields"]}
        self.assertIn("press Refresh", fields["Files"])


class ReadableText(unittest.TestCase):
    def test_a_markdown_link_is_read_as_text_with_its_address(self):
        url = "https://preaucess.net/odoo/all-tasks/70934/sale.order/18347"
        self.assertEqual(shuttle._readable(f"Context: [{url}]({url}) on order"), f"Context: {url} on order")
        self.assertEqual(
            shuttle._readable("see [the order](https://a.example/o/1)"), "see the order (https://a.example/o/1)"
        )
        self.assertEqual(
            shuttle._readable("a [x](javascript:alert(1)) b"), "a [x](javascript:alert(1)) b", "only http and https"
        )
