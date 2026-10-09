# Contributing to odoo-task-fetch

Thank you for helping. Issues and pull requests are welcome.

## Principles

- **Read-only.** Never add a way to create, change or delete data in Odoo.
- **No secrets** in profiles, logs, arguments or error messages.
- **No dependencies.** The standard library is enough; ask before adding one.
- **Generic.** No company name, customer data, server address or personal path in code, tests, examples or docs.
- **Tested.** A change comes with a test; the fake Odoo in `tests/fake_odoo.py` makes that cheap.

## Setup

```bash
git clone https://github.com/adityaoryza/odoo-task-fetch.git
cd odoo-task-fetch
make test
make deps-dev && make lint     # ruff
```

## Pull requests

- Keep a pull request to one subject, with a clear title and a short description of what changed and why.
- Run `make test` and `make lint` first.
- Update `CHANGELOG.md` under *Unreleased* and the README when behaviour changes.

## Releasing (maintainers)

1. Update `__version__` in `src/odoo_task/__init__.py` and `version` in `pyproject.toml`; move the *Unreleased* entries of
   `CHANGELOG.md` under the new version.
2. `make lint && make test`.
3. `scripts/release.sh` builds `dist/` and prints the publishing commands (tag, then `gh release create` with the three
   files). It publishes nothing by itself.
4. Install the result once on a clean account before announcing it.
