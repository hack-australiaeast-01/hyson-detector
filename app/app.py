"""Fraud-analyst copilot — Streamlit interface (brief §10). FR / EN.

Run:  streamlit run app.py
"""
import os
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st


def _secrets_to_env():
    """Streamlit Community Cloud: expose secrets as env vars before the modules read them.

    Accepts root-level keys and keys nested one level under a [section] (a common way to paste them).
    """
    try:
        items = list(st.secrets.items())
    except Exception:          # no secrets.toml locally -> .env is used instead
        return
    for k, v in items:
        pairs = v.items() if hasattr(v, "items") else [(k, v)]
        for k2, v2 in pairs:
            if isinstance(v2, (str, int, float, bool)) and not os.getenv(str(k2)):
                os.environ[str(k2)] = str(v2)


_secrets_to_env()

import copilot  # noqa: E402  (after the secrets bridge on purpose)
import data_access as da
import deepsearch
import fairness
import features as fx
import market
import onboarding
import person_search
import studio
import tools
import ui

st.set_page_config(page_title="Hyson Detector · Fraude", page_icon=ui.FAVICON, layout="wide")
ui.inject()

ICON_DIR = Path(__file__).parent / "static" / "icons"
st.session_state.setdefault("lang", "fr")


def L(fr, en):
    """Pick the text for the current language."""
    return en if st.session_state.get("lang") == "en" else fr


# internal page ids (stable across languages) -> labels, grouped like a banking platform menu
PAGES = ["guide", "queue", "tx", "cust", "deep", "proces", "replay", "contre", "galaxy", "impact", "market", "perf", "pbi", "journal", "onboard"]
PAGE_LABEL = {"guide": ("Démarrer ici", "Start here"),
              "queue": ("File d'alertes", "Alert queue"), "tx": ("Fiche transaction & copilote", "Transaction & copilot"),
              "cust": ("Vue client 360", "Customer 360"),
              "deep": ("Enquête approfondie", "Deep search"),
              "proces": ("Le Procès", "The Trial"), "replay": ("Reconstitution", "Crime-scene replay"),
              "contre": ("Contre-enquête", "Counter-inquiry"), "galaxy": ("Constellation", "Constellation"),
              "impact": ("Impact & processus", "Impact & process"),
              "market": ("Marché & benchmarks", "Market & benchmarks"), "perf": ("Performance du modèle", "Model performance"),
              "journal": ("Journal & traçabilité", "Audit log"), "pbi": ("Tableau de bord Power BI", "Power BI dashboard"),
              "onboard": ("Nouvelle source de données", "New data source")}
PAGE_ICON = {"guide": ":material/flag:", "queue": ":material/notifications_active:", "tx": ":material/manage_search:",
             "cust": ":material/person:", "deep": ":material/troubleshoot:", "proces": ":material/gavel:", "replay": ":material/movie:",
             "contre": ":material/alt_route:", "galaxy": ":material/hub:", "impact": ":material/insights:", "market": ":material/public:",
             "perf": ":material/monitoring:", "pbi": ":material/dashboard:", "journal": ":material/fact_check:",
             "onboard": ":material/upload_file:"}
NAV_GROUPS = [(("Bienvenue", "Welcome"), ["guide"]),
              (("Analyste", "Analyst"), ["queue", "tx", "cust"]),
              (("Enquête IA", "AI investigation"), ["deep", "proces", "replay", "contre", "galaxy"]),
              (("Pilotage", "Steering"), ["impact", "market", "perf", "pbi", "journal"]),
              (("Données", "Data"), ["onboard"])]
DEMO_LABEL = {"obvious_fraud": ("Fraude évidente", "Obvious fraud"), "subtle_fraud": ("Fraude subtile", "Subtle fraud"),
              "avoided_false_positive": ("Faux positif évité", "Avoided false positive")}
SUGGESTIONS = copilot.SUGGESTIONS          # same strings as warmup.py -> pre-computed answers are cache hits
RISK_TXT = {"ELEVE": ("ELEVE", "HIGH"), "MOYEN": ("MOYEN", "MEDIUM"), "FAIBLE": ("FAIBLE", "LOW")}


def tr(pair):
    return L(*pair)


@st.cache_resource(show_spinner=False)
def connect():
    src = da.source()
    return src.mode


@st.cache_data(show_spinner=False)
def load(_mode):
    return da.queue(), da.explanations()


def refresh():
    da.reset()
    fx.reset()
    deepsearch.reset()
    connect.clear()
    load.clear()


def open_tx(tid, page="tx"):
    st.session_state.tx = tid
    st.session_state.tx_select = tid
    for k in ("proces_tx", "replay_tx", "contre_tx", "deep_tx"):
        st.session_state[k] = tid
    st.session_state.goto = page


def go(page):
    st.session_state.goto = page


def mark(step):
    st.session_state.setdefault("done", set()).add(step)


def money(x):
    return f"{x:,.3f} TND".replace(",", " ")


def nb(x):
    return f"{x:,}".replace(",", " ")


_splash = st.empty()
if "tx" not in st.session_state:                       # first load: branded, reassuring loading screen
    _splash.markdown(
        f'<div class="welcome" style="margin-top:12vh;text-align:center"><div style="display:flex;justify-content:center">'
        f'{ui.logo("white", 92)}</div>'
        f'<h1>Hyson Detector</h1><p style="margin:0 auto">{L("Connexion sécurisée à Microsoft Fabric et chargement des alertes du jour…",
                                                           "Secure connection to Microsoft Fabric and loading today’s alerts…")}</p>'
        f'<p style="margin:.8rem auto 0;color:#9FE3D7;font-size:.85rem">{L("Détecter · Expliquer · Décider", "Detect · Explain · Decide")}</p></div>',
        unsafe_allow_html=True)
queue, expl = load(connect())
_splash.empty()
demos = queue[queue.demo_case.notna()]
DEMO_TX = dict(zip(demos.demo_case, demos.transaction_id))
st.session_state.setdefault("tx", demos.transaction_id.iloc[0] if len(demos) else queue.transaction_id.iloc[0])
st.session_state.setdefault("chat", {})
if st.session_state.get("page") not in PAGES:
    st.session_state.page = "guide"
if "goto" in st.session_state:
    st.session_state.page = st.session_state.pop("goto")
page = st.session_state.page

# ---------------------------------------------------------------- sidebar
src = da.source()
LIVE = src.mode == "fabric"


def mode_label():
    return f"Azure OpenAI · {os.getenv('AZURE_OPENAI_DEPLOYMENT')}" if copilot.configured() else L("Hors-ligne (règles)", "Offline (rules)")


def status_chips():
    return [ui.chip("Fabric live" if LIVE else L("Export local", "Local export"), "#22C55E" if LIVE else "#F59E0B"),
            ui.chip(mode_label(), ui.BLUE2), ui.chip(L("Données synthétiques", "Synthetic data"))]


