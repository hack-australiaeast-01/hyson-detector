"""Page « Contexte personnel » — is this operation coherent with THIS customer's life? (principle given by a bank CEO: be human with the customer first; his illustration: a retired customer abroad)."""
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import streamlit as st

import context
import data_access as da
import ui

DEMO_CUSTOMER = "C000308"       # 81, retired, Sfax — a customer of the alert queue (history available online too)


def _band(b, L):
    for k, fr, en, col in context.BANDS:
        if k == b:
            return L(fr, en), col
    return b, ui.MUTED


def _result(res, L, lang, key):
    if not res.get("scope"):
        st.info(L("Opération au domicile du client ou à distance : pas de lecture de voyage (le score du modèle et le copilote s'appliquent).",
                  "Operation at the customer's home or remote: no travel reading (the model score and the copilot apply)."))
        return
    sc = res["score"]
    if sc is None:
        st.warning(L("Poids non disponibles pour ce type de lieu (" + context.load_weights().get("domestic_note", "") + ")",
                     "No weights for this kind of place yet (no such operations in the data)."))
        return
    label, col = _band(sc["band"], L)
    p = res["profile"]
    m = sc.get("measured") or {}
    rate = f"{m['fraud_rate']:.0%}" if m.get("fraud_rate") is not None else "—"
    st.markdown(
        f'<div style="background:#fff;border:1px solid {ui.LINE};border-left:6px solid {col};border-radius:16px;padding:1rem 1.2rem;margin:.4rem 0 .8rem">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap">'
        f'<div><div style="font-size:.8rem;color:{ui.MUTED};text-transform:uppercase;letter-spacing:.06em">{L("Lecture du contexte personnel", "Personal context reading")}</div>'
        f'<div style="font-size:1.55rem;font-weight:800;color:{col}">{ui.esc(label)}</div>'
        f'<div style="color:{ui.MUTED}">{ui.esc(res["place_label"])} · {ui.esc(context._age_band(p.get("age")))} {L("ans", "y/o")} · '
        f'{ui.esc(p.get("segment", "—"))} · {L("domicile", "home")} {ui.esc(p.get("home_city", "—"))} · '
        f'{res["n_history"]} {L("opérations connues avant", "known operations before")}</div></div>'
        f'<div style="text-align:right"><div style="font-size:2rem;font-weight:800;color:{ui.NAVY}">{rate}</div>'
        f'<div style="font-size:.82rem;color:{ui.MUTED};max-width:260px">{L("de fraudes mesurées dans ce niveau (test 2026, opérations à l’étranger)", "fraud measured at this level (2026 test, operations abroad)")}</div></div>'
        f'</div></div>', unsafe_allow_html=True)
    pro, con = context.evidence(res, lang)
    a, b = st.columns(2)
    with a:
        ui.section(L("Cohérent avec sa vie", "Consistent with his life"))
        ui.factors([{"facteur": f"{x['text']} — {x['effect']}"} for x in pro], False, empty=L("Aucun élément", "None"))
    with b:
        ui.section(L("Ce qui inquiète", "What is worrying"))
        ui.factors([{"facteur": f"{x['text']} — {x['effect']}"} for x in con], True, empty=L("Aucun élément", "None"))
    ui.section(L("Que faire avec le client", "What to do with the customer"))
    st.markdown(f"> {context.contact_script(res, lang)}")
    st.caption(L("Jamais déduit ni affiché : ", "Never inferred nor shown: ") + ", ".join(context.NEVER) +
               L(". Le système lit des faits (lieux, dates, montants, appareil), pas les raisons du voyage.",
                 ". The system reads facts (places, dates, amounts, device), never the reasons for a trip."))
    c1, c2 = st.columns(2)
    if c1.button(L("Expliquer en langage naturel (IA)", "Explain in plain language (AI)"), key=f"ctx_nl_{key}", icon=":material/auto_awesome:"):
        with st.spinner(L("L'IA rédige à partir des faits calculés…", "The AI writes from the computed facts…")):
            txt = context.narrative(res, lang)
        st.info(txt or L("Azure OpenAI indisponible : la lecture ci-dessus reste valable (calculée sans IA).",
                         "Azure OpenAI unavailable: the reading above stands (computed without AI)."))
    with c2.popover(L("Enregistrer un avis de voyage", "Record a travel notice"), icon=":material/flight_takeoff:"):
        d1 = st.date_input(L("Du", "From"), res["tx"]["timestamp"].date() - timedelta(days=2), key=f"ctx_d1_{key}")
        d2 = st.date_input(L("Au", "To"), res["tx"]["timestamp"].date() + timedelta(days=14), key=f"ctx_d2_{key}")
        if st.button(L("Enregistrer (déclaré par le client)", "Save (declared by the customer)"), key=f"ctx_save_{key}", type="primary"):
            context.add_notice(p.get("customer_id"), res["place"], d1, d2, by=st.session_state.get("analyst", "analyste"))
            st.success(L("Avis enregistré : les prochaines opérations sur place seront lues avec ce contexte.",
                         "Notice saved: the next operations there will be read with this context."))


