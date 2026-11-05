"""Hyson Detector — the pages that make the difference: first-time guide, business impact & process,
Le Procès (AI courtroom), Reconstitution (crime-scene replay), Contre-enquête (counterfactual),
Constellation (points of compromise) and the regulatory case file.

Pages receive a context `c` built in app.py: c.L(fr, en), c.lang, c.queue, c.open_tx(tid, page), c.go(page),
c.chips(), c.mark(step), c.demos (dict demo_case -> transaction_id).
"""
import html
import math
import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

import copilot
import courtroom
import data_access as da
import deepsearch
import features as fx
import tools
import ui

DEC_EN = {"BLOQUER": "BLOCK", "ESCALADER": "ESCALATE", "VALIDER": "VALIDATE"}
CONF_EN = {"faible": "low", "moyenne": "medium", "élevée": "high"}


def _money(x, d=0):
    return f"{x:,.{d}f} TND".replace(",", " ")


def _nb(x):
    return f"{int(x):,}".replace(",", " ")


def _tx_picker(c, key, label=None):
    ids = c.queue.transaction_id.tolist()
    risk_of = dict(zip(c.queue.transaction_id, c.queue.risk_icon))
    demo_of = {v: k for k, v in c.demos.items()}
    cur = st.session_state.get("tx") if st.session_state.get("tx") in ids else ids[0]
    if st.session_state.get(key) not in ids:
        st.session_state[key] = cur
    names = {"obvious_fraud": c.L("fraude évidente", "obvious fraud"), "subtle_fraud": c.L("fraude subtile", "subtle fraud"),
             "avoided_false_positive": c.L("faux positif évité", "avoided false positive")}
    tid = st.selectbox(label or "Transaction", ids, key=key,
                       format_func=lambda t: f"{risk_of[t]} {t}" + (f" · 🎬 {names[demo_of[t]]}" if t in demo_of else ""))
    st.session_state.tx = tid
    return tid


# ================================================================= 0. guide (first-time user)
TOUR = [  # (step id, FR title, EN title, FR text, EN text, page, demo case)
    ("open", "Ouvrir une vraie fraude", "Open a real fraud",
     "Une prise de contrôle de compte : 3 échecs de connexion depuis l'Italie, un bénéficiaire ajouté, puis 3 virements de nuit.",
     "An account takeover: 3 failed logins from Italy, a new beneficiary, then 3 night transfers.", "tx", "obvious_fraud"),
    ("ask", "Poser une question au copilote", "Ask the copilot a question",
     "Cliquez « Pourquoi cette transaction est-elle suspecte ? » : la réponse est chiffrée, sourcée et suit le format en 5 parties.",
     "Click “Why is this transaction suspicious?”: the answer is quantified, sourced and follows the 5-part format.", "tx", None),
    ("proces", "Assister au Procès", "Watch the Trial",
     "Un procureur IA et un avocat IA plaident avec les mêmes faits ; un juge IA tranche. Vous gardez le dernier mot.",
     "An AI prosecutor and an AI defence lawyer plead with the same facts; an AI judge rules. You keep the last word.", "proces", None),
    ("replay", "Revoir la scène", "Replay the scene",
     "La Reconstitution rejoue les heures qui précèdent l'alerte, étape par étape, avec les signaux en rouge.",
     "The Replay plays back the hours before the alert, step by step, with risk signals in red.", "replay", None),
    ("decide", "Décider en moins de 30 secondes", "Decide in under 30 seconds",
     "Revenez sur la fiche et enregistrez la décision : le chronomètre mesure le temps alerte → décision.",
     "Go back to the case and save the decision: the stopwatch measures alert → decision time.", "tx", None),
    ("fp", "Comprendre un faux positif évité", "Understand an avoided false positive",
     "3 361 TND chez un commerçant de Tunis : le moteur actuel alerte, le modèle non. La Contre-enquête montre pourquoi c'est robuste.",
     "3,361 TND at a Tunis shop: the current rules alert, the model does not. The Counter-inquiry shows why this is robust.",
     "contre", "avoided_false_positive"),
    ("galaxy", "Explorer la Constellation", "Explore the Constellation",
     "Les points de compromission (DAB, commerçants) par où sont passées les cartes fraudées, et les alertes du jour qui y sont liées.",
     "Points of compromise (ATMs, merchants) that defrauded cards went through, and today's alerts linked to them.", "galaxy", None),
    ("impact", "Voir l'impact pour la banque", "See the impact for the bank",
     "Fraude interceptée en TND, paiements légitimes épargnés, charge analystes, coût IA par dossier, gouvernance du modèle.",
     "Fraud intercepted in TND, legitimate payments spared, analyst workload, AI cost per case, model governance.", "impact", None),
]


def next_step(c):
    done = st.session_state.setdefault("done", set())
    return next((s for s in TOUR if s[0] not in done), None)


def _go_step(c, step):
    sid, *_, page, demo = step
    if demo and c.demos.get(demo):
        c.open_tx(c.demos[demo], page)
    else:
        c.go(page)


def tour_hint(c, page):
    """Small banner on every page while the guided tour is running."""
    if not st.session_state.get("tour") or page == "guide":
        return
    s = next_step(c)
    if s is None:
        ui.hint(c.L("🎉 <b>Visite terminée.</b> Vous avez vu tout le parcours : détecter → expliquer → décider → piloter.",
                    "🎉 <b>Tour complete.</b> You have seen the whole journey: detect → explain → decide → steer."))
        return
    n = [x[0] for x in TOUR].index(s[0]) + 1
    a, b = st.columns([5, 1.3])
    with a:
        ui.hint(f"🧭 <b>{c.L('Visite guidée', 'Guided tour')} · {c.L('étape', 'step')} {n}/{len(TOUR)} :</b> "
                f"{html.escape(c.L(s[1], s[2]))} — {html.escape(c.L(s[3], s[4]))}")
    with b:
        st.button(c.L("Y aller →", "Go →"), key=f"tour_go_{page}", on_click=_go_step, args=(c, s), type="primary", width="stretch")


def page_guide(c):
    done = st.session_state.setdefault("done", set())
    st.markdown(
        f'<div class="welcome"><span class="tag">{c.L("Bienvenue", "Welcome")}</span>'
        f'<h1>Hyson Detector</h1><p>{html.escape(c.L(
            "Le copilote de l’analyste fraude : le modèle score chaque transaction, l’IA explique avec les données de la banque, "
            "l’analyste décide. Cette visite de 3 minutes vous montre tout le parcours, comme au premier jour.",
            "The fraud analyst's copilot: the model scores every transaction, AI explains with the bank's data, the analyst decides. "
            "This 3-minute tour shows you the whole journey, just like on your first day."))}</p></div>', unsafe_allow_html=True)
    k = tools.get_kpis()
    imp = fx.impact()
    a, b, d, e = st.columns(4)
    with a:
        ui.kpi(c.L("Fraudes détectées", "Frauds caught"), f"×{k['modele_top_1pct']['fraudes_detectees'] / max(k['moteur_regles_actuel']['fraudes_detectees'], 1):.1f}",
               c.L(f"<b>{k['modele_top_1pct']['fraudes_detectees']}</b> vs {k['moteur_regles_actuel']['fraudes_detectees']} avec les règles actuelles",
                   f"<b>{k['modele_top_1pct']['fraudes_detectees']}</b> vs {k['moteur_regles_actuel']['fraudes_detectees']} with current rules"))
    with b:
        ui.kpi(c.L("Fausses alertes", "False alerts"),
               f"−{1 - k['modele_top_1pct']['fausses_alertes'] / k['moteur_regles_actuel']['fausses_alertes']:.0%}",
               c.L(f"<b>{_nb(k['modele_top_1pct']['fausses_alertes'])}</b> vs {_nb(k['moteur_regles_actuel']['fausses_alertes'])}",
                   f"<b>{_nb(k['modele_top_1pct']['fausses_alertes'])}</b> vs {_nb(k['moteur_regles_actuel']['fausses_alertes'])}"))
    with d:
        if imp:
            ui.kpi(c.L("Paiements légitimes épargnés", "Legitimate payments spared"),
                   f"{(imp['moteur']['fausses_tnd'] - imp['modele']['fausses_tnd']) / 1e6:.1f} M TND",
                   c.L("bloqués à tort en moins sur 2 mois", "fewer wrongly stopped over 2 months"))
    with e:
        ui.kpi(c.L("Temps cible", "Target time"), "< 30 s", c.L("de l’alerte à la décision", "from alert to decision"))

    ui.section(c.L("Votre visite guidée · 8 étapes", "Your guided tour · 8 steps"))
    left, right = st.columns([1.6, 1])
    with left:
        for i, s in enumerate(TOUR, 1):
            ui.step(i, c.L(s[1], s[2]), c.L(s[3], s[4]), s[0] in done)
    with right:
        n_done = sum(1 for s in TOUR if s[0] in done)
        st.progress(n_done / len(TOUR), text=c.L(f"{n_done}/{len(TOUR)} étapes faites", f"{n_done}/{len(TOUR)} steps done"))
        s = next_step(c)
        if s:
            if st.button(c.L("▶ Commencer / continuer la visite", "▶ Start / continue the tour"), type="primary", width="stretch"):
                st.session_state.tour = True
                _go_step(c, s)
                st.rerun()
        if st.button(c.L("Recommencer la visite", "Restart the tour"), width="stretch"):
            st.session_state.done = set()
            st.session_state.tour = True
            st.rerun()
        ui.section(c.L("Comment lire l'écran", "How to read the screen"))
        st.markdown(c.L(
            "- 🔴 **Risque élevé** · 🟠 **moyen** · 🟢 **faible**\n"
            "- **Percentile** : 99,9 % = plus risquée que 99,9 % des opérations du jour\n"
            "- **Recommandation système** : règle documentée, mesurée en validation — **vous décidez**\n"
            "- Chaque réponse de l'IA cite ses sources (outils) et ses tokens\n"
            "- Menu de gauche : **Analyste** (traiter), **Enquête IA** (comprendre), **Pilotage** (mesurer)",
            "- 🔴 **High risk** · 🟠 **medium** · 🟢 **low**\n"
            "- **Percentile**: 99.9% = riskier than 99.9% of the day's operations\n"
            "- **System recommendation**: documented rule, measured in validation — **you decide**\n"
            "- Every AI answer cites its sources (tools) and tokens\n"
            "- Left menu: **Analyst** (handle), **AI investigation** (understand), **Steering** (measure)"))
    c.mark("guide")


