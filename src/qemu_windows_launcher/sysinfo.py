"""Thin I/O wrappers over host CPU/memory capacity.

Deliberately untested (per the project's testing decisions): this module
only gathers plain data (CPU count, available memory) for the pure
`planning.plan_launch` seam to compare requested resources against.
Verified manually against the real system instead.
"""

import os


def cpu_count() -> int | None:
    return os.cpu_count()


def available_memory_bytes() -> int | None:
    """Read MemAvailable from /proc/meminfo, in bytes.

    Returns None if /proc/meminfo is missing or unparsable (e.g. non-Linux),
    so the caller can skip the capacity warning rather than compare against
    a bogus value.
    """
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None
