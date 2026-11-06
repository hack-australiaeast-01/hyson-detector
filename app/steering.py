"""Steering — strategic fraud intelligence with progressive drilldown (brief §4–§5).

Level 1 overview by a dimension → click a bar → Level 2 by a second dimension → click → Level 3 patterns of the selection →
Level 4 transactions + timeline + escalation on the same cards → Level 5 AI strategic insight.
All numbers come from fixed, read-only SQL on the star schema (DuckDB on the Fabric snapshot). The AI receives only numbered facts
K1…Kn computed here and must cite them; it classifies each pattern as cybersecurity / administrative-operational / technical-infrastructure
/ customer behaviour / coordinated fraud, separates facts from hypotheses, and never presents a hypothesis as an incident.
"""
import json
import re

import pandas as pd
import plotly.express as px
import streamlit as st

import askdata
import copilot
import memory
import ui

DIMS = {  # key: (FR, EN, SQL expression, join)
    "canal": ("Canal", "Channel", "c.canal", "c"), "type_operation": ("Type d'opération", "Operation type", "c.type_operation", "c"),
    "mode_saisie": ("Mode d'authentification / saisie", "Authentication / entry mode", "c.mode_saisie", "c"),
    "type_carte": ("Type de carte", "Card type", "k.type_carte", "k"), "categorie": ("Catégorie de commerçant", "Merchant category", "m.categorie", "m"),
    "region": ("Région", "Region", "g.region", "g"), "segment": ("Segment client", "Customer segment", "cl.segment", "cl"),
    "tranche_age": ("Tranche d'âge", "Age band", "cl.tranche_age", "cl"), "tranche_horaire": ("Moment de la journée", "Time of day", "h.tranche_horaire", "h"),
    "tranche_montant": ("Tranche de montant", "Amount band", "CASE WHEN f.montant_tnd < 50 THEN '1 · < 50 TND' WHEN f.montant_tnd < 200 THEN "
                        "'2 · 50–200 TND' WHEN f.montant_tnd < 1000 THEN '3 · 200–1 000 TND' ELSE '4 · ≥ 1 000 TND' END", None),
    "typologie": ("Typologie de fraude", "Fraud typology", "COALESCE(ty.fraud_scenario, '(non typée)')", "ty"),
}
JOIN = {"c": "JOIN dim_channel c ON c.channel_key = f.channel_key", "k": "LEFT JOIN dim_card k ON k.card_key = f.card_key",
        "m": "LEFT JOIN dim_merchant m ON m.merchant_key = f.merchant_key", "g": "JOIN dim_geo g ON g.geo_key = f.geo_key",
        "cl": "JOIN dim_client cl ON cl.client_key = f.client_key", "h": "JOIN dim_heure h ON h.heure = f.heure",
        "d": "JOIN dim_date d ON d.date_key = f.date_key", "ty": "LEFT JOIN typology ty ON ty.transaction_id = f.transaction_id"}
SCOPES = {"fraud": ("Fraudes signalées · janv. 2025 → juil. 2026", "Reported frauds · Jan 2025 → Jul 2026",
                    "f.fraude_signalee IS NOT NULL", "SUM(f.fraude_signalee)"),
          "valid": ("Validation juin–juil. 2026 (fraudes + modèle)", "Validation Jun–Jul 2026 (frauds + model)",
                    "f.fraude_signalee IS NOT NULL AND f.date_key >= 20260601", "SUM(f.fraude_signalee)"),
          "live": ("Flux août–sept. 2026 · alertes du modèle", "Live flow Aug–Sep 2026 · model alerts", "f.date_key >= 20260801",
                   "SUM(CASE WHEN f.alerte_modele THEN 1 ELSE 0 END)")}
CATS = {"cyber": ("Cybersécurité", "Cybersecurity"), "admin": ("Administratif / opérationnel", "Administrative / operational"),
        "tech": ("Technique / infrastructure", "Technical / infrastructure"), "customer": ("Comportement client / carte", "Customer / card behaviour"),
        "coordinated": ("Fraude organisée / coordonnée", "Organised / coordinated fraud")}


