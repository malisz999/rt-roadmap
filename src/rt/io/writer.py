"""Atomic file writes (RS CLI-3, ADS 8.4): a failed run never leaves a partial or corrupted file."""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from pathlib import Path


def _target_mode(path: Path) -> int:
    """Keep an existing file's permission bits; a new file gets 0o666 minus the umask, like open() would."""
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        umask = os.umask(0)
        os.umask(umask)
        return 0o666 & ~umask


def _is_special(path: Path) -> bool:
    """An existing target that is neither a regular file nor a directory: a character device, FIFO or socket."""
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))


def atomic_write(path: str | Path, data: bytes, *, exclusive: bool = False) -> None:
    """Write `data` to a temporary file in the target's directory, fsync it, then rename it over `path`.

    `exclusive=True` raises FileExistsError when `path` already exists (rt init without --force). On any failure
    the temporary file is removed and the OSError propagates.
    """
    target = Path(path)
    if exclusive and (target.exists() or target.is_symlink()):
        raise FileExistsError(17, "File exists", str(path))
    if _is_special(target):
        # Devices and pipes (-o /dev/null, a FIFO) cannot be replaced by a rename; write to them directly.
        with open(target, "wb") as handle:
            handle.write(data)
        return
    directory = target.parent if str(target.parent) else Path(".")
    mode = _target_mode(target)
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(OSError):
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
