"""Report Intelligence Pipeline, phases 1-3: retrieval, analysis (SQL, no LLM arithmetic), evidence verification.

Every number in a report is a *fact* (F#) or a *table* (T#) produced here by a fixed SQL query on the source's canonical views,
with its source, period, method and query kept for the evidence register. Confirmed fraud = label recorded by the bank
(is_fraud = 1); suspected = model alert without a label yet. They are never mixed.
"""
from datetime import datetime

import pandas as pd

import report_i18n as I
import report_sources as rs

LBL = {  # fact key -> (FR, EN, AR, unit, kind)
    "ops": ("Opérations", "Transactions", "العمليات", "count", "fact"),
    "amount": ("Montant total", "Total amount", "المبلغ الإجمالي", "tnd", "fact"),
    "declines": ("Opérations refusées", "Declined transactions", "العمليات المرفوضة", "count", "fact"),
    "decline_rate": ("Taux de refus", "Decline rate", "نسبة الرفض", "pct", "fact"),
    "labelled_share": ("Part des opérations avec un statut de fraude connu", "Share of transactions with a known fraud status",
                       "نسبة العمليات ذات حالة احتيال معروفة", "pct", "fact"),
    "frauds": ("Fraudes confirmées", "Confirmed frauds", "حالات احتيال مؤكدة", "count", "fact"),
    "fraud_amount": ("Montant des fraudes confirmées", "Confirmed fraud amount", "مبلغ الاحتيال المؤكد", "tnd", "fact"),
    "fraud_rate": ("Taux de fraude confirmée", "Confirmed fraud rate", "معدل الاحتيال المؤكد", "pct", "fact"),
    "fraud_approved_amount": ("Fraudes confirmées acceptées (exposition financière)", "Confirmed frauds approved (financial exposure)",
                              "احتيال مؤكد تمت الموافقة عليه (التعرض المالي)", "tnd", "fact"),
    "model_alerts": ("Alertes du modèle", "Model alerts", "تنبيهات النموذج", "count", "ml"),
    "suspected": ("Alertes du modèle sans statut confirmé (suspicions)", "Model alerts without a confirmed status (suspected)",
                  "تنبيهات النموذج دون حالة مؤكدة (مشتبه بها)", "count", "ml"),
    "model_precision": ("Précision des alertes du modèle", "Model alert precision", "دقة تنبيهات النموذج", "pct", "ml"),
    "model_recall": ("Fraudes confirmées couvertes par une alerte du modèle", "Confirmed frauds caught by a model alert",
                     "حالات الاحتيال المؤكدة التي رصدها النموذج", "pct", "ml"),
    "rules_alerts": ("Alertes du moteur de règles actuel", "Current rules-engine alerts", "تنبيهات محرك القواعد الحالي", "count", "fact"),
    "rules_precision": ("Précision des alertes du moteur de règles", "Rules-engine alert precision", "دقة تنبيهات محرك القواعد", "pct", "fact"),
    "rules_recall": ("Fraudes confirmées couvertes par le moteur de règles", "Confirmed frauds caught by the rules engine",
                     "حالات الاحتيال المؤكدة التي رصدها محرك القواعد", "pct", "fact"),
    "night_fraud_share": ("Part des fraudes confirmées la nuit (0 h–6 h)", "Share of confirmed frauds at night (0–6 h)",
                          "نسبة الاحتيال المؤكد ليلاً (0–6)", "pct", "fact"),
    "night_ops_share": ("Part des opérations la nuit (0 h–6 h)", "Share of transactions at night (0–6 h)", "نسبة العمليات ليلاً (0–6)", "pct", "fact"),
    "logins": ("Connexions", "Logins", "عمليات تسجيل الدخول", "count", "fact"),
    "failed_logins": ("Connexions échouées", "Failed logins", "محاولات دخول فاشلة", "count", "fact"),
    "failed_rate": ("Taux d'échec de connexion", "Login failure rate", "نسبة فشل تسجيل الدخول", "pct", "fact"),
    "sensitive_events": ("Changements sensibles du compte (appareil, bénéficiaire, mot de passe, téléphone)",
                         "Sensitive account changes (device, payee, password, phone)", "تغييرات حساسة في الحساب", "count", "fact"),
    "foreign_ip_share": ("Connexions depuis une adresse IP étrangère", "Logins from a foreign IP address", "تسجيلات دخول من عنوان IP أجنبي", "pct",
                         "fact"),
    "fraud_after_sensitive": ("Fraudes confirmées précédées d'un changement sensible (72 h)", "Confirmed frauds preceded by a sensitive change (72 h)",
                              "احتيال مؤكد سبقه تغيير حساس (72 ساعة)", "pct", "fact"),
    "fraud_after_failed": ("Fraudes confirmées précédées d'une connexion échouée (24 h)", "Confirmed frauds preceded by a failed login (24 h)",
                           "احتيال مؤكد سبقته محاولة دخول فاشلة (24 ساعة)", "pct", "fact"),
    "no3ds_rate": ("Taux de fraude en ligne sans 3-D Secure", "Online fraud rate without 3-D Secure", "معدل الاحتيال عبر الإنترنت دون 3-D Secure",
                   "pct", "fact"),
    "with3ds_rate": ("Taux de fraude en ligne avec 3-D Secure", "Online fraud rate with 3-D Secure", "معدل الاحتيال عبر الإنترنت مع 3-D Secure",
                     "pct", "fact"),
    "magstripe_rate": ("Taux de fraude en piste magnétique", "Fraud rate on magnetic stripe", "معدل الاحتيال بالشريط المغناطيسي", "pct", "fact"),
    "chip_rate": ("Taux de fraude en puce", "Fraud rate on chip", "معدل الاحتيال بالشريحة", "pct", "fact"),
    "alerts_per_day": ("Alertes du modèle par jour (moyenne)", "Model alerts per day (average)", "تنبيهات النموذج يومياً (متوسط)", "count", "ml"),
    "dq_warnings": ("Opérations avec un avertissement qualité", "Transactions with a data-quality warning", "عمليات بتحذير جودة البيانات", "count",
                    "fact"),
    "decisions": ("Décisions d'analystes enregistrées", "Analyst decisions recorded", "قرارات المحللين المسجلة", "count", "employee"),
    "override_rate": ("Décisions différentes de la recommandation", "Decisions differing from the recommendation", "قرارات مخالفة للتوصية", "pct",
                      "employee"),
    "decision_time": ("Temps médian alerte → décision", "Median alert → decision time", "الوقت الوسيط من التنبيه إلى القرار", "hours", "employee"),
}
DIMS = {  # table key -> (column, FR, EN, AR, limit)
    "channel": ("channel", "par canal", "by channel", "حسب القناة", 10),
    "card_type": ("card_type", "par type de carte", "by card type", "حسب نوع البطاقة", 12),
    "merchant_category": ("merchant_category", "par catégorie de commerçant", "by merchant category", "حسب فئة التاجر", 12),
    "country": ("country", "par pays", "by country", "حسب البلد", 12),
    "city": ("city", "par ville", "by city", "حسب المدينة", 12),
    "region": ("region", "par région du client", "by customer region", "حسب منطقة العميل", 12),
    "entry_mode": ("entry_mode", "par mode de saisie", "by entry mode", "حسب طريقة الإدخال", 10),
    "segment": ("segment", "par segment client", "by customer segment", "حسب شريحة العميل", 10),
    "hour_band": ("CASE WHEN hour < 6 THEN '00-05' WHEN hour < 12 THEN '06-11' WHEN hour < 18 THEN '12-17' ELSE '18-23' END",
                  "par tranche horaire", "by time of day", "حسب الفترة الزمنية", 4),
}


