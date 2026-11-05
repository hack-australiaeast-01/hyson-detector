"""Hyson Detector — visual layer. Calm, light banking-platform design built for long analyst sessions:
soft neutral background, white cards with gentle shadows, one confident bank blue, readable 15.5 px type,
generous spacing, colour used only for meaning (risk, decisions)."""
import base64
import html

import streamlit as st

# palette
BG, CARD, LINE, LINE2 = "#F4F6FA", "#FFFFFF", "#E3E8F0", "#EEF2F8"
TEXT, MUTED, SOFT = "#0F1E36", "#5B6B82", "#8A97AB"
NAVY, BLUE, BLUE2, TEAL, GOLD = "#0B2545", "#1E5BD8", "#3B76E8", "#0E9F8A", "#C8A24A"
RED, AMBER, GREEN = "#D92D20", "#C77700", "#16A34A"
RISK = {"ELEVE": (RED, "Risque élevé"), "MOYEN": (AMBER, "Risque moyen"), "FAIBLE": (GREEN, "Risque faible")}
RISK_EN = {"ELEVE": "High risk", "MOYEN": "Medium risk", "FAIBLE": "Low risk"}
DECISION = {"BLOQUER": RED, "ESCALADER": AMBER, "VALIDER": GREEN}

LOGO_SVG = ('<svg width="38" height="38" viewBox="0 0 48 48" fill="none">'
            '<defs><linearGradient id="hg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1E5BD8"/>'
            '<stop offset="1" stop-color="#0E9F8A"/></linearGradient></defs>'
            '<path d="M24 3 7 9v12c0 11 7.3 20.2 17 24 9.7-3.8 17-13 17-24V9L24 3Z" fill="url(#hg)"/>'
            '<circle cx="24" cy="22" r="9" stroke="#fff" stroke-width="2.2" fill="none" opacity=".95"/>'
            '<circle cx="24" cy="22" r="3.2" fill="#fff"/>'
            '<path d="M24 13v-3M24 34v-3M15 22h-3M36 22h-3" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></svg>')

BRAND_DIR = __import__("pathlib").Path(__file__).parent / "static" / "brand"
FAVICON = str(BRAND_DIR / "favicon.png") if (BRAND_DIR / "favicon.png").exists() else "🛡️"


def _logo_img(name, size):
    """Team logo (PNG, embedded as base64 so no static server is needed); SVG shield if the file is missing."""
    p = BRAND_DIR / name
    if not p.exists():
        return LOGO_SVG
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" width="{size}" height="{size}" alt="Hyson Detector" style="display:block">'


LOGO = _logo_img("logo_white.png", 40)          # on the navy sidebar card


def logo(variant="blue", size=96):
    """'white' on navy backgrounds, 'blue' on light ones."""
    return _logo_img(f"logo_{variant}.png", size)

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea, select, label {{ font-family: 'Inter', sans-serif !important; }}
html {{ font-size: 15.5px; }}
.stApp {{ background: {BG}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.5rem; padding-bottom: 2.5rem; max-width: 1480px; }}
p, li {{ line-height: 1.62; }}
h1, h2, h3 {{ letter-spacing: -.015em; color: {TEXT}; }}

/* sidebar */
[data-testid="stSidebar"] {{ background: {CARD}; border-right: 1px solid {LINE}; }}
[data-testid="stSidebar"] .block-container {{ padding-top: 1rem; }}
[data-testid="stSidebar"] .stButton > button {{ justify-content: flex-start; text-align: left; border: 1px solid transparent;
    background: transparent; color: {TEXT}; font-weight: 500; padding: .42rem .7rem; border-radius: 10px; min-height: 2.3rem;
    box-shadow: none; width: 100%; }}
