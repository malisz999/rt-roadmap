"""IOPort: the only object that touches files and standard streams (ADS 8.4, RS 6.5).

A spec is a path or "-" (standard input / standard output). Implementations: SystemIO (real) and FakeIO (tests).
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from typing import Protocol

STDIN_NAME = "<stdin>"
STDOUT_NAME = "<stdout>"
MAX_INPUT_BYTES = 5 * 1024 * 1024  # RS ST-5


class ClosedPipeError(Exception):
    """The reader closed stdout before rt finished writing (RS ST-6 → exit 141)."""


class IOPort(Protocol):
    def read(self, spec: str) -> tuple[bytes, str]:
        """Read all bytes of a path or of stdin ("-"); return them with the source name for messages
        (`<stdin>`, or the path as given). Reads at most MAX_INPUT_BYTES + 1 bytes so oversize is detectable.
        Raises OSError when the input cannot be read."""
        ...

    def write(self, spec: str, data: bytes, *, exclusive: bool = False) -> None:
        """Write all bytes at once to a path (atomically, RS CLI-3) or to stdout ("-", one write and flush).
        `exclusive=True` fails with FileExistsError when the file exists (rt init without --force).
        Raises OSError on I/O failure and ClosedPipeError when stdout's reader went away."""
        ...

    def stdin_is_tty(self) -> bool: ...

    def stderr_is_tty(self) -> bool: ...

    def err(self, text: str) -> None:
        """Write text to stderr (UTF-8); a newline is NOT added."""
        ...

    def getenv(self, name: str) -> str | None: ...


def _is_closed_pipe(exc: OSError) -> bool:
    """BrokenPipeError everywhere; on Windows a closed pipe shows up as EINVAL or EPIPE (ADS 8.4)."""
    if isinstance(exc, BrokenPipeError):
        return True
    return os.name == "nt" and exc.errno in (errno.EINVAL, errno.EPIPE)


class SystemIO:
    """The real IOPort: files on disk, the process's standard streams and environment."""

    def read(self, spec: str) -> tuple[bytes, str]:
        if spec == "-":
            stdin = sys.stdin
            if stdin is None:
                return b"", STDIN_NAME
            return stdin.buffer.read(MAX_INPUT_BYTES + 1), STDIN_NAME
        with open(spec, "rb") as handle:
            return handle.read(MAX_INPUT_BYTES + 1), spec

    def write(self, spec: str, data: bytes, *, exclusive: bool = False) -> None:
        if spec != "-":
            from rt.io.writer import atomic_write

            atomic_write(spec, data, exclusive=exclusive)
            return
        try:
            out = sys.stdout.buffer
            out.write(data)
            out.flush()
        except OSError as exc:
            if _is_closed_pipe(exc):
                raise ClosedPipeError from exc
            raise

    def stdin_is_tty(self) -> bool:
        stdin = sys.stdin
        return stdin is None or stdin.isatty()

    def stderr_is_tty(self) -> bool:
        stderr = sys.stderr
        return stderr is not None and stderr.isatty()

    def err(self, text: str) -> None:
        stderr = sys.stderr
        if stderr is None:
            return
        try:
            stderr.write(text)
            stderr.flush()
        except OSError:  # stderr closed: messages are lost, the exit code still tells
            pass

    def getenv(self, name: str) -> str | None:
        return os.environ.get(name)

    def silence_stdout(self) -> None:
        """After a closed pipe: point fd 1 at the null device so the interpreter's final flush cannot fail."""
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            os.close(devnull)
        except (OSError, ValueError, AttributeError):
            pass


class FakeIO:
    """In-memory IOPort for tests.

    - `stdin`: bytes returned by read("-"); `stdin_tty` / `stderr_tty`: what the tty checks answer.
    - `stdout`: bytes written to "-"; `stdout_writes`: how many writes went there; `stderr`: text written by err().
    - `files`: path -> bytes, read and written in memory. With `real_fs=True`, reads of paths missing from
      `files` (and existence checks for exclusive writes) fall back to the real file system; writes always stay
      in memory.
    - `closed_stdout=True` makes writes to "-" raise ClosedPipeError; `fail_write` / `fail_read` hold paths whose
      writes / reads raise PermissionError.
    """

    def __init__(
        self,
        stdin: bytes = b"",
        *,
        stdin_tty: bool = False,
        stderr_tty: bool = False,
        env: dict[str, str] | None = None,
        files: dict[str, bytes] | None = None,
        real_fs: bool = False,
        closed_stdout: bool = False,
    ) -> None:
        self.stdin = stdin
        self.stdin_tty = stdin_tty
        self.stderr_tty = stderr_tty
        self.env: dict[str, str] = dict(env or {})
        self.files: dict[str, bytes] = dict(files or {})
        self.real_fs = real_fs
        self.closed_stdout = closed_stdout
        self.fail_write: set[str] = set()
        self.fail_read: set[str] = set()
        self.stdout = b""
        self.stdout_writes = 0
        self.stdin_reads = 0
        self.stderr = ""
        self.silenced = False

    def read(self, spec: str) -> tuple[bytes, str]:
        if spec == "-":
            self.stdin_reads += 1
            return self.stdin[: MAX_INPUT_BYTES + 1], STDIN_NAME
        if spec in self.fail_read:
            raise PermissionError(errno.EACCES, "Permission denied", spec)
        if spec in self.files:
            return self.files[spec][: MAX_INPUT_BYTES + 1], spec
        if self.real_fs:
            with open(spec, "rb") as handle:
                return handle.read(MAX_INPUT_BYTES + 1), spec
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", spec)

    def write(self, spec: str, data: bytes, *, exclusive: bool = False) -> None:
        if spec == "-":
            if self.closed_stdout:
                raise ClosedPipeError
            self.stdout += data
            self.stdout_writes += 1
            return
        if spec in self.fail_write:
            raise PermissionError(errno.EACCES, "Permission denied", spec)
        if exclusive and self.exists(spec):
            raise FileExistsError(errno.EEXIST, "File exists", spec)
        self.files[spec] = bytes(data)

    def exists(self, spec: str) -> bool:
        return spec in self.files or (self.real_fs and Path(spec).exists())

    def stdin_is_tty(self) -> bool:
        return self.stdin_tty

    def stderr_is_tty(self) -> bool:
        return self.stderr_tty

    def err(self, text: str) -> None:
        self.stderr += text

    def getenv(self, name: str) -> str | None:
        return self.env.get(name)

    def silence_stdout(self) -> None:
        self.silenced = True