class Analysis:
    def __init__(self, spec, src):
        self.spec, self.src = spec, src
        self.lang = spec["lang"]
        self.facts, self.tables, self.checks, self.limits = [], [], [], []
        self.charts, self.insights, self.extra = [], [], {}
        self.generated = datetime.now().isoformat(timespec="seconds")

    # -------------------------------------------------------- evidence items
    def fact(self, key, value, period, sql, method, refs=None, kind=None, label=None):
        lb = LBL.get(key)
        f = {"id": f"F{len(self.facts) + 1}", "key": key,
             "value": None if value is None else round(float(value), 3 if (lb and lb[3] == "tnd") else 6),
             "unit": lb[3] if lb else "count", "kind": kind or (lb[4] if lb else "fact"),
             "label": label or ({"fr": lb[0], "en": lb[1], "ar": lb[2]} if lb else {"fr": key, "en": key, "ar": key}),
             "period": [str(p) for p in period], "source": self.src.provenance, "sql": " ".join(sql.split()), "method": method,
             "refs": refs or [], "computed_at": self.generated}
        self.facts.append(f)
        return f

    def get(self, key, prev=False):
        k = ("prev:" if prev else "") + key
        return next((f for f in self.facts if f.get("tag", f["key"]) == k), None)

    def val(self, key, prev=False):
        f = self.get(key, prev)
        return None if f is None else f["value"]

    def table(self, key, title, df, sql, period, cols):
        t = {"id": f"T{len(self.tables) + 1}", "key": key, "title": title, "df": df, "sql": " ".join(sql.split()),
             "period": [str(p) for p in period], "source": self.src.provenance, "cols": cols}
        self.tables.append(t)
        return t

    def check(self, name, ok, detail, level="warn"):
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail, "level": "ok" if ok else level})

    def limit(self, fr, en, ar):
        self.limits.append({"fr": fr, "en": en, "ar": ar})

    def L(self, fr, en, ar=None):
        return I.tr(self.lang, fr, en, ar)