with st.sidebar:
    ui.brand(L("Détecter · Expliquer · Décider", "Detect · Explain · Decide"))
    st.segmented_control("Langue / Language", ["fr", "en"], key="lang", format_func=lambda x: {"fr": "Français", "en": "English"}[x],
                         label_visibility="collapsed")
    # who decides: written into every decision of the audit trail (production: Entra ID single sign-on instead of a typed name)
    st.text_input(L("Analyste connecté", "Signed-in analyst"), key="analyst", value=st.session_state.get("analyst", "analyste.demo"),
                  help=L("Nom enregistré avec chaque décision (piste d'audit). En production : identité Entra ID (SSO).",
                         "Name stored with every decision (audit trail). In production: Entra ID identity (SSO)."))
    for (fr, en), ids in NAV_GROUPS:
        ui.side_label(L(fr, en))
        for pid in ids:
            st.button(tr(PAGE_LABEL[pid]), key=f"nav_{pid}", on_click=go, args=(pid,), icon=PAGE_ICON[pid], width="stretch",
                      type="primary" if pid == page else "secondary")
    ui.side_label(L("Cas de démo", "Demo cases"))
    for _, d in demos.iterrows():
        st.button(f"{d.risk_icon}  {tr(DEMO_LABEL.get(d.demo_case, (d.demo_case, d.demo_case)))} · {d.transaction_id}",
                  key=f"demo_{d.transaction_id}", on_click=open_tx, args=(d.transaction_id,), width="stretch")
    ui.side_label(L("Système", "System"))
    u = copilot.usage_summary()
    info = (f"{L('Données', 'Data')} : <b>{ui.esc(src.describe())}</b><br>{L('Copilote', 'Copilot')} : <b>{ui.esc(mode_label())}</b><br>"
            f"{L('Appels LLM', 'LLM calls')} : <b>{u['appels']}</b> · tokens : <b>{nb(u['tokens'])}</b> · cache : <b>{u['caches']}</b>")
    if getattr(src, "feedback_synced", None):
        info += f"<br>{L('Journal synchronisé dans OneLake à', 'Log synced to OneLake at')} {ui.esc(src.feedback_synced)}"
    if src.error:
        info += f"<br>⚠ {ui.esc(src.error)}"
    ui.side_info(info)
    st.button(L("Rafraîchir depuis Fabric", "Refresh from Fabric"), on_click=refresh, width="stretch", icon=":material/sync:")


# ---------------------------------------------------------------- 1. alert queue
def page_queue():
    ui.hero(L("Surveillance des transactions", "Transaction monitoring"), tr(PAGE_LABEL["queue"]),
            L("Top 1 % des scores du modèle, priorisé pour la capacité des analystes · cliquez une ligne pour l'ouvrir",
              "Top 1% of model scores, prioritised for analyst capacity · click a row to open it"), status_chips())
    c1, c2, c3, c4 = st.columns([1.3, 1.4, 1.4, 1.4])
    period = c1.segmented_control(L("Période", "Period"), ["test", "valid"], default="test", key="period_sel",
                                  format_func=lambda p: L("Flux du jour", "Live flow") if p == "test" else "Validation") or "test"
    q = queue[queue.period == period]
    dmin, dmax = q.date.min(), q.date.max()
    dates = c2.date_input("Dates", (dmin, dmax), min_value=dmin, max_value=dmax, format="DD/MM/YYYY")
    channels = c3.multiselect(L("Canal", "Channel"), sorted(q.channel.dropna().unique()), placeholder=L("Tous les canaux", "All channels"))
    risks = c4.multiselect(L("Niveau de risque", "Risk level"), ["ELEVE", "MOYEN", "FAIBLE"], default=["ELEVE", "MOYEN"],
                           format_func=lambda r: tr(RISK_TXT[r]), placeholder=L("Tous les niveaux", "All levels"))
    if isinstance(dates, tuple) and len(dates) == 2:
        q = q[(q.date >= dates[0]) & (q.date <= dates[1])]
    if channels:
        q = q[q.channel.isin(channels)]
    if risks:
        q = q[q.risk_level.isin(risks)]
    if period == "valid":
        types = st.multiselect(L("Typologie (validation uniquement)", "Fraud type (validation only)"),
                               sorted(queue.fraud_scenario.dropna().unique()), placeholder=L("Toutes les typologies", "All types"))
        if types:
            q = q[q.fraud_scenario.isin(types)]

    days = max(q.date.nunique(), 1)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(L("Alertes", "Alerts"), nb(len(q)))
    m2.metric(L("Risque élevé", "High risk"), nb(int((q.risk_level == "ELEVE").sum())))
    m3.metric(L("Alertes / jour", "Alerts / day"), f"{len(q) / days:.1f}")
    m4.metric(L("Montant en jeu", "Amount at stake"), f"{q.amount_tnd.sum():,.0f} TND".replace(",", " "))

    with st.expander(L("Volume d'alertes par jour et niveau de risque", "Alert volume per day and risk level"),
                     expanded=False, icon=":material/bar_chart:"):
        per_day = q.groupby(["date", "risk_level"]).size().unstack(fill_value=0)
        order = [x for x in ["ELEVE", "MOYEN", "FAIBLE"] if x in per_day.columns]
        st.bar_chart(per_day[order].rename(columns=lambda c: tr(RISK_TXT[c])), color=[ui.RISK[x][0] for x in order], height=240)

    if period == "test":
        nw = deepsearch.watch("test")
        ui.section(L(f"🔎 L'IA signale {len(nw)} alertes moyennes à creuser · survolez pour voir pourquoi",
                     f"🔎 AI flags {len(nw)} medium alerts to dig into · hover to see why"))
        studio.watch_buttons(ctx, key="wq")

    ui.section(L(f"{nb(len(q))} alertes · triées par score", f"{nb(len(q))} alerts · sorted by score"))
    alerts_only = q[q.risk_level != "FAIBLE"]
    if len(alerts_only):
        total_ops = int(fx.impact()["flux_du_jour"]["operations"]) if period == "test" and fx.impact() else None
        exp_fraud = float(tools.measured_fraud_rate(alerts_only.score_model).sum())
        dec, _ = tools.recommend_vector(alerts_only)
        n_block, n_esc = int((dec == "BLOQUER").sum()), int((dec == "ESCALADER").sum())
        scope = (L(f"Sur <b>{nb(total_ops)}</b> opérations du flux, seules", f"Out of <b>{nb(total_ops)}</b> live operations, only")
                 if total_ops else L("Seules", "Only"))
        ui.hint(L(f"⚖️ <b>Une alerte n'est pas une fraude, c'est une opération à vérifier.</b> {scope} les 1 % les plus "
                  f"risquées arrivent ici (99 % ne dérangent personne). Parmi ces {nb(len(alerts_only))} alertes, la validation "
                  f"juin–juillet prédit <b>≈ {nb(round(exp_fraud))} vraies fraudes</b> : <b>{nb(n_block)}</b> à bloquer "
                  f"(87 % de fraudes mesurées en moyenne) et <b>{nb(n_esc)}</b> à faire vérifier par un analyste, dont la plupart "
                  "sont des clients légitimes à rassurer vite. La colonne « Fraudes mesurées » le montre ligne par ligne.",
                  f"⚖️ <b>An alert is not a fraud, it is an operation to check.</b> {scope} the riskiest 1% reach this queue "
                  f"(99% disturb nobody). Among these {nb(len(alerts_only))} alerts, the June–July validation predicts "
                  f"<b>≈ {nb(round(exp_fraud))} real frauds</b>: <b>{nb(n_block)}</b> to block (87% measured fraud on average) and "
                  f"<b>{nb(n_esc)}</b> for an analyst to check, most of them legitimate customers to clear quickly. "
                  "The “Measured fraud” column shows it row by row."))
    view = q.sort_values("score_model", ascending=False)[
        ["risk_icon", "transaction_id", "timestamp", "customer_id", "transaction_type", "channel", "merchant_category",
         "amount_tnd", "city", "country", "score_model", "score_pct", "risk_level", "legacy_alert", "top_model_factors"]].copy()
    view["fraud_rate"] = np.where(view.risk_level != "FAIBLE", tools.measured_fraud_rate(view.score_model), np.nan)
    dec, _ = tools.recommend_vector(view)
    view["action"] = dec.map({"BLOQUER": L("Bloquer", "Block"), "ESCALADER": L("Vérifier", "Check"),
                              "VALIDER": L("Valider", "Validate")})
    view = view[["risk_icon", "transaction_id", "timestamp", "customer_id", "transaction_type", "channel", "merchant_category",
                 "amount_tnd", "city", "country", "fraud_rate", "action", "risk_level", "legacy_alert", "top_model_factors"]]
    flags = deepsearch.watch(period).level
    view.insert(2, "flag", view.transaction_id.map(lambda t: L(*studio.DEEP_LEVEL[flags[t]]) if t in flags.index else ""))
    for c in ["merchant_category", "city", "top_model_factors"]:
        view[c] = view[c].fillna("—").replace({"None": "—", "": "—"})
    view["risk_level"] = view.risk_level.map(lambda r: tr(RISK_TXT.get(r, (r, r))))
    cc = st.column_config
    ev = st.dataframe(view, hide_index=True, width="stretch", height=480, on_select="rerun",
                      selection_mode="single-row", key=f"q_{period}",
                      column_config={"risk_icon": cc.TextColumn("", width="small"),
                                     "transaction_id": cc.TextColumn("Transaction"),
                                     "flag": cc.TextColumn(L("Signal IA", "AI flag"),
                                                           help=L("Alerte moyenne dont le client a déjà eu une alerte dans les 72 h : "
                                                                  "38 à 75 % de fraudes mesurées (contre 15 %).",
                                                                  "Medium alert whose customer already had an alert in the previous 72 h: "
                                                                  "38–75% measured fraud (vs 15%).")),
                                     "timestamp": cc.DatetimeColumn("Date", format="DD/MM HH:mm"),
                                     "customer_id": cc.TextColumn(L("Client", "Customer")),
                                     "transaction_type": cc.TextColumn("Type"),
                                     "channel": cc.TextColumn(L("Canal", "Channel")),
                                     "merchant_category": cc.TextColumn(L("Catégorie", "Category")),
                                     "amount_tnd": cc.NumberColumn(L("Montant (TND)", "Amount (TND)"), format="%.3f"),
                                     "city": cc.TextColumn(L("Ville", "City")),
                                     "country": cc.TextColumn(L("Pays", "Country"), width="small"),
                                     "fraud_rate": cc.ProgressColumn(L("Fraudes mesurées", "Measured fraud"), min_value=0,
                                                                     max_value=1, format="percent",
                                                                     help=L("Part de vraies fraudes parmi les alertes de score comparable "
                                                                            "en validation (juin–juillet 2026). Le score est un classement, "
                                                                            "pas une probabilité : un score de 0,70 ≈ 12 % de fraudes.",
                                                                            "Share of real frauds among validation alerts (June–July 2026) "
                                                                            "with a similar score. The score is a ranking, not a probability: "
                                                                            "a 0.70 score ≈ 12% frauds.")),
                                     "action": cc.TextColumn(L("Action conseillée", "Suggested action"),
                                                             help=L("Règle documentée (tools.recommend) ; l'analyste décide.",
                                                                    "Documented rule (tools.recommend); the analyst decides.")),
                                     "risk_level": cc.TextColumn(L("Risque", "Risk")),
                                     "legacy_alert": cc.CheckboxColumn(L("Règles actuelles", "Current rules")),
                                     "top_model_factors": cc.TextColumn(L("Facteurs principaux", "Main factors"), width="large")})
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        tid = view.iloc[rows[0]].transaction_id
        b1, b2, _ = st.columns([1, 1, 2])
        b1.button(L(f"Ouvrir {tid} →", f"Open {tid} →"), on_click=open_tx, args=(tid,), type="primary", width="stretch")
        b2.button(L("🔎 Enquête approfondie", "🔎 Deep search"), on_click=open_tx, args=(tid, "deep"), width="stretch",
                  help=deepsearch.reason(tid, st.session_state.lang) or None)


