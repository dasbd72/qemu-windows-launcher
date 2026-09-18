"""The plan_launch seam: pure decision logic for what to boot and how.

Everything here operates on plain data handed in by the CLI layer -- no
filesystem, subprocess, or environment access happens in this module. That
keeps disk selection and QEMU command assembly, the two places a mistake is
most costly, cheap to unit test.
"""

import re
from dataclasses import dataclass

from .config import Config

FIXED_DEFAULTS: Config = {
    "cores": 8,
    "threads": 2,
    "memory": "8G",
    "vga": "std",
    "display": "gtk",
    "ovmf_code_path": "/usr/share/ovmf/x64/OVMF_CODE.4m.fd",
}

VGA_CHOICES: tuple[str, ...] = ("std", "qxl", "virtio")
DISPLAY_CHOICES: tuple[str, ...] = ("gtk", "sdl", "none")

_MEMORY_SPEC_RE = re.compile(r"^(\d+)([KMGTkmgt]?)$")
_MEMORY_UNITS = {"": 1024**2, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}


def parse_memory_bytes(spec: str) -> int:
    """Parse a QEMU `-m`-style size spec (e.g. "8G", "512M") into bytes.

    A bare number with no suffix is mebibytes, matching QEMU's own default
    unit for `-m`. Raises ValueError if `spec` doesn't match that syntax.
    """
    match = _MEMORY_SPEC_RE.match(spec.strip())
    if match is None:
        raise ValueError(f"Invalid memory size: {spec!r}")
    value, unit = match.groups()
    return int(value) * _MEMORY_UNITS[unit.lower()]


def human_bytes(n: int) -> str:
    """Format a byte count as a human-readable size (e.g. 17179869184 -> "16.0G")."""
    size = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def _oversubscription_warning(
    config: Config, cpu_count: int | None, available_memory_bytes: int | None
) -> str | None:
    """Compare `config`'s requested cores/threads/memory against host capacity.

    Returns a human-readable warning if either is oversubscribed, or None if
    both fit (or the corresponding host figure is unavailable to compare
    against). The requested values are never rejected here -- only flagged,
    so the caller can ask the user to confirm before proceeding.
    """
    warnings: list[str] = []

    requested_vcpus = config["cores"] * config["threads"]
    if cpu_count is not None and requested_vcpus > cpu_count:
        warnings.append(
            f"Requested {requested_vcpus} vCPUs (cores={config['cores']} x "
            f"threads={config['threads']}) exceeds the host's {cpu_count} CPUs."
        )

    if available_memory_bytes is not None:
        requested_bytes = parse_memory_bytes(config["memory"])
        if requested_bytes > available_memory_bytes:
            warnings.append(
                f"Requested memory {config['memory']} exceeds the host's "
                f"available memory ({human_bytes(available_memory_bytes)})."
            )

    return " ".join(warnings) if warnings else None


@dataclass
class LaunchPlan:
    ok: bool
    error: str | None
    resolved_device: str | None
    argv: list[str] | None
    warning: str | None = None


def build_argv(config: Config, resolved_device: str, win_vars_path: str) -> list[str]:
    return [
        "-enable-kvm",
        "-cpu",
        "host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time",
        "-smp",
        f"cores={config['cores']},threads={config['threads']}",
        "-m",
        config["memory"],
        "-drive",
        f"if=pflash,format=raw,readonly=on,file={config['ovmf_code_path']}",
        "-drive",
        f"if=pflash,format=raw,file={win_vars_path}",
        "-device",
        "ahci,id=ahci",
        "-drive",
        f"file={resolved_device},format=raw,if=none,id=disk,aio=native,cache=none",
        "-device",
        "ide-hd,bus=ahci.0,drive=disk",
        "-usb",
        "-device",
        "usb-tablet",
        "-vga",
        config["vga"],
        "-display",
        config["display"],
    ]


def _mounted_partition_of(mount_table: list[str], disk_device: str) -> str | None:
    """Return the first entry of `mount_table` that is `disk_device` itself or
    one of its partitions (e.g. /dev/sdb1, or /dev/nvme0n1p2), or None.
    """
    for mounted in mount_table:
        if mounted == disk_device:
            return mounted
        if not mounted.startswith(disk_device):
            continue
        suffix = mounted[len(disk_device) :].removeprefix("p")
        if suffix.isdigit():
            return mounted
    return None


def plan_launch(
    config: Config,
    disk_inventory: dict[str, str],
    mount_table: list[str],
    win_vars_path: str,
    cpu_count: int | None = None,
    available_memory_bytes: int | None = None,
) -> LaunchPlan:
    """Resolve `config`'s chosen disk against `disk_inventory` and build the argv.

    `disk_inventory` maps a disk's stable /dev/disk/by-id path to its current
    resolved device node (e.g. /dev/sdb), for whichever by-id paths are
    currently present on the system. `mount_table` lists every /dev device
    path currently mounted on the host. `cpu_count` and
    `available_memory_bytes` are the host's capacity figures to warn against
    if the configured cores/threads/memory oversubscribe them; pass None to
    skip that check (e.g. when the figure couldn't be read).
    """
    disk_by_id = config.get("disk_by_id")
    if not disk_by_id:
        return LaunchPlan(
            ok=False,
            error="No disk configured. Run `qemu-windows-launcher configure` first.",
            resolved_device=None,
            argv=None,
        )

    resolved_device = disk_inventory.get(disk_by_id)
    if resolved_device is None:
        return LaunchPlan(
            ok=False,
            error=(
                f"Configured disk '{disk_by_id}' was not found. It may be "
                "unplugged, or no longer exists. Run `qemu-windows-launcher configure` to "
                "pick a disk again."
            ),
            resolved_device=None,
            argv=None,
        )

    mounted = _mounted_partition_of(mount_table, resolved_device)
    if mounted is not None:
        return LaunchPlan(
            ok=False,
            error=(
                f"Refusing to launch: '{mounted}' on disk '{resolved_device}' is "
                "currently mounted. Unmount it before launching, or run "
                "`qemu-windows-launcher configure` if this is the wrong disk."
            ),
            resolved_device=None,
            argv=None,
        )

    argv = build_argv(config, resolved_device, win_vars_path)
    warning = _oversubscription_warning(config, cpu_count, available_memory_bytes)
    return LaunchPlan(
        ok=True, error=None, resolved_device=resolved_device, argv=argv, warning=warning
    )
