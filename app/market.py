"""Market & benchmarks page: real public KPIs (cited) next to the same KPIs computed on our data.

Rules: every external number has its source and year; our data is synthetic and its fraud rate is deliberately
higher than reality (brief, FAQ), so comparisons are about *shape* (ratios, shares), and scale-ups are scenarios
with editable assumptions, never claims.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import features as fx
import ui

# ---------------------------------------------------------------- real public benchmarks (cited)
BENCH = [
    {"id": "fp", "value": "90–95 %",
     "fr": "des alertes des systèmes à règles sont des faux positifs", "en": "of rule-based monitoring alerts are false positives",
     "src": "PwC / McKinsey, cités par Fluxforce (2024)", "url": "https://www.fluxforce.ai/statistics/false-positive-rates-transaction-monitoring",
     "note_fr": "Estimation de l'industrie, pas une étude publiée", "note_en": "Industry estimate, not a peer-reviewed study"},
    {"id": "card_rate", "value": "0,031 %",
     "fr": "de la valeur des paiements par carte est frauduleuse (EEE, S1 2023)", "en": "of card payment value is fraudulent (EEA, H1 2023)",
     "src": "EBA / BCE, rapport 2024 sur la fraude aux paiements",
     "url": "https://eba.europa.eu/sites/default/files/2024-08/465e3044-4773-4e9d-8ca8-b1cd031295fc/EBA_ECB%202024%20Report%20on%20Payment%20Fraud.pdf",
     "note_fr": "0,015 % en nombre de paiements", "note_en": "0.015% by number of payments"},
    {"id": "xborder", "value": "28 % vs 4 %",
     "fr": "de la fraude carte (valeur) est transfrontalière hors EEE, contre 4 % des paiements",
     "en": "of card fraud value is cross-border outside the EEA, vs 4% of payments",
     "src": "EBA / BCE, rapport 2024", "url": "https://eba.europa.eu/sites/default/files/2024-08/465e3044-4773-4e9d-8ca8-b1cd031295fc/EBA_ECB%202024%20Report%20on%20Payment%20Fraud.pdf",
     "note_fr": "La fraude se concentre là où l'activité est rare", "note_en": "Fraud concentrates where activity is rare"},
    {"id": "eu_total", "value": "4,2 Md€",
     "fr": "de fraude aux paiements dans l'UE en 2024 (carte : 1,33 Md€, +29 %)", "en": "of payment fraud in the EU in 2024 (cards: €1.33 bn, +29%)",
     "src": "EBA / BCE, rapport décembre 2025", "url": "https://www.ecb.europa.eu/press/intro/publications/pdf/ecb.ebaecb202512.en.pdf",
     "note_fr": "", "note_en": ""},
    {"id": "uk_prev", "value": "67p → 70p",
     "fr": "sur chaque £1 de fraude non autorisée tentée sont bloqués par les banques (2024 → 2025)",
     "en": "of every £1 of attempted unauthorised fraud is stopped by banks (2024 → 2025)",
     "src": "UK Finance, Annual Fraud Report 2025 et 2026", "url": "https://www.ukfinance.org.uk/news-and-insight/press-release/fraud-report-2025-press-release",
     "note_fr": "2024 : 1,45 Md£ évités, 722 M£ perdus · 2025 : 1,68 Md£ évités",
     "note_en": "2024: £1.45 bn prevented, £722 m lost · 2025: £1.68 bn prevented"},
    {"id": "tn", "value": "163 M · 27,8 Md TND",
     "fr": "opérations par carte en Tunisie en 2024 (5,49 M cartes, 39 100 TPE, 3 305 DAB)",
     "en": "card operations in Tunisia in 2024 (5.49 m cards, 39,100 POS terminals, 3,305 ATMs)",
     "src": "Banque Centrale de Tunisie, via Managers.tn (2025)",
     "url": "https://managers.tn/2025/11/10/les-paiements-electroniques-depassent-27-milliards-de-dinars-en-2024-malgre-la-baisse-du-nombre-de-cartes-bancaires/",
     "note_fr": "E-paiement : 20,2 M opérations, 1 241 MTND · aucun taux de fraude public de la BCT",
     "note_en": "E-payment: 20.2 m operations, TND 1,241 m · no public BCT fraud rate"},
]
TN_CARD_VALUE_TND = 27.8e9          # BCT 2024
TN_CARD_OPS = 163e6                 # BCT 2024
EU_CARD_FRAUD_RATE = 0.00031        # EBA/ECB, H1 2023, share of value
CARD_CHANNELS = ("TPE", "EN_LIGNE")  # card payments (in store + online), as in the EBA card-payment perimeter


@st.cache_data(ttl=3600, show_spinner=False)
def market_raw(_mode):
    """Labelled history (train + validation) aggregated by channel × entry mode × cross-border. Live on Fabric, snapshot offline."""
    return fx._q("market", """
        SELECT channel, entry_mode, transaction_type,
               CASE WHEN country IS NULL OR country = 'TN' THEN 0 ELSE 1 END AS xborder,
               COUNT(*) AS n, SUM(CAST(amount_tnd AS FLOAT)) AS v,
               SUM(CASE WHEN is_fraud = 1 THEN 1 ELSE 0 END) AS nf,
               SUM(CASE WHEN is_fraud = 1 THEN CAST(amount_tnd AS FLOAT) ELSE 0 END) AS vf,
               SUM(CASE WHEN status = 'REFUSEE' THEN 1 ELSE 0 END) AS nd
        FROM dbo.silver_transactions
        WHERE is_fraud IS NOT NULL
        GROUP BY channel, entry_mode, transaction_type, CASE WHEN country IS NULL OR country = 'TN' THEN 0 ELSE 1 END""")


@st.cache_data(ttl=3600, show_spinner=False)
def legacy_raw(_mode):
    """Every alert of the current rules engine with the analyst's verdict and the amount (training period)."""
    return fx._q("legacy_rules", """
        SELECT l.rules_triggered, l.analyst_decision, CAST(s.amount_tnd AS FLOAT) AS amount
        FROM dbo.legacy_rule_alerts_train l JOIN dbo.silver_transactions s ON s.transaction_id = l.transaction_id""")


