"""Data sources for the reporting engine: one canonical SQL surface over the Hyson star schema or any onboarded bank (tenant).

Every report query runs on the same views, whatever the bank:
    tx(transaction_id, ts, day, hour, dow, amount_tnd, channel, entry_mode, transaction_type, card_type, country, city,
       merchant_category, status, decline_reason, is_fraud, model_alert, rules_alert, score, risk_level, segment, age_band,
       region, customer_key, dq_status)
    auth(ts, day, customer_key, event_type, status, ip_country, auth_method)
is_fraud is NULL where the bank has no confirmed label yet (never 0 by default): confirmed and suspected fraud stay separate.
"""
import os
import tempfile
from pathlib import Path

import pandas as pd

import data_access as da

STAR = da.DATA / "star"
SENSITIVE_EVENTS = ("AJOUT_BENEFICIAIRE", "AJOUT_APPAREIL", "REINITIALISATION_MOT_DE_PASSE", "MODIFICATION_NUMERO_TELEPHONE")


class Source:
    """A read-only DuckDB connection exposing `tx` (and `auth` if available) + what is known about the data."""

    def __init__(self, sid, name, con, provenance, scope_dir, tenant=None):
        self.id, self.name, self.con, self.provenance, self.dir, self.tenant = sid, name, con, provenance, Path(scope_dir), tenant
        r = con.execute("SELECT MIN(day), MAX(day), MAX(CASE WHEN is_fraud IS NOT NULL THEN day END), "
                        "COUNT(*) FILTER (WHERE model_alert IS NOT NULL), COUNT(*) FILTER (WHERE rules_alert IS NOT NULL) FROM tx").fetchone()
        self.first_day, self.last_day, self.labelled_until = r[0], r[1], r[2]
        self.has_model_alerts, self.has_rules_alerts = r[3] > 0, r[4] > 0
        self.has_auth = bool(con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'auth'").fetchone()[0])

    def q(self, sql, params=None):
        cur = self.con.cursor()                       # one cursor per query: safe when several Streamlit sessions share the source
        try:
            return cur.execute(sql, params or []).df()
        finally:
            cur.close()

    def one(self, sql, params=None):
        cur = self.con.cursor()
        try:
            return cur.execute(sql, params or []).fetchone()
        finally:
            cur.close()

    @property
    def institution(self):
        return self.name


def _lock(con, allowed=None):
    for s in ([f"SET allowed_directories=['{allowed}']"] if allowed else []) + ["SET enable_external_access=false", "SET lock_configuration=true"]:
        try:
            con.execute(s)
        except Exception:
            pass


def hyson():
    """The Hyson bank: star schema exported from the Fabric lakehouse (mart.*), reconciled with Fabric by app/export_star.py."""
    import duckdb
    con = duckdb.connect()
    con.execute("SET threads=1; SET memory_limit='100MB'; SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{(Path(tempfile.gettempdir()) / 'hyson_duckdb').as_posix()}'")   # spill outside the app folder
    p = {t: (STAR / f"{t}.parquet").as_posix() for t in ("fact_transactions", "fact_digital_events", "dim_date", "dim_channel", "dim_card",
                                                          "dim_geo", "dim_merchant", "dim_client")}
    con.execute(f"""
        CREATE VIEW tx AS
        SELECT f.transaction_id, CAST(d.date AS TIMESTAMP) + f.heure * INTERVAL 1 HOUR AS ts, d.date AS day, f.heure AS hour,
               d.jour_semaine_num AS dow, f.montant_tnd AS amount_tnd, ch.canal AS channel, ch.mode_saisie AS entry_mode,
               ch.type_operation AS transaction_type, c.type_carte AS card_type, g.code_pays AS country, g.ville AS city,
               m.categorie AS merchant_category, f.statut AS status, f.motif_refus AS decline_reason,
               CAST(f.fraude_signalee AS INTEGER) AS is_fraud, f.alerte_modele AS model_alert,
               CASE WHEN d.periode_modele = 'flux_test' THEN NULL ELSE f.alerte_regles_actuelles END AS rules_alert,
               f.score_modele AS score, f.niveau_risque AS risk_level, cl.segment, cl.tranche_age AS age_band,
               cl.region_residence AS region, CAST(f.client_key AS VARCHAR) AS customer_key, f.dq_status
        FROM read_parquet('{p["fact_transactions"]}') f
        JOIN read_parquet('{p["dim_date"]}') d ON d.date_key = f.date_key
        LEFT JOIN read_parquet('{p["dim_channel"]}') ch ON ch.channel_key = f.channel_key
        LEFT JOIN read_parquet('{p["dim_card"]}') c ON c.card_key = CAST(f.card_key AS BIGINT)
        LEFT JOIN read_parquet('{p["dim_geo"]}') g ON g.geo_key = f.geo_key
        LEFT JOIN read_parquet('{p["dim_merchant"]}') m ON m.merchant_key = CAST(f.merchant_key AS BIGINT)
        LEFT JOIN read_parquet('{p["dim_client"]}') cl ON cl.client_key = f.client_key""")
    con.execute(f"""
        CREATE VIEW auth AS
        SELECT CAST(d.date AS TIMESTAMP) + e.heure * INTERVAL 1 HOUR AS ts, d.date AS day, CAST(e.client_key AS VARCHAR) AS customer_key,
               e.type_evenement AS event_type, e.statut AS status, e.pays_ip AS ip_country, e.methode_auth AS auth_method
        FROM read_parquet('{p["fact_digital_events"]}') e JOIN read_parquet('{p["dim_date"]}') d ON d.date_key = e.date_key""")
    _lock(con, STAR.as_posix())
    return Source("hyson", "Hyson Bank (démo)", con,
                  "Microsoft Fabric · lakehouse lh_fraud · schéma mart (étoile), instantané reconcilié (app/export_star.py)",
                  Path(os.getenv("HYSON_REPORTS_DIR") or (da.DATA / "reports")))


def tenant(tid):
    """An onboarded bank: its canonical (pseudonymised) data, its approved model / own score, its authentication logs."""
    import duckdb
    import numpy as np

    import tenants as tn
    t = tn.Tenant(tid)
    if t.config["status"] != "active":
        raise tn.TenantError("tenant is not active")
    can = t.canonical()
    tx = can["transactions"].copy()
    sc = t.score(tx)
    tx["score"] = sc["score"].to_numpy()
    kind = sc["score_kind"].iat[0] if len(sc) else None
    top = tx["score"] >= np.quantile(tx["score"], 0.99) if len(tx) else pd.Series(dtype=bool)
    tx["model_alert"] = top if kind == "model" else None
    if "risk_score" in tx and tx["risk_score"].notna().any():
        tx["rules_alert"] = tx["risk_score"] >= np.quantile(tx["risk_score"].fillna(0), 0.99)
    else:
        tx["rules_alert"] = None
    cards, cust, merch = can.get("cards"), can.get("customers"), can.get("merchants")
    if cards is not None and "card_type" in cards and "card_id" in tx:
        tx["card_type"] = tx["card_id"].map(cards.drop_duplicates("card_id").set_index("card_id")["card_type"])
    if cust is not None:
        ref = cust.drop_duplicates("customer_id").set_index("customer_id")
        for src, dst in (("segment", "segment"), ("region", "region")):
            if src in ref:
                tx[dst] = tx["customer_id"].map(ref[src])
        if "age" in ref:
            age = tx["customer_id"].map(ref["age"])
            tx["age_band"] = pd.cut(age, [0, 25, 35, 50, 65, 200], labels=["<25", "25-34", "35-49", "50-64", "65+"]).astype(str)
    if merch is not None and "merchant_category" not in tx and "category" in merch:
        tx["merchant_category"] = tx["merchant_id"].map(merch.drop_duplicates("merchant_id").set_index("merchant_id")["category"])
    cols = {"transaction_id": None, "timestamp": None, "amount_tnd": None, "channel": None, "entry_mode": None, "transaction_type": None,
            "card_type": None, "country": None, "city": None, "merchant_category": None, "status": None, "decline_reason": None,
            "is_fraud": None, "model_alert": None, "rules_alert": None, "score": None, "segment": None, "age_band": None, "region": None,
            "customer_id": None}
    for c in cols:
        if c not in tx:
            tx[c] = None
    tx = tx[list(cols)]
    tx["is_fraud"] = tx["is_fraud"].astype("Int64") if tx["is_fraud"].notna().any() else pd.Series([None] * len(tx), dtype="Int64")
    con = duckdb.connect()
    con.register("tx_raw", tx)
    con.execute("""CREATE TABLE tx AS SELECT transaction_id, CAST(timestamp AS TIMESTAMP) AS ts, CAST(timestamp AS DATE) AS day,
                   HOUR(CAST(timestamp AS TIMESTAMP)) AS hour, ISODOW(CAST(timestamp AS TIMESTAMP)) AS dow, amount_tnd, channel, entry_mode,
                   transaction_type, CAST(card_type AS VARCHAR) AS card_type, country, city, CAST(merchant_category AS VARCHAR) AS merchant_category,
                   status, CAST(decline_reason AS VARCHAR) AS decline_reason, CAST(is_fraud AS INTEGER) AS is_fraud,
                   CAST(model_alert AS BOOLEAN) AS model_alert, CAST(rules_alert AS BOOLEAN) AS rules_alert, score,
                   CAST(NULL AS VARCHAR) AS risk_level, CAST(segment AS VARCHAR) AS segment, CAST(age_band AS VARCHAR) AS age_band,
                   CAST(region AS VARCHAR) AS region, customer_id AS customer_key, 'OK' AS dq_status FROM tx_raw""")
    con.unregister("tx_raw")
    au = can.get("auth_events")
    if au is not None and len(au):
        a = au.copy()
        for c in ("status", "ip_country", "device_id"):
            if c not in a:
                a[c] = None
        con.register("auth_raw", a)
        con.execute("""CREATE TABLE auth AS SELECT CAST(timestamp AS TIMESTAMP) AS ts, CAST(timestamp AS DATE) AS day, customer_id AS customer_key,
                       event_type, status, ip_country, CAST(NULL AS VARCHAR) AS auth_method FROM auth_raw""")
        con.unregister("auth_raw")
    _lock(con)
    return Source(tid, t.config["name"], con, f"Données canoniques du tenant « {tid} » (correspondance v{t.config['activated']['mapping_version']},"
                  f" identifiants pseudonymisés)", t.dir / "reports", tenant=t)


def available():
    """[(id, label)] of sources a report can be built on: Hyson + every active tenant."""
    out = [("hyson", "Hyson Bank (démo) · Fabric")] if (STAR / "fact_transactions.parquet").exists() else []
    try:
        import tenants as tn
        for tid in tn.list_tenants():
            cfg = tn.Tenant(tid).config
            if cfg["status"] == "active":
                out.append((tid, f"{cfg['name']} · tenant"))
    except Exception:
        pass
    return out


_CACHE = {}


def get(sid):
    """Cached per process; a tenant source is rebuilt when its data changes (mapping version / model / file mtime)."""
    key = sid
    if sid != "hyson":
        import tenants as tn
        t = tn.Tenant(sid)
        p = t.dir / "canonical" / "transactions.parquet"
        key = (sid, t.config.get("mapping_version"), t.config.get("model"), os.path.getmtime(p) if p.exists() else 0)
    if key not in _CACHE:
        _CACHE[key] = hyson() if sid == "hyson" else tenant(sid)
    return _CACHE[key]
