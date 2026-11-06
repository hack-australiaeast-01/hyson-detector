"""Render the Mermaid diagrams of docs/diagrams/*.md to PNG images in docs/img/ (used by docs/ARCHITECTURE.md and slides).

Each diagram is a ```mermaid block preceded by a comment <!-- img: NAME --> giving the output file name.
Needs: pip install playwright && playwright install chromium (or Microsoft Edge installed); internet access for mermaid.js.
Usage (from the repo root):  python docs/diagrams/render.py
"""
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
IMG = HERE.parent / "img"
HTML = """<html><body style='background:white;margin:0'><div id=o></div><script type=module>
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({startOnLoad:false, theme:'default', securityLevel:'loose'});
window.render = async (id, c) => { try { const {svg} = await mermaid.render(id, c); document.getElementById('o').innerHTML = svg;
  return 'ok'; } catch(e) { return 'ERR ' + e.message; } };
window.ready = true;</script></body></html>"""


def diagrams():
    for md in sorted(HERE.glob("*.md")):
        for name, code in re.findall(r"<!-- img: (\w+) -->\s*```mermaid\n(.*?)```", md.read_text(encoding="utf-8"), re.S):
            yield md.name, name, code


def main():
    IMG.mkdir(exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2200, "height": 1400}, device_scale_factor=2)
        page.set_content(HTML)
        page.wait_for_function("window.ready === true", timeout=60000)
        bad = 0
        for src, name, code in diagrams():
            res = page.evaluate("([i, c]) => window.render(i, c)", ["d" + re.sub(r"\W", "", name), code])
            if res == "ok":
                page.locator("#o svg").screenshot(path=str(IMG / f"{name}.png"))
            else:
                bad += 1
            print(f"{'ok ' if res == 'ok' else 'ERR'} {src:<28} {name:<26} {'' if res == 'ok' else res[:200]}")
        browser.close()
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
