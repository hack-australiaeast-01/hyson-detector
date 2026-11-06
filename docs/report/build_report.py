"""build_report.py — turns Hyson_Detector_Report.md into a designed PDF.

    python build_report.py

Layout modelled on the PyraGrid business plan generator (cover, contents with page numbers, numbered sections, KPI cards,
inline SVG charts), restyled in Hyson colours. Markdown -> HTML -> headless Microsoft Edge "print to PDF", two passes so
the contents page shows real page numbers. Fonts are Windows system fonts (Bahnschrift, Segoe UI): nothing to license.
Every figure comes from the project's measured results (README, model card, jury handbook); nothing is invented here.
"""
from __future__ import annotations

import base64
import math
import re
import subprocess
import tempfile
from pathlib import Path

import markdown
from pypdf import PdfReader

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
LOGO = ROOT / "app" / "static" / "brand" / "logo_blue.png"
OUT = HERE / "Hyson_Detector_Report.pdf"
EDGE = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]

# Hyson palette: deep navy, bank blue, signal cyan
INK, BLUE, CYAN, MUTED, LINE, PAPER, NIGHT, SAND = "#0B1430", "#1E5BD8", "#22B8F0", "#5A6782", "#DCE3EE", "#F6F8FC", "#081634", "#EDF2FA"
GREY, RED, GREEN = "#A9B4C8", "#C8412B", "#12996B"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


LOGO_URI = "data:image/png;base64," + b64(LOGO.read_bytes())


# ------------------------------------------------------------------ chart helpers (inline SVG)
def nice_step(span: float, n: int = 5) -> float:
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    return next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)


def axis(lo, hi, x0, x1, sy, fmt) -> str:
    step = nice_step(hi - lo)
    v, out = math.floor(lo / step) * step, []
    while v <= hi + 1e-9:
        y = sy(v)
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="{INK if abs(v) < 1e-9 else LINE}" stroke-width="{1 if abs(v) < 1e-9 else .6}"/>'
                   f'<text x="{x0 - 6}" y="{y + 3:.1f}" text-anchor="end" class="ax">{fmt(v)}</text>')
        v += step
    return "".join(out)


def legend(items, x, y) -> str:
    out = []
    for label, color, kind in items:
        mark = (f'<rect x="{x}" y="{y - 7}" width="10" height="10" rx="2" fill="{color}"/>' if kind == "bar"
                else f'<line x1="{x - 1}" x2="{x + 11}" y1="{y - 2}" y2="{y - 2}" stroke="{color}" stroke-width="2.4" stroke-dasharray="4 2"/>')
        out.append(mark + f'<text x="{x + 16}" y="{y + 2}" class="lg">{label}</text>')
        x += 24 + len(label) * 5.7
    return "".join(out)


def svg(w, h, body, caption) -> str:
    return (f'<figure class="chart"><svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
            f'<figcaption>{caption}</figcaption></figure>')


def fmt_n(v):
    return f"{v:,.0f}"


# ------------------------------------------------------------------ charts
def chart_compare() -> str:
    W, H, l, r, t, b = 680, 235, 52, 14, 34, 28
    groups = ["Alerts", "Frauds caught", "False alerts"]
    series = [("Current rules engine", [3338, 117, 3221], GREY), ("Model, same alert volume", [3338, 787, 2551], CYAN),
              ("Model, top 1 % (analyst capacity)", [1779, 718, 1061], BLUE)]
    hi = 3700
    sy = lambda v: t + (hi - v) / hi * (H - t - b)
    gw = (W - l - r) / 3
    body = axis(0, hi, l, W - r, sy, lambda v: fmt_n(v))
    for i, g in enumerate(groups):
        x = l + gw * i
        for j, (_, vals, col) in enumerate(series):
            v, bx = vals[i], x + gw * (0.14 + 0.25 * j)
            body += f'<rect x="{bx:.1f}" y="{sy(v):.1f}" width="{gw * .22:.1f}" height="{sy(0) - sy(v):.1f}" fill="{col}" rx="2"/>'
            body += f'<text x="{bx + gw * .11:.1f}" y="{sy(v) - 5:.1f}" text-anchor="middle" class="vl">{fmt_n(v)}</text>'
        body += f'<text x="{x + gw / 2:.1f}" y="{H - 9}" text-anchor="middle" class="ax b">{g}</text>'
    body += legend([(s[0], s[2], "bar") for s in series], l, 13)
    return svg(W, H, body, "Validation June–July 2026 (177,953 operations, 1,013 frauds). Top 1 %: 6.1× more frauds caught with 47 % fewer alerts.")


