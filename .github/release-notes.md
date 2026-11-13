## Downloads

| File | For |
| --- | --- |
| `rt-<version>-macos-arm64` | macOS on Apple silicon (M1 and later) |
| `rt-<version>-linux-x86_64` | Linux x86_64 with glibc 2.28 or later (RHEL/Alma/Rocky 8+, Debian 11+, Ubuntu 20.04+, WSL) |
| `rt-<version>-windows-x86_64.exe` | Windows 10/11, x86_64 |
| `rt_roadmap-<version>-py3-none-any.whl` | Any OS with Python 3.12+: `uv tool install ./rt_roadmap-…whl` or `pipx install …` |
| `SHA256SUMS` | Checksums of all files |

Each binary is a single self-contained program: no Python needed. Rename it to `rt` (`rt.exe`), put it on your
`PATH`, and run `rt --version`.

## First run: the binaries are not code-signed

- **macOS:** make it executable and remove the download quarantine, then run it:

  ```bash
  chmod +x rt-*-macos-arm64 && xattr -d com.apple.quarantine rt-*-macos-arm64
  ```

  (Or run it once, then allow it under System Settings → Privacy & Security.)
- **Linux:** `chmod +x rt-*-linux-x86_64`.
- **Windows:** SmartScreen may say "Windows protected your PC": choose *More info* → *Run anyway*. Your
  company's antivirus may also need to allow it.

Verify a download with `shasum -a 256 -c SHA256SUMS --ignore-missing` (macOS/Linux) or
`Get-FileHash rt-*.exe` (PowerShell).

See `docs/manual/user-manual.pdf` and `docs/manual/cheat-sheet.pdf` in the repository for how to use rt.