# ================================================================= 1. impact & process
@st.cache_data(show_spinner=False, ttl=3600)
def _reco_distribution(_queue):
    """Vectorised version of tools.recommend over the live queue (same rule)."""
    e = da.explanations()
    strong = e[(e.source == "model_for") & (e.points >= tools.STRONG_CONTRIBUTION)].groupby("transaction_id").size()
    rules = e[(e.source == "rules") & (e.points > 0)].groupby("transaction_id").size()
    q = _queue[(_queue.period == "test") & (_queue.risk_level != "FAIBLE")].copy()
    sig = q.transaction_id.map(strong).fillna(0) + q.transaction_id.map(rules).fillna(0)
    hi = q.risk_level == "ELEVE"
    q["decision"] = np.where(hi & (sig >= 2), "BLOQUER", "ESCALADER")
    q["conf"] = np.where(hi & (sig >= 2) & (q.score_pct >= tools.TOP_BAND), "élevée", "moyenne")
    return q.groupby(["decision", "conf"]).size().to_dict()


def page_impact(c):
    L = c.L
    ui.hero(L("Pilotage · comité des risques", "Steering · risk committee"), L("Impact & processus", "Impact & process"),
            L("Ce que Hyson Detector change pour la banque : fraude interceptée, clients épargnés, charge analystes, coût de l'IA, "
              "gouvernance du modèle. Validation hors échantillon juin → juillet 2026.",
              "What Hyson Detector changes for the bank: fraud intercepted, customers spared, analyst workload, AI cost, "
              "model governance. Out-of-time validation June → July 2026."), c.chips())
    imp = fx.impact()
    if imp is None:
        st.warning(L("Impact indisponible (Fabric hors ligne et pas d'instantané local).", "Impact unavailable (Fabric offline, no snapshot)."))
        return
    m, r = imp["modele"], imp["moteur"]
    a, b, d, e = st.columns(4)
    with a:
        ui.kpi(L("Fraude interceptée", "Fraud intercepted"), _money(m["fraudes_tnd"]),
               L(f"<b>{m['taux_tnd']:.0%}</b> du montant fraudé · moteur actuel {_money(r['fraudes_tnd'])} ({r['taux_tnd']:.0%})",
                 f"<b>{m['taux_tnd']:.0%}</b> of fraud value · current rules {_money(r['fraudes_tnd'])} ({r['taux_tnd']:.0%})"),
               f"×{m['fraudes_tnd'] / max(r['fraudes_tnd'], 1):.1f}")
    with b:
        ui.kpi(L("Paiements légitimes interrompus", "Legitimate payments interrupted"), _money(m["fausses_tnd"]),
               L(f"moteur actuel : <b>{_money(r['fausses_tnd'])}</b> de paiements de bons clients",
                 f"current rules: <b>{_money(r['fausses_tnd'])}</b> of good customers' payments"),
               f"−{1 - m['fausses_tnd'] / r['fausses_tnd']:.1%}")
    with d:
        ui.kpi(L("Clients dérangés à tort", "Customers wrongly disturbed"), _nb(m["fausses"]),
               L(f"vs <b>{_nb(r['fausses'])}</b> fausses alertes du moteur actuel", f"vs <b>{_nb(r['fausses'])}</b> current-rules false alerts"),
               f"−{1 - m['fausses'] / r['fausses']:.0%}")
    with e:
        ui.kpi(L("Fraudes détectées", "Frauds caught"), f"{_nb(m['fraudes'])} / {_nb(imp['fraudes'])}",
               L(f"moteur actuel : <b>{_nb(r['fraudes'])}</b> · avec 2× moins d'alertes ({_nb(m['alertes'])} vs {_nb(r['alertes'])})",
                 f"current rules: <b>{_nb(r['fraudes'])}</b> · with 2× fewer alerts ({_nb(m['alertes'])} vs {_nb(r['alertes'])})"),
               f"×{m['fraudes'] / max(r['fraudes'], 1):.1f}")

    ui.section(L("Charge de l'équipe fraude (hypothèses modifiables)", "Fraud team workload (editable assumptions)"))
    s1, s2, s3 = st.columns([1, 1, 2.2])
    minutes = s1.number_input(L("Minutes par alerte", "Minutes per alert"), 2, 60, 8)
    hours_month = s2.number_input(L("Heures productives / analyste / mois", "Productive hours / analyst / month"), 60, 180, 120)
    h_rules, h_model = r["alertes"] * minutes / 60, m["alertes"] * minutes / 60
    with s3:
        x1, x2, x3 = st.columns(3)
        x1.metric(L("Heures · règles actuelles", "Hours · current rules"), _nb(h_rules), help=L("sur 2 mois", "over 2 months"))
        x2.metric(L("Heures · Hyson", "Hours · Hyson"), _nb(h_model), f"-{_nb(h_rules - h_model)} h", delta_color="inverse",
                  help=L("sur 2 mois", "over 2 months"))
        x3.metric(L("Analystes libérés (ETP)", "Analysts freed (FTE)"), f"{(h_rules - h_model) / (2 * hours_month):.1f}")

    ui.section(L("Processus : de la transaction à la décision", "Process: from transaction to decision"))
    fun = fx.funnel_raw()
    total = int(fun.n.sum()) if fun is not None else None
    dist = _reco_distribution(c.queue)
    dec = tools.decisions()
    n_block = sum(v for (dcs, _), v in dist.items() if dcs == "BLOQUER")
    ui.flow([(_nb(total) if total else "—", L("transactions dans Fabric (2025 → 2026)", "transactions in Fabric (2025 → 2026)"), ui.NAVY),
             (_nb(imp["flux_du_jour"]["operations"]), L("opérations du flux du jour scorées", "live-flow operations scored"), "#123A6B"),
             (_nb(imp["flux_du_jour"]["alertes"]), L("alertes · top 1 %, capacité analystes", "alerts · top 1%, analyst capacity"), ui.BLUE),
             (_nb(n_block), L("recommandées BLOQUER", "BLOCK recommended"), ui.RED),
             (_nb(len(dec)), L("décisions de l'analyste → OneLake", "analyst decisions → OneLake"), ui.TEAL)])
    share = imp["flux_du_jour"]["alertes"] / max(imp["flux_du_jour"]["operations"], 1)
    st.caption(L(f"Seules {share:.1%} des opérations arrivent devant un analyste. Le modèle score, l'IA explique, l'analyste décide ; "
                 "chaque décision revient dans OneLake pour le prochain réentraînement.",
                 f"Only {share:.1%} of operations reach an analyst. The model scores, AI explains, the analyst decides; "
                 "every decision flows back to OneLake for the next retraining."))
    f1, f2 = st.columns([1, 1])
    with f2:
        st.markdown(f"**{L('Temps alerte → décision', 'Alert → decision time')}**")
        dur = pd.to_numeric(dec.get("duration_s", pd.Series(dtype=float)), errors="coerce").dropna() if len(dec) else pd.Series(dtype=float)
        if len(dur):
            st.metric(L("Temps médian", "Median time"), f"{dur.median():.0f} s",
                      L(f"{(dur <= 30).mean():.0%} en moins de 30 s", f"{(dur <= 30).mean():.0%} under 30 s"))
        else:
            st.info(L("Enregistrez une décision : le temps alerte → décision s'affichera ici.",
                      "Save a decision: the alert → decision time will show here."), icon=":material/timer:")
    with f1:
        st.markdown(f"**{L('Recommandations sur le flux du jour', 'Recommendations on the live flow')}**")
        rows = [(DEC_EN[k[0]] if c.lang == "en" else k[0], CONF_EN[k[1]] if c.lang == "en" else k[1], v) for k, v in sorted(dist.items())]
        st.dataframe(pd.DataFrame(rows, columns=[L("Recommandation", "Recommendation"), L("Confiance", "Confidence"), L("Alertes", "Alerts")]),
                     hide_index=True, width="stretch")
        bp = tools._band_precision()
        st.caption(L(f"Précision mesurée en validation : BLOQUER confiance élevée {bp['percentile_ge_0998']:.0%}, niveau élevé {bp['eleve']:.0%}, "
                     f"niveau moyen {bp['moyen']:.0%} → les cas « moyens » vont en revue (ESCALADER).",
                     f"Precision measured in validation: BLOCK high confidence {bp['percentile_ge_0998']:.0%}, high level {bp['eleve']:.0%}, "
                     f"medium level {bp['moyen']:.0%} → medium cases go to review (ESCALATE)."))

    ui.section(L("Coût de l'IA générative", "Generative AI cost"))
    u = copilot.usage_summary()
    rows = [x for x in u.get("rows", []) if not x.get("cached")]
    p1, p2, p3, p4 = st.columns(4)
    pin = p1.number_input(L("$ / 1M tokens entrée", "$ / 1M input tokens"), 0.0, 20.0, 0.25, 0.05)
    pcache = p2.number_input(L("$ / 1M tokens en cache", "$ / 1M cached tokens"), 0.0, 20.0, 0.025, 0.005, format="%.3f")
    pout = p3.number_input(L("$ / 1M tokens sortie", "$ / 1M output tokens"), 0.0, 60.0, 2.0, 0.1)
    fx_rate = p4.number_input("TND / USD", 1.0, 5.0, 3.1, 0.05)
    if rows:
        tp = np.mean([x["tokens"].get("prompt", 0) for x in rows])
        tc = np.mean([x["tokens"].get("cached_prompt", 0) for x in rows])
        to = np.mean([x["tokens"].get("completion", 0) for x in rows])
        usd = ((tp - tc) * pin + tc * pcache + to * pout) / 1e6
        q1, q2, q3, q4 = st.columns(4)
        q1.metric(L("Tokens par question", "Tokens per question"), _nb(tp + to), L(f"dont {tc:.0f} en cache", f"{tc:.0f} cached"))
        q2.metric(L("Coût par question", "Cost per question"), f"{usd * fx_rate * 1000:.2f} mTND", f"${usd:.4f}")
        q3.metric(L("Coût IA pour 1 879 alertes", "AI cost for 1,879 alerts"), f"{usd * fx_rate * 1879 * 3:.0f} TND",
                  L("3 questions par alerte", "3 questions per alert"))
        q4.metric(L("Réponses servies par le cache", "Answers served from cache"), f"{u['caches']}", L("coût nul", "zero cost"))
        st.caption(L("Tarifs indicatifs modifiables (déploiement gpt-5-mini). Comparez au coût d'un analyste par alerte évitée.",
                     "Indicative editable prices (gpt-5-mini deployment). Compare with an analyst's cost per avoided alert."))

    ui.section(L("Gouvernance du modèle (fiche réglementaire)", "Model governance (regulatory card)"))
    g1, g2 = st.columns([1.15, 1])
    with g1:
        st.markdown(L(
            "| | |\n|---|---|\n"
            "| **Modèle** | LightGBM (champion) vs HGB, LambdaRank, blend — choisi sur la validation |\n"
            "| **Données** | 1 908 228 transactions synthétiques · entraînement jan. 2025 → mai 2026 |\n"
            "| **Validation** | hors échantillon juin → juillet 2026 (jamais aléatoire) |\n"
            "| **Variables** | 73, calculées uniquement avec le **passé** de chaque transaction |\n"
            "| **Équité** | genre exclu ; identifiants jamais utilisés comme variables |\n"
            "| **Explicabilité** | contributions SHAP par transaction + règles métier lisibles |\n"
            "| **Décision** | humaine ; recommandation par règle documentée ; journal OneLake |\n"
            "| **Traçabilité IA** | question, outils, tokens, latence de chaque appel journalisés |",
            "| | |\n|---|---|\n"
            "| **Model** | LightGBM (champion) vs HGB, LambdaRank, blend — chosen on validation |\n"
            "| **Data** | 1,908,228 synthetic transactions · training Jan 2025 → May 2026 |\n"
            "| **Validation** | out-of-time June → July 2026 (never random) |\n"
            "| **Features** | 73, computed only from each transaction's **past** |\n"
            "| **Fairness** | gender excluded; IDs never used as features |\n"
            "| **Explainability** | per-transaction SHAP contributions + readable business rules |\n"
            "| **Decision** | human; recommendation by documented rule; OneLake journal |\n"
            "| **AI traceability** | question, tools, tokens, latency of every call logged |"))
    with g2:
        dr = fx.drift()
        if dr:
            color = ui.GREEN if dr["status"] == "stable" else (ui.AMBER if dr["status"] == "à surveiller" else ui.RED)
            st.markdown(f"**{L('Stabilité du score (PSI)', 'Score stability (PSI)')}** : "
                        f"<span style='color:{color};font-weight:800'>{dr['psi']:.3f} · "
                        f"{L(dr['status'], {'stable': 'stable', 'à surveiller': 'watch', 'dérive': 'drift'}[dr['status']])}</span>",
                        unsafe_allow_html=True)
            d = dr["dist"].set_index("bucket").rename(columns={"validation": L("Validation (référence)", "Validation (reference)"),
                                                               "flux_du_jour": L("Flux du jour", "Live flow")})
            st.bar_chart(d, stack=False, height=230, color=[ui.SOFT, ui.BLUE])
            st.caption(L("PSI < 0,10 : population stable entre la validation et le flux du jour — pas de réentraînement requis.",
                         "PSI < 0.10: population stable between validation and the live flow — no retraining required."))
    c.mark("impact")