def where(spec, extra=None):
    """Scope filter as SQL + bound parameters (values never interpolated)."""
    sc, parts, params = spec.get("scope") or {}, ["day BETWEEN ? AND ?"], []
    for col, key in (("channel", "channels"), ("card_type", "card_types"), ("city", "cities"), ("country", "countries")):
        vals = sc.get(key) or []
        if vals:
            parts.append(f"{col} IN ({', '.join('?' * len(vals))})")
            params += list(vals)
    if extra:
        parts.append(extra)
    return " AND ".join(parts), params


def _run(a, sql, period, extra_params=None):
    w, p = where(a.spec)
    return a.src.q(sql.replace("{W}", w), [str(period[0]), str(period[1])] + p + (extra_params or []))


# ---------------------------------------------------------------- phase 1-2: retrieval + analysis
OVERVIEW_SQL = """SELECT COUNT(*) AS ops, COUNT(DISTINCT transaction_id) AS distinct_ops, SUM(amount_tnd) AS amount,
  COUNT(*) FILTER (WHERE status = 'REFUSEE') AS declines,
  COUNT(*) FILTER (WHERE is_fraud IS NOT NULL) AS labelled, SUM(is_fraud) AS frauds,
  SUM(CASE WHEN is_fraud = 1 THEN amount_tnd END) AS fraud_amount,
  SUM(CASE WHEN is_fraud = 1 AND status = 'APPROUVEE' THEN amount_tnd END) AS fraud_approved_amount,
  COUNT(*) FILTER (WHERE model_alert) AS model_alerts, COUNT(*) FILTER (WHERE model_alert AND is_fraud = 1) AS model_tp,
  COUNT(*) FILTER (WHERE model_alert AND is_fraud IS NOT NULL) AS model_labelled,
  COUNT(*) FILTER (WHERE model_alert AND is_fraud IS NULL) AS suspected,
  COUNT(*) FILTER (WHERE rules_alert) AS rules_alerts, COUNT(*) FILTER (WHERE rules_alert AND is_fraud = 1) AS rules_tp,
  COUNT(*) FILTER (WHERE rules_alert AND is_fraud IS NOT NULL) AS rules_labelled,
  COUNT(*) FILTER (WHERE model_alert IS NOT NULL) AS model_scored, COUNT(*) FILTER (WHERE rules_alert IS NOT NULL) AS rules_scored,
  SUM(is_fraud) FILTER (WHERE model_alert IS NOT NULL) AS frauds_model_scored, SUM(is_fraud) FILTER (WHERE rules_alert IS NOT NULL) AS frauds_rules_scored,
  MIN(day) FILTER (WHERE model_alert IS NOT NULL) AS model_from,
  COUNT(*) FILTER (WHERE hour < 6) AS night_ops, SUM(CASE WHEN hour < 6 THEN is_fraud END) AS night_frauds,
  COUNT(*) FILTER (WHERE dq_status = 'WARNING') AS dq_warnings, COUNT(DISTINCT day) AS days
FROM tx WHERE {W}"""


