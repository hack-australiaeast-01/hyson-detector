"""Visual layer: bank-grade dark navy design (same palette as the Power BI report)."""
import html

import streamlit as st

NAVY, CARD, LINE = "#0B1426", "#14213A", "#22324F"
TEXT, MUTED, BLUE, BLUE2 = "#E6EDF7", "#8A9BB8", "#4C7CF3", "#8FB0FF"
RISK = {"ELEVE": ("#F43F5E", "Risque élevé"), "MOYEN": ("#F59E0B", "Risque moyen"), "FAIBLE": ("#22C55E", "Risque faible")}

SHIELD = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none"><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z" '
          'fill="#4C7CF3" fill-opacity=".18" stroke="#8FB0FF" stroke-width="1.6"/><path d="m8.5 12 2.3 2.3 4.7-4.8" '
          'stroke="#E6EDF7" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea, select {{ font-family: 'Inter', sans-serif !important; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1500px; }}
h1, h2, h3 {{ letter-spacing: -.01em; }}

/* sidebar */
[data-testid="stSidebar"] {{ border-right: 1px solid {LINE}; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding: .45rem .6rem; border-radius: 8px; margin: 1px 0; width: 100%; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: {CARD}; }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{ background: rgba(76,124,243,.16);
    box-shadow: inset 3px 0 0 {BLUE}; }}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {{ display: none; }}
[data-testid="stSidebar"] [role="radiogroup"] p {{ font-size: .92rem; font-weight: 500; }}
.brand {{ display: flex; gap: .7rem; align-items: center; margin: -.4rem 0 1.1rem; }}
.brand b {{ display: block; font-size: 1.02rem; color: {TEXT}; letter-spacing: .02em; }}
.brand span {{ font-size: .74rem; color: {MUTED}; }}
.side-label {{ font-size: .7rem; font-weight: 600; color: {MUTED}; text-transform: uppercase; letter-spacing: .08em;
    margin: .6rem 0 .35rem; }}
.side-info {{ font-size: .78rem; color: {MUTED}; line-height: 1.5; }}
.side-info b {{ color: {TEXT}; font-weight: 600; }}

/* page header */
.hero {{ background: linear-gradient(135deg, #14213A 0%, #18284A 60%, #1B3366 100%); border: 1px solid {LINE};
    border-radius: 16px; padding: 1.15rem 1.4rem; margin-bottom: 1.1rem; display: flex; justify-content: space-between;
    align-items: center; gap: 1rem; flex-wrap: wrap; }}
.hero .kicker {{ font-size: .72rem; font-weight: 600; color: {BLUE2}; text-transform: uppercase; letter-spacing: .1em; }}
.hero h1 {{ font-size: 1.55rem; margin: .15rem 0 .2rem; padding: 0; color: {TEXT}; font-weight: 700; }}
.hero p {{ margin: 0; color: {MUTED}; font-size: .88rem; }}
.chips {{ display: flex; gap: .45rem; flex-wrap: wrap; }}
.chip {{ font-size: .74rem; padding: .28rem .65rem; border-radius: 999px; border: 1px solid {LINE};
    background: rgba(11,20,38,.55); color: {TEXT}; white-space: nowrap; }}
.chip i {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: .4rem; vertical-align: 1px; }}

/* section titles */
.sec {{ font-size: .78rem; font-weight: 600; color: {MUTED}; text-transform: uppercase; letter-spacing: .08em;
    margin: 1.1rem 0 .5rem; }}

/* KPI cards */
[data-testid="stMetric"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; padding: .85rem 1rem; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED} !important; font-size: .78rem !important; font-weight: 500; }}
[data-testid="stMetricValue"] {{ font-size: 1.65rem !important; font-weight: 700; color: {TEXT}; }}

/* containers */
[data-testid="stExpander"], [data-testid="stForm"] {{ background: {CARD}; border: 1px solid {LINE} !important; border-radius: 14px; }}
[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 12px; overflow: hidden; }}
[data-testid="stChatMessage"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 14px; }}
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{ border-radius: 10px; font-weight: 500; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button {{ background: {BLUE}; border-color: {BLUE}; }}

/* transaction card */
.txcard {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: 1rem 1.2rem; margin-bottom: .8rem; }}
.txcard .top {{ display: flex; justify-content: space-between; align-items: center; gap: .6rem; flex-wrap: wrap; }}
.txcard .id {{ font-size: 1.25rem; font-weight: 700; color: {TEXT}; }}
.txcard .meta {{ color: {MUTED}; font-size: .84rem; margin-top: .3rem; line-height: 1.55; }}
.badge {{ font-size: .74rem; font-weight: 600; padding: .25rem .65rem; border-radius: 999px; }}
.factor {{ display: flex; gap: .6rem; padding: .55rem .7rem; border-radius: 10px; background: rgba(11,20,38,.6);
    border: 1px solid {LINE}; margin-bottom: .4rem; font-size: .88rem; color: {TEXT}; }}
.factor .dot {{ width: 8px; height: 8px; border-radius: 50%; margin-top: .42rem; flex: none; }}
.factor small {{ color: {MUTED}; }}
.foot {{ color: {MUTED}; font-size: .74rem; text-align: center; margin-top: 2rem; }}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x):
    return html.escape(str(x))


def brand(subtitle="Banque de détail · Cellule anti-fraude"):
    st.markdown(f'<div class="brand">{SHIELD}<div><b>COPILOTE FRAUDE</b><span>{esc(subtitle)}</span></div></div>',
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


RISK_EN = {"ELEVE": "High risk", "MOYEN": "Medium risk", "FAIBLE": "Low risk"}


def badge(level, lang="fr"):
    c, label = RISK.get(level, (MUTED, str(level)))
    if lang == "en":
        label = RISK_EN.get(level, label)
    return f'<span class="badge" style="background:{c}22;color:{c};border:1px solid {c}55">{esc(label)}</span>'


def tx_card(tid, badges_html, meta_html):
    st.markdown(f'<div class="txcard"><div class="top"><span class="id">{esc(tid)}</span><span>{badges_html}</span></div>'
                f'<div class="meta">{meta_html}</div></div>', unsafe_allow_html=True)


def factors(rows, positive):
    if not rows:
        st.markdown(f'<div class="factor"><small>Aucun élément</small></div>', unsafe_allow_html=True)
        return
    dot = "#F43F5E" if positive else "#22C55E"
    out = []
    for f in rows:
        obs, usual = f.get("valeur_observee"), f.get("valeur_habituelle")
        val = "" if obs is None else f" : <b>{esc(obs)}</b>"
        cmp_ = "" if usual is None else f" <small>· habituel {esc(usual)}</small>"
        out.append(f'<div class="factor"><span class="dot" style="background:{dot}"></span><div>{esc(f["facteur"])}{val}{cmp_}</div></div>')
    st.markdown("".join(out), unsafe_allow_html=True)


def footer(text="Données 100 % synthétiques · Microsoft Fabric (Lakehouse lh_fraud) · Azure OpenAI · "
                "le modèle score, l'IA explique, l'analyste décide"):
    st.markdown(f'<div class="foot">{esc(text)}</div>', unsafe_allow_html=True)


def icon_html(path, active=False):
    """Centred navigation icon (base64, no static server needed); the active one gets a blue halo."""
    import base64
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    halo = f"background:rgba(76,124,243,.18);box-shadow:0 0 0 1px {BLUE};" if active else ""
    return (f'<div style="display:flex;justify-content:center;margin-bottom:.35rem"><div style="padding:8px;border-radius:14px;{halo}">'
            f'<img src="data:image/png;base64,{b64}" width="54" height="54" alt=""></div></div>')