@st.cache_data(ttl=3600, show_spinner=False)
def detect_raw(_mode):
    """Days between a fraudulent transaction and the date the fraud was reported, by fraud type."""
    return fx._q("time_to_detect", """
        SELECT fraud_scenario, DATEDIFF(day, CAST(timestamp AS date), fraud_reported_date) AS d,
               COUNT(*) AS n, SUM(CAST(amount_tnd AS FLOAT)) AS v
        FROM dbo.silver_transactions
        WHERE is_fraud = 1 AND fraud_reported_date IS NOT NULL
        GROUP BY fraud_scenario, DATEDIFF(day, CAST(timestamp AS date), fraud_reported_date)""")


def rules_audit(df):
    """Per legacy rule: alerts, confirmed frauds, precision, frauds only this rule caught, value of false alerts."""
    d = df.copy()
    d["fraud"] = d.analyst_decision.eq("FRAUDE_CONFIRMEE")
    d["rules"] = d.rules_triggered.fillna("").str.split("|")
    d["n_rules"] = d.rules.str.len()
    e = d.explode("rules")
    e = e[e.rules != ""].reset_index(drop=True)
    e["false_amt"] = e.amount.where(~e.fraud, 0.0)
    g = e.groupby("rules").agg(alerts=("fraud", "size"), frauds=("fraud", "sum"), false_value=("false_amt", "sum"))
    solo = e[(e.n_rules == 1) & e.fraud].groupby("rules").size()
    g["solo_frauds"] = solo.reindex(g.index).fillna(0).astype(int)
    g["precision"] = g.frauds / g.alerts
    g["false_alerts"] = g.alerts - g.frauds
    return g.reset_index().rename(columns={"rules": "rule"}).sort_values("precision")


