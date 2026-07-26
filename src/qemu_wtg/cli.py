import argparse
import os
import shlex
import sys
from collections.abc import Callable

from . import config as config_mod
from . import disks as disks_mod
from . import firmware as firmware_mod
from . import planning
from . import sysinfo as sysinfo_mod


def _prompt_disk_choice(
    candidates: list[disks_mod.DiskCandidate],
) -> disks_mod.DiskCandidate | None:
    if not candidates:
        print(
            "No candidate disks found. If your Windows-To-Go drive isn't "
            "showing up, try `qemu-wtg configure --show-all-disks`.",
            file=sys.stderr,
        )
        return None

    print("Select the Windows-To-Go disk:")
    for i, candidate in enumerate(candidates, start=1):
        print(
            f"  {i}) {candidate.device}  {candidate.model}  {candidate.size_human}  ({candidate.by_id})"
        )

    while True:
        choice = input(f"Enter 1-{len(candidates)}: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]
        print("Invalid choice, try again.")


def _prompt_int(label: str, default: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if raw == "":
            return default
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Enter a positive integer.")


def _prompt_memory(label: str, default: str) -> str:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if raw == "":
            return default
        try:
            planning.parse_memory_bytes(raw)
        except ValueError:
            print("Enter a size like 8G, 512M, or a plain number of MiB.")
            continue
        return raw


def _prompt_choice(label: str, choices: tuple[str, ...], default: str) -> str:
    default_index = choices.index(default) + 1 if default in choices else 1
    print(f"{label}:")
    for i, choice in enumerate(choices, start=1):
        marker = " (default)" if i == default_index else ""
        print(f"  {i}) {choice}{marker}")

    while True:
        raw = input(f"Enter 1-{len(choices)} [{default_index}]: ").strip()
        if raw == "":
            return choices[default_index - 1]
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print("Invalid choice, try again.")


def _default_int(existing: config_mod.Config, key: str) -> int:
    return int(existing[key]) if key in existing else int(planning.FIXED_DEFAULTS[key])


def _default_str(existing: config_mod.Config, key: str) -> str:
    return str(existing[key]) if key in existing else str(planning.FIXED_DEFAULTS[key])


def cmd_configure(args: argparse.Namespace) -> int:
    candidates = disks_mod.list_candidate_disks(show_all=args.show_all_disks)
    chosen = _prompt_disk_choice(candidates)
    if chosen is None:
        return 1

    existing = config_mod.load_config() or {}
    cores = _prompt_int("Cores", _default_int(existing, "cores"))
    threads = _prompt_int("Threads", _default_int(existing, "threads"))
    memory = _prompt_memory("Memory", _default_str(existing, "memory"))
    vga = _prompt_choice("VGA device", planning.VGA_CHOICES, _default_str(existing, "vga"))
    display = _prompt_choice(
        "Display backend", planning.DISPLAY_CHOICES, _default_str(existing, "display")
    )

    config = {
        "disk_by_id": chosen.by_id,
        **planning.FIXED_DEFAULTS,
        "cores": cores,
        "threads": threads,
        "memory": memory,
        "vga": vga,
        "display": display,
    }
    config_mod.save_config(config)
    print(f"Saved config to {config_mod.config_path()}")
    return 0


def _yes_no(prompt: str) -> bool:
    answer = input(prompt).strip().lower()
    return answer in ("y", "yes")


def _confirm_launch(model: str, size_human: str, device: str) -> bool:
    prompt = f"About to boot {model} ({size_human}) via {device} -- continue? [y/N] "
    return _yes_no(prompt)


def cmd_run(args: argparse.Namespace) -> int:
    config = config_mod.load_config()
    if config is None:
        print("No config found. Run `qemu-wtg configure` first.", file=sys.stderr)
        return 1

    # Overrides apply to this run only -- `config` on disk is left untouched.
    overrides: dict[str, object] = {}
    if args.cores is not None:
        if args.cores <= 0:
            print(
                f"Invalid --cores value '{args.cores}'. Must be a positive integer.",
                file=sys.stderr,
            )
            return 1
        overrides["cores"] = args.cores
    if args.threads is not None:
        if args.threads <= 0:
            print(
                f"Invalid --threads value '{args.threads}'. Must be a positive integer.",
                file=sys.stderr,
            )
            return 1
        overrides["threads"] = args.threads
    if args.mem is not None:
        try:
            planning.parse_memory_bytes(args.mem)
        except ValueError:
            print(
                f"Invalid --mem value '{args.mem}'. Use a size like 8G, 512M, "
                "or a plain number of MiB.",
                file=sys.stderr,
            )
            return 1
        overrides["memory"] = args.mem
    if args.vga is not None:
        overrides["vga"] = args.vga
    if args.display is not None:
        overrides["display"] = args.display

    config = {**config, **overrides}

    ovmf_code_path = str(config.get("ovmf_code_path", planning.FIXED_DEFAULTS["ovmf_code_path"]))
    ovmf_error = firmware_mod.check_ovmf_code_path(ovmf_code_path)
    if ovmf_error is not None:
        print(ovmf_error, file=sys.stderr)
        return 1

    win_vars_path = str(config_mod.win_vars_path())
    ovmf_vars_template_path = firmware_mod.default_vars_template_path(ovmf_code_path)
    win_vars_error = firmware_mod.ensure_win_vars(win_vars_path, ovmf_vars_template_path)
    if win_vars_error is not None:
        print(win_vars_error, file=sys.stderr)
        return 1

    disk_by_id = config.get("disk_by_id")
    disk_inventory = disks_mod.resolve_disk_inventory(disk_by_id) if disk_by_id else {}
    mount_table = disks_mod.read_mounted_devices()

    plan = planning.plan_launch(
        config,
        disk_inventory,
        mount_table,
        win_vars_path,
        cpu_count=sysinfo_mod.cpu_count(),
        available_memory_bytes=sysinfo_mod.available_memory_bytes(),
    )
    if not plan.ok:
        print(plan.error, file=sys.stderr)
        return 1
    assert plan.argv is not None  # guaranteed by plan.ok, but not visible to mypy
    assert plan.resolved_device is not None

    if args.dry_run:
        print(shlex.join(["sudo", "qemu-system-x86_64", *plan.argv]))
        return 0

    if plan.warning is not None:
        print(f"Warning: {plan.warning}", file=sys.stderr)
        if not _yes_no("Continue anyway? [y/N] "):
            print("Aborted.", file=sys.stderr)
            return 1

    description = disks_mod.describe_disk(plan.resolved_device)
    if not _confirm_launch(description.model, description.size_human, plan.resolved_device):
        print("Aborted.", file=sys.stderr)
        return 1

    try:
        os.execvp("sudo", ["sudo", "qemu-system-x86_64", *plan.argv])
    except OSError as exc:
        print(f"Failed to launch: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qemu-wtg", description="Launch a Windows-To-Go USB drive in a QEMU/KVM VM."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure", help="Run the setup wizard.")
    configure_parser.add_argument(
        "--show-all-disks",
        action="store_true",
        help="Show all block devices, not just USB-attached ones.",
    )

    run_parser = subparsers.add_parser("run", help="Launch the VM using the saved config.")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the QEMU command without launching it.",
    )
    run_parser.add_argument(
        "--cores",
        type=int,
        default=None,
        help="Override the configured core count for this run only.",
    )
    run_parser.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Override the configured thread count for this run only.",
    )
    run_parser.add_argument(
        "--mem",
        type=str,
        default=None,
        help="Override the configured memory size (e.g. 8G) for this run only.",
    )
    run_parser.add_argument(
        "--vga",
        choices=planning.VGA_CHOICES,
        default=None,
        help="Override the configured VGA device for this run only.",
    )
    run_parser.add_argument(
        "--display",
        choices=planning.DISPLAY_CHOICES,
        default=None,
        help="Override the configured display backend for this run only.",
    )

    return parser


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "configure": cmd_configure,
    "run": cmd_run,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