def overview(a, period, prev=False):
    """Headline facts for one period (tagged prev: for the comparison period)."""
    r = _run(a, OVERVIEW_SQL, period).iloc[0].to_dict()
    r = {k: (None if pd.isna(v) else v) for k, v in r.items()}
    sql = OVERVIEW_SQL
    ops = r["ops"] or 0
    out = {"raw": r}

    def add(key, value, method, kind=None):
        if value is None:
            return None
        f = a.fact(key, value, period, sql, method, kind=kind)
        f["tag"] = ("prev:" if prev else "") + key
        if prev:
            f["label"] = {lg: v + I.tr(lg, " (période précédente)", " (previous period)", " (الفترة السابقة)") for lg, v in f["label"].items()}
        out[key] = f
        return f
    add("ops", ops, "COUNT(*)")
    add("amount", r["amount"] or 0, "SUM(amount_tnd)")
    add("declines", r["declines"], "COUNT(status = REFUSEE)")
    if ops:
        add("decline_rate", r["declines"] / ops, "declines / ops")
        add("labelled_share", r["labelled"] / ops, "COUNT(is_fraud IS NOT NULL) / ops")
    if r["labelled"]:
        add("frauds", r["frauds"] or 0, "SUM(is_fraud) on labelled rows")
        add("fraud_amount", r["fraud_amount"] or 0, "SUM(amount_tnd) WHERE is_fraud = 1")
        add("fraud_rate", (r["frauds"] or 0) / r["labelled"], "frauds / labelled transactions")
        add("fraud_approved_amount", r["fraud_approved_amount"] or 0, "SUM(amount_tnd) WHERE is_fraud = 1 AND status = APPROUVEE")
        if r["frauds"]:
            add("night_fraud_share", (r["night_frauds"] or 0) / r["frauds"], "frauds at hour < 6 / frauds")
            add("night_ops_share", r["night_ops"] / ops, "transactions at hour < 6 / transactions")
    if r["model_scored"]:
        add("model_alerts", r["model_alerts"], "COUNT(model_alert)")
        if r["suspected"]:
            add("suspected", r["suspected"], "COUNT(model_alert AND is_fraud IS NULL)")
        if r["model_labelled"]:
            add("model_precision", r["model_tp"] / r["model_labelled"], "model alerts confirmed fraud / labelled model alerts")
        if r["frauds_model_scored"]:
            add("model_recall", r["model_tp"] / r["frauds_model_scored"], "confirmed frauds with a model alert / confirmed frauds on scored days")
        if not prev and r["model_scored"] < ops:
            a.limit(f"Scores du modèle disponibles à partir du {str(r['model_from'])[:10]} seulement ({r['model_scored'] / ops:.0%} des opérations) : "
                    f"alertes, précision et couverture du modèle portent sur cette partie.",
                    f"Model scores are available from {str(r['model_from'])[:10]} only ({r['model_scored'] / ops:.0%} of transactions): model alerts, "
                    f"precision and coverage refer to that part.", f"درجات النموذج متاحة من {str(r['model_from'])[:10]} فقط ({r['model_scored'] / ops:.0%} من العمليات).")
        if r["days"]:
            nd = a.src.one(f"SELECT COUNT(DISTINCT day) FROM tx WHERE {where(a.spec)[0]} AND model_alert IS NOT NULL",
                           [str(period[0]), str(period[1])] + where(a.spec)[1])[0]
            add("alerts_per_day", r["model_alerts"] / max(nd, 1), "model alerts / days with model scores")
    if r["rules_scored"]:
        add("rules_alerts", r["rules_alerts"], "COUNT(rules_alert)")
        if r["rules_labelled"]:
            add("rules_precision", r["rules_tp"] / r["rules_labelled"], "rules alerts confirmed fraud / labelled rules alerts")
        if r["frauds_rules_scored"]:
            add("rules_recall", r["rules_tp"] / r["frauds_rules_scored"], "confirmed frauds with a rules alert / confirmed frauds on covered days")
    if not prev and r["dq_warnings"]:
        add("dq_warnings", r["dq_warnings"], "COUNT(dq_status = WARNING)")
    return out


def breakdown(a, key, period, prev_period=None):
    col, fr, en, ar, limit = DIMS[key]
    sql = f"""WITH cur AS (SELECT {col} AS grp, COUNT(*) AS ops, SUM(amount_tnd) AS amount,
                 COUNT(*) FILTER (WHERE is_fraud IS NOT NULL) AS labelled, SUM(is_fraud) AS frauds,
                 SUM(CASE WHEN is_fraud = 1 THEN amount_tnd END) AS fraud_amount, COUNT(*) FILTER (WHERE model_alert) AS model_alerts,
                 COUNT(*) FILTER (WHERE status = 'REFUSEE') AS declines
               FROM tx WHERE {{W}} AND {col} IS NOT NULL GROUP BY 1)
             SELECT * FROM cur ORDER BY COALESCE(frauds, 0) DESC, ops DESC"""
    df = _run(a, sql, period)
    if df.empty:
        return None
    tot_ops, tot_fr = df["ops"].sum(), df["frauds"].fillna(0).sum()
    df["share_ops"] = df["ops"] / tot_ops
    df["share_frauds"] = df["frauds"].fillna(0) / tot_fr if tot_fr else None
    df["fraud_rate"] = df["frauds"] / df["labelled"].where(df["labelled"] > 0)
    df["lift"] = df["share_frauds"] / df["share_ops"] if tot_fr else None
    df["decline_rate"] = df["declines"] / df["ops"]
    if prev_period:
        p = _run(a, sql, prev_period)[["grp", "frauds", "ops"]].rename(columns={"frauds": "prev_frauds", "ops": "prev_ops"})
        df = df.merge(p, on="grp", how="left")
        df["change"] = (df["frauds"] - df["prev_frauds"]) / df["prev_frauds"].where(df["prev_frauds"] > 0)
    df = df.head(limit).reset_index(drop=True)
    if key == "channel":
        df["grp"] = df["grp"].map(lambda c: I.channel_label(c, a.lang))
    title = {"fr": f"Opérations et fraudes {fr}", "en": f"Transactions and frauds {en}", "ar": f"العمليات والاحتيال {ar}"}
    return a.table(key, title, df, sql, period, ["grp", "ops", "share_ops", "frauds", "share_frauds", "fraud_rate", "lift", "fraud_amount"]
                   + (["prev_frauds", "change"] if prev_period else []))


