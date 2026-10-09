"""`odoo-task update`: install the newest release with the installer that ships with this copy."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def root_dir() -> Path:
    env = os.environ.get("ODOO_TASK_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def is_release_install(root: Path | None = None) -> bool:
    return (Path(root) if root else root_dir()).joinpath("RELEASE").is_file()


def run_update(check_only: bool = False) -> int:
    root = root_dir()
    if not is_release_install(root):
        print(f"This copy is a source checkout ({root}): update it with  git pull.", file=sys.stderr)
        print("To install the released version instead, see the Installation section of the README.", file=sys.stderr)
        return 0
    installer = root / "scripts" / "install.sh"
    if not installer.is_file():
        print(f"odoo-task: installer not found: {installer}", file=sys.stderr)
        return 1
    cmd = [str(installer), "remote"] + (["--check"] if check_only else [])
    return subprocess.call(cmd)  # noqa: S603 (a fixed path inside this installation)
