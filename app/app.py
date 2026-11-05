"""Fraud-analyst copilot — Streamlit interface (brief §10).

Run:  streamlit run app.py
"""
import json

import pandas as pd
import streamlit as st

import copilot
import data_access as da
import tools

st.set_page_config(page_title="Copilote Fraude", page_icon="🛡️", layout="wide")

PAGES = ["🚨 File d'alertes", "🔍 Fiche transaction + copilote", "👤 Vue client 360", "📊 Performance", "📒 Journal"]
DEMO_LABEL = {"obvious_fraud": "Fraude évidente", "subtle_fraud": "Fraude subtile", "avoided_false_positive": "Faux positif évité"}
SUGGESTIONS = ["Pourquoi cette transaction est-elle suspecte ?",
               "Cette transaction ressemble-t-elle au comportement habituel du client ?",
               "Que s'est-il passé juste avant cette opération ?",
               "D'autres clients sont-ils passés par le même commerçant ou appareil ?",
               "Pourquoi cette alerte pourrait-elle ne pas être une fraude ?",
               "Rédige le résumé d'investigation pour le dossier."]


@st.cache_data
def load():
    return da.queue(), da.explanations()


def open_tx(tid, page=PAGES[1]):
    st.session_state.tx = tid
    st.session_state.tx_select = tid
    st.session_state.goto = page


def money(x):
    return f"{x:,.3f} TND".replace(",", " ")


