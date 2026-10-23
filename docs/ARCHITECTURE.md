# Architecture

How `odoo-task` is built, so that you can change it with confidence. For *using* it, see the [README](../README.md).

## Layout

```
bin/odoo-task            Launcher: finds its folder, checks Python, runs `python -m odoo_task`. Nothing else.
src/odoo_task/
├── cli.py               Commands and the menu wiring. The only place that prints and reads the terminal.
├── client.py            Read-only XML-RPC client (allow-list of methods, timeouts, no secret in repr or errors).
├── fetch.py             TaskFetcher (reads a task and writes the folder), render_markdown, render_prompt.
├── html_text.py         Odoo HTML to Markdown (html.parser); removes access tokens from links.
├── listing.py           The text table of a list of tasks.
├── selection.py         "1,3-5" to positions in a list.
├── clipboard.py         Copy text with the program the system offers (stdin, never the command line).
├── opener.py            Open a file or folder with the desktop (VS Code, Explorer from WSL, xdg-open).
├── images.py            Saves the images of a description and rewrites their references.
├── taskref.py           A number or an Odoo URL to a task id; safe folder names.
├── store.py             Profiles and secrets on disk (modes 700 / 600).
├── settings.py          The preferences a profile can keep (`--set key=value`): parsing, validation, the field list.
├── menu.py              whiptail or numbered list.
└── update.py            `odoo-task update` (runs the installer of this copy).
scripts/install.sh       One-line installer and updater (checksum verified); also `install` for a checkout.
scripts/release.sh       Builds a release in a local folder. Publishes nothing.
tests/                   Unit tests; fake_odoo.py is a fake Odoo XML-RPC server on localhost.
```

## Design decisions

| Decision | Why |
|---|---|
| **Read-only client with an allow-list** | The tool is about reading. Enforcing it in one function (`OdooClient.execute`) means no future code path can write by accident, and a test proves it. The only write, `OdooClient.append_custom_field` (an `x_...` field of one task, for the git-shuttle report), is a separate method that `execute` cannot reach. |
| **Standard library only** | Nothing to install, no virtualenv, no supply-chain surface. XML-RPC, `argparse`, `html.parser` are enough. |
| **Profiles hold no secret** | A profile can be copied, committed by mistake or pasted in a chat. The key is read from the environment, an explicit mode-600 file, or a hidden prompt. |
| **Fields are checked with `fields_get`** | Odoo versions and custom modules differ. Asking only for fields that exist lets one profile work everywhere and turns a missing field into a warning. |
| **stdout = the result, stderr = messages** | `path=$(odoo-task fetch 42)` and `odoo-task fetch $(odoo-task tasks --ids)` work in scripts. |
| **"Open" is decided from the Odoo schema** | `fields_get` tells whether `state` or `is_closed` can be searched; nothing is guessed when neither can. |
| **Release = archive + SHA256SUMS + install.sh** | The installer verifies the archive before unpacking and refuses paths that could leave the folder. `update` runs the installer of the copy you have, so the logic exists once. |
| **Fake Odoo in the tests** | The tests run the real client against a local server that records every call, so they check what is actually sent. |

## Preferences and their priority

`settings.SETTINGS` lists the keys a profile may keep (`out`, `attachments`, `prompt`, `messages`), each with its parser. `apply_settings`
checks every item before changing anything, so one bad value changes nothing. At run time `do_fetch` resolves each option as
*flag, then profile, then built-in default*; the flags are tri-state (`--attachments` / `--no-attachments`, default `None`) so that
"not given" can be told from "no". The clipboard is not a setting: it has a visible side effect outside the tool.

## Flow of `tasks` and the menu

```
cli.cmd_tasks / menu "Pick from my open tasks"
  └─ TaskFetcher.my_tasks              domain: user_ids = me, plus closed_domain() unless --all
       ├─ closed_domain()              `state` selection (done / cancel keys) or `is_closed`, only if searchable
       └─ open_domain()                + not in a folded stage, + not in a stage the user calls closed (never hides "no stage")
  └─ format_tasks → table; parse_selection("1,3-5") → task numbers → do_fetch
```

`do_fetch` takes every reference first (a bad one stops before any request), connects once, and fetches the tasks one by one:
a failing task is reported and collected, the others continue, and the exit code is 1 if any failed.

## Flow of `fetch`

```
cli.cmd_fetch
  ├─ resolve_profile / secret_for      profile + key (env, file, prompt)
  ├─ OdooClient.connect                authenticate
  ├─ parse_task_ref | newest           which task
  └─ TaskFetcher.fetch
       ├─ fields_get                   which fields exist
       ├─ read project.task            only those fields
       ├─ localize_images              files next to task.md
       ├─ attachments / messages       optional
       └─ render_markdown → task.md
```

## Releases and updates

A release is three files: `odoo-task-fetch-vX.Y.Z.tar.gz` (with a `RELEASE` file holding the version), `SHA256SUMS` and
`install.sh`. `scripts/release.sh` builds them. The installer unpacks to `~/.local/share/odoo-task/vX.Y.Z/`, points `current`
to it and links the command to `current/bin/odoo-task`. A copy without a `RELEASE` file is a source checkout and is never
updated this way. The installer reads releases from GitHub, or from `ODOO_TASK_RELEASE_BASE` (a folder or URL with a
`latest` file and one folder per tag): that is what the tests use, so they need no network.

## Security invariants

A change must keep all of these true:

1. The client never calls a method outside `READ_ONLY_METHODS`.
2. A secret never appears in an argument list, a log line, a profile, an exception message or `repr()`.
3. Anything that becomes a path (task title, attachment name, task id) is sanitized first.
4. A URL must be `http(s)`; anything else is refused.
5. Nothing waits for input when there is no terminal.

## How to add an option or a field

1. Add the argument in `build_parser` (`cli.py`) and pass it to `TaskFetcher.fetch`.
2. Put the logic in `fetch.py` (or a helper module), not in `cli.py`.
3. Add a test against `tests/fake_odoo.py` (extend the fake data if you need more), and document the option in the README.

## Testing

| Level | What | Command |
|---|---|---|
| Unit | parsing, HTML, images, profiles, client rules, fetch and CLI against the fake Odoo, release/install/update | `make test` |
| Lint | `ruff` | `make lint` |
