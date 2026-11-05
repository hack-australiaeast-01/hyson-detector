"""Data access for the app: live Microsoft Fabric (default) with a local parquet fallback.

Live mode (brief §11, option A): T-SQL against the lh_fraud SQL analytics endpoint, authenticated with
Microsoft Entra (Azure CLI login, else browser). Small Gold tables are loaded once; customer history,
digital events and related cases are queried on demand with server-side filters (full history since 2025).
Analyst decisions are written back to OneLake (Files/app_feedback/decisions.csv) to close the feedback loop.

Local mode (option B / offline demo): the parquet files in app/data. Each successful live load refreshes
this snapshot, so the demo keeps working without network.
"""
import os
import struct
import threading
import time
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

APP_DIR = Path(__file__).parent
DATA = APP_DIR / "data"
load_dotenv(APP_DIR / ".env")

SQL_ENDPOINT = os.getenv("FABRIC_SQL_ENDPOINT", "")
SQL_DATABASE = os.getenv("FABRIC_DATABASE", "lh_fraud")
WORKSPACE_ID = os.getenv("FABRIC_WORKSPACE_ID", "")
LAKEHOUSE_ID = os.getenv("FABRIC_LAKEHOUSE_ID", "")
MODE = os.getenv("DATA_SOURCE", "auto").lower()          # auto | fabric | local
ODBC_DRIVER = os.getenv("ODBC_DRIVER", "")

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
for _k, _v in {   # model drivers shown on the performance page (names aligned with the Power BI report)
        "f_speed_kmh": "Vitesse de déplacement", "f_amount": "Montant", "merchant_category": "Catégorie marchande",
        "channel": "Canal", "f_secs_since_prev": "Temps depuis l'opération précédente", "f_new_merchant": "Nouveau commerçant",
        "transaction_type": "Type d'opération", "entry_mode": "Mode de saisie", "f_n_before": "Ancienneté (nb opérations)",
        "f_key_contactless_24h": "Sans contact sur 24 h", "f_is_foreign": "Opération à l'étranger",
        "merchant_type": "Type de commerçant", "f_same_country_7d": "Opérations dans ce pays (7 j)",
        "f_dist_prev_km": "Distance depuis l'opération précédente", "f_amount_z": "Écart au montant habituel (z)",
        "f_amount_over_limit": "Montant / plafond", "f_amount_ratio": "Montant / moyenne habituelle",
        "f_merchant_frauds_30d": "Commerçant lié à des fraudes (30 j)",
        "f_key_new_merchants_24h": "Nouveaux commerçants sur 24 h"}.items():
    FEATURE_FR.setdefault(_k, _v)
SCENARIO_EN = {"CARD_TESTING": "Card testing", "ACCOUNT_TAKEOVER": "Account takeover",
               "CARTE_CLONEE_ETRANGER": "Card cloned abroad", "SKIMMING_DAB": "ATM skimming",
               "CARTE_VOLEE_SANS_CONTACT": "Stolen card, contactless", "FRAUDE_EN_LIGNE_DISCRETE": "Discreet online fraud"}
FEATURE_EN = {"f_speed_kmh": "Travel speed", "f_amount": "Amount", "merchant_category": "Merchant category", "channel": "Channel",
              "f_secs_since_prev": "Time since previous operation", "f_new_merchant": "New merchant",
              "transaction_type": "Operation type", "entry_mode": "Entry mode", "f_n_before": "History length (nb ops)",
              "f_key_contactless_24h": "Contactless in 24 h", "f_is_foreign": "Operation abroad", "merchant_type": "Merchant type",
              "f_same_country_7d": "Ops in this country (7 d)", "f_dist_prev_km": "Distance from previous op",
              "f_amount_z": "Amount deviation (z)", "f_amount_over_limit": "Amount / limit", "f_amount_ratio": "Amount / usual average",
              "f_merchant_frauds_30d": "Merchant linked to frauds (30 d)", "f_night_share_before": "Habit of night operations",
              "f_key_new_merchants_24h": "New merchants in 24 h"}
