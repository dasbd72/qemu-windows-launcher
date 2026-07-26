"""Validating and self-healing the OVMF firmware files a launch depends on.

Runs before every launch. `win_vars.fd` is this tool's writable NVRAM store;
it's created from the system's OVMF_VARS template the first time it's
needed, and its ownership/permissions are corrected to the invoking user on
every run so a stale root- or sudo-created file can't silently block boot.
The read-only OVMF code image is only checked for existence -- fixing that
isn't this tool's job, so a missing path is reported as a clear error
instead of being handed to QEMU as-is.
"""

import os
import shutil
import stat
import subprocess

_OWNER_RW = 0o600
_VARS_TEMPLATE_NAME = "OVMF_VARS.4m.fd"


def default_vars_template_path(ovmf_code_path: str) -> str:
    """The OVMF_VARS template sitting alongside the configured OVMF_CODE image.

    Distros ship both files in the same directory, so this tracks wherever
    `ovmf_code_path` points rather than needing its own config setting.
    """
    return os.path.join(os.path.dirname(ovmf_code_path), _VARS_TEMPLATE_NAME)


def ensure_win_vars(win_vars_path: str, ovmf_vars_template_path: str) -> str | None:
    """Ensure `win_vars_path` exists and is owned/writable by the current user.

    Copies it from `ovmf_vars_template_path` if missing. Returns an error
    message if it's missing and the template can't be found either;
    otherwise returns None once ownership and permissions are corrected.
    """
    if not os.path.exists(win_vars_path):
        if not os.path.exists(ovmf_vars_template_path):
            return (
                f"OVMF variables template not found at '{ovmf_vars_template_path}'. "
                "Install edk2-ovmf, or fix ovmf_code_path in your qemu-wtg config via "
                "`configure`."
            )
        os.makedirs(os.path.dirname(win_vars_path), exist_ok=True)
        shutil.copyfile(ovmf_vars_template_path, win_vars_path)

    _fix_ownership_and_permissions(win_vars_path)
    return None


def _fix_ownership_and_permissions(path: str) -> None:
    st = os.stat(path)
    uid, gid = os.getuid(), os.getgid()
    if st.st_uid != uid or st.st_gid != gid:
        # A previous run under sudo, or a manual `cp`, can leave this
        # root-owned -- which means even chown'ing it *to* ourselves needs
        # root, since only the owner or root may call chown().
        try:
            os.chown(path, uid, gid)
        except PermissionError:
            subprocess.run(["sudo", "chown", f"{uid}:{gid}", path], check=True)
        st = os.stat(path)

    mode = stat.S_IMODE(st.st_mode)
    if mode & _OWNER_RW != _OWNER_RW:
        try:
            os.chmod(path, mode | _OWNER_RW)
        except PermissionError:
            subprocess.run(["sudo", "chmod", "u+rw", path], check=True)


def check_ovmf_code_path(ovmf_code_path: str) -> str | None:
    """Check the configured OVMF code image exists.

    Returns an actionable error message if it doesn't, so a bad path is
    caught here rather than surfacing as an opaque QEMU startup failure.
    """
    if not os.path.exists(ovmf_code_path):
        return (
            f"OVMF code firmware not found at '{ovmf_code_path}'. Install "
            "edk2-ovmf, or fix ovmf_code_path in your qemu-wtg config via `configure`."
        )
    return None