def chart_rules() -> str:
    W, H, l = 680, 196, 210
    rules = [("R02 · foreign country", 10967, 1206, "11.0 %"), ("R01 · amount > 3,000 TND", 10726, 4, "0.04 %"),
             ("R03 · night, amount > 300 TND", 8403, 34, "0.4 %"), ("R05 · transfer > 4,000 TND", 4179, 2, "0.05 %"),
             ("R04 · > 5 transactions in 1 h", 2584, 0, "0.0 %")]
    mx, bw = 10967, W - l - 215
    body = legend([("Alerts raised", GREY, "bar"), ("Confirmed frauds", BLUE, "bar")], l, 13)
    for i, (name, a, f, p) in enumerate(rules):
        y = 30 + i * 32
        body += f'<text x="{l - 10}" y="{y + 13}" text-anchor="end" class="lg">{name}</text>'
        body += f'<rect x="{l}" y="{y}" width="{a / mx * bw:.1f}" height="18" rx="2" fill="{GREY if i else "#C9D3E3"}"/>'
        body += f'<rect x="{l}" y="{y}" width="{max(f / mx * bw, 1.5):.1f}" height="18" rx="2" fill="{BLUE}"/>'
        body += (f'<text x="{l + a / mx * bw + 8:.1f}" y="{y + 13}" class="vl">{fmt_n(a)}</text>'
                 f'<text x="{l + a / mx * bw + 52:.1f}" y="{y + 13}" class="ax" fill="{RED if i else GREEN}">{fmt_n(f)} frauds · {p}</text>')
    return svg(W, H, body, "Audit of the current rules on 32,065 legacy alerts with analyst verdicts. R04, R01 and R05 together: 17,489 alerts, 6 frauds.")


def chart_types() -> str:
    W, H, l = 680, 236, 170
    types = [("Account takeover", 89, 10), ("Cloned card abroad", 91, 100), ("ATM skimming", 74, 18),
             ("Stolen contactless card", 68, 0), ("Discreet online", 68, 13), ("Card testing", 61, 0)]
    bw = W - l - 60
    body = legend([("Model, top 1 %", BLUE, "bar"), ("Current rules", GREY, "bar")], l, 13)
    for i, (name, m, r) in enumerate(types):
        y = 28 + i * 34
        body += f'<text x="{l - 10}" y="{y + 15}" text-anchor="end" class="lg">{name}</text>'
        body += f'<rect x="{l}" y="{y}" width="{m / 100 * bw:.1f}" height="12" rx="2" fill="{BLUE}"/>'
        body += f'<text x="{l + m / 100 * bw + 6:.1f}" y="{y + 10}" class="vl">{m} %</text>'
        body += f'<rect x="{l}" y="{y + 14}" width="{max(r / 100 * bw, 1.5):.1f}" height="10" rx="2" fill="{GREY}"/>'
        body += f'<text x="{l + max(r / 100 * bw, 1.5) + 6:.1f}" y="{y + 23}" class="ax">{r} %</text>'
    return svg(W, H, body, "Recall by fraud type, validation June–July 2026. The legacy foreign-country rule is kept for cloned cards abroad.")


