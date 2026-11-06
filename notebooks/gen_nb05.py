"""Generates notebooks/05_quality_star.ipynb (Fabric, PySpark): row-by-row data quality + star schema.

Run:  python notebooks/gen_nb05.py
Reads only the raw (bronze) tables; never modifies silver_transactions / gold_* used by the scoring (frozen for the pitch).
"""
import json
from pathlib import Path

CELLS = []


def md(s):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": s.strip("\n").splitlines(keepends=True)})


def code(s):
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                  "source": s.strip("\n").splitlines(keepends=True)})


code('''
%%configure -f
{"defaultLakehouse": {"name": "lh_fraud"}}
''')

md('''
# 05 · Data quality (row by row) and star schema

**Bronze** = the raw tables loaded by the copy job `cj_bronze_load` (transactions_train / _test, customers, cards, merchants,
digital_events). This notebook:

1. logs the bronze load (rows, columns, schema fingerprint) in `bronze_ingestion_log`;
2. checks **every row** of every bronze table against documented rules (`dq_rules`): each failure is one row of `dq_issues`
   (table, record, rule, severity, column, value, message); each record gets a status in `dq_row_status`
   (`OK` / `WARNING` / `REJECTED`); rejected rows go to `quarantine_<table>`; `dq_summary` gives the rate per rule;
3. builds the **star schema** for analysis in natural language: `dim_date`, `dim_heure`, `dim_geo`, `dim_client`,
   `dim_merchant`, `dim_channel`, `dim_card`, `fact_transactions` (+ alert and score of the model) and
   `fact_digital_events`. Only rows that pass the ERROR rules enter the facts.

It never rewrites `silver_transactions` / `gold_*` (the scoring is frozen for the pitch).
''')

code('''
import hashlib, json
from datetime import datetime, date
from pyspark.sql import functions as F, Window as W, types as T

RUN_TS = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
DATA_START, DATA_END = "2025-01-01 00:00:00", "2026-09-30 23:59:59"
GOVERNORATES = ["Tunis", "Ariana", "Ben Arous", "Manouba", "Nabeul", "Zaghouan", "Bizerte", "Beja", "Jendouba", "Kef",
                "Siliana", "Sousse", "Monastir", "Mahdia", "Sfax", "Kairouan", "Kasserine", "Sidi Bouzid", "Gabes",
                "Medenine", "Tataouine", "Gafsa", "Tozeur", "Kebili"]
REGION = {"Tunis": "Grand Tunis", "Ariana": "Grand Tunis", "Ben Arous": "Grand Tunis", "Manouba": "Grand Tunis",
          "Nabeul": "Nord-Est", "Zaghouan": "Nord-Est", "Bizerte": "Nord-Est",
          "Beja": "Nord-Ouest", "Jendouba": "Nord-Ouest", "Kef": "Nord-Ouest", "Siliana": "Nord-Ouest",
          "Sousse": "Centre-Est", "Monastir": "Centre-Est", "Mahdia": "Centre-Est", "Sfax": "Centre-Est",
          "Kairouan": "Centre-Ouest", "Kasserine": "Centre-Ouest", "Sidi Bouzid": "Centre-Ouest",
          "Gabes": "Sud-Est", "Medenine": "Sud-Est", "Tataouine": "Sud-Est",
          "Gafsa": "Sud-Ouest", "Tozeur": "Sud-Ouest", "Kebili": "Sud-Ouest"}
COUNTRY = {"TN": "Tunisie", "FR": "France", "IT": "Italie", "SA": "Arabie saoudite", "TR": "Turquie", "DE": "Allemagne",
           "ES": "Espagne", "AE": "Émirats arabes unis", "MA": "Maroc", "GB": "Royaume-Uni", "EG": "Égypte", "QA": "Qatar",
           "DZ": "Algérie", "RO": "Roumanie", "RU": "Russie", "ID": "Indonésie", "CN": "Chine", "US": "États-Unis",
           "BE": "Belgique", "CH": "Suisse", "CA": "Canada", "NL": "Pays-Bas", "LY": "Libye", "JO": "Jordanie",
           "LB": "Liban", "MY": "Malaisie", "TH": "Thaïlande", "PT": "Portugal", "GR": "Grèce", "SE": "Suède"}
DOMAINS = {
    "transaction_type": ["ACHAT", "RETRAIT", "VIREMENT", "RECHARGE", "PAIEMENT_FACTURE"],
    "channel": ["TPE", "EN_LIGNE", "DAB", "MOBILE", "WEB"],
    "entry_mode": ["CHIP", "SANS_CONTACT", "APP_AUTH", "ECOM_3DS", "ECOM_SANS_3DS", "MAGSTRIPE"],
    "status": ["APPROUVEE", "REFUSEE"],
    "decline_reason": ["SOLDE_INSUFFISANT", "PLAFOND_DEPASSE", "CODE_PIN_ERRONE", "DATE_EXPIRATION_INVALIDE",
                       "CVV_INVALIDE", "CARTE_NON_INTERNATIONALE"],
    "segment": ["Particulier", "Retraite", "Etudiant", "Professionnel", "Premium"],
    "kyc_risk_level": ["Faible", "Moyen", "Eleve"],
    "event_type": ["CONNEXION", "AJOUT_BENEFICIAIRE", "AJOUT_APPAREIL", "REINITIALISATION_MOT_DE_PASSE",
                   "MODIFICATION_NUMERO_TELEPHONE"],
    "event_status": ["SUCCES", "ECHEC"],
}
TN_BBOX = (30.0, 37.6, 7.4, 11.7)   # lat min/max, lon min/max

tx = (spark.table("transactions_train").withColumn("split", F.lit("train"))
      .unionByName(spark.table("transactions_test").withColumn("split", F.lit("test"))))
bronze = {"transactions": tx, "customers": spark.table("customers"), "cards": spark.table("cards"),
          "merchants": spark.table("merchants"), "digital_events": spark.table("digital_events")}
KEYS = {"transactions": "transaction_id", "customers": "customer_id", "cards": "card_id",
        "merchants": "merchant_id", "digital_events": "event_id"}
''')

