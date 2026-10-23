# Security policy

`odoo-task` logs in to an Odoo server with an API key or a password, so security reports are taken seriously.

## What it promises

- **Read-only.** The client only accepts `search_read`, `read`, `search`, `search_count` and `fields_get`. Any other method is
  refused before it leaves your machine (see `src/odoo_task/client.py` and `tests/unit/test_client.py`).
- **One narrow write, opt-in.** For the git-shuttle add-on only, `OdooClient.append_custom_field` writes a custom field (`x_...`) of one
  task, to add the pull request and the commits to the Customer report. It is off until you turn it on for a repository, the old text is read
  first and kept, the field is read again afterwards (the old value is put back if it changed), and the general `execute` is still read-only.
- **No secret in a profile, a log or the command line.** The key comes from `ODOO_TASK_API_KEY`, from a file with mode 600
  that you explicitly asked to create, or from a hidden prompt. A key file that other users can read is refused.
- **Safe output paths.** Folder and file names are built from the task number and a sanitized title; downloaded attachment
  names are reduced to their last component.

## What it does not do

- It does not protect the Odoo account itself: use an API key with the least rights needed, and revoke it when done.
- `http://` URLs send the key in clear text. Use `https://` outside your own machine.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability. Use the private security advisory feature of the repository
(Security tab, "Report a vulnerability"). Include the version, what you did, what you expected and what happened.