def trend(a, period):
    days = (pd.Timestamp(period[1]) - pd.Timestamp(period[0])).days + 1
    unit = "day" if days <= 62 else "week" if days <= 370 else "month"
    sql = f"""SELECT DATE_TRUNC('{unit}', day) AS t, COUNT(*) AS ops, SUM(is_fraud) AS frauds, COUNT(*) FILTER (WHERE model_alert) AS model_alerts,
              COUNT(*) FILTER (WHERE is_fraud IS NOT NULL) AS labelled FROM tx WHERE {{W}} GROUP BY 1 ORDER BY 1"""
    df = _run(a, sql, period)
    t = a.table("trend", {"fr": "Évolution dans la période", "en": "Trend over the period", "ar": "التطور خلال الفترة"}, df, sql, period,
                ["t", "ops", "frauds", "model_alerts"])
    t["unit"] = unit
    return t


def cyber(a, period):
    if not a.src.has_auth:
        a.limit("Aucun journal d'authentification transmis par la banque : indicateurs de connexion indisponibles.",
                "No authentication log provided by the bank: login indicators unavailable.", "لم يقدم البنك سجل المصادقة: مؤشرات الدخول غير متاحة.")
        return
    p = [str(period[0]), str(period[1])]
    sql = """SELECT COUNT(*) FILTER (WHERE event_type = 'CONNEXION') AS logins,
                    COUNT(*) FILTER (WHERE event_type = 'CONNEXION' AND status = 'ECHEC') AS failed,
                    COUNT(*) FILTER (WHERE event_type IN ('AJOUT_BENEFICIAIRE','AJOUT_APPAREIL','REINITIALISATION_MOT_DE_PASSE','MODIFICATION_NUMERO_TELEPHONE')) AS sensitive,
                    COUNT(*) FILTER (WHERE event_type = 'CONNEXION' AND ip_country IS NOT NULL AND ip_country <> (SELECT MODE(ip_country) FROM auth)) AS foreign_ip
             FROM auth WHERE day BETWEEN ? AND ?"""
    r = a.src.one(sql, p)
    logins, failed, sensitive, foreign = (x or 0 for x in r)
    a.fact("logins", logins, period, sql, "COUNT(event_type = CONNEXION)")
    a.fact("failed_logins", failed, period, sql, "COUNT(CONNEXION AND ECHEC)")
    if logins:
        a.fact("failed_rate", failed / logins, period, sql, "failed / logins")
        a.fact("foreign_ip_share", foreign / logins, period, sql, "logins whose IP country differs from the most frequent one / logins")
    a.fact("sensitive_events", sensitive, period, sql, "COUNT(sensitive event types)")
    w, wp = where(a.spec)
    sql2 = f"""WITH fr AS (SELECT transaction_id, customer_key, ts FROM tx WHERE {w} AND is_fraud = 1)
              SELECT COUNT(*) AS n,
                     COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM auth e WHERE e.customer_key = fr.customer_key AND e.ts < fr.ts
                        AND e.ts >= fr.ts - INTERVAL 72 HOUR AND e.event_type IN ('AJOUT_BENEFICIAIRE','AJOUT_APPAREIL',
                        'REINITIALISATION_MOT_DE_PASSE','MODIFICATION_NUMERO_TELEPHONE'))) AS after_sensitive,
                     COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM auth e WHERE e.customer_key = fr.customer_key AND e.ts < fr.ts
                        AND e.ts >= fr.ts - INTERVAL 24 HOUR AND e.event_type = 'CONNEXION' AND e.status = 'ECHEC')) AS after_failed
              FROM fr"""
    n, s72, f24 = a.src.one(sql2, p + wp)
    if n:
        a.fact("fraud_after_sensitive", s72 / n, period, sql2, "confirmed frauds whose customer had a sensitive change in the 72 h before / frauds")
        a.fact("fraud_after_failed", f24 / n, period, sql2, "confirmed frauds whose customer had a failed login in the 24 h before / frauds")
    sql3 = """SELECT day, COUNT(*) FILTER (WHERE event_type = 'CONNEXION' AND status = 'ECHEC') AS failed,
                     COUNT(*) FILTER (WHERE event_type IN ('AJOUT_BENEFICIAIRE','AJOUT_APPAREIL','REINITIALISATION_MOT_DE_PASSE','MODIFICATION_NUMERO_TELEPHONE')) AS sensitive
              FROM auth WHERE day BETWEEN ? AND ? GROUP BY 1 ORDER BY 1"""
    df = a.src.q(sql3, p)
    if len(df) > 3:
        m, sd = df["failed"].mean(), df["failed"].std()
        df["spike"] = df["failed"] > m + 3 * (sd or 0)
        a.table("auth_daily", {"fr": "Connexions échouées et changements sensibles par jour", "en": "Failed logins and sensitive changes per day",
                               "ar": "محاولات الدخول الفاشلة والتغييرات الحساسة يومياً"}, df, sql3, period, ["day", "failed", "sensitive", "spike"])
    _entry_rates(a, period)
    if "DAB" in (a.spec["scope"].get("channels") or []) or not a.spec["scope"].get("channels"):
        sql4 = f"""SELECT city AS grp, COUNT(*) AS ops, SUM(is_fraud) AS frauds, COUNT(*) FILTER (WHERE entry_mode = 'MAGSTRIPE') AS magstripe
                  FROM tx WHERE {w} AND channel = 'DAB' AND city IS NOT NULL GROUP BY 1 HAVING SUM(is_fraud) > 0 ORDER BY frauds DESC LIMIT 10"""
        d4 = a.src.q(sql4, p + wp)
        if len(d4):
            d4["fraud_rate"] = d4["frauds"] / d4["ops"]
            a.table("atm_cities", {"fr": "Fraudes aux DAB par ville (pistes de skimming à vérifier)", "en": "ATM frauds by city (skimming leads to verify)",
                                   "ar": "الاحتيال في الصراف الآلي حسب المدينة (مؤشرات تحتاج تحقق)"}, d4, sql4, period,
                    ["grp", "ops", "frauds", "fraud_rate", "magstripe"])


