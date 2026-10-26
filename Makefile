PYTHON ?= python3
TARGET ?= aarch64-apple-darwin

.PHONY: controller-test fetch doctor clean

controller-test:
	$(PYTHON) build.py controller-test

fetch:
	$(PYTHON) build.py fetch --target $(TARGET)

doctor:
	$(PYTHON) build.py doctor --target $(TARGET)

clean:
	rm -rf build dist .work/tmp
