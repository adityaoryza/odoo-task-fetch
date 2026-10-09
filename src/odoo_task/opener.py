"""Open a file or a folder with the program of the desktop (VS Code, the file manager, the Windows Explorer from WSL).

Only fixed program names are started, with the path as an argument and without a shell.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _in_wsl() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"))


def candidates(path: Path, folder: bool) -> list[list[str]]:
    """The commands to try, best first. Pure: it only looks at which programs exist."""
    target = str(path)
    out: list[list[str]] = []
    if shutil.which("code"):
        out.append(["code", target])
    if folder and _in_wsl() and shutil.which("explorer.exe") and shutil.which("wslpath"):
        windows_path = subprocess.run(  # noqa: S603
            ["wslpath", "-w", target],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if windows_path:
            out.append(["explorer.exe", windows_path])
    for name in ("wslview", "xdg-open", "open"):
        if shutil.which(name):
            out.append([name, target])
    return out


def open_path(path: Path, folder: bool = False) -> bool:
    """Start the first program that can open `path`. Returns False when there is none."""
    for command in candidates(path, folder):
        try:
            subprocess.Popen(  # noqa: S603
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            continue
        return True
    return False
