"""Turn what the user types (a number or an Odoo URL) into a task id, and build safe folder names."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def parse_task_ref(text: str) -> int:
    """Accepts `123`, `#123`, or an Odoo URL such as /odoo/project/5/tasks/123, /web#id=123&model=project.task."""
    raw = (text or "").strip()
    if re.fullmatch(r"#?\d+", raw):
        return int(raw.lstrip("#"))
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        fragment = parse_qs(parsed.fragment)
        query = parse_qs(parsed.query)
        for source in (fragment, query):
            if "id" in source and re.fullmatch(r"\d+", source["id"][0]):
                model = source.get("model", ["project.task"])[0]
                if model == "project.task":
                    return int(source["id"][0])
        match = re.search(r"/tasks/(\d+)", parsed.path)
        if match:
            return int(match.group(1))
        numbers = re.findall(r"/(\d+)(?=/|$)", parsed.path)
        if numbers:
            return int(numbers[-1])
    raise ValueError(f"Not a task number or an Odoo task URL: '{text}'")


def slugify(name: str, max_len: int = 60) -> str:
    """A folder-safe name: letters, digits, underscores. Never empty, never a path."""
    text = re.sub(r"[^\w\s-]", "", name or "", flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "_", text.strip()).strip("_")
    return (text[:max_len].strip("_")) or "task"


def task_folder_name(task_id: int, task_name: str) -> str:
    return f"{int(task_id)}_{slugify(task_name)}"