SCENARIO_FR = {"CARD_TESTING": "Test de carte", "ACCOUNT_TAKEOVER": "Prise de contrôle de compte",
               "CARTE_CLONEE_ETRANGER": "Carte clonée à l'étranger", "SKIMMING_DAB": "Skimming DAB",
               "CARTE_VOLEE_SANS_CONTACT": "Carte volée sans contact", "FRAUDE_EN_LIGNE_DISCRETE": "Fraude en ligne discrète"}
RISK_ICON = {"ELEVE": "🔴", "MOYEN": "🟠", "FAIBLE": "🟢"}
FACTOR_CLARIFY = {
    "f_key_new_merchants_24h": "Nouveaux commerçants sur la carte dans les 24 h précédentes",
    "f_amount_over_limit": "Montant / plafond journalier de la carte (> 1 = au-dessus du plafond)",
    "f_amount_ratio": "Montant / moyenne habituelle (> 1 = au-dessus des habitudes)",
    "f_amount_over_max": "Montant / plus gros montant passé (> 1 = record)",
    "f_amount_over_income": "Montant / revenu mensuel",
    "f_payday": "Période de paie (25 → 3 du mois)",
}
TX_COLS = ["transaction_id", "timestamp", "period", "customer_id", "card_id", "merchant_id", "beneficiary_id",
           "device_id", "session_id", "transaction_type", "channel", "entry_mode", "merchant_category", "amount_tnd",
           "city", "country", "latitude", "longitude", "ip_country", "status", "decline_reason"]
EV_COLS = ["timestamp", "customer_id", "session_id", "event_type", "channel", "device_id", "ip_country",
           "auth_method", "status", "beneficiary_id"]
GOLD = ["gold_alert_queue", "gold_alert_explanations", "gold_model_metrics", "gold_model_leaderboard",
        "gold_model_recall_by_type", "gold_model_importance"]


def label(name):
    return FEATURE_FR.get(name, name)


def _clean(df):
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s) and getattr(s.dt, "tz", None) is not None:
            df[c] = s.dt.tz_localize(None)            # Fabric wrote Tunis local time tagged as UTC
        elif s.dtype == object:
            first = s.dropna().head(1)
            if len(first) and isinstance(first.iloc[0], Decimal):
                df[c] = pd.to_numeric(s, errors="coerce")
    return df


# ---------------------------------------------------------------- Fabric backend
class FabricSQL:
    def __init__(self):
        if not SQL_ENDPOINT:
            raise RuntimeError("FABRIC_SQL_ENDPOINT non configuré")
        import pyodbc
        from azure.identity import AzureCliCredential, ChainedTokenCredential, InteractiveBrowserCredential
        self._pyodbc = pyodbc
        self._cred = ChainedTokenCredential(AzureCliCredential(), InteractiveBrowserCredential())
        drivers = [d for d in pyodbc.drivers() if "SQL Server" in d and "ODBC Driver" in d]
        self.driver = ODBC_DRIVER or (sorted(drivers)[-1] if drivers else "ODBC Driver 18 for SQL Server")
        self._lock = threading.Lock()
        self._cn = None
        self._connect()

    def _connect(self):
        tok = self._cred.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
        attrs = {1256: struct.pack(f"<I{len(tok)}s", len(tok), tok)}   # SQL_COPT_SS_ACCESS_TOKEN
        cs = (f"Driver={{{self.driver}}};Server={SQL_ENDPOINT},1433;Database={SQL_DATABASE};"
              "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=45")
        self._cn = self._pyodbc.connect(cs, attrs_before=attrs)

    def query(self, sql, params=()):
        with self._lock:
            for attempt in (1, 2):
                try:
                    cur = self._cn.cursor()
                    cur.execute(sql, params)
                    cols = [c[0] for c in cur.description]
                    return _clean(pd.DataFrame.from_records(cur.fetchall(), columns=cols))
                except self._pyodbc.Error:
                    if attempt == 2:
                        raise
                    self._connect()                    # expired token / dropped connection


