"""A read-only Odoo XML-RPC client.

Only a short allow-list of methods can be called, so no code path of this tool can create, change or delete a record.
Standard library only.
"""

from __future__ import annotations

import http.client
import re
import xmlrpc.client
from typing import Any
from urllib.parse import urlparse

# Methods that cannot change data. Anything else is refused before it leaves this machine.
READ_ONLY_METHODS = frozenset({"search_read", "read", "search", "search_count", "fields_get"})

DEFAULT_TIMEOUT = 30


class OdooError(Exception):
    """Any failure talking to Odoo, with a message that is safe to print (it never holds a secret)."""


_BARE_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?(/.*)?$")


def normalize_url(url: str) -> str:
    """Return the base URL without a trailing slash, or raise OdooError if it is not an http(s) URL.

    A bare host (`odoo.example.com`, `localhost:8069`) is accepted: https is assumed, except for localhost.
    Anything with another scheme (file:, javascript:, ftp:) is refused.
    """
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url and _BARE_HOST.match(url):
        host = url.split("/")[0].split(":")[0].lower()
        url = ("http://" if host == "localhost" or host.startswith("127.") else "https://") + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise OdooError(f"Not a valid Odoo URL: '{url}' (expected http(s)://host[:port])")
    return url


class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._timeout = timeout

    def make_connection(self, host: Any) -> http.client.HTTPConnection:
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class _TimeoutSafeTransport(xmlrpc.client.SafeTransport):
    def __init__(self, timeout: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._timeout = timeout

    def make_connection(self, host: Any) -> http.client.HTTPConnection:
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class OdooClient:
    """Connects with a database, a login and a password or API key. Never stores or logs the secret."""

    def __init__(self, url: str, db: str, user: str, secret: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.url = normalize_url(url)
        self.db = db
        self.user = user
        self._secret = secret
        self.timeout = timeout
        self.uid: int | None = None
        # Companies the user may access. Sent with every call, like ticking all companies in the web client, so a
        # task of another company can be read. Empty when it cannot be known: Odoo then uses the default company.
        self.company_ids: list[int] = []
        self._models: xmlrpc.client.ServerProxy | None = None

    def __repr__(self) -> str:  # the secret must never end up in a log or a traceback
        return f"OdooClient(url={self.url!r}, db={self.db!r}, user={self.user!r})"

    def _proxy(self, path: str) -> xmlrpc.client.ServerProxy:
        transport: xmlrpc.client.Transport
        if self.url.startswith("https"):
            transport = _TimeoutSafeTransport(self.timeout)
        else:
            transport = _TimeoutTransport(self.timeout)
        return xmlrpc.client.ServerProxy(f"{self.url}{path}", transport=transport, allow_none=True)

    def version(self) -> dict[str, Any]:
        """Server version information. Needs no login."""
        try:
            return self._proxy("/xmlrpc/2/common").version()
        except (OSError, xmlrpc.client.Error) as exc:
            raise OdooError(f"Cannot reach {self.url}: {exc}") from None

    def connect(self) -> int:
        """Authenticate and return the user id."""
        try:
            uid = self._proxy("/xmlrpc/2/common").authenticate(self.db, self.user, self._secret, {})
        except (OSError, xmlrpc.client.Error) as exc:
            raise OdooError(f"Cannot reach {self.url}: {exc}") from None
        if not uid:
            raise OdooError("Authentication failed: wrong database, login or password / API key.")
        self.uid = int(uid)
        self._models = self._proxy("/xmlrpc/2/object")
        self._load_companies()
        return self.uid

    def _load_companies(self) -> None:
        """Best effort: a failure here must not stop the work, the default company is then used."""
        self.company_ids = []
        try:
            rows = self._models.execute_kw(  # type: ignore[union-attr]
                self.db, self.uid, self._secret, "res.users", "read", [[self.uid]], {"fields": ["company_ids"]}
            )
            self.company_ids = [int(c) for c in (rows[0].get("company_ids") or [])] if rows else []
        except (OSError, xmlrpc.client.Error, KeyError, TypeError, ValueError):
            self.company_ids = []

    def execute(
        self, model: str, method: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None
    ) -> Any:
        if method not in READ_ONLY_METHODS:
            raise OdooError(f"Refused: '{method}' is not a read-only method (odoo-task never writes to Odoo).")
        if self.uid is None or self._models is None:
            self.connect()
        assert self._models is not None
        kwargs = dict(kwargs or {})
        if self.company_ids:
            context = dict(kwargs.get("context") or {})
            context.setdefault("allowed_company_ids", self.company_ids)
            kwargs["context"] = context
        try:
            return self._models.execute_kw(self.db, self.uid, self._secret, model, method, args or [], kwargs)
        except xmlrpc.client.Fault as exc:
            first_line = str(exc.faultString).strip().splitlines()[-1] if exc.faultString else "error"
            hint = ""
            if "multi-company" in first_line.lower():
                hint = " (odoo-task already asks for every company you may access: ask an admin for access to that one)"
            raise OdooError(f"Odoo refused {model}.{method}: {first_line}{hint}") from None
        except (OSError, xmlrpc.client.Error) as exc:
            raise OdooError(f"Cannot reach {self.url}: {exc}") from None

    # Convenience wrappers ------------------------------------------------------------------------------------------

    def read(self, model: str, ids: list[int], fields: list[str] | None = None) -> list[dict[str, Any]]:
        return self.execute(model, "read", [ids], {"fields": fields or []})

    def search_read(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        order: str = "",
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        return self.execute(
            model, "search_read", [domain or []], {"fields": fields or [], "order": order, "limit": limit}
        )

    def fields_get(self, model: str, attributes: list[str] | None = None) -> dict[str, dict[str, Any]]:
        return self.execute(model, "fields_get", [], {"attributes": attributes or ["string", "type"]})