queue, expl = load()
demos = queue[queue.demo_case.notna()]
st.session_state.setdefault("tx", demos.transaction_id.iloc[0] if len(demos) else queue.transaction_id.iloc[0])
st.session_state.setdefault("chat", {})
if "goto" in st.session_state:
    st.session_state.page = st.session_state.pop("goto")

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🛡️ Copilote Fraude")
    page = st.radio("Navigation", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    st.caption("Cas de démo")
    for _, d in demos.iterrows():
        st.button(f"{d.risk_icon} {DEMO_LABEL.get(d.demo_case, d.demo_case)} · {d.transaction_id}",
                  key=f"demo_{d.transaction_id}", on_click=open_tx, args=(d.transaction_id,), width="stretch")
    st.divider()
    mode = f"Azure OpenAI · {copilot.os.getenv('AZURE_OPENAI_DEPLOYMENT')}" if copilot.configured() else "hors-ligne (règles)"
    st.caption(f"Copilote : **{mode}**")
    u = copilot.usage_summary()
    st.caption(f"Appels LLM : {u['appels']} · tokens : {u['tokens']:,} · cache : {u['caches']}".replace(",", " "))
    missing = [k for k, ok in da.data_status().items() if not ok]
    if missing:
        st.caption("⚠️ Non exporté : " + ", ".join(missing))


# ---------------------------------------------------------------- 1. alert queue
def page_queue():
    st.header("🚨 File d'alertes")
    c1, c2, c3, c4 = st.columns([1.3, 1.4, 1.4, 1.4])
    period = c1.radio("Période", ["test", "valid"], horizontal=True,
                      format_func=lambda p: "Flux du jour (août–sept.)" if p == "test" else "Validation (juin–juil.)")
    q = queue[queue.period == period]
    dmin, dmax = q.date.min(), q.date.max()
    dates = c2.date_input("Dates", (dmin, dmax), min_value=dmin, max_value=dmax)
    channels = c3.multiselect("Canal", sorted(q.channel.dropna().unique()))
    risks = c4.multiselect("Niveau de risque", ["ELEVE", "MOYEN", "FAIBLE"], default=["ELEVE", "MOYEN"])
    if isinstance(dates, tuple) and len(dates) == 2:
        q = q[(q.date >= dates[0]) & (q.date <= dates[1])]
    if channels:
        q = q[q.channel.isin(channels)]
    if risks:
        q = q[q.risk_level.isin(risks)]
    if period == "valid":
        types = st.multiselect("Typologie (validation uniquement)", sorted(queue.fraud_scenario.dropna().unique()))
        if types:
            q = q[q.fraud_scenario.isin(types)]

    days = max(q.date.nunique(), 1)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Alertes", f"{len(q):,}".replace(",", " "))
    m2.metric("🔴 Risque élevé", int((q.risk_level == "ELEVE").sum()))
    m3.metric("Alertes / jour", f"{len(q) / days:.1f}")
    m4.metric("Aussi levées par le moteur actuel", int(q.legacy_alert.sum()))

    with st.expander("Alertes par jour", expanded=False):
        per_day = q.groupby(["date", "risk_level"]).size().unstack(fill_value=0)
        order = [x for x in ["ELEVE", "MOYEN", "FAIBLE"] if x in per_day.columns]
        palette = {"ELEVE": "#d62728", "MOYEN": "#ff7f0e", "FAIBLE": "#2ca02c"}
        st.bar_chart(per_day[order], color=[palette[x] for x in order])

    view = q.sort_values("score_model", ascending=False)[
        ["risk_icon", "transaction_id", "timestamp", "customer_id", "transaction_type", "channel", "merchant_category",
         "amount_tnd", "city", "country", "score_pct", "risk_level", "legacy_alert", "top_model_factors"]]
    st.caption("Cliquez une ligne pour ouvrir la fiche transaction.")
    ev = st.dataframe(view, hide_index=True, width="stretch", height=480, on_select="rerun",
                      selection_mode="single-row", key=f"q_{period}",
                      column_config={"risk_icon": st.column_config.TextColumn("", width="small"),
                                     "timestamp": st.column_config.DatetimeColumn("Date", format="DD/MM HH:mm"),
                                     "amount_tnd": st.column_config.NumberColumn("Montant (TND)", format="%.3f"),
                                     "score_pct": st.column_config.ProgressColumn("Percentile risque", min_value=0, max_value=1, format="%.4f"),
                                     "legacy_alert": st.column_config.CheckboxColumn("Moteur actuel"),
                                     "top_model_factors": st.column_config.TextColumn("Facteurs principaux", width="large")})
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        tid = view.iloc[rows[0]].transaction_id
        st.button(f"Ouvrir {tid} →", on_click=open_tx, args=(tid,), type="primary")


# ---------------------------------------------------------------- 2. transaction card + copilot
def factor_table(rows, positive):
    if not rows:
        st.caption("—")
        return
    for f in rows:
        obs = f.get("valeur_observee")
        usual = f.get("valeur_habituelle")
        val = "" if obs is None else f" : **{obs}**"
        cmp_ = "" if usual is None else f" (habituel {usual})"
        st.markdown(f"{'🔺' if positive else '🟢'} {f['facteur']}{val}{cmp_}")


def page_transaction():
    ids = queue.transaction_id.tolist()
    risk_of = dict(zip(queue.transaction_id, queue.risk_icon))
    tid = st.session_state.tx if st.session_state.tx in ids else ids[0]
    if st.session_state.get("tx_select") not in ids:
        st.session_state.tx_select = tid
    tid = st.selectbox("Transaction", ids, key="tx_select", format_func=lambda t: f"{risk_of[t]} {t}")
    st.session_state.tx = tid
    t = tools.get_transaction(tid)
    r = queue[queue.transaction_id == tid].iloc[0]
    tx, s = t["transaction"], t["score"]

    left, right = st.columns([1.15, 1])
    with left:
        demo = f" · 🎬 {DEMO_LABEL[r.demo_case]}" if pd.notna(r.demo_case) else ""
        st.subheader(f"{r.risk_icon} {tid}{demo}")
        st.caption(f"{tx['timestamp']} · {tx.get('transaction_type')} · {tx.get('channel')} · {tx.get('entry_mode')} · "
                   f"{tx.get('merchant_category') or '—'} · {tx.get('city') or '—'} ({tx.get('country')}) · {tx.get('status')} · "
                   f"client {tx['customer_id']}")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Montant", money(tx["amount_tnd"]))
        k2.metric("Risque", s["niveau_risque"])
        k3.metric("Percentile", f"{s['percentile_risque_periode']:.2%}")
        k4.metric("Moteur actuel", "Alerte" if s["alerte_moteur_regles_actuel"] else "Pas d'alerte")
        a, b = st.columns(2)
        with a:
            st.markdown("**Facteurs de risque**")
            factor_table(t["facteurs_modele_pour_fraude"] + t["regles_metier_declenchees"][:2], True)
        with b:
            st.markdown("**Éléments rassurants**")
            factor_table(t["facteurs_modele_rassurants"] + t["regles_rassurantes"], False)
        if r.period == "valid" and pd.notna(r.is_fraud):
            with st.expander("Vérité terrain (validation uniquement — jamais visible sur le flux du jour)"):
                st.write("Fraude" if r.is_fraud == 1 else "Légitime", r.fraud_scenario if pd.notna(r.fraud_scenario) else "")

        with st.form(f"decision_{tid}", clear_on_submit=True):
            st.markdown("**Décision de l'analyste**")
            d1, d2 = st.columns(2)
            decision = d1.radio("Décision", ["BLOQUER", "ESCALADER", "VALIDER"], horizontal=True)
            conf = d2.select_slider("Confiance", ["faible", "moyenne", "élevée"], value="moyenne")
            comment = st.text_input("Commentaire")
            if st.form_submit_button("Enregistrer la décision", type="primary"):
                res = tools.record_decision(tid, decision, conf, comment, source="interface")
                st.success(f"Décision {res['decision']} enregistrée") if res.get("enregistre") else st.error(res)
        past = tools.decisions()
        past = past[past.transaction_id == tid]
        if len(past):
            st.caption("Décisions précédentes : " + " · ".join(f"{x.decision} ({x.confidence}, {x.decided_at})" for x in past.itertuples()))

    with right:
        st.subheader("💬 Copilote")
        history = st.session_state.chat.setdefault(tid, [])
        cols = st.columns(2)
        clicked = None
        for i, sug in enumerate(SUGGESTIONS):
            if cols[i % 2].button(sug, key=f"sug_{tid}_{i}", width="stretch"):
                clicked = sug
        box = st.container(height=430)
        for m in history:
            with box.chat_message(m["role"]):
                st.markdown(m["content"])
                if m.get("meta"):
                    st.caption(m["meta"])
        question = st.chat_input("Posez votre question sur cette alerte…") or clicked
        if question:
            with box.chat_message("user"):
                st.markdown(question)
            with box.chat_message("assistant"), st.spinner("Analyse des données…"):
                out = copilot.ask(question, context_tx=tid, history=history)
                meta = (f"{out['mode']} · outils : {', '.join(x['name'] for x in out['tools']) or '—'} · "
                        f"tokens : {out['tokens']['total']}{' · cache' if out.get('cached') else ''} · {out.get('latency_s', 0)} s")
                st.markdown(out["answer"])
                st.caption(meta)
            history += [{"role": "user", "content": question}, {"role": "assistant", "content": out["answer"], "meta": meta}]
        st.button("👤 Vue client 360", on_click=open_tx, args=(tid, PAGES[2]))


# ---------------------------------------------------------------- 3. customer 360
def page_customer():
    r = queue[queue.transaction_id == st.session_state.tx].iloc[0]
    cust = st.text_input("Client", r.customer_id)
    prof = tools.get_customer_profile(cust)
    if "erreur" in prof:
        st.error(prof["erreur"])
        return
    p, hab = prof.get("profil", {}), prof.get("habitudes", {})
    st.header(f"👤 {cust}")
    c = st.columns(6)
    c[0].metric("Âge", p.get("age", "—"))
    c[1].metric("Segment", p.get("segment", "—"))
    c[2].metric("Ville", p.get("home_city", "—"))
    c[3].metric("Revenu mensuel", money(p["monthly_income_tnd"]) if p.get("monthly_income_tnd") else "—")
    c[4].metric("KYC", p.get("kyc_risk_level", "—"))
    c[5].metric("Alertes en file", prof["nb_alertes_dans_file"])
    if hab:
        h = st.columns(5)
        h[0].metric("Opérations", hab["nb_operations"], help=hab["periode_observee"])
        h[1].metric("Montant moyen", money(hab["montant_moyen"]))
        h[2].metric("Montant p95", money(hab["montant_p95"]))
        h[3].metric("Part de nuit", f"{hab['part_operations_nuit_0h_6h']:.1%}")
        h[4].metric("Appareils / bénéficiaires", f"{hab['nb_appareils']} / {hab['nb_beneficiaires']}")
        st.caption("Pays physiques : " + ", ".join(f"{x['valeur']} ({x['part']:.0%})" for x in hab["pays_paiements_physiques"]) +
                   " · Canaux : " + ", ".join(f"{x['valeur']} ({x['part']:.0%})" for x in hab["canaux"]) +
                   " · Catégories : " + ", ".join(x["valeur"] for x in hab["categories"]))

    hist = da.history()
    if hist is None:
        st.info("Historique client non exporté.")
        return
    t = hist[hist.customer_id == cust].copy()
    if t.empty:
        st.info("Aucune opération pour ce client dans l'historique exporté.")
        return
    anchor = r.timestamp if r.customer_id == cust else t.timestamp.max()
    days = st.slider("Fenêtre de la timeline (jours avant l'alerte)", 1, 30, 7)
    w = t[(t.timestamp <= anchor + pd.Timedelta(hours=6)) & (t.timestamp >= anchor - pd.Timedelta(days=days))].copy()
    alerted = set(queue.transaction_id)
    w["⚑"] = w.transaction_id.map(lambda x: "🎯" if x == st.session_state.tx else ("🚨" if x in alerted else ""))
    st.subheader("Timeline")
    st.scatter_chart(w.assign(type=w["⚑"].replace({"": "normale", "🚨": "alerte", "🎯": "alerte ouverte"})),
                     x="timestamp", y="amount_tnd", color="type", height=260)
    ev = da.digital_events()
    if ev is not None:
        e = ev[(ev.customer_id == cust) & (ev.timestamp <= anchor + pd.Timedelta(hours=6)) &
               (ev.timestamp >= anchor - pd.Timedelta(days=days))]
        w = pd.concat([w, e.assign(**{"⚑": "📱", "transaction_type": e.event_type})], ignore_index=True)
    st.dataframe(w.sort_values("timestamp", ascending=False)[
        [c for c in ["⚑", "timestamp", "transaction_id", "transaction_type", "channel", "entry_mode", "merchant_category",
                     "amount_tnd", "city", "country", "status", "decline_reason", "device_id", "beneficiary_id"] if c in w.columns]],
        hide_index=True, width="stretch", height=360)
    if {"latitude", "longitude"} <= set(t.columns):
        geo = w.dropna(subset=["latitude", "longitude"])
        geo = geo.assign(color=geo["⚑"].map({"🎯": "#d62728", "🚨": "#ff7f0e"}).fillna("#1f77b4"))
        st.subheader("Carte des opérations")
        st.map(geo, latitude="latitude", longitude="longitude", color="color", size=40)
    else:
        st.caption("🗺️ Carte : coordonnées non exportées (ajouter latitude/longitude à customer_history).")


# ---------------------------------------------------------------- 4. performance
def page_performance():
    k = tools.get_kpis()
    lg, same, top = k["moteur_regles_actuel"], k["modele_meme_volume"], k["modele_top_1pct"]
    st.header("📊 Performance — validation juin → juillet 2026 (hors échantillon)")
    c = st.columns(4)
    c[0].metric("Fraudes détectées (top 1 %)", top["fraudes_detectees"], f"+{top['fraudes_detectees'] - lg['fraudes_detectees']} vs moteur actuel")
    c[1].metric("Fausses alertes", top["fausses_alertes"], f"{top['fausses_alertes'] - lg['fausses_alertes']} vs moteur actuel", delta_color="inverse")
    c[2].metric("Précision", f"{top['precision']:.1%}", f"{(top['precision'] - lg['precision']) * 100:+.1f} pts")
    c[3].metric("Rappel", f"{top['rappel']:.1%}", f"{(top['rappel'] - lg['rappel']) * 100:+.1f} pts")
    comp = pd.DataFrame([
        {"Approche": "Moteur de règles actuel", "Alertes": lg["alertes"], "Fraudes détectées": lg["fraudes_detectees"],
         "Précision": lg["precision"], "Rappel": lg["rappel"]},
        {"Approche": "Modèle, même volume d'alertes", "Alertes": same["alertes"], "Fraudes détectées": same["fraudes_detectees"],
         "Précision": same["precision"], "Rappel": same["rappel"]},
        {"Approche": "Modèle, top 1 % (capacité analystes)", "Alertes": top["alertes"], "Fraudes détectées": top["fraudes_detectees"],
         "Précision": top["precision"], "Rappel": top["rappel"]}])
    st.dataframe(comp, hide_index=True, width="stretch",
                 column_config={"Précision": st.column_config.NumberColumn(format="percent"),
                                "Rappel": st.column_config.NumberColumn(format="percent")})
    a, b = st.columns(2)
    with a:
        st.subheader("Rappel par typologie")
        rt = da.recall_by_type().set_index("fraud_scenario")[["recall_model", "recall_legacy"]]
        st.bar_chart(rt.rename(columns={"recall_model": "Modèle (top 1 %)", "recall_legacy": "Moteur actuel"}),
                     stack=False, horizontal=True, height=320)
    with b:
        st.subheader("Principaux facteurs du modèle")
        imp = da.importance().sort_values("gain_share", ascending=False).head(12)
        st.bar_chart(imp.set_index("label")["gain_share"], horizontal=True, height=320)
    st.subheader("Champion vs challengers")
    st.dataframe(da.leaderboard(), hide_index=True, width="stretch")
    st.caption(f"PR-AUC du modèle : {k['pr_auc_modele']} · {k['fraudes_validation']} fraudes en validation · "
               "Le moteur actuel reste meilleur sur CARTE_CLONEE_ETRANGER : sa règle est conservée en complément.")


# ---------------------------------------------------------------- 5. journal
def page_journal():
    st.header("📒 Journal des décisions et du copilote")
    d = tools.decisions()
    c = st.columns(4)
    c[0].metric("Décisions", len(d))
    for i, lab in enumerate(["BLOQUER", "ESCALADER", "VALIDER"], 1):
        c[i].metric(lab, int((d.decision == lab).sum()) if len(d) else 0)
    if len(d):
        d = d.merge(queue[["transaction_id", "risk_level", "score_pct", "period"]], on="transaction_id", how="left")
        st.dataframe(d.sort_values("decided_at", ascending=False), hide_index=True, width="stretch")
        st.download_button("Exporter (CSV)", d.to_csv(index=False).encode("utf-8"), "decisions.csv", "text/csv")
        st.caption("Boucle d'amélioration : ces décisions deviennent des labels pour le prochain réentraînement dans Fabric.")
    st.subheader("Traçabilité du copilote")
    u = copilot.usage_summary()
    st.caption(f"{u['appels']} questions · {u['tokens']:,} tokens · {u['caches']} réponses servies par le cache".replace(",", " "))
    if u.get("rows"):
        log = pd.DataFrame(u["rows"])
        log["outils"] = log.tools.map(lambda x: ", ".join(t["name"] for t in x))
        log["tokens_total"] = log.tokens.map(lambda x: x.get("total", 0))
        st.dataframe(log[[c for c in ["ts", "context_tx", "question", "mode", "outils", "tokens_total", "cached", "latency_s"]
                          if c in log.columns]].iloc[::-1], hide_index=True, width="stretch")


{PAGES[0]: page_queue, PAGES[1]: page_transaction, PAGES[2]: page_customer,
 PAGES[3]: page_performance, PAGES[4]: page_journal}[page]()
