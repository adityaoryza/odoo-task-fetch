"""Copy text to the clipboard with the program the system offers (WSL, macOS, Wayland, X11).

Only fixed program names are started and the text goes through their standard input, never through the command line.
"""

from __future__ import annotations

import os
import shutil
import subprocess


def _in_wsl() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"))


def candidates() -> list[tuple[list[str], str]]:
    """(command, encoding) pairs to try, best first. Pure: it only looks at which programs exist."""
    out: list[tuple[list[str], str]] = []
    if _in_wsl() and shutil.which("clip.exe"):
        out.append((["clip.exe"], "utf-16"))  # with a byte-order mark, so that accents survive
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        out.append((["wl-copy"], "utf-8"))
    if shutil.which("pbcopy"):
        out.append((["pbcopy"], "utf-8"))
    if shutil.which("xclip"):
        out.append((["xclip", "-selection", "clipboard"], "utf-8"))
    if shutil.which("xsel"):
        out.append((["xsel", "--clipboard", "--input"], "utf-8"))
    return out


def copy(text: str) -> bool:
    """Put `text` on the clipboard. Returns False when no clipboard program works."""
    for command, encoding in candidates():
        try:
            subprocess.run(  # noqa: S603
                command,
                input=text.encode(encoding),
                check=True,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return True
    return False
