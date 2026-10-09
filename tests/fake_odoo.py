"""A tiny fake Odoo XML-RPC server on localhost, for the tests. It records every call, so a test can prove that
odoo-task never sent anything but reads."""

from __future__ import annotations

import base64
import threading
import xmlrpc.client
from typing import Any
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

# 1x1 transparent PNG
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
LOGIN, SECRET, UID = "dev@example.com", "s3cret", 7

SCHEMA = {
    "name": {"string": "Task Title", "type": "char"},
    "project_id": {"string": "Project", "type": "many2one", "relation": "project.project"},
    "stage_id": {"string": "Stage", "type": "many2one", "relation": "project.task.type"},
    "user_ids": {"string": "Assignees", "type": "many2many", "relation": "res.users"},
    "tag_ids": {"string": "Tags", "type": "many2many", "relation": "project.tags"},
    "partner_id": {"string": "Customer", "type": "many2one", "relation": "res.partner"},
    "date_deadline": {"string": "Deadline", "type": "date"},
    "description": {"string": "Description", "type": "html"},
    "x_report": {"string": "Customer Report", "type": "html"},
    "x_ref": {"string": "Reference", "type": "char"},
    "state": {
        "string": "State",
        "type": "selection",
        "searchable": True,
        "selection": [
            ["01_in_progress", "In Progress"],
            ["02_changes_requested", "Changes Requested"],
            ["1_done", "Done"],
            ["1_canceled", "Cancelled"],
        ],
    },
}

TASKS: dict[int, dict[str, Any]] = {
    42: {
        "id": 42,
        "name": "Fix the invoice export ../../etc",
        "project_id": [5, "Project A"],
        "stage_id": [2, "In Progress"],
        "user_ids": [UID],
        "tag_ids": [1, 2],
        "partner_id": [9, "ACME"],
        "date_deadline": "2026-12-01",
        "description": (
            "<p>Export fails.</p><ul><li>Step <b>one</b></li><li>Step two</li></ul>"
            f'<p><img src="data:image/png;base64,{PNG_B64}"/></p>'
            '<p><img src="/web/image/77?unique=abc"/></p>'
        ),
        "x_report": "<p>Customer says <strong>urgent</strong>.</p>",
        "x_ref": "REF-1",
        "state": "02_changes_requested",
    },
    43: {"id": 43, "name": "Second", "user_ids": [UID], "description": False, "state": "01_in_progress"},
    44: {"id": 44, "name": "Closed one", "user_ids": [UID], "description": False, "state": "1_done"},
    45: {"id": 45, "name": "Not mine", "user_ids": [UID + 1], "description": False, "state": "01_in_progress"},
    # open by state, but in a folded stage / in a stage the user calls closed; and one with no stage at all
    46: {"id": 46, "name": "Folded stage", "user_ids": [UID], "state": "01_in_progress", "stage_id": [3, "Done"]},
    30: {"id": 30, "name": "Other company", "user_ids": [UID + 1], "state": "01_in_progress", "company_id": 2},
    48: {"id": 48, "name": "No stage", "user_ids": [UID], "state": "01_in_progress"},
    49: {"id": 49, "name": "Shipped stage", "user_ids": [UID], "state": "01_in_progress", "stage_id": [4, "Shipped"]},
}
STAGES = {
    2: {"name": "In Progress", "fold": False},
    3: {"name": "Done", "fold": True},
    4: {"name": "Shipped", "fold": False},
}
DISPLAY = {
    ("res.users", UID): "Dev User",
    ("res.users", UID + 1): "Colleague",
    ("project.tags", 1): "bug",
    ("project.tags", 2): "export",
}
ATTACHMENTS = {
    77: {"id": 77, "name": "shot.png", "mimetype": "image/png", "file_size": 70, "datas": PNG_B64, "res_id": 42},
    78: {
        "id": 78,
        "name": "../evil.txt",
        "mimetype": "text/plain",
        "file_size": 5,
        "datas": base64.b64encode(b"hello").decode(),
        "res_id": 42,
    },
}
MESSAGES = [
    {"id": 1, "date": "2026-10-01 10:00:00", "author_id": [9, "ACME Contact"], "body": "<p>First</p>", "res_id": 42},
    {"id": 2, "date": "2026-10-02 11:00:00", "author_id": [7, "Dev User"], "body": "<p>Second</p>", "res_id": 42},
]


def _value(record: dict[str, Any], field: str) -> Any:
    if field.startswith("stage_id."):
        stage = record.get("stage_id")
        return STAGES[stage[0]][field.split(".", 1)[1]] if stage else None
    return record.get(field)


