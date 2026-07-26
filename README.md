# qemu-wtg

Launch a Windows-To-Go USB drive in a QEMU/KVM VM, without hand-editing a
`qemu-system-x86_64` command line.

## Usage

```
qemu-wtg configure               # pick your Windows-To-Go disk, save config
qemu-wtg configure --show-all-disks  # also show non-USB disks
qemu-wtg run --dry-run           # print the QEMU command without launching it
```

## Config

Settings are saved to `$XDG_CONFIG_HOME/qemu-wtg/config.json` (falling back
to `~/.config/qemu-wtg/config.json`) by `configure`. `ovmf_code_path` points
at the host's read-only OVMF code image; it defaults to
`/usr/share/ovmf/x64/OVMF_CODE.4m.fd` and can be overridden by hand-editing
the file if your distro puts it somewhere else. `run` refuses to launch
QEMU with a missing path here rather than passing it straight through.

`win_vars.fd`, this VM's writable NVRAM store, lives at
`$XDG_CONFIG_HOME/qemu-wtg/win_vars.fd`. `run` creates it on first use by
copying `OVMF_VARS.4m.fd` from the same directory as `ovmf_code_path`, and
corrects its ownership/permissions to the invoking user on every run.

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
