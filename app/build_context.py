"""Fit and test the personal-context weights on the real labelled data (Fabric), then write the small tables the app needs.

    cd app && python build_context.py
Design = 2025 (weights + thresholds), test = 2026-01 → 2026-07 (never used to fit). Only data before each operation is used.
Writes: context_weights.json, data/feat_ctx_daily.parquet, data/feat_ctx_profile.parquet, data/feat_ctx_eval.parquet, ../docs/CONTEXT_EVAL.md
"""
import layout
import json
import math
import sys
import time
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

import context
import data_access as da

DESIGN_END = pd.Timestamp("2026-01-01")
MONOTONE = [("visite_lieu", "oui", "non"), ("deja_ailleurs", "oui", "non"), ("preparation", "oui", "non"), ("sejour", "en_cours", "debut"),
            ("affluence", "pic", "normale"), ("profil", "frequent", "rare"), ("categorie", "connue", "nouvelle"), ("mode", "CHIP", "MAGSTRIPE"),
            ("absence", "plus_7j", "impossible")]
TEST_END = pd.Timestamp("2026-08-01")

SIGNALS = context.DATA / "feat_ctx_signals.parquet"


def compute():
    t0 = time.time()
    f = da.FabricSQL()
    tx = f.query(f"""SELECT t.transaction_id, t.customer_id, t.timestamp, t.channel, t.entry_mode, t.merchant_category, t.amount_tnd,
                           t.city, t.country, l.is_fraud
                    FROM {layout.fq('silver_transactions')} t LEFT JOIN {layout.fq('fraud_labels_train')} l ON l.transaction_id = t.transaction_id""")
    tx["timestamp"] = pd.to_datetime(tx.timestamp)
    for c in ("channel", "entry_mode", "merchant_category", "city", "country"):
        tx[c] = tx[c].astype("category")
    cust = f.query(f"SELECT customer_id, age, segment, home_city, monthly_income_tnd FROM {layout.fq('customers')}")
    legacy = set(f.query(f"SELECT DISTINCT transaction_id FROM {layout.fq('legacy_rule_alerts_train')}").transaction_id)
    model = f.query(f"SELECT transaction_id, score_model, CAST(is_alert AS INT) is_alert FROM {layout.fq('gold_scores')} WHERE period = 'valid'")
    ev = f.query(f"""SELECT customer_id, timestamp, status, ip_country, device_id FROM {layout.fq('digital_events')} WHERE event_type = 'CONNEXION'""")
    ev["timestamp"] = pd.to_datetime(ev.timestamp)
    print(f"pulled {len(tx):,} tx, {len(ev):,} logins in {time.time() - t0:.0f}s", flush=True)

    # known device = seen at least 24 h before; only foreign-IP logins are kept for the signal
    first_seen = ev.groupby(["customer_id", "device_id"]).timestamp.min().rename("first_seen").reset_index()
    ev = ev.merge(first_seen, on=["customer_id", "device_id"], how="left")
    ev["known_device"] = ev.timestamp - ev.first_seen >= timedelta(hours=24)
    ev_abroad = ev[ev.ip_country.notna() & (ev.ip_country != "TN")]

    home = dict(zip(cust.customer_id, cust.home_city))
    phys = tx[tx.channel.isin(context.PHYSICAL)].copy()
    phys["place"] = np.where(phys.country.astype(str) != "TN", phys.country.astype(str), phys.city.astype(str))
    phys["home"] = phys.customer_id.map(home)

    # population tables (distinct customers per place per day; trip share per segment x age band, 2025 only)
    daily = (phys.assign(date=phys.timestamp.dt.normalize()).groupby(["place", "date"], observed=True).customer_id.nunique()
             .rename("n").reset_index())
    daily = daily[daily.place != "nan"]
    daily.to_parquet(context.DATA / "feat_ctx_daily.parquet", index=False)
    c2 = cust.assign(tranche_age=cust.age.map(context._age_band))
    y25 = phys[(phys.timestamp < DESIGN_END) & ((phys.country.astype(str) != "TN") | (phys.city.astype(str) != phys.home))]
    trips = y25.groupby("place").customer_id.unique()
    rows = []
    for (seg, band), g in c2.groupby(["segment", "tranche_age"]):
        ids = set(g.customer_id)
        for place, who in trips.items():
            k = len(ids & set(who))
            if k:
                rows.append({"segment": seg, "tranche_age": band, "place": place, "share": k / len(ids), "n_customers": len(ids)})
    prof = pd.DataFrame(rows)
    prof.to_parquet(context.DATA / "feat_ctx_profile.parquet", index=False)

    # candidate operations: labelled physical abroad, and labelled physical in a city of Tunisia not visited for 180 days (not home)
    lab = phys[phys.is_fraud.notna() & (phys.timestamp < TEST_END)].copy()
    lab = lab.sort_values(["customer_id", "place", "timestamp"])
    prev_same = phys.sort_values(["customer_id", "place", "timestamp"]).groupby(["customer_id", "place"], observed=True).timestamp.shift()
    gap = (phys.sort_values(["customer_id", "place", "timestamp"]).timestamp - prev_same).dt.days
    phys.loc[gap.index, "gap_days"] = gap
    lab = lab.join(phys["gap_days"])
    abroad = lab[lab.country.astype(str) != "TN"]
    dom = lab[(lab.country.astype(str) == "TN") & (lab.city.astype(str) != lab.home) & lab.city.notna()
              & (lab.gap_days.isna() | (lab.gap_days > 180))]
    print(f"candidates: abroad {len(abroad):,} ({int(abroad.is_fraud.sum())} frauds) · unusual city {len(dom):,} ({int(dom.is_fraud.sum())} frauds)", flush=True)

    by_cust = {k: g.sort_values("timestamp").reset_index(drop=True) for k, g in tx.groupby("customer_id", observed=True)}
    ev_by = {k: g for k, g in ev_abroad.groupby("customer_id")}
    profiles = cust.set_index("customer_id").to_dict("index")
    out = []
    t1 = time.time()
    for r in pd.concat([abroad, dom]).itertuples():
        h = by_cust[r.customer_id]
        i = int(h.timestamp.searchsorted(r.timestamp, side="left"))
        p = dict(profiles.get(r.customer_id, {}), customer_id=r.customer_id)
        txd = {"timestamp": r.timestamp, "channel": r.channel, "entry_mode": r.entry_mode, "merchant_category": r.merchant_category,
               "amount_tnd": r.amount_tnd, "city": r.city, "country": r.country}
        scope, place, sig = context.signals(txd, h.iloc[:i], p, ev_by.get(r.customer_id), daily, prof)
        if scope:
            out.append({"transaction_id": r.transaction_id, "scope": scope, "timestamp": r.timestamp, "is_fraud": int(r.is_fraud), **sig})
    sig = pd.DataFrame(out)
    sig["legacy"] = sig.transaction_id.isin(legacy)
    sig.to_parquet(SIGNALS, index=False)
    model.to_parquet(context.DATA / "feat_ctx_model_valid.parquet", index=False)
    print(f"signals for {len(sig):,} operations in {time.time() - t1:.0f}s", flush=True)
    return sig, legacy, model


