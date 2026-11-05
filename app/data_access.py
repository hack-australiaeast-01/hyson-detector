"""Read-only access to the Gold exports (parquet files produced by the Fabric notebooks)."""
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"

FEATURE_FR = {
    "f_age": "Âge du client", "f_avg_amt_before": "Montant moyen habituel", "f_balance": "Solde moyen",
    "f_contactless_near_limit": "Sans contact proche du plafond", "f_digital_user": "Client banque digitale",
    "f_dow": "Jour de la semaine", "f_income": "Revenu mensuel", "f_is_night": "Opération de nuit",
    "f_max_amt_before": "Plus gros montant passé", "f_night_share_before": "Part d'opérations de nuit (passé)",
    "f_payday": "Période de paie", "f_std_amt_before": "Variabilité des montants",
    "f_tenure_days": "Ancienneté client (jours)", "f_ramadan": "Ramadan", "f_intl_card": "Carte internationale",
    "f_new_category": "Nouvelle catégorie de commerçant", "f_round_amount": "Montant rond",
    "f_benef_n_customers_before": "Clients ayant déjà payé ce bénéficiaire",
}
RISK_ICON = {"ELEVE": "🔴", "MOYEN": "🟠", "FAIBLE": "🟢"}


def label(name):
    return FEATURE_FR.get(name, name)


def _read(name):
    path = DATA / f"{name}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]) and getattr(df[c].dt, "tz", None) is not None:
            df[c] = df[c].dt.tz_localize(None)   # Fabric wrote Tunis local time as UTC
    return df


@lru_cache(maxsize=None)
def queue():
    q = _read("gold_alert_queue")
    q.loc[q.period == "test", ["is_fraud", "fraud_scenario"]] = None   # never expose test labels
    q["risk_icon"] = q.risk_level.map(RISK_ICON).fillna("⚪")
    q["date"] = q.timestamp.dt.date
    return q.sort_values(["period", "rank_in_period"]).reset_index(drop=True)


@lru_cache(maxsize=None)
def explanations():
    e = _read("gold_alert_explanations")
    e["factor"] = e.factor.map(label)
    return e


@lru_cache(maxsize=None)
def metrics():
    m = _read("gold_model_metrics")
    return dict(zip(m.metric, m.value))


@lru_cache(maxsize=None)
def leaderboard():
    return _read("gold_model_leaderboard")


@lru_cache(maxsize=None)
def recall_by_type():
    return _read("gold_model_recall_by_type")


@lru_cache(maxsize=None)
def importance():
    imp = _read("gold_model_importance")
    imp["label"] = imp.feature.map(label)
    return imp


@lru_cache(maxsize=None)
def customers():
    c = _read("customers")
    if c is None:
        return None
    for col in ["monthly_income_tnd", "avg_monthly_balance_tnd"]:
        c[col] = pd.to_numeric(c[col], errors="coerce")
    return c


@lru_cache(maxsize=None)
def history():
    """Valid + test transactions of customers present in the alert queue (no labels)."""
    h = _read("customer_history")
    if h is None:
        return None
    h = h.drop(columns=[c for c in ["is_fraud", "fraud_scenario"] if c in h.columns])
    return h.sort_values("timestamp").reset_index(drop=True)


@lru_cache(maxsize=None)
def digital_events():
    return _read("digital_events")


def data_status():
    names = ["gold_alert_queue", "gold_alert_explanations", "gold_model_metrics", "gold_model_leaderboard",
             "gold_model_recall_by_type", "gold_model_importance", "customer_history", "customers", "digital_events"]
    return {n: (DATA / f"{n}.parquet").exists() for n in names}