# ---------------------------------------------------------------- 2. transaction card + copilot
def page_transaction():
    ids = queue.transaction_id.tolist()
    risk_of = dict(zip(queue.transaction_id, queue.risk_icon))
    tid = st.session_state.tx if st.session_state.tx in ids else ids[0]
    if st.session_state.get("tx_select") not in ids:
        st.session_state.tx_select = tid
    ui.hero("Investigation", tr(PAGE_LABEL["tx"]),
            L("Score du modèle, facteurs chiffrés vs habitudes du client, question libre au copilote, décision tracée",
              "Model score, quantified factors vs the customer's habits, free question to the copilot, traced decision"),
            status_chips())
    tid = st.selectbox("Transaction", ids, key="tx_select", format_func=lambda t: f"{risk_of[t]} {t}")
    st.session_state.tx = tid
    opened = st.session_state.setdefault("opened", {})
    opened.setdefault(tid, time.time())             # stopwatch: alert opened -> decision saved
    if tid == DEMO_TX.get("obvious_fraud"):
        mark("open")
    t = tools.get_transaction(tid)
    r = queue[queue.transaction_id == tid].iloc[0]
    tx, s = t["transaction"], t["score"]

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        badges = ui.badge(s["niveau_risque"], st.session_state.get("lang"))
        if pd.notna(r.demo_case):
            badges += " " + ui.chip(tr(DEMO_LABEL[r.demo_case]))
        meta = " · ".join(ui.esc(x) for x in [tx["timestamp"], tx.get("transaction_type"), tx.get("channel"), tx.get("entry_mode"),
                                               tx.get("merchant_category") or "—",
                                               f"{tx.get('city') or '—'} ({tx.get('country')})", tx.get("status")])
        ui.tx_card(tid, badges, meta + f"<br>{L('Client', 'Customer')} <b>{ui.esc(tx['customer_id'])}</b>")
        k1, k2, k3 = st.columns(3)
        k1.metric(L("Montant (TND)", "Amount (TND)"), f"{tx['amount_tnd']:,.3f}".replace(",", " "))
        if s["niveau_risque"] != "FAIBLE":
            k2.metric(L("Fraudes mesurées à ce score", "Measured fraud at this score"),
                      f"{float(tools.measured_fraud_rate([s['score_modele']])[0]):.0%}",
                      help=L(f"Percentile de risque {s['percentile_risque_periode']:.2%}. Part de vraies fraudes parmi les alertes "
                             "de score comparable en validation (juin–juillet 2026).",
                             f"Risk percentile {s['percentile_risque_periode']:.2%}. Share of real frauds among validation alerts "
                             "(June–July 2026) with a similar score."))
        else:
            k2.metric(L("Fraudes mesurées à ce score", "Measured fraud at this score"), L("sous le seuil", "below threshold"),
                      help=L(f"Percentile de risque {s['percentile_risque_periode']:.2%} : pas une alerte du modèle.",
                             f"Risk percentile {s['percentile_risque_periode']:.2%}: not a model alert."))
        k3.metric(L("Règles actuelles", "Current rules"),
                  L("Alerte", "Alert") if s["alerte_moteur_regles_actuel"] else L("Pas d'alerte", "No alert"))
        a, b = st.columns(2)
        with a:
            ui.section(L("Facteurs de risque", "Risk factors"))
            ui.factors(t["facteurs_modele_pour_fraude"] + t["regles_metier_declenchees"][:2], True, L("habituel", "usual"),
                       L("Aucun élément", "None"))
        with b:
            ui.section(L("Éléments rassurants", "Reassuring elements"))
            ui.factors(t["facteurs_modele_rassurants"] + t["regles_rassurantes"], False, L("habituel", "usual"),
                       L("Aucun élément", "None"))
        if r.period == "valid" and pd.notna(r.is_fraud):
            with st.expander(L("Vérité terrain (validation uniquement — jamais visible sur le flux du jour)",
                               "Ground truth (validation only — never shown on the live flow)")):
                st.write(L("Fraude", "Fraud") if r.is_fraud == 1 else L("Légitime", "Legitimate"),
                         r.fraud_scenario if pd.notna(r.fraud_scenario) else "")

        rs = t.get("recommandation_systeme") or {}
        if rs:
            dec_en = {"BLOQUER": "BLOCK", "ESCALADER": "ESCALATE", "VALIDER": "VALIDATE"}
            conf_en = {"faible": "low", "moyenne": "medium", "élevée": "high"}
            prec = rs.get("precision_mesuree_validation")
            prec_txt = (L(f" · {prec:.0%} de vraies fraudes à ce niveau en validation",
                          f" · {prec:.0%} true frauds at this level in validation") if prec is not None else "")
            st.info(L(f"**Recommandation système : {rs['decision']}** (confiance {rs['confiance']}){prec_txt} — l'analyste décide.",
                      f"**System recommendation: {dec_en[rs['decision']]}** ({conf_en[rs['confiance']]} confidence){prec_txt} "
                      f"— the analyst decides."), icon=":material/rule:")

        with st.form(f"decision_{tid}", clear_on_submit=True):
            st.markdown(f"**{L('Décision de l’analyste', 'Analyst decision')}**")
            d1, d2 = st.columns(2)
            options = ["BLOQUER", "ESCALADER", "VALIDER"]
            decision = d1.radio(L("Décision", "Decision"), options, horizontal=True,
                                index=options.index(rs["decision"]) if rs.get("decision") in options else 1,
                                format_func=lambda x: L(x, {"BLOQUER": "BLOCK", "ESCALADER": "ESCALATE", "VALIDER": "VALIDATE"}[x]))
            conf = d2.select_slider(L("Confiance", "Confidence"), ["faible", "moyenne", "élevée"], value=rs.get("confiance", "moyenne"),
                                    format_func=lambda x: L(x, {"faible": "low", "moyenne": "medium", "élevée": "high"}[x]))
            comment = st.text_input(L("Commentaire", "Comment"))
            elapsed = time.time() - opened.get(tid, time.time())
            st.caption(L(f"⏱️ Dossier ouvert depuis {elapsed:.0f} s — objectif : décision en moins de 30 s",
                         f"⏱️ Case open for {elapsed:.0f} s — target: decision in under 30 s"))
            if st.form_submit_button(L("Enregistrer la décision", "Save decision"), type="primary"):
                dur = time.time() - opened.get(tid, time.time())
                res = tools.record_decision(tid, decision, conf, comment, analyst=st.session_state.get("analyst"),
                                            source="interface", duration_s=dur)
                if res.get("enregistre"):
                    st.success(L(f"Décision {res['decision']} enregistrée en {dur:.0f} s", f"Decision {res['decision']} saved in {dur:.0f} s"))
                    mark("decide")
                else:
                    st.error(res)
        past = tools.decisions()
        past = past[past.transaction_id == tid]
        if len(past):
            st.caption(L("Décisions précédentes : ", "Previous decisions: ") +
                       " · ".join(f"{x.decision} ({x.confidence}, {x.decided_at})" for x in past.itertuples()))
        q0, q1, q2, q3 = st.columns(4)
        q0.button(L("🔎 Enquête approfondie", "🔎 Deep search"), on_click=open_tx, args=(tid, "deep"), width="stretch",
                  help=deepsearch.reason(tid, st.session_state.lang) or L("Preuves calculées sans token + 1 appel IA (~600 tokens).",
                                                                          "Evidence computed with no tokens + 1 AI call (~600 tokens)."))
        q1.button(L("⚖️ Le Procès", "⚖️ The Trial"), on_click=open_tx, args=(tid, "proces"), width="stretch")
        q2.button(L("🎬 Reconstitution", "🎬 Replay"), on_click=open_tx, args=(tid, "replay"), width="stretch")
        q3.download_button(L("🧾 Dossier (HTML)", "🧾 Case file (HTML)"), studio.case_file_html(ctx, tid).encode("utf-8"),
                           f"dossier_{tid}.html", "text/html", width="stretch",
                           help=L("Dossier d'investigation imprimable en PDF : faits, score, recommandation, Procès, échanges, décisions.",
                                  "Investigation file, printable to PDF: facts, score, recommendation, Trial, exchanges, decisions."))

    with right:
        ui.section(L("Copilote · réponses ancrées dans les données", "Copilot · answers grounded in the data"))
        history = st.session_state.chat.setdefault(tid, [])
        cols = st.columns(2)
        clicked = None
        for i, sug in enumerate(SUGGESTIONS):
            if cols[i % 2].button(tr(sug), key=f"sug_{tid}_{i}", width="stretch"):
                clicked = tr(sug)
        box = st.container(height=430)
        for m in history:
            with box.chat_message(m["role"]):
                st.markdown(m["content"])
                if m.get("meta"):
                    st.caption(m["meta"])
        question = st.chat_input(L("Posez votre question sur cette alerte…", "Ask a question about this alert…")) or clicked
        if question:
            with box.chat_message("user"):
                st.markdown(question)
            with box.chat_message("assistant"):
                steps = st.status(L("Recherche des faits…", "Looking up the facts…"), expanded=False)
                placeholder = st.empty()
                streamed = []

                def on_step(name):
                    steps.write(f"🔎 {copilot.STEP_LABEL.get(name, name)} · `{name}`")

                def on_token(text):
                    streamed.append(text)
                    placeholder.markdown("".join(streamed) + " ▌")

                out = copilot.ask(question, context_tx=tid, history=history, lang=st.session_state.get("lang", "fr"),
                                  on_token=on_token, on_step=on_step)
                n_tools = len(out["tools"])
                steps.update(label=L(f"{n_tools} source(s) consultée(s)", f"{n_tools} source(s) checked") +
                             (" · cache" if out.get("cached") else ""), state="complete")
                placeholder.markdown(out["answer"])
                tok = out["tokens"]
                cached_tok = f" ({tok.get('cached_prompt', 0)} {L('en cache', 'cached')})" if tok.get("cached_prompt") else ""
                meta = (f"{out['mode']} · {L('outils', 'tools')} : {', '.join(x['name'] for x in out['tools']) or '—'} · "
                        f"tokens : {tok['total']}{cached_tok}{' · cache' if out.get('cached') else ''} · {out.get('latency_s', 0)} s")
                st.caption(meta)
            history += [{"role": "user", "content": question}, {"role": "assistant", "content": out["answer"], "meta": meta}]
            mark("ask")
        if st.session_state.get("lang") == "en" and not copilot.configured():
            st.caption("Offline mode answers in French (rule templates); the LLM answers in English.")
        st.button(tr(PAGE_LABEL["cust"]), on_click=open_tx, args=(tid, "cust"), icon=":material/person:")


