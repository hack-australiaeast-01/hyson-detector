"""Data Readiness Report for a tenant's canonical data: quality, integrity, labels, and what the platform can safely activate."""
import numpy as np
import pandas as pd

import canonical as cn

FK = [("transactions.customer_id", "customers.customer_id"), ("transactions.card_id", "cards.card_id"),
      ("transactions.merchant_id", "merchants.merchant_id"), ("cards.customer_id", "customers.customer_id"),
      ("fraud_labels.transaction_id", "transactions.transaction_id"), ("cases.transaction_id", "transactions.transaction_id"),
      ("auth_events.customer_id", "transactions.customer_id")]
PK = {"transactions": "transaction_id", "customers": "customer_id", "cards": "card_id", "merchants": "merchant_id", "cases": "case_id",
      "fraud_labels": "transaction_id", "auth_events": "event_id"}


def _col(canon, ref):
    e, f = ref.split(".")
    df = canon.get(e)
    return None if df is None or f not in df else df[f]


def report(canon, trans_report, now=None):
    now = now or pd.Timestamp.now()
    issues, checks = [], {}

    def issue(level, fr, en):
        issues.append({"level": level, "fr": fr, "en": en})

    tx = canon.get("transactions")
    if tx is None or not {"transaction_id", "timestamp", "amount"} <= set(tx.columns):
        issue("blocker", "Aucune table d'opérations exploitable (identifiant, date et montant requis).",
              "No usable transactions table (id, timestamp and amount required).")
        return {"score": 0, "gate": "red", "issues": issues, "checks": checks, "entities": {e: len(d) for e, d in canon.items()}}

    # completeness of required fields per entity
    comp = {}
    for e, df in canon.items():
        for f, (_k, req, _d) in cn.ENTITIES.get(e, {}).items():
            if req:
                comp[f"{e}.{f}"] = float(df[f].notna().mean()) if f in df else 0.0
    checks["completeness"] = comp
    for k, v in comp.items():
        if v < 0.98:
            issue("warning" if v >= 0.9 else "blocker", f"{k} : {v:.1%} renseigné.", f"{k}: {v:.1%} filled.")

    # translation validity
    val = {k: r["valid"] / r["present"] for k, r in trans_report.items() if r["present"]}
    checks["validity"] = val
    for k, v in val.items():
        if v < 0.95:
            ex = list(trans_report[k]["untranslated"])[:4]
            issue("warning", f"{k} : {1 - v:.1%} de valeurs non traduites {ex}.", f"{k}: {1 - v:.1%} untranslated values {ex}.")

    # uniqueness
    dup = {}
    for e, pk in PK.items():
        df = canon.get(e)
        if df is not None and pk in df and e != "auth_events":
            dup[e] = int(df[pk].duplicated().sum())
    checks["duplicates"] = dup
    if dup.get("transactions", 0) > 0:
        rate = dup["transactions"] / len(tx)
        issue("blocker" if rate > 0.01 else "warning", f"{dup['transactions']} identifiants d'opération en double.",
              f"{dup['transactions']} duplicate transaction ids.")

    # timestamps
    ts = tx["timestamp"]
    bad_ts = float(ts.isna().mean())
    future = int((ts > now + pd.Timedelta(days=1)).sum())
    checks["timestamps"] = {"invalid_rate": bad_ts, "future": future, "min": str(ts.min())[:19], "max": str(ts.max())[:19],
                            "days": int((ts.max() - ts.min()).days) if ts.notna().any() else 0}
    if bad_ts > 0.005:
        issue("blocker" if bad_ts > 0.05 else "warning", f"{bad_ts:.1%} de dates illisibles.", f"{bad_ts:.1%} unreadable timestamps.")
    if future:
        issue("warning", f"{future} opérations datées dans le futur.", f"{future} transactions dated in the future.")

    # amounts and currency
    amt = tx["amount"]
    checks["amounts"] = {"negative": int((amt < 0).sum()), "zero": int((amt == 0).sum()),
                         "currencies": tx["currency"].value_counts().to_dict() if "currency" in tx else {},
                         "unconverted": int((amt.notna() & tx.get("amount_tnd", pd.Series(np.nan, index=tx.index)).isna()).sum())}
    if checks["amounts"]["unconverted"]:
        issue("warning", f"{checks['amounts']['unconverted']} montants sans taux de change connu.",
              f"{checks['amounts']['unconverted']} amounts with no known exchange rate.")
    if checks["amounts"]["negative"]:
        issue("warning", f"{checks['amounts']['negative']} montants négatifs (remboursements ?).",
              f"{checks['amounts']['negative']} negative amounts (refunds?).")

    # referential integrity
    ri = {}
    for a, b in FK:
        sa, sb = _col(canon, a), _col(canon, b)
        if sa is None or sb is None:
            continue
        vals = sa.dropna()
        ri[f"{a} → {b}"] = float(vals.isin(set(sb.dropna())).mean()) if len(vals) else 1.0
    checks["integrity"] = ri
    for k, v in ri.items():
        if v < 0.99:
            issue("warning" if v >= 0.9 else "blocker", f"Intégrité {k} : {v:.1%}.", f"Integrity {k}: {v:.1%}.")

    # labels
    lab = None
    if "is_fraud" in tx:
        y = tx["is_fraud"].dropna().astype(int)
        months = tx.loc[tx["is_fraud"].notna(), "timestamp"].dt.to_period("M").nunique()
        lab = {"labelled": int(len(y)), "positives": int(y.sum()), "rate": float(y.mean()) if len(y) else 0.0, "months": int(months)}
        fl = canon.get("fraud_labels")
        if fl is not None and "reported_at" in fl:
            m = fl.merge(tx[["transaction_id", "timestamp"]], on="transaction_id", how="inner")
            delay = (pd.to_datetime(m["reported_at"]) - m["timestamp"]).dt.days
            lab["report_delay_days_median"] = float(delay.median()) if len(delay) else None
        lab["trainable"] = lab["positives"] >= 30 and months >= 3
        if not lab["trainable"]:
            issue("warning", f"Étiquettes insuffisantes pour entraîner un modèle propre ({lab['positives']} fraudes sur {months} mois).",
                  f"Not enough labels to train a bank-specific model ({lab['positives']} frauds over {months} months).")
    else:
        issue("info", "Aucune étiquette de fraude : seuls les modules non supervisés et descriptifs sont activables.",
              "No fraud labels: only unsupervised and descriptive modules can be activated.")
    checks["labels"] = lab

    # score
    s_comp = np.mean(list(comp.values())) if comp else 0
    s_val = np.mean(list(val.values())) if val else 1
    s_dup = 1 - min(1, dup.get("transactions", 0) / max(len(tx), 1) * 20)
    s_ri = np.mean(list(ri.values())) if ri else 1
    s_ts = 1 - min(1, bad_ts * 10)
    score = round(100 * (0.30 * s_comp + 0.25 * s_val + 0.15 * s_dup + 0.15 * s_ri + 0.15 * s_ts))
    blockers = any(i["level"] == "blocker" for i in issues)
    gate = "red" if blockers or score < 65 else "green" if score >= 85 else "amber"
    return {"score": int(score), "gate": gate, "issues": issues, "checks": checks, "entities": {e: int(len(d)) for e, d in canon.items()}}
