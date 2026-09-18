# qemu-windows-launcher

Launch a Windows-To-Go USB drive or Windows in another partition
in a QEMU/KVM VM, without hand-editing a
`qemu-system-x86_64` command line.

## Installation

On Arch Linux, install the `qemu-windows-launcher` AUR package:

```
paru -S qemu-windows-launcher
```

## Usage

```
qemu-windows-launcher configure               # pick your Windows-To-Go disk, save config
qemu-windows-launcher configure --show-all-disks  # also show non-USB disks
qemu-windows-launcher run --dry-run           # print the QEMU command without launching it
qemu-windows-launcher run --cores 4 --threads 1 --mem 4G  # override cores/threads/memory for this run only
qemu-windows-launcher run --vga qxl --display sdl  # override the VGA device/display backend for this run only
```

## Development setup

Requires [`uv`](https://docs.astral.sh/uv/).

```
uv sync
uv run pre-commit install
```

## License

MIT -- see [LICENSE](LICENSE).
