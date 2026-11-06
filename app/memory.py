"""Behavioural memory (RAG): retrieve past cases that look like this one — by meaning (text embedding of the case summary) and by
behaviour (standardised model features) — with their status AS KNOWN AT THE TIME of the case under review.

Rules (brief §3):
- only cases strictly BEFORE the reviewed operation are searched (no future information);
- a past fraud counts as "confirmed" only if the bank's fraud report came before the reviewed operation; a label 0 counts as
  "legitimate" only after 60 days without dispute; live-period alerts stay "suspected, not verified";
- AI conclusions are never knowledge: previous Judge outputs live in the case file (intel.cases), never in this corpus;
- exact matching (same card / ATM / device) and numbers stay with SQL and the model — this complements them, it never replaces them.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
FILE = DATA / "memory.parquet"
W_TEXT, W_BEH = 0.5, 0.5
STATUS = {"confirmed_fraud": ("Fraude confirmée (signalée par la banque)", "Confirmed fraud (reported to the bank)", "#D92D20"),
          "fraud_not_yet_known": ("Non confirmée à cette date", "Not yet confirmed at that date", "#C77700"),
          "legit": ("Légitime (aucune contestation)", "Legitimate (never disputed)", "#16A34A"),
          "too_recent": ("Trop récente pour conclure", "Too recent to conclude", "#64748B"),
          "suspected": ("Suspectée, non vérifiée", "Suspected, not verified", "#C77700")}


def ready():
    return FILE.exists()


@lru_cache(maxsize=1)
def _load():
    m = pd.read_parquet(FILE)
    m["timestamp"] = pd.to_datetime(m.timestamp)
    m["fraud_reported_date"] = pd.to_datetime(m.fraud_reported_date)
    T = np.vstack(m.pop("text_vec").values).astype(np.float32)
    B = np.vstack(m.pop("beh_vec").values).astype(np.float32)
    return m.reset_index(drop=True), T, B


def status_at(row, as_of):
    if row.is_fraud == 1:
        return "confirmed_fraud" if pd.notna(row.fraud_reported_date) and row.fraud_reported_date < as_of else "fraud_not_yet_known"
    if row.is_fraud == 0:
        return "legit" if (as_of - row.timestamp).days >= 60 else "too_recent"
    return "suspected"


def similar(tid, k=8, as_of=None, lang="fr"):
    """Top-k past cases similar to `tid` (must be in the corpus: alerts and labelled cases). Returns (cases DataFrame, stats) or (None, None)."""
    if not ready():
        return None, None
    m, T, B = _load()
    pos = np.where(m.transaction_id.values == tid)[0]
    if not len(pos):
        return None, None
    i = int(pos[0])
    ts = m.timestamp.iloc[i]
    as_of = pd.Timestamp(as_of) if as_of is not None else ts
    past = np.where((m.timestamp.values < np.datetime64(ts)) & (np.arange(len(m)) != i))[0]
    st = W_TEXT * (T[past] @ T[i]) + W_BEH * (B[past] @ B[i])
    top = past[np.argsort(-st)[:k]]
    sims = np.sort(st)[::-1][:k]
    out = m.iloc[top].copy()
    out["similarity"] = np.round(sims, 3)
    out["status"] = [status_at(r, as_of) for r in out.itertuples()]
    out["status_label"] = out.status.map(lambda s: STATUS[s][1 if lang == "en" else 0])
    out["scenario_known"] = np.where(out.status == "confirmed_fraud", out.fraud_scenario, None)
    known = out[out.status.isin(["confirmed_fraud", "legit"])]
    stats = {"k": len(out), "known": len(known), "confirmed_fraud": int((out.status == "confirmed_fraud").sum()),
             "legit": int((out.status == "legit").sum()), "suspected": int((out.status == "suspected").sum()),
             "undetermined": int(out.status.isin(["too_recent", "fraud_not_yet_known"]).sum()),
             "fraud_rate_known": float((known.status == "confirmed_fraud").mean()) if len(known) else None,
             "scenarios": out.scenario_known.dropna().value_counts().head(3).to_dict(), "mean_similarity": float(sims.mean()) if len(sims) else 0.0,
             "query_summary": m.summary.iloc[i]}
    return out, stats


def evidence_lines(cases, stats, lang="fr"):
    """Short lines for the agents (no IDs of customers, no raw rows)."""
    if cases is None:
        return []
    en = lang == "en"
    lines = [(f"Of the {stats['k']} most similar past cases, {stats['confirmed_fraud']} were confirmed frauds, {stats['legit']} legitimate, "
              f"{stats['suspected']} suspected and not verified, {stats['undetermined']} not yet determined at that date" if en else
              f"Sur les {stats['k']} cas passés les plus proches : {stats['confirmed_fraud']} fraudes confirmées, {stats['legit']} légitimes, "
              f"{stats['suspected']} suspectés non vérifiés, {stats['undetermined']} encore indéterminés à cette date")
             + (f" — typology: {', '.join(stats['scenarios'])}" if en and stats["scenarios"] else
                f" — typologie : {', '.join(stats['scenarios'])}" if stats["scenarios"] else "") + "."]
    for r in cases.head(4).itertuples():
        lines.append(f"[{r.status_label} · {pd.Timestamp(r.timestamp):%Y-%m-%d} · {'similarity' if en else 'similarité'} {r.similarity:.2f}] "
                     f"{r.summary}")
    return lines