def _entry_rates(a, period):
    w, wp = where(a.spec)
    sql = f"""SELECT entry_mode, COUNT(*) FILTER (WHERE is_fraud IS NOT NULL) AS labelled, SUM(is_fraud) AS frauds
              FROM tx WHERE {w} AND entry_mode IN ('ECOM_3DS','ECOM_SANS_3DS','MAGSTRIPE','CHIP') GROUP BY 1"""
    df = a.src.q(sql, [str(period[0]), str(period[1])] + wp).set_index("entry_mode")
    for mode, key in (("ECOM_SANS_3DS", "no3ds_rate"), ("ECOM_3DS", "with3ds_rate"), ("MAGSTRIPE", "magstripe_rate"), ("CHIP", "chip_rate")):
        if mode in df.index and df.at[mode, "labelled"] >= 30:
            a.fact(key, (df.at[mode, "frauds"] or 0) / df.at[mode, "labelled"], period, sql, f"frauds / labelled transactions WHERE entry_mode = {mode}")


def operational(a, period):
    w, wp = where(a.spec)
    p = [str(period[0]), str(period[1])] + wp
    sql = f"""SELECT decline_reason AS grp, COUNT(*) AS ops, SUM(is_fraud) AS frauds FROM tx WHERE {w} AND status = 'REFUSEE'
              AND decline_reason IS NOT NULL GROUP BY 1 ORDER BY ops DESC"""
    df = a.src.q(sql, p)
    if len(df):
        df["share_ops"] = df["ops"] / df["ops"].sum()
        a.table("decline_reasons", {"fr": "Motifs de refus", "en": "Decline reasons", "ar": "أسباب الرفض"}, df, sql, period, ["grp", "ops", "share_ops", "frauds"])
    if a.src.id == "hyson":
        try:
            import tools
            d = tools.decisions()
        except Exception:
            d = pd.DataFrame()
        if len(d) and "decided_at" in d:
            d = d[pd.to_datetime(d["decided_at"], errors="coerce").dt.date.between(pd.Timestamp(period[0]).date(), pd.Timestamp(period[1]).date())]
        if len(d):
            sqlj = "decisions journal (app/data/decisions.csv, hash-chained)"
            a.fact("decisions", len(d), period, sqlj, "rows in the decision journal decided in the period")
            if "system_decision" in d:
                a.fact("override_rate", float((d["decision"] != d["system_decision"]).mean()), period, sqlj, "decision != system recommendation")
            if "duration_s" in d and pd.to_numeric(d["duration_s"], errors="coerce").notna().any():
                a.fact("decision_time", float(pd.to_numeric(d["duration_s"], errors="coerce").median()) / 3600, period, sqlj, "median(duration_s) / 3600")
        else:
            a.limit("Aucune décision d'analyste enregistrée sur la période : temps de résolution non mesurable.",
                    "No analyst decision recorded in the period: resolution time cannot be measured.", "لا توجد قرارات محللين مسجلة في الفترة.")
    elif a.src.tenant is not None:
        cases = a.src.tenant.canonical("cases")
        if cases is not None and "opened_at" in cases:
            c = cases[pd.to_datetime(cases["opened_at"], errors="coerce").dt.date.between(pd.Timestamp(period[0]).date(), pd.Timestamp(period[1]).date())]
            a.fact("decisions", len(c), period, "tenant canonical cases", "cases opened in the period", kind="employee",
                   label={"fr": "Dossiers d'enquête ouverts", "en": "Investigation cases opened", "ar": "ملفات التحقيق المفتوحة"})


