"""The plan_launch seam: pure decision logic for what to boot and how.

Everything here operates on plain data handed in by the CLI layer -- no
filesystem, subprocess, or environment access happens in this module. That
keeps disk selection and QEMU command assembly, the two places a mistake is
most costly, cheap to unit test.
"""

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


@dataclass
class LaunchPlan:
    ok: bool
    error: str | None
    resolved_device: str | None
    argv: list[str] | None


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


def plan_launch(config: Config, disk_inventory: dict[str, str], win_vars_path: str) -> LaunchPlan:
    """Resolve `config`'s chosen disk against `disk_inventory` and build the argv.

    `disk_inventory` maps a disk's stable /dev/disk/by-id path to its current
    resolved device node (e.g. /dev/sdb), for whichever by-id paths are
    currently present on the system.
    """
    disk_by_id = config.get("disk_by_id")
    if not disk_by_id:
        return LaunchPlan(
            ok=False,
            error="No disk configured. Run `qemu-wtg configure` first.",
            resolved_device=None,
            argv=None,
        )

    resolved_device = disk_inventory.get(disk_by_id)
    if resolved_device is None:
        return LaunchPlan(
            ok=False,
            error=(
                f"Configured disk '{disk_by_id}' was not found. It may be "
                "unplugged, or no longer exists. Run `qemu-wtg configure` to "
                "pick a disk again."
            ),
            resolved_device=None,
            argv=None,
        )

    argv = build_argv(config, resolved_device, win_vars_path)
    return LaunchPlan(ok=True, error=None, resolved_device=resolved_device, argv=argv)
