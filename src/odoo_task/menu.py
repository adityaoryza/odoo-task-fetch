"""A small menu: arrow keys with whiptail when it exists, a numbered list otherwise."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence

Item = "tuple[str, str]"  # (key, label)


def _use_whiptail() -> bool:
    return (
        os.environ.get("ODOO_TASK_MENU", "auto") != "plain"
        and shutil.which("whiptail") is not None
        and os.environ.get("TERM", "dumb") != "dumb"
        and sys.stdin.isatty()
        and sys.stderr.isatty()
    )


def _read(prompt: str) -> str | None:
    try:
        return input(prompt)
    except EOFError:
        return None


def choose(title: str, text: str, items: Sequence[tuple[str, str]]) -> str | None:
    """Return the key of the chosen item, or None when cancelled."""
    if _use_whiptail():
        args = ["whiptail", "--title", title, "--notags", "--menu", text, "20", "78", str(len(items))]
        for key, label in items:
            args += [key, label]
        result = subprocess.run(args, stderr=subprocess.PIPE, text=True, check=False)  # noqa: S603
        return result.stderr.strip() or None if result.returncode == 0 else None

    print(f"\n{title}", file=sys.stderr)
    if text:
        print(text, file=sys.stderr)
    for i, (_, label) in enumerate(items, 1):
        print(f"  {i}) {label}", file=sys.stderr)
    while True:
        answer = _read(f"  Choice [1-{len(items)}, q = quit]: ")
        if answer is None or answer.strip().lower() in ("", "q"):
            return None
        if answer.strip().isdigit() and 1 <= int(answer) <= len(items):
            return items[int(answer) - 1][0]
        print("  Please type a number from the list.", file=sys.stderr)
