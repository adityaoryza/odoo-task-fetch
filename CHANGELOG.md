# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.1] - 2026-10-26

### Changed

- The row of steps has two cells for the deploys: **Staging** and **Production** (the step `Deployed to prod`), instead of one.

## [0.6.0] - 2026-10-26

### Added

- The Customer Report has a row of steps (Started to Deployed): a dark cell for each step that is in the trace, a light one for the others. It uses plain cells with a background, which Odoo keeps (a picture with a data address it does not show).

### Changed

- The steps of the task are one block of git-shuttle at the start of an html field (`<div id="git-shuttle-flow">`). A later run replaces that block with the newer one, and nothing else: the other text is read first, kept as it is, and put back if Odoo changed it. An older entry stays below the block. A text field is still only added to.

## [0.5.1] - 2026-10-26

### Changed

- The steps of the task in the Customer Report are a table (step, date, details) instead of lists. The inline colours are a bonus: if the field of Odoo removes them, it is still a plain table.

## [0.5.0] - 2026-10-26

### Added
- The Customer Report can hold **the steps of the task**, one block for each: Started, Linked to the task, Commits, Pushed, Pull request, Merged, Released, Deployed,
  each with its date (in your time) and its links. It only adds: a step (or a commit, a deploy) that is in the field already is not written again, so a later run
  adds only what is new, and the report grows as the task goes on. git-shuttle gives the steps (from the trace of the task); without them the report is still
  the pull request and its commits.

### Fixed
- The card of a task shows a markdown link as text: `[label](address)` is `label (address)`, and `[address](address)` is the address alone (it was shown as it is written
  in the task).

## [0.4.2] - 2026-10-26

### Added
- The Customer Report of git-shuttle can go to a field of a module of your own, without the `x_` (like `report_details`), when you name it a second time on
  purpose: `git config shuttle.odoo-task.report-field report_details` and `git config shuttle.odoo-task.report-field-allow report_details`. The fields that hold
  the task itself (`name`, `description`, `state`, `stage_id`, `project_id`, `user_ids`) are never written. It still only adds to what is there.

## [0.4.1] - 2026-10-26

### Added
- `odoo-task fields [WORDS...]`: lists the custom fields of a task (`x_...`), or the fields whose name or label holds every word (`odoo-task fields customer
  report`), with their type: the way to find the technical name of a field (for the Customer report of git-shuttle) without developer mode in Odoo.

### Fixed
- When the field of the Customer report does not exist in your Odoo, the message names the custom text fields that look like it (up to three, with their
  labels) and the command that sets the right one (`git config shuttle.odoo-task.report-field NAME`), instead of only saying that the field is missing.

## [0.4.0] - 2026-10-26

### Added
- The card of the task in git-shuttle can be **refreshed**: the add-on fetches the task from Odoo again (a read, with its latest 10 messages) and says
  whether it changed since the last fetch and when it was fetched. The card shows the whole description (up to 5000 characters) and the latest
  messages instead of its first 600 characters, says "(no description in Odoo)" for an empty one, leaves out the images that are files of your machine,
  and shows the deadline.
- A refresh downloads the **attachments and the images of the description** too (the first fetch, when a branch is started, only lists them: a hook has a
  few seconds), and the card says which files were saved and in which folder (`Files`, `Folder`), or that they are listed and not downloaded yet.

## [0.3.0] - 2026-10-23

### Added
- The git-shuttle add-on can add the pull request and the commits to the **Customer report** of a task (hook `report`), for the PM to check on
  GitHub. It is off until `git shuttle addon report odoo-task on` (for one repository), shows the text and asks first, and only **adds**: the text
  that is in the field is kept, one entry for each pull request, and the old value is put back if Odoo changed it. Only a custom field (`x_...`)
  of text or html type of one task is written (`x_customer_report`, or `git config shuttle.odoo-task.report-field`). The general client is still
  read-only; the write is the separate `OdooClient.append_custom_field`.

### Fixed
- The add-on: the description of a pull request no longer starts with an image of the task (a file on your machine, it shows nothing on GitHub): the
  first paragraph with text is used.

## [0.2.1] - 2026-10-23

### Fixed
- The add-on: a task whose title has quotes, a question mark or a dollar sign (`Copy "Export" to Accounting`) no longer makes git-shuttle refuse
  the proposed branch name; what is not simple text is dropped from it.

## [0.2.0] - 2026-10-23

### Added
- The add-on of [git-shuttle](https://github.com/adityaoryza/git-shuttle) (`git-shuttle-odoo-task`, installed next to `odoo-task`, protocol 1):
  `git shuttle start --task 4821` makes the branch from the title of the task (`[Sales]` tags removed) and the branch remembers the task;
  `git shuttle pr` fills the title and the description (in the style `## Description`, `## Commits & Changes`, `## Verification`); the web UI
  shows a card of the task. It reads the folders that `odoo-task fetch` writes (the folder of your connection, or
  `git config shuttle.odoo-task.dir`), fetches a missing task with `odoo-task fetch` (read-only), and never writes to Odoo. It does nothing
  until you run `git shuttle addon enable odoo-task`.
- The add-on lists your open tasks (`tasks` hook) and has a `setup` hook: the connection (URL, database, login, folder) and the API key can be
  set from the web UI of git-shuttle. The key is tested first, saved in a file of mode 600 and never shown back.
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
