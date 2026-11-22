PYTHON ?= sh bootstrap/buildlib-run --
TARGET ?= aarch64-apple-darwin
JOBS ?= 10
BOOTSTRAP ?= bootstrap/buildlib-run

.PHONY: test coverage build verify package repro controller-test fetch doctor clean lint setup bench bench-check bench-list

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

setup:
	sh scripts/setup-dev

clean:
	@for artifact in ./build ./dist ./.ruff_cache; do \
	  if test -L "$$artifact" || { test -e "$$artifact" && ! test -d "$$artifact"; }; then \
	    printf '%s\n' "make clean: $$artifact must be a local build directory" >&2; exit 1; \
	  fi; \
	done
	rm -rf -- ./build ./dist ./.ruff_cache

# Ruff and ty are development tools pinned in uv.lock (`make setup` installs
# them); the controller runs through the vendored buildlib bootstrap.
lint:
	uv run --frozen ruff check build.py buildsys tests
	uv run --frozen ty check build.py buildsys tests

test: controller-test

bench:
	$(PYTHON) -m buildsys.bench run $(BENCH_ARGS)

bench-check:
	$(PYTHON) -m buildsys.bench check $(BENCH_ARGS)

bench-list:
	$(PYTHON) -m buildsys.bench list