# ---------------------------------------------------------------- 3. customer 360
def _pick_customer(row):
    """Open a customer found by description: on their riskiest alert if they have one (habits = before it)."""
    if row.get("alerte_la_plus_risquee") and row["alerte_la_plus_risquee"] in set(queue.transaction_id):
        open_tx(row["alerte_la_plus_risquee"], "cust")
    else:
        st.session_state.cust_override = row["customer_id"]


def customer_search():
    with st.container(border=True):
        sq = st.text_input(L("Rechercher un client par description", "Find a customer by description"), key="cust_search",
                           placeholder=L("ex. client retraité de Sfax de plus de 70 ans avec des alertes",
                                         "e.g. retired customer in Sfax over 70 with alerts"))
        if not sq:
            st.caption(L("Ville, segment, profession, âge, KYC, « avec alertes » · recherche en lecture seule sur filtres autorisés, 0 token.",
                         "City, segment, occupation, age, KYC, \"with alerts\" · read-only search on approved filters, 0 tokens."))
            return
        f = person_search.parse(sq)
        if not {k for k in f if k not in ("with_alerts", "digital")}:
            st.warning(L("Aucun critère reconnu (ville, segment, profession, âge, KYC).", "No criterion recognised (city, segment, occupation, age, KYC)."))
            return
        res = person_search.find_customers(**f, limit=8)
        st.caption(L("Critères compris : ", "Understood criteria: ") + ", ".join(f"{k} = {v}" for k, v in f.items()) +
                   f" · {res.get('nb_clients_correspondants', 0)} " + L("client(s)", "customer(s)"))
        for row in res.get("clients", []):
            a, b = st.columns([6, 1])
            al = (L(f"{row['nb_alertes']} alerte(s)", f"{row['nb_alertes']} alert(s)") if row["nb_alertes"] else L("aucune alerte", "no alert"))
            a.markdown(f"**{row['customer_id']}** · {row['age']} {L('ans', 'y/o')} · {row['segment']} · {row['occupation']} · "
                       f"{row['ville']} · KYC {row['kyc']} · {al}")
            b.button(L("Ouvrir", "Open"), key=f"pick_{row['customer_id']}", on_click=_pick_customer, args=(row,), width="stretch")


