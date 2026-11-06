"""Build three simulated banks with deliberately different schemas, from the synthetic Hyson data (test fixtures for the universal
integration — never shown as a real bank's figures).

    cd app && python build_bank_fixtures.py
- Banque Atlas (SQLite database, French names, dd/mm/yyyy dates, amounts in TND, fraud reports in a separate table)
- Nordic Pay (CSV files, camelCase English, epoch-ms timestamps, EUR minor units, ISO-8583-like codes, auth logs, devices, merchants,
  card table, the bank's own rules score, investigation notes)
- Sahel Bank (one wide JSON-lines extract, ISO-3 countries, "1 234,500" amounts, numeric status codes, no labels, no customer table)
Everything is derived from real rows of the synthetic dataset (customers, cards, merchants, operations, logins, fraud reports,
legacy rule alerts), so every figure after integration can be reconciled with the source.
"""
import json
import sqlite3
import sys

import numpy as np
import pandas as pd

import data_access as da
import layout

OUT = da.DATA.parent / "samples" / "banks"
START, END = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-08-01")
EUR = 3.40


def pick(h, n, seed):
    """n customers, half of them with at least one reported fraud in the window."""
    w = h[(h.timestamp >= START) & (h.timestamp < END)]
    fr = sorted(w[w.reported_date.notna()].customer_id.unique())
    ok = sorted(set(w.customer_id.unique()) - set(fr))
    rng = np.random.default_rng(seed)
    return list(rng.choice(fr, n // 2, replace=False)) + list(rng.choice(ok, n - n // 2, replace=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    h = pd.read_parquet(da.DATA / "customer_history.parquet")
    h["timestamp"] = pd.to_datetime(h.timestamp)
    cust = pd.read_parquet(da.DATA / "customers.parquet")
    ev = pd.read_parquet(da.DATA / "digital_events.parquet")
    ev["timestamp"] = pd.to_datetime(ev.timestamp)
    f = da.FabricSQL()
    cards = f.query(f"SELECT card_id, customer_id, card_type, is_international, daily_limit_tnd FROM {layout.fq('cards')}")
    merch = f.query(f"SELECT merchant_id, category, mcc, city, country FROM {layout.fq('merchants')}")
    scen = f.query(f"SELECT transaction_id, fraud_scenario FROM {layout.fq('fraud_labels_train')} WHERE is_fraud = 1")
    rules = f.query(f"SELECT transaction_id, rules_triggered FROM {layout.fq('legacy_rule_alerts_train')}")
    rules["n_rules"] = rules.rules_triggered.astype(str).str.count(r"\|") + 1
    OUT.mkdir(parents=True, exist_ok=True)
    w = h[(h.timestamp >= START) & (h.timestamp < END)].copy()
    w["is_fraud"] = w.reported_date.notna().astype(int)
    for col in w.columns:
        if isinstance(w[col].dtype, pd.CategoricalDtype) or str(w[col].dtype).startswith("str"):
            w[col] = w[col].astype(object)

    # ---------------- Banque Atlas: SQLite, French
    ids = pick(h, 70, 1)
    a = w[w.customer_id.isin(ids)]
    db = OUT / "atlas.sqlite"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    pd.DataFrame({"ref_operation": a.transaction_id, "date_operation": a.timestamp.dt.strftime("%d/%m/%Y %H:%M"), "num_client": a.customer_id,
                  "num_carte": a.card_id, "montant_dt": a.amount_tnd.round(3), "canal": a.channel.map({"TPE": "TPE", "DAB": "GAB", "EN_LIGNE": "E-COMMERCE",
                  "MOBILE": "MOBILE", "WEB": "INTERNET"}), "nature": a.transaction_type.map({"ACHAT": "ACHAT", "RETRAIT": "RETRAIT", "VIREMENT": "VIREMENT",
                  "PAIEMENT_FACTURE": "FACTURE", "RECHARGE": "RECHARGE"}), "etat": a.status.map({"APPROUVEE": "ACCEPTEE", "REFUSEE": "REJETEE"}),
                  "ville": a.city, "pays": a.country, "code_commercant": a.merchant_id, "secteur": a.merchant_category}).to_sql("operations", con, index=False)
    c = cust[cust.customer_id.isin(ids)]
    pd.DataFrame({"num_client": c.customer_id, "age": c.age, "segment": c.segment, "ville": c.home_city, "gouvernorat": c.governorate,
                  "revenu_mensuel": c.monthly_income_tnd.round(0), "niveau_kyc": c.kyc_risk_level, "date_entree": c.customer_since,
                  "nom_complet": "masqué-" + c.customer_id.str[-4:]}).to_sql("clients", con, index=False)
    k = cards[cards.customer_id.isin(ids)]
    pd.DataFrame({"num_carte": k.card_id, "num_client": k.customer_id, "type_carte": k.card_type, "plafond_jour": k.daily_limit_tnd,
                  "cvv": "***"}).to_sql("cartes", con, index=False)
    fa = a[a.is_fraud == 1].merge(scen, on="transaction_id", how="left")
    pd.DataFrame({"ref_operation": fa.transaction_id, "date_signalement": fa.reported_date.astype(str), "typologie": fa.fraud_scenario}) \
        .to_sql("signalements_fraude", con, index=False)
    con.close()
    print(f"Atlas: {len(a):,} operations, {len(c)} clients, {len(k)} cards, {len(fa)} fraud reports -> {db.name}")

    # ---------------- Nordic Pay: CSV, camelCase, epoch ms, EUR cents
    ids = pick(h, 80, 2)
    b = w[w.customer_id.isin(ids)].merge(rules[["transaction_id", "n_rules"]], on="transaction_id", how="left")
    nd = OUT / "nordic"
    nd.mkdir(exist_ok=True)
    chan = {"TPE": "POS", "DAB": "ATM", "EN_LIGNE": "ECOM", "MOBILE": "APP", "WEB": "WEB"}
    mode = {"CHIP": "EMV", "SANS_CONTACT": "NFC", "MAGSTRIPE": "SWIPE", "ECOM_3DS": "3DS", "ECOM_SANS_3DS": "NO3DS", "APP_AUTH": "BIOMETRIC"}
    pd.DataFrame({"txnRef": b.transaction_id, "createdAtMs": b.timestamp.astype("datetime64[ms]").astype("int64"), "clientRef": b.customer_id,
                  "paymentCard": b.card_id, "amountMinor": (b.amount_tnd / EUR * 100).round(0).astype("Int64"), "ccy": "EUR",
                  "channelCode": b.channel.map(chan), "posEntryMode": b.entry_mode.map(mode), "txnKind": b.transaction_type.map(
                      {"ACHAT": "PURCHASE", "RETRAIT": "CASH_WITHDRAWAL", "VIREMENT": "TRANSFER", "PAIEMENT_FACTURE": "BILL_PAYMENT", "RECHARGE": "TOP_UP"}),
                  "responseCode": np.where(b.status == "REFUSEE", "05", "00"), "mid": b.merchant_id, "deviceRef": b.device_id,
                  "countryCode": b.country, "fraudFlag": b.is_fraud, "rulesScore": b.n_rules.fillna(0).astype(int)}).to_csv(nd / "txn.csv", index=False)
    c = cust[cust.customer_id.isin(ids)]
    pd.DataFrame({"clientRef": c.customer_id, "birthYear": 2026 - c.age, "tier": c.segment, "homeCity": c.home_city, "kycRating": c.kyc_risk_level,
                  "email": "masked@" + c.customer_id.str.lower() + ".example", "gender": "n/a"}).to_csv(nd / "customer.csv", index=False)
    k = cards[cards.customer_id.isin(ids)]
    pd.DataFrame({"paymentCard": k.card_id, "clientRef": k.customer_id, "product": k.card_type, "intl": k.is_international.astype(int)}) \
        .to_csv(nd / "card.csv", index=False)
    m = merch[merch.merchant_id.isin(b.merchant_id.dropna())]
    pd.DataFrame({"mid": m.merchant_id, "mccCode": m.mcc, "mccLabel": m.category, "city": m.city, "countryCode": m.country}).to_csv(nd / "merchant.csv", index=False)
    e = ev[ev.customer_id.isin(ids) & (ev.timestamp >= START) & (ev.timestamp < END)]
    pd.DataFrame({"logId": [f"L{i:07d}" for i in range(len(e))], "loggedAt": e.timestamp.dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "clientRef": e.customer_id,
                  "action": e.event_type.map({"CONNEXION": "LOGIN", "AJOUT_BENEFICIAIRE": "ADD_PAYEE", "AJOUT_APPAREIL": "ADD_DEVICE",
                                              "REINITIALISATION_MOT_DE_PASSE": "PASSWORD_RESET", "MODIFICATION_NUMERO_TELEPHONE": "PHONE_CHANGE"}),
                  "result": e.status.map({"SUCCES": "OK", "ECHEC": "FAIL"}), "deviceRef": e.device_id, "ipCountry": e.ip_country}).to_csv(nd / "auth_log.csv", index=False)
    fb = b[b.is_fraud == 1].merge(scen, on="transaction_id", how="left")
    pd.DataFrame({"caseId": [f"NP-{i:05d}" for i in range(len(fb))], "txnRef": fb.transaction_id, "openedAt": fb.reported_date.astype(str),
                  "outcome": "CONFIRMED_FRAUD", "analystNotes": "Customer disputed the operation; typology " + fb.fraud_scenario.fillna("unknown").str.lower()
                  + "; channel " + fb.channel.map(chan) + "; card blocked and reissued."}).to_csv(nd / "investigation.csv", index=False)
    print(f"Nordic: {len(b):,} txn, {len(c)} customers, {len(k)} cards, {len(m)} merchants, {len(e):,} auth logs, {len(fb)} cases")

    # ---------------- Sahel Bank: one wide JSON-lines extract, no labels
    ids = pick(h, 50, 3)
    s = w[w.customer_id.isin(ids)]
    iso3 = {"TN": "TUN", "FR": "FRA", "IT": "ITA", "DE": "DEU", "ES": "ESP", "SA": "SAU", "TR": "TUR", "AE": "ARE", "MA": "MAR", "GB": "GBR",
            "EG": "EGY", "DZ": "DZA", "LY": "LBY", "QA": "QAT", "BE": "BEL", "CA": "CAN", "CN": "CHN", "US": "USA", "RO": "ROU", "RU": "RUS"}
    rows = [{"id": r.transaction_id, "ts": r.timestamp.isoformat(), "client": r.customer_id, "carte": r.card_id,
             "montant": f"{r.amount_tnd:,.3f}".replace(",", " ").replace(".", ","), "devise": "TND",
             "type_canal": {"TPE": "POS", "DAB": "ATM", "EN_LIGNE": "WEB_CARD", "MOBILE": "MOBILE", "WEB": "NETBANKING"}[r.channel],
             "statut": 0 if r.status == "APPROUVEE" else 1, "pays_iso3": iso3.get(r.country, r.country), "ville": r.city,
             "categorie": r.merchant_category} for r in s.itertuples()]
    with open(OUT / "sahel_extract.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Sahel: {len(s):,} rows (no labels, no customer table) -> sahel_extract.jsonl")
    truth = {"atlas": {"transactions": int(len(a)), "frauds": int(a.is_fraud.sum()), "amount_tnd": round(float(a.amount_tnd.sum()), 3)},
             "nordic": {"transactions": int(len(b)), "frauds": int(b.is_fraud.sum()), "amount_tnd": round(float(b.amount_tnd.sum()), 3),
                        "amount_eur": round(float((b.amount_tnd / EUR * 100).round(0).sum()) / 100, 2), "eur_rate": EUR},
             "sahel": {"transactions": int(len(s)), "amount_tnd": round(float(s.amount_tnd.sum()), 3)}}
    (OUT / "truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
    print("truth:", truth)