def _con():
    ty = (f"SELECT transaction_id, fraud_scenario FROM read_parquet('{memory.FILE.as_posix()}') WHERE is_fraud = 1" if memory.ready()
          else "SELECT NULL::VARCHAR transaction_id, NULL::VARCHAR fraud_scenario WHERE FALSE")
    return askdata._duck({"typology": ty})


def _q(sql):
    with askdata._lock:
        con = _con()
        try:
            return con.execute(sql).df()
        finally:
            con.close()


def _where(scope, filters):
    w = [SCOPES[scope][2]]
    for k, v in filters:
        w.append(f"{DIMS[k][2]} = '{str(v).replace(chr(39), chr(39) * 2)}'")
    return " AND ".join(w)


def _joins(keys):
    need = {DIMS[k][3] for k in keys if DIMS[k][3]}
    return " ".join(JOIN[j] for j in ["c", "k", "m", "g", "cl", "h", "d", "ty"] if j in need)


@st.cache_data(show_spinner=False, ttl=3600)
def breakdown(scope, filters, dim):
    keys = [k for k, _ in filters] + [dim]
    meas = SCOPES[scope][3]
    sql = (f"SELECT {DIMS[dim][2]} AS valeur, COUNT(*) AS operations, {meas} AS cas FROM fact_transactions f {_joins(keys)} "
           f"WHERE {_where(scope, filters)} GROUP BY 1 HAVING {meas} > 0 ORDER BY cas DESC LIMIT 25")
    d = _q(sql)
    d["valeur"] = d.valeur.fillna("(non renseigné)").astype(str)
    d["taux"] = d.cas / d.operations
    d["part"] = d.cas / max(d.cas.sum(), 1)
    return d


def _bar(df, L, title, key):
    d = df.sort_values("cas")
    fig = px.bar(d, x="cas", y="valeur", orientation="h", custom_data=["valeur"], height=max(260, 30 * len(d) + 70),
                 text=[f"{c:,.0f} · {p:.0%}".replace(",", " ") for c, p in zip(d.cas, d.part)])
    fig.update_traces(marker_color=ui.BLUE, textposition="outside", cliponaxis=False, hovertemplate="%{y}<br>%{x:,} cas<extra></extra>")
    fig.update_layout(margin=dict(l=8, r=60, t=34, b=8), title=dict(text=title, font=dict(size=14)), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", xaxis=dict(title=None, gridcolor="#EEF2F8"), yaxis=dict(title=None), clickmode="event+select")
    ev = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key=key, config={"displayModeBar": False})
    pts = (ev or {}).get("selection", {}).get("points", []) if isinstance(ev, dict) else getattr(getattr(ev, "selection", None), "points", [])
    if pts:
        p = pts[0]
        return (p.get("customdata") or [p.get("y")])[0]
    return None