def chart_backtest() -> str:
    W, H, l, r, t, b = 680, 220, 52, 14, 34, 28
    per = [("Dec–Jan", 66.7), ("Feb–Mar", 68.8), ("Apr–May", 71.2), ("Jun–Jul", 70.9)]
    hi = 90
    sy = lambda v: t + (hi - v) / hi * (H - t - b)
    gw = (W - l - r) / 4
    body = axis(0, hi, l, W - r, sy, lambda v: f"{v:g} %")
    body += f'<rect x="{l}" y="{sy(71.5):.1f}" width="{W - l - r}" height="{sy(67.3) - sy(71.5):.1f}" fill="{CYAN}" opacity=".14"/>'
    for i, (p, v) in enumerate(per):
        x = l + gw * (i + .3)
        body += f'<rect x="{x:.1f}" y="{sy(v):.1f}" width="{gw * .4:.1f}" height="{sy(0) - sy(v):.1f}" fill="{BLUE}" rx="2"/>'
        body += f'<text x="{x + gw * .2:.1f}" y="{sy(v) - 6:.1f}" text-anchor="middle" class="vl">{v} %</text>'
        body += f'<text x="{l + gw * (i + .5):.1f}" y="{H - 9}" text-anchor="middle" class="ax b">{p}</text>'
    body += f'<line x1="{l}" x2="{W - r}" y1="{sy(12.6):.1f}" y2="{sy(12.6):.1f}" stroke="{RED}" stroke-width="2" stroke-dasharray="5 3"/>'
    body += legend([("Top-1 % recall, model re-trained on the past only", BLUE, "bar"), ("69.4 % ± 2.1 band", CYAN, "bar"),
                    ("Current rules, same periods: 12.6 %", RED, "line")], l, 13)
    return svg(W, H, body, "Rolling backtest: four re-trainings on the past only, each tested on the next two months.")


def chart_scenario() -> str:
    W, H, l = 680, 210, 230
    rows = [("Annual card-fraud exposure", 8.62, "#C9D3E3", "27.8 bn TND × 0.031 % (EU rate, assumed)"),
            ("Stopped by the rules (22.1 %)", 1.90, GREY, ""), ("Stopped by Hyson (67.7 %)", 5.83, BLUE, ""),
            ("Extra fraud stopped per year", 3.93, CYAN, "model − rules coverage, in value")]
    bw = W - l - 110
    body = ""
    for i, (name, v, col, note) in enumerate(rows):
        y = 16 + i * 40
        body += f'<text x="{l - 10}" y="{y + 15}" text-anchor="end" class="lg{" b" if i == 3 else ""}">{name}</text>'
        body += f'<rect x="{l}" y="{y}" width="{v / 8.62 * bw:.1f}" height="22" rx="3" fill="{col}"/>'
        body += f'<text x="{l + v / 8.62 * bw + 8:.1f}" y="{y + 15}" class="vl">≈ {v:.1f} M TND</text>'
        if note:
            body += f'<text x="{l}" y="{y + 34}" class="an">{note}</text>'
    body += f'<text x="{l}" y="{H - 8}" class="lg">≈ 2.0 million fewer false alerts per year (our reduction per operation × 163 m operations)</text>'
    return svg(W, H, body, "Tunisian-scale scenario (BCT 2024 volumes, EU fraud rate as assumption). A scenario, not a measurement.")


def chart_positioning() -> str:
    W, H, x0, y0, pw, ph = 680, 320, 70, 18, 560, 262
    sx = lambda v: x0 + v * pw
    sy = lambda v: y0 + (1 - v) * ph
    body = (f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="{SAND}" rx="6"/>'
            f'<rect x="{x0 + pw / 2}" y="{y0}" width="{pw / 2}" height="{ph / 2}" fill="#DCE8FB" rx="6"/>'
            f'<line x1="{x0 + pw / 2}" x2="{x0 + pw / 2}" y1="{y0}" y2="{y0 + ph}" stroke="{LINE}" stroke-width="1.2"/>'
            f'<line x1="{x0}" x2="{x0 + pw}" y1="{y0 + ph / 2}" y2="{y0 + ph / 2}" stroke="{LINE}" stroke-width="1.2"/>'
            f'<text x="{x0 + pw / 2}" y="{H - 10}" text-anchor="middle" class="ax">Flags operations  →  explains and guides the decision</text>'
            f'<text transform="translate(22 {y0 + ph / 2}) rotate(-90)" text-anchor="middle" class="ax">One signal  →  many sources connected</text>'
            f'<text x="{x0 + pw - 12}" y="{y0 + 20}" text-anchor="end" class="qd">ANALYST COPILOT</text>'
            f'<text x="{x0 + 12}" y="{y0 + ph - 12}" class="qd">SINGLE-RULE ALERTING</text>')
    players = [("Legacy rules engine", .10, .14), ("ML risk score (black box)", .22, .56), ("Case-management tool", .62, .22),
               ("Generic AI chatbot", .70, .36), ("Spreadsheet investigation", .40, .10)]
    for name, x, y in players:
        body += f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="6" fill="{INK}"/><text x="{sx(x) + 10:.1f}" y="{sy(y) + 4:.1f}" class="lg">{name}</text>'
    px, py = sx(.85), sy(.82)
    body += (f'<circle cx="{px:.1f}" cy="{py:.1f}" r="16" fill="{BLUE}" opacity=".18"/><circle cx="{px:.1f}" cy="{py:.1f}" r="8" fill="{BLUE}"/>'
             f'<text x="{px - 16:.1f}" y="{py + 5:.1f}" text-anchor="end" class="big" fill="{BLUE}">Hyson Detector</text>')
    return svg(W, H, body, "Positioning by category of tool, team assessment (not a vendor ranking).")


