"""Build the behavioural memory (RAG corpus) from Fabric: one record per past case, two vectors per record.

    cd app && python build_memory.py
Corpus: every labelled fraud of 2025-01 → 2026-07 (with its report date), a sample of legitimate operations the current rules
flagged (look-alike false alarms), all model alerts of the validation and live periods (unlabelled → "suspected", never "confirmed").
Each record: a deterministic French summary (no names, no IDs, no gender) → text embedding (Azure OpenAI text-embedding-3-small,
256 dims) + a behavioural vector (standardised model features, target-encoded risks excluded). Writes data/memory.parquet.
"""
import layout
import os
import sys
import time

import numpy as np
import pandas as pd

import data_access as da

OUT = da.DATA / "memory.parquet"
EMB_MODEL = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
DIMS = 256
BEHAVIOUR = ["f_hour", "f_is_night", "f_amount_ratio", "f_amount_z", "f_amount_over_max", "f_amount_over_income", "f_amount_over_limit",
             "f_key_tx_10m", "f_key_tx_1h", "f_key_declines_1h", "f_key_small_tx_1h", "f_cust_tx_24h", "f_new_merchant", "f_new_device",
             "f_new_beneficiary", "f_new_ip_country", "f_new_country_phys", "f_is_foreign", "f_ip_foreign", "f_speed_kmh", "f_magstripe",
             "f_contactless", "f_ecom_no3ds", "f_chip_abroad", "f_unusual_night", "f_new_category", "f_key_contactless_24h",
             "f_key_new_merchants_24h", "f_round_amount", "f_login_fail_24h", "f_device_added_24h", "f_benef_added_24h",
             "f_pwd_reset_24h", "f_phone_change_24h", "f_mins_since_benef_added", "f_merchant_frauds_30d", "f_device_frauds_30d",
             "f_declined", "f_secs_since_prev"]


def _n(x, d=0):
    try:
        return 0 if pd.isna(x) else round(float(x), d)
    except (TypeError, ValueError):
        return 0


