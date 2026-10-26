"""What git-shuttle adds to the Customer report of a task: the pull request and the commits, for the PM.

It only ever ADDS: the text that is there is read first, kept as it is, and the entry is put after it (an entry
for a pull request that is already in the field is not added twice). After the write the field is read again,
and if the old text is not all there, the old value is put back. Only a custom field (x_...) of text or html
type is written, and only when the user turned it on for the repository.
"""

from __future__ import annotations

import calendar
import html
import re
import time
from typing import Any

from .client import PROTECTED_FIELDS, OdooClient, OdooError

MODEL = "project.task"
DEFAULT_FIELD = "x_customer_report"
FIELD_RE = re.compile(r"^x_[a-z0-9_]{1,60}$")
MAX_COMMITS = 30
KINDS = ("html", "text")


def _plain(value: Any) -> str:
    """The words of a field, whatever the markup: to compare what was there with what is there."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _when(iso: str) -> str:
    """A date of the trace (UTC, with a Z) in your time: 2026-10-26 09:13."""
    try:
        return time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(calendar.timegm(time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ")))
        )
    except ValueError:
        return str(iso)[:16]


def _shown(item: dict) -> str:
    """The text of an item as the report shows it: with its time, in your time, when it has one (`at`)."""
    text = str(item.get("text", ""))
    return f"{text} · {_when(item['at'])}" if item.get("at") else text


def fresh_phases(info: dict, old: object) -> list[dict]:
    """The steps of the task that are not in the field yet: [{title, when, items: [{text, url, ref}]}].

    Every item has a `ref`, a text that stays visible in the field (a link, a hash, a branch name): an item whose ref is
    already there is left out, so the same step is never written twice and a later run adds only what is new.
    """
    seen = f"{_plain(old)} {old or ''}"
    out = []
    for phase in info.get("phases") or []:
        items = []
        for item in phase.get("items") or []:
            ref = str(item.get("ref") or _shown(item))
            if ref and ref not in seen and html.escape(ref, quote=True) not in seen:
                items.append(item)
        if items:
            out.append({**phase, "items": items})
    return out


def phases_text(phases: list[dict]) -> str:
    lines = [f"git-shuttle - the steps of the task - {time.strftime('%Y-%m-%d')}"]
    for phase in phases:
        lines.append(f"{phase.get('title', '')} - {_when(phase.get('when', ''))}")
        for item in phase["items"][:MAX_COMMITS]:
            lines.append(f"- {_shown(item)}" + (f" ({item['url']})" if item.get("url") else ""))
        if len(phase["items"]) > MAX_COMMITS:
            lines.append(f"- and {len(phase['items']) - MAX_COMMITS} more")
    return "\n".join(lines)


def phases_html(phases: list[dict]) -> str:
    esc = html.escape
    out = [f"<p><strong>git-shuttle</strong> &middot; the steps of the task &middot; {time.strftime('%Y-%m-%d')}</p>"]
    for phase in phases:
        out.append(
            f"<p><strong>{esc(str(phase.get('title', '')))}</strong> &middot; {esc(_when(phase.get('when', '')))}</p>"
        )
        rows = []
        for item in phase["items"][:MAX_COMMITS]:
            text = esc(_shown(item))
            rows.append(
                f'<li><a href="{esc(item["url"], quote=True)}">{text}</a></li>'
                if item.get("url")
                else f"<li>{text}</li>"
            )
        if len(phase["items"]) > MAX_COMMITS:
            rows.append(f"<li>and {len(phase['items']) - MAX_COMMITS} more</li>")
        out.append("<ul>" + "".join(rows) + "</ul>")
    return "".join(out)


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


def _candidates(fields: dict) -> str:
    """The custom text or html fields that look like a report: the way out when the name is not the one of this Odoo."""
    words = ("report", "customer", "client", "rapport")
    near = sorted(
        f"{name} ({info.get('string', '')})"
        for name, info in fields.items()
        if FIELD_RE.match(name)
        and info.get("type") in KINDS
        and any(w in name.lower() or w in str(info.get("string", "")).lower() for w in words)
    )
    if not near:
        return " No custom text field looks like a report: find its technical name in Odoo (developer mode)."
    return " Look-alikes: " + ", ".join(near[:3]) + ". Set one: git config shuttle.odoo-task.report-field NAME"


def field_kind(client: OdooClient, field: str, allow_plain: bool = False) -> str:
    plain_ok = allow_plain and re.fullmatch(r"[a-z][a-z0-9_]{1,60}", field or "") and field not in PROTECTED_FIELDS
    if not FIELD_RE.match(field or "") and not plain_ok:
        raise OdooError(
            f"'{field}' is not a custom field (x_...): git-shuttle writes only to one of those. To write to a field "
            f"of a module of your own on purpose: git config shuttle.odoo-task.report-field-allow {field}"
        )
    fields = client.fields_get(MODEL, ["string", "type"])
    found = fields.get(field)
    if not found:
        raise OdooError(f"The task has no field '{field}'.{_candidates(fields)}")
    if found.get("type") not in KINDS:
        raise OdooError(f"The field '{field}' is a {found.get('type')} field: only text or html fields are written.")
    return str(found["type"])


def plan(client: OdooClient, task_id: int, field: str, info: dict, allow_plain: bool = False) -> dict:
    """What would be written: {kind, old, new, entry, skip}. Reads Odoo; writes nothing."""
    kind = field_kind(client, field, allow_plain)
    rows = client.read(MODEL, [task_id], [field])
    if not rows:
        raise OdooError(f"Task {task_id} was not found (or you cannot read it).")
    old = rows[0].get(field) or ""
    if info.get("phases") is not None:
        # the steps of the task, each once: only what is not in the field yet is written
        fresh = fresh_phases(info, old)
        entry = phases_html(fresh) if kind == "html" else phases_text(fresh)
        preview, skip = phases_text(fresh), not fresh
        count = sum(len(p["items"]) for p in fresh)
    else:
        entry = entry_html(info) if kind == "html" else entry_text(info)
        url = (info.get("pr") or {}).get("url", "")
        preview, skip, count = entry_text(info), bool(url) and (url in old or html.escape(url, quote=True) in old), 0
    separator = "\n\n" if old and kind == "text" and not str(old).endswith("\n\n") else ""
    return {
        "kind": kind,
        "old": old,
        "entry": entry,
        "skip": skip,
        "new": str(old) + separator + entry,
        "preview": preview,
        "count": count,
    }


def post(client: OdooClient, task_id: int, field: str, info: dict, allow_plain: bool = False) -> str:
    """Adds the entry and says what happened. The old text is kept (put back if it is not all there afterwards)."""
    done = plan(client, task_id, field, info, allow_plain)
    if done["skip"]:
        what = "every step of the task" if info.get("phases") is not None else "this pull request"
        return f"Nothing was written: the Customer report already has {what} ({field})."
    client.append_custom_field(MODEL, task_id, field, done["new"], allow_plain)
    after = (client.read(MODEL, [task_id], [field]) or [{}])[0].get(field) or ""
    if done["old"] and _plain(done["old"]) not in _plain(after):
        client.append_custom_field(MODEL, task_id, field, str(done["old"]), allow_plain)
        raise OdooError(f"Odoo changed the old text of {field}: it was put back as it was; nothing was added.")
    if info.get("phases") is not None:
        steps = ", ".join(str(p.get("title", "")) for p in fresh_phases(info, done["old"]))
        return f"Added to {field} of task {task_id}: {steps}. The text that was there is kept."
    count = len(info.get("commits") or [])
    return (
        f"Added to {field} of task {task_id}: the pull request and {count} commit(s). The text that was there is kept."
    )
