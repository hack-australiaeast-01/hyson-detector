"""Bank-specific model and unsupervised behaviour score, on canonical data only.

- Features use only the past of each customer (expanding statistics shifted by one, look-back windows), never later information.
- Model: L2 logistic regression (Newton, balanced classes) in numpy: small, explainable, stored as JSON (no pickle).
- Validation: time split (train on the first 70 % of the period, test on the rest); compared with the bank's own score if present.
- A trained model is a *candidate*: it scores nothing until an admin approves it. Never retrained automatically.
- Without labels, the behaviour score ranks departures from a customer's own habits; it is not a fraud probability.
"""
from datetime import datetime

import numpy as np
import pandas as pd

import mapper as mp

CATS = {"channel": list(mp.VOCAB["channel"]), "entry_mode": list(mp.VOCAB["entry_mode"]),
        "transaction_type": list(mp.VOCAB["transaction_type"])}
SENSITIVE_EVENTS = {"AJOUT_BENEFICIAIRE", "AJOUT_APPAREIL", "REINITIALISATION_MOT_DE_PASSE", "MODIFICATION_NUMERO_TELEPHONE"}
LABELS = {  # feature -> (FR, EN) reason when it pushes the score up
    "z_amount": ("montant inhabituel pour ce client", "amount unusual for this customer"),
    "log_amount": ("montant élevé", "high amount"),
    "count_24h": ("rafale d'opérations sur 24 h", "burst of operations within 24 h"),
    "hours_since_prev": ("délai inhabituel depuis l'opération précédente", "unusual gap since the previous operation"),
    "new_country": ("premier usage dans ce pays", "first use in this country"),
    "new_merchant": ("nouveau commerçant pour ce client", "new merchant for this customer"),
    "new_device": ("nouvel appareil", "new device"),
    "foreign": ("opération à l'étranger", "foreign operation"),
    "night": ("opération de nuit (0 h–6 h)", "night-time operation (0–6 h)"),
    "weekend": ("week-end", "weekend"),
    "failed_logins_24h": ("connexions échouées dans les 24 h précédentes", "failed logins in the previous 24 h"),
    "sensitive_events_72h": ("changement sensible du compte dans les 72 h (appareil, bénéficiaire, mot de passe, téléphone)",
                             "sensitive account change in the previous 72 h (device, payee, password, phone)"),
    "history_len": ("client avec peu d'historique", "customer with little history"),
}


def _first_seen(d, col):
    if col not in d or d[col].isna().all():
        return pd.Series(0.0, index=d.index)
    first = d.groupby(["customer_id", d[col].fillna("∅")]).cumcount().eq(0)
    return (first & d["history_len"].gt(3) & d[col].notna()).astype(float)


def _window_counts(d, ev, mask, hours):
    """Number of auth events (mask) of the same customer in [t - hours, t)."""
    e = ev.loc[mask, ["customer_id", "timestamp"]].dropna().astype({"timestamp": "datetime64[ns]"}).sort_values("timestamp")
    if e.empty:
        return pd.Series(0.0, index=d.index)
    e["cum"] = e.groupby("customer_id").cumcount() + 1
    q = d[["customer_id", "timestamp"]].astype({"timestamp": "datetime64[ns]"}).reset_index().sort_values("timestamp")
    now = pd.merge_asof(q, e, on="timestamp", by="customer_id", direction="backward", allow_exact_matches=False)
    q2 = q.assign(timestamp=q["timestamp"] - pd.Timedelta(hours=hours))
    then = pd.merge_asof(q2, e, on="timestamp", by="customer_id", direction="backward", allow_exact_matches=True)
    cnt = (now["cum"].fillna(0).to_numpy() - then["cum"].fillna(0).to_numpy())
    return pd.Series(cnt, index=now["index"].to_numpy()).reindex(d.index).fillna(0.0)