md('## 1 · Bronze ingestion log')
code('''
log = []
for name, df in bronze.items():
    schema = ",".join(f"{f.name}:{f.dataType.simpleString()}" for f in df.schema.fields)
    log.append((RUN_TS, name, df.count(), len(df.columns), hashlib.sha256(schema.encode()).hexdigest()[:16], schema))
spark.createDataFrame(log, "run_ts string, table_name string, rows long, columns int, schema_fingerprint string, schema string") \\
     .write.mode("append").format("delta").saveAsTable("bronze_ingestion_log")
display(spark.table("bronze_ingestion_log").orderBy(F.desc("run_ts")).limit(10))
''')

md('''
## 2 · Row-by-row validation rules

Severity **ERROR** = the row cannot be trusted (quarantined, kept out of the facts). **WARNING** = kept, flagged for review.
''')
code('''
def dup(df, key):
    return F.count(F.lit(1)).over(W.partitionBy(key)) > 1

def isin(c, values):
    return F.col(c).isNotNull() & ~F.col(c).isin(values)

cust_ids = bronze["customers"].select(F.col("customer_id").alias("_c")).distinct()
card_ref = bronze["cards"].select(F.col("card_id").alias("_k"), F.col("customer_id").alias("_kc"),
                                  F.to_date("issue_date").alias("_ki"), F.to_date("expiry_date").alias("_ke"))
merch_ids = bronze["merchants"].select(F.col("merchant_id").alias("_m")).distinct()

t = (bronze["transactions"]
     .withColumn("_ts", F.to_timestamp("timestamp"))
     .withColumn("_dup", dup(None, "transaction_id"))
     .join(cust_ids, F.col("customer_id") == F.col("_c"), "left")
     .join(card_ref, F.col("card_id") == F.col("_k"), "left")
     .join(merch_ids, F.col("merchant_id") == F.col("_m"), "left"))
lat_out = (F.col("latitude") < TN_BBOX[0]) | (F.col("latitude") > TN_BBOX[1]) | (F.col("longitude") < TN_BBOX[2]) | (F.col("longitude") > TN_BBOX[3])
RULES = {"transactions": [
    ("T01", "ERROR", "transaction_id", F.col("transaction_id").isNull() | F.col("_dup"), "identifiant manquant ou en double"),
    ("T02", "ERROR", "*", F.col("timestamp").isNull() | F.col("customer_id").isNull() | F.col("amount_tnd").isNull()
        | F.col("transaction_type").isNull() | F.col("channel").isNull() | F.col("status").isNull(), "champ obligatoire manquant"),
    ("T03", "ERROR", "amount_tnd", F.col("amount_tnd") <= 0, "montant nul ou négatif"),
    ("T04", "WARNING", "amount_tnd", F.col("amount_tnd") > 50000, "montant extrême (> 50 000 TND)"),
    ("T05", "ERROR", "timestamp", F.col("_ts").isNull() | (F.col("_ts") < F.lit(DATA_START)) | (F.col("_ts") > F.lit(DATA_END)),
        "date illisible ou hors période"),
    ("T06", "ERROR", "codes", isin("transaction_type", DOMAINS["transaction_type"]) | isin("channel", DOMAINS["channel"])
        | isin("entry_mode", DOMAINS["entry_mode"]) | isin("status", DOMAINS["status"]) | isin("decline_reason", DOMAINS["decline_reason"]),
        "code inconnu (type, canal, mode de saisie, statut, motif)"),
    ("T07", "ERROR", "customer_id", F.col("customer_id").isNotNull() & F.col("_c").isNull(), "client inconnu"),
    ("T08", "ERROR", "card_id", F.col("card_id").isNotNull() & F.col("_k").isNull(), "carte inconnue"),
    ("T09", "ERROR", "merchant_id", F.col("merchant_id").isNotNull() & F.col("_m").isNull(), "commerçant inconnu"),
    ("T10", "ERROR", "card_id", F.col("_k").isNotNull() & (F.col("_kc") != F.col("customer_id")), "carte d'un autre client"),
    ("T11", "WARNING", "card_id", F.col("_k").isNotNull() & ((F.to_date("_ts") > F.col("_ke")) | (F.to_date("_ts") < F.col("_ki"))),
        "carte expirée ou pas encore émise à la date de l'opération"),
    ("T12", "ERROR", "status", ((F.col("status") == "REFUSEE") & F.col("decline_reason").isNull())
        | ((F.col("status") == "APPROUVEE") & F.col("decline_reason").isNotNull()), "statut et motif de refus incohérents"),
    ("T13", "WARNING", "channel", ((F.col("transaction_type") == "RETRAIT") != (F.col("channel") == "DAB"))
        | ((F.col("transaction_type") == "VIREMENT") & ~F.col("channel").isin("MOBILE", "WEB")), "type et canal incohérents"),
    ("T14", "WARNING", "entry_mode", (F.col("entry_mode").startswith("ECOM") & (F.col("channel") != "EN_LIGNE"))
        | ((F.col("entry_mode") == "APP_AUTH") & ~F.col("channel").isin("MOBILE", "WEB"))
        | (F.col("entry_mode").isin("CHIP", "SANS_CONTACT", "MAGSTRIPE") & ~F.col("channel").isin("TPE", "DAB")),
        "mode de saisie et canal incohérents"),
    ("T15", "WARNING", "city", F.col("channel").isin("TPE", "DAB") & (F.col("city").isNull() | F.col("latitude").isNull()),
        "opération physique sans lieu"),
    ("T16", "WARNING", "original_currency", ((F.col("country") == "TN") & (F.col("original_currency") != "TND"))
        | ((F.col("country") != "TN") & (F.col("original_currency") == "TND")), "devise incohérente avec le pays"),
    ("T17", "WARNING", "latitude", (F.col("country") == "TN") & F.col("latitude").isNotNull() & lat_out, "coordonnées hors de Tunisie"),
]}

c = bronze["customers"].withColumn("_dup", dup(None, "customer_id"))
RULES["customers"] = [
    ("C01", "ERROR", "customer_id", F.col("customer_id").isNull() | F.col("_dup"), "identifiant manquant ou en double"),
    ("C02", "ERROR", "age", F.col("age").isNull() | (F.col("age") < 18) | (F.col("age") > 105), "âge manquant ou impossible"),
    ("C03", "ERROR", "monthly_income_tnd", F.col("monthly_income_tnd").isNull() | (F.col("monthly_income_tnd") <= 0), "revenu manquant ou négatif"),
    ("C04", "WARNING", "segment", isin("segment", DOMAINS["segment"]) | isin("kyc_risk_level", DOMAINS["kyc_risk_level"]), "segment ou niveau KYC inconnu"),
    ("C05", "ERROR", "governorate", F.col("governorate").isNull() | ~F.col("governorate").isin(GOVERNORATES), "gouvernorat inconnu"),
    ("C06", "WARNING", "customer_since", F.to_date("customer_since") > F.lit(DATA_END[:10]), "client depuis une date future"),
    ("C07", "WARNING", "segment", (F.col("segment") == "Retraite") & (F.col("age") < 45), "retraité de moins de 45 ans"),
    ("C08", "WARNING", "segment", (F.col("segment") == "Etudiant") & (F.col("age") > 35), "étudiant de plus de 35 ans"),
]
k = bronze["cards"].withColumn("_dup", dup(None, "card_id")).join(cust_ids, F.col("customer_id") == F.col("_c"), "left")
RULES["cards"] = [
    ("K01", "ERROR", "card_id", F.col("card_id").isNull() | F.col("_dup"), "identifiant manquant ou en double"),
    ("K02", "ERROR", "customer_id", F.col("_c").isNull(), "carte d'un client inconnu"),
    ("K03", "ERROR", "expiry_date", F.to_date("expiry_date") <= F.to_date("issue_date"), "expiration avant émission"),
    ("K04", "WARNING", "daily_limit_tnd", (F.col("daily_limit_tnd") <= 0) | (F.col("atm_daily_limit_tnd") <= 0), "plafond nul ou négatif"),
]
m = bronze["merchants"].withColumn("_dup", dup(None, "merchant_id"))
RULES["merchants"] = [
    ("M01", "ERROR", "merchant_id", F.col("merchant_id").isNull() | F.col("_dup"), "identifiant manquant ou en double"),
    ("M02", "WARNING", "category", F.col("category").isNull() | F.col("mcc").isNull(), "catégorie ou MCC manquant"),
    ("M03", "WARNING", "latitude", (F.col("country") == "TN") & F.col("latitude").isNotNull() & lat_out, "coordonnées hors de Tunisie"),
]
e = (bronze["digital_events"].withColumn("_dup", dup(None, "event_id")).withColumn("_ts", F.to_timestamp("timestamp"))
     .join(cust_ids, F.col("customer_id") == F.col("_c"), "left"))
RULES["digital_events"] = [
    ("E01", "ERROR", "event_id", F.col("event_id").isNull() | F.col("_dup"), "identifiant manquant ou en double"),
    ("E02", "ERROR", "customer_id", F.col("_c").isNull(), "client inconnu"),
    ("E03", "ERROR", "timestamp", F.col("_ts").isNull() | (F.col("_ts") < F.lit(DATA_START)) | (F.col("_ts") > F.lit(DATA_END)), "date illisible ou hors période"),
    ("E04", "WARNING", "event_type", isin("event_type", DOMAINS["event_type"]) | isin("status", DOMAINS["event_status"]), "type ou statut inconnu"),
]
CHECKED = {"transactions": t, "customers": c, "cards": k, "merchants": m, "digital_events": e}
spark.createDataFrame([(tb, r, s, col, msg) for tb, rs in RULES.items() for r, s, col, _, msg in rs],
                      "table_name string, rule_id string, severity string, column_name string, description string") \\
     .write.mode("overwrite").format("delta").saveAsTable("dq_rules")
''')

