"""Build the single-file `rt` binary with PyInstaller and smoke-test it on the fixtures (ADS 11.3 release job).

Usage: uv run --with pyinstaller python tools/build_binary.py [--dist DIR]
Prints the path of the binary; exits non-zero when the build or a smoke test fails.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = [
    "scheduling-worked-example.yaml",
    "dependencies-example.yaml",
    "products-example.yaml",
    "roadmap.example.yaml",
]


def binary_name(version: str) -> str:
    system = {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux")
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    return f"rt-{version}-{system}-{arch}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "src"))
    from rt import __version__

    name = binary_name(__version__)
    with tempfile.TemporaryDirectory() as work:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--onefile",
                "--noconfirm",
                "--clean",
                "--name",
                name,
                "--distpath",
                args.dist,
                "--workpath",
                work,
                "--specpath",
                work,
                "--paths",
                str(ROOT / "src"),
                "--collect-data",
                "rt",
                "--collect-submodules",
                "rt",
                str(ROOT / "tools" / "pyinstaller_entry.py"),
            ],
            check=True,
        )
    exe = Path(args.dist) / (name + (".exe" if platform.system() == "Windows" else ""))
    version = subprocess.run([str(exe), "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if version != f"rt {__version__}":
        print(f"smoke test failed: --version printed {version!r}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as out:
        for fixture in FIXTURES:
            target = Path(out) / fixture.replace(".yaml", ".html")
            result = subprocess.run(
                [str(exe), "render", str(ROOT / "docs" / "fixtures" / fixture), "-o", str(target), "-q"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not target.read_bytes().startswith(b"<!doctype html>"):
                print(f"smoke test failed on {fixture}: exit {result.returncode}\n{result.stderr}", file=sys.stderr)
                return 1
    print(exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