def page_customer():
    r = queue[queue.transaction_id == st.session_state.tx].iloc[0]
    customer_search()
    cust = st.text_input(L("Client", "Customer"), st.session_state.pop("cust_override", r.customer_id))
    # habits = the customer's past at the time of the open alert (same rule as the copilot; never later operations)
    prof = tools.get_customer_profile(cust, before_transaction_id=r.transaction_id if cust == r.customer_id else None)
    if "erreur" in prof:
        st.error(prof["erreur"])
        return
    p, hab = prof.get("profil", {}), prof.get("habitudes", {})
    ui.hero(L("Connaissance client", "Know your customer"), f"{tr(PAGE_LABEL['cust'])} · {cust}",
            L("Profil, habitudes, timeline des opérations et événements digitaux autour de l'alerte",
              "Profile, habits, timeline of operations and digital events around the alert"), status_chips())
    c = st.columns(6)
    c[0].metric(L("Âge", "Age"), p.get("age", "—"))
    c[1].metric("Segment", p.get("segment", "—"))
    c[2].metric(L("Ville", "City"), p.get("home_city", "—"))
    c[3].metric(L("Revenu mensuel", "Monthly income"), money(p["monthly_income_tnd"]) if p.get("monthly_income_tnd") else "—")
    c[4].metric("KYC", p.get("kyc_risk_level", "—"))
    c[5].metric(L("Alertes en file", "Alerts in queue"), prof["nb_alertes_dans_file"])
    if hab:
        h = st.columns(5)
        h[0].metric(L("Opérations", "Operations"), hab["nb_operations"], help=hab["periode_observee"])
        h[1].metric(L("Montant moyen", "Average amount"), money(hab["montant_moyen"]))
        h[2].metric(L("Montant p95", "Amount p95"), money(hab["montant_p95"]))
        h[3].metric(L("Part de nuit", "Night share"), f"{hab['part_operations_nuit_0h_6h']:.1%}")
        h[4].metric(L("Appareils / bénéficiaires", "Devices / beneficiaries"), f"{hab['nb_appareils']} / {hab['nb_beneficiaires']}")
        st.caption(L("Pays physiques : ", "Physical countries: ") +
                   ", ".join(f"{x['valeur']} ({x['part']:.0%})" for x in hab["pays_paiements_physiques"]) +
                   L(" · Canaux : ", " · Channels: ") + ", ".join(f"{x['valeur']} ({x['part']:.0%})" for x in hab["canaux"]) +
                   L(" · Catégories : ", " · Categories: ") + ", ".join(x["valeur"] for x in hab["categories"]))

    t = da.customer_tx(cust).copy()
    if t.empty:
        st.info(L("Aucune opération pour ce client.", "No operations for this customer."))
        return
    anchor = r.timestamp if r.customer_id == cust else t.timestamp.max()
    days = st.slider(L("Fenêtre de la timeline (jours avant l'alerte)", "Timeline window (days before the alert)"), 1, 30, 7)
    lo, hi = anchor - pd.Timedelta(days=days), anchor + pd.Timedelta(hours=6)
    w = t[(t.timestamp <= hi) & (t.timestamp >= lo)].copy()
    alerted = set(queue.transaction_id)
    w["⚑"] = w.transaction_id.map(lambda x: "🎯" if x == st.session_state.tx else ("🚨" if x in alerted else ""))
    ui.section(L("Timeline des opérations", "Operations timeline"))
    kinds = {"": L("normale", "normal"), "🚨": L("alerte", "alert"), "🎯": L("alerte ouverte", "open alert")}
    st.scatter_chart(w.assign(type=w["⚑"].replace(kinds)), x="timestamp", y="amount_tnd", color="type", height=260)
    e = da.events(cust, lo.to_pydatetime(), hi.to_pydatetime())
    if e is not None and len(e):
        w = pd.concat([w, e.assign(**{"⚑": "📱", "transaction_type": e.event_type})], ignore_index=True)
        st.caption(L(f"📱 {len(e)} événement(s) digital(aux) dans la fenêtre, dont {int((e.status == 'ECHEC').sum())} échec(s).",
                     f"📱 {len(e)} digital event(s) in the window, {int((e.status == 'ECHEC').sum())} failed."))
    st.dataframe(w.sort_values("timestamp", ascending=False)[
        [c for c in ["⚑", "timestamp", "transaction_id", "transaction_type", "channel", "entry_mode", "merchant_category",
                     "amount_tnd", "city", "country", "status", "decline_reason", "device_id", "ip_country", "beneficiary_id"]
         if c in w.columns]],
        hide_index=True, width="stretch", height=360)
    geo = w.dropna(subset=["latitude", "longitude"]) if {"latitude", "longitude"} <= set(w.columns) else pd.DataFrame()
    if len(geo):
        geo = geo.assign(color=geo["⚑"].map({"🎯": "#d62728", "🚨": "#ff7f0e"}).fillna("#1f77b4"),
                         size=geo["⚑"].map({"🎯": 400, "🚨": 250}).fillna(120))
        ui.section(L("Carte des opérations physiques", "Map of physical operations"))
        st.map(geo, latitude="latitude", longitude="longitude", color="color", size="size")
        st.caption(L("🔴 alerte ouverte · 🟠 autres alertes · 🔵 opérations habituelles",
                     "🔴 open alert · 🟠 other alerts · 🔵 usual operations"))
    else:
        st.caption(L("🗺️ Carte : aucune opération géolocalisée dans la fenêtre (paiements en ligne / virements).",
                     "🗺️ Map: no geolocated operation in the window (online payments / transfers)."))


