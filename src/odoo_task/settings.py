"""The preferences a profile can keep, with their validation.

Priority when a command runs: a flag on the command line, then the profile, then the built-in default.
`copy` (the clipboard) is deliberately not one of them: a setting that silently overwrites the clipboard at every fetch
is a surprise, so it stays an explicit flag.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from odoo_task.fetch import ExtraField
from odoo_task.store import Profile

MAX_MESSAGES = 50
_YES = {"y", "yes", "true", "1", "on"}
_NO = {"n", "no", "false", "0", "off"}


def parse_bool(text: str) -> bool:
    value = text.strip().lower()
    if value in _YES:
        return True
    if value in _NO:
        return False
    raise ValueError(f"'{text}' is not yes or no")


def parse_messages(text: str) -> int:
    if not text.strip().isdigit():
        raise ValueError(f"'{text}' is not a number")
    number = int(text)
    if number > MAX_MESSAGES:
        raise ValueError(f"at most {MAX_MESSAGES} messages")
    return number


def parse_folder(text: str) -> str:
    folder = text.strip()
    if not folder or "\n" in folder or "\x00" in folder:
        raise ValueError("a folder is needed")
    return folder


# key -> (profile attribute, parser, what it means)
SETTINGS: dict[str, tuple[str, Callable[[str], Any], str]] = {
    "out": ("output_dir", parse_folder, "folder where the tasks are saved"),
    "attachments": ("attachments", parse_bool, "download the attachments (yes/no)"),
    "prompt": ("prompt", parse_bool, "also write prompt.md (yes/no)"),
    "messages": ("messages", parse_messages, f"how many chatter messages to include (0-{MAX_MESSAGES})"),
}


def apply_settings(profile: Profile, assignments: Iterable[str]) -> list[str]:
    """Apply `key=value` items to the profile (in memory). Returns what was set, for a confirmation message.

    Everything is checked before anything is changed, so one bad item changes nothing.
    """
    parsed: list[tuple[str, str, Any]] = []
    for item in assignments:
        key, sep, value = item.partition("=")
        key = key.strip().lower()
        if not sep:
            raise ValueError(f"'{item}' should look like key=value (keys: {', '.join(SETTINGS)})")
        if key not in SETTINGS:
            hint = " (it is not saved on purpose: use --copy when you want it)" if key == "copy" else ""
            raise ValueError(f"unknown setting '{key}'{hint}. Keys: {', '.join(SETTINGS)}")
        attribute, parser, _meaning = SETTINGS[key]
        try:
            parsed.append((key, attribute, parser(value)))
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from None
    for _key, attribute, value in parsed:
        setattr(profile, attribute, value)
    return [
        f"{key}={'yes' if value is True else 'no' if value is False else value}" for key, _attribute, value in parsed
    ]


def add_extra_field(profile: Profile, text: str) -> str:
    """Add `NAME[:TITLE]`, replacing an entry of the same field."""
    field = ExtraField.parse(text)
    kept = [e for e in profile.extra_fields if ExtraField.parse(e).name != field.name]
    profile.extra_fields = [*kept, f"{field.name}:{field.title}" if field.title else field.name]
    return profile.extra_fields[-1]


def remove_extra_field(profile: Profile, name: str) -> bool:
    kept = [e for e in profile.extra_fields if ExtraField.parse(e).name != name.strip()]
    changed = len(kept) != len(profile.extra_fields)
    profile.extra_fields = kept
    return changed


def describe(profile: Profile) -> list[str]:
    """The settings of a profile as readable lines (never a key)."""
    stages = ", ".join(profile.closed_stages) or "none"
    extras = ", ".join(profile.extra_fields) or "none"
    return [
        f"profile      {profile.name}",
        f"connection   {profile.user} @ {profile.url}  (database {profile.db})",
        f"out          {profile.output_dir}",
        f"attachments  {'yes' if profile.attachments else 'no'}",
        f"prompt       {'yes' if profile.prompt else 'no'}",
        f"messages     {profile.messages}",
        f"extra fields {extras}",
        f"closed stages {stages}",
    ]
