"""RS NF-11: rt convert handles a 10,000-row CSV in under 2 s (whole process, as a user runs it)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "convert" / "teams.base.yaml"


def _csv(rows: int, base: bool) -> str:
    lines = ["Projekt;Rozmiar;Zespół;Domena;Start;Zależności;Opis;Właściciel"]
    for i in range(rows):
        team = ("blik", "Aplikacja mobilna")[i % 2] if base else f"Zespół {i % 50}"
        dep = f"Projekt numer {i - 2} – łańcuch" if i % 7 == 3 else ""
        lines.append(
            f"Projekt numer {i} – łańcuch;{'SML'[i % 3]};{team};Domena {i % 50 // 10};"
            f'{2027 + i % 3}-{i % 12 + 1:02d}-15;{dep};"Opis; projekt {i}";Anna'
        )
    return "\r\n".join(lines) + "\r\n"


@pytest.mark.slow
@pytest.mark.parametrize("base", [False, True], ids=["skeleton", "base"])
def test_nf_11_ten_thousand_rows_under_two_seconds(tmp_path: Path, base: bool) -> None:
    path = tmp_path / "big.csv"
    path.write_text(_csv(10_000, base), encoding="utf-8-sig")
    argv = [sys.executable, "-m", "rt", "convert", str(path), "-o", str(tmp_path / "out.yaml"), "-q"]
    argv += [
        "--map",
        "Projekt=name,Rozmiar=size,Zespół=team,Domena=subdomain,Start=start,Zależności=depends_on,Opis=description",
    ]
    if base:
        argv += ["--base", str(BASE)]
    started = time.perf_counter()
    proc = subprocess.run(argv, capture_output=True, check=False, timeout=60)
    elapsed = time.perf_counter() - started
    assert proc.returncode == 0, proc.stderr.decode()
    assert (tmp_path / "out.yaml").read_text(encoding="utf-8").count("\n  - name: ") == 10_000
    assert elapsed < 2.0, f"{elapsed:.2f} s"
