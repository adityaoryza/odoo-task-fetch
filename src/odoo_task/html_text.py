"""Odoo HTML (task descriptions, chatter) to readable Markdown. Standard library only."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that grant access by themselves. They must never be copied into a file that may be shared.
_SECRET_PARAMS = frozenset({"access_token", "token", "signature", "sig", "auth", "key", "api_key"})


def clean_url(url: str, base_url: str | None = None) -> str:
    """Drop access tokens from a link and make a relative Odoo link absolute (when the base URL is known)."""
    if not url or url.startswith(("javascript:", "data:", "#", "mailto:")):
        return url
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _SECRET_PARAMS]
    cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    if base_url and cleaned.startswith("/") and not cleaned.startswith("//"):
        cleaned = base_url.rstrip("/") + cleaned
    return cleaned


_BLOCK = {"p", "div", "section", "article", "tr", "table", "ul", "ol", "blockquote", "pre", "hr"}


class _Converter(HTMLParser):
    def __init__(self, keep_images: bool, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.keep_images = keep_images
        self.base_url = base_url
        self.out: list[str] = []
        self._lists: list[list[int]] = []  # stack of [counter] for ordered lists, [-1] for unordered
        self._href: list[str | None] = []
        self._in_pre = 0
        self._skip = 0  # inside <script>/<style>

    # helpers
    def _w(self, text: str) -> None:
        self.out.append(text)

    def _newline(self, count: int = 1) -> None:
        joined = "".join(self.out)
        trailing = len(joined) - len(joined.rstrip("\n"))
        if joined and trailing < count:
            self._w("\n" * (count - trailing))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "br":
            self._w("\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._newline(2)
            self._w("#" * min(int(tag[1]) + 1, 6) + " ")  # one level down: the task title is the h1
        elif tag in ("ul", "ol"):
            self._newline(1 if self._lists else 2)
            self._lists.append([0 if tag == "ol" else -1])
        elif tag == "li":
            self._newline(1)
            depth = max(len(self._lists) - 1, 0)
            if self._lists and self._lists[-1][0] >= 0:
                self._lists[-1][0] += 1
                self._w("  " * depth + f"{self._lists[-1][0]}. ")
            else:
                self._w("  " * depth + "- ")
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")
        elif tag == "code" and not self._in_pre:
            self._w("`")
        elif tag == "pre":
            self._newline(2)
            self._w("```\n")
            self._in_pre += 1
        elif tag == "a":
            href = a.get("href")
            self._href.append(clean_url(href, self.base_url) if href else None)
            self._w("[")
        elif tag == "img":
            src = clean_url(a.get("src") or "", self.base_url)
            if self.keep_images and src:
                alt = (a.get("alt") or "image").replace("]", "")
                self._newline(2)
                self._w(f"![{alt}]({src})")
                self._newline(2)
        elif tag in ("td", "th"):
            self._w(" | ")
        elif tag in _BLOCK:
            self._newline(1)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(self._skip - 1, 0)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._newline(2)
        elif tag in ("ul", "ol"):
            if self._lists:
                self._lists.pop()
            self._newline(1 if self._lists else 2)
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")
        elif tag == "code" and not self._in_pre:
            self._w("`")
        elif tag == "pre":
            self._in_pre = max(self._in_pre - 1, 0)
            self._newline(1)
            self._w("```")
            self._newline(2)
        elif tag == "a":
            href = self._href.pop() if self._href else None
            self._w(f"]({href})" if href and not href.startswith("javascript:") else "]")
        elif tag in ("p", "blockquote"):
            self._newline(2)
        elif tag in ("div", "tr", "table"):
            self._newline(1)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self._w(data if self._in_pre else re.sub(r"\s+", " ", data))


def html_to_markdown(
    html: str | None, *, keep_images: bool = True, max_length: int | None = None, base_url: str | None = None
) -> str:
    """Convert Odoo HTML to Markdown text. Images become `![alt](src)` lines, or are dropped.

    Links lose their access tokens; with `base_url`, relative links become absolute.
    """
    if not html:
        return ""
    parser = _Converter(keep_images, base_url)
    parser.feed(html)
    parser.close()
    text = "".join(parser.out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if max_length is not None and len(text) > max_length:
        text = text[: max_length - 3].rstrip() + "..."
    return text