def chart_arch() -> str:
    W, H = 680, 300
    def box(x, y, w, h, title, lines, fill="#fff", stroke=LINE, tc=INK):
        s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        s += f'<text x="{x + w / 2}" y="{y + 16}" text-anchor="middle" class="bx" fill="{tc}">{title}</text>'
        for k, ln in enumerate(lines):
            s += f'<text x="{x + w / 2}" y="{y + 30 + k * 12}" text-anchor="middle" class="bs" fill="{tc if fill != "#fff" else MUTED}">{ln}</text>'
        return s
    def arrow(x1, y1, x2, y2, label=""):
        s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{BLUE}" stroke-width="1.5" marker-end="url(#ah)"/>'
        if label:
            s += f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 4}" text-anchor="middle" class="an">{label}</text>'
        return s
    body = (f'<defs><marker id="ah" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
            f'<path d="M0,0 L8,4 L0,8 z" fill="{BLUE}"/></marker></defs>')
    # lanes
    body += f'<rect x="96" y="6" width="300" height="288" rx="10" fill="{SAND}"/><text x="246" y="22" text-anchor="middle" class="qd">MICROSOFT FABRIC</text>'
    body += f'<rect x="410" y="6" width="130" height="288" rx="10" fill="#E7F6FD"/><text x="475" y="22" text-anchor="middle" class="qd">AZURE AI</text>'
    body += box(6, 40, 80, 62, "Bank data", ["Azure SQL", "transactions,", "digital events"])
    body += box(6, 200, 80, 62, "Other banks", ["any schema", "via the API"])
    body += box(108, 34, 130, 48, "Copy job → bronze", ["raw tables, run log"])
    body += box(108, 92, 130, 48, "Quality (41 rules)", ["every row, quarantine"])
    body += box(108, 150, 130, 48, "Silver → Gold", ["73 past-only features"])
    body += box(108, 208, 130, 62, "LightGBM + SHAP", ["scores, alert queue,", "explanations, MLflow"], fill=BLUE, stroke=BLUE, tc="#fff")
    body += box(252, 34, 132, 48, "Star schema (mart)", ["ask-the-data in SQL"])
    body += box(252, 92, 132, 48, "Power BI", ["Direct Lake, as code"])
    body += box(252, 150, 132, 48, "SQL endpoint", ["Entra ID, read-only"])
    body += box(252, 208, 132, 62, "Feedback", ["analyst decisions", "back to OneLake"])
    body += box(420, 34, 110, 62, "Azure OpenAI", ["gpt-5-mini", "copilot, assistant,", "reports"])
    body += box(420, 104, 110, 44, "Embeddings", ["16,302-case memory"])
    body += box(420, 176, 110, 44, "AI Foundry", ["judge agent"])
    body += box(420, 234, 110, 48, "Safety", ["filters + injection guard"])
    body += box(556, 34, 118, 126, "Hyson app", ["21 pages · FR / EN", "copilot · Nazar", "case file · reports", "bank integration API"], fill=NIGHT, stroke=NIGHT, tc="#fff")
    body += box(556, 176, 118, 44, "Fraud analyst", ["decides, logged"], fill="#fff")
    body += box(556, 232, 118, 44, "Risk manager", ["Power BI, reports"], fill="#fff")
    body += arrow(86, 71, 106, 58) + arrow(46, 198, 46, 106)
    body += f'<text x="51" y="150" class="an">same</text><text x="51" y="161" class="an">pipeline</text>'
    body += arrow(173, 82, 173, 90) + arrow(173, 140, 173, 148) + arrow(173, 198, 173, 206)
    body += arrow(238, 226, 250, 186)
    body += arrow(384, 168, 554, 156) + arrow(532, 64, 554, 70) + arrow(615, 160, 615, 174) + arrow(615, 220, 615, 230)
    body += (f'<polyline points="556,206 547,206 547,288 318,288 318,276" fill="none" stroke="{BLUE}" stroke-width="1.5" marker-end="url(#ah)"/>'
             f'<text x="470" y="284" text-anchor="middle" class="an">decisions</text>')
    return svg(W, H, body, "End-to-end architecture: data and model in Microsoft Fabric, language in Azure AI, decisions by people.")