def investigation_case(a):
    """Evidence for one transaction: the existing evidence board (0 token), the system recommendation, similar past cases,
    continuous-monitoring triggers, the employee's decision if any, and (optional) the three AI agents' debate."""
    tid = a.spec.get("case_id")
    if not tid:
        return
    if a.src.id == "hyson":
        import investigation as iv
        import tools
        t = tools.get_transaction(tid)
        if t.get("introuvable") or "transaction" not in t:
            a.limit(f"Opération {tid} introuvable.", f"Transaction {tid} not found.", f"العملية {tid} غير موجودة.")
            return
        tx = t["transaction"]
        a.extra["transaction"] = tx
        ev, rec, trig, cases, stats = iv.board(tid, None, "fr")
        a.extra["board"], a.extra["system"], a.extra["triggers"] = ev, rec, trig
        per = [str(tx.get("timestamp", ""))[:10]] * 2
        src_sql = f"tools.get_transaction('{tid}') · investigation.board('{tid}')"
        a.fact("case_amount", tx.get("amount_tnd"), per, src_sql, "transaction amount", refs=[tid], kind="fact",
               label={"fr": "Montant de l'opération", "en": "Transaction amount", "ar": "مبلغ العملية"})["unit"] = "tnd"
        s = t.get("score") or {}
        if s.get("score_modele") is not None:
            f = a.fact("case_score", s["score_modele"], per, src_sql, "model score (LightGBM, frozen scoring)", refs=[tid], kind="ml",
                       label={"fr": "Score du modèle", "en": "Model score", "ar": "درجة النموذج"})
            f["unit"] = "score"
        if s.get("fraudes_mesurees_a_ce_score") is not None:
            a.fact("case_measured", s["fraudes_mesurees_a_ce_score"], per, src_sql, "share of frauds measured at this score in validation",
                   refs=[tid], kind="ml", label={"fr": "Fraudes mesurées à ce score (validation)", "en": "Frauds measured at this score (validation)",
                                                 "ar": "نسبة الاحتيال المقاسة عند هذه الدرجة"})["unit"] = "pct"
        if stats and stats.get("known"):
            a.fact("case_similar_rate", stats.get("fraud_rate_known") or 0, per, "memory.similar (16,302 past cases, status as known then)",
                   f"confirmed frauds among {stats['known']} similar past cases with a known outcome", refs=list(cases["transaction_id"][:8])
                   if hasattr(cases, "columns") and "transaction_id" in cases else [], kind="fact",
                   label={"fr": "Cas similaires passés confirmés frauduleux", "en": "Similar past cases confirmed as fraud",
                          "ar": "الحالات المشابهة السابقة المؤكدة احتيالاً"})["unit"] = "pct"
            a.extra["similar"] = cases
        try:
            d = tools.decisions()
            d = d[d["transaction_id"] == tid] if len(d) else d
            if len(d):
                a.extra["decision"] = d.iloc[-1].to_dict()
        except Exception:
            pass
        if a.spec.get("ai_agents"):
            import copilot
            if copilot.configured():
                out = iv.investigate(tid, None, "en" if a.lang == "en" else "fr")
                a.extra["agents"] = {k: out.get(k) for k in ("prosecution", "defense", "judge", "judge_model", "tokens", "mode")}
            else:
                a.limit("Débat des agents IA non exécuté : Azure OpenAI non configuré.", "AI agents' debate not run: Azure OpenAI not configured.",
                        "لم يتم تشغيل نقاش وكلاء الذكاء الاصطناعي.")
    else:
        t = a.src.tenant
        tx = t.canonical("transactions")
        row = tx[tx["transaction_id"].astype(str) == tid]
        if row.empty:
            a.limit(f"Opération {tid} introuvable.", f"Transaction {tid} not found.", f"العملية {tid} غير موجودة.")
            return
        sc = t.score(tx)
        r = sc[sc["transaction_id"].astype(str) == tid].iloc[0]
        rec = row.iloc[0].to_dict()
        a.extra["transaction"] = {k: (str(v) if k == "timestamp" else v) for k, v in rec.items() if k not in ("customer_id", "card_id")}
        per = [str(rec["timestamp"])[:10]] * 2
        a.fact("case_amount", rec.get("amount_tnd"), per, "tenant canonical transactions", "transaction amount", refs=[tid],
               label={"fr": "Montant de l'opération", "en": "Transaction amount", "ar": "مبلغ العملية"})["unit"] = "tnd"
        f = a.fact("case_score", float(r["score"]), per, f"tenant score ({r['score_kind']})", "score of the active scoring method", refs=[tid],
                   kind="ml", label={"fr": "Score", "en": "Score", "ar": "الدرجة"})
        f["unit"] = "score"
        a.extra["board"] = [{"id": f"E{i + 1}", "kind": "signal", "text": x} for i, x in enumerate(r["reasons"])]
        a.extra["system"] = {"decision": None, "score_kind": r["score_kind"]}
        hist = tx[tx["customer_id"] == rec["customer_id"]].sort_values("timestamp")
        hist = hist[hist["timestamp"] < rec["timestamp"]].tail(10)
        a.extra["history"] = hist.drop(columns=["customer_id", "card_id"], errors="ignore")
        hits = t.memory_search(" ".join(str(rec.get(c, "")) for c in ("channel", "entry_mode", "merchant_category", "country")), 5)
        a.extra["memory"] = hits


