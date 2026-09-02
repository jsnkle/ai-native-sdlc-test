.PHONY: build test lint
build:
	python3 -m compileall -q app && echo "Build succeeded"
test:
	python3 -m pytest -q
lint:
	python3 -m pyflakes app tests
