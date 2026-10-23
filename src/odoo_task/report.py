"""What git-shuttle adds to the Customer report of a task: the pull request and the commits, for the PM.

It only ever ADDS: the text that is there is read first, kept as it is, and the entry is put after it (an entry
for a pull request that is already in the field is not added twice). After the write the field is read again,
and if the old text is not all there, the old value is put back. Only a custom field (x_...) of text or html
type is written, and only when the user turned it on for the repository.
"""

from __future__ import annotations

import html
import re
import time
from typing import Any

from .client import OdooClient, OdooError

MODEL = "project.task"
DEFAULT_FIELD = "x_customer_report"
FIELD_RE = re.compile(r"^x_[a-z0-9_]{1,60}$")
MAX_COMMITS = 30
KINDS = ("html", "text")


def _plain(value: Any) -> str:
    """The words of a field, whatever the markup: to compare what was there with what is there."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def entry_text(info: dict) -> str:
    pr = info.get("pr") or {}
    commits = info.get("commits") or []
    lines = [f"git-shuttle - branch {info.get('branch', '')} - {time.strftime('%Y-%m-%d')}"]
    if pr.get("url"):
        lines.append(f"Pull request: {pr.get('title', '')} ({pr['url']}) -> {pr.get('base', '')}")
    else:
        lines.append(f"Pull request: {pr.get('title', '')} (the address is added when it is opened)")
    if commits:
        lines.append("Commits:")
        for commit in commits[:MAX_COMMITS]:
            where = f" ({commit['url']})" if commit.get("url") else ""
            lines.append(f"- {commit['sha'][:8]} {commit.get('subject', '')}{where}")
        if len(commits) > MAX_COMMITS:
            lines.append(f"- and {len(commits) - MAX_COMMITS} more")
    return "\n".join(lines)


def entry_html(info: dict) -> str:
    esc = html.escape
    pr = info.get("pr") or {}
    commits = info.get("commits") or []
    branch, day = esc(str(info.get("branch", ""))), time.strftime("%Y-%m-%d")
    head = f"<p><strong>git-shuttle</strong> &middot; branch <code>{branch}</code> &middot; {day}</p>"
    if pr.get("url"):
        link = f'<a href="{esc(pr["url"], quote=True)}">{esc(str(pr.get("title", "")) or pr["url"])}</a>'
    else:
        link = f"{esc(str(pr.get('title', '')))} (the address is added when it is opened)"
    items = [f"<li>Pull request: {link} &rarr; {esc(str(pr.get('base', '')))}</li>"]
    if commits:
        rows = []
        for commit in commits[:MAX_COMMITS]:
            short = esc(commit["sha"][:8])
            sha = f'<a href="{esc(commit["url"], quote=True)}">{short}</a>' if commit.get("url") else short
            rows.append(f"<li>{sha} {esc(str(commit.get('subject', '')))}</li>")
        if len(commits) > MAX_COMMITS:
            rows.append(f"<li>and {len(commits) - MAX_COMMITS} more</li>")
        items.append("<li>Commits:<ul>" + "".join(rows) + "</ul></li>")
    return head + "<ul>" + "".join(items) + "</ul>"


def field_kind(client: OdooClient, field: str) -> str:
    if not FIELD_RE.match(field or ""):
        raise OdooError(f"'{field}' is not a custom field (x_...): git-shuttle writes only to one of those.")
    found = client.fields_get(MODEL, ["string", "type"]).get(field)
    if not found:
        raise OdooError(f"The task has no field '{field}'.")
    if found.get("type") not in KINDS:
        raise OdooError(f"The field '{field}' is a {found.get('type')} field: only text or html fields are written.")
    return str(found["type"])


def plan(client: OdooClient, task_id: int, field: str, info: dict) -> dict:
    """What would be written: {kind, old, new, entry, skip}. Reads Odoo; writes nothing."""
    kind = field_kind(client, field)
    rows = client.read(MODEL, [task_id], [field])
    if not rows:
        raise OdooError(f"Task {task_id} was not found (or you cannot read it).")
    old = rows[0].get(field) or ""
    entry = entry_html(info) if kind == "html" else entry_text(info)
    url = (info.get("pr") or {}).get("url", "")
    skip = bool(url) and (url in old or html.escape(url, quote=True) in old)
    separator = "\n\n" if old and kind == "text" and not str(old).endswith("\n\n") else ""
    return {"kind": kind, "old": old, "entry": entry, "skip": skip, "new": str(old) + separator + entry}


def post(client: OdooClient, task_id: int, field: str, info: dict) -> str:
    """Adds the entry and says what happened. The old text is kept (put back if it is not all there afterwards)."""
    done = plan(client, task_id, field, info)
    if done["skip"]:
        return f"Nothing was written: the Customer report already has this pull request ({field})."
    client.append_custom_field(MODEL, task_id, field, done["new"])
    after = (client.read(MODEL, [task_id], [field]) or [{}])[0].get(field) or ""
    if done["old"] and _plain(done["old"]) not in _plain(after):
        client.append_custom_field(MODEL, task_id, field, str(done["old"]))
        raise OdooError(f"Odoo changed the old text of {field}: it was put back as it was; nothing was added.")
    count = len(info.get("commits") or [])
    return (
        f"Added to {field} of task {task_id}: the pull request and {count} commit(s). The text that was there is kept."
    )