def kpi_cards() -> str:
    cards = [("Frauds caught", "718", "vs 117 for the current rules"), ("Precision", "40.4 %", "vs 3.5 % · top 1 % of operations"),
             ("Recall", "70.9 %", "vs 11.5 % · CI 68.3–73.0 %"), ("False alerts avoided", "2,160", "1,061 left vs 3,221 today"),
             ("Fraud value stopped", "67.7 %", "vs 22.1 % for the rules"), ("PR-AUC", "0.646", "vs 0.014 for the rules"),
             ("Stable over time", "69.4 %", "recall ± 2.1 on 4 re-trainings"), ("Copilot accuracy", "18 / 18", "golden questions · 99.5 % grounded")]
    return '<div class="cards">' + "".join(
        f'<div class="card"><div class="c-l">{a}</div><div class="c-v">{b}</div><div class="c-s">{c}</div></div>' for a, b, c in cards) + "</div>"


CHARTS = {"compare": chart_compare, "rules": chart_rules, "types": chart_types, "backtest": chart_backtest,
          "scenario": chart_scenario, "positioning": chart_positioning, "arch": chart_arch}


# ------------------------------------------------------------------ document
def cover() -> str:
    stats = [("6×", "more frauds caught"), ("−47 %", "alerts for analysts"), ("67.7 %", "of fraud value stopped"), ("Day 0", "alert, vs 11 days to report")]
    return f"""
<section class="cover">
  <div class="cv-top"><span>Product, results &amp; business report</span><span>Confidential</span></div>
  <div class="cv-mid">
    <img class="cv-logo" src="{LOGO_URI}" alt="Hyson logo">
    <h1 class="cv-name">Hyson <span style="color: var(--blue)">Detector</span></h1>
    <p class="cv-tag">The AI copilot for bank fraud analysts: detect, explain, decide</p>
    <div class="cv-rule"></div>
    <p class="cv-sub">Microsoft Fabric · Azure OpenAI · Azure AI Foundry · Power BI</p>
  </div>
  <div class="cv-night">
    <div class="cv-stats">{"".join(f'<div><b>{v}</b><span>{k}</span></div>' for v, k in stats)}</div>
    <div class="cv-meta"><span>Team Hyson · DSI Forum Hackathon</span><span>Version 1.0 · November 2026</span><span>hyson-detector.streamlit.app</span></div>
  </div>
</section>"""


def toc(pages: dict[int, int]) -> str:
    items = []
    for n, title in SECTIONS:
        items.append(f'<li><a href="#{SLUG[n]}"><span class="t-n">{n:02d}</span><span class="t-t">{title}</span>'
                     f'<span class="t-d"></span><span class="t-p">{pages.get(n, "")}</span></a></li>')
    note = ("All Hyson figures are measured on the organisers' synthetic Tunisian bank in Microsoft Fabric (validation June–July 2026 "
            "unless stated). External benchmarks carry their source. Scale-ups are labelled <em>scenario</em>: they are orders of "
            "magnitude to discuss with a partner bank, not measurements.")
    return f'<section class="toc"><h2 class="toc-h">Contents</h2><ol>{"".join(items)}</ol><p class="toc-note">{note}</p></section>'


