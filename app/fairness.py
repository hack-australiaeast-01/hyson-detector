"""Fairness check + acknowledged model limits (Performance page).

Fairness = are some customer groups disturbed more than others? We compare, per segment and per age band, the
false-alert rate on legitimate operations (validation Jun–Jul 2026), for the model (top 1 %) and the current rules.
Gender is never used by the model; this checks the other profile variables (age, segment) do not act as proxies.
"""
import pandas as pd
import streamlit as st

import features as fx
import ui

AGE = ("CASE WHEN c.age < 30 THEN '18-29' WHEN c.age < 45 THEN '30-44' WHEN c.age < 60 THEN '45-59' ELSE '60+' END")


@st.cache_data(ttl=3600, show_spinner=False)
def fairness_raw(_mode):
    return fx._q("fairness", f"""
        SELECT c.segment, {AGE} AS age_band,
               SUM(CASE WHEN f.is_fraud = 0 THEN 1 ELSE 0 END) AS legit,
               SUM(CASE WHEN f.is_fraud = 0 AND g.is_alert = 1 THEN 1 ELSE 0 END) AS legit_alerted,
               SUM(CASE WHEN f.is_fraud = 0 AND g.legacy_alert = 1 THEN 1 ELSE 0 END) AS legit_rules,
               SUM(CASE WHEN f.is_fraud = 1 THEN 1 ELSE 0 END) AS frauds,
               SUM(CASE WHEN f.is_fraud = 1 AND g.is_alert = 1 THEN 1 ELSE 0 END) AS frauds_caught
        FROM dbo.gold_scores g
        JOIN dbo.silver_transactions f ON f.transaction_id = g.transaction_id
        JOIN dbo.customers c ON c.customer_id = f.customer_id
        WHERE g.period = 'valid'
        GROUP BY c.segment, {AGE}""")


def _table(raw, by):
    t = raw.groupby(by, as_index=False)[["legit", "legit_alerted", "legit_rules", "frauds", "frauds_caught"]].sum()
    t["fpr_model"] = t.legit_alerted / t.legit           # share of legitimate operations wrongly alerted
    t["fpr_rules"] = t.legit_rules / t.legit
    t["recall"] = t.frauds_caught / t.frauds.where(t.frauds > 0)
    return t


def render_fairness(L, mode):
    ui.section(L("Équité : les clients sont-ils dérangés de la même façon ?", "Fairness: are customers disturbed equally?"))
    raw = fairness_raw(mode)
    if raw is None or raw.empty:
        st.info(L("Données d'équité indisponibles.", "Fairness data unavailable."))
        return
    for col in ["legit", "legit_alerted", "legit_rules", "frauds", "frauds_caught"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0)
    a, b = st.columns(2)
    cfg = {"legit": st.column_config.NumberColumn(L("Opérations légitimes", "Legitimate ops"), format="%d"),
           "fpr_model": st.column_config.NumberColumn(L("Fausses alertes · modèle", "False alerts · model"), format="%.3f%%"),
           "fpr_rules": st.column_config.NumberColumn(L("Fausses alertes · règles", "False alerts · rules"), format="%.3f%%"),
           "recall": st.column_config.NumberColumn(L("Fraudes détectées", "Frauds caught"), format="percent")}
    out = {}
    for col, by, title in [(a, "segment", L("Par segment", "By segment")), (b, "age_band", L("Par âge", "By age"))]:
        t = _table(raw, by)
        out[by] = t
        show = t[[by, "legit", "fpr_model", "fpr_rules", "recall"]].assign(fpr_model=t.fpr_model * 100, fpr_rules=t.fpr_rules * 100)
        with col, st.container(border=True):
            st.markdown(f"**{title}**")
            st.dataframe(show, hide_index=True, width="stretch",
                         column_config={by: "Segment" if by == "segment" else L("Âge", "Age"), **cfg})
    lines = []
    for by, name in [("segment", L("segments", "segments")), ("age_band", L("tranches d'âge", "age bands"))]:
        t = out[by][out[by].legit >= 500]
        if len(t) < 2:
            continue
        hi, lo = t.loc[t.fpr_model.idxmax()], t.loc[t.fpr_model.idxmin()]
        ratio = hi.fpr_model / lo.fpr_model if lo.fpr_model > 0 else float("inf")
        rhi, rlo = t.loc[t.fpr_rules.idxmax()], t.loc[t.fpr_rules.idxmin()]
        rratio = rhi.fpr_rules / rlo.fpr_rules if rlo.fpr_rules > 0 else float("inf")
        lines.append(L(f"Entre {name} : le modèle dérange **{ratio:.1f}×** plus le groupe « {hi[by]} » ({hi.fpr_model:.3%}) que « {lo[by]} » "
                       f"({lo.fpr_model:.3%}) ; les règles actuelles : **{rratio:.1f}×** (« {rhi[by]} » {rhi.fpr_rules:.3%}).",
                       f"Across {name}: the model disturbs group \"{hi[by]}\" **{ratio:.1f}×** more ({hi.fpr_model:.3%}) than \"{lo[by]}\" "
                       f"({lo.fpr_model:.3%}); current rules: **{rratio:.1f}×** (\"{rhi[by]}\" {rhi.fpr_rules:.3%})."))
    for ln in lines:
        st.markdown("- " + ln)
    st.caption(L("Lecture : taux d'opérations légitimes alertées à tort, validation juin–juillet 2026. Le genre n'est jamais utilisé ; "
                 "l'âge et le segment restent des variables de profil, d'où ce contrôle. Un écart important se corrige par un seuil "
                 "par segment ou en retirant la variable ; la décision revient au comité des risques.",
                 "How to read: share of legitimate operations wrongly alerted, validation June–July 2026. Gender is never used; age and "
                 "segment remain profile variables, hence this check. A large gap is fixed with a per-segment threshold or by dropping "
                 "the variable; the decision belongs to the risk committee."))


