# qemu-wtg

Launch a Windows-To-Go USB drive in a QEMU/KVM VM, without hand-editing a
`qemu-system-x86_64` command line.

## Installation

On Arch Linux, install the `qemu-wtg-git` AUR package:

```
paru -S qemu-wtg-git
```

It's a VCS (`-git`) package: there's no tagged release process, so every
push to `main` is immediately installable via `paru -Syu`. `PKGBUILD` at
the repo root builds it, installing `qemu-wtg` to `/usr/bin` and pulling
in `qemu` and `edk2-ovmf` as dependencies.

## Usage

```
qemu-wtg configure               # pick your Windows-To-Go disk, save config
qemu-wtg configure --show-all-disks  # also show non-USB disks
qemu-wtg run --dry-run           # print the QEMU command without launching it
qemu-wtg run --cores 4 --threads 1 --mem 4G  # override cores/threads/memory for this run only
qemu-wtg run --vga qxl --display sdl  # override the VGA device/display backend for this run only
```

## Config

Settings are saved to `$XDG_CONFIG_HOME/qemu-wtg/config.json` (falling back
to `~/.config/qemu-wtg/config.json`) by `configure`. Alongside the disk
choice, `configure` prompts for cores, threads, and memory -- each prompt is
pre-filled with the current saved value (or the built-in default of
cores=8, threads=2, mem=8G the first time), so accepting the defaults is a
single keypress. It also offers a fixed picker for the VGA device
(`std`/`qxl`/`virtio`) and the display backend (`gtk`/`sdl`/`none`) --
picked by number, not typed freeform, so an unsupported combination can't
be entered by accident. `ovmf_code_path` points at the host's read-only
OVMF code image; it defaults to `/usr/share/ovmf/x64/OVMF_CODE.4m.fd` and
can be overridden by hand-editing the file if your distro puts it
somewhere else. `run` refuses to launch QEMU with a missing path here
rather than passing it straight through.

`run --cores`/`--threads`/`--mem`/`--vga`/`--display` override the saved
config for that invocation only -- they're never written back to
`config.json`. `--vga`/`--display` are restricted to the same fixed choices
as the `configure` picker. If the requested `cores x threads` exceeds the
host's CPU count, or the requested memory exceeds what `/proc/meminfo`
reports as available, `run` prints a warning and asks for a yes/no
confirmation before proceeding; the oversubscribed values are still used
if you confirm.

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

## License

MIT -- see [LICENSE](LICENSE).