# ================================================================= 2. Le Procès
def _type(ph, text, render, speed=0.012):
    words = text.split(" ")
    step = max(1, len(words) // 60)
    for i in range(0, len(words), step):
        render(ph, " ".join(words[:i + step]) + " ▌")
        time.sleep(speed)
    render(ph, text)


def page_proces(c):
    L = c.L
    ui.hero(L("Enquête IA", "AI investigation"), L("Le Procès de la transaction", "The Trial of the transaction"),
            L("Un procureur IA et un avocat de la défense IA plaident avec les mêmes faits tirés de Fabric ; un juge IA rend un verdict "
              "aligné sur la règle documentée. Vous gardez le dernier mot.",
              "An AI prosecutor and an AI defence lawyer plead with the same facts from Fabric; an AI judge gives a verdict aligned with "
              "the documented rule. You keep the last word."), c.chips())
    top = st.columns([2.2, 1, 1])
    with top[0]:
        tid = _tx_picker(c, "proces_tx")
    r = c.queue[c.queue.transaction_id == tid].iloc[0]
    st.session_state.setdefault("opened", {}).setdefault(tid, time.time())
    top[1].metric(L("Montant", "Amount"), _money(r.amount_tnd, 3))
    top[2].metric(L("Percentile", "Percentile"), f"{r.score_pct:.2%}")
    trials = st.session_state.setdefault("trials", {})
    start = st.button(L("⚖️  Ouvrir l'audience", "⚖️  Open the hearing"), type="primary")
    col_p, col_d = st.columns(2)
    ph = {"procureur": col_p.empty(), "defense": col_d.empty()}
    verdict_ph, judge_ph = st.empty(), st.empty()

    def plea(role, text):
        if role == "procureur":
            with ph[role].container():
                ui.plea(L("Accusation", "Prosecution"), L("Le procureur", "The prosecutor"), "🔺", ui.RED, text)
        elif role == "defense":
            with ph[role].container():
                ui.plea(L("Défense", "Defence"), L("L'avocat du client", "The customer's lawyer"), "🛡️", ui.GREEN, text)

    def render_judge(_, text):
        with judge_ph.container():
            ui.plea(L("Délibéré", "Deliberation"), L("Le juge", "The judge"), "⚖️", ui.NAVY, text)

    key = f"{tid}|{c.lang}"
    if start:
        for role in ("procureur", "defense"):
            plea(role, L("… prépare sa plaidoirie à partir des faits Fabric", "… preparing the plea from the Fabric facts"))
        with st.spinner(L("Audience en cours : les deux parties plaident en parallèle…", "Hearing in progress: both sides plead in parallel…")):
            def stage(role, text):
                if role in ("procureur", "defense"):
                    _type(ph[role], text, lambda p, t, role=role: plea(role, t))
                else:
                    _type(judge_ph, text, render_judge)
            out = courtroom.trial(tid, c.lang, on_stage=stage)
        trials[key] = out
        c.mark("proces")
    out = trials.get(key)
    if out:
        if not start:
            plea("procureur", out["procureur"])
            plea("defense", out["defense"])
            render_judge(None, out["juge"])
        reco = out.get("recommendation") or {}
        dec = reco.get("decision", "ESCALADER")
        label = (DEC_EN[dec] if c.lang == "en" else dec) + " · " + L(f"confiance {reco.get('confiance', '')}",
                                                                      f"{CONF_EN.get(reco.get('confiance'), '')} confidence")
        with verdict_ph.container():
            ui.verdict(L("Verdict : ", "Verdict: ") + label, dec,
                       L("Règle documentée du système, confirmée par le juge IA. ", "Documented system rule, confirmed by the AI judge. ") +
                       (L(f"Précision mesurée en validation à ce niveau : {reco['precision_mesuree_validation']:.0%}.",
                          f"Precision measured in validation at this level: {reco['precision_mesuree_validation']:.0%}.")
                        if reco.get("precision_mesuree_validation") is not None else ""))
        st.caption(f"{out.get('mode', '')} · tokens : {out['tokens'].get('total', 0)}"
                   f"{' · cache' if out.get('cached') else ''} · {out.get('latency_s', 0)} s · "
                   + L("3 rôles, mêmes faits (transaction, habitudes, événements digitaux, cas liés)",
                       "3 roles, same facts (transaction, habits, digital events, related cases)"))
        b1, b2, b3 = st.columns(3)
        if b1.button(L(f"✅ Retenir le verdict ({dec})", f"✅ Accept the verdict ({DEC_EN[dec]})"), width="stretch"):
            opened = st.session_state.get("opened", {}).get(tid)
            res = tools.record_decision(tid, dec, reco.get("confiance", "moyenne"), L("Verdict du Procès retenu", "Trial verdict accepted"),
                                        source="proces", duration_s=(time.time() - opened) if opened else None)
            st.success(L(f"Décision {res['decision']} enregistrée", f"Decision {res['decision']} saved"))
            c.mark("decide")
        b2.button(L("🔍 Revoir la scène", "🔍 Replay the scene"), on_click=c.open_tx, args=(tid, "replay"), width="stretch")
        b3.button(L("🧾 Fiche & dossier", "🧾 Case & file"), on_click=c.open_tx, args=(tid, "tx"), width="stretch")
    elif not start:
        st.info(L("Cliquez « Ouvrir l'audience ». Pour les 3 cas de démo, l'audience est pré-calculée (rejouée instantanément).",
                  "Click “Open the hearing”. For the 3 demo cases the hearing is pre-computed (replayed instantly)."),
                icon=":material/gavel:")


# ================================================================= 3. Reconstitution
def page_replay(c):
    L = c.L
    ui.hero(L("Enquête IA", "AI investigation"), L("Reconstitution", "Crime-scene replay"),
            L("Les heures qui précèdent l'alerte rejouées pas à pas : connexions, appareils, bénéficiaires, paiements. "
              "Les signaux de risque s'allument en rouge.",
              "The hours before the alert played back step by step: logins, devices, beneficiaries, payments. "
              "Risk signals light up in red."), c.chips())
    a, b = st.columns([2.2, 1])
    with a:
        tid = _tx_picker(c, "replay_tx")
    hours = b.select_slider(L("Fenêtre", "Window"), [6, 12, 24, 48, 72], value=24, format_func=lambda h: f"{h} h")
    data = fx.replay_steps(tid, hours, c.lang)
    if not data or not data["steps"]:
        st.info(L("Aucune activité dans la fenêtre.", "No activity in the window."))
        return
    steps = data["steps"]
    span = (data["end"] - steps[0]["ts"]).total_seconds() / 3600
    k = st.columns(4)
    k[0].metric(L("Étapes", "Steps"), len(steps))
    k[1].metric(L("Signaux de risque", "Risk signals"), data["n_signals"])
    k[2].metric(L("Durée de la séquence", "Sequence span"), f"{span:.1f} h")
    k[3].metric(L("Montant habituel", "Usual amount"), _money(data["usual_avg"], 0) if data["usual_avg"] else "—")
    play = st.button(L("▶  Lancer la reconstitution", "▶  Play the replay"), type="primary")
    left, right = st.columns([1.1, 1])
    with right:
        chart_ph = st.empty()
    with left:
        tl_ph = st.empty()

    def fmt(s):
        return {**s, "ts": s["ts"].strftime("%d/%m %H:%M")}

    def chart(upto):
        import plotly.graph_objects as go
        shown = steps[:upto]
        fig = go.Figure()
        for lane, kind, sym in [(L("Application", "App"), "event", "diamond"), (L("Paiements", "Payments"), "tx", "circle")]:
            pts = [s for s in shown if s["kind"] == kind]
            if not pts:
                continue
            fig.add_trace(go.Scatter(
                x=[s["ts"] for s in pts], y=[lane] * len(pts), mode="markers+text",
                marker=dict(size=[24 if s["target"] else 16 for s in pts], symbol=["star" if s["target"] else sym for s in pts],
                            color=[ui.RED if s["risky"] else ui.SOFT for s in pts], line=dict(width=1.5, color="#fff")),
                text=[s["icon"] for s in pts], textposition="top center",
                hovertext=[f"{s['ts']:%d/%m %H:%M} · {s['title']}<br>{', '.join(s['flags'])}" for s in pts], hoverinfo="text",
                showlegend=False))
        fig.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor=ui.CARD, font=dict(family="Inter", color=ui.TEXT),
                          xaxis=dict(range=[steps[0]["ts"] - pd.Timedelta(minutes=30), data["end"] + pd.Timedelta(minutes=30)],
                                     gridcolor=ui.LINE2), yaxis=dict(gridcolor=ui.LINE2))
        chart_ph.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"replay_chart_{upto}_{time.time()}")

    if play:
        for i in range(1, len(steps) + 1):
            with tl_ph.container():
                ui.timeline([fmt(s) for s in steps[:i]])
            chart(i)
            time.sleep(0.55 if steps[i - 1]["risky"] else 0.3)
        c.mark("replay")
    else:
        with tl_ph.container():
            ui.timeline([fmt(s) for s in steps])
        chart(len(steps))
    with right:
        ui.section(L("Récit du copilote", "Copilot narrative"))
        q = copilot.SUGGESTIONS[2][1 if c.lang == "en" else 0]
        if st.button(L("🎙️ Raconter la scène", "🎙️ Narrate the scene"), width="stretch") or st.session_state.get(f"narr_{tid}_{c.lang}"):
            out = copilot.ask(q, context_tx=tid, lang=c.lang)
            st.session_state[f"narr_{tid}_{c.lang}"] = True
            st.markdown(out["answer"])
            st.caption(f"{out['mode']} · tokens : {out['tokens']['total']}{' · cache' if out.get('cached') else ''}")
            c.mark("replay")
        geo = [s for s in steps if s.get("lat") is not None]
        if len(geo) >= 1:
            ui.section(L("Lieux", "Places"))
            st.map(pd.DataFrame([{"lat": s["lat"], "lon": s["lon"], "color": ui.RED if s["target"] else ui.BLUE,
                                  "size": 300 if s["target"] else 120} for s in geo]), latitude="lat", longitude="lon",
                   color="color", size="size", height=240)