# ---------------------------------------------------------------- 4. performance
def page_performance():
    k = tools.get_kpis()
    lg, same, top = k["moteur_regles_actuel"], k["modele_meme_volume"], k["modele_top_1pct"]
    ui.hero(L("Validation hors échantillon · juin → juillet 2026", "Out-of-time validation · June → July 2026"),
            tr(PAGE_LABEL["perf"]),
            L("Comparaison chiffrée au moteur de règles actuel, à volume d'alertes égal et à capacité analystes",
              "Quantified comparison with the current rule engine, at equal alert volume and at analyst capacity"), status_chips())
    vs = L("vs moteur actuel", "vs current rules")
    c = st.columns(4)
    c[0].metric(L("Fraudes détectées (top 1 %)", "Frauds caught (top 1%)"), nb(top["fraudes_detectees"]),
                f"+{top['fraudes_detectees'] - lg['fraudes_detectees']} {vs}")
    c[1].metric(L("Fausses alertes", "False alerts"), nb(top["fausses_alertes"]),
                f"{nb(top['fausses_alertes'] - lg['fausses_alertes'])} {vs}", delta_color="inverse")
    c[2].metric(L("Précision", "Precision"), f"{top['precision']:.1%}", f"{(top['precision'] - lg['precision']) * 100:+.1f} pts")
    c[3].metric(L("Rappel", "Recall"), f"{top['rappel']:.1%}", f"{(top['rappel'] - lg['rappel']) * 100:+.1f} pts")
    A, AL, F, P, R = (L("Approche", "Approach"), L("Alertes", "Alerts"), L("Fraudes détectées", "Frauds caught"),
                      L("Précision", "Precision"), L("Rappel", "Recall"))
    comp = pd.DataFrame([
        {A: L("Moteur de règles actuel", "Current rule engine"), AL: lg["alertes"], F: lg["fraudes_detectees"],
         P: lg["precision"], R: lg["rappel"]},
        {A: L("Modèle, même volume d'alertes", "Model, same alert volume"), AL: same["alertes"], F: same["fraudes_detectees"],
         P: same["precision"], R: same["rappel"]},
        {A: L("Modèle, top 1 % (capacité analystes)", "Model, top 1% (analyst capacity)"), AL: top["alertes"],
         F: top["fraudes_detectees"], P: top["precision"], R: top["rappel"]}])
    st.dataframe(comp, hide_index=True, width="stretch",
                 column_config={P: st.column_config.NumberColumn(format="percent"), R: st.column_config.NumberColumn(format="percent")})
    a, b = st.columns(2)
    names = da.SCENARIO_EN if st.session_state.get("lang") == "en" else da.SCENARIO_FR
    with a:
        ui.section(L("Rappel par typologie", "Recall by fraud type"))
        rt = da.recall_by_type().assign(typologie=lambda d: d.fraud_scenario.map(names).fillna(d.fraud_scenario))
        rt = rt.set_index("typologie")[["recall_model", "recall_legacy"]]
        st.bar_chart(rt.rename(columns={"recall_model": L("Modèle (top 1 %)", "Model (top 1%)"),
                                        "recall_legacy": L("Règles actuelles", "Current rules")}),
                     stack=False, horizontal=True, height=320, color=[ui.BLUE, "#5B6B8C"])
    with b:
        ui.section(L("Principaux facteurs du modèle", "Main model drivers"))
        imp = da.importance().sort_values("gain_share", ascending=False).head(12)
        lab = imp.feature.map(da.FEATURE_EN).fillna(imp.label) if st.session_state.get("lang") == "en" else imp.label
        st.bar_chart(imp.assign(lab=lab).set_index("lab")["gain_share"].rename(L("Part du gain", "Gain share")),
                     horizontal=True, height=320, color=ui.BLUE2)
    ui.section("Champion vs challengers")
    pct = lambda lab_: st.column_config.NumberColumn(lab_, format="percent")
    st.dataframe(da.leaderboard(), hide_index=True, width="stretch",
                 column_config={"model": L("Modèle", "Model"), "pr_auc": st.column_config.NumberColumn("PR-AUC", format="%.3f"),
                                "top1pct_precision": pct(L("Précision top 1 %", "Precision top 1%")),
                                "top1pct_recall": pct(L("Rappel top 1 %", "Recall top 1%")),
                                "legacy_budget_precision": pct(L("Précision (volume règles)", "Precision (rules volume)")),
                                "legacy_budget_recall": pct(L("Rappel (volume règles)", "Recall (rules volume)")),
                                "champion": st.column_config.CheckboxColumn("Champion")})
    st.caption(L(f"PR-AUC du modèle : {k['pr_auc_modele']} · {k['fraudes_validation']} fraudes en validation · "
                 "Le moteur actuel reste meilleur sur CARTE_CLONEE_ETRANGER : sa règle est conservée en complément.",
                 f"Model PR-AUC: {k['pr_auc_modele']} · {k['fraudes_validation']} frauds in validation · "
                 "The current engine stays better on cards cloned abroad: its rule is kept as a complement."))
    page_robustness()