# ---------------------------------------------------------------- level 3–4 evidence (0 token)
def evidence(scope, filters):
    keys = [k for k, _ in filters]
    j = _joins(keys)
    w = _where(scope, filters)
    flag = "f.fraude_signalee = 1" if scope != "live" else "f.alerte_modele"
    base = f"FROM fact_transactions f {j} WHERE {w}"
    tot = _q(f"SELECT COUNT(*) n, SUM(CASE WHEN {flag} THEN 1 ELSE 0 END) cas FROM fact_transactions f WHERE {SCOPES[scope][2]}").iloc[0]
    sel = _q(f"SELECT COUNT(*) n, SUM(CASE WHEN {flag} THEN 1 ELSE 0 END) cas, COUNT(DISTINCT CASE WHEN {flag} THEN f.card_key END) cartes, "
             f"COUNT(DISTINCT CASE WHEN {flag} THEN f.client_key END) clients, COUNT(DISTINCT CASE WHEN {flag} THEN f.merchant_key END) points, "
             f"SUM(CASE WHEN {flag} AND f.heure < 6 THEN 1 ELSE 0 END) nuit, SUM(CASE WHEN {flag} AND f.statut = 'REFUSEE' THEN 1 ELSE 0 END) refus, "
             f"SUM(CASE WHEN {flag} AND f.alerte_regles_actuelles THEN 1 ELSE 0 END) regles, "
             f"SUM(CASE WHEN {flag} AND f.alerte_modele THEN 1 ELSE 0 END) modele, "
             f"SUM(CASE WHEN {flag} AND f.score_modele IS NOT NULL THEN 1 ELSE 0 END) scorables {base}").iloc[0]
    ev = []

    def add(cat, text):
        ev.append({"id": f"K{len(ev) + 1}", "cat": cat, "text": text})
    rate, base_rate = sel.cas / max(sel.n, 1), tot.cas / max(tot.n, 1)
    add("scope", f"{int(sel.cas):,} cas sur {int(sel.n):,} opérations ({rate:.2%}), soit ×{rate / max(base_rate, 1e-9):.1f} le taux moyen "
                 f"({base_rate:.2%}) ; {int(sel.cartes)} cartes, {int(sel.clients)} clients, {int(sel.points)} commerçants / DAB distincts".replace(",", " "))
    if sel.cas:
        add("time", f"{sel.nuit / sel.cas:.0%} des cas la nuit (0 h–5 h)")
        add("admin", f"Le moteur de règles actuel en a signalé {sel.regles / sel.cas:.0%}" +
            (f" ; le modèle {sel.modele / max(sel.scorables, 1):.0%} sur la période où il est appliqué" if sel.scorables else ""))
        add("tech", f"{sel.refus / sel.cas:.0%} des cas ont été refusés par l'autorisation")
    top = _q(f"SELECT f.merchant_key, COUNT(*) n FROM fact_transactions f {j} WHERE {w} AND {flag} AND f.merchant_key IS NOT NULL "
             f"GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    if len(top) and sel.cas:
        add("coordinated", f"Les 5 commerçants / DAB les plus touchés concentrent {top.n.sum() / sel.cas:.0%} des cas (le 1er : {int(top.n.iloc[0])})")
    multi = _q(f"SELECT COUNT(*) n FROM (SELECT f.card_key FROM fact_transactions f {j} WHERE {w} AND {flag} AND f.card_key IS NOT NULL "
               f"GROUP BY 1 HAVING COUNT(*) >= 3)").n.iloc[0]
    if sel.cartes:
        add("customer", f"{int(multi)} carte(s) avec au moins 3 cas : enchaînements sur la même carte ({multi / sel.cartes:.0%} des cartes touchées)")
    if "c" in {DIMS[k][3] for k in keys} or True:
        mode = _q(f"SELECT c2.mode_saisie m, COUNT(*) n FROM fact_transactions f {j} JOIN dim_channel c2 ON c2.channel_key = f.channel_key "
                  f"WHERE {w} AND {flag} GROUP BY 1 ORDER BY 2 DESC")
        if len(mode):
            add("tech", "Modes de saisie des cas : " + ", ".join(f"{r.m} {r.n / mode.n.sum():.0%}" for r in mode.head(4).itertuples()))
            mag = mode[mode.m == "MAGSTRIPE"].n.sum()
            if mag:
                add("tech", f"{mag / mode.n.sum():.0%} des cas passent par la piste magnétique alors que les cartes ont une puce "
                            "(repli magnétique accepté par les terminaux)")
            ns = mode[mode.m == "ECOM_SANS_3DS"].n.sum()
            if ns:
                add("cyber", f"{ns / mode.n.sum():.0%} des cas en ligne sans 3-D Secure")
    log = _q(f"SELECT COUNT(DISTINCT f.client_key) n FROM fact_transactions f {j} JOIN fact_digital_events e ON e.client_key = f.client_key "
             f"AND e.date_key BETWEEN f.date_key - 1 AND f.date_key AND e.statut = 'ECHEC' WHERE {w} AND {flag}").n.iloc[0]
    reset = _q(f"SELECT COUNT(DISTINCT f.client_key) n FROM fact_transactions f {j} JOIN fact_digital_events e ON e.client_key = f.client_key "
               f"AND e.date_key BETWEEN f.date_key - 1 AND f.date_key AND e.type_evenement IN ('REINITIALISATION_MOT_DE_PASSE', "
               f"'MODIFICATION_NUMERO_TELEPHONE', 'AJOUT_APPAREIL', 'AJOUT_BENEFICIAIRE') WHERE {w} AND {flag}").n.iloc[0]
    if sel.clients:
        add("cyber", f"{log / sel.clients:.0%} des clients touchés ont eu une connexion échouée la veille ou le jour du cas ; "
                     f"{reset / sel.clients:.0%} un changement de sécurité (mot de passe, téléphone, appareil, bénéficiaire)")
    dec = _q(f"SELECT f.motif_refus r, COUNT(*) n FROM fact_transactions f {j} WHERE {w} AND f.statut = 'REFUSEE' GROUP BY 1 ORDER BY 2 DESC LIMIT 3")
    if len(dec):
        add("tech", "Motifs de refus dans cette sélection : " + ", ".join(f"{r.r} {int(r.n)}" for r in dec.itertuples()))
    trend = _q(f"SELECT d2.annee_mois m, SUM(CASE WHEN {flag} THEN 1 ELSE 0 END) cas, COUNT(*) n FROM fact_transactions f {j} "
               f"JOIN dim_date d2 ON d2.date_key = f.date_key WHERE {w} GROUP BY 1 ORDER BY 1")
    if len(trend) >= 4:
        last, prev = trend.tail(3), trend.iloc[:-3].tail(6)
        if prev.cas.sum():
            add("trend", f"Évolution : {last.cas.mean():.0f} cas / mois sur les 3 derniers mois contre {prev.cas.mean():.0f} les 6 précédents "
                         f"({(last.cas.mean() / prev.cas.mean() - 1):+.0%})")
    add("missing", "Non disponible dans les données : identité des employés, journaux techniques des terminaux et du switch, "
                   "réclamations clients — une cause administrative ou technique reste une hypothèse")
    return ev, trend


def transactions(scope, filters, limit=300):
    keys = [k for k, _ in filters]
    flag = "f.fraude_signalee = 1" if scope != "live" else "f.alerte_modele"
    sql = (f"SELECT f.transaction_id, d2.date, f.heure, f.montant_tnd, c2.canal, c2.mode_saisie, k2.type_carte, g2.ville, f.statut, f.motif_refus, "
           f"f.score_modele, f.niveau_risque, f.alerte_regles_actuelles, f.card_key FROM fact_transactions f {_joins(keys)} "
           f"JOIN dim_date d2 ON d2.date_key = f.date_key JOIN dim_channel c2 ON c2.channel_key = f.channel_key "
           f"LEFT JOIN dim_card k2 ON k2.card_key = f.card_key JOIN dim_geo g2 ON g2.geo_key = f.geo_key "
           f"WHERE {_where(scope, filters)} AND {flag} ORDER BY d2.date DESC, f.heure DESC LIMIT {limit}")
    return _q(sql)


# ---------------------------------------------------------------- level 5: AI strategic insight
INSIGHT = """Tu es analyste stratégique fraude d'une banque. Tu reçois des FAITS numérotés (K1…Kn) calculés sur une sélection de données.
Identifie 1 à 3 motifs. Pour chacun, rends : motif détecté, preuves (K-numéros cités), périmètre, explication possible classée dans UNE
catégorie parmi cyber (authentification, compromission de compte, appareils), admin (contrôles, procédures, règles), tech (traitement,
terminaux, configuration, repli magnétique), customer (comportement client / carte), coordinated (cas liés, mêmes points, enchaînements),
confiance (élevée / moyenne / faible selon la force des preuves), prochaine enquête, impact si rien n'est fait.
Règles : sépare faits et hypothèses ; une cause administrative ou technique sans donnée dédiée reste une HYPOTHÈSE (confiance faible) ;
ne présente jamais une hypothèse comme un incident avéré ; aucun chiffre qui ne soit pas dans les faits ; pas de nom de colonne. {lang}
Réponds UNIQUEMENT en JSON : {"insights": [{"motif": "…", "preuves": ["K1"], "perimetre": "…", "categorie": "cyber|admin|tech|customer|coordinated",
"explication": "…", "statut": "fait|hypothèse", "confiance": "élevée|moyenne|faible", "prochaine_enquete": "…", "impact": "…"}]}"""


def insight(ev, selection_label, lang="fr"):
    if not copilot.configured():
        return None
    import investigation
    txt = "\n".join(f"{e['id']} [{e['cat']}] {e['text']}" for e in ev)
    raw, tok, model = investigation._chat(INSIGHT.replace("{lang}", "Answer in English." if lang == "en" else "Réponds en français."),
                                          f"SÉLECTION : {selection_label}\n\nFAITS :\n{txt}", 3000)
    j = investigation._parse_json(raw) or {"insights": []}
    ids = {e["id"] for e in ev}
    for i in j.get("insights", []):
        i["preuves_valides"] = [p for p in i.get("preuves", []) if p in ids]
        if not i["preuves_valides"]:
            i["confiance"] = "faible"
            i["statut"] = "hypothèse"
    j["tokens"], j["model"] = tok, model
    return j


# ---------------------------------------------------------------- page
def page_steering(ctx):
    L, lang = ctx.L, ctx.lang
    ui.hero(L("Pilotage stratégique", "Strategic steering"), L("Intelligence fraude · exploration", "Fraud intelligence · drilldown"),
            L("Chaque graphique est une porte d'entrée : cliquez une barre pour descendre jusqu'aux transactions, puis demandez à l'IA ce que "
              "le motif peut signifier.", "Every chart is an entry point: click a bar to drill down to the transactions, then ask the AI what "
              "the pattern may mean."), ctx.chips())
    if not askdata.star_ready():
        st.warning(L("Schéma en étoile indisponible (notebook 05 + export_star.py).", "Star schema unavailable."))
        return
    path = st.session_state.setdefault("steer_path", [])
    c1, c2, c3 = st.columns([1.6, 1.2, 1.2])
    scope = c1.selectbox(L("Périmètre", "Scope"), list(SCOPES), format_func=lambda s: SCOPES[s][1 if lang == "en" else 0], key="steer_scope")
    if st.session_state.get("_steer_scope_prev") != scope:
        st.session_state._steer_scope_prev = scope
        path.clear()
    used = {k for k, _ in path}
    dims = [k for k in DIMS if k not in used and not (k == "typologie" and scope == "live")]
    d1 = c2.selectbox(L("Analyser par", "Analyse by"), dims, index=dims.index("canal") if "canal" in dims else 0,
                      format_func=lambda k: DIMS[k][1 if lang == "en" else 0], key=f"steer_dim_{len(path)}")
    with c3:
        st.write("")
        if path and st.button(L("↩ Remonter d'un niveau", "↩ Up one level"), width="stretch"):
            path.pop()
            st.rerun()
    crumbs = " › ".join([L("Tout", "All")] + [f"{DIMS[k][1 if lang == 'en' else 0]} = **{v}**" for k, v in path])
    st.markdown(f"🧭 {crumbs}")
    df = breakdown(scope, tuple(path), d1)
    if df.empty:
        st.info(L("Aucun cas dans cette sélection.", "No case in this selection."))
        return
    a, b = st.columns([3, 2])
    with a:
        picked = _bar(df, L, L(f"Niveau {len(path) + 1} · cas par {DIMS[d1][0].lower()}", f"Level {len(path) + 1} · cases by {DIMS[d1][1].lower()}"),
                      key=f"steer_chart_{len(path)}_{d1}_{'_'.join(str(v) for _, v in path)}")
        if picked and len(path) < 4:
            path.append((d1, picked))
            st.rerun()
    with b:
        t = df.copy()
        t["taux"] = (t.taux * 100).round(2).astype(str) + " %"
        t["part"] = (t.part * 100).round(1).astype(str) + " %"
        st.dataframe(t.rename(columns={"valeur": DIMS[d1][1 if lang == "en" else 0], "cas": L("cas", "cases"), "taux": L("taux", "rate"),
                                       "part": L("part des cas", "share")}), hide_index=True, width="stretch", height=min(420, 38 + 35 * len(t)))
        pick = st.selectbox(L("…ou choisir", "…or pick"), ["—"] + df.valeur.tolist(), key=f"steer_pick_{len(path)}")
        if pick != "—" and len(path) < 4:
            path.append((d1, pick))
            st.rerun()
    if not path:
        st.caption(L("Cliquez une barre (ou choisissez une valeur) pour descendre d'un niveau.", "Click a bar (or pick a value) to go one level down."))
        return
    ev, trend = evidence(scope, tuple(path))
    ui.section(L("Ce que montre la sélection (faits calculés)", "What the selection shows (computed facts)"))
    for e in ev:
        st.markdown(f"<div class='factor'><span class='dot' style='background:{ui.BLUE}'></span><div><b>{e['id']}</b> · {ui.esc(e['text'])}</div></div>",
                    unsafe_allow_html=True)
    if len(trend):
        fig = px.area(trend, x="m", y="cas", height=230)
        fig.update_traces(line_color=ui.BLUE, fillcolor="rgba(30,91,216,.10)")
        fig.update_layout(margin=dict(l=8, r=8, t=10, b=8), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          xaxis=dict(title=None), yaxis=dict(title=None, gridcolor="#EEF2F8"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    ui.section(L("Transactions de la sélection (les plus récentes) et enchaînements", "Transactions of the selection (most recent) and sequences"))
    tx = transactions(scope, tuple(path))
    if len(tx):
        seq = tx.groupby("card_key").size()
        tx["meme_carte"] = tx.card_key.map(seq)
        show = tx.drop(columns=["card_key"]).rename(columns={"meme_carte": L("cas sur la même carte", "cases on the same card")})
        st.dataframe(show, hide_index=True, width="stretch", height=300)
        opts = [t for t in tx.transaction_id if t in set(ctx.queue.transaction_id)]
        if opts:
            o1, o2 = st.columns([3, 1])
            sel = o1.selectbox(L("Ouvrir une alerte de la sélection", "Open an alert of the selection"), opts, key="steer_open")
            if o2.button(L("Ouvrir le dossier", "Open the case"), width="stretch"):
                ctx.open_tx(sel, "case")
                st.rerun()
    ui.section(L("Analyse stratégique par l'IA", "AI strategic analysis"))
    label = " · ".join(f"{DIMS[k][0]} = {v}" for k, v in path) + f" · {SCOPES[scope][0]}"
    if st.button(L("Que peut signifier ce motif ?", "What could this pattern mean?"), type="primary", icon=":material/psychology:"):
        with st.spinner(L("L'IA analyse les faits K1…Kn…", "The AI is analysing facts K1…Kn…")):
            st.session_state[f"steer_ai_{label}"] = insight(ev, label, lang)
    res = st.session_state.get(f"steer_ai_{label}")
    if res is None and not copilot.configured():
        st.info(L("IA non connectée : les faits ci-dessus restent valables.", "AI not connected: the facts above stand."))
    for i in (res or {}).get("insights", []):
        cat = CATS.get(i.get("categorie"), (i.get("categorie"), i.get("categorie")))[1 if lang == "en" else 0]
        col = {"élevée": ui.RED, "moyenne": ui.AMBER, "faible": ui.MUTED}.get(i.get("confiance"), ui.MUTED)
        badge = L("Hypothèse", "Hypothesis") if i.get("statut") != "fait" else L("Fait observé", "Observed fact")
        st.markdown(
            f"<div style='background:#fff;border:1px solid {ui.LINE};border-left:5px solid {col};border-radius:14px;padding:.8rem 1rem;margin:.5rem 0'>"
            f"<div style='display:flex;justify-content:space-between;gap:1rem'><b>{ui.esc(i.get('motif', ''))}</b>"
            f"<span style='font-size:.8rem;color:{col};white-space:nowrap'>{ui.esc(cat)} · {ui.esc(badge)} · {L('confiance', 'confidence')} {ui.esc(i.get('confiance', ''))}</span></div>"
            f"<div style='font-size:.9rem;margin-top:.35rem'><b>{L('Preuves', 'Evidence')}</b> : {ui.esc(', '.join(i.get('preuves_valides', [])) or '—')} · "
            f"<b>{L('Périmètre', 'Scope')}</b> : {ui.esc(i.get('perimetre', ''))}<br><b>{L('Explication possible', 'Possible explanation')}</b> : "
            f"{ui.esc(i.get('explication', ''))}<br><b>{L('À enquêter ensuite', 'Investigate next')}</b> : {ui.esc(i.get('prochaine_enquete', ''))}<br>"
            f"<b>{L('Impact si rien n’est fait', 'Impact if unresolved')}</b> : {ui.esc(i.get('impact', ''))}</div></div>", unsafe_allow_html=True)
    if res:
        st.caption(f"{res.get('model')} · {res.get('tokens')} tokens · " + L("faits calculés en SQL, l'IA interprète seulement",
                                                                             "facts computed in SQL, the AI only interprets"))