# ================================================================= 4. Contre-enquête
def page_contre(c):
    L = c.L
    ui.hero(L("Enquête IA", "AI investigation"), L("Contre-enquête", "Counter-inquiry"),
            L("Et si … ? On neutralise un à un les facteurs que le modèle a pesés (contributions SHAP) pour voir ce qui ferait basculer "
              "la décision. Une décision robuste ne tient pas à un seul indice.",
              "What if…? We neutralise, one by one, the factors the model weighed (SHAP contributions) to see what would flip the decision. "
              "A robust decision does not rest on a single clue."), c.chips())
    tid = _tx_picker(c, "contre_tx")
    cf = fx.counterfactual(tid)
    if not cf:
        st.info(L("Transaction hors file d'alertes.", "Transaction outside the alert queue."))
        return
    th = cf["thresholds"]
    path = cf["path"]
    alert = cf["alert"]
    import plotly.graph_objects as go
    import textwrap

    def wrap(s):
        return "<br>".join(textwrap.wrap(s, 22)[:3])
    xs = [L("Score actuel", "Current score")] + [("− " + wrap(p["facteur"])) for p in path]
    ys = [cf["score"]] + [p["score_apres"] for p in path]
    fig = go.Figure(go.Scatter(x=list(range(len(xs))), y=ys, mode="lines+markers+text", text=[f"{y:.1%}" for y in ys],
                               textposition="top center", line=dict(color=ui.BLUE, width=3), cliponaxis=False,
                               marker=dict(size=15, color=[ui.RED if y >= th["alerte"] else ui.GREEN for y in ys],
                                           line=dict(width=2, color="#fff"))))
    fig.add_hline(y=th["alerte"], line_dash="dash", line_color=ui.AMBER, annotation_position="bottom right",
                  annotation_text=L(f"seuil d'alerte (top 1 %) · {th['alerte']:.1%}", f"alert threshold (top 1%) · {th['alerte']:.1%}"))
    if th.get("eleve"):
        fig.add_hline(y=th["eleve"], line_dash="dot", line_color=ui.RED, annotation_position="bottom left",
                      annotation_text=L(f"seuil risque élevé · {th['eleve']:.1%}", f"high-risk threshold · {th['eleve']:.1%}"))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=36, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=ui.CARD,
                      font=dict(family="Inter", color=ui.TEXT), yaxis=dict(range=[0, 1.12], tickformat=".0%", gridcolor=ui.LINE2),
                      xaxis=dict(tickmode="array", tickvals=list(range(len(xs))), ticktext=xs, tickangle=0, gridcolor=ui.LINE2,
                                 range=[-0.4, len(xs) - 0.6]))
    left, right = st.columns([1.5, 1])
    with left:
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with right:
        ui.section(L("Conclusion", "Conclusion"))
        if alert and cf["flip_at"] is None:
            ui.verdict(L("Décision robuste", "Robust decision"), "BLOQUER",
                       L(f"Même en neutralisant ses {len(path)} principaux facteurs de risque, l'opération reste au-dessus du seuil "
                         f"d'alerte ({path[-1]['score_apres']:.1%} > {th['alerte']:.1%}) : plusieurs indices indépendants convergent.",
                         f"Even after neutralising its {len(path)} main risk factors, the operation stays above the alert threshold "
                         f"({path[-1]['score_apres']:.1%} > {th['alerte']:.1%}): several independent clues converge."))
        elif alert:
            ui.verdict(L("Décision sensible", "Sensitive decision"), "ESCALADER",
                       L(f"Il suffit de neutraliser {cf['flip_at']} facteur(s) pour que l'opération sorte de la file : "
                         + ", ".join(p['facteur'] for p in path[:cf['flip_at']]) + ". Vérifiez ces points en priorité.",
                         f"Neutralising {cf['flip_at']} factor(s) is enough to drop the operation from the queue: "
                         + ", ".join(p['facteur'] for p in path[:cf['flip_at']]) + ". Check these points first."))
        elif cf["flip_at"] is None:
            if path:
                body = L(f"Même sans ses éléments rassurants, le score resterait à {path[-1]['score_apres']:.2%}, bien sous le seuil "
                         f"d'alerte ({th['alerte']:.1%}). Le moteur de règles actuel l'aurait pourtant bloquée.",
                         f"Even without its reassuring elements, the score would stay at {path[-1]['score_apres']:.2%}, far below the "
                         f"alert threshold ({th['alerte']:.1%}). The current rules would still have blocked it.")
            else:
                body = L("Aucun élément rassurant stocké pour cette opération.", "No reassuring element stored for this operation.")
            ui.verdict(L("Validation robuste", "Robust clearance"), "VALIDER", body)
        else:
            ui.verdict(L("Validation fragile", "Fragile clearance"), "ESCALADER",
                       L("Sans ses éléments rassurants, l'opération entrerait dans la file : à surveiller.",
                         "Without its reassuring elements, the operation would enter the queue: keep an eye on it."))
        for p in path:
            ui.factors([{"facteur": p["facteur"], "valeur_observee": p["observe"],
                         "valeur_habituelle": None}], alert, empty="")
            st.caption(L(f"contribution {p['contribution']:+.2f} (log-odds) → score sans ce facteur : {p['score_apres']:.2%}",
                         f"contribution {p['contribution']:+.2f} (log-odds) → score without this factor: {p['score_apres']:.2%}"))
    st.caption(L("Méthode : les contributions SHAP du modèle LightGBM sont additives en log-odds ; « neutraliser » un facteur = le ramener à "
                 "sa valeur moyenne. Seuls les 5 principaux facteurs par alerte sont stockés dans Fabric (gold_alert_explanations).",
                 "Method: the LightGBM model's SHAP contributions are additive in log-odds; “neutralising” a factor = bringing it back to its "
                 "average value. Only the top 5 factors per alert are stored in Fabric (gold_alert_explanations)."))
    if tid == c.demos.get("avoided_false_positive"):
        c.mark("fp")


