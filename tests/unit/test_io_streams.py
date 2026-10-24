"""io.streams (SystemIO, FakeIO) and io.writer.atomic_write (RS CLI-3, ST-4, ST-6; ADS 8.4)."""

from __future__ import annotations

import errno
import io
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from rt.io import streams
from rt.io.streams import MAX_INPUT_BYTES, ClosedPipeError, FakeIO, SystemIO
from rt.io.writer import atomic_write


def test_atomic_write_creates_and_replaces(tmp_path: Path) -> None:
    target = tmp_path / "out.html"
    atomic_write(target, b"one")
    assert target.read_bytes() == b"one"
    atomic_write(str(target), b"two")
    assert target.read_bytes() == b"two"
    assert [p.name for p in tmp_path.iterdir()] == ["out.html"]


def test_atomic_write_exclusive(tmp_path: Path) -> None:
    target = tmp_path / "roadmap.yaml"
    atomic_write(target, b"a", exclusive=True)
    with pytest.raises(FileExistsError):
        atomic_write(target, b"b", exclusive=True)
    assert target.read_bytes() == b"a"


def test_atomic_write_failure_leaves_no_temp_and_keeps_old(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "out.html"
    target.write_bytes(b"old")

    def boom(src: Any, dst: Any) -> None:
        raise OSError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.html"]


def test_atomic_write_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        atomic_write(tmp_path / "nope" / "x.html", b"x")


class _Buffer(io.BytesIO):
    def isatty(self) -> bool:
        return False


class _Stream:
    def __init__(self, data: bytes = b"", tty: bool = False, fail: OSError | None = None) -> None:
        self.buffer: Any = _Buffer(data)
        self.tty = tty
        self.fail = fail
        self.text = ""
        if fail is not None:
            failing = fail

            class _Broken(io.BytesIO):
                def write(self, b: Any) -> int:
                    raise failing

            self.buffer = _Broken()

    def isatty(self) -> bool:
        return self.tty

    def write(self, text: str) -> int:
        self.text += text
        return len(text)

    def flush(self) -> None:
        pass


def test_system_io_reads_stdin_bytes_with_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _Stream(b"x" * (MAX_INPUT_BYTES + 10)))
    data, name = SystemIO().read("-")
    assert name == "<stdin>" and len(data) == MAX_INPUT_BYTES + 1


def test_system_io_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "r.yaml"
    path.write_bytes(b"a: 1\n")
    assert SystemIO().read(str(path)) == (b"a: 1\n", str(path))
    with pytest.raises(OSError):
        SystemIO().read(str(tmp_path / "missing.yaml"))


def test_system_io_writes_stdout_bytes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _Stream()
    monkeypatch.setattr(sys, "stdout", out)
    SystemIO().write("-", "Płatności\n".encode())
    assert out.buffer.getvalue() == "Płatności\n".encode()


def test_system_io_closed_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Stream(fail=BrokenPipeError(errno.EPIPE, "broken")))
    with pytest.raises(ClosedPipeError):
        SystemIO().write("-", b"x")


def test_system_io_windows_einval_is_closed_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Stream(fail=OSError(errno.EINVAL, "invalid")))
    monkeypatch.setattr(streams.os, "name", "nt")
    with pytest.raises(ClosedPipeError):
        SystemIO().write("-", b"x")


def test_system_io_other_oserror_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Stream(fail=OSError(errno.ENOSPC, "full")))
    with pytest.raises(OSError) as info:
        SystemIO().write("-", b"x")
    assert not isinstance(info.value, ClosedPipeError)


def test_system_io_file_write_tty_err_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = SystemIO()
    target = tmp_path / "a.txt"
    port.write(str(target), b"ok")
    assert target.read_bytes() == b"ok"
    with pytest.raises(FileExistsError):
        port.write(str(target), b"no", exclusive=True)
    err = _Stream(tty=True)
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(sys, "stdin", _Stream(tty=True))
    port.err("hello\n")
    assert err.text == "hello\n"
    assert port.stderr_is_tty() and port.stdin_is_tty()
    monkeypatch.setenv("RT_TEST_VAR", "1")
    assert port.getenv("RT_TEST_VAR") == "1"


def test_system_io_without_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", None)
    assert SystemIO().stdin_is_tty()
    assert SystemIO().read("-") == (b"", "<stdin>")


def test_fake_io_round_trip(tmp_path: Path) -> None:
    fake = FakeIO(b"in", files={"a.yaml": b"A"}, env={"NO_COLOR": "1"}, stdin_tty=True, stderr_tty=True)
    assert fake.read("-") == (b"in", "<stdin>") and fake.stdin_reads == 1
    assert fake.read("a.yaml") == (b"A", "a.yaml")
    with pytest.raises(FileNotFoundError):
        fake.read("b.yaml")
    fake.write("-", b"x")
    fake.write("out", b"y")
    assert fake.stdout == b"x" and fake.stdout_writes == 1 and fake.files["out"] == b"y"
    with pytest.raises(FileExistsError):
        fake.write("out", b"z", exclusive=True)
    fake.err("e")
    assert fake.stderr == "e" and fake.getenv("NO_COLOR") == "1"
    assert fake.stdin_is_tty() and fake.stderr_is_tty()


def test_fake_io_failures_and_real_fs(tmp_path: Path) -> None:
    real = tmp_path / "r.yaml"
    real.write_bytes(b"R")
    fake = FakeIO(real_fs=True, closed_stdout=True)
    assert fake.read(str(real)) == (b"R", str(real))
    with pytest.raises(FileExistsError):
        fake.write(str(real), b"x", exclusive=True)
    with pytest.raises(ClosedPipeError):
        fake.write("-", b"x")
    fake.fail_read.add("p")
    fake.fail_write.add("q")
    with pytest.raises(PermissionError):
        fake.read("p")
    with pytest.raises(PermissionError):
        fake.write("q", b"")
    fake.silence_stdout()
    assert fake.silenced


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX device files")
def test_atomic_write_to_device_writes_directly() -> None:
    from rt.io.writer import atomic_write

    atomic_write("/dev/null", b"<html></html>")  # a rename over a device would fail
