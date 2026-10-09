"""Save the images of a task description next to the Markdown file, and point the HTML at the local copies."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable
from pathlib import Path

EXT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGES = 60

_DATA_URI = re.compile(r'src="data:(image/[a-z+.-]+);base64,([A-Za-z0-9+/=\s]+)"')
_ATTACHMENT = re.compile(r'src="/web/(?:image|content)/(\d+)[^"]*"')

# Reads an attachment: returns (base64 data, mime type) or None. Injected, so the tests need no Odoo.
AttachmentReader = Callable[[int], "tuple[str, str] | None"]


def _write(out_dir: Path, name: str, b64: str) -> bool:
    try:
        raw = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return False
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / name).write_bytes(raw)
    return True


def localize_images(html: str, out_dir: Path, read_attachment: AttachmentReader | None) -> tuple[str, list[str]]:
    """Return (html with local file names, names of the files written). Failures leave the original reference."""
    saved: list[str] = []
    if not html:
        return html, saved

    def data_uri(match: re.Match[str]) -> str:
        mime, payload = match.group(1), re.sub(r"\s+", "", match.group(2))
        ext = EXT_BY_MIME.get(mime)
        if ext is None or len(saved) >= MAX_IMAGES:
            return match.group(0)
        name = f"img_b64_{len(saved) + 1}.{ext}"
        if _write(out_dir, name, payload):
            saved.append(name)
            return f'src="{name}"'
        return match.group(0)

    html = _DATA_URI.sub(data_uri, html)

    if read_attachment is not None:
        cache: dict[int, str | None] = {}

        def attachment(match: re.Match[str]) -> str:
            att_id = int(match.group(1))
            if att_id not in cache:
                cache[att_id] = None
                if len(saved) < MAX_IMAGES:
                    got = read_attachment(att_id)
                    ext = EXT_BY_MIME.get((got[1] if got else "") or "")
                    if got and ext:
                        name = f"img_att_{att_id}.{ext}"
                        if _write(out_dir, name, got[0]):
                            saved.append(name)
                            cache[att_id] = name
            name = cache[att_id]
            return f'src="{name}"' if name else match.group(0)

        html = _ATTACHMENT.sub(attachment, html)
    return html, saved
