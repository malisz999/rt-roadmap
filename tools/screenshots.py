"""Screenshot review for RS AT-25 / NF-6 (ADS 10.1 "Visual" layer, release pipeline).

Renders EX, WE, DE and the products example (EX also with --summary and in overflow mode) and captures them in
Chromium, Firefox and WebKit, light and dark, plus an A3-landscape print PDF from Chromium. A human reviews the
images; the script also checks the things a machine can: sticky header and label column stay put after scrolling,
no element overflows the bar text, and the print stylesheet produces a PDF.

Usage:
  uv run --with playwright python -m playwright install chromium firefox webkit
  uv run --with playwright python tools/screenshots.py [--out DIR]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "docs" / "fixtures"
PAGES: dict[str, list[str]] = {
    "ex": [str(FIXTURES / "roadmap.example.yaml")],
    "ex-summary": [str(FIXTURES / "roadmap.example.yaml"), "--summary"],
    "we": [str(FIXTURES / "scheduling-worked-example.yaml"), "--summary"],
    "we-overflow": [str(FIXTURES / "scheduling-worked-example.yaml"), "--on-conflict", "overflow", "--summary"],
    "de": [str(FIXTURES / "dependencies-example.yaml")],
    "products": [str(FIXTURES / "products-example.yaml")],
}


def render(out: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for name, args in PAGES.items():
        target = out / f"{name}.html"
        subprocess.run([sys.executable, "-m", "rt", "render", *args, "-o", str(target), "-q"], check=True)
        files[name] = target
    return files


def check_sticky(page: Page) -> list[str]:
    """In a small window, scroll down and right; the timeline head must then sit at the top and the team labels
    at the left edge (RS OUT-6, ADS 7.2). Axes the page cannot scroll along are not judged."""
    problems: list[str] = []
    page.set_viewport_size({"width": 800, "height": 500})
    natural = page.evaluate("document.querySelector('.rt-timeline-head').getBoundingClientRect().top + window.scrollY")
    page.evaluate(f"window.scrollTo(400, {natural + 300})")
    page.wait_for_timeout(150)
    state = page.evaluate(
        """({x: window.scrollX, y: window.scrollY,
             head: document.querySelector('.rt-timeline-head').getBoundingClientRect().top,
             label: Math.min(...[...document.querySelectorAll('.rt-team__label')]
                    .map(e => e.getBoundingClientRect().left))})"""
    )
    if state["y"] > natural and abs(state["head"]) > 1:
        problems.append(f"timeline head not sticky (top={state['head']} at scrollY={state['y']})")
    if state["x"] > 0 and abs(state["label"]) > 1:
        problems.append(f"team labels not sticky (left={state['label']} at scrollX={state['x']})")
    page.evaluate("window.scrollTo(0, 0)")
    page.set_viewport_size({"width": 1600, "height": 1000})
    return problems


def check_labels(page: Page) -> list[str]:
    """Bar names (`.rt-bar__label`) must not spill out of their bar (ellipsis instead) and must not clip glyphs
    vertically: a name box shorter than its content cuts descenders (g, j, p, y) in some engines."""
    found = page.evaluate(
        """[...document.querySelectorAll('.rt-bar')].flatMap(b => {
             const bar = b.getBoundingClientRect();
             return [...b.querySelectorAll('.rt-bar__label')].flatMap(l => {
               const r = l.getBoundingClientRect();
               const out = [];
               const spill = r.width > 0 && (r.right > bar.right + 0.5 || r.left < bar.left - 0.5);
               if (spill) out.push(['spill', b.dataset.seq]);
               if (l.scrollHeight > l.clientHeight + 0.5) out.push(['clip', b.dataset.seq]);
               return out;
             });
           })"""
    )
    text = {"spill": "label spills out of bar", "clip": "label clips glyphs vertically in bar"}
    return [f"{text[kind]} seq {seq}" for kind, seq in found]


def capture_tooltip(page: Page, path: Path) -> list[str]:
    """Focus (keyboard style) the first delayed bar and capture the styled tooltip below it (ADS 7.2)."""
    bar = page.locator(".rt-bar--delayed").first
    bar.scroll_into_view_if_needed()
    bar.focus()
    if not page.evaluate("getComputedStyle(document.activeElement.querySelector('.rt-tip')).display !== 'none'"):
        bar.hover()  # some engines show :focus-visible only after keyboard input; :hover shows the same tooltip
    box = bar.bounding_box()
    tip = page.evaluate(
        "(() => { const t = document.querySelector('.rt-bar--delayed .rt-tip');"
        " return getComputedStyle(t).display; })()"
    )
    if box is not None:
        clip = {"x": max(box["x"] - 40, 0), "y": max(box["y"] - 40, 0), "width": 520, "height": 300}
        page.screenshot(path=str(path), clip=clip)
    return [] if tip != "none" else ["styled tooltip not shown on focus or hover"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "work" / "out" / "screenshots"))
    args = parser.parse_args()
    out = Path(args.out).resolve()  # page URIs need an absolute path
    out.mkdir(parents=True, exist_ok=True)
    files = render(out)
    problems: list[str] = []
    with sync_playwright() as pw:
        for engine in (pw.chromium, pw.firefox, pw.webkit):
            browser = engine.launch()
            for scheme in ("light", "dark"):
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme=scheme)
                for name, html in files.items():
                    page.goto(html.as_uri())
                    page.screenshot(path=str(out / f"{name}-{engine.name}-{scheme}.png"), full_page=True)
                    if scheme == "light":
                        problems += [f"{engine.name}/{name}: {p}" for p in check_sticky(page) + check_labels(page)]
                        if name == "ex":
                            tip = capture_tooltip(page, out / f"ex-tooltip-{engine.name}.png")
                            problems += [f"{engine.name}/{name}: {p}" for p in tip]
                page.close()
            if engine is pw.chromium:
                page = browser.new_page()
                page.goto(files["ex-summary"].as_uri())
                page.emulate_media(media="print")
                page.screenshot(path=str(out / "ex-summary-print.png"), full_page=True)
                page.pdf(path=str(out / "ex-summary-print.pdf"), prefer_css_page_size=True, print_background=True)
                page.close()
            browser.close()
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    print(f"screenshots in {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