md = (HERE / "Hyson_Detector_Report.md").read_text(encoding="utf-8")
PB = '<div style="page-break-after: always;"></div>'
body_md = PB.join(md.split(PB)[2:])                 # drop the placeholder cover and contents; rebuilt below
html = markdown.markdown(body_md, extensions=["tables", "toc", "sane_lists"])

SECTIONS, SLUG = [], {}


def h2(mo):
    slug, n, title = mo.group(1), int(mo.group(2)), mo.group(3)
    SECTIONS.append((n, re.sub(r"<.*?>", "", title)))
    SLUG[n] = slug
    return (f'<h2 id="{slug}" class="sec"><span class="mk">@@S{n}@@</span>'
            f'<span class="num">{n:02d}</span><span class="t">{title}</span></h2>')


html = re.sub(r'<h2 id="([^"]+)">(\d+)\. (.*?)</h2>', h2, html)
html = re.sub(r"<!-- chart:(\w+) -->", lambda mo: CHARTS[mo.group(1)](), html)
html = html.replace("<!-- kpi-cards -->", kpi_cards())
html = re.sub(r"<tr>\s*<td><strong>", '<tr class="total"><td><strong>', html)
html = html.replace(PB, '<div class="pb"></div>')
html = html.replace('<h2 id="1-executive-summary"', '<div class="exec"><h2 id="1-executive-summary"', 1)
html = html.replace('<div class="pb"></div>', '</div><div class="pb"></div>', 1)

