PYTHON ?= python3
TARGET ?= aarch64-apple-darwin
JOBS ?= 10

.PHONY: build verify package repro controller-test fetch doctor clean lint

fetch:
	$(PYTHON) build.py fetch --target $(TARGET)

doctor:
	$(PYTHON) build.py doctor --target $(TARGET)

build: fetch
	$(PYTHON) build.py build --target $(TARGET) --jobs $(JOBS)
	$(PYTHON) build.py package --target $(TARGET)

package:
	$(PYTHON) build.py package --target $(TARGET)

verify:
	$(PYTHON) build.py qualify --target $(TARGET)
	$(PYTHON) build.py check-budgets --target $(TARGET)

repro:
	$(PYTHON) build.py reproduce --target $(TARGET) --jobs $(JOBS)

controller-test:
	$(PYTHON) build.py controller-test

clean:
	rm -rf build dist .venv .ruff_cache .work/tmp
	find . -path './.git' -prune -o -path './.work' -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +

lint:
	uv run --frozen ruff check build.py buildsys tests
	uv run --frozen ty check build.py buildsys tests
