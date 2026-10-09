# odoo-task-fetch

**Fetch an Odoo task (description, images, extra fields) to a local Markdown folder: read-only, in one command.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A5%203.9-3776ab)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL2%20%7C%20macOS-lightgrey)
![Odoo](https://img.shields.io/badge/tested%20with-Odoo%2018-714B67)

### Install in one line

```bash
curl -fsSL https://github.com/adityaoryza/odoo-task-fetch/releases/latest/download/install.sh | bash
```

Then open a new terminal and run **`odoo-task`**: a menu asks what you want to do. The installer verifies the SHA-256 of
the release and needs no `sudo`; `odoo-task update` keeps it current. To read the script first, or to install another way,
see [Installation](#installation).

> **Windows:** run it in [WSL2](https://learn.microsoft.com/windows/wsl/install) (`wsl --install` once, then the Ubuntu
> terminal). It does not run in Command Prompt or PowerShell.

---

`odoo-task` reads a task from your Odoo (the description, the images inside it, a few useful fields, optionally the latest
chatter messages and attachments) and saves it as a clean Markdown folder. It is made for two things: **working from a task
offline**, and **handing a task to a coding assistant** (it can write a ready-to-paste prompt).

```
$ odoo-task fetch https://odoo.example.com/odoo/project/5/tasks/4821
OK    #4821 Export fails on large invoices
      folder    ~/odoo-tasks/4821_Export_fails_on_large_invoices
      markdown  ~/odoo-tasks/4821_Export_fails_on_large_invoices/task.md
      images    2 saved
```

## Features

- **Read-only, by construction.** The client accepts only read methods; anything else is refused before it is sent. Tests
  prove that a fetch sends nothing but reads.
- **Paste what you have.** A task number, `#4821`, or the URL from your browser; several at once.
- **Pick from your own tasks.** `odoo-task tasks` lists the open tasks assigned to you; the menu lets you choose one or more.
- **Hand it to an assistant.** `--prompt` writes a ready-to-paste prompt, `--copy` puts it on the clipboard.
- **Images included.** Embedded and attached images are saved next to `task.md` and linked from it.
- **Any field you need.** Add custom or standard task fields by name (`--field NAME[:TITLE]`); a field that does not exist
  in your Odoo is skipped with a warning, so the same profile works across databases and versions.
- **No dependencies.** Python 3.9+ and its standard library; nothing to `pip install`.
- **No secret on disk by default.** The key comes from an environment variable or a hidden prompt; saving it in a file
  (mode 600) is an explicit choice.
- **Menu or scripts.** A menu without arguments; plain commands and exit codes for automation.
- **One-line install, self-updating,** with a checksum check.

## Installation

### From a release (recommended)

```bash
curl -fsSL https://github.com/adityaoryza/odoo-task-fetch/releases/latest/download/install.sh | bash
```

The installer downloads the latest release, **checks its SHA-256**, unpacks it under `~/.local/share/odoo-task/` and links
the `odoo-task` command into a folder of your `PATH` (it adds `~/.local/bin` to your bash, zsh, `~/.profile` and fish
configuration if needed, once). Nothing needs `sudo`.

Prefer to read it first?

```bash
curl -fsSLO https://github.com/adityaoryza/odoo-task-fetch/releases/latest/download/install.sh
less install.sh
bash install.sh
```

Options: `--prefix /usr/local` (every user, needs `sudo`), `--version v0.1.0` (a specific release).

### On Windows

Install WSL2 and Ubuntu once (PowerShell as administrator: `wsl --install`, then restart), open the **Ubuntu** app, and
follow *From a release* there.

### Update

```bash
odoo-task update           # install the newest release (checksum verified)
odoo-task update --check   # only say whether one exists
```

### From a source checkout (to contribute)

```bash
git clone https://github.com/adityaoryza/odoo-task-fetch.git
cd odoo-task-fetch
bin/odoo-task --version
make install               # links this checkout as the command
```

## Quick start

**1. Save a connection** (asked once; the key is not stored unless you say so):

```bash
odoo-task login
```

You give the Odoo URL, the database, your login and a folder for the results. At the end you can test the connection.

**2. Fetch a task:**

```bash
odoo-task fetch 4821
odoo-task fetch '#4821'
odoo-task fetch https://odoo.example.com/odoo/project/5/tasks/4821
odoo-task fetch --newest          # the newest open task assigned to you
odoo-task fetch 4821 4830 4902    # several at once
```

**Or choose from your tasks:**

```bash
odoo-task tasks                   # the open tasks assigned to you
odoo-task fetch $(odoo-task tasks --ids --limit 3)
```

**3. Add what you need:**

```bash
odoo-task fetch 4821 --field x_customer_report:"Customer report" --messages 5 --attachments --prompt
```

**Menu:** run `odoo-task` with no arguments. *Pick from my open tasks* shows a numbered list; answer `2`, `1,3` or `2-4`.
The menu does one thing and ends, like any command: you choose an action, it runs, and the text stays on your terminal.
For a fetch it asks where to save (Enter keeps your default folder), whether to download attachments, write the prompt,
copy it to the clipboard and include chatter messages, and then offers one last choice: open `task.md`, open the folder,
copy the prompt, or *Done*.

For a key without typing it each time, set `ODOO_TASK_API_KEY` (Odoo: *My Profile → Account Security → New API Key*).

## What you get

```
~/odoo-tasks/4821_Export_fails_on_large_invoices/
├── task.md          title, fields, description, extra sections, attachments, messages
├── img_b64_1.png    images found in the description
├── img_att_77.png
├── attachments/     only with --attachments
└── prompt.md        only with --prompt
```

`task.md` starts like this:

```markdown
# Export fails on large invoices

- **Project:** Accounting
- **Stage:** In Progress
- **Assignees:** Alex Doe
- **Tags:** bug, export
- **Deadline:** 2026-12-01
- **Link:** https://odoo.example.com/web#id=4821&model=project.task&view_type=form

## Description

The export stops after 500 lines. Steps: ...
```

On success the path of `task.md` is printed on **stdout** and everything else goes to stderr, so a script can do
`path=$(odoo-task fetch 4821)`.

## Commands

| Command | Purpose |
|---|---|
| *(none)* | Open the menu (in a terminal). |
| `fetch [REF ...]` | Fetch one or more tasks by number or URL (`--newest` for your latest open one). |
| `tasks` | List the open tasks assigned to you (`--all`, `--limit N`, `--ids` for a script). |
| `login` | Save a connection: URL, database, login, output folder. |
| `profiles` | List the saved connections; `--show` their settings; `--set KEY=VALUE`, `--extra-field`, `--closed-stages` to change them; `--default NAME`; `--forget-key NAME`. |
| `check` | Test the connection. Read-only. |
| `update` | Install the newest release (`--check` only looks). |

`fetch` options:

| Option | Effect |
|---|---|
| `--newest` | The newest task assigned to you. |
| `--profile NAME` | Use another saved connection. |
| `--out DIR` | Write the result here instead of the profile's folder. |
| `--field NAME[:TITLE]` | Include an extra field (repeatable). |
| `--messages N` | Include the last N chatter messages (default: the profile's). |
| `--attachments` / `--no-attachments` | Download the attachments (they are listed either way); overrides the profile. |
| `--prompt` / `--no-prompt` | Also write `prompt.md` for a coding assistant; overrides the profile. |
| `--copy` | Copy the prompt to the clipboard (one task; implies `--prompt`). Uses `clip.exe` on WSL, `pbcopy`, `wl-copy`, `xclip` or `xsel`. |
| `--prompt-template FILE` | Use your own template (`{task_id}`, `{title}`, `{date}`, `{task_content}`). |

Environment variables: `ODOO_TASK_API_KEY` (the key), `ODOO_TASK_HOME` (settings folder, default
`~/.config/odoo-task`), `ODOO_TASK_MENU=plain` (numbered menu), `ODOO_TASK_NO_MENU=1` (no menu).

## Saving your preferences

A profile can keep what you would otherwise type at every fetch:

```bash
odoo-task profiles --set out=~/work/tasks attachments=yes prompt=yes messages=5
odoo-task profiles --extra-field x_customer_report:"Customer report"   # a field to always include
odoo-task profiles --closed-stages "Done,Cancelled"
odoo-task profiles --show                                              # what is saved (never the key)
```

| Setting | Meaning |
|---|---|
| `out` | folder where the tasks are saved (default `~/odoo-tasks`) |
| `attachments` | download the attachments (`yes`/`no`) |
| `prompt` | also write `prompt.md` (`yes`/`no`) |
| `messages` | how many chatter messages to include (0-50) |

**Priority:** a flag on the command line beats the profile, and the profile beats the built-in default. So with
`attachments=yes` saved, `odoo-task fetch 4821` downloads them, and `odoo-task fetch 4821 --no-attachments` does not
(same for `--no-prompt` and `--messages 0`). The menu shows the saved values as its defaults: press Enter to keep them.

The clipboard (`--copy`) is **not** a setting on purpose: it would overwrite your clipboard at every fetch, so you ask for
it when you want it. Several profiles (for several Odoo servers) each keep their own preferences; choose one with
`--profile NAME`.

## What "open" means

`odoo-task tasks`, `--newest` and the menu list a task as open when **all** of these hold:

1. you are one of its assignees;
2. its `state` is not done or cancelled (this is Odoo's own *Open* filter);
3. its stage is not **folded** (the usual way to mark a "done" column in Odoo);
4. its stage is not one you named as closed.

A task with no stage is never hidden by the stage rules. To name stages:

```bash
odoo-task tasks --exclude-stage Done --exclude-stage Cancelled      # for this run
odoo-task profiles --closed-stages "Done,Cancelled"                 # saved in the profile
odoo-task tasks --all                                               # everything, closed ones included
```

`tasks` prints the rule it applied on stderr, so you always know what is hidden.

## Profiles, keys and security

A profile (`~/.config/odoo-task/profiles/NAME.json`, mode 600) holds only the URL, database, login, output folder,
extra fields, closed stages and your preferences. **The key is never written to it.** In order, the key is taken from:

1. `ODOO_TASK_API_KEY`;
2. a file `~/.config/odoo-task/secrets/NAME` (mode 600) that you chose to create at `login`; a file readable by others is
   refused;
3. a hidden prompt.

Use an API key with the least rights you need and revoke it when you are done. Use `https://` outside your own machine.
See [SECURITY.md](SECURITY.md).

## Requirements

- Python 3.9 or later (standard library only).
- Bash for the installer and the `odoo-task` launcher.
- Optional: `whiptail` for the arrow-key menu (installed on Ubuntu and WSL2).
- An Odoo server reachable over HTTP(S) with the external API enabled (the default on Odoo Online and on-premise).

## Limitations

- Reads `project.task`. Other models are not supported.
- "Open" follows Odoo's own rule (`state` not done or cancelled), and also hides tasks in a **folded** stage. If your team
  closes tasks by moving them to a stage such as *Done* without changing the state, name that stage yourself (below).
- Images are saved for the **description**; images inside extra fields and messages are not downloaded.
- Tested against Odoo 18 (Enterprise); it only uses the standard external API (`fields_get`, `read`, `search_read`), so other recent versions are expected to work but are not tested.
- Not tested on Windows outside WSL2.

## Project layout

```
bin/odoo-task          launcher
src/odoo_task/         the package: client, fetch, html_text, images, store, taskref, listing, selection, clipboard, opener, menu, update, cli
scripts/               install.sh (one-line installer, also used by `update`) and release.sh (builds a release)
tests/                 unit tests with a fake Odoo server on localhost
docs/ARCHITECTURE.md   how it is built
```

## Development

```bash
make test      # 65+ unit tests, no Odoo needed
make lint      # ruff, if installed (make deps-dev)
```

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [CONTRIBUTING.md](CONTRIBUTING.md) before a larger change.

## License

MIT. See [LICENSE](LICENSE).