def page_robustness():
    """Proof that the result is not a lucky period: rolling backtest, confidence intervals, registry, copilot evaluation."""
    rob, ci, ev = fx.robustness(), fx.model_ci(), fx.copilot_eval()
    if rob is None and ci is None and ev is None:
        return
    ui.section(L("Robustesse et gouvernance du modèle", "Model robustness and governance"))
    if rob is not None and len(rob):
        r = rob.top1_recall
        c = st.columns(4)
        with c[0]:
            ui.kpi(L("Rappel top 1 % · 4 périodes", "Top-1% recall · 4 periods"), f"{r.mean():.1%}",
                   L(f"± <b>{r.std(ddof=1) * 100:.1f} pts</b> d'une période à l'autre (ré-entraîné sur le passé à chaque fois)",
                     f"± <b>{r.std(ddof=1) * 100:.1f} pts</b> from one period to the next (re-trained on the past each time)"))
        with c[1]:
            ui.kpi(L("Pire période", "Worst period"), f"{r.min():.1%}",
                   L("rappel top 1 % le plus bas des 4 tests", "lowest top-1% recall of the 4 tests"))
        with c[2]:
            ui.kpi(L("Fraude en valeur (TND) détectée", "Fraud value (TND) caught"), f"{rob.value_recall.mean():.1%}",
                   L("moyenne des 4 périodes", "mean of the 4 periods"))
        with c[3]:
            ui.kpi(L("Règles actuelles · mêmes périodes", "Current rules · same periods"), f"{rob.legacy_recall.mean():.1%}",
                   L(f"rappel · précision <b>{rob.legacy_precision.mean():.1%}</b>",
                     f"recall · precision <b>{rob.legacy_precision.mean():.1%}</b>"))
        fold = L("Période de test", "Test period")
        labels = [f"{pd.Timestamp(a):%m/%Y} → {pd.Timestamp(b):%m/%Y}" + (" · validation" if i == len(rob) - 1 else "")
                  for i, (a, b) in enumerate(zip(rob.test_from, rob.test_to))]
        view = rob.assign(**{fold: labels})[
            [fold, "train_rows", "test_rows", "test_frauds", "pr_auc", "top1_precision", "top1_recall", "value_recall",
             "legacy_precision", "legacy_recall"]]
        pct = lambda lab_: st.column_config.NumberColumn(lab_, format="percent")
        st.dataframe(view, hide_index=True, width="stretch",
                     column_config={"train_rows": st.column_config.NumberColumn(L("Lignes d'entraînement", "Training rows")),
                                    "test_rows": st.column_config.NumberColumn(L("Opérations testées", "Operations tested")),
                                    "test_frauds": st.column_config.NumberColumn(L("Fraudes", "Frauds")),
                                    "pr_auc": st.column_config.NumberColumn("PR-AUC", format="%.3f"),
                                    "top1_precision": pct(L("Précision top 1 %", "Precision top 1%")),
                                    "top1_recall": pct(L("Rappel top 1 %", "Recall top 1%")),
                                    "value_recall": pct(L("Fraude en TND détectée", "Fraud TND caught")),
                                    "legacy_precision": pct(L("Précision règles", "Rules precision")),
                                    "legacy_recall": pct(L("Rappel règles", "Rules recall"))})
    if ci is not None and len(ci):
        name = {"top1_precision": L("Précision top 1 %", "Precision top 1%"), "top1_recall": L("Rappel top 1 %", "Recall top 1%"),
                "pr_auc": "PR-AUC", "legacy_precision": L("Précision règles actuelles", "Current rules precision"),
                "legacy_recall": L("Rappel règles actuelles", "Current rules recall"),
                "recall_gain_points": L("Gain de rappel vs règles", "Recall gain vs rules"),
                "false_alerts_avoided": L("Fausses alertes évitées", "False alerts avoided")}

        def fmt(m, v):
            return f"{v:,.0f}".replace(",", " ") if m == "false_alerts_avoided" else (f"{v:.3f}" if m == "pr_auc" else f"{v:.1%}")
        rows = [{L("Indicateur (validation juin–juillet)", "Metric (validation June–July)"): name.get(x.metric, x.metric),
                 L("Valeur", "Value"): fmt(x.metric, x.estimate),
                 L("Intervalle de confiance 95 %", "95% confidence interval"): f"[{fmt(x.metric, x.ci_low)} ; {fmt(x.metric, x.ci_high)}]"}
                for x in ci.itertuples()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if ev:
        res = ev["results"]
        nums = sum(r["numbers_checked"] for r in res)
        faith = sum(r["faithfulness"] * r["numbers_checked"] for r in res) / max(nums, 1)
        st.caption(L(f"Copilote : {sum(r['passed'] for r in res)}/{len(res)} questions de référence réussies "
                     f"(§9.7 + garde-fous), {faith:.1%} des chiffres cités retrouvés dans les données des outils "
                     f"(évaluation du {ev['run'][:10]}, docs/COPILOT_EVAL.md).",
                     f"Copilot: {sum(r['passed'] for r in res)}/{len(res)} golden questions passed (§9.7 + guardrails), "
                     f"{faith:.1%} of the numbers cited found in the tools' data (evaluation of {ev['run'][:10]}, docs/COPILOT_EVAL.md)."))
    st.caption(L("Méthode : backtest glissant (notebook Fabric 04_robustness : mêmes variables, échantillonnage et réglages que la "
                 "production, ré-entraîné 4 fois sur le passé seulement) · intervalles par bootstrap de journées entières (1 000 tirages) · "
                 "modèle enregistré dans MLflow (« hyson-fraud-lightgbm », identique aux scores de production : corrélation 1,0) · "
                 "réentraînement orchestré par le pipeline Fabric « pl_hyson_retrain ».",
                 "Method: rolling backtest (Fabric notebook 04_robustness: same features, sampling and settings as production, re-trained "
                 "4 times on the past only) · intervals by whole-day bootstrap (1,000 resamples) · model registered in MLflow "
                 "(\"hyson-fraud-lightgbm\", identical to production scores: correlation 1.0) · retraining orchestrated by the Fabric "
                 "pipeline \"pl_hyson_retrain\"."))
    fairness.render_fairness(L, src.mode)
    fairness.render_limits(L)


# ---------------------------------------------------------------- 5. journal
def page_journal():
    ui.hero(L("Gouvernance", "Governance"), tr(PAGE_LABEL["journal"]),
            L("Décisions des analystes (boucle de feedback) et journal du copilote : questions, outils, tokens",
              "Analyst decisions (feedback loop) and copilot log: questions, tools, tokens"), status_chips())
    d = tools.decisions()
    c = st.columns(4)
    c[0].metric(L("Décisions", "Decisions"), len(d))
    for i, lab in enumerate(["BLOQUER", "ESCALADER", "VALIDER"], 1):
        c[i].metric(L(lab, {"BLOQUER": "BLOCK", "ESCALADER": "ESCALATE", "VALIDER": "VALIDATE"}[lab]),
                    int((d.decision == lab).sum()) if len(d) else 0)
    if len(d):
        ui.section(L("Piste d'audit", "Audit trail"))
        integ = tools.verify_journal()
        with_reco = d[d.system_decision.astype(str).str.len() > 0] if "system_decision" in d else d.iloc[0:0]
        over = with_reco[with_reco.decision != with_reco.system_decision]
        a1, a2, a3 = st.columns(3)
        a1.metric(L("Intégrité du journal", "Log integrity"), L("✅ intacte", "✅ intact") if integ["ok"] else L("❌ modifiée", "❌ altered"),
                  help=L("Chaque décision porte l'empreinte SHA-256 de la précédente : modifier ou supprimer une ligne passée "
                         "casse toute la chaîne.", "Each decision carries the SHA-256 fingerprint of the previous one: editing or "
                         "deleting a past row breaks the whole chain."))
        a2.metric(L("Désaccord analyste / recommandation", "Analyst overrides the recommendation"),
                  f"{len(over) / max(len(with_reco), 1):.0%}" if len(with_reco) else "—",
                  help=L("Part des décisions différentes de la recommandation système affichée au moment de la décision "
                         "(supervision humaine, à revoir par le superviseur).",
                         "Share of decisions that differ from the system recommendation shown at decision time "
                         "(human oversight, for supervisor review)."))
        a3.metric(L("Analystes", "Analysts"), d.analyst.nunique() if "analyst" in d else 0)
        if integ["ok"]:
            st.caption(L(f"Chaîne vérifiée sur {integ['rows']} décisions · dernière empreinte {integ.get('last_hash', '')}… · "
                         f"modèle et version du prompt enregistrés avec chaque décision.",
                         f"Chain verified on {integ['rows']} decisions · last fingerprint {integ.get('last_hash', '')}… · "
                         "model and prompt version stored with every decision."))
        else:
            st.error(L(f"Le journal a été modifié hors application à partir de la décision n° {integ['broken_at'] + 1}.",
                       f"The log was edited outside the application from decision #{integ['broken_at'] + 1}."))
        if len(over):
            st.caption(L("Désaccords à revoir : ", "Overrides to review: ") +
                       " · ".join(f"{x.transaction_id} ({x.system_decision} → {x.decision}, {x.analyst})" for x in over.tail(5).itertuples()))
        with st.expander(L("Intégration au SI de la banque · message de la dernière décision (simulation)",
                           "Bank IT integration · message of the latest decision (simulation)"), icon=":material/hub:"):
            ev = tools.decision_event(d.iloc[-1].to_dict())
            st.json(ev)
            st.caption(L("En production, ce message part par la passerelle API / Service Bus vers la monétique (blocage de carte), "
                         "le core banking (gel du virement), la gestion de dossiers et la notification client ; le double contrôle "
                         f"(« quatre yeux ») s'applique aux blocages ≥ {tools.FOUR_EYES_TND:,.0f} TND et aux décisions qui écartent "
                         "un BLOQUER recommandé. Ici, rien n'est envoyé.".replace(",", " "),
                         "In production this message goes through the API gateway / Service Bus to card management (block card), "
                         "core banking (hold transfer), case management and customer notification; four-eyes approval applies to "
                         f"blocks ≥ {tools.FOUR_EYES_TND:,.0f} TND and to decisions that set aside a recommended BLOCK. Nothing is sent "
                         "from this demo.".replace(",", " ")))
        d = d.merge(queue[["transaction_id", "risk_level", "score_pct", "period"]], on="transaction_id", how="left")
        show = [x for x in ["decided_at", "transaction_id", "decision", "system_decision", "confidence", "analyst", "source",
                            "duration_s", "comment", "risk_level", "model_version", "prompt_version", "row_hash"] if x in d.columns]
        st.dataframe(d.sort_values("decided_at", ascending=False)[show], hide_index=True, width="stretch",
                     column_config={"row_hash": st.column_config.TextColumn(L("Empreinte", "Fingerprint"), width="small")})
        st.download_button(L("Exporter (CSV)", "Export (CSV)"), d.to_csv(index=False).encode("utf-8"), "decisions.csv", "text/csv")
        st.caption(L("Boucle d'amélioration : ces décisions deviennent des labels pour le prochain réentraînement dans Fabric.",
                     "Improvement loop: these decisions become labels for the next retraining in Fabric."))
    ui.section(L("Traçabilité du copilote", "Copilot traceability"))
    u = copilot.usage_summary()
    st.caption(L(f"{u['appels']} questions · {nb(u['tokens'])} tokens · {u['caches']} réponses servies par le cache",
                 f"{u['appels']} questions · {nb(u['tokens'])} tokens · {u['caches']} answers served from cache"))
    if u.get("rows"):
        log = pd.DataFrame(u["rows"])
        log["outils"] = log.tools.map(lambda x: ", ".join(t["name"] for t in x))
        log["tokens_total"] = log.tokens.map(lambda x: x.get("total", 0))
        log["tokens_cached"] = log.tokens.map(lambda x: x.get("cached_prompt", 0))
        st.dataframe(log[[c for c in ["ts", "context_tx", "lang", "intent", "question", "mode", "outils", "tokens_total",
                                      "tokens_cached", "rounds", "cached", "latency_s"]
                          if c in log.columns]].iloc[::-1], hide_index=True, width="stretch")


# ---------------------------------------------------------------- 6. Power BI (manager view)
# icon -> (FR title, EN title, FR section, EN section): same icons and names as the report's own navigation bar
PBI_PAGES = {"files": ("Vue exécutive", "Executive view", "p1exec", "p1exec_en"),
             "warning": ("File d'alertes", "Alert queue", "p2queue", "p2queue_en"),
             "question": ("Pourquoi ?", "Why?", "p3why", "p3why_en"),
             "typologies": ("Typologies", "Fraud types", "p4types", "p4types_en")}


def page_powerbi():
    from urllib.parse import urlencode

    ui.hero(L("Pilotage", "Management"), tr(PAGE_LABEL["pbi"]),
            L("Vue manager en Direct Lake sur les tables Gold de Fabric · cliquez une icône pour changer de page",
              "Manager view in Direct Lake on the Fabric Gold tables · click an icon to change page"), status_chips())
    st.session_state.setdefault("pbi_tab", "files")
    cols = st.columns(len(PBI_PAGES) + 2)
    for col, (icon, (fr, en, _, _)) in zip(cols, PBI_PAGES.items()):
        with col:
            active = st.session_state.pbi_tab == icon
            st.markdown(ui.icon_html(ICON_DIR / f"{icon}.png", active), unsafe_allow_html=True)
            if st.button(L(fr, en), key=f"pbi_{icon}", type="primary" if active else "secondary", width="stretch"):
                st.session_state.pbi_tab = icon
                st.rerun()
    fr, en, sec_fr, sec_en = PBI_PAGES[st.session_state.pbi_tab]
    section = sec_en if st.session_state.get("lang") == "en" else sec_fr
    report = os.getenv("PBI_REPORT_ID", "146f267f-bb36-4331-9897-a414d7bb2894")
    tenant = os.getenv("PBI_TENANT_ID", "2db552ee-04d3-40c4-b4a6-87474f06a6d5")
    group = os.getenv("FABRIC_WORKSPACE_ID", "8d6c2b96-7b50-4b1a-87b1-e8f872903613")
    cols[-1].link_button(L("Ouvrir dans Power BI ↗", "Open in Power BI ↗"),
                         f"https://app.fabric.microsoft.com/groups/{group}/reports/{report}/{section}?experience=power-bi")
    # Secure embed: the viewer signs in with their organisation account (no public "publish to web").
    params = {"reportId": report, "autoAuth": "true", "ctid": tenant, "pageName": section,
              "navContentPaneEnabled": "false", "filterPaneEnabled": "false"}
    st.iframe("https://app.powerbi.com/reportEmbed?" + urlencode(params), height=780)
    st.caption(L("Direct Lake sur les tables Gold de Fabric (modèle sm_fraud_copilot) · rapport construit en code "
                 "(notebooks/03e_powerbi_dashboard.ipynb) · connexion avec le compte de l'organisation requise.",
                 "Direct Lake on the Fabric Gold tables (model sm_fraud_copilot) · report built as code "
                 "(notebooks/03e_powerbi_dashboard.ipynb) · organisation sign-in required."))


@st.dialog("Bienvenue sur Hyson Detector · Welcome", width="large")
def welcome():
    st.markdown(f'<div style="display:flex;justify-content:center;margin:-.4rem 0 .4rem">{ui.logo("blue", 84)}</div>',
                unsafe_allow_html=True)
    st.markdown(L(
        "### Le copilote de l'analyste fraude\n"
        "Hyson Detector **détecte** les transactions suspectes (modèle entraîné dans Microsoft Fabric), **explique** chaque alerte "
        "avec les données de la banque (Azure OpenAI) et vous aide à **décider** : bloquer, escalader ou valider.\n\n"
        "**Première visite ?** La visite guidée vous montre tout en 3 minutes, avec de vrais cas : une prise de contrôle de compte, "
        "une fraude discrète et un client honnête que l'ancien moteur aurait bloqué.",
        "### The fraud analyst's copilot\n"
        "Hyson Detector **detects** suspicious transactions (model trained in Microsoft Fabric), **explains** every alert with the "
        "bank's data (Azure OpenAI) and helps you **decide**: block, escalate or validate.\n\n"
        "**First visit?** The guided tour shows you everything in 3 minutes with real cases: an account takeover, a discreet fraud "
        "and an honest customer the old engine would have blocked."))
    a, b = st.columns(2)
    if a.button(L("▶ Lancer la visite guidée (3 min)", "▶ Start the guided tour (3 min)"), type="primary", width="stretch"):
        st.session_state.tour = True
        st.session_state.goto = "guide"
        st.rerun()
    if b.button(L("Explorer librement", "Explore freely"), width="stretch"):
        st.rerun()


ctx = SimpleNamespace(L=L, lang=st.session_state.get("lang", "fr"), queue=queue, open_tx=open_tx, go=go, chips=status_chips,
                      mark=mark, demos=DEMO_TX)
if not st.session_state.get("welcomed"):
    st.session_state.welcomed = True
    welcome()
studio.tour_hint(ctx, page)
{"guide": lambda: studio.page_guide(ctx), "queue": page_queue, "tx": page_transaction, "cust": page_customer,
 "deep": lambda: studio.page_deep(ctx), "proces": lambda: studio.page_proces(ctx), "replay": lambda: studio.page_replay(ctx), "contre": lambda: studio.page_contre(ctx),
 "galaxy": lambda: studio.page_galaxy(ctx), "impact": lambda: studio.page_impact(ctx),
 "market": lambda: market.page_market(ctx, src.mode), "perf": page_performance,
 "journal": page_journal, "pbi": page_powerbi,
 "onboard": lambda: onboarding.page_onboarding(ctx, src.mode)}[page]()
ui.footer(L("Hyson Detector · données 100 % synthétiques · Microsoft Fabric (Lakehouse lh_fraud) · Azure OpenAI · "
            "le modèle score, l'IA explique, l'analyste décide",
            "Hyson Detector · 100% synthetic data · Microsoft Fabric (Lakehouse lh_fraud) · Azure OpenAI · "
            "the model scores, AI explains, the analyst decides"))