head_logo = "data:image/svg+xml;base64," + b64(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"><image href="{LOGO_URI}" width="18" height="18"/></svg>'.encode())

CSS = f"""
:root {{ --ink: {INK}; --blue: {BLUE}; --cyan: {CYAN}; --muted: {MUTED}; --line: {LINE}; --paper: {PAPER}; --night: {NIGHT}; --sand: {SAND};
  --display: "Bahnschrift", "Segoe UI", Arial, sans-serif; --body: "Segoe UI", "Helvetica Neue", Arial, sans-serif; }}
@page {{ size: A4; margin: 21mm 17mm 19mm 17mm;
  @top-left {{ content: url("{head_logo}") "  Hyson Detector"; font-family: var(--display); font-weight: 600; font-size: 10.5pt; color: {INK}; vertical-align: bottom; padding-bottom: 3mm; }}
  @top-right {{ content: "Product, results & business report  ·  2026"; font-family: "Segoe UI", Arial; font-size: 7.5pt; color: {MUTED}; vertical-align: bottom; padding-bottom: 3.6mm; }}
  @bottom-left {{ content: "Confidential  ·  November 2026"; font-family: "Segoe UI", Arial; font-size: 7.5pt; color: {MUTED}; vertical-align: top; padding-top: 4mm; }}
  @bottom-right {{ content: counter(page) " / " counter(pages); font-family: "Segoe UI", Arial; font-weight: 700; font-size: 8pt; color: {INK}; vertical-align: top; padding-top: 4mm; }}
}}
@page :first {{ margin: 0; @top-left {{ content: none; }} @top-right {{ content: none; }} @bottom-left {{ content: none; }} @bottom-right {{ content: none; }} }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
html {{ font-family: var(--body); font-size: 9.3pt; line-height: 1.5; color: #1F2638; }}
body {{ margin: 0; }}
p {{ margin: 0 0 7pt; orphans: 3; widows: 3; }}
strong {{ font-weight: 700; color: var(--ink); }}
em {{ color: var(--muted); }}
a {{ color: inherit; text-decoration: none; }}
.pb {{ break-after: page; }}
.mk {{ position: absolute; font-size: 1px; color: transparent; }}

/* cover */
.cover {{ position: relative; width: 210mm; height: 297mm; background: var(--paper); break-after: page; overflow: hidden; display: flex; flex-direction: column; }}
.cover::after {{ content: ""; position: absolute; width: 170mm; height: 170mm; right: -60mm; top: -55mm; border-radius: 50%;
  background: radial-gradient(circle, rgba(34,184,240,.16), rgba(30,91,216,0) 68%); }}
.cv-top {{ display: flex; justify-content: space-between; padding: 16mm 18mm 0; font-size: 8pt; letter-spacing: .18em; text-transform: uppercase; color: var(--muted); font-weight: 600; position: relative; z-index: 1; }}
.cv-mid {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 0 20mm; position: relative; z-index: 1; }}
.cv-logo {{ width: 52mm; height: auto; margin-bottom: 8mm; }}
.cv-name {{ font-family: var(--display); font-weight: 700; font-size: 56pt; line-height: 1; margin: 0 0 5mm; color: var(--ink); letter-spacing: -.01em; }}
.cv-tag {{ font-size: 15pt; font-weight: 300; color: var(--ink); margin: 0; max-width: 140mm; line-height: 1.3; }}
.cv-rule {{ width: 36mm; height: 3px; margin: 8mm auto 5mm; background: linear-gradient(90deg, var(--blue), var(--cyan)); border-radius: 3px; }}
.cv-sub {{ font-size: 10pt; color: var(--muted); letter-spacing: .04em; margin: 0; }}
.cv-night {{ background: var(--night); color: #E6ECF7; padding: 12mm 18mm 13mm; position: relative; }}
.cv-night::before {{ content: ""; position: absolute; left: 0; right: 0; top: -1px; height: 3px; background: linear-gradient(90deg, var(--blue), var(--cyan) 60%, transparent); }}
.cv-stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 6mm; }}
.cv-stats b {{ display: block; font-family: var(--display); font-size: 22pt; font-weight: 700; color: #fff; }}
.cv-stats span {{ font-size: 8pt; color: #9FB0CF; }}
.cv-meta {{ display: flex; justify-content: space-between; margin-top: 9mm; padding-top: 4mm; border-top: 1px solid #1F3160; font-size: 7.8pt; color: #8597BA; }}

/* contents */
.toc-h {{ font-family: var(--display); font-weight: 700; font-size: 32pt; margin: 4mm 0 8mm; color: var(--ink); }}
.toc ol {{ list-style: none; padding: 0; margin: 0; }}
.toc li a {{ display: flex; align-items: baseline; gap: 4mm; padding: 2.4mm 0; border-bottom: 1px solid var(--line); }}
.t-n {{ font-weight: 700; color: var(--blue); width: 8mm; font-size: 9pt; }}
.t-t {{ font-size: 11.5pt; color: var(--ink); }}
.t-d {{ flex: 1; }}
.t-p {{ font-weight: 700; color: var(--ink); }}
.toc-note {{ margin-top: 10mm; padding: 4mm 5mm; background: var(--sand); border-left: 3px solid var(--cyan); font-size: 8.4pt; color: var(--muted); }}

/* headings */
h2.sec {{ position: relative; display: flex; align-items: baseline; gap: 4mm; font-family: var(--display); font-weight: 700; font-size: 25pt; line-height: 1.25; padding-top: 1mm;
  color: var(--ink); margin: 0 0 6mm; padding-bottom: 3mm; overflow: hidden; border-bottom: 1.5px solid var(--ink); break-after: avoid; }}
h2.sec .num {{ font-family: var(--body); font-size: 11pt; font-weight: 700; color: var(--blue); letter-spacing: .05em; }}
h3 {{ font-family: var(--display); font-size: 12.5pt; font-weight: 600; color: var(--ink); margin: 7mm 0 3mm; break-after: avoid; display: flex; align-items: center; gap: 2.5mm; }}
h3::before {{ content: ""; width: 3px; height: 11pt; background: var(--blue); border-radius: 2px; }}
h2 + h3 {{ margin-top: 0; }}
ul, ol {{ padding-left: 5mm; margin: 0 0 7pt; }}
li {{ margin-bottom: 2.2pt; }}
li::marker {{ color: var(--blue); font-weight: 700; }}
blockquote {{ margin: 0 0 8pt; padding: 3mm 5mm; background: var(--sand); border-left: 3px solid var(--cyan); color: #34405C; }}
blockquote p {{ margin: 0; }}
code {{ font-size: 8.4pt; background: var(--sand); padding: 0 3px; border-radius: 3px; }}

/* tables */
table {{ width: 100%; border-collapse: collapse; margin: 0 0 8pt; font-size: 8.2pt; line-height: 1.35; }}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; }}
th {{ background: var(--night); color: #EEF2FA; font-weight: 600; padding: 2.1mm 2.2mm; font-size: 7.9pt; text-align: left; }}
th strong {{ color: {CYAN}; }}
td {{ padding: 1.7mm 2.2mm; border-bottom: 1px solid var(--line); vertical-align: top; }}
tbody tr:nth-child(even) td {{ background: #F9FBFE; }}
tr.total td {{ background: #E3ECFB !important; border-top: 1.2px solid var(--blue); border-bottom: 1.2px solid var(--blue); }}
td:first-child {{ color: var(--ink); }}

.exec p {{ margin-bottom: 5pt; }} .exec figure.chart {{ margin: 2mm 0 4mm; padding: 3mm 3mm 1.5mm; }} .exec li {{ margin-bottom: 1.6pt; }}
/* charts and cards */
figure.chart {{ margin: 3mm 0 7mm; padding: 4mm 4mm 2mm; border: 1px solid var(--line); border-radius: 6px; break-inside: avoid; background: #fff; }}
figure.chart svg {{ width: 100%; height: auto; display: block; font-family: var(--body); }}
figcaption {{ font-size: 7.8pt; color: var(--muted); margin-top: 2mm; }}
.ax {{ font-size: 10px; fill: {MUTED}; }} .ax.b {{ font-weight: 700; fill: {INK}; }}
.vl {{ font-size: 10.5px; font-weight: 700; fill: {INK}; }}
.lg {{ font-size: 10.5px; fill: {INK}; }} .lg.b {{ font-weight: 700; }}
.an {{ font-size: 9.5px; fill: {MUTED}; font-style: italic; }}
.big {{ font-size: 15px; font-weight: 700; fill: {INK}; }}
.qd {{ font-size: 9px; font-weight: 700; letter-spacing: .12em; fill: {MUTED}; }}
.bx {{ font-size: 10px; font-weight: 700; }} .bs {{ font-size: 8.6px; }}
.cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; margin: 2mm 0 6mm; break-inside: avoid; }}
.card {{ border: 1px solid var(--line); border-radius: 6px; padding: 3.2mm 3.4mm 3mm; background: #fff; border-top: 3px solid var(--blue); }}
.card:nth-child(n+5) {{ border-top-color: var(--cyan); }}
.c-l {{ font-size: 7.3pt; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); font-weight: 600; }}
.c-v {{ font-family: var(--display); font-size: 19pt; font-weight: 700; color: var(--ink); margin: 1.2mm 0 .6mm; }}
.c-s {{ font-size: 7.3pt; color: var(--muted); line-height: 1.3; }}
"""


def render(pages: dict[int, int]) -> Path:
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Hyson Detector · Report</title>'
           f"<style>{CSS}</style></head><body>{cover()}{toc(pages)}<div class=\"pb\"></div>{html}</body></html>")
    tmp = Path(tempfile.gettempdir()) / "hyson_report.html"
    tmp.write_text(doc, encoding="utf-8")
    edge = next(p for p in EDGE if p.exists())
    subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=8000",
                    f"--print-to-pdf={OUT}", tmp.as_uri()], check=True, capture_output=True, timeout=180)
    return OUT


# two passes: the first finds the page of each section, the second prints the contents with page numbers
render({})
found: dict[int, int] = {}
for i, page in enumerate(PdfReader(OUT).pages, start=1):
    for mo in re.finditer(r"@@S(\d+)@@", page.extract_text() or ""):
        found.setdefault(int(mo.group(1)), i)
render(found)
print("written", OUT, f"{OUT.stat().st_size / 1024:.0f} KB,", len(PdfReader(OUT).pages), "pages; sections found:", len(found), "of", len(SECTIONS))
