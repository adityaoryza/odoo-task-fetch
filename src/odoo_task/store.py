"""Profiles and secrets on disk.

A profile holds only what is not secret (URL, database, login, output folder). The API key or password is read from the
environment, from an optional file with mode 600 that the user asked for, or typed at a hidden prompt. It is never
written to a profile, a log or the command line.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

ENV_SECRET = "ODOO_TASK_API_KEY"  # noqa: S105 (the name of a variable, not a secret)
_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")
RESERVED = frozenset({"fetch", "check", "fields", "login", "profiles", "update", "help", "version", "prompt"})


def config_home() -> Path:
    explicit = os.environ.get("ODOO_TASK_HOME")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "odoo-task"


def valid_profile_name(name: str) -> bool:
    return bool(_NAME.match(name or "")) and name not in RESERVED


@dataclass
class Profile:
    name: str
    url: str
    db: str
    user: str
    output_dir: str = "~/odoo-tasks"
    extra_fields: list[str] = field(default_factory=list)  # "field_name" or "field_name:Title"
    closed_stages: list[str] = field(default_factory=list)  # stage names this user counts as closed (e.g. "Done")
    attachments: bool = False  # preferences: what a fetch does when no flag says otherwise
    prompt: bool = False
    messages: int = 0

    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser()


_KEYS = ("url", "db", "user", "output_dir", "extra_fields", "closed_stages", "attachments", "prompt", "messages")


def _profiles_dir() -> Path:
    return config_home() / "profiles"


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def list_profiles() -> list[str]:
    d = _profiles_dir()
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def load_profile(name: str) -> Profile:
    if not valid_profile_name(name):
        raise ValueError(f"Invalid profile name: '{name}'")
    path = _profiles_dir() / f"{name}.json"
    if not path.is_file():
        known = ", ".join(list_profiles()) or "none"
        raise FileNotFoundError(f"No profile named '{name}' (saved profiles: {known}). Run: odoo-task login")
    data = json.loads(path.read_text(encoding="utf-8"))
    kwargs = {k: data[k] for k in _KEYS if k in data}
    for required in ("url", "db", "user"):
        if not kwargs.get(required):
            raise ValueError(f"Profile '{name}' has no '{required}'")
    return Profile(name=name, **kwargs)


def save_profile(profile: Profile) -> Path:
    if not valid_profile_name(profile.name):
        raise ValueError(f"Invalid profile name: '{profile.name}' (letters, digits, _ . -; not a command word)")
    _private_dir(config_home())
    _private_dir(_profiles_dir())
    path = _profiles_dir() / f"{profile.name}.json"
    data = {k: v for k, v in asdict(profile).items() if k in _KEYS}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def default_profile_name() -> str | None:
    names = list_profiles()
    cfg = config_home() / "config.json"
    if cfg.is_file():
        try:
            chosen = json.loads(cfg.read_text(encoding="utf-8")).get("default")
        except (OSError, ValueError):
            chosen = None
        if chosen in names:
            return chosen
    return names[0] if len(names) == 1 else None


def set_default_profile(name: str) -> None:
    if name not in list_profiles():
        raise FileNotFoundError(f"No profile named '{name}'")
    _private_dir(config_home())
    cfg = config_home() / "config.json"
    cfg.write_text(json.dumps({"default": name}) + "\n", encoding="utf-8")
    cfg.chmod(0o600)


# Secrets -----------------------------------------------------------------------------------------------------------


def _secret_path(name: str) -> Path:
    return config_home() / "secrets" / name


def save_secret(name: str, secret: str) -> Path:
    if not valid_profile_name(name):
        raise ValueError(f"Invalid profile name: '{name}'")
    _private_dir(config_home())
    _private_dir(config_home() / "secrets")
    path = _secret_path(name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(secret)
    path.chmod(0o600)
    return path


def delete_secret(name: str) -> bool:
    path = _secret_path(name)
    if path.is_file():
        path.unlink()
        return True
    return False


def has_saved_secret(name: str) -> bool:
    return _secret_path(name).is_file()


def read_secret(name: str) -> str | None:
    """The environment wins, then the saved file (only if it is not readable by others). None = ask the user."""
    env = os.environ.get(ENV_SECRET)
    if env:
        return env
    path = _secret_path(name)
    if path.is_file():
        if path.stat().st_mode & 0o077:
            raise PermissionError(f"{path} is readable by other users: run  chmod 600 {path}  (or delete it)")
        return path.read_text(encoding="utf-8").strip() or None
    return None