def fit(sig, legacy, model):
    t0 = time.time()

    weights, report = {}, []
    for scope, g in sig.groupby("scope"):
        des, test = g[g.timestamp < DESIGN_END], g[g.timestamp >= DESIGN_END]
        nf, nl = des.is_fraud.sum(), (1 - des.is_fraud).sum()
        lr = {}
        for col in [c for c in g.columns if c not in ("transaction_id", "scope", "timestamp", "is_fraud")]:
            vals = des[col].dropna().unique()
            k = len(vals)
            if k < 2:
                continue
            lr[col] = {str(v): round(math.log((((des[col] == v) & (des.is_fraud == 1)).sum() + 1) / (nf + k))
                                     - math.log((((des[col] == v) & (des.is_fraud == 0)).sum() + 1) / (nl + k)), 3) for v in vals}
        # business guardrails: one direction per signal (a reassuring fact can never add risk; if the data says otherwise the signal
        # is ignored), an amount never reassures, an out-of-pattern amount is at least x3 risk (policy: only 47 such cases here)
        ignored = []
        for sigk, good, bad in MONOTONE:
            m = lr.get(sigk)
            if m and good in m and bad in m and m[good] > m[bad]:
                lr[sigk] = {v: 0.0 for v in m}
                ignored.append(sigk)
        if "categorie" in lr and "nouvelle" in lr["categorie"]:      # only on shop payments: relative to "new kind of shop" (ATM effect is in canal)
            base = lr["categorie"]["nouvelle"]
            lr["categorie"] = {v: round(x - base, 3) for v, x in lr["categorie"].items()}
        if "montant" in lr:
            lr["montant"] = {v: max(x, 0.0) for v, x in lr["montant"].items()}
            lr["montant"]["hors_norme"] = max(lr["montant"].get("hors_norme", 0.0), round(math.log(3), 3))
        lr.setdefault("telephone", {})
        lr["telephone"].setdefault("sur_place", -1.2)
        lr["telephone"].setdefault("suspect", 1.2)
        w = {"prior": round(math.log(nf / nl), 3), "lr": lr, "n_design": int(len(des)), "frauds_design": int(nf), "ignored": ignored,
             "policy": ["montant ≥ 0, hors_norme ≥ ×3", "telephone ±1.2 (non mesuré : trop peu de connexions depuis l'étranger)",
                        "avis de voyage −2.5 (déclaratif)"]}

        def post(df):
            z = np.full(len(df), w["prior"])
            for col, m in lr.items():
                if col not in df:
                    continue
                z += df[col].astype(object).map(lambda v: m.get(str(v), 0.0) if pd.notna(v) else 0.0).astype(float).values
            return 1 / (1 + np.exp(-z))
        pd_ = post(des)
        # thresholds on the DESIGN year: "coherent" keeps ≤ 1 % fraud, "inconsistent" ≥ 50 % fraud
        order = np.argsort(pd_)
        cf = np.cumsum(des.is_fraud.values[order]) / np.arange(1, len(des) + 1)
        ok = np.where(cf <= 0.01)[0]
        w["cut_low"] = round(float(pd_[order][ok[-1]]) + 1e-9, 4) if len(ok) else 0.0
        desc = np.argsort(-pd_)
        cfh = np.cumsum(des.is_fraud.values[desc]) / np.arange(1, len(des) + 1)
        okh = np.where(cfh >= 0.5)[0]
        w["cut_high"] = round(float(pd_[desc][okh[-1]]), 4) if len(okh) else 0.99
        pt = post(test)
        test = test.assign(p=pt, band=np.where(pt < w["cut_low"], "coherent", np.where(pt >= w["cut_high"], "incoherent", "verifier")))
        w["bands"] = {b: {"n": int((test.band == b).sum()), "frauds": int(test[test.band == b].is_fraud.sum()),
                          "fraud_rate": round(float(test[test.band == b].is_fraud.mean()), 4) if (test.band == b).any() else None}
                      for b in ("coherent", "verifier", "incoherent")}
        w["test"] = {"n": int(len(test)), "frauds": int(test.is_fraud.sum()), "base_rate": round(float(test.is_fraud.mean()), 4),
                     "roc_auc": round(float(roc_auc_score(test.is_fraud, pt)), 3), "pr_auc": round(float(average_precision_score(test.is_fraud, pt)), 3)}
        t = test.assign(legacy=test.transaction_id.isin(legacy)).merge(model, on="transaction_id", how="left")
        fp_leg = t[(t.legacy) & (t.is_fraud == 0)]
        w["test"]["legacy_false_alerts"] = int(len(fp_leg))
        w["test"]["legacy_false_alerts_coherent"] = int((fp_leg.band == "coherent").sum())
        w["test"]["legacy_frauds"] = int(((t.legacy) & (t.is_fraud == 1)).sum())
        w["test"]["frauds_in_coherent"] = int(t[(t.band == "coherent") & (t.is_fraud == 1)].shape[0])
        v = t[t.is_alert.notna()]
        w["test"]["model_alerts_valid"] = int((v.is_alert == 1).sum())
        w["test"]["model_false_alerts_valid_coherent"] = int(((v.is_alert == 1) & (v.is_fraud == 0) & (v.band == "coherent")).sum())
        w["test"]["model_false_alerts_valid"] = int(((v.is_alert == 1) & (v.is_fraud == 0)).sum())
        weights[scope] = w
        sig.loc[test.index, "p"] = pt
        sig.loc[test.index, "band"] = test.band
        report.append((scope, w))
    weights["notice_lr"] = -2.5
    weights["domestic_note"] = ("Aucun paiement physique hors de la ville de résidence dans ces données synthétiques : "
                                "le moteur gère ce cas, ses poids seront mesurés sur les données réelles de la banque.")
    context.WEIGHTS_FILE.write_text(json.dumps(weights, ensure_ascii=False, indent=1), encoding="utf-8")
    sig.to_parquet(context.DATA / "feat_ctx_eval.parquet", index=False)
    for scope, w in report:
        print(f"\n== {scope}: design {w['n_design']:,} ({w['frauds_design']} frauds) · cuts {w['cut_low']} / {w['cut_high']}")
        print("  test 2026:", w["test"])
        print("  bands:", w["bands"])
        top = sorted(((k, v, lr) for k, m in w["lr"].items() for v, lr in m.items()), key=lambda x: x[2])
        print("  most reassuring:", top[:5], "\n  most worrying:", top[-5:])
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--refit" in sys.argv and SIGNALS.exists():          # reuse the signals computed from Fabric (no new pull)
        sig = pd.read_parquet(SIGNALS)
        fit(sig, set(sig.transaction_id[sig.legacy]), pd.read_parquet(context.DATA / "feat_ctx_model_valid.parquet"))
    else:
        fit(*compute())