# ================================================================= 5. Constellation
def page_galaxy(c):
    L = c.L
    ui.hero(L("Enquête IA · fraude organisée", "AI investigation · organised fraud"), "Constellation",
            L("Les points de compromission : DAB et commerçants par où les cartes fraudées sont passées dans les 30 jours avant la fraude, "
              "bien plus souvent que la moyenne. Les alertes du jour qui y sont passées gravitent autour.",
              "Points of compromise: ATMs and merchants that defrauded cards went through in the 30 days before the fraud, far more often "
              "than average. Today's alerts that went there orbit around them."), c.chips())
    period = st.segmented_control(L("Période", "Period"), ["test", "valid"], default="test", key="galaxy_period",
                                  format_func=lambda p: L("Flux du jour (août–sept.)", "Live flow (Aug–Sep)") if p == "test"
                                  else L("Validation (juin–juil.)", "Validation (Jun–Jul)")) or "test"
    with st.spinner(L("Calcul des points de compromission dans Fabric…", "Computing points of compromise in Fabric…")):
        g = fx.constellation(period)
    if not g:
        st.info(L("Aucun point de compromission (données indisponibles).", "No point of compromise (data unavailable)."))
        return
    graph, pos, rings, cp = g["graph"], g["pos"], g["rings"], g["points"]
    alerts = [n for n, d in graph.nodes(data=True) if d["kind"] == "alert"]
    k = st.columns(4)
    k[0].metric(L("Points de compromission", "Points of compromise"), len(cp), L(f"risque ×{cp.lift.min():.1f} à ×{cp.lift.max():.1f}",
                                                                              f"risk ×{cp.lift.min():.1f} to ×{cp.lift.max():.1f}"))
    k[1].metric(L("Alertes exposées", "Exposed alerts"), len(alerts))
    k[2].metric(L("Clients concernés", "Customers concerned"), len({graph.nodes[a]['customer'] for a in alerts}))
    k[3].metric(L("Réseaux (composantes)", "Networks (components)"), len(rings))

    import plotly.graph_objects as go
    rng = np.random.default_rng(3)
    fig = go.Figure()
    ex, ey = [], []
    for u, v in graph.edges():
        ex += [pos[u][0], pos[v][0], None]
        ey += [pos[u][1], pos[v][1], None]
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color="rgba(143,176,255,.18)", width=1), hoverinfo="skip",
                             showlegend=False))
    dx, dy = [], []
    pts = [n for n, d in graph.nodes(data=True) if d["kind"] == "point"]
    for p in pts:                                   # stardust: one faint dot per past victim of the point
        n = graph.nodes[p]["victims"]
        ang, rad = rng.uniform(0, 2 * np.pi, n), rng.uniform(.012, .045, n)
        dx += list(pos[p][0] + rad * np.cos(ang))
        dy += list(pos[p][1] + rad * np.sin(ang))
    fig.add_trace(go.Scatter(x=dx, y=dy, mode="markers", marker=dict(size=3, color="rgba(255,214,120,.45)"), hoverinfo="skip",
                             showlegend=False))
    color = {"ELEVE": "#FF5C5C", "MOYEN": "#FFB020", "FAIBLE": "#4ADE80"}
    fig.add_trace(go.Scatter(
        x=[pos[a][0] for a in alerts], y=[pos[a][1] for a in alerts], mode="markers", customdata=alerts,
        marker=dict(size=[5 + 7 * graph.nodes[a]["score"] ** 8 for a in alerts], color=[color[graph.nodes[a]["risk"]] for a in alerts],
                    line=dict(color="rgba(255,255,255,.55)", width=.6), opacity=.9),
        hovertext=[f"{a} · {graph.nodes[a]['risk']} · {graph.nodes[a]['amount']:.0f} TND · {graph.nodes[a]['channel']}" for a in alerts],
        hoverinfo="text", name=L("Alerte du jour", "Today's alert")))
    labelled = []
    for p in sorted(pts, key=lambda p: -graph.nodes[p]["lift"]):
        if len(labelled) < 9 and all(math.dist(pos[p], pos[q]) > 0.08 for q in labelled):
            labelled.append(p)
    fig.add_trace(go.Scatter(                         # stars drawn last, so they shine above their orbiting alerts
        x=[pos[p][0] for p in pts], y=[pos[p][1] for p in pts], mode="markers+text", customdata=pts,
        marker=dict(symbol="star", size=[16 + 3.2 * graph.nodes[p]["lift"] ** 1.6 for p in pts], color="#FFD36E",
                    line=dict(color="#FFF4CF", width=1.2)),
        text=[graph.nodes[p]["label"] if p in labelled else "" for p in pts], textposition="top center",
        textfont=dict(color="#E8EEFF", size=10.5),
        hovertext=[f"{graph.nodes[p]['label']} · {graph.nodes[p]['city'] or ''}<br>{graph.nodes[p]['victims']} "
                   + L("victimes", "victims") + f" / {graph.nodes[p]['visitors']} " + L("cartes", "cards")
                   + f" · ×{graph.nodes[p]['lift']:.1f}" for p in pts], hoverinfo="text", name=L("Point de compromission", "Point of compromise")))
    fig.update_layout(height=600, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#070B1E", plot_bgcolor="#070B1E",
                      xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"), dragmode="pan",
                      legend=dict(orientation="h", y=0.02, x=0.01, font=dict(color="#E8EEFF"), bgcolor="rgba(0,0,0,0)"),
                      hoverlabel=dict(bgcolor="#0A1128", font=dict(color="#fff", family="Inter")))
    rng_bg = np.random.default_rng(1)                 # faint background starfield
    xs_all = [v[0] for v in pos.values()]
    ys_all = [v[1] for v in pos.values()]
    fig.add_trace(go.Scatter(x=rng_bg.uniform(min(xs_all) - .1, max(xs_all) + .1, 260),
                             y=rng_bg.uniform(min(ys_all) - .1, max(ys_all) + .1, 260), mode="markers",
                             marker=dict(size=rng_bg.uniform(1, 2.6, 260), color="rgba(255,255,255,.35)"), hoverinfo="skip",
                             showlegend=False))
    fig.data = (fig.data[-1],) + fig.data[:-1]
    left, right = st.columns([1.75, 1])
    with left:
        ev = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key=f"galaxy_{period}",
                             config={"displayModeBar": False, "scrollZoom": True})
        st.caption(L("⭐ point de compromission (taille = risque ×) · poussière dorée = cartes déjà fraudées passées par ce point · "
                     "🔴🟠 alertes du jour. Cliquez une étoile ou une alerte.",
                     "⭐ point of compromise (size = risk ×) · golden dust = already-defrauded cards that went through this point · "
                     "🔴🟠 today's alerts. Click a star or an alert."))
    sel = None
    try:
        p = ev.selection.points if ev and ev.selection else []
        sel = p[0].get("customdata") if p else None
        if isinstance(sel, list):
            sel = sel[0]
    except Exception:
        sel = None
    with right:
        if sel and sel in graph.nodes:
            ring = next((r for r in rings if sel in r["points"] or sel in r["alerts"]), None)
            if graph.nodes[sel]["kind"] == "alert":
                st.button(L(f"🔎 Ouvrir l'alerte {sel}", f"🔎 Open alert {sel}"), on_click=c.open_tx, args=(sel, "tx"), type="primary",
                          width="stretch")
            if ring:
                ui.section(L("Réseau sélectionné", "Selected network"))
                for p_ in ring["points"]:
                    d = graph.nodes[p_]
                    st.markdown(f"⭐ **{d['label']}** · {d['city'] or ''} — {d['victims']} {L('victimes', 'victims')} / "
                                f"{d['visitors']} {L('cartes', 'cards')} (×{d['lift']:.1f})")
                st.markdown(L(f"**{len(ring['alerts'])} alertes**, {ring['customers']} clients, {_money(ring['amount'])} en jeu, "
                              f"{ring['high']} à risque élevé.",
                              f"**{len(ring['alerts'])} alerts**, {ring['customers']} customers, {_money(ring['amount'])} at stake, "
                              f"{ring['high']} high risk."))
                top = sorted(ring["alerts"], key=lambda a: -graph.nodes[a]["score"])[:6]
                for a in top:
                    st.button(f"{'🔴' if graph.nodes[a]['risk'] == 'ELEVE' else '🟠'} {a} · {graph.nodes[a]['amount']:.0f} TND",
                              key=f"gal_{a}", on_click=c.open_tx, args=(a, "tx"), width="stretch")
        else:
            ui.section(L("Réseaux les plus exposés", "Most exposed networks"))
            for i, r in enumerate(rings[:5], 1):
                names = ", ".join(graph.nodes[p]["label"] for p in r["points"][:2])
                st.markdown(f"**{i}. {names}**  \n" + L(f"{len(r['alerts'])} alertes · {r['customers']} clients · {r['high']} risque élevé",
                                                       f"{len(r['alerts'])} alerts · {r['customers']} customers · {r['high']} high risk"))
            st.info(L("Action proposée : surveillance renforcée (ou réémission préventive) des cartes passées par ces points.",
                      "Suggested action: reinforced monitoring (or preventive reissue) of cards that went through these points."),
                    icon=":material/shield:")
    with st.expander(L("🗺️ Carte de Tunisie des points de compromission", "🗺️ Tunisia map of the points of compromise"), expanded=False):
        geo = cp.dropna(subset=["latitude", "longitude"])
        if len(geo):
            st.map(geo.assign(size=geo.lift * 2500, color="#E0A100"), latitude="latitude", longitude="longitude", size="size",
                   color="color", height=380)
        st.dataframe(cp[["merchant_id", "merchant_name", "merchant_type", "city", "victims", "visitors", "lift"]]
                     .rename(columns={"merchant_name": L("Nom", "Name"), "merchant_type": "Type", "city": L("Ville", "City"),
                                      "victims": L("Victimes", "Victims"), "visitors": L("Cartes passées", "Cards seen"),
                                      "lift": L("Risque ×", "Risk ×")}).round({L("Risque ×", "Risk ×"): 2}),
                     hide_index=True, width="stretch")
    st.caption(L("Honnêteté : en validation, les alertes passées par un point de compromission ne sont pas plus souvent frauduleuses "
                 "(41 % vs 40 %). Ce signal n'est donc pas dans le score : il oriente l'enquête et la prévention. Seules les fraudes "
                 "signalées avant le début de la période sont utilisées.",
                 "Honesty note: in validation, alerts that went through a point of compromise are not more often fraudulent "
                 "(41% vs 40%). This signal is therefore not in the score: it guides investigation and prevention. Only frauds reported "
                 "before the period start are used."))
    c.mark("galaxy")


