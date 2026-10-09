import unittest

from fake_odoo import LOGIN, SECRET, FakeOdoo
from odoo_task.client import READ_ONLY_METHODS, OdooClient, OdooError, normalize_url


class ReadOnlyClient(unittest.TestCase):
    def test_only_read_methods_are_allowed(self):
        self.assertEqual(READ_ONLY_METHODS, {"search_read", "read", "search", "search_count", "fields_get"})

    def test_writes_are_refused_before_anything_is_sent(self):
        with FakeOdoo() as odoo:
            client = OdooClient(odoo.url, "testdb", LOGIN, SECRET)
            for method in ("write", "create", "unlink", "copy", "action_done", "execute"):
                with self.assertRaises(OdooError):
                    client.execute("project.task", method, [[1], {}])
            self.assertEqual(odoo.calls, [])  # nothing reached the server

    def test_connect_and_read(self):
        with FakeOdoo() as odoo:
            client = OdooClient(odoo.url, "testdb", LOGIN, SECRET)
            self.assertEqual(client.version()["server_version"], "19.0")
            self.assertEqual(client.connect(), 7)
            self.assertEqual(client.read("project.task", [43], ["name"])[0]["name"], "Second")

    def test_wrong_credentials(self):
        with FakeOdoo() as odoo:
            client = OdooClient(odoo.url, "testdb", LOGIN, "BAD-KEY-12345")
            with self.assertRaises(OdooError) as ctx:
                client.connect()
            self.assertIn("Authentication failed", str(ctx.exception))
            self.assertNotIn("BAD-KEY-12345", str(ctx.exception))

    def test_secret_never_appears_in_repr(self):
        client = OdooClient("http://localhost:1", "d", "u", "TOP-SECRET-KEY")
        self.assertNotIn("TOP-SECRET-KEY", repr(client))
        self.assertNotIn("TOP-SECRET-KEY", str(client.__dict__.get("url")))

    def test_unreachable_server_is_a_clear_error(self):
        client = OdooClient("http://127.0.0.1:1", "d", "u", "UNREACHABLE-KEY-1", timeout=2)
        with self.assertRaises(OdooError) as ctx:
            client.connect()
        self.assertIn("Cannot reach", str(ctx.exception))
        self.assertNotIn("UNREACHABLE-KEY-1", str(ctx.exception))

    def test_urls(self):
        self.assertEqual(normalize_url(" https://x.example.com/ "), "https://x.example.com")
        for bad in (
            "",
            "file:///etc/passwd",
            "ftp://x",
            "javascript:alert(1)",
            "https://",
            "a b",
            "x.example.com:99999999",
        ):
            with self.assertRaises(OdooError, msg=bad):
                normalize_url(bad)

    def test_a_bare_host_gets_a_scheme(self):
        self.assertEqual(normalize_url("odoo.example.com"), "https://odoo.example.com")
        self.assertEqual(normalize_url("odoo.example.com:8443/"), "https://odoo.example.com:8443")
        self.assertEqual(normalize_url("localhost:8069"), "http://localhost:8069")
        self.assertEqual(normalize_url("127.0.0.1:8069"), "http://127.0.0.1:8069")


if __name__ == "__main__":
    unittest.main()


class MultiCompany(unittest.TestCase):
    def test_the_companies_of_the_user_are_sent_with_every_call(self):
        with FakeOdoo() as odoo:
            client = OdooClient(odoo.url, "testdb", LOGIN, SECRET)
            client.connect()
            self.assertEqual(client.company_ids, [1, 2])
            # task 30 belongs to company 2: readable only because company 2 is in the context
            self.assertEqual(client.read("project.task", [30], ["name"])[0]["name"], "Other company")

    def test_without_the_list_of_companies_the_error_is_explained(self):
        with FakeOdoo() as odoo:
            odoo.hide_companies = True
            client = OdooClient(odoo.url, "testdb", LOGIN, SECRET)
            client.connect()  # a failure to read the companies never stops the work
            self.assertEqual(client.company_ids, [])
            with self.assertRaises(OdooError) as ctx:
                client.read("project.task", [30], ["name"])
            message = str(ctx.exception)
            self.assertIn("multi-company", message)
            self.assertIn("ask an admin", message)

    def test_a_context_given_by_the_caller_is_kept(self):
        with FakeOdoo() as odoo:
            client = OdooClient(odoo.url, "testdb", LOGIN, SECRET)
            client.connect()
            rows = client.execute(
                "project.task", "read", [[43]], {"fields": ["name"], "context": {"allowed_company_ids": [1]}}
            )
            self.assertEqual(rows[0]["name"], "Second")