[data-testid="stSidebar"] .stButton > button > div {{ justify-content: flex-start !important; width: 100%; gap: .55rem; }}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .3rem; }}
[data-testid="stSidebar"] .side-label {{ margin: 1rem 0 .55rem .25rem; line-height: 1.2; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background: {LINE2}; border-color: {LINE}; color: {NAVY}; }}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{ background: #E8EFFD; color: {BLUE}; border-color: #C9D9FA;
    box-shadow: inset 3px 0 0 {BLUE}; font-weight: 600; }}
[data-testid="stSidebar"] .stButton > button p {{ font-size: .92rem; }}
.brand {{ display: flex; gap: .75rem; align-items: center; margin: -.2rem 0 1rem; padding: .7rem .75rem; border-radius: 14px;
    background: linear-gradient(135deg, {NAVY} 0%, #123A6B 100%); }}
.brand b {{ display: block; font-size: 1.12rem; color: #fff; letter-spacing: .01em; font-weight: 800; }}
.brand span {{ font-size: .74rem; color: #B9C8E0; }}
.side-label {{ font-size: .68rem; font-weight: 700; color: {SOFT}; text-transform: uppercase; letter-spacing: .1em;
    margin: 1rem 0 .3rem .25rem; }}
.side-info {{ font-size: .78rem; color: {MUTED}; line-height: 1.55; background: {LINE2}; border-radius: 12px; padding: .65rem .75rem; }}
.side-info b {{ color: {TEXT}; font-weight: 600; }}

/* page header */
.hero {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 18px; padding: 1.2rem 1.5rem; margin-bottom: 1.2rem;
    display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;
    box-shadow: 0 1px 2px rgba(16,24,40,.04), 0 6px 18px rgba(16,24,40,.05); position: relative; overflow: hidden; }}
.hero:before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px;
    background: linear-gradient(180deg, {BLUE}, {TEAL}); }}
.hero .kicker {{ font-size: .72rem; font-weight: 700; color: {BLUE}; text-transform: uppercase; letter-spacing: .12em; }}
.hero h1 {{ font-size: 1.6rem; margin: .2rem 0 .25rem; padding: 0; color: {TEXT}; font-weight: 800; }}
.hero p {{ margin: 0; color: {MUTED}; font-size: .92rem; max-width: 820px; }}
.chips {{ display: flex; gap: .45rem; flex-wrap: wrap; }}
.chip {{ font-size: .75rem; padding: .3rem .7rem; border-radius: 999px; border: 1px solid {LINE};
    background: {LINE2}; color: {TEXT}; white-space: nowrap; font-weight: 500; }}
.chip i {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: .42rem; vertical-align: 1px; }}

/* section titles */
.sec {{ font-size: .76rem; font-weight: 700; color: {MUTED}; text-transform: uppercase; letter-spacing: .1em;
    margin: 1.3rem 0 .55rem; display: flex; align-items: center; gap: .5rem; }}
.sec:after {{ content: ""; flex: 1; height: 1px; background: {LINE}; }}

/* KPI cards */
[data-testid="stMetric"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: .95rem 1.1rem;
    box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
[data-testid="stMetricLabel"] p {{ color: {MUTED} !important; font-size: .8rem !important; font-weight: 500; }}
[data-testid="stMetricValue"] {{ font-size: 1.7rem !important; font-weight: 800; color: {TEXT}; }}
.kpi {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 18px; padding: 1.1rem 1.25rem; height: 100%;
    box-shadow: 0 1px 2px rgba(16,24,40,.04), 0 6px 18px rgba(16,24,40,.04); }}
.kpi .lab {{ font-size: .8rem; color: {MUTED}; font-weight: 600; }}
.kpi .val {{ font-size: 2.05rem; font-weight: 800; color: {TEXT}; line-height: 1.15; margin: .25rem 0; letter-spacing: -.02em; }}
.kpi .cmp {{ font-size: .82rem; color: {MUTED}; }}
.kpi .cmp b {{ color: {TEXT}; }}
.kpi .delta {{ display: inline-block; font-size: .76rem; font-weight: 700; padding: .15rem .5rem; border-radius: 999px; margin-top: .35rem; }}

/* containers */
[data-testid="stExpander"], [data-testid="stForm"] {{ background: {CARD}; border: 1px solid {LINE} !important; border-radius: 16px; }}
[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 14px; overflow: hidden; background: {CARD}; }}
[data-testid="stChatMessage"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 16px; }}
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{ border-radius: 11px; font-weight: 600; min-height: 2.5rem; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button {{ background: {BLUE}; border-color: {BLUE}; color: #fff; }}
[data-testid="stAlert"] {{ border-radius: 14px; }}

/* transaction card */
.txcard {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 18px; padding: 1.05rem 1.25rem; margin-bottom: .9rem;
    box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
.txcard .top {{ display: flex; justify-content: space-between; align-items: center; gap: .6rem; flex-wrap: wrap; }}
.txcard .id {{ font-size: 1.3rem; font-weight: 800; color: {TEXT}; }}
.txcard .meta {{ color: {MUTED}; font-size: .87rem; margin-top: .35rem; line-height: 1.6; }}
.badge {{ font-size: .75rem; font-weight: 700; padding: .27rem .7rem; border-radius: 999px; }}
.factor {{ display: flex; gap: .65rem; padding: .6rem .75rem; border-radius: 12px; background: {CARD};
    border: 1px solid {LINE}; margin-bottom: .45rem; font-size: .9rem; color: {TEXT}; }}
.factor .dot {{ width: 9px; height: 9px; border-radius: 50%; margin-top: .45rem; flex: none; }}
.factor small {{ color: {MUTED}; }}

/* guide */
.welcome {{ background: linear-gradient(135deg, {NAVY} 0%, #123A6B 55%, #0E6E6A 100%); color: #fff; border-radius: 22px;
    padding: 1.8rem 2rem; margin-bottom: 1.3rem; }}
.welcome h1 {{ color: #fff; font-size: 2.1rem; margin: .2rem 0 .4rem; font-weight: 800; }}
.welcome p {{ color: #D5E1F2; font-size: 1rem; margin: 0; max-width: 860px; }}
.welcome .tag {{ display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase;
    color: #9FE3D7; }}
.step {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: .9rem 1rem; margin-bottom: .6rem;
    display: flex; gap: .9rem; align-items: flex-start; }}
.step .n {{ flex: none; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-weight: 800; background: #E8EFFD; color: {BLUE}; }}
.step.done .n {{ background: #DCFCE7; color: {GREEN}; }}
.step b {{ color: {TEXT}; }}
.step span {{ color: {MUTED}; font-size: .88rem; }}
.hint {{ background: #EEF5FF; border: 1px solid #CFE0FB; border-radius: 14px; padding: .65rem .9rem; margin-bottom: .9rem;
    color: {NAVY}; font-size: .9rem; }}

/* courtroom */
.plea {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 18px; padding: 1rem 1.15rem; min-height: 260px;
    box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
.plea h4 {{ margin: 0 0 .5rem; font-size: 1rem; display: flex; align-items: center; gap: .5rem; }}
.plea .who {{ font-size: .72rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }}
.plea .body {{ color: {TEXT}; font-size: .92rem; line-height: 1.65; white-space: pre-wrap; }}
.verdict {{ border-radius: 20px; padding: 1.2rem 1.4rem; color: #fff; margin: .6rem 0 1rem;
    box-shadow: 0 10px 30px rgba(16,24,40,.12); }}
.verdict .big {{ font-size: 1.9rem; font-weight: 800; letter-spacing: -.01em; }}
.verdict .body {{ font-size: .95rem; line-height: 1.65; white-space: pre-wrap; opacity: .97; margin-top: .4rem; }}

/* replay */
.tl {{ border-left: 2px solid {LINE}; margin-left: .6rem; padding-left: 1.1rem; }}
.tl .it {{ position: relative; background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; padding: .6rem .85rem;
    margin-bottom: .55rem; }}
.tl .it:before {{ content: ""; position: absolute; left: -1.53rem; top: .95rem; width: 12px; height: 12px; border-radius: 50%;
    background: {SOFT}; border: 2px solid {BG}; }}
.tl .it.risky:before {{ background: {RED}; }}
.tl .it.target {{ border-color: {RED}; box-shadow: 0 0 0 3px rgba(217,45,32,.12); }}
.tl .it.target:before {{ background: {RED}; width: 14px; height: 14px; left: -1.6rem; }}
.tl .it .t {{ font-size: .75rem; color: {MUTED}; font-weight: 600; }}
.tl .it .h {{ font-weight: 700; color: {TEXT}; font-size: .93rem; }}
.tl .it .d {{ color: {MUTED}; font-size: .84rem; }}
.flag {{ display: inline-block; font-size: .7rem; font-weight: 700; padding: .1rem .45rem; border-radius: 999px;
    background: #FEE4E2; color: {RED}; margin: .2rem .25rem 0 0; }}
.flag.ok {{ background: #DCFCE7; color: {GREEN}; }}

/* process flow */
.flow {{ display: flex; align-items: stretch; gap: .5rem; flex-wrap: wrap; margin: .2rem 0 .6rem; }}
.flow .st {{ flex: 1; min-width: 150px; background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: .85rem 1rem;
    box-shadow: 0 1px 2px rgba(16,24,40,.04); border-top: 4px solid var(--c); }}
.flow .st .v {{ font-size: 1.55rem; font-weight: 800; color: {TEXT}; letter-spacing: -.02em; }}
.flow .st .l {{ font-size: .8rem; color: {MUTED}; line-height: 1.35; margin-top: .15rem; }}
.flow .ar {{ display: flex; align-items: center; color: {SOFT}; font-size: 1.3rem; font-weight: 700; }}

/* galaxy */
.space {{ background: radial-gradient(ellipse at 30% 20%, #1B2D55 0%, #0A1128 55%, #050816 100%); border-radius: 20px;
    padding: .4rem; border: 1px solid #1E2A4A; }}
.foot {{ color: {SOFT}; font-size: .76rem; text-align: center; margin-top: 2.2rem; }}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x):
    return html.escape(str(x))


def brand(subtitle="Détecter · Expliquer · Décider"):
    st.markdown(f'<div class="brand">{LOGO}<div><b>Hyson Detector</b><span>{esc(subtitle)}</span></div></div>',
                unsafe_allow_html=True)


def side_label(text):
    st.markdown(f'<div class="side-label">{esc(text)}</div>', unsafe_allow_html=True)


def side_info(html_text):
    st.markdown(f'<div class="side-info">{html_text}</div>', unsafe_allow_html=True)


def chip(text, dot=None):
    d = f'<i style="background:{dot}"></i>' if dot else ""
    return f'<span class="chip">{d}{esc(text)}</span>'


def hero(kicker, title, subtitle, chips=()):
    st.markdown(f'<div class="hero"><div><div class="kicker">{esc(kicker)}</div><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>'
                f'<div class="chips">{"".join(chips)}</div></div>', unsafe_allow_html=True)


def section(text):
    st.markdown(f'<div class="sec">{esc(text)}</div>', unsafe_allow_html=True)


def badge(level, lang="fr"):
    c, label = RISK.get(level, (MUTED, str(level)))
    if lang == "en":
        label = RISK_EN.get(level, label)
    return f'<span class="badge" style="background:{c}14;color:{c};border:1px solid {c}40">{esc(label)}</span>'


def tx_card(tid, badges_html, meta_html):
    st.markdown(f'<div class="txcard"><div class="top"><span class="id">{esc(tid)}</span><span>{badges_html}</span></div>'
                f'<div class="meta">{meta_html}</div></div>', unsafe_allow_html=True)


def factors(rows, positive, usual_word="habituel", empty="Aucun élément"):
    if not rows:
        st.markdown(f'<div class="factor"><small>{esc(empty)}</small></div>', unsafe_allow_html=True)
        return
    dot = RED if positive else GREEN
    out = []
    for f in rows:
        obs, usual = f.get("valeur_observee"), f.get("valeur_habituelle")
        val = "" if obs is None else f" : <b>{esc(obs)}</b>"
        cmp_ = "" if usual is None else f" <small>· {esc(usual_word)} {esc(usual)}</small>"
        out.append(f'<div class="factor"><span class="dot" style="background:{dot}"></span><div>{esc(f["facteur"])}{val}{cmp_}</div></div>')
    st.markdown("".join(out), unsafe_allow_html=True)


def kpi(label, value, compare_html="", delta=None, good=True):
    d = ""
    if delta:
        c = GREEN if good else RED
        d = f'<div class="delta" style="background:{c}14;color:{c}">{esc(delta)}</div>'
    st.markdown(f'<div class="kpi"><div class="lab">{esc(label)}</div><div class="val">{esc(value)}</div>'
                f'<div class="cmp">{compare_html}</div>{d}</div>', unsafe_allow_html=True)


def step(n, title, text, done=False):
    st.markdown(f'<div class="step{" done" if done else ""}"><div class="n">{"✓" if done else n}</div>'
                f'<div><b>{esc(title)}</b><br><span>{esc(text)}</span></div></div>', unsafe_allow_html=True)


def hint(html_text):
    st.markdown(f'<div class="hint">{html_text}</div>', unsafe_allow_html=True)


def plea(who, title, icon, color, body):
    st.markdown(f'<div class="plea" style="border-top:4px solid {color}"><div class="who" style="color:{color}">{esc(who)}</div>'
                f'<h4>{icon} {esc(title)}</h4><div class="body">{esc(body)}</div></div>', unsafe_allow_html=True)


def verdict(decision_label, decision_key, body):
    c = DECISION.get(decision_key, BLUE)
    st.markdown(f'<div class="verdict" style="background:linear-gradient(135deg,{c} 0%,{NAVY} 140%)">'
                f'<div class="big">⚖️ {esc(decision_label)}</div><div class="body">{esc(body)}</div></div>', unsafe_allow_html=True)


def timeline(items):
    out = []
    for s in items:
        cls = "it" + (" risky" if s.get("risky") else "") + (" target" if s.get("target") else "")
        flags = "".join(f'<span class="flag{" ok" if f.startswith(("en agence", "in branch")) else ""}">{esc(f)}</span>'
                        for f in s.get("flags", []))
        out.append(f'<div class="{cls}"><div class="t">{esc(s["ts"])}</div><div class="h">{s["icon"]} {esc(s["title"])}</div>'
                   f'<div class="d">{esc(s.get("detail", ""))}</div>{flags}</div>')
    st.markdown(f'<div class="tl">{"".join(out)}</div>', unsafe_allow_html=True)


def flow(stages):
    """Horizontal process: [(value, label, colour), ...] joined by arrows."""
    items = []
    for i, (v, lab, col) in enumerate(stages):
        if i:
            items.append('<div class="ar">→</div>')
        items.append(f'<div class="st" style="--c:{col}"><div class="v">{esc(v)}</div><div class="l">{esc(lab)}</div></div>')
    st.markdown(f'<div class="flow">{"".join(items)}</div>', unsafe_allow_html=True)


def footer(text):
    st.markdown(f'<div class="foot">{esc(text)}</div>', unsafe_allow_html=True)


def icon_html(path, active=False):
    """Centred navigation icon (base64, no static server needed); the active one gets a blue halo."""
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    halo = f"background:#E8EFFD;box-shadow:0 0 0 1px {BLUE};" if active else ""
    return (f'<div style="display:flex;justify-content:center;margin-bottom:.35rem"><div style="padding:8px;border-radius:14px;{halo}">'
            f'<img src="data:image/png;base64,{b64}" width="54" height="54" alt=""></div></div>')
