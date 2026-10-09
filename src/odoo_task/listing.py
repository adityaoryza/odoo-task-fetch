"""Text table of a list of tasks."""

from __future__ import annotations

from collections.abc import Sequence

from odoo_task.fetch import TaskSummary


def _cut(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: max(width - 1, 1)].rstrip() + "…"


def format_tasks(tasks: Sequence[TaskSummary], numbered: bool = False) -> list[str]:
    """Header and one line per task. With `numbered`, each line starts with its position (for a choice)."""
    if not tasks:
        return []
    id_width = max(len("ID"), *(len(str(t.id)) for t in tasks))
    prefix_header = "     " if numbered else ""
    lines = [f"{prefix_header}{'ID':>{id_width}}  {'STAGE':<16}  {'PROJECT':<20}  {'DEADLINE':<10}  TITLE"]
    for position, t in enumerate(tasks, 1):
        prefix = f"{position:>3}) " if numbered else ""
        lines.append(
            f"{prefix}{t.id:>{id_width}}  {_cut(t.stage, 16):<16}  {_cut(t.project, 20):<20}  "
            f"{t.deadline[:10]:<10}  {_cut(t.title, 70)}"
        )
    return lines