def wmedian(values, weights):
    s = pd.DataFrame({"v": values, "w": weights}).sort_values("v")
    cum = s.w.cumsum()
    return float(s.v[cum >= s.w.sum() / 2].iloc[0]) if len(s) else None


def _pct(x, d=1):
    return f"{x * 100:.{d}f} %".replace(".", ",") if x is not None else "—"


def _pct_en(x, d=1):
    return f"{x * 100:.{d}f}%" if x is not None else "—"


def _money(x):
    return f"{x:,.0f} TND".replace(",", " ")


def _bar(df, x, y, color, height=300, fmt="{:.2%}"):
    fig = go.Figure(go.Bar(x=df[x], y=df[y], marker_color=color, text=[fmt.format(v) for v in df[y]], textposition="outside"))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", yaxis=dict(tickformat=".1%", gridcolor="#E3E8F0"), showlegend=False)
    return fig


def page_market(c, mode):
    L = c.L
    P = (lambda x, d=1: _pct(x, d)) if c.lang != "en" else (lambda x, d=1: _pct_en(x, d))
    ui.hero(L("Pilotage · marché", "Steering · market"), L("Marché & benchmarks", "Market & benchmarks"),
            L("Nos résultats face aux chiffres publics réels (BCE, EBA, UK Finance, BCT), avec leurs sources · "
              "et ce que cela représenterait à l'échelle de la Tunisie",
              "Our results against real public figures (ECB, EBA, UK Finance, BCT), with their sources · "
              "and what it would mean at Tunisian scale"), c.chips())

    # ---- 1. real benchmarks
    ui.section(L("1 · Chiffres réels du marché (sources publiques)", "1 · Real market figures (public sources)"))
    cols = st.columns(3)
    for i, b in enumerate(BENCH):
        with cols[i % 3], st.container(border=True):
            st.markdown(f"### {b['value']}")
            st.markdown(b["fr"] if c.lang != "en" else b["en"])
            note = b["note_fr"] if c.lang != "en" else b["note_en"]
            if note:
                st.caption(note)
            st.caption(f"[{b['src']}]({b['url']})")

    raw = market_raw(mode)
    imp = fx.impact()
    if raw is None or raw.empty:
        st.info(L("Indicateurs sur nos données indisponibles (Fabric hors ligne et pas d'instantané local).",
                  "KPIs on our data unavailable (Fabric offline and no local snapshot)."))
        return
    for col in ["n", "v", "nf", "vf", "nd"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0)
    card = raw[raw.channel.isin(CARD_CHANNELS)]

    # ---- 2. like-for-like comparison
    ui.section(L("2 · Les mêmes indicateurs, calculés sur nos données", "2 · The same KPIs, computed on our data"))
    card_rate = card.vf.sum() / card.v.sum() if card.v.sum() else None
    xb_fraud = card[card.xborder == 1].vf.sum() / card.vf.sum() if card.vf.sum() else None
    xb_value = card[card.xborder == 1].v.sum() / card.v.sum() if card.v.sum() else None
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        ui.kpi(L("Alertes fausses · règles actuelles", "False alerts · current rules"),
               P(imp["moteur"]["fausses"] / imp["moteur"]["alertes"]) if imp else "—",
               L("Marché : <b>90–95 %</b> (estimation)", "Market: <b>90–95%</b> (estimate)"),
               L("cohérent avec le marché", "in line with the market"), True)
    with k2:
        ui.kpi(L("Alertes fausses · notre modèle", "False alerts · our model"),
               P(imp["modele"]["fausses"] / imp["modele"]["alertes"]) if imp else "—",
               L("même capacité analystes, top 1 %", "same analyst capacity, top 1%"),
               L("bien sous le marché", "well below the market"), True)
    with k3:
        ui.kpi(L("Fraude carte transfrontalière", "Cross-border card fraud"), P(xb_fraud),
               L(f"de la valeur fraudée vs <b>{P(xb_value)}</b> de la valeur payée · UE : 28 % vs 4 %",
                 f"of fraud value vs <b>{P(xb_value)}</b> of value paid · EU: 28% vs 4%"))
    with k4:
        ui.kpi(L("Valeur fraudée bloquée", "Fraud value stopped"),
               P(imp["modele"]["taux_tnd"]) if imp else "—",
               L(f"règles actuelles : <b>{P(imp['moteur']['taux_tnd'])}</b> · UK : 67–70 % (périmètre différent)",
                 f"current rules: <b>{P(imp['moteur']['taux_tnd'])}</b> · UK: 67–70% (different scope)") if imp else "")
    st.caption(L(f"Taux de fraude carte dans nos données : {P(card_rate, 2)} de la valeur, contre 0,031 % dans l'UE. "
                 "C'est voulu : le jeu de données du hackathon est synthétique et plus riche en fraudes que la réalité "
                 "(brief, FAQ). On compare donc des formes (parts, ratios), pas des montants absolus.",
                 f"Card fraud rate in our data: {P(card_rate, 2)} of value, vs 0.031% in the EU. This is by design: the hackathon "
                 "dataset is synthetic and richer in fraud than reality (brief, FAQ). We compare shapes (shares, ratios), not absolute amounts."))

    # ---- 3. Tunisia-scale scenario
    ui.section(L("3 · Scénario à l'échelle tunisienne (hypothèses modifiables)", "3 · Tunisian-scale scenario (editable assumptions)"))
    s1, s2, s3 = st.columns(3)
    rate = s1.number_input(L("Taux de fraude supposé (% de la valeur)", "Assumed fraud rate (% of value)"),
                           0.005, 0.5, EU_CARD_FRAUD_RATE * 100, 0.005, format="%.3f",
                           help=L("Par défaut : taux UE (EBA/BCE). Aucun taux tunisien public.", "Default: EU rate (EBA/ECB). No public Tunisian rate.")) / 100
    model_cov = s2.slider(L("Valeur fraudée bloquée · modèle", "Fraud value stopped · model"), 0.0, 1.0,
                          float(imp["modele"]["taux_tnd"]) if imp else 0.7, 0.01, format="%.2f")
    rules_cov = s3.slider(L("Valeur fraudée bloquée · règles", "Fraud value stopped · rules"), 0.0, 1.0,
                          float(imp["moteur"]["taux_tnd"]) if imp else 0.12, 0.01, format="%.2f")
    exposure = TN_CARD_VALUE_TND * rate
    gain = exposure * (model_cov - rules_cov)
    fa_per_op = None
    if imp and imp.get("operations"):
        fa_per_op = (imp["moteur"]["fausses"] - imp["modele"]["fausses"]) / imp["operations"]
    t1, t2, t3 = st.columns(3)
    with t1:
        ui.kpi(L("Exposition annuelle estimée", "Estimated annual exposure"), _money(exposure),
               L("27,8 Md TND de paiements carte (BCT 2024) × taux supposé", "TND 27.8 bn of card payments (BCT 2024) × assumed rate"))
    with t2:
        ui.kpi(L("Fraude supplémentaire bloquée / an", "Extra fraud stopped / year"), _money(gain),
               L("écart de couverture modèle − règles, en valeur", "model − rules coverage gap, in value"))
    with t3:
        ui.kpi(L("Fausses alertes évitées / an", "False alerts avoided / year"),
               f"{fa_per_op * TN_CARD_OPS:,.0f}".replace(",", " ") if fa_per_op else "—",
               L("notre réduction par opération × 163 M opérations (BCT 2024)", "our reduction per operation × 163 m operations (BCT 2024)"))
    st.caption(L("Scénario, pas une mesure : il applique nos taux de validation (données synthétiques) au volume réel tunisien. "
                 "Utile pour l'ordre de grandeur et pour discuter les hypothèses avec la banque.",
                 "A scenario, not a measurement: it applies our validation rates (synthetic data) to the real Tunisian volume. "
                 "Useful for the order of magnitude and to discuss assumptions with the bank."))

    # ---- 4. bank KPIs from our data
    ui.section(L("4 · Indicateurs de pilotage tirés de nos données", "4 · Steering KPIs from our data"))
    a, b = st.columns(2)
    by_ch = raw.groupby("channel", as_index=False)[["v", "vf", "n", "nf"]].sum()
    by_ch["rate"] = by_ch.vf / by_ch.v
    by_ch = by_ch.sort_values("rate", ascending=False)
    with a, st.container(border=True):
        st.markdown(f"**{L('Taux de fraude par canal (en valeur)', 'Fraud rate by channel (by value)')}**")
        st.plotly_chart(_bar(by_ch, "channel", "rate", ui.BLUE), width="stretch", config={"displayModeBar": False})
    by_em = raw[raw.entry_mode.notna()].groupby("entry_mode", as_index=False)[["v", "vf", "n", "nf"]].sum()
    by_em["rate"] = by_em.vf / by_em.v
    by_em = by_em.sort_values("rate", ascending=False)
    with b, st.container(border=True):
        st.markdown(f"**{L('Taux de fraude par mode de saisie (en valeur)', 'Fraud rate by entry mode (by value)')}**")
        st.plotly_chart(_bar(by_em, "entry_mode", "rate", ui.RED), width="stretch", config={"displayModeBar": False})
    ecom = by_em.set_index("entry_mode")
    if {"ECOM_3DS", "ECOM_SANS_3DS"} <= set(ecom.index) and ecom.loc["ECOM_3DS", "rate"] > 0:
        ratio = ecom.loc["ECOM_SANS_3DS", "rate"] / ecom.loc["ECOM_3DS", "rate"]
        ratio_fr = f"{ratio:.1f}".replace(".", ",")
        st.info(L(f"Paiement en ligne sans 3-D Secure : **{ratio_fr}×** plus de fraude (en valeur) qu'avec 3-D Secure. "
                  "Le rapport EBA/BCE fait le même constat avec l'authentification forte (SCA) : c'est un levier direct pour la banque.",
                  f"Online payments without 3-D Secure: **{ratio:.1f}×** more fraud (by value) than with 3-D Secure. "
                  "The EBA/ECB report finds the same with strong customer authentication (SCA): a direct lever for the bank."))
    tbl = by_ch.assign(share_value=by_ch.v / by_ch.v.sum(), share_fraud=by_ch.vf / by_ch.vf.sum(),
                       decline=raw.groupby("channel").nd.sum().reindex(by_ch.channel).values / by_ch.n)
    st.dataframe(tbl[["channel", "n", "share_value", "share_fraud", "rate", "decline"]], hide_index=True, width="stretch",
                 column_config={"channel": L("Canal", "Channel"), "n": st.column_config.NumberColumn(L("Opérations", "Operations"), format="%d"),
                                "share_value": st.column_config.NumberColumn(L("Part de la valeur", "Share of value"), format="percent"),
                                "share_fraud": st.column_config.NumberColumn(L("Part de la fraude", "Share of fraud"), format="percent"),
                                "rate": st.column_config.NumberColumn(L("Taux de fraude (valeur)", "Fraud rate (value)"), format="percent"),
                                "decline": st.column_config.NumberColumn(L("Taux de refus", "Decline rate"), format="percent")})
    st.caption(L("Historique labellisé (entraînement + validation), données synthétiques · requête live sur Fabric "
                 "(silver_transactions), instantané local hors ligne.",
                 "Labelled history (training + validation), synthetic data · live query on Fabric (silver_transactions), "
                 "local snapshot when offline."))

    # ---- 5. audit of the current rules engine
    ui.section(L("5 · Audit du moteur de règles actuel : quelles règles éteindre demain ?",
                 "5 · Audit of the current rules engine: which rules to switch off tomorrow?"))
    leg = legacy_raw(mode)
    if leg is None or leg.empty:
        st.info(L("Alertes du moteur actuel indisponibles.", "Current-engine alerts unavailable."))
    else:
        leg["amount"] = pd.to_numeric(leg.amount, errors="coerce").fillna(0)
        au = rules_audit(leg)
        total_alerts, total_fraud = len(leg), int(leg.analyst_decision.eq("FRAUDE_CONFIRMEE").sum())
        # candidates to switch off: precision under 1 % and (almost) no fraud that only they catch
        off = au[(au.precision < 0.01) & (au.solo_frauds <= max(2, int(0.01 * total_fraud)))]
        r1, r2, r3 = st.columns(3)
        with r1:
            ui.kpi(L("Alertes du moteur actuel", "Current-engine alerts"), f"{total_alerts:,}".replace(",", " "),
                   L(f"<b>{total_fraud:,}</b> fraudes confirmées par les analystes".replace(",", " "),
                     f"<b>{total_fraud:,}</b> frauds confirmed by analysts"))
        with r2:
            cut = int(off.false_alerts.sum())
            ui.kpi(L("Règles à éteindre", "Rules to switch off"), f"{len(off)} / {len(au)}",
                   L(f"≈ <b>{cut:,}</b> fausses alertes en moins".replace(",", " "), f"≈ <b>{cut:,}</b> fewer false alerts"),
                   L("gain immédiat", "immediate gain"), True)
        with r3:
            lost = int(off.solo_frauds.sum())
            ui.kpi(L("Fraudes perdues en les éteignant", "Frauds lost by switching them off"), f"{lost}",
                   L("fraudes détectées par ces règles seules, sur la période (à couvrir par le modèle ou une règle ciblée)",
                     "frauds caught by these rules alone over the period (to cover with the model or a targeted rule)"))
        fig = go.Figure(go.Bar(y=au.rule, x=au.precision, orientation="h",
                               marker_color=[ui.RED if r in set(off.rule) else ui.BLUE for r in au.rule],
                               text=[f"{p:.1%} · {a:,} alertes".replace(",", " ") if c.lang != "en" else f"{p:.1%} · {a:,} alerts"
                                     for p, a in zip(au.precision, au.alerts)], textposition="outside"))
        fig.update_layout(height=max(260, 34 * len(au)), margin=dict(l=10, r=40, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)", xaxis=dict(tickformat=".0%", gridcolor="#E3E8F0"), showlegend=False)
        with st.container(border=True):
            st.markdown(f"**{L('Précision de chaque règle (rouge = candidate à l’extinction)', 'Precision of each rule (red = candidate to switch off)')}**")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.dataframe(au[["rule", "alerts", "frauds", "precision", "solo_frauds", "false_alerts", "false_value"]].sort_values("precision"),
                     hide_index=True, width="stretch",
                     column_config={"rule": L("Règle", "Rule"), "alerts": L("Alertes", "Alerts"), "frauds": L("Fraudes", "Frauds"),
                                    "precision": st.column_config.NumberColumn(L("Précision", "Precision"), format="percent"),
                                    "solo_frauds": L("Fraudes vues par elle seule", "Frauds only it caught"),
                                    "false_alerts": L("Fausses alertes", "False alerts"),
                                    "false_value": st.column_config.NumberColumn(L("Paiements légitimes bloqués (TND)",
                                                                                   "Legitimate payments flagged (TND)"), format="%.0f")})
        st.caption(L("Verdict des analystes de la banque (legacy_rule_alerts_train, historique labellisé janv. 2025 – juil. 2026). Une règle est candidate si sa "
                     "précision est sous 1 % et qu'elle ne détecte presque aucune fraude seule. Décision finale : comité des risques.",
                     "Verdict of the bank's analysts (legacy_rule_alerts_train, labelled history Jan 2025 – Jul 2026). A rule is a candidate when its precision "
                     "is under 1% and it catches almost no fraud on its own. Final decision: risk committee."))

    # ---- 6. time to detect
    ui.section(L("6 · Délai de détection : combien de jours la fraude court-elle avant d'être signalée ?",
                 "6 · Time to detect: how many days does a fraud run before it is reported?"))
    det = detect_raw(mode)
    if det is None or det.empty:
        st.info(L("Dates de signalement indisponibles.", "Report dates unavailable."))
        return
    for col in ["d", "n", "v"]:
        det[col] = pd.to_numeric(det[col], errors="coerce").fillna(0)
    med = wmedian(det.d, det.n)
    within7 = det[det.d <= 7].n.sum() / det.n.sum()
    late_v = det[det.d > 7].v.sum()
    d1, d2, d3 = st.columns(3)
    with d1:
        ui.kpi(L("Délai médian de signalement", "Median time to report"), L(f"{med:.0f} jours", f"{med:.0f} days"),
               L("entre la transaction frauduleuse et son signalement", "between the fraudulent transaction and its report"))
    with d2:
        ui.kpi(L("Signalées en moins de 7 jours", "Reported within 7 days"), P(within7),
               L("le reste circule plus d'une semaine sans être vu", "the rest runs for over a week unseen"))
    with d3:
        ui.kpi(L("Montant fraudé signalé après 7 jours", "Fraud value reported after 7 days"), _money(late_v),
               L("notre modèle alerte <b>au moment de la transaction</b> (jour 0)", "our model alerts <b>at transaction time</b> (day 0)"),
               L("délai → 0", "delay → 0"), True)
    names = {"CARD_TESTING": ("Test de carte", "Card testing"), "ACCOUNT_TAKEOVER": ("Prise de contrôle", "Account takeover"),
             "CARTE_CLONEE_ETRANGER": ("Carte clonée étranger", "Card cloned abroad"), "SKIMMING_DAB": ("Skimming DAB", "ATM skimming"),
             "CARTE_VOLEE_SANS_CONTACT": ("Carte volée sans contact", "Stolen contactless"),
             "FRAUDE_EN_LIGNE_DISCRETE": ("Fraude en ligne discrète", "Discreet online fraud")}
    per = (det.groupby("fraud_scenario").apply(lambda g: wmedian(g.d, g.n), include_groups=False)
           .rename("median_days").reset_index().sort_values("median_days"))
    per["label"] = per.fraud_scenario.map(lambda s: names.get(s, (s, s))[1 if c.lang == "en" else 0])
    fig = go.Figure(go.Bar(y=per.label, x=per.median_days, orientation="h", marker_color=ui.AMBER if hasattr(ui, "AMBER") else "#F59E0B",
                           text=[L(f"{x:.0f} j", f"{x:.0f} d") for x in per.median_days], textposition="outside"))
    fig.update_layout(height=280, margin=dict(l=10, r=40, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(gridcolor="#E3E8F0", title=L("jours (médiane)", "days (median)")), showlegend=False)
    with st.container(border=True):
        st.markdown(f"**{L('Délai médian de signalement par typologie', 'Median time to report by fraud type')}**")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(L("fraud_reported_date sert ici d'indicateur de pilotage, jamais de variable du modèle (brief §8.6). "
                 "Chaque jour gagné entre la transaction et l'alerte réduit les pertes et le nombre d'opérations frauduleuses en chaîne.",
                 "fraud_reported_date is used here as a steering KPI, never as a model feature (brief §8.6). "
                 "Every day saved between the transaction and the alert cuts losses and chained fraudulent operations."))