# ================================================================= regulatory case file (HTML, printable to PDF)
def case_file_html(c, tid):
    L = c.L
    t = tools.get_transaction(tid)
    tx, s, rs = t["transaction"], t.get("score", {}), t.get("recommandation_systeme", {})
    esc = html.escape

    def rows(fs):
        return "".join(f"<tr><td>{esc(str(f['facteur']))}</td><td>{esc(str(f.get('valeur_observee', '')))}</td>"
                       f"<td>{esc(str(f.get('valeur_habituelle', '')))}</td></tr>" for f in fs) or "<tr><td colspan=3>—</td></tr>"
    chat = st.session_state.get("chat", {}).get(tid, [])
    trial = st.session_state.get("trials", {}).get(f"{tid}|{c.lang}")
    dec = tools.decisions()
    dec = dec[dec.transaction_id == tid] if len(dec) else dec
    css = ("body{font-family:Inter,Arial,sans-serif;color:#0F1E36;max-width:900px;margin:30px auto;line-height:1.55}"
           "h1{color:#0B2545;margin:0}h2{color:#1E5BD8;border-bottom:2px solid #E3E8F0;padding-bottom:4px;margin-top:26px}"
           "table{border-collapse:collapse;width:100%}td,th{border:1px solid #E3E8F0;padding:6px 8px;text-align:left;font-size:13px}"
           "th{background:#F4F6FA}.box{background:#F4F6FA;border-radius:10px;padding:10px 14px;white-space:pre-wrap}"
           ".muted{color:#5B6B82;font-size:12px}")
    parts = [f"<html><head><meta charset='utf-8'><title>Dossier {esc(tid)}</title><style>{css}</style></head><body>",
             f"<h1>Hyson Detector — {L('Dossier d’investigation', 'Investigation file')} {esc(tid)}</h1>",
             f"<p class='muted'>{L('Généré le', 'Generated on')} {datetime.now():%Y-%m-%d %H:%M} · "
             f"{esc(da.source().describe())} · {L('données 100 % synthétiques', '100% synthetic data')}</p>",
             f"<h2>1. {L('Transaction', 'Transaction')}</h2><table>" +
             "".join(f"<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>" for k, v in tx.items()) + "</table>",
             f"<h2>2. {L('Score et recommandation', 'Score and recommendation')}</h2><table>"
             f"<tr><th>{L('Niveau de risque', 'Risk level')}</th><td>{esc(str(s.get('niveau_risque')))}</td></tr>"
             f"<tr><th>Score</th><td>{esc(str(s.get('score_modele')))} (percentile {esc(str(s.get('percentile_risque_periode')))})</td></tr>"
             f"<tr><th>{L('Moteur de règles actuel', 'Current rules engine')}</th><td>{L('alerte', 'alert') if s.get('alerte_moteur_regles_actuel') else '—'}</td></tr>"
             f"<tr><th>{L('Recommandation système', 'System recommendation')}</th><td><b>{esc(str(rs.get('decision')))}</b> "
             f"({esc(str(rs.get('confiance')))}) — {esc(', '.join(rs.get('signaux_concordants', [])))}</td></tr>"
             f"<tr><th>{L('Règle', 'Rule')}</th><td>{esc(str(rs.get('regle', '')))}</td></tr></table>",
             f"<h2>3. {L('Facteurs de risque', 'Risk factors')}</h2><table><tr><th>{L('Facteur', 'Factor')}</th><th>{L('Observé', 'Observed')}</th>"
             f"<th>{L('Habituel', 'Usual')}</th></tr>{rows(t['facteurs_modele_pour_fraude'] + t['regles_metier_declenchees'])}</table>",
             f"<h2>4. {L('Éléments rassurants', 'Reassuring elements')}</h2><table><tr><th>{L('Facteur', 'Factor')}</th>"
             f"<th>{L('Observé', 'Observed')}</th><th>{L('Habituel', 'Usual')}</th></tr>"
             f"{rows(t['facteurs_modele_rassurants'] + t['regles_rassurantes'])}</table>"]
    if trial:
        parts.append(f"<h2>5. {L('Le Procès', 'The Trial')}</h2><p><b>{L('Procureur', 'Prosecutor')}</b></p><div class='box'>"
                     f"{esc(trial['procureur'])}</div><p><b>{L('Défense', 'Defence')}</b></p><div class='box'>{esc(trial['defense'])}</div>"
                     f"<p><b>{L('Juge', 'Judge')}</b></p><div class='box'>{esc(trial['juge'])}</div>")
    if chat:
        parts.append(f"<h2>6. {L('Échanges avec le copilote', 'Copilot exchanges')}</h2>" +
                     "".join(f"<p><b>{'Analyste' if m['role'] == 'user' else 'Copilote'}</b></p><div class='box'>{esc(m['content'])}</div>"
                             for m in chat))
    parts.append(f"<h2>7. {L('Décisions', 'Decisions')}</h2>")
    if len(dec):
        parts.append(dec.to_html(index=False, border=0))
    else:
        parts.append(f"<p>{L('Aucune décision enregistrée.', 'No decision saved.')}</p>")
    parts.append(f"<p class='muted'>{L('Le modèle score (LightGBM, validation hors échantillon), l’IA explique à partir des données '
                                       '(Azure OpenAI, outils tracés), l’analyste décide. Journal des appels IA : copilot_log.jsonl ; '
                                       'décisions synchronisées dans OneLake (Files/app_feedback).',
                                       'The model scores (LightGBM, out-of-time validation), AI explains from the data (Azure OpenAI, '
                                       'traced tools), the analyst decides. AI call log: copilot_log.jsonl; decisions synced to OneLake '
                                       '(Files/app_feedback).')}</p></body></html>")
    return "".join(parts)


