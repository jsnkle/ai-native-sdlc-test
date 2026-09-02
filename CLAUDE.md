# claims-portal

A tiny claims status lookup service. This file is what a new joiner needs on day one; keep it under a page. Claude reads all of it at the start of every session.

**Working rule:** when Claude makes the same mistake twice, the correction goes in "Things Claude gets wrong" below, in the same PR that fixed it.

## Commands

All targets call `.venv/bin/python` directly, so the virtualenv must exist at `.venv/` first:
`python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`

- Build: `make build` (healthy output ends with `Build succeeded`; it is a byte-compile of `app/`)
- Test: `make test` (healthy output ends with `N passed in 0.0Ns`, e.g. `2 passed in 0.00s`; any `failed` or `error` is a failure)
- Lint: `make lint` (healthy output is only the echoed `pyflakes` command line with nothing after it; each problem prints as `path:line: message`)

There is no run target: the service is a library module with no web layer yet.

## Conventions

- Python 3.14, standard library only at runtime. Dev-only dependencies live in `requirements-dev.txt` (pytest, pyflakes). Adding a runtime dependency is a design decision for `spec.md`, not something to slip into a plan.
- Claim ids are strings shaped like `C-1001`. Statuses are lowercase snake_case strings (`received`, `in_review`, `approved`, `paid`).
- An unknown claim id raises `KeyError`. That is the tested contract; do not swallow it into a default.
- Tests are pytest, in `tests/test_<module>.py`, one test module per `app/` module. Every behaviour change ships with a test in the same PR.
- Every change starts as `intent/<change-slug>/intent.md`, then `spec.md`, then `plan.md` (see `intent/README.md`). PR review follows the passes in `REVIEW.md`.

## Architecture

- `app/` is the whole service. `app/claims.py` holds the in-memory status table (`STATUSES`) and the single lookup, `get_status`. There is no database, config, or HTTP layer.
- `tests/` mirrors `app/` one-to-one.
- There is no generated code. Protected paths are listed in `.claude/protected-paths` (currently empty) and a hook blocks edits there.

## Things Claude gets wrong

- Nothing recorded yet. Add a line the second time the same mistake happens.
- Any command containing both `deploy` and `production` is blocked by `.claude/hooks/production-gate.sh` until `RELEASE_APPROVAL` is set; there is no deploy target yet, and the pattern stays broad until one exists.

## Verifying your work

- Build: `make build` (must finish with `Build succeeded`)
- Test: `make test` (all green; never skip or delete a failing test)
- Lint: `make lint` (nothing printed after the command line)

Run all three before reporting any task complete, and paste the output. If a test fails, fix the code, not the test. During a fix task the `.claude/fix-task` marker is present and test files are locked by a hook; the failing test you were given is the proof, not something to edit.
