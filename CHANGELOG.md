# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `odoo-task tasks`: the open tasks assigned to you (`--all`, `--limit`, `--ids` for scripts).
- `fetch` takes several tasks at once; a task that fails does not stop the others and the exit code says so.
- `fetch --copy`: the prompt on the clipboard (`clip.exe` on WSL, `pbcopy`, `wl-copy`, `xclip`, `xsel`).
- Menu: pick from your open tasks (`2`, `1,3`, `2-4`), choose the folder, ask for attachments, prompt, clipboard and messages,
  and open `task.md` or the folder afterwards.
- The menu does **one action and ends** (no loop), with the exit code of that action; the result stays on the terminal.
- Preferences in the profile: `profiles --set out=... attachments=... prompt=... messages=...`, `--extra-field`, `--show`.
  Priority: flag, then profile, then built-in default (`--no-attachments`, `--no-prompt` and `--messages 0` override it).
  The menu uses the saved values as its defaults. The clipboard is deliberately not a setting.
- `--newest` now means the newest *open* task. Open means: not done or cancelled (`state`), not in a folded stage, and not in
  a stage you name with `--exclude-stage` or `profiles --closed-stages`.

## [0.1.0] - 2026-10-09

### Added
- `odoo-task fetch`: a task by number, `#number`, or the URL of the task in Odoo, or the newest task assigned to you
  (`--newest`). Writes `task.md` (title, project, stage, assignees, tags, customer, deadline, link, description) and the
  images of the description in one folder per task.
- Extra fields (`--field NAME[:TITLE]`, or saved in the profile): any field of the task, for example a custom report field.
  Fields that do not exist in your Odoo are skipped with a warning.
- `--messages N` (latest chatter messages), `--attachments` (download the attachments; they are always listed),
  `--prompt` (a ready-to-paste prompt for a coding assistant, from a template you can replace).
- `login`, `profiles` and `check`. A profile never holds the key: it comes from `ODOO_TASK_API_KEY`, a file with mode 600
  that you ask for, or a hidden prompt.
- A menu when started with no arguments (arrow keys with `whiptail`, a numbered list otherwise).
- A one-line installer with a SHA-256 check, `odoo-task update`, and `scripts/release.sh`.
- The client can only call read-only methods; this is enforced in one place and covered by tests.