def features(tx, auth=None):
    d = tx.copy()
    d = d[d["timestamp"].notna() & d["customer_id"].notna()]
    d = d.sort_values(["customer_id", "timestamp"], kind="stable")
    amt = d["amount_tnd"] if "amount_tnd" in d and d["amount_tnd"].notna().any() else d["amount"]
    d["log_amount"] = np.log1p(amt.clip(lower=0).fillna(0))
    g = d.groupby("customer_id")
    n = g.cumcount()
    s1 = g["log_amount"].cumsum() - d["log_amount"]
    s2 = (d["log_amount"] ** 2).groupby(d["customer_id"]).cumsum() - d["log_amount"] ** 2
    mean = s1 / n.replace(0, np.nan)
    var = (s2 / n.replace(0, np.nan) - mean ** 2).clip(lower=0)
    d["history_len"] = n
    d["z_amount"] = ((d["log_amount"] - mean) / (np.sqrt(var) + 0.35)).where(n >= 3, 0).fillna(0).clip(-5, 8)
    gap = (d["timestamp"] - g["timestamp"].shift()).dt.total_seconds() / 3600
    d["hours_since_prev"] = np.log1p(gap.fillna(24 * 90).clip(0, 24 * 90))
    roll = d.set_index("timestamp").groupby("customer_id")["log_amount"].rolling("24h").count()
    d["count_24h"] = (roll.to_numpy() - 1)
    d["new_country"] = _first_seen(d, "country")
    d["new_merchant"] = _first_seen(d, "merchant_id")
    d["new_device"] = _first_seen(d, "device_id")
    home = d["country"].mode().iat[0] if "country" in d and d["country"].notna().any() else None
    d["foreign"] = (d["country"].notna() & (d["country"] != home)).astype(float) if home else 0.0
    d["night"] = (d["timestamp"].dt.hour < 6).astype(float)
    d["weekend"] = (d["timestamp"].dt.dayofweek >= 5).astype(float)
    if auth is not None and {"customer_id", "timestamp", "event_type"} <= set(auth.columns):
        ev = auth.dropna(subset=["customer_id", "timestamp"])
        failed = (ev["status"] == "ECHEC") if "status" in ev else pd.Series(False, index=ev.index)
        d["failed_logins_24h"] = _window_counts(d, ev, failed & (ev["event_type"] == "CONNEXION"), 24)
        d["sensitive_events_72h"] = _window_counts(d, ev, ev["event_type"].isin(SENSITIVE_EVENTS), 72)
    cols = ["log_amount", "z_amount", "count_24h", "hours_since_prev", "new_country", "new_merchant", "new_device", "foreign", "night",
            "weekend", "history_len"] + [c for c in ("failed_logins_24h", "sensitive_events_72h") if c in d]
    d["history_len"] = np.log1p(d["history_len"])
    X = d[cols].astype(float)
    for c, levels in CATS.items():
        if c in d and d[c].notna().any():
            for lv in levels:
                X[f"{c}={lv}"] = (d[c] == lv).astype(float)
    return X.reindex(tx.index)


# ---------------------------------------------------------------- metrics
def average_precision(y, s):
    o = np.argsort(-s, kind="stable")
    y = np.asarray(y)[o]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / max(y.sum(), 1))


def roc_auc(y, s):
    y = np.asarray(y)
    r = pd.Series(s).rank().to_numpy()
    p = y.sum()
    n = len(y) - p
    return float((r[y == 1].sum() - p * (p + 1) / 2) / max(p * n, 1))


def at_top(y, s, frac=0.01):
    k = max(1, int(round(len(s) * frac)))
    top = np.argsort(-s, kind="stable")[:k]
    y = np.asarray(y)
    return {"alerts": k, "frauds_caught": int(y[top].sum()), "precision": float(y[top].mean()), "recall": float(y[top].sum() / max(y.sum(), 1))}


def evaluate(y, s):
    return {"pr_auc": round(average_precision(y, s), 4), "roc_auc": round(roc_auc(y, s), 4), "base_rate": round(float(np.mean(y)), 5),
            "top_1pct": at_top(y, s, 0.01), "top_5pct": at_top(y, s, 0.05)}


