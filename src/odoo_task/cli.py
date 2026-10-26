"""Command line: odoo-task [menu] | fetch | tasks | check | login | profiles | update | version."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from odoo_task import __version__, clipboard, menu, opener, settings, store
from odoo_task.client import OdooClient, OdooError, normalize_url
from odoo_task.fetch import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    ExtraField,
    FetchResult,
    TaskFetcher,
    TaskSummary,
    render_prompt,
)
from odoo_task.listing import format_tasks
from odoo_task.selection import parse_selection
from odoo_task.taskref import parse_task_ref
from odoo_task.update import run_update

PROG = "odoo-task"


def say(text: str = "") -> None:
    print(text, file=sys.stderr)


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def ask(question: str, default: str = "") -> str:
    """Ask in a terminal. Without one (a script, a test) the default is used and nothing waits for input."""
    if not interactive():
        return default
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"  {question}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def ask_yes(question: str, default: bool) -> bool:
    answer = ask(f"{question} [{'Y/n' if default else 'y/N'}]").lower()
    return default if not answer else answer.startswith("y")


# Connecting ----------------------------------------------------------------------------------------------------------


def resolve_profile(name: str | None) -> store.Profile:
    chosen = name or store.default_profile_name()
    if not chosen:
        raise FileNotFoundError("No profile yet. Run:  odoo-task login")
    return store.load_profile(chosen)


def secret_for(profile: store.Profile) -> str:
    found = store.read_secret(profile.name)
    if found:
        return found
    if not interactive():
        raise OdooError(f"No API key: set {store.ENV_SECRET}, or run in a terminal to be asked for it.")
    return getpass.getpass(f"  API key or password for {profile.user} on {profile.url} (hidden): ")


def connect(profile: store.Profile) -> OdooClient:
    client = OdooClient(profile.url, profile.db, profile.user, secret_for(profile))
    client.connect()
    return client


# Commands ------------------------------------------------------------------------------------------------------------


def fetch_refs(args: argparse.Namespace) -> list[int]:
    """The task numbers asked for, without repeats. Everything is parsed before any network call."""
    refs = [parse_task_ref(text) for text in (args.refs or [])]
    if not refs and not args.newest:
        if not interactive():
            raise ValueError("Give a task number or URL, or --newest.")
        refs = [parse_task_ref(ask("Task number or URL"))]
    return list(dict.fromkeys(refs))


def write_prompt(result: FetchResult, template_file: str | None) -> Path:
    path = Path(template_file).expanduser() if template_file else store.config_home() / "prompt.md"
    template = path.read_text(encoding="utf-8") if path.is_file() else None
    text = render_prompt(result.task_id, result.title, result.markdown.read_text(encoding="utf-8"), template)
    prompt_path = result.directory / "prompt.md"
    prompt_path.write_text(text, encoding="utf-8")
    result.prompt = prompt_path
    return prompt_path


def do_fetch(args: argparse.Namespace) -> tuple[list[FetchResult], list[tuple[int, str]]]:
    """Fetch the tasks the arguments name. Returns (results, failures); one failing task does not stop the others."""
    profile = resolve_profile(args.profile)
    ids = fetch_refs(args)
    if args.copy and len(ids) + (1 if args.newest else 0) > 1:
        raise ValueError("--copy works with one task at a time")
    # flag > profile > built-in default
    attachments = profile.attachments if args.attachments is None else args.attachments
    messages = profile.messages if args.messages is None else args.messages
    want_prompt = args.copy or (profile.prompt if args.prompt is None else args.prompt)
    client = connect(profile)
    fetcher = TaskFetcher(client)

    if args.newest:
        newest = fetcher.newest_assigned_task_id(closed_stages=profile.closed_stages)
        if newest is None:
            raise OdooError("No open task is assigned to you.")
        say(f"Newest open task assigned to you: #{newest}")
        ids = list(dict.fromkeys([newest, *ids]))

    extra = [ExtraField.parse(text) for text in [*profile.extra_fields, *(args.field or [])]]
    out_root = Path(args.out).expanduser() if args.out else profile.output_path()
    results: list[FetchResult] = []
    failures: list[tuple[int, str]] = []
    for task_id in ids:
        try:
            result = fetcher.fetch(
                task_id,
                out_root,
                extra_fields=extra,
                messages=max(messages, 0),
                attachments=attachments,
                base_url=profile.url,
            )
        except OdooError as exc:
            failures.append((task_id, str(exc)))
            say(f"ERROR #{task_id}: {exc}")
            continue
        for name in result.skipped_fields:
            say(f"WARN  field '{name}' does not exist on this Odoo's tasks: skipped")
        say(f"OK    #{result.task_id} {result.title}")
        say(f"      folder    {result.directory}")
        say(f"      markdown  {result.markdown}")
        if result.images:
            say(f"      images    {len(result.images)} saved")
        if want_prompt:
            say(f"      prompt    {write_prompt(result, args.prompt_template)}")
        if args.copy and result.prompt:
            copy_prompt(result)
        results.append(result)
    return results, failures


def copy_prompt(result: FetchResult) -> bool:
    if result.prompt is None:
        return False
    if clipboard.copy(result.prompt.read_text(encoding="utf-8")):
        say("      copied    the prompt is on the clipboard")
        return True
    say(f"WARN  no clipboard program found here; the prompt is in {result.prompt}")
    return False


def cmd_fetch(args: argparse.Namespace) -> int:
    results, failures = do_fetch(args)
    for result in results:
        print(result.markdown)  # stdout: the paths, so a script can use them
    return 1 if failures else 0


def load_tasks(
    profile_name: str | None, limit: int, include_closed: bool, extra_closed_stages: Sequence[str] = ()
) -> list[TaskSummary]:
    profile = resolve_profile(profile_name)
    closed = [*profile.closed_stages, *extra_closed_stages]
    return TaskFetcher(connect(profile)).my_tasks(limit=limit, include_closed=include_closed, closed_stages=closed)


def open_rule_note(extra: Sequence[str], profile_name: str | None) -> str:
    stages = [*resolve_profile(profile_name).closed_stages, *extra]
    named = f", nor in stage {', '.join(stages)}" if stages else ""
    return f"Open = state not done or cancelled, stage not folded{named}. Use --all to see everything."


def cmd_tasks(args: argparse.Namespace) -> int:
    if not 1 <= args.limit <= MAX_LIST_LIMIT:
        raise ValueError(f"--limit must be between 1 and {MAX_LIST_LIMIT}")
    extra = args.exclude_stage or []
    tasks = load_tasks(args.profile, args.limit, args.all, extra)
    if args.ids:
        for task in tasks:
            print(task.id)  # stdout only: odoo-task fetch $(odoo-task tasks --ids)
        return 0
    if not tasks:
        say(
            "No task assigned to you."
            if args.all
            else "No open task assigned to you (use --all to include closed ones)."
        )
        return 0
    for line in format_tasks(tasks):
        print(line)
    if not args.all:
        say(open_rule_note(extra, args.profile))
    return 0


def cmd_fields(args: argparse.Namespace) -> int:
    """The fields of a task (read-only): the custom ones (x_...), or those that match every word given."""
    client = connect(resolve_profile(args.profile))
    words = [w.lower() for w in args.words]
    rows = []
    for name, info in sorted(client.fields_get("project.task", ["string", "type"]).items()):
        label = str(info.get("string", ""))
        if words:
            if all(w in f"{name} {label}".lower() for w in words):
                rows.append((name, str(info.get("type", "")), label))
        elif name.startswith("x_"):
            rows.append((name, str(info.get("type", "")), label))
    if not rows:
        say("No field matches." if words else "No custom field (x_...) on a task.")
        return 0
    for name, kind, label in rows:
        print(f"{name:42} {kind:10} {label}")
    say(
        "git-shuttle writes only to a custom text or html field (x_...): git config shuttle.odoo-task.report-field NAME"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    profile = resolve_profile(args.profile)
    client = OdooClient(profile.url, profile.db, profile.user, secret_for(profile))
    info = client.version()
    say(f"OK    server reachable: Odoo {info.get('server_version', '?')}")
    uid = client.connect()
    say(f"OK    logged in as {profile.user} (user id {uid}) on database '{profile.db}'")
    say("      odoo-task only reads: it cannot create, change or delete anything in Odoo.")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    say("odoo-task login: saves the connection settings (never the key, unless you ask).")
    name = args.profile or ask("Profile name", "default")
    url = args.url or ask("Odoo URL (https://...)", "")
    db = args.db or ask("Database", "")
    user = args.user or ask("Login (e-mail or user name)", "")
    out = args.out or ask("Folder for fetched tasks", "~/odoo-tasks")
    profile = store.Profile(name=name, url=normalize_url(url), db=db, user=user, output_dir=out)
    if not (db and user):
        raise ValueError("The database and the login are required.")
    path = store.save_profile(profile)
    say(f"OK    saved {path}")
    if len(store.list_profiles()) == 1:
        store.set_default_profile(name)

    if interactive() and ask_yes("Test the connection now?", True):
        secret = store.read_secret(name) or getpass.getpass("  API key or password (hidden): ")
        client = OdooClient(profile.url, profile.db, profile.user, secret)
        client.connect()
        say("OK    connection works")
        if not store.has_saved_secret(name) and not os.environ.get(store.ENV_SECRET):
            say("      The key is NOT stored by default: you will be asked for it, or set " + store.ENV_SECRET + ".")
            if ask_yes("Save the key in a file only you can read (mode 600)?", False):
                saved = store.save_secret(name, secret)
                say(f"OK    key saved in {saved} (delete it with: odoo-task profiles --forget-key {name})")
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    if args.forget_key:
        say("OK    saved key removed" if store.delete_secret(args.forget_key) else "No saved key for that profile.")
        return 0
    edits = args.set or args.extra_field or args.remove_extra_field
    if edits:
        profile = resolve_profile(args.profile)
        done = settings.apply_settings(profile, args.set or [])
        for text in args.extra_field or []:
            done.append(f"extra field {settings.add_extra_field(profile, text)}")
        for name in args.remove_extra_field or []:
            done.append(
                f"extra field {name} " + ("removed" if settings.remove_extra_field(profile, name) else "was not set")
            )
        store.save_profile(profile)
        say(f"OK    '{profile.name}': " + ", ".join(done))
        return 0
    if args.show:
        for line in settings.describe(resolve_profile(args.profile)):
            say(line)
        return 0
    if args.closed_stages is not None:
        profile = resolve_profile(args.profile)
        profile.closed_stages = [name.strip() for name in args.closed_stages.split(",") if name.strip()]
        store.save_profile(profile)
        shown = ", ".join(profile.closed_stages) or "none"
        say(f"OK    stages counted as closed in '{profile.name}': {shown}")
        return 0
    if args.default:
        store.set_default_profile(args.default)
        say(f"OK    default profile: {args.default}")
        return 0
    names = store.list_profiles()
    if not names:
        say("No profile yet. Run:  odoo-task login")
        return 0
    current = store.default_profile_name()
    say(f"{'PROFILE':<20} {'LOGIN @ URL':<50} KEY")
    for name in names:
        p = store.load_profile(name)
        key = "saved file" if store.has_saved_secret(name) else "asked / env"
        say(f"{name + (' *' if name == current else ''):<20} {p.user + ' @ ' + p.url:<50} {key}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    return run_update(check_only=args.check)


# Menu ----------------------------------------------------------------------------------------------------------------


def _guarded(action: Callable[[], int | None]) -> int:
    """Run a menu action; an error is reported like on the command line and does not end the menu."""
    try:
        return int(action() or 0)
    except KeyboardInterrupt:
        say("\ninterrupted")
        return 130
    except (OdooError, ValueError, OSError) as exc:
        say(f"{PROG}: {exc}")
        return 1


def ask_fetch_options(task_count: int) -> list[str]:
    """Ask where to save and what else to fetch (the profile's preferences are the defaults, so Enter keeps them)."""
    try:
        profile = resolve_profile(None)
    except (FileNotFoundError, ValueError):
        profile = None
    default_out = str(profile.output_dir) if profile else "~/odoo-tasks"
    flags: list[str] = []
    out = ask("Save in folder (Enter = the default)", default_out)
    if out and out != default_out:
        flags += ["--out", out]
    flags.append(
        "--attachments"
        if ask_yes("Download the attachments too?", bool(profile and profile.attachments))
        else "--no-attachments"
    )
    write_prompt_file = ask_yes("Also write prompt.md for an AI assistant?", bool(profile and profile.prompt))
    flags.append("--prompt" if write_prompt_file else "--no-prompt")
    if write_prompt_file and task_count == 1 and ask_yes("Copy the prompt to the clipboard?", False):
        flags.append("--copy")
    default_messages = str(profile.messages) if profile else "0"
    messages = ask("Latest chatter messages to include (0 = none)", default_messages)
    flags += ["--messages", messages if messages.isdigit() else default_messages]
    return flags


def pick_from_my_tasks() -> tuple[int, list[int]]:
    """Show the open tasks assigned to the user and let them choose. Returns (exit code, task numbers)."""
    chosen: list[int] = []

    def choose() -> None:
        tasks = load_tasks(None, DEFAULT_LIST_LIMIT, False)
        if not tasks:
            say("No open task assigned to you.")
            return
        for line in format_tasks(tasks, numbered=True):
            say(line)
        answer = ask("Which ones? (e.g. 1,3 or 2-4; Enter = none)")
        if answer:
            chosen.extend(tasks[position - 1].id for position in parse_selection(answer, len(tasks)))

    return _guarded(choose), chosen


def menu_fetch(mode: str) -> int:
    """mode: "ref" (type a number or URL), "newest", or "pick" (choose from my open tasks)."""
    argv = ["fetch"]
    if mode == "newest":
        argv.append("--newest")
    elif mode == "pick":
        code, ids = pick_from_my_tasks()
        if code != 0 or not ids:
            return code
        argv += [str(task_id) for task_id in ids]
    else:
        ref = ask("Task number or URL")
        if not ref:
            return 0
        argv.append(ref)
    argv += ask_fetch_options(task_count=len(argv) - 1 if mode != "newest" else 1)

    args = build_parser().parse_args(argv)
    outcome: list[tuple[list[FetchResult], list[tuple[int, str]]]] = []
    code = _guarded(lambda: outcome.append(do_fetch(args)))
    if code == 0 and outcome:
        results, failures = outcome[0]
        if results:
            offer_to_open(results)
        code = 1 if failures else 0
    return code


def offer_to_open(results: list[FetchResult]) -> None:
    """One last choice (open the file, the folder, copy the prompt), then the program ends: no loop."""
    single = results[0] if len(results) == 1 else None
    folder = single.directory if single else results[0].directory.parent
    title = f"#{single.task_id} saved" if single else f"{len(results)} tasks saved"
    items: list[tuple[str, str]] = []
    if single:
        items.append(("file", "Open task.md"))
    items.append(("folder", "Open the folder"))
    if single and single.prompt:
        items.append(("copy", "Copy prompt.md to the clipboard"))
    items.append(("done", "Done"))
    details = [str(folder)]
    if single:
        details.append(f"{len(single.images)} image(s) saved")
    if single and single.prompt:
        details.append("prompt.md written")
    choice = menu.choose(title, "\n".join(details), items)
    if choice in (None, "done"):
        return
    if choice == "copy" and single:
        copy_prompt(single)
        return
    path, is_folder = (single.markdown, False) if choice == "file" and single else (folder, True)
    if not opener.open_path(path, folder=is_folder):
        say(f"Nothing could open it here. The path is:  {path}")


def run_menu() -> int:
    """Choose one action, run it, and end with its exit code (the text stays on the terminal)."""
    items = [
        ("ref", "Fetch a task (number or URL)"),
        ("pick", "Pick from my open tasks"),
        ("newest", "Fetch my newest open task"),
        ("login", "Add or change a connection (login)"),
        ("check", "Check the connection"),
        ("profiles", "Show the saved connections"),
        ("update", "Update odoo-task"),
    ]
    choice = menu.choose(f"{PROG} {__version__}", "Fetch an Odoo task to a local Markdown folder. Read-only.", items)
    if choice is None:
        return 0
    if choice in ("ref", "pick", "newest"):
        return menu_fetch(choice)
    return main([choice])


# Entry ---------------------------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Fetch an Odoo task (description, images, extra fields) to a local Markdown folder. Read-only.",
        epilog="With no command in a terminal, a menu opens.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    sub = parser.add_subparsers(dest="command")

    fetch = sub.add_parser("fetch", help="fetch a task by number or Odoo URL")
    fetch.add_argument("refs", nargs="*", metavar="REF", help="task numbers, #numbers or Odoo task URLs (one or more)")
    fetch.add_argument("--newest", action="store_true", help="the newest open task assigned to you")
    fetch.add_argument("--profile", help="saved connection to use (default: the default profile)")
    fetch.add_argument("--out", help="folder for the result (default: the profile's folder)")
    fetch.add_argument(
        "--field", action="append", metavar="NAME[:TITLE]", help="an extra task field to include (repeatable)"
    )
    fetch.add_argument(
        "--messages",
        type=int,
        default=None,
        metavar="N",
        help="include the last N chatter messages (default: the profile's)",
    )
    fetch.add_argument(
        "--attachments",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="download the task attachments (they are listed either way); --no-attachments overrides the profile",
    )
    fetch.add_argument(
        "--prompt",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="also write prompt.md for a coding assistant; --no-prompt overrides the profile",
    )
    fetch.add_argument(
        "--copy", action="store_true", help="copy the prompt to the clipboard (one task; implies --prompt)"
    )
    fetch.add_argument(
        "--prompt-template",
        metavar="FILE",
        help="prompt template (placeholders {task_id} {title} {date} {task_content})",
    )
    fetch.set_defaults(func=cmd_fetch)

    tasks = sub.add_parser("tasks", help="list the open tasks assigned to you")
    tasks.add_argument("--all", action="store_true", help="include closed (done, cancelled) tasks")
    tasks.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help=f"how many (default {DEFAULT_LIST_LIMIT})")
    tasks.add_argument("--ids", action="store_true", help="print only the numbers, for a script")
    tasks.add_argument(
        "--exclude-stage", action="append", metavar="NAME", help="also hide tasks in this stage, e.g. Done (repeatable)"
    )
    tasks.add_argument("--profile", help="saved connection to use")
    tasks.set_defaults(func=cmd_tasks)

    fields = sub.add_parser(
        "fields", help="list the fields of a task: the custom ones, or those that match the words (read-only)"
    )
    fields.add_argument("words", nargs="*", help="words that the name or the label must hold, e.g. customer report")
    fields.add_argument("--profile")
    fields.set_defaults(func=cmd_fields)

    check = sub.add_parser("check", help="test the connection (read-only)")
    check.add_argument("--profile")
    check.set_defaults(func=cmd_check)

    login = sub.add_parser("login", help="save a connection (URL, database, login)")
    login.add_argument("--profile", help="name of the connection")
    login.add_argument("--url")
    login.add_argument("--db")
    login.add_argument("--user")
    login.add_argument("--out", help="folder for fetched tasks")
    login.set_defaults(func=cmd_login)

    profiles = sub.add_parser("profiles", help="list the saved connections")
    profiles.add_argument("--default", metavar="NAME", help="make NAME the default connection")
    profiles.add_argument("--forget-key", metavar="NAME", help="delete the key file saved for NAME")
    profiles.add_argument(
        "--closed-stages", metavar="NAMES", help='stage names counted as closed in "tasks", comma separated ("" = none)'
    )
    profiles.add_argument(
        "--set",
        nargs="+",
        metavar="KEY=VALUE",
        help=f"save preferences in the profile; keys: {', '.join(settings.SETTINGS)} (e.g. attachments=yes messages=5)",
    )
    profiles.add_argument(
        "--extra-field", action="append", metavar="NAME[:TITLE]", help="always include this task field"
    )
    profiles.add_argument(
        "--remove-extra-field", action="append", metavar="NAME", help="stop including this task field"
    )
    profiles.add_argument("--show", action="store_true", help="show the settings of a connection (never the key)")
    profiles.add_argument("--profile", help="the connection the options above apply to (default: the default one)")
    profiles.set_defaults(func=cmd_profiles)

    update = sub.add_parser("update", help="install the newest release")
    update.add_argument("--check", action="store_true", help="only say whether a newer release exists")
    update.set_defaults(func=cmd_update)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not args_list:
        if interactive() and os.environ.get("ODOO_TASK_NO_MENU") != "1":
            try:
                return run_menu()
            except KeyboardInterrupt:
                return 130
        parser.print_help(sys.stderr)
        return 0
    args = parser.parse_args(args_list)
    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 0
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        say("\ninterrupted")
        return 130
    except (OdooError, ValueError, OSError) as exc:
        say(f"{PROG}: {exc}")
        return 1