def summary(r):
    """Deterministic case summary: what happened, how it differs from habits, card / app / network context."""
    when = pd.Timestamp(r.timestamp)
    place = (r.city if isinstance(r.city, str) else "en ligne") + (f" ({r.country})" if isinstance(r.country, str) and r.country != "TN" else "")
    parts = [f"{r.transaction_type} {r.channel} {r.entry_mode} de {_n(r.amount_tnd)} TND, {_n(r.f_amount_ratio, 1)}× son montant moyen, "
             f"à {when.hour} h{' (nuit)' if r.f_is_night else ''}, {place}, {r.merchant_category if isinstance(r.merchant_category, str) else 'virement'}"]
    card = []
    if _n(r.f_key_declines_1h): card.append(f"{_n(r.f_key_declines_1h)} refus sur la carte en 1 h")
    if _n(r.f_key_tx_1h) >= 3: card.append(f"{_n(r.f_key_tx_1h)} opérations en 1 h")
    if _n(r.f_key_small_tx_1h): card.append(f"{_n(r.f_key_small_tx_1h)} micro-paiements en 1 h")
    if _n(r.f_key_new_merchants_24h) >= 2: card.append(f"{_n(r.f_key_new_merchants_24h)} nouveaux commerçants en 24 h")
    if _n(r.f_key_contactless_24h) >= 3: card.append(f"{_n(r.f_key_contactless_24h)} sans contact en 24 h")
    if r.f_new_merchant: card.append("commerçant jamais vu")
    if r.f_new_country_phys: card.append("premier paiement physique dans ce pays")
    if _n(r.f_speed_kmh) > 150: card.append(f"déplacement impossible ({_n(r.f_speed_kmh)} km/h)")
    if r.f_magstripe: card.append("piste magnétique")
    if r.f_ecom_no3ds: card.append("en ligne sans 3-D Secure")
    app = []
    if _n(r.f_login_fail_24h): app.append(f"{_n(r.f_login_fail_24h)} échecs de connexion en 24 h")
    if r.f_benef_added_24h: app.append(f"bénéficiaire ajouté {_n(r.f_mins_since_benef_added)} min avant")
    if r.f_device_added_24h or r.f_new_device: app.append("nouvel appareil")
    if r.f_pwd_reset_24h: app.append("mot de passe réinitialisé")
    if r.f_phone_change_24h: app.append("numéro de téléphone changé")
    if r.f_ip_foreign: app.append(f"connexion depuis l'étranger ({r.ip_country})")
    net = []
    if _n(r.f_merchant_frauds_30d): net.append(f"commerçant / DAB lié à {_n(r.f_merchant_frauds_30d)} fraude(s) signalée(s) en 30 j")
    if _n(r.f_device_frauds_30d): net.append(f"appareil lié à {_n(r.f_device_frauds_30d)} fraude(s)")
    out = parts[0] + "."
    if card: out += " Carte : " + ", ".join(card) + "."
    if app: out += " Application : " + ", ".join(app) + "."
    if net: out += " Réseau : " + ", ".join(net) + "."
    out += f" Client {r.segment}, risque KYC {r.kyc_risk_level}, carte {r.card_type}." + (f" Statut {r.status}" + (f" ({r.decline_reason})" if isinstance(r.decline_reason, str) else "") + "." if r.status == "REFUSEE" else "")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    f = da.FabricSQL()
    cols = ", ".join(["g.transaction_id", "g.timestamp", "g.period", "g.transaction_type", "g.channel", "g.entry_mode", "g.merchant_category",
                      "g.amount_tnd", "g.city", "g.country", "g.ip_country", "g.status", "g.decline_reason", "g.segment", "g.kyc_risk_level",
                      "g.card_type", "l.is_fraud", "l.fraud_scenario", "l.fraud_reported_date", "s.score_model", "s.risk_level",
                      "CAST(s.is_alert AS INT) AS is_alert"] + [f"g.{c}" for c in BEHAVIOUR])
    base = (f"SELECT {cols} FROM {layout.fq('gold_features')} g LEFT JOIN {layout.fq('fraud_labels_train')} l ON l.transaction_id = g.transaction_id "
            f"LEFT JOIN {layout.fq('gold_scores')} s ON s.transaction_id = g.transaction_id ")
    frauds = f.query(base + "WHERE l.is_fraud = 1")
    alerts = f.query(base + "WHERE s.is_alert = 1")
    legacy = f.query(base + f"WHERE l.is_fraud = 0 AND g.transaction_id IN (SELECT TOP 4000 transaction_id FROM {layout.fq('legacy_rule_alerts_train')} "
                            "ORDER BY CHECKSUM(transaction_id))")
    df = pd.concat([frauds, alerts, legacy]).drop_duplicates("transaction_id").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df.timestamp)
    df["fraud_reported_date"] = pd.to_datetime(df.fraud_reported_date)
    df["source"] = np.where(df.is_fraud == 1, "fraude_signalee", np.where(df.is_fraud == 0, "legitime_etiquete", "alerte_non_etiquetee"))
    print(f"corpus {len(df):,} cases ({int((df.is_fraud == 1).sum()):,} frauds, {int((df.is_fraud == 0).sum()):,} labelled legit, "
          f"{int(df.is_fraud.isna().sum()):,} unlabelled alerts) in {time.time() - t0:.0f}s", flush=True)
    df["summary"] = [summary(r) for r in df.itertuples()]

    X = df[BEHAVIOUR].astype(float).fillna(0.0).to_numpy(copy=True)
    X[:, BEHAVIOUR.index("f_secs_since_prev")] = np.log1p(np.clip(X[:, BEHAVIOUR.index("f_secs_since_prev")], 0, None))
    X[:, BEHAVIOUR.index("f_mins_since_benef_added")] = np.log1p(np.clip(X[:, BEHAVIOUR.index("f_mins_since_benef_added")], 0, None))
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = np.clip((X - mu) / sd, -5, 5)
    Z /= np.maximum(np.linalg.norm(Z, axis=1, keepdims=True), 1e-9)

    import copilot
    client = copilot._client()
    emb = []
    for i in range(0, len(df), 1000):
        for attempt in range(5):
            try:
                r = client.embeddings.create(model=EMB_MODEL, input=df.summary.iloc[i:i + 1000].tolist(), dimensions=DIMS)
                emb += [d.embedding for d in r.data]
                break
            except Exception as exc:
                print("retry", type(exc).__name__, flush=True)
                time.sleep(10 * (attempt + 1))
        print(f"  embedded {min(i + 1000, len(df)):,}/{len(df):,}", flush=True)
    E = np.asarray(emb, dtype=np.float32)
    E /= np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9)

    keep = ["transaction_id", "timestamp", "period", "transaction_type", "channel", "entry_mode", "merchant_category", "amount_tnd",
            "country", "status", "is_fraud", "fraud_scenario", "fraud_reported_date", "score_model", "risk_level", "is_alert", "source", "summary"]
    out = df[keep].copy()
    out["text_vec"] = list(E.astype(np.float16))
    out["beh_vec"] = list(Z.astype(np.float16))
    out.to_parquet(OUT, index=False, compression="zstd")
    print(f"wrote {OUT.name}: {len(out):,} records, {OUT.stat().st_size / 1e6:.1f} MB, {time.time() - t0:.0f}s")
