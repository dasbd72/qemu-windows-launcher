# qemu-wtg

Launch a Windows-To-Go USB drive in a QEMU/KVM VM, without hand-editing a
`qemu-system-x86_64` command line.

## Usage

```
qemu-wtg configure               # pick your Windows-To-Go disk, save config
qemu-wtg configure --show-all-disks  # also show non-USB disks
qemu-wtg run --dry-run           # print the QEMU command without launching it
```

## Development setup

Requires [`uv`](https://docs.astral.sh/uv/).

```
uv sync
uv run pre-commit install
```

This installs the dev-only tooling (`ruff`, `mypy`, `pre-commit`) into a
local `.venv` and wires up the git hook, so `ruff check`/`ruff format`,
`mypy --strict`, and the test suite all run automatically before each
commit. The same checks run in CI on push/PR.

Run them by hand with:

```
uv run ruff check .
uv run ruff format .
uv run mypy --strict src/qemu_wtg
PYTHONPATH=src uv run python -m unittest discover -s tests -v
```