def _leaf(record: dict[str, Any], leaf: tuple[str, str, Any]) -> bool:
    field, op, value = leaf
    have = _value(record, field)
    if field == "stage_id" and isinstance(have, list):
        have = have[0]
    have_set = set(have) if isinstance(have, list) else {have}
    if op == "=":
        return have == value if value is not False else not have
    if op == "in":
        return bool(have_set & set(value))
    if op == "not in":
        return not (have_set & set(value))
    raise ValueError(f"fake Odoo: unsupported operator {op}")


def matches(record: dict[str, Any], domain: list[Any]) -> bool:
    """A domain in Odoo's prefix notation: leaves are ANDed unless a '|' or '&' says otherwise."""

    def parse(index: int) -> tuple[bool, int]:
        item = domain[index]
        if item in ("|", "&"):
            left, nxt = parse(index + 1)
            right, nxt = parse(nxt)
            return (left or right) if item == "|" else (left and right), nxt
        return _leaf(record, item), index + 1

    index, result = 0, True
    while index < len(domain):
        value, index = parse(index)
        result = result and value
    return result


class _Handler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/xmlrpc/2/common", "/xmlrpc/2/object")

    def do_POST(self) -> None:  # noqa: N802
        self.server.current_path = self.path  # type: ignore[attr-defined]
        super().do_POST()


class _Server(SimpleXMLRPCServer):
    def __init__(self, fake: FakeOdoo) -> None:
        super().__init__(("127.0.0.1", 0), requestHandler=_Handler, logRequests=False, allow_none=True)
        self.fake = fake
        self.current_path = ""

    def _dispatch(self, method: str, params: tuple[Any, ...]) -> Any:
        return self.fake._dispatch(self.current_path, method, params)


class FakeOdoo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (model, method)
        self.hide_companies = False  # True: the user cannot read their own company list
        self._server = _Server(self)
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> FakeOdoo:
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()

    # --- the fake Odoo ---------------------------------------------------------------------------------------------

    def _dispatch(self, path: str, method: str, params: tuple[Any, ...]) -> Any:
        if path.endswith("/common"):
            if method == "version":
                return {"server_version": "19.0"}
            if method == "authenticate":
                db, login, secret = params[0], params[1], params[2]
                return UID if (login, secret) == (LOGIN, SECRET) and db == "testdb" else False
        if path.endswith("/object") and method == "execute_kw":
            _db, uid, secret, model, meth, args, kwargs = params
            if (uid, secret) != (UID, SECRET):
                raise xmlrpc.client.Fault(1, "AccessDenied")
            self.calls.append((model, meth))
            return self._execute(model, meth, args, kwargs)
        raise xmlrpc.client.Fault(1, f"unknown {path} {method}")

    def _execute(self, model: str, meth: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        fields = kwargs.get("fields") or []
        if meth == "fields_get":
            return SCHEMA if model == "project.task" else {}
        if model == "res.users" and meth == "read" and "company_ids" in fields:
            if self.hide_companies:
                raise xmlrpc.client.Fault(3, "AccessError: cannot read company_ids")
            return [{"id": UID, "company_ids": [1, 2]}]
        if model == "project.task" and meth == "read":
            allowed = (kwargs.get("context") or {}).get("allowed_company_ids") or [1]
            for i in args[0]:
                company = TASKS.get(i, {}).get("company_id", 1)
                if company not in allowed:
                    raise xmlrpc.client.Fault(
                        4,
                        "Odoo Server Error\nThis seems to be a multi-company issue, you might be able to access the "
                        "record by switching to the company: Second Co.",
                    )
            return [{k: v for k, v in TASKS[i].items() if k in fields or k == "id"} for i in args[0] if i in TASKS]
        if model == "project.task" and meth == "search_read":
            rows = [t for t in TASKS.values() if matches(t, args[0])]
            rows.sort(key=lambda t: -t["id"])
            return [{k: v for k, v in t.items() if k in fields or k == "id"} for t in rows][: kwargs.get("limit", 80)]
        if meth == "read" and model in ("res.users", "project.tags"):
            return [{"id": i, "display_name": DISPLAY[(model, i)]} for i in args[0]]
        if model == "ir.attachment" and meth == "read":
            return [
                {k: v for k, v in ATTACHMENTS[i].items() if k in fields or k == "id"}
                for i in args[0]
                if i in ATTACHMENTS
            ]
        if model == "ir.attachment" and meth == "search_read":
            return [
                {k: v for k, v in a.items() if k in fields or k == "id"}
                for a in ATTACHMENTS.values()
                if a["res_id"] == 42
            ]
        if model == "mail.message" and meth == "search_read":
            rows = sorted(MESSAGES, key=lambda m: -m["id"])[: kwargs.get("limit", 80)]
            return [{k: v for k, v in m.items() if k in fields or k == "id"} for m in rows]
        raise xmlrpc.client.Fault(2, f"unsupported {model}.{meth}")