# ================================================================= Enquête approfondie (deep search)
DEEP_LEVEL = {"priorite": ("🔥 Priorité", "🔥 Priority"), "creuser": ("⚠ À creuser", "⚠ Dig deeper")}
KIND_COLOR = {"risk": ui.RED, "calm": ui.GREEN, "info": "#64748B"}
SOURCE_LABEL = {"score": ("score", "score"), "watch": ("alertes du client", "customer alerts"), "habits": ("habitudes", "habits"),
                "digital": ("banque digitale", "digital banking"), "network": ("réseau", "network"),
                "compromise": ("point de compromission", "point of compromise"), "counterfactual": ("contre-enquête", "counter-inquiry"),
                "analogs": ("cas similaires", "similar cases"), "decisions": ("vos décisions", "your decisions")}


def watch_buttons(c, n=6, key="wq"):
    """Flagged medium alerts as buttons: hover = why (0 token), click = deep search."""
    top = deepsearch.ranked("test").head(n)
    if top.empty:
        return
    cols = st.columns(min(n, len(top)))
    for col, (tid, r) in zip(cols, top.iterrows()):
        col.button(f"{c.L(*DEEP_LEVEL[r.level])} · {tid}", key=f"{key}_{tid}", width="stretch",
                   help=deepsearch.reason(tid, c.lang) + c.L(" — cliquez pour l'enquête approfondie.", " — click for the deep search."),
                   on_click=c.open_tx, args=(tid, "deep"))


