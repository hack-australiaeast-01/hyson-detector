"""Fairness and limits sections of the Performance > Robustness page."""
import pandas as pd
import streamlit as st

import features as fx


def render_fairness(L, mode=None):
    fair = fx.fairness()
    if fair is not None and len(fair):
        st.markdown(f"**{L('Équité · le modèle traite-t-il tous les clients de la même façon ?', 'Fairness · does the model treat all customers alike?')}**")
        fa, fb = st.columns(2)
        for col, key, title in [(fa, "segment", L("Par segment", "By segment")), (fb, "age_band", L("Par âge", "By age"))]:
            v = fair[fair.period == "valid"].groupby(key)[["ops", "alerts", "tp", "frauds"]].sum()
            t = fair[fair.period == "test"].groupby(key)[["ops", "alerts"]].sum()
            tab = pd.DataFrame({
                L("Taux d'alerte (flux du jour)", "Alert rate (live flow)"): (t.alerts / t.ops).round(4),
                L("Taux de fraude (validation)", "Fraud rate (validation)"): (v.frauds / v.ops).round(4),
                L("Précision", "Precision"): (v.tp / v.alerts.clip(lower=1)).round(3),
                L("Rappel", "Recall"): (v.tp / v.frauds.clip(lower=1)).round(3)}).rename_axis(title).reset_index()
            col.dataframe(tab, hide_index=True, width="stretch",
                          column_config={c: st.column_config.NumberColumn(format="percent") for c in tab.columns[1:]})
        st.caption(L("Le genre n'est jamais utilisé. Âge et segment sont des variables de profil : leur effet est surveillé. "
                     "Taux d'alerte homogènes (≈ 0,9–1,1 %) ; les retraités et les 60 ans et plus ont moins de fraude, une précision "
                     "et un rappel plus bas : à suivre en production (seuil ou revue dédiée), et à expliquer au client en cas d'alerte.",
                     "Gender is never used. Age and segment are profile features: their effect is monitored. Alert rates are similar "
                     "(≈ 0.9–1.1%); retirees and over-60s have less fraud, lower precision and recall: to monitor in production "
                     "(threshold or dedicated review), and to explain to the customer when alerted."))


def render_limits(L):
    st.markdown(f"**{L('Limites et suivi', 'Limits and monitoring')}**")
    st.markdown("\n".join([
        L("- Données synthétiques riches en fraude (≈ 0,55 % contre ≈ 0,1 % en réalité) : à revalider sur données réelles.",
          "- Synthetic, fraud-rich data (≈ 0.55% fraud vs ≈ 0.1% in reality): re-validate on real data."),
        L("- Scoring par lots (pas à l'autorisation) ; délai de labellisation non simulé dans le backtest.",
          "- Batch scoring (not at authorisation time); label delay not simulated in the backtest."),
        L("- Suivi : dérive PSI du score, volume d'alertes par jour, décisions des analystes renvoyées vers OneLake.",
          "- Monitoring: PSI drift of the score, alert volume per day, analyst decisions fed back to OneLake."),
        L("- Réentraînement : pipeline Fabric « pl_hyson_retrain » ; une nouvelle version remplace la v1 seulement si elle la bat au backtest.",
          "- Retraining: Fabric pipeline \"pl_hyson_retrain\"; a new version replaces v1 only if it beats it on the same backtest.")]))