md('## 3 · Run every rule on every row → issues, row status, quarantine, summary')
code('''
issues, statuses, summary = None, {}, []
for tb, df in CHECKED.items():
    key = KEYS[tb]
    df = df.cache()
    n = df.count()
    flags = [F.when(F.coalesce(cond, F.lit(False)), F.lit(f"{rid}|{sev}")) for rid, sev, _, cond, _ in RULES[tb]]
    flagged = df.select(F.col(key).cast("string").alias("record_id"), F.array_compact(F.array(*flags)).alias("hits"))
    st = (flagged.withColumn("n_err", F.size(F.filter("hits", lambda h: h.endswith("ERROR"))))
                 .withColumn("n_warn", F.size(F.filter("hits", lambda h: h.endswith("WARNING"))))
                 .select(F.lit(tb).alias("table_name"), "record_id",
                         F.when(F.col("n_err") > 0, "REJECTED").when(F.col("n_warn") > 0, "WARNING").otherwise("OK").alias("dq_status"),
                         F.concat_ws(",", F.transform("hits", lambda h: F.split(h, "\\\\|")[0])).alias("dq_rules")))
    statuses[tb] = st
    for rid, sev, col, cond, msg in RULES[tb]:
        bad = df.filter(F.coalesce(cond, F.lit(False)))
        val = F.col(col).cast("string") if col in df.columns else F.lit(None).cast("string")
        part = bad.select(F.lit(tb).alias("table_name"), F.col(key).cast("string").alias("record_id"), F.lit(rid).alias("rule_id"),
                          F.lit(sev).alias("severity"), F.lit(col).alias("column_name"), val.alias("value"), F.lit(msg).alias("message"))
        issues = part if issues is None else issues.unionByName(part)
        summary.append((RUN_TS, tb, rid, sev, msg, n, bad.count()))
issues.withColumn("run_ts", F.lit(RUN_TS)).write.mode("overwrite").format("delta").option("overwriteSchema", "true").saveAsTable("dq_issues")
row_status = None
for st in statuses.values():
    row_status = st if row_status is None else row_status.unionByName(st)
row_status.write.mode("overwrite").format("delta").option("overwriteSchema", "true").saveAsTable("dq_row_status")
spark.createDataFrame(summary, "run_ts string, table_name string, rule_id string, severity string, description string, rows_checked long, rows_failed long") \\
     .withColumn("fail_pct", F.round(F.col("rows_failed") / F.col("rows_checked") * 100, 4)) \\
     .write.mode("overwrite").format("delta").option("overwriteSchema", "true").saveAsTable("dq_summary")
for tb, df in bronze.items():
    rej = statuses[tb].filter("dq_status = 'REJECTED'").select(F.col("record_id").alias("_rid"), "dq_rules")
    df.join(rej, df[KEYS[tb]].cast("string") == F.col("_rid")).drop("_rid") \\
      .write.mode("overwrite").format("delta").option("overwriteSchema", "true").saveAsTable(f"quarantine_{tb}")
display(spark.table("dq_summary").orderBy("table_name", "rule_id"))
display(spark.table("dq_row_status").groupBy("table_name", "dq_status").count().orderBy("table_name", "dq_status"))
''')

