"""Thin I/O wrappers over the system's block-device state.

Deliberately untested (per the project's testing decisions): this module
only gathers plain data (candidate disks, by-id -> device resolution) for
the pure `planning.plan_launch` seam to work with. Verified manually against
the real system instead.
"""

import os
import subprocess
from dataclasses import dataclass

BY_ID_DIR = "/dev/disk/by-id"
SYS_BLOCK_DIR = "/sys/block"

# /sys/block lists every whole-disk block device (partitions live nested
# under their disk's own directory, not as top-level entries here) -- but it
# also includes non-physical-disk categories we don't want to offer as a
# Windows-To-Go boot target.
_EXCLUDED_NAME_PREFIXES = ("loop", "sr", "dm-", "md", "zram")


@dataclass
class DiskCandidate:
    by_id: str
    device: str
    model: str
    size_human: str
    bus: str


def _udev_property(device: str, key: str) -> str | None:
    try:
        result = subprocess.run(
            ["udevadm", "info", "--query=property", f"--name={device}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    prefix = f"{key}="
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def _size_human(device_name: str) -> str:
    try:
        with open(f"{SYS_BLOCK_DIR}/{device_name}/size") as f:
            size_bytes = int(f.read().strip()) * 512
    except (OSError, ValueError):
        return "unknown size"

    size = float(size_bytes)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def _find_by_id_path(device: str) -> str | None:
    """Find a stable /dev/disk/by-id/... path that resolves to `device`.

    Returns None if no by-id entry exists for it -- such a disk can't be
    safely remembered across device-letter reshuffles, so it's skipped
    rather than offered as a pickable candidate.
    """
    if not os.path.isdir(BY_ID_DIR):
        return None
    matches = [
        os.path.join(BY_ID_DIR, name)
        for name in os.listdir(BY_ID_DIR)
        if os.path.exists(os.path.join(BY_ID_DIR, name))
        and os.path.realpath(os.path.join(BY_ID_DIR, name)) == device
    ]
    if not matches:
        return None
    return min(matches)


def list_candidate_disks(show_all: bool = False) -> list[DiskCandidate]:
    """List whole-disk block devices, defaulting to USB-attached ones only."""
    if not os.path.isdir(SYS_BLOCK_DIR):
        return []

    candidates: list[DiskCandidate] = []
    for name in sorted(os.listdir(SYS_BLOCK_DIR)):
        if name.startswith(_EXCLUDED_NAME_PREFIXES):
            continue

        device = f"/dev/{name}"
        bus = _udev_property(device, "ID_BUS") or "unknown"
        if not show_all and bus != "usb":
            continue

        by_id = _find_by_id_path(device)
        if by_id is None:
            continue  # no stable identifier available -- can't safely persist this choice

        candidates.append(
            DiskCandidate(
                by_id=by_id,
                device=device,
                model=_udev_property(device, "ID_MODEL") or "unknown model",
                size_human=_size_human(name),
                bus=bus,
            )
        )

    return candidates


def resolve_disk_inventory(disk_by_id: str) -> dict[str, str]:
    """Resolve a single configured by-id path to its current device.

    Returns an empty mapping if the by-id path no longer exists, so
    `planning.plan_launch` sees a clean "not found" rather than silently
    resolving to whatever the stale path happens to point at.
    """
    if not os.path.exists(disk_by_id):
        return {}
    return {disk_by_id: os.path.realpath(disk_by_id)}