class Source:
    """Single access point used by tools.py and app.py."""

    def __init__(self):
        self.mode, self.error, self.sql = "local", None, None
        if MODE in ("auto", "fabric"):
            try:
                t0 = time.time()
                self.sql = FabricSQL()
                self.mode = "fabric"
                self.connect_s = round(time.time() - t0, 1)
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {str(exc)[:200]}"
                if MODE == "fabric":
                    raise
        self._gold = {}

    # ---------- small Gold tables
    def gold(self, name):
        if name not in self._gold:
            df = None
            if self.mode == "fabric":
                try:
                    df = self.sql.query(f"SELECT * FROM dbo.{name}")
                    DATA.mkdir(exist_ok=True)
                    df.to_parquet(DATA / f"{name}.parquet", index=False)   # refresh offline snapshot
                except Exception as exc:
                    self.error = f"{name}: {type(exc).__name__}: {str(exc)[:160]}"
            if df is None:
                path = DATA / f"{name}.parquet"
                df = _clean(pd.read_parquet(path)) if path.exists() else None
            self._gold[name] = df
        return self._gold[name]

    # ---------- transactions (labels never returned)
    def customer_tx(self, customer_id):
        if self.mode == "fabric":
            cols = ", ".join(TX_COLS)
            return self.sql.query(f"SELECT {cols} FROM dbo.silver_transactions WHERE customer_id = ? ORDER BY timestamp",
                                  (customer_id,))
        h = _local_history()
        return pd.DataFrame(columns=TX_COLS) if h is None else h[h.customer_id == customer_id].reset_index(drop=True)

    def tx_by_id(self, transaction_id):
        if self.mode == "fabric":
            df = self.sql.query(f"SELECT {', '.join(TX_COLS)} FROM dbo.silver_transactions WHERE transaction_id = ?",
                                (transaction_id,))
            return None if df.empty else df.iloc[0]
        h = _local_history()
        if h is not None:
            m = h[h.transaction_id == transaction_id]
            if not m.empty:
                return m.iloc[0]
        return None

    def related(self, key, value, start, end, exclude_customer):
        """Other customers' operations on the same merchant/device/beneficiary, with frauds already reported
        before the analysed transaction (fraud_reported_date < end: the only legitimate use of that column)."""
        if key not in ("merchant_id", "device_id", "beneficiary_id"):
            raise ValueError(key)
        if self.mode == "fabric":
            return self.sql.query(
                f"""SELECT transaction_id, timestamp, customer_id, card_id, amount_tnd, channel, city,
                           CASE WHEN is_fraud = 1 AND fraud_reported_date < CAST(? AS date) THEN 1 ELSE 0 END AS reported_fraud
                    FROM dbo.silver_transactions
                    WHERE {key} = ? AND timestamp >= ? AND timestamp < ? AND customer_id <> ?""",
                (end, value, start, end, exclude_customer))
        h = _local_history()
        if h is None:
            return pd.DataFrame()
        o = h[(h[key] == value) & (h.timestamp >= start) & (h.timestamp < end) & (h.customer_id != exclude_customer)]
        return o.assign(reported_fraud=0)

    def events(self, customer_id, start=None, end=None):
        if self.mode == "fabric":
            sql, params = f"SELECT {', '.join(EV_COLS)} FROM dbo.digital_events WHERE customer_id = ?", [customer_id]
            if start is not None:
                sql, params = sql + " AND timestamp >= ?", params + [start]
            if end is not None:
                sql, params = sql + " AND timestamp <= ?", params + [end]
            return self.sql.query(sql + " ORDER BY timestamp", tuple(params))
        ev = _local_events()
        if ev is None:
            return None
        t = ev[ev.customer_id == customer_id]
        if start is not None:
            t = t[t.timestamp >= start]
        if end is not None:
            t = t[t.timestamp <= end]
        return t

    def customers(self):
        if "customers" not in self._gold:
            df = None
            if self.mode == "fabric":
                try:
                    df = self.sql.query("SELECT * FROM dbo.customers")
                    df = df.drop(columns=[c for c in ["gender"] if c in df.columns])   # never used (fairness)
                    df.to_parquet(DATA / "customers.parquet", index=False)
                except Exception as exc:
                    self.error = f"customers: {type(exc).__name__}"
            if df is None and (DATA / "customers.parquet").exists():
                df = _clean(pd.read_parquet(DATA / "customers.parquet"))
            if df is not None:
                for col in ["monthly_income_tnd", "avg_monthly_balance_tnd"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
            self._gold["customers"] = df
        return self._gold["customers"]

    def push_feedback(self, csv_path):
        """Upload the decision journal to OneLake (Files/app_feedback) in the background."""
        if self.mode != "fabric" or not (WORKSPACE_ID and LAKEHOUSE_ID):
            return

        def _upload():
            try:
                from azure.storage.filedatalake import DataLakeServiceClient
                svc = DataLakeServiceClient("https://onelake.dfs.fabric.microsoft.com", credential=self.sql._cred)
                f = svc.get_file_system_client(WORKSPACE_ID).get_file_client(
                    f"{LAKEHOUSE_ID}/Files/app_feedback/decisions.csv")
                f.upload_data(Path(csv_path).read_bytes(), overwrite=True)
                self.feedback_synced = time.strftime("%H:%M:%S")
            except Exception as exc:
                self.error = f"feedback: {type(exc).__name__}: {str(exc)[:120]}"

        threading.Thread(target=_upload, daemon=True).start()

    def describe(self):
        if self.mode == "fabric":
            return f"Fabric live · {SQL_DATABASE} (SQL endpoint)"
        return "Fichiers locaux (parquet)" + (" · Fabric indisponible" if self.error else "")


@lru_cache(maxsize=None)
def _local_history():
    p = DATA / "customer_history.parquet"
    if not p.exists():
        return None
    h = _clean(pd.read_parquet(p))
    h = h.drop(columns=[c for c in ["is_fraud", "fraud_scenario", "fraud_reported_date"] if c in h.columns])
    return h.sort_values("timestamp").reset_index(drop=True)


@lru_cache(maxsize=None)
def _local_events():
    p = DATA / "digital_events.parquet"
    return _clean(pd.read_parquet(p)) if p.exists() else None


_source = None
_source_lock = threading.Lock()


def source():
    global _source
    with _source_lock:
        if _source is None:
            _source = Source()
        return _source


def reset():
    """Drop all caches (button "Rafraîchir depuis Fabric")."""
    global _source
    with _source_lock:
        _source = None
    for fn in (queue, explanations, metrics, leaderboard, recall_by_type, importance, customer_tx, tx_by_id, events):
        fn.cache_clear()


# ---------------------------------------------------------------- cached accessors used by the app and tools
@lru_cache(maxsize=None)
def queue():
    q = source().gold("gold_alert_queue").copy()
    q.loc[q.period == "test", ["is_fraud", "fraud_scenario"]] = None   # never expose test labels
    q["risk_icon"] = q.risk_level.map(RISK_ICON).fillna("⚪")
    q["date"] = q.timestamp.dt.date
    return q.sort_values(["period", "rank_in_period"]).reset_index(drop=True)


@lru_cache(maxsize=None)
def explanations():
    e = source().gold("gold_alert_explanations").copy()
    e["factor"] = e.factor.map(label)
    for feat, text in FACTOR_CLARIFY.items():      # unambiguous wording (avoids wrong readings by the LLM / analyst)
        e.loc[e.feature == feat, "factor"] = text
    return e


@lru_cache(maxsize=None)
def metrics():
    m = source().gold("gold_model_metrics")
    return dict(zip(m.metric, m.value))


@lru_cache(maxsize=None)
def leaderboard():
    return source().gold("gold_model_leaderboard")


@lru_cache(maxsize=None)
def recall_by_type():
    return source().gold("gold_model_recall_by_type")


@lru_cache(maxsize=None)
def importance():
    imp = source().gold("gold_model_importance").copy()
    imp["label"] = imp.feature.map(label)
    return imp


def customers():
    return source().customers()


@lru_cache(maxsize=512)
def customer_tx(customer_id):
    return source().customer_tx(customer_id)


@lru_cache(maxsize=4096)
def tx_by_id(transaction_id):
    return source().tx_by_id(transaction_id)


@lru_cache(maxsize=512)
def events(customer_id, start=None, end=None):
    return source().events(customer_id, start, end)


def related(key, value, start, end, exclude_customer):
    return source().related(key, value, start, end, exclude_customer)


def data_status():
    s = source()
    if s.mode == "fabric":
        return {"source": s.describe()}
    names = GOLD + ["customer_history", "customers", "digital_events"]
    return {n: (DATA / f"{n}.parquet").exists() for n in names}
