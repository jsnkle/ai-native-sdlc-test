.PHONY: build test lint run
build:
	.venv/bin/python -m compileall -q app && echo "Build succeeded"
test:
	.venv/bin/python -m pytest -q
lint:
	.venv/bin/python -m pyflakes app tests ops
run:
	.venv/bin/python -m app.server