def render_limits(L):
    ui.section(L("Limites assumées et parades", "Acknowledged limits and safeguards"))
    items = [
        (L("Délai de signalement", "Reporting delay"),
         L("Une fraude est signalée en médiane 11 jours après l'opération : les dernières semaines paraissent « propres » à tort. "
           "En production, on exclut les 30 derniers jours de l'entraînement (maturité des labels).",
           "A fraud is reported a median 11 days after the operation, so the latest weeks look wrongly \"clean\". In production, the "
           "last 30 days are excluded from training (label maturity).")),
        (L("Biais de la boucle de feedback", "Feedback-loop bias"),
         L("Seules les alertes sont enquêtées : les fraudes jamais alertées ne deviennent jamais des labels. Parade : un échantillon "
           "aléatoire d'environ 0,1 % d'opérations non alertées revu chaque semaine.",
           "Only alerts are investigated, so frauds never alerted never become labels. Safeguard: a random sample of about 0.1% of "
           "non-alerted operations reviewed every week.")),
        (L("Données synthétiques", "Synthetic data"),
         L("Le modèle peut apprendre la logique du générateur plutôt que la vraie fraude ; taux de fraude volontairement élevé (≈ 0,55 %). "
           "Avant production : réentraînement et validation sur données réelles.",
           "The model can learn the generator's logic rather than real fraud; fraud rate deliberately high (≈ 0.55%). Before production: "
           "retraining and validation on real data.")),
        (L("Score ≠ probabilité", "Score ≠ probability"),
         L("Le score classe les opérations ; la probabilité réelle est la précision mesurée par niveau d'alerte, affichée à côté.",
           "The score ranks operations; the real probability is the precision measured per alert level, shown next to it.")),
        (L("Carte clonée à l'étranger", "Card cloned abroad"),
         L("Le moteur actuel reste meilleur sur cette typologie : sa règle (pays étranger) est conservée en complément.",
           "The current engine stays better on this type: its rule (foreign country) is kept as a complement.")),
        (L("Points de compromission", "Points of compromise"),
         L("Signal d'enquête, pas de score : en validation il n'améliore pas la précision (41 % vs 40 %).",
           "Investigation signal, not a score input: in validation it does not improve precision (41% vs 40%).")),
    ]
    cols = st.columns(3)
    for i, (title, body) in enumerate(items):
        with cols[i % 3], st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(body)
