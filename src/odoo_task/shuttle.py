"""The add-on of git-shuttle for odoo-task (protocol 1: see docs/addons.md of git-shuttle).

    git-shuttle-odoo-task --shuttle-manifest      what it is and what it asks for
    git-shuttle-odoo-task hook start|pr|status    the context on standard input, one JSON object on standard output
    git-shuttle-odoo-task fetch ...               anything else is odoo-task itself (`git shuttle odoo-task fetch 4821`)

It only reads: the folders that `odoo-task fetch` writes (task.md), and, when the task of `git shuttle start --task N`
is not there yet, it runs `odoo-task fetch N` (which only reads Odoo). It never sees more of git-shuttle than the
context it is given, and git-shuttle checks everything it says; the sizes below are the limits of the protocol, kept
here so that a long title is cut instead of refused.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import __version__, store
from .taskref import parse_task_ref

PROTOCOL = 1
NAME = "odoo-task"
FETCH_TIMEOUT = 15  # seconds: git-shuttle gives a hook 20


class Problem(Exception):
    """Something the user can fix; the message is said as it is."""


def manifest() -> dict:
    return {
        "protocol": PROTOCOL,
        "name": NAME,
        "version": __version__,
        "description": (
            "Starts a branch from an Odoo task and fills the pull request from it "
            "(reads the folders that odoo-task fetch writes)"
        ),
        "hooks": ["start", "pr", "status", "tasks", "setup", "report"],
        "flags": {"start": ["--task"]},
        # only to fetch a task that is not there yet, when the key is not saved by odoo-task itself
        "env": [store.ENV_SECRET],
    }


# --- where the tasks are ----------------------------------------------------------------------------------------------


def _git_config(root: str | None, key: str) -> str:
    try:
        done = subprocess.run(  # noqa: S603  (a fixed command; the key is one of ours)
            ["git", "config", "--get", key],  # noqa: S607 (git, from the PATH, as the user runs it)
            cwd=root or None,
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def profile_name(ctx: dict) -> str | None:
    """The profile of this repository (git config shuttle.odoo-task.profile), else the default profile of odoo-task."""
    chosen = _git_config(ctx.get("repo", {}).get("root"), "shuttle.odoo-task.profile")
    if chosen:
        if chosen not in store.list_profiles():
            raise Problem(
                f"the profile '{chosen}' (git config shuttle.odoo-task.profile) does not exist: odoo-task profiles"
            )
        return chosen
    return store.default_profile_name()


def tasks_folder(ctx: dict) -> Path:
    """The folder of the fetched tasks: git config shuttle.odoo-task.dir, else the folder of the profile."""
    override = _git_config(ctx.get("repo", {}).get("root"), "shuttle.odoo-task.dir")
    if override:
        return Path(override).expanduser()
    name = profile_name(ctx)
    if not name:
        known = store.list_profiles()
        if not known:
            raise Problem("odoo-task has no saved connection: run  odoo-task login")
        raise Problem(
            "odoo-task has several connections and none is the default: odoo-task profiles --default NAME, "
            "or git config shuttle.odoo-task.profile NAME"
        )
    return store.load_profile(name).output_path()


def find_folder(root: Path, task_id: int) -> Path | None:
    """The folder `<id>_<title>` that holds a task.md (the newest, if a title changed and it was fetched again)."""
    if not root.is_dir():
        return None
    found = [p for p in root.glob(f"{int(task_id)}_*") if (p / "task.md").is_file()]
    return max(found, key=lambda p: (p / "task.md").stat().st_mtime) if found else None


def fetch_missing(
    task_id: int, ctx: dict, messages: int = 0, timeout: int = FETCH_TIMEOUT, attachments: bool = False
) -> None:
    """`odoo-task fetch N`, as a program of its own: read-only, and its own error is the message when it cannot.

    With `attachments` the files and the images of the description are downloaded too: that takes longer, so the
    first fetch of a task (a hook has a few seconds) lists them only, and a refresh (it has more time) downloads them.
    """
    argv = [sys.executable, "-m", "odoo_task", "fetch", str(int(task_id))]
    argv.append("--attachments" if attachments else "--no-attachments")
    if messages > 0:
        argv += ["--messages", str(int(messages))]
    name = profile_name(ctx)
    if name:
        argv += ["--profile", name]
    env = dict(
        os.environ,
        ODOO_TASK_NO_MENU="1",
        PYTHONPATH=str(Path(__file__).resolve().parents[1]) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    try:
        # our own interpreter and our own package, with the number of a task (an int): nothing from outside
        done = subprocess.run(  # noqa: S603
            argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env
        )
    except subprocess.TimeoutExpired:
        raise Problem(
            f"task {task_id} is not fetched yet and Odoo did not answer in {timeout} s: odoo-task fetch {task_id}"
        ) from None
    if done.returncode != 0:
        why = " ".join((done.stderr or done.stdout).split())[:200]
        raise Problem(f"task {task_id} is not fetched yet, and the fetch failed ({why}): odoo-task fetch {task_id}")


# --- task.md ---------------------------------------------------------------------------------------------------------


def read_task(folder: Path) -> dict:
    """The parts of task.md that are used: the title, the fields at the top, the description."""
    text = (folder / "task.md").read_text(encoding="utf-8", errors="replace")
    title, fields, description, messages, listed, section = "", {}, [], [], [], ""
    for line in text.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        field = re.match(r"^- \*\*([^:*]+):\*\*\s*(.*)$", line)
        if field and not section:
            fields[field.group(1).strip().lower()] = field.group(2).strip()
        elif section == "description":
            description.append(line)
        elif section == "latest messages":
            messages.append(line)
        elif section == "attachments" and line.startswith("- "):
            listed.append(line[2:].split(" (")[0].strip())
    return {
        "title": title,
        "fields": fields,
        "description": "\n".join(description).strip(),
        "messages": "\n".join(messages).strip(),
        "attachments": listed,
    }


def clean(value: str, limit: int, single_line: bool = True) -> str:
    """Cut to the limit of the protocol; no control character; one line when it must be."""
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value or "")
    if single_line:
        value = " ".join(value.split())
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def branch_text(name: str) -> str:
    """The name proposed for the branch: quotes, $, ? and the like of a title are dropped."""
    return clean(re.sub(r"\s+", " ", re.sub(r"[^\w\[\]() .,:#'&/-]", " ", name)).strip(), 120)


def strip_tag(title: str) -> str:
    """'[Sales] Keep manual Order Date' -> 'Keep manual Order Date': tags at the start are not part of a name."""
    return re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", title or "").strip()


def load(ctx: dict, task_id: int, fetch: bool) -> tuple[Path, dict]:
    root = tasks_folder(ctx)
    folder = find_folder(root, task_id)
    if folder is None and fetch:
        fetch_missing(task_id, ctx)
        folder = find_folder(root, task_id)
    if folder is None:
        raise Problem(f"task {task_id} is not in {root}: odoo-task fetch {task_id}")
    return folder, read_task(folder)


def reference_of(task_id: int, task: dict) -> dict:
    ref = {"id": str(int(task_id)), "title": clean(task["title"], 200)}
    # what is known of the task now (git-shuttle keeps it in the trace of the task, with the date)
    details = [
        {"label": label, "value": clean(task["fields"][key], 300)}
        for key, label in (("project", "Project"), ("stage", "Stage"), ("assignees", "Assignees"), ("tags", "Tags"))
        if task["fields"].get(key)
    ]
    if details:
        ref["details"] = details
    link = task["fields"].get("link", "")
    if re.match(r"^https?://\S{1,500}$", link):
        ref["link"] = link
    return ref


# --- the hooks -------------------------------------------------------------------------------------------------------


def hook_start(ctx: dict) -> dict:
    task_id = parse_task_ref(str(ctx.get("args", {}).get("task", "")))
    folder, task = load(ctx, task_id, fetch=True)
    name = strip_tag(task["title"]) or f"task {task_id}"
    return {
        "branch": branch_text(name),
        "reference": reference_of(task_id, task),
        "note": clean(f"task {task_id}: {task['title']}", 500),
    }


def _ref_id(ctx: dict) -> int | None:
    if ctx.get("ref-addon") not in (None, "", NAME) or not ctx.get("ref-id"):
        return None
    try:
        return int(str(ctx["ref-id"]))
    except ValueError:
        return None


REFRESH_TIMEOUT = (
    40  # a refresh downloads the attachments too: more time than the look at a task that is not fetched yet
)
REFRESH_MESSAGES = 10  # the latest messages of the task that a refresh brings (the chatter is often where the news is)


def _readable(text: str) -> str:
    """What a person reads of a piece of task.md: no local image (a file on this machine), no empty marker."""
    text = re.sub(r"!\[[^\]]*\]\((?!https?://)[^)]*\)", "", text or "")
    return text.replace("_(empty)_", "").replace("**", "").strip()


def _digest(folder: Path | None) -> str:
    try:
        return hashlib.sha256((folder / "task.md").read_bytes()).hexdigest() if folder else ""
    except OSError:
        return ""


def hook_status(ctx: dict) -> dict:
    """The card of the task. `args.refresh` fetches it again from Odoo first (a read) and says whether it changed."""
    task_id = _ref_id(ctx)
    if task_id is None:
        return {"cards": []}
    refresh = (ctx.get("args") or {}).get("refresh") == "1"
    note, before = "", _digest(find_folder(tasks_folder(ctx), task_id))
    if refresh:
        try:
            fetch_missing(task_id, ctx, messages=REFRESH_MESSAGES, timeout=REFRESH_TIMEOUT, attachments=True)
        except Problem as problem:
            note = f"not refreshed: {problem}"
    folder, task = load(ctx, task_id, fetch=False)
    fields = [
        {"label": label, "value": clean(task["fields"][key], 300)}
        for key, label in (
            ("project", "Project"),
            ("assignees", "Assignees"),
            ("tags", "Tags"),
            ("deadline", "Deadline"),
        )
        if task["fields"].get(key)
    ]
    fetched = time.strftime("%Y-%m-%d %H:%M", time.localtime((folder / "task.md").stat().st_mtime))
    fields.append({"label": "Fetched", "value": fetched})
    files = (
        sorted(p.name for p in (folder / "attachments").glob("*") if p.is_file())
        if (folder / "attachments").is_dir()
        else []
    )
    if files:
        shown = ", ".join(files[:4]) + (f" and {len(files) - 4} more" if len(files) > 4 else "")
        fields.append({"label": "Files", "value": clean(f"{len(files)} saved: {shown}", 300)})
    elif task.get("attachments"):
        fields.append({"label": "Files", "value": f"{len(task['attachments'])} listed, not downloaded: press Refresh"})
    fields.append({"label": "Folder", "value": clean(str(folder), 300)})
    if refresh:
        after = _digest(folder)
        what = (
            "the task changed since the last fetch" if before and after != before else "no change since the last fetch"
        )
        fields.append({"label": "Refresh", "value": clean(note or (what if before else "fetched"), 300)})
    description = _readable(task["description"]) or "(no description in Odoo)"
    messages = _readable(task.get("messages", ""))
    card = {
        "title": clean(task["title"] or f"Task {task_id}", 120),
        "subtitle": clean(task["fields"].get("stage", ""), 200),
        "text": clean(description + (f"\n\nLatest messages\n{messages}" if messages else ""), 5000, single_line=False),
        "fields": fields[:12],
    }
    link = reference_of(task_id, task).get("link")
    if link:
        card["link"] = link
    return {"cards": [card]}


def _commit_sections(commits: str) -> list[str]:
    """The commit lines (`sha [TAG] module: summary`) as sections of the description (`### 1. module: summary`)."""
    out = []
    for number, line in enumerate((c for c in commits.splitlines() if c.strip()), 1):
        sha, _, subject = line.strip().partition(" ")
        match = re.match(r"^\[[A-Za-z]+\]\s+([^:]+):\s*(.+)$", subject)
        if match:
            module, summary = match.group(1).strip(), match.group(2).strip()
            out += [f"### {number}. `{module}`: {summary} ({sha})", f"- {summary}", ""]
        else:
            out += [f"### {number}. {subject.strip() or sha} ({sha})", f"- {subject.strip() or sha}", ""]
    return out


def hook_pr(ctx: dict) -> dict:
    task_id = _ref_id(ctx)
    if task_id is None:
        return {}
    folder, task = load(ctx, task_id, fetch=False)
    # an image of the task is a file on this machine (img_att_1.png): it shows nothing in a pull request
    text = re.sub(r"!\[[^\]]*\]\((?!https?://)[^)]*\)", "", task["description"])
    first = next((p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()), "")
    intro = clean(first, 600, single_line=False) or task["title"]
    link = reference_of(task_id, task).get("link")
    lines = ["## Description", intro, ""]
    lines.append(f"Task #{task_id}: {link}" if link else f"Task #{task_id}")
    lines += ["", "## Commits & Changes", ""]
    lines += _commit_sections(ctx.get("commits", "")) or ["(no commit yet)", ""]
    lines += [
        "## Verification",
        f"- Verify: {clean(strip_tag(task['title']), 200)}",
        "- (add the steps that show it works)",
    ]
    return {"title": clean(task["title"], 200), "body": clean("\n".join(lines), 20000, single_line=False)}


LIST_LIMIT = 40


def local_tasks(root: Path) -> list[dict]:
    """The tasks already fetched into the folder (newest first): they can be started from without Odoo."""
    out = []
    if root.is_dir():
        folders = [p for p in root.iterdir() if re.match(r"^\d+_", p.name) and (p / "task.md").is_file()]
        for folder in sorted(folders, key=lambda p: (p / "task.md").stat().st_mtime, reverse=True)[:LIST_LIMIT]:
            task = read_task(folder)
            out.append(
                {
                    "id": folder.name.split("_", 1)[0],
                    "title": clean(task["title"] or folder.name, 200),
                    "fields": task["fields"],
                }
            )
    return out


def hook_tasks(ctx: dict) -> dict:
    """The tasks to choose from: your open tasks of Odoo (all with `args.all`), then the ones fetched before."""
    from .cli import load_tasks  # the same list as `odoo-task tasks`

    root = tasks_folder(ctx)
    fetched = {t["id"]: t for t in local_tasks(root)}
    note, live = "", []
    try:
        live = load_tasks(profile_name(ctx), LIST_LIMIT, (ctx.get("args") or {}).get("all") == "1")
    except Exception as error:  # noqa: BLE001  (any failure of the connection is a reason to show, not a crash)
        note = clean(
            f"Odoo was not asked or did not answer ({error}): these are the tasks that were fetched before.", 300
        )
    tasks, seen = [], set()
    for item in live:
        seen.add(str(item.id))
        fields = [
            {"label": label, "value": clean(value, 300)}
            for label, value in (("Project", item.project), ("Deadline", item.deadline))
            if value
        ]
        fields.append({"label": "Fetched", "value": "yes" if str(item.id) in fetched else "no"})
        tasks.append(
            {"id": str(item.id), "title": clean(item.title, 200), "subtitle": clean(item.stage, 200), "fields": fields}
        )
    for task_id, task in fetched.items():
        if task_id not in seen:
            fields = [
                {"label": label, "value": clean(task["fields"][key], 300)}
                for key, label in (("project", "Project"),)
                if task["fields"].get(key)
            ]
            tasks.append(
                {
                    "id": task_id,
                    "title": task["title"],
                    "subtitle": clean(task["fields"].get("stage", "") or "fetched before", 200),
                    "fields": fields,
                }
            )
    return {"tasks": tasks[: LIST_LIMIT + 20], "note": note}


# --- the connection to Odoo: what the web UI asks for in Set up ----------------------


def _setup_profile(ctx: dict) -> tuple[str, store.Profile | None]:
    name = profile_name(ctx) or "default"
    try:
        return name, store.load_profile(name)
    except (FileNotFoundError, ValueError):
        return name, None


def _field(key: str, kind: str, label: str, value: str, help_text: str = "") -> dict:
    required = key != "output_dir"
    return {"key": key, "kind": kind, "label": label, "value": value, "help": help_text, "required": required}


def hook_setup(ctx: dict) -> dict:
    """`action: status` says what is saved (never the key); `action: save` tests the connection, then saves it
    as `odoo-task login` does."""
    name, profile = _setup_profile(ctx)
    if ctx.get("action") == "save":
        return _setup_save(name, profile, ctx.get("values") or {})
    has_key = bool(os.environ.get(store.ENV_SECRET)) or store.has_saved_secret(name)
    return {
        "ready": bool(profile and has_key),
        "note": clean(f"Profile '{name}' of odoo-task. The key is saved in a file only you can read (mode 600).", 300),
        "fields": [
            _field("url", "url", "Odoo URL", profile.url if profile else "", "for example https://odoo.example.com"),
            _field("db", "text", "Database", profile.db if profile else ""),
            _field("user", "text", "Login", profile.user if profile else "", "your e-mail or user name in Odoo"),
            _field(
                "output_dir", "path", "Folder for the fetched tasks", profile.output_dir if profile else "~/odoo-tasks"
            ),
            {
                **_field(
                    "api_key",
                    "secret",
                    "API key",
                    "",
                    "Odoo: your profile, Account Security, New API Key. Tested before it is saved.",
                ),
                "set": has_key,
            },
        ],
    }


def _setup_save(name: str, profile: store.Profile | None, values: dict) -> dict:
    from .client import OdooClient, OdooError, normalize_url

    def pick(key: str, old: str) -> str:
        return str(values.get(key) or "").strip() or old

    try:
        url = normalize_url(pick("url", profile.url if profile else ""))
    except OdooError as error:
        return {"ok": False, "message": clean(str(error), 300)}
    db, user = pick("db", profile.db if profile else ""), pick("user", profile.user if profile else "")
    if not (db and user):
        return {"ok": False, "message": "The database and the login are required."}
    out = pick("output_dir", profile.output_dir if profile else "~/odoo-tasks")
    typed = str(values.get("api_key") or "").strip()
    try:
        key = typed or store.read_secret(name)
    except PermissionError as error:
        return {"ok": False, "message": clean(str(error), 300)}
    if key:
        try:
            OdooClient(url, db, user, key, timeout=15).connect()
        except OdooError as error:
            return {"ok": False, "message": clean(f"Nothing was saved: {error}", 300)}
    updated = profile or store.Profile(name=name, url=url, db=db, user=user, output_dir=out)
    updated.url, updated.db, updated.user, updated.output_dir = url, db, user, out
    store.save_profile(updated)
    if len(store.list_profiles()) == 1:
        store.set_default_profile(name)
    if typed:
        store.save_secret(name, typed)
    if key:
        return {"ok": True, "message": f"Connected to {url} as {user}. The profile '{name}' is saved."}
    return {"ok": True, "message": f"The profile '{name}' is saved; it has no key yet: add the API key to use it."}


def hook_report(ctx: dict) -> dict:
    """The pull request and the commits, added to the Customer report of the task (only added: what is there is kept).

    `action: preview` reads Odoo and says what would be added; `action: post` adds it. git-shuttle calls it
    only when the user turned it on for the repository, and shows the preview first. The field is git config
    shuttle.odoo-task.report-field (default x_customer_report).
    """
    from . import report
    from .cli import connect, resolve_profile
    from .client import OdooError

    try:
        task_id = int(str(ctx.get("ref_id", "")))
    except ValueError:
        raise Problem("no task number to write to") from None
    field = _git_config(ctx.get("repo", {}).get("root"), "shuttle.odoo-task.report-field") or report.DEFAULT_FIELD
    info = {"branch": ctx.get("branch", ""), "pr": ctx.get("pr") or {}, "commits": ctx.get("commits") or []}
    try:
        client = connect(resolve_profile(profile_name(ctx)))
        if ctx.get("action") == "post":
            message = report.post(client, task_id, field, info)
            return {
                "ok": True,
                "message": clean(message, 300),
                "text": "",
                "field": field,
                "skipped": "Nothing was written" in message,
            }
        done = report.plan(client, task_id, field, info)
    except (OdooError, PermissionError, ValueError, FileNotFoundError) as error:
        return {"ok": False, "message": clean(str(error), 300), "text": "", "field": field, "skipped": False}
    where = (
        "already has this pull request: nothing will be added"
        if done["skip"]
        else "has text: the entry is added after it, the text is kept"
    )
    note = (
        f"{field} ({done['kind']}) {where}"
        if done["old"]
        else f"{field} ({done['kind']}) is empty: the entry is the first text"
    )
    return {
        "ok": True,
        "message": clean(note, 300),
        "text": report.entry_text(info)[:6000],
        "field": field,
        "skipped": done["skip"],
    }


HOOKS = {
    "start": hook_start,
    "pr": hook_pr,
    "status": hook_status,
    "tasks": hook_tasks,
    "setup": hook_setup,
    "report": hook_report,
}


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "--shuttle-manifest":
        print(json.dumps(manifest()))
        return 0
    if len(argv) == 3 and argv[1] == "hook" and argv[2] in HOOKS:
        try:
            ctx = json.loads(sys.stdin.read() or "{}")
            print(json.dumps(HOOKS[argv[2]](ctx), ensure_ascii=False))
            return 0
        except Problem as problem:
            print(str(problem), file=sys.stderr)
            return 1
        except (ValueError, OSError) as error:
            print(f"git-shuttle-odoo-task: {error}", file=sys.stderr)
            return 1
    # not a protocol call: it is odoo-task (git shuttle odoo-task fetch 4821)
    from .cli import main as odoo_task_main

    return odoo_task_main(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