def page_deep(c):
    L = c.L
    ui.hero(L("Enquête IA · alertes moyennes", "AI investigation · medium alerts"), L("Enquête approfondie", "Deep search"),
            L("Pour les alertes « suspectes mais pas confirmées » : Python fouille toutes les données Fabric sans aucun token, "
              "puis l'IA relie les preuves en un seul appel. L'analyste décide.",
              "For “suspicious but not confirmed” alerts: Python digs through all the Fabric data with zero tokens, "
              "then the AI connects the evidence in a single call. The analyst decides."), c.chips())
    stt, w = deepsearch.watch_stats(), deepsearch.watch("test")
    k = st.columns(4)
    with k[0]:
        ui.kpi(L("Alertes signalées aujourd'hui", "Alerts flagged today"), str(len(w)),
               L(f"<b>{int((w.level == 'priorite').sum())}</b> priorité · <b>{int((w.level == 'creuser').sum())}</b> à creuser",
                 f"<b>{int((w.level == 'priorite').sum())}</b> priority · <b>{int((w.level == 'creuser').sum())}</b> dig deeper"))
    with k[1]:
        ui.kpi(L("🔥 Priorité : fraudes mesurées", "🔥 Priority: measured fraud"), f"{stt['priorite'][1]:.0%}",
               L(f"sur {stt['priorite'][0]} alertes validées", f"on {stt['priorite'][0]} validated alerts"),
               f"×{stt['priorite'][1] / stt['other'][1]:.1f}")
    with k[2]:
        ui.kpi(L("⚠ À creuser : fraudes mesurées", "⚠ Dig deeper: measured fraud"), f"{stt['creuser'][1]:.0%}",
               L(f"sur {stt['creuser'][0]} alertes validées", f"on {stt['creuser'][0]} validated alerts"),
               f"×{stt['creuser'][1] / stt['other'][1]:.1f}")
    with k[3]:
        ui.kpi(L("Autres alertes moyennes", "Other medium alerts"), f"{stt['other'][1]:.0%}",
               L(f"sur {stt['other'][0]} · coût du signalement : <b>0 token</b>", f"on {stt['other'][0]} · flagging cost: <b>0 tokens</b>"))
    st.caption(L("Signal mesuré sur la validation juin–juillet 2026, sans information future : le client a déjà eu une alerte dans les "
                 "72 h précédentes (🔥 = dans les 24 h avec une rafale d'activité). Survolez un bouton pour voir pourquoi.",
                 "Signal measured on the Jun–Jul 2026 validation, with no future information: the customer already had an alert in the "
                 "previous 72 h (🔥 = within 24 h with a burst of activity). Hover a button to see why."))
    watch_buttons(c, key="wd")

    ids = c.queue.transaction_id.tolist()
    if st.session_state.get("deep_tx") not in ids:
        rk = deepsearch.ranked("test")
        st.session_state.deep_tx = rk.index[0] if len(rk) else st.session_state.get("tx", ids[0])
    top = st.columns([2.2, 1, 1, 1.2])
    with top[0]:
        tid = _tx_picker(c, "deep_tx")
    r = c.queue[c.queue.transaction_id == tid].iloc[0]
    top[1].metric(L("Montant", "Amount"), _money(r.amount_tnd, 3))
    top[2].metric(L("Percentile", "Percentile"), f"{r.score_pct:.2%}")
    lvl = w.loc[tid, "level"] if tid in w.index else None
    top[3].metric(L("Signal IA", "AI flag"), L(*DEEP_LEVEL[lvl]) if lvl else "—")
    if lvl:
        ui.hint("🔎 " + html.escape(deepsearch.reason(tid, c.lang)))

    results = st.session_state.setdefault("deep_res", {})
    key = f"{tid}|{c.lang}"
    run = st.button(L("🔎  Lancer l'enquête approfondie", "🔎  Run the deep search"), type="primary")
    left, right = st.columns([1.15, 1])
    with left:
        ui.section(L("Tableau des preuves · 0 token (Python sur Fabric)", "Evidence board · 0 tokens (Python on Fabric)"))
        board = st.empty()
    with right:
        ui.section(L("Conclusion de l'enquêteur IA · 1 appel", "AI investigator's conclusion · 1 call"))
        answer_ph, cost_ph = st.empty(), st.empty()

    def show_board(lines):
        rows = "".join(
            f'<div style="display:flex;gap:.6rem;align-items:flex-start;padding:.45rem .2rem;border-bottom:1px solid #EEF1F6">'
            f'<b style="min-width:2.1rem;color:{KIND_COLOR[x["kind"]]}">{x["id"]}</b>'
            f'<span style="flex:1">{html.escape(x["text"])}</span>'
            f'<span class="chip" style="white-space:nowrap">{html.escape(L(*SOURCE_LABEL.get(x["source"], (x["source"], x["source"]))))}</span>'
            f'</div>' for x in lines)
        legend = L("● rouge = risque · ● vert = rassurant · ● gris = contexte", "● red = risk · ● green = reassuring · ● grey = context")
        board.markdown(f'<div style="background:#FFFFFF;border:1px solid #E3E8F0;border-radius:14px;box-shadow:0 1px 3px rgba(15,30,54,.06);padding:.6rem .9rem">{rows}<div style="color:#64748B;font-size:.8rem;'
                       f'padding-top:.4rem">{legend}</div></div>', unsafe_allow_html=True)

    def show_answer(text):
        out = []
        for line in html.escape(text.replace("**", "")).splitlines():
            m = re.match(r"\s*([^:]{2,40}?)\s*:(.*)", line)
            out.append(f"<b>{m.group(1)}</b> :{m.group(2)}" if m else line)
        answer_ph.markdown(f'<div style="background:#FFFFFF;border:1px solid #E3E8F0;border-radius:14px;box-shadow:0 1px 3px '
                           f'rgba(15,30,54,.06);border-top:4px solid {ui.NAVY};padding:1rem 1.1rem;line-height:1.6">'
                           f'{"<br>".join(out)}</div>', unsafe_allow_html=True)

    if run:
        with st.spinner(L("Python fouille l'historique, la banque digitale, le réseau et les cas similaires…",
                          "Python is digging through history, digital banking, the network and similar cases…")):
            lines, _ = deepsearch.evidence(tid, c.lang)
        show_board(lines)
        buf = []
        res = deepsearch.investigate(tid, c.lang, on_token=lambda t: (buf.clear() if t is None else buf.append(t),
                                                                      show_answer("".join(buf))))
        results[key] = res
        c.mark("deep")
    res = results.get(key)
    if not res:
        board.info(L("Cliquez « Lancer l'enquête approfondie » : les preuves s'affichent ici en quelques secondes.",
                     "Click “Run the deep search”: the evidence appears here in a few seconds."), icon=":material/search:")
        return
    show_board(res["lines"])
    show_answer(res["answer"])
    t = res.get("tokens", {})
    usd = t.get("prompt", 0) * 0.25e-6 + t.get("completion", 0) * 2e-6
    cost_ph.caption(
        (L("Réponse en cache · 0 token · instantané", "Cached answer · 0 tokens · instant") if res.get("cached") else
         f"{res['mode']} · {t.get('total', 0)} tokens ({t.get('prompt', 0)} {L('entrée', 'in')} / {t.get('completion', 0)} "
         f"{L('sortie', 'out')}) · ≈ {usd * 3.1:.4f} TND · {res.get('latency_s', 0):.1f} s · "
         + L("une question copilote ≈ 3 300 tokens", "a copilot question ≈ 3,300 tokens")
         + (L(" · incohérence détectée → 1 relance automatique", " · inconsistency detected → 1 automatic retry") if t.get("retry") else ""))
        + f" · {res.get('n_evidence', len(res['lines']))} {L('preuves', 'pieces of evidence')}")
    with right:
        st.markdown(f"**{L('Votre décision', 'Your decision')}**")
        d = st.columns(3)
        for col, (dec, en) in zip(d, [("BLOQUER", "BLOCK"), ("ESCALADER", "ESCALATE"), ("VALIDER", "VALIDATE")]):
            if col.button(L(dec, en), key=f"deep_dec_{dec}", width="stretch"):
                opened = st.session_state.setdefault("opened", {}).get(tid)
                out = tools.record_decision(tid, dec, "moyenne", L("après enquête approfondie", "after deep search"),
                                            source="enquete_approfondie", duration_s=(time.time() - opened) if opened else None)
                if out.get("enregistre"):
                    st.success(L(f"Décision {dec} enregistrée (journal + OneLake).", f"Decision {en} saved (log + OneLake)."))
                else:
                    st.error(out)
        n = st.columns(2)
        n[0].button(L("⚖️ Le Procès", "⚖️ The Trial"), on_click=c.open_tx, args=(tid, "proces"), width="stretch", key="deep_proces")
        n[1].button(L("📄 Fiche transaction", "📄 Transaction card"), on_click=c.open_tx, args=(tid, "tx"), width="stretch",
                    key="deep_tx_btn")