def page_context(ctx):
    L, lang = ctx.L, ctx.lang
    ui.hero(L("Connaissance client", "Know your customer"), L("Contexte personnel", "Personal context"),
            L("Cette opération est-elle cohérente avec la vie de CE client ? Voyages précédents, préparation, séjour en cours, vague de voyages, "
              "montant vs ses habitudes — sans jamais deviner ses raisons.",
              "Is this operation coherent with THIS customer's life? Previous trips, preparation, stay in progress, travel waves, amount vs his "
              "habits — never guessing his reasons."), ctx.chips())
    w = context.load_weights() or {}
    tabs = st.tabs([L("Opération de la file", "Queue operation"), L("Nouvelle opération (temps réel)", "New operation (real time)"),
                    L("Flux d'une autre banque (CSV)", "Another bank's feed (CSV)"), L("Comment c'est mesuré", "How it is measured")])
    with tabs[0]:
        q = ctx.queue
        abroad = q[(q.country.astype(str) != "TN") & q.channel.astype(str).isin(context.PHYSICAL)] if "country" in q else q.iloc[0:0]
        opts = abroad.sort_values("score_model", ascending=False).transaction_id.tolist() or q.transaction_id.tolist()
        if st.session_state.get("tx") in opts and st.session_state.get("ctx_from") != st.session_state.get("tx"):
            st.session_state.ctx_tid = st.session_state.ctx_from = st.session_state.tx      # opened from a transaction page
        tid = st.selectbox(L("Alerte à l'étranger", "Alert abroad"), opts, key="ctx_tid",
                           format_func=lambda t: f"{t} · {q.set_index('transaction_id').loc[t, 'country']} · "
                                                 f"{q.set_index('transaction_id').loc[t, 'amount_tnd']:,.0f} TND".replace(",", " "))
        r = q[q.transaction_id == tid].iloc[0]
        res = context.assess(r.to_dict(), r.customer_id, lang=lang)
        _result(res, L, lang, "q")
    with tabs[1]:
        st.caption(L("Une opération qui arrive maintenant (d'une autre banque, d'un terminal…) : lue immédiatement contre l'historique du client, "
                     "sans réentraînement. Exemples (scénarios illustratifs sur un client retraité synthétique) :",
                     "An operation arriving now (another bank, a terminal…): read immediately against the customer's history, no retraining. "
                     "Examples (illustrative scenarios on a synthetic retired customer):"))
        presets = {L("Exemple · yacht en Italie", "Example · yacht in Italy"):
                       dict(country="IT", city="Naples", amount=48000.0, channel="TPE", mode="CHIP", cat="Nautisme", hours_after=5),
                   L("Exemple · séjour en Arabie saoudite", "Example · stay in Saudi Arabia"):
                       dict(country="SA", city="La Mecque", amount=180.0, channel="TPE", mode="CHIP", cat="Supermarche", hours_after=200),
                   L("Exemple · courses à Paris", "Example · shopping in Paris"):
                       dict(country="FR", city="Paris", amount=95.0, channel="TPE", mode="SANS_CONTACT", cat="Supermarche", hours_after=60)}
        pc = st.segmented_control(L("Exemple", "Example"), list(presets), key="ctx_preset", default=list(presets)[0])
        pr = presets.get(pc) or list(presets.values())[0]
        hist = da.customer_tx(DEMO_CUSTOMER)
        last = pd.to_datetime(hist.timestamp).max() if len(hist) else pd.Timestamp("2026-09-29")
        default_ts = last + timedelta(hours=pr["hours_after"])
        with st.form("ctx_new"):
            c = st.columns(4)
            cid = c[0].text_input(L("Client", "Customer"), DEMO_CUSTOMER)
            d = c[1].date_input("Date", default_ts.date())
            tm = c[2].time_input(L("Heure", "Time"), default_ts.time().replace(second=0, microsecond=0))
            amount = c[3].number_input(L("Montant (TND)", "Amount (TND)"), value=pr["amount"], min_value=0.0, step=10.0)
            c = st.columns(5)
            country = c[0].text_input(L("Pays (code)", "Country (code)"), pr["country"]).upper()[:2]
            city = c[1].text_input(L("Ville", "City"), pr["city"])
            channel = c[2].selectbox(L("Canal", "Channel"), ["TPE", "DAB"], index=["TPE", "DAB"].index(pr["channel"]))
            mode = c[3].selectbox(L("Mode", "Mode"), ["CHIP", "SANS_CONTACT", "MAGSTRIPE"], index=["CHIP", "SANS_CONTACT", "MAGSTRIPE"].index(pr["mode"]))
            cat = c[4].text_input(L("Type de commerce", "Kind of shop"), pr["cat"])
            go = st.form_submit_button(L("Lire le contexte", "Read the context"), type="primary")
        if go or pc:
            tx = {"timestamp": datetime.combine(d, tm), "amount_tnd": amount, "country": country, "city": city, "channel": channel,
                  "entry_mode": mode, "merchant_category": cat}
            res = context.assess(tx, cid.strip().upper(), lang=lang)
            _result(res, L, lang, "n")
    with tabs[2]:
        st.caption(L("Colonnes attendues (notre schéma, ou la sortie de « Nouvelle source de données ») : transaction_id, customer_id, timestamp, "
                     "amount_tnd, country, city, channel, entry_mode, merchant_category. Les lignes sont lues dans l'ordre du temps : chaque opération "
                     "voit l'historique du client ET les lignes précédentes du flux.",
                     "Expected columns (our schema, or the output of « New data source »): transaction_id, customer_id, timestamp, amount_tnd, "
                     "country, city, channel, entry_mode, merchant_category. Rows are read in time order: each one sees the customer's history AND "
                     "the earlier rows of the feed."))
        up = st.file_uploader("CSV", type=["csv"], key="ctx_csv")
        if st.button(L("Essayer avec un flux d'exemple", "Try a sample feed"), key="ctx_sample"):
            st.session_state.ctx_sample_on = True
        df = pd.read_csv(up) if up is not None else (_sample_feed() if st.session_state.get("ctx_sample_on") else None)
        if df is not None:
            with st.spinner(L("Lecture du flux…", "Reading the feed…")):
                out = context.batch(df, lang)
            names = {k: (fr if lang != "en" else en) for k, fr, en, _ in context.BANDS}
            out["verdict"] = out.verdict.map(lambda v: names.get(v, v))
            st.dataframe(out, hide_index=True, width="stretch")
            st.download_button("CSV", out.to_csv(index=False).encode("utf-8"), "contexte_flux.csv", "text/csv")
    with tabs[3]:
        a = w.get("abroad", {})
        t = a.get("test", {})
        if t:
            st.markdown(L(
                f"**Mesuré sur {t['n']:,} paiements physiques à l'étranger de 2026 (jamais utilisés pour régler les poids, fixés sur 2025).**\n"
                f"- Pouvoir de séparation : ROC-AUC **{t['roc_auc']}**, PR-AUC **{t['pr_auc']}** (taux de fraude de base {t['base_rate']:.1%}).\n"
                f"- « Voyage cohérent » : **{a['bands']['coherent']['n']:,}** opérations, **{a['bands']['coherent']['fraud_rate']:.1%}** de fraude — "
                f"elles contiennent **{t['legacy_false_alerts_coherent']:,} des {t['legacy_false_alerts']:,} fausses alertes** du moteur actuel à l'étranger "
                f"(appels évitables), pour {t['frauds_in_coherent']} fraudes sur {t['frauds']} (à rattraper par le modèle principal).\n"
                f"- « Peu cohérent » : **{a['bands']['incoherent']['n']:,}** opérations, **{a['bands']['incoherent']['fraud_rate']:.0%}** de fraude.\n"
                f"- Juin–juillet : {t['model_false_alerts_valid_coherent']} des {t['model_false_alerts_valid']} fausses alertes du modèle à l'étranger "
                "sont lues « voyage cohérent » → un appel en moins, ou une simple notification.",
                f"**Measured on {t['n']:,} physical payments abroad in 2026 (never used to set the weights, fitted on 2025).**\n"
                f"- Separation: ROC-AUC **{t['roc_auc']}**, PR-AUC **{t['pr_auc']}** (base fraud rate {t['base_rate']:.1%}).\n"
                f"- \"Coherent trip\": **{a['bands']['coherent']['n']:,}** operations, **{a['bands']['coherent']['fraud_rate']:.1%}** fraud — they hold "
                f"**{t['legacy_false_alerts_coherent']:,} of the {t['legacy_false_alerts']:,} false alerts** of the current engine abroad (avoidable calls), "
                f"for {t['frauds_in_coherent']} of {t['frauds']} frauds (left to the main model).\n"
                f"- \"Hardly consistent\": **{a['bands']['incoherent']['n']:,}** operations, **{a['bands']['incoherent']['fraud_rate']:.0%}** fraud.\n"
                f"- June–July: {t['model_false_alerts_valid_coherent']} of the model's {t['model_false_alerts_valid']} false alerts abroad read "
                "\"coherent trip\" → one call fewer, or a simple notification."))
            rows = [{"signal": k, "valeur": v, "effet": (f"÷{2.718 ** -x:.1f}" if x < 0 else f"×{2.718 ** x:.1f}") if x else "ignoré"}
                    for k, m in a["lr"].items() for v, x in m.items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=320)
            st.caption(L("Garde-fous métier : ", "Business guardrails: ") + " · ".join(a.get("policy", [])) +
                       (L(" · signaux ignorés (sens contraire au bon sens sur ces données) : ", " · ignored signals (against common sense on this data): ")
                        + ", ".join(a["ignored"]) if a.get("ignored") else "") + " · " + w.get("domestic_note", ""))