md('''
## 4 · Star schema (only rows without ERROR)

`fact_transactions` = one row per operation, with foreign keys to the dimensions, the amount, the status, the model's
score / alert (valid and test periods) and `fraude_signalee` (labelled period only — NULL for the test period, whose labels
are held by the jury).
''')
code('''
ok_tx = statuses["transactions"].filter("dq_status != 'REJECTED'").select(F.col("record_id").alias("transaction_id"), "dq_status")
ok_cust = statuses["customers"].filter("dq_status != 'REJECTED'").select(F.col("record_id").alias("customer_id"))
ok_ev = statuses["digital_events"].filter("dq_status != 'REJECTED'").select(F.col("record_id").alias("event_id"))

# dim_date
days = spark.sql(f"SELECT explode(sequence(to_date('{DATA_START[:10]}'), to_date('{DATA_END[:10]}'), interval 1 day)) AS d")
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
HOLIDAYS = {"01-01": "Jour de l'an", "01-14": "Fête de la Révolution", "03-20": "Fête de l'Indépendance", "04-09": "Journée des Martyrs",
            "05-01": "Fête du Travail", "07-25": "Fête de la République", "08-13": "Fête de la Femme", "10-15": "Fête de l'Évacuation"}
mname = F.element_at(F.array(*[F.lit(x) for x in MONTHS]), F.month("d"))
dname = F.element_at(F.array(*[F.lit(x) for x in DAYS]), ((F.dayofweek("d") + 5) % 7) + 1)
hol = F.create_map(*[F.lit(x) for kv in HOLIDAYS.items() for x in kv])
dim_date = days.select(
    F.date_format("d", "yyyyMMdd").cast("int").alias("date_key"), F.col("d").alias("date"), F.year("d").alias("annee"),
    F.quarter("d").alias("trimestre"), F.month("d").alias("mois"), mname.alias("nom_mois"),
    F.date_format("d", "yyyy-MM").alias("annee_mois"), F.weekofyear("d").alias("semaine"), F.dayofmonth("d").alias("jour"),
    (((F.dayofweek("d") + 5) % 7) + 1).alias("jour_semaine_num"), dname.alias("jour_semaine"),
    F.dayofweek("d").isin(1, 7).alias("est_weekend"),
    ((F.dayofmonth("d") >= 25) | (F.dayofmonth("d") <= 3)).alias("periode_de_paie"),
    hol[F.date_format("d", "MM-dd")].alias("jour_ferie"),
    F.when(F.col("d") < F.lit("2026-06-01"), "entrainement").when(F.col("d") < F.lit("2026-08-01"), "validation").otherwise("flux_test").alias("periode_modele"))

dim_heure = spark.createDataFrame([(h, "nuit (0h–5h)" if h < 6 else "matin (6h–11h)" if h < 12 else "après-midi (12h–17h)" if h < 18 else "soir (18h–23h)")
                                   for h in range(24)], "heure int, tranche_horaire string")

# dim_geo: where the operation happened (online operations have no city)
tx_ok = bronze["transactions"].join(ok_tx, "transaction_id")
cent = (bronze["merchants"].filter(F.col("latitude").isNotNull()).groupBy("city", "country")
        .agg(F.avg("latitude").alias("latitude"), F.avg("longitude").alias("longitude")))
region = F.create_map(*[F.lit(x) for kv in REGION.items() for x in kv])
cname = F.create_map(*[F.lit(x) for kv in COUNTRY.items() for x in kv])
places = tx_ok.select("city", "country").distinct().join(cent, ["city", "country"], "left")
dim_geo = (places.withColumn("geo_key", F.dense_rank().over(W.orderBy(F.col("country"), F.col("city").asc_nulls_first())))
           .select("geo_key", F.coalesce("city", F.lit("Non localisé (en ligne)")).alias("ville"),
                   F.when(F.col("country") == "TN", F.when(F.col("city").isin(GOVERNORATES), F.col("city"))).alias("gouvernorat"),
                   F.when(F.col("country") == "TN", F.coalesce(region[F.col("city")], F.lit("Non localisé"))).otherwise(F.lit("Étranger")).alias("region"),
                   F.col("country").alias("code_pays"), F.coalesce(cname[F.col("country")], F.col("country")).alias("pays"),
                   (F.col("country") == "TN").alias("est_tunisie"), F.col("city").isNotNull().alias("est_localise"),
                   F.round("latitude", 4).alias("latitude"), F.round("longitude", 4).alias("longitude")))

# dim_client (gender deliberately excluded)
cu = bronze["customers"].join(ok_cust, "customer_id")
dim_client = (cu.withColumn("client_key", F.dense_rank().over(W.orderBy("customer_id")))
              .select("client_key", "customer_id", "age",
                      F.when(F.col("age") < 25, "18–24").when(F.col("age") < 35, "25–34").when(F.col("age") < 45, "35–44")
                       .when(F.col("age") < 60, "45–59").when(F.col("age") < 70, "60–69").otherwise("70 et +").alias("tranche_age"),
                      "segment", F.col("occupation").alias("profession"), F.col("home_city").alias("ville_residence"),
                      F.col("governorate").alias("gouvernorat_residence"), region[F.col("governorate")].alias("region_residence"),
                      F.to_date("customer_since").alias("client_depuis"),
                      F.when(F.col("monthly_income_tnd") < 1000, "< 1 000 TND").when(F.col("monthly_income_tnd") < 2000, "1 000–2 000 TND")
                       .when(F.col("monthly_income_tnd") < 4000, "2 000–4 000 TND").otherwise("≥ 4 000 TND").alias("tranche_revenu"),
                      F.round("monthly_income_tnd", 0).alias("revenu_mensuel_tnd"),
                      F.col("kyc_risk_level").alias("risque_kyc"), F.col("digital_banking_user").cast("boolean").alias("utilise_banque_digitale")))

dim_merchant = (bronze["merchants"].withColumn("merchant_key", F.dense_rank().over(W.orderBy("merchant_id")))
                .select("merchant_key", "merchant_id", F.col("merchant_name").alias("nom_commercant"), F.col("category").alias("categorie"),
                        "mcc", F.col("merchant_type").alias("type_commercant"), F.col("city").alias("ville_commercant"), F.col("country").alias("pays_commercant")))

combos = tx_ok.select("transaction_type", "channel", "entry_mode").distinct()
dim_channel = (combos.withColumn("channel_key", F.dense_rank().over(W.orderBy("transaction_type", "channel", F.col("entry_mode").asc_nulls_first())))
               .select("channel_key", F.col("transaction_type").alias("type_operation"), F.col("channel").alias("canal"),
                       F.col("entry_mode").alias("mode_saisie"), F.col("channel").isin("TPE", "DAB").alias("carte_presente"),
                       F.col("channel").isin("EN_LIGNE", "MOBILE", "WEB").alias("a_distance"),
                       (F.col("entry_mode") == "ECOM_3DS").alias("avec_3ds"), F.col("entry_mode").isin("SANS_CONTACT").alias("sans_contact")))

dim_card = (bronze["cards"].withColumn("card_key", F.dense_rank().over(W.orderBy("card_id")))
            .select("card_key", "card_id", F.col("card_type").alias("type_carte"), F.col("is_international").cast("boolean").alias("internationale"),
                    F.col("contactless_enabled").cast("boolean").alias("sans_contact_active"),
                    F.col("daily_limit_tnd").alias("plafond_jour_tnd"), F.col("atm_daily_limit_tnd").alias("plafond_dab_jour_tnd")))

labels = spark.table("fraud_labels_train").select("transaction_id", F.col("is_fraud").cast("int").alias("_f"))
scores = spark.table("gold_scores").select("transaction_id", "score_model", F.col("is_alert").cast("boolean").alias("alerte_modele"),
                                          F.col("risk_level").alias("niveau_risque"), F.col("legacy_alert").cast("boolean").alias("alerte_regles_actuelles"))
f = (tx_ok.withColumn("_ts", F.to_timestamp("timestamp"))
     .join(dim_geo.select("geo_key", F.col("ville").alias("_v"), F.col("code_pays").alias("_p")),
           (F.coalesce(F.col("city"), F.lit("Non localisé (en ligne)")) == F.col("_v")) & (F.col("country") == F.col("_p")), "left")
     .join(dim_client.select("client_key", "customer_id"), "customer_id", "left")
     .join(dim_merchant.select("merchant_key", "merchant_id"), "merchant_id", "left")
     .join(dim_card.select("card_key", "card_id"), "card_id", "left")
     .join(dim_channel.select("channel_key", F.col("type_operation").alias("transaction_type"), F.col("canal").alias("channel"),
                              F.col("mode_saisie").alias("entry_mode")), ["transaction_type", "channel", "entry_mode"], "left")
     .join(labels, "transaction_id", "left").join(scores, "transaction_id", "left"))
fact = f.select("transaction_id", F.date_format("_ts", "yyyyMMdd").cast("int").alias("date_key"), F.hour("_ts").alias("heure"),
                F.col("_ts").alias("horodatage"), "geo_key", "client_key", "merchant_key", "card_key", "channel_key",
                F.round("amount_tnd", 3).alias("montant_tnd"), F.col("original_currency").alias("devise_origine"),
                F.col("status").alias("statut"), F.col("decline_reason").alias("motif_refus"), (F.col("status") == "APPROUVEE").alias("est_approuvee"),
                F.col("beneficiary_id").alias("beneficiaire_id"),
                F.when(F.col("split") == "train", F.col("_f")).alias("fraude_signalee"),
                F.round("score_model", 6).alias("score_modele"), "alerte_modele", "niveau_risque", "alerte_regles_actuelles", "dq_status")

ev = bronze["digital_events"].join(ok_ev, "event_id").withColumn("_ts", F.to_timestamp("timestamp"))
fact_ev = (ev.join(dim_client.select("client_key", "customer_id"), "customer_id", "left")
           .select("event_id", F.date_format("_ts", "yyyyMMdd").cast("int").alias("date_key"), F.hour("_ts").alias("heure"),
                   F.col("_ts").alias("horodatage"), "client_key", F.col("event_type").alias("type_evenement"), F.col("status").alias("statut"),
                   F.col("channel").alias("canal"), F.col("ip_country").alias("pays_ip"), F.col("auth_method").alias("methode_auth"),
                   F.col("device_id").alias("appareil_id")))

for name, df in {"dim_date": dim_date, "dim_heure": dim_heure, "dim_geo": dim_geo, "dim_client": dim_client, "dim_merchant": dim_merchant,
                 "dim_channel": dim_channel, "dim_card": dim_card, "fact_transactions": fact, "fact_digital_events": fact_ev}.items():
    df.write.mode("overwrite").format("delta").option("overwriteSchema", "true").saveAsTable(name)
    print(name, spark.table(name).count())
''')

