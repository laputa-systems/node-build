PYTHON ?= python3
TARGET ?= aarch64-apple-darwin
RUFF_VERSION ?= 0.17.2

.PHONY: controller-test fetch doctor clean lint

controller-test:
	$(PYTHON) build.py controller-test

fetch:
	$(PYTHON) build.py fetch --target $(TARGET)

doctor:
	$(PYTHON) build.py doctor --target $(TARGET)

clean:
	rm -rf build dist .work/tmp

lint:
	uvx "ruff@$(RUFF_VERSION)" check build.py buildsys tests .github/scripts