@st.cache_data(show_spinner=False)
def _sample_feed():
    """A small feed from another bank: an illustrative week of a synthetic retired customer + a cloned card used at the same time in Italy."""
    h = da.customer_tx(DEMO_CUSTOMER)
    t0 = pd.to_datetime(h.timestamp).max() if len(h) else pd.Timestamp("2026-09-29")
    rows = [("NEW0001", t0 + timedelta(days=1, hours=2), 640.0, "TN", "Sfax", "TPE", "CHIP", "Agence de voyage"),
            ("NEW0002", t0 + timedelta(days=4, hours=9), 210.0, "SA", "Djeddah", "TPE", "CHIP", "Supermarche"),
            ("NEW0003", t0 + timedelta(days=5, hours=3), 300.0, "SA", "La Mecque", "DAB", "CHIP", "Retrait DAB"),
            ("NEW0004", t0 + timedelta(days=5, hours=4), 9500.0, "IT", "Milan", "TPE", "MAGSTRIPE", "Bijouterie"),
            ("NEW0005", t0 + timedelta(days=6, hours=2), 95.0, "SA", "La Mecque", "TPE", "CHIP", "Restaurant")]
    return pd.DataFrame([{"transaction_id": a, "customer_id": DEMO_CUSTOMER, "timestamp": b, "amount_tnd": c, "country": d, "city": e,
                          "channel": f, "entry_mode": g, "merchant_category": k} for a, b, c, d, e, f, g, k in rows])