# ---------------------------------------------------------------- phase 3: verification
def verify(a, ov):
    s, src = a.spec, a.src
    p0, p1 = pd.Timestamp(s["period"][0]).date(), pd.Timestamp(s["period"][1]).date()
    inside = p0 >= src.first_day and p1 <= src.last_day
    a.check("period", inside, a.L(f"Période demandée {p0} → {p1} ; données disponibles {src.first_day} → {src.last_day}.",
                                  f"Requested period {p0} → {p1}; data available {src.first_day} → {src.last_day}.",
                                  f"الفترة المطلوبة {p0} → {p1}؛ البيانات المتاحة {src.first_day} → {src.last_day}."), "warn")
    if not ov:
        return
    r = ov["raw"]
    a.check("duplicates", r["ops"] == r["distinct_ops"], a.L(f"{int(r['ops'] - r['distinct_ops'])} identifiant(s) d'opération en double.",
                                                             f"{int(r['ops'] - r['distinct_ops'])} duplicate transaction id(s).",
                                                             f"{int(r['ops'] - r['distinct_ops'])} معرف(ات) مكررة."), "error")
    ch = next((t for t in a.tables if t["key"] == "channel"), None)
    if ch is not None:
        n_null = src.one(f"SELECT COUNT(*) FROM tx WHERE {where(s)[0]} AND channel IS NULL", [str(p0), str(p1)] + where(s)[1])[0]
        ok = int(ch["df"]["ops"].sum()) + n_null == int(r["ops"]) and abs((ch["df"]["frauds"].fillna(0).sum()) - (r["frauds"] or 0)) < 1e-6
        a.check("breakdown_sums", ok, a.L("La somme par canal égale le total (opérations et fraudes).", "Channel breakdown adds up to the total.",
                                          "مجموع التوزيع حسب القناة يساوي الإجمالي."), "error")
    if not any((s.get("scope") or {}).values()):
        n = src.one("SELECT COUNT(*) FROM tx WHERE day BETWEEN ? AND ?", [str(p0), str(p1)])[0]
        a.check("recount", n == r["ops"], a.L(f"Recomptage indépendant : {n} opérations.", f"Independent recount: {n} transactions.",
                                              f"إعادة عد مستقلة: {n} عملية."), "error")
    share = (r["labelled"] or 0) / r["ops"] if r["ops"] else 0
    a.check("labels", share >= 0.999, a.L(f"Statut de fraude connu pour {share:.1%} des opérations.", f"Fraud status known for {share:.1%} of transactions.",
                                          f"حالة الاحتيال معروفة لـ {share:.1%} من العمليات."), "warn")
    if share < 0.999:
        lu = src.labelled_until
        a.limit(f"Fraudes confirmées connues jusqu'au {lu} seulement : après cette date, seules les alertes du modèle (suspicions) sont comptées, "
                f"jamais comme fraudes.", f"Confirmed frauds are known only until {lu}: after that date only model alerts (suspected) are counted, "
                f"never as frauds.", f"حالات الاحتيال المؤكدة معروفة حتى {lu} فقط؛ بعد ذلك تُحتسب تنبيهات النموذج كاشتباه فقط.")
    a.check("separation", True, a.L("Fraudes confirmées (étiquette de la banque) et suspicions (alertes sans étiquette) comptées séparément.",
                                    "Confirmed frauds (bank label) and suspected (alerts without label) counted separately.",
                                    "الاحتيال المؤكد والمشتبه به محسوبان بشكل منفصل."))
    if (r["ops"] or 0) < 1000:
        a.limit("Volume faible sur ce périmètre : les taux sont fragiles.", "Low volume in this scope: rates are fragile.", "حجم منخفض: النسب غير مستقرة.")