# ---------------------------------------------------------------- model
def _sig(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def fit(X, y, l2=1.0, iters=40):
    mu = X.mean().to_numpy()
    sd = X.std().replace(0, 1).fillna(1).to_numpy()
    Z = np.c_[np.ones(len(X)), (X.to_numpy() - mu) / sd]
    y = np.asarray(y, dtype=float)
    pos = max(y.sum(), 1)
    sw = np.where(y == 1, len(y) / (2 * pos), len(y) / (2 * max(len(y) - pos, 1)))
    w = np.zeros(Z.shape[1])
    reg = np.full(Z.shape[1], l2)
    reg[0] = 0
    for _ in range(iters):
        p = _sig(Z @ w)
        grad = Z.T @ (sw * (p - y)) + reg * w
        H = (Z * (sw * p * (1 - p))[:, None]).T @ Z + np.diag(reg + 1e-6)
        step = np.linalg.solve(H, grad)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return {"features": list(X.columns), "mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist()}


def predict(model, X):
    X = X.reindex(columns=model["features"]).fillna(0.0)
    Z = (X.to_numpy() - np.array(model["mu"])) / np.array(model["sd"])
    return _sig(model["w"][0] + Z @ np.array(model["w"][1:]))


def reasons(model, X, lang="fr", k=3):
    X = X.reindex(columns=model["features"]).fillna(0.0)
    Z = (X.to_numpy() - np.array(model["mu"])) / np.array(model["sd"])
    contrib = Z * np.array(model["w"][1:])
    binary = np.array([("=" in f) or f in ("new_country", "new_merchant", "new_device", "foreign", "night", "weekend") for f in model["features"]])
    active = ~binary | (X.to_numpy() > 0.5)                  # a 0/1 feature is a reason only when it is present
    contrib = np.where(active, contrib, 0)
    out = []
    for row in contrib:
        idx = [i for i in np.argsort(-row)[:k] if row[i] > 0.15]
        out.append([_label(model["features"][i], lang) for i in idx])
    return out


def _label(f, lang):
    if "=" in f:
        c, v = f.split("=", 1)
        fr, en = {"channel": ("canal", "channel"), "entry_mode": ("mode de saisie", "entry mode"),
                  "transaction_type": ("type d'opération", "operation type")}.get(c, (c, c))
        return f"{en if lang == 'en' else fr} {v}"
    fr, en = LABELS.get(f, (f, f))
    return en if lang == "en" else fr


def train(tx, auth=None, version=1):
    """-> candidate model dict (with validation metrics) or {'error': ...}."""
    d = tx[tx["is_fraud"].notna()].sort_values("timestamp") if "is_fraud" in tx else None
    if d is None or d["is_fraud"].sum() < 30:
        return {"error": "not_enough_labels"}
    X = features(tx, auth).loc[d.index]
    y = d["is_fraud"].astype(int).to_numpy()
    cut = d["timestamp"].quantile(0.7)
    tr, te = (d["timestamp"] <= cut).to_numpy(), (d["timestamp"] > cut).to_numpy()
    if y[tr].sum() < 20 or y[te].sum() < 5:
        return {"error": "not_enough_labels_per_period"}
    model = fit(X[tr], y[tr])
    s = predict(model, X[te])
    model.update({"version": version, "status": "candidate", "trained_at": datetime.now().isoformat(timespec="seconds"),
                  "train_period": [str(d["timestamp"][tr].min())[:10], str(cut)[:10]],
                  "test_period": [str(cut)[:10], str(d["timestamp"][te].max())[:10]],
                  "n_train": int(tr.sum()), "frauds_train": int(y[tr].sum()), "n_test": int(te.sum()), "frauds_test": int(y[te].sum()),
                  "metrics": evaluate(y[te], s), "algorithm": "L2 logistic regression (numpy, balanced classes)"})
    if "risk_score" in d and d["risk_score"].notna().mean() > 0.9:
        rs = d.loc[te, "risk_score"].fillna(0).to_numpy(dtype=float) + np.random.default_rng(0).uniform(0, 1e-6, te.sum())
        model["baseline"] = {"name": "score actuel de la banque / bank's current score", "metrics": evaluate(y[te], rs)}
    return model


def behaviour_score(tx, auth=None):
    """Unsupervised 0..1 score of departure from the customer's own habits (labelled as such, never as a fraud probability)."""
    X = features(tx, auth)
    s = (0.40 * (X["z_amount"].clip(0, 5) / 5) + 0.15 * X["new_country"] + 0.10 * X["new_device"] + 0.08 * X["new_merchant"]
         + 0.07 * X["night"] + 0.10 * (X["count_24h"].clip(0, 6) / 6))
    if "sensitive_events_72h" in X:
        s += 0.10 * X["sensitive_events_72h"].clip(0, 1)
    return s.clip(0, 1), X