md('## 5 · Reconciliation (bronze = accepted + quarantined; facts = accepted)')
code('''
rec = []
for tb in bronze:
    n = bronze[tb].count(); q = spark.table(f"quarantine_{tb}").count()
    rec.append((tb, n, n - q, q))
rec = spark.createDataFrame(rec, "table_name string, bronze_rows long, accepted long, quarantined long")
display(rec)
n_fact = spark.table("fact_transactions").count(); acc = rec.filter("table_name='transactions'").first()["accepted"]
assert n_fact == acc, (n_fact, acc)
assert spark.table("fact_transactions").filter("geo_key IS NULL OR client_key IS NULL OR channel_key IS NULL OR date_key IS NULL").count() == 0
assert spark.table("fact_transactions").groupBy("transaction_id").count().filter("count > 1").count() == 0
test_labels = spark.table("fact_transactions").join(spark.table("dim_date"), "date_key").filter("periode_modele = 'flux_test' AND fraude_signalee IS NOT NULL").count()
assert test_labels == 0, test_labels
print("reconciled:", n_fact, "facts · 0 missing keys · 0 duplicates · 0 test labels")
''')

nb = {"cells": CELLS, "metadata": {"kernel_info": {"name": "synapse_pyspark"},
                                   "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
out = Path(__file__).parent / "05_quality_star.ipynb"
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", out)
