# odoo-task-fetch: developer tasks.   `make help` lists them.
SHELL := bash
PYTHON ?= python3
export PYTHONPATH := src:tests
RUFF ?= $(shell command -v ruff 2>/dev/null || echo '$(PYTHON) -m ruff')

.PHONY: help test lint deps-dev install uninstall release

help: ## show this help
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

test: ## unit tests (no Odoo needed)
	$(PYTHON) -m unittest discover -s tests/unit -t . </dev/null

lint: ## ruff (install it with `make deps-dev`) and shell syntax
	bash -n bin/odoo-task scripts/install.sh scripts/release.sh
	$(RUFF) check src tests
	$(RUFF) format --check src tests

deps-dev: ## install the development tools (ruff)
	$(PYTHON) -m pip install --user -r requirements-dev.txt

install: ## put `odoo-task` on your PATH (any shell) from this checkout. System-wide: make install PREFIX=/usr/local
	scripts/install.sh install $(if $(PREFIX),--prefix "$(PREFIX)")

uninstall: ## remove the command and the PATH lines added by `make install`
	scripts/install.sh uninstall $(if $(PREFIX),--prefix "$(PREFIX)")

release: ## build the release files in ./dist (publishes nothing)
	scripts/release.sh
