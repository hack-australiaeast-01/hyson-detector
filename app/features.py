"""Analytics behind the "out of this world" pages: impact in TND, process funnel, model drift (PSI),
points of compromise (Constellation), crime-scene replay (Reconstitution) and counterfactuals (Contre-enquête).

Every number comes from Microsoft Fabric (lh_fraud SQL endpoint) when live; each result is snapshotted to
app/data/feat_*.parquet so the demo still works offline. Labels are only used for validation metrics and for
frauds already reported BEFORE the period analysed (never future information).
"""
import math
import re
from datetime import timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

import data_access as da

PERIOD_START = {"valid": "2026-06-01", "test": "2026-08-01"}
COMPROMISE_SCENARIOS = ("SKIMMING_DAB", "CARTE_CLONEE_ETRANGER", "CARD_TESTING")
_ID = re.compile(r"^[A-Za-z0-9_]+$")


def _q(name, sql, params=()):
    """Live query with parquet snapshot fallback."""
    path = da.DATA / f"feat_{name}.parquet"
    src = da.source()
    if src.mode == "fabric":
        try:
            df = src.sql.query(sql, params)
            da.DATA.mkdir(exist_ok=True)
            df.to_parquet(path, index=False)
            return df
        except Exception as exc:
            src.error = f"{name}: {type(exc).__name__}: {str(exc)[:120]}"
    return pd.read_parquet(path) if path.exists() else None


def reset():
    for fn in (impact_raw, funnel_raw, drift_raw, compromise_points, exposures, alert_geo, robustness, model_ci,
               fairness, copilot_eval):
        fn.cache_clear()


# ---------------------------------------------------------------- robustness & governance (notebook 04, MLflow)
@lru_cache(maxsize=None)
def robustness():
    """Rolling-origin backtest written by notebooks/04_robustness (4 folds, 2 months each, train = past only)."""
    return _q("robustness", "SELECT * FROM dbo.gold_model_robustness ORDER BY test_from")


@lru_cache(maxsize=None)
def model_ci():
    """95 % day-block bootstrap intervals on the production validation scores (notebook 04)."""
    return _q("model_ci", "SELECT * FROM dbo.gold_model_ci")


@lru_cache(maxsize=None)
def fairness():
    """Alert rate, precision and recall by customer segment and age band (validation), alert rate on the live flow.
    Gender is not a feature and is not reported; age / segment are profile features, so their effect is monitored."""
    return _q("fairness", """
        SELECT c.segment, CASE WHEN c.age < 30 THEN '18-29' WHEN c.age < 45 THEN '30-44' WHEN c.age < 60 THEN '45-59' ELSE '60+' END AS age_band,
               t.period, COUNT(*) AS ops, SUM(CAST(g.is_alert AS INT)) AS alerts,
               SUM(CASE WHEN g.is_alert = 1 AND t.is_fraud = 1 THEN 1 ELSE 0 END) AS tp, SUM(CAST(t.is_fraud AS INT)) AS frauds
        FROM dbo.gold_scores g JOIN dbo.silver_transactions t ON t.transaction_id = g.transaction_id
        JOIN dbo.customers c ON c.customer_id = t.customer_id
        GROUP BY c.segment, CASE WHEN c.age < 30 THEN '18-29' WHEN c.age < 45 THEN '30-44' WHEN c.age < 60 THEN '45-59' ELSE '60+' END,
                 t.period""")


@lru_cache(maxsize=None)
def copilot_eval():
    """Latest golden-question evaluation of the copilot (app/eval_copilot.py)."""
    p = da.DATA / "copilot_eval.json"
    if not p.exists():
        return None
    import json
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- impact & process (bank KPIs)
@lru_cache(maxsize=None)
def impact_raw():
    return _q("impact", """
        SELECT g.period, g.is_alert, g.legacy_alert, COALESCE(f.is_fraud, 0) AS is_fraud,
               COUNT(*) AS n, SUM(f.amount_tnd) AS amt
        FROM dbo.gold_scores g JOIN dbo.silver_transactions f ON f.transaction_id = g.transaction_id
        GROUP BY g.period, g.is_alert, g.legacy_alert, COALESCE(f.is_fraud, 0)""")


def impact():
    """Validation (Jun–Jul 2026) business impact: frauds and TND caught, legitimate customers disturbed."""
    r = impact_raw()
    if r is None:
        return None
    v = r[r.period == "valid"].copy()
    v["amt"] = pd.to_numeric(v.amt, errors="coerce").fillna(0)

    def agg(mask):
        s = v[mask]
        return int(s.n.sum()), float(s.amt.sum())

    fraud = v.is_fraud == 1
    total_f, total_f_amt = agg(fraud)
    out = {"fraudes": total_f, "fraudes_tnd": total_f_amt, "operations": int(v.n.sum())}
    for name, flag in [("modele", v.is_alert == 1), ("moteur", v.legacy_alert == 1)]:
        alerts, _ = agg(flag)
        caught, caught_amt = agg(flag & fraud)
        false, false_amt = agg(flag & ~fraud)
        out[name] = {"alertes": alerts, "fraudes": caught, "fraudes_tnd": caught_amt, "fausses": false,
                     "fausses_tnd": false_amt, "taux_tnd": caught_amt / total_f_amt if total_f_amt else 0}
    t = r[(r.period == "test")]
    out["flux_du_jour"] = {"operations": int(t.n.sum()), "alertes": int(t[t.is_alert == 1].n.sum())}
    return out


@lru_cache(maxsize=None)
def funnel_raw():
    return _q("funnel", "SELECT period, COUNT(*) AS n FROM dbo.silver_transactions GROUP BY period")


@lru_cache(maxsize=None)
def drift_raw():
    """Score distribution per period on fixed log-spaced buckets (computed in SQL, 2 x 10 rows)."""
    return _q("drift", """
        SELECT period, CASE
            WHEN score_model < 0.0005 THEN 0 WHEN score_model < 0.001 THEN 1 WHEN score_model < 0.002 THEN 2
            WHEN score_model < 0.005 THEN 3 WHEN score_model < 0.01 THEN 4 WHEN score_model < 0.02 THEN 5
            WHEN score_model < 0.05 THEN 6 WHEN score_model < 0.2 THEN 7 WHEN score_model < 0.6 THEN 8 ELSE 9 END AS bucket,
            COUNT(*) AS n
        FROM dbo.gold_scores GROUP BY period, CASE
            WHEN score_model < 0.0005 THEN 0 WHEN score_model < 0.001 THEN 1 WHEN score_model < 0.002 THEN 2
            WHEN score_model < 0.005 THEN 3 WHEN score_model < 0.01 THEN 4 WHEN score_model < 0.02 THEN 5
            WHEN score_model < 0.05 THEN 6 WHEN score_model < 0.2 THEN 7 WHEN score_model < 0.6 THEN 8 ELSE 9 END""")


BUCKET_LABEL = ["<0.05 %", "0.05–0.1 %", "0.1–0.2 %", "0.2–0.5 %", "0.5–1 %", "1–2 %", "2–5 %", "5–20 %", "20–60 %", "≥60 %"]


def drift():
    """Population Stability Index between validation (reference) and the live flow (test)."""
    r = drift_raw()
    if r is None:
        return None
    p = r.pivot_table(index="bucket", columns="period", values="n", aggfunc="sum").reindex(range(10)).fillna(0)
    a = (p["valid"] / p["valid"].sum()).clip(lower=1e-6)
    b = (p["test"] / p["test"].sum()).clip(lower=1e-6)
    psi = float(((b - a) * np.log(b / a)).sum())
    dist = pd.DataFrame({"bucket": BUCKET_LABEL, "validation": a.values, "flux_du_jour": b.values})
    status = "stable" if psi < 0.1 else ("à surveiller" if psi < 0.25 else "dérive")
    return {"psi": psi, "status": status, "dist": dist}


# ---------------------------------------------------------------- Constellation: points of compromise
@lru_cache(maxsize=None)
def compromise_points(period="test", min_lift=2.5, min_victims=8):
    """Merchants/ATMs visited by fraud victims in the 30 days BEFORE their fraud, far more than average.
    Only frauds reported before the start of `period` are used."""
    cut = PERIOD_START[period]
    scen = ",".join(f"'{s}'" for s in COMPROMISE_SCENARIOS)
    r = _q(f"compromise_{period}", f"""
        WITH v AS (
          SELECT card_id, MIN(timestamp) AS t0 FROM dbo.silver_transactions
          WHERE is_fraud = 1 AND fraud_scenario IN ({scen}) AND card_id IS NOT NULL AND fraud_reported_date < ?
          GROUP BY card_id),
        vis AS (SELECT merchant_id, COUNT(DISTINCT card_id) AS visitors FROM dbo.silver_transactions
                WHERE merchant_id IS NOT NULL AND card_id IS NOT NULL AND timestamp < ? GROUP BY merchant_id),
        hit AS (SELECT s.merchant_id, COUNT(DISTINCT v.card_id) AS victims FROM v JOIN dbo.silver_transactions s
                ON s.card_id = v.card_id AND s.timestamp < v.t0 AND s.timestamp >= DATEADD(day, -30, v.t0)
                AND COALESCE(s.is_fraud, 0) = 0
                WHERE s.merchant_id IS NOT NULL GROUP BY s.merchant_id)
        SELECT h.merchant_id, m.merchant_name, m.merchant_type, m.category, m.city, m.latitude, m.longitude,
               h.victims, vis.visitors
        FROM hit h JOIN vis ON vis.merchant_id = h.merchant_id LEFT JOIN dbo.merchants m ON m.merchant_id = h.merchant_id
        WHERE vis.visitors >= 30""", (cut, cut))
    if r is None or r.empty:
        return pd.DataFrame()
    r = r.copy()
    for c in ["victims", "visitors", "latitude", "longitude"]:
        r[c] = pd.to_numeric(r[c], errors="coerce")
    base = r.victims.sum() / r.visitors.sum()
    r["rate"] = r.victims / r.visitors
    r["lift"] = r.rate / base
    r["base_rate"] = base
    top = r[(r.lift >= min_lift) & (r.victims >= min_victims)].sort_values("lift", ascending=False)
    return top.reset_index(drop=True)


@lru_cache(maxsize=None)
def exposures(period="test"):
    """Alerts of `period` whose card visited a point of compromise in the 30 days before the alert."""
    cp = compromise_points(period)
    if cp.empty:
        return pd.DataFrame(columns=["transaction_id", "merchant_id", "visits", "last_visit"])
    ids = [m for m in cp.merchant_id if _ID.match(str(m))]
    values = ",".join(f"('{m}')" for m in ids)
    r = _q(f"exposure_{period}", f"""
        WITH cp AS (SELECT merchant_id FROM (VALUES {values}) t(merchant_id)),
        a AS (SELECT transaction_id, card_id, timestamp FROM dbo.gold_alert_queue WHERE card_id IS NOT NULL AND period = ?)
        SELECT a.transaction_id, s.merchant_id, COUNT(*) AS visits, MAX(s.timestamp) AS last_visit
        FROM a JOIN dbo.silver_transactions s ON s.card_id = a.card_id AND s.timestamp < a.timestamp
             AND s.timestamp >= DATEADD(day, -30, a.timestamp)
        JOIN cp ON cp.merchant_id = s.merchant_id
        GROUP BY a.transaction_id, s.merchant_id""", (period,))
    return r if r is not None else pd.DataFrame(columns=["transaction_id", "merchant_id", "visits", "last_visit"])


@lru_cache(maxsize=None)
def alert_geo():
    """Location and entities of every alert (for the Tunisia map)."""
    return _q("alert_geo", """
        SELECT s.transaction_id, s.latitude, s.longitude, s.merchant_id, s.device_id, s.beneficiary_id
        FROM dbo.silver_transactions s JOIN dbo.gold_alert_queue a ON a.transaction_id = s.transaction_id""")


def constellation(period="test"):
    """Graph: points of compromise (stars) <- alerts whose card passed there (planets). Returns nodes, edges, rings."""
    import networkx as nx
    cp, ex, q = compromise_points(period), exposures(period), da.queue()
    q = q[(q.period == period) & (q.risk_level != "FAIBLE")]
    ex = ex[ex.transaction_id.isin(q.transaction_id)]
    if cp.empty or ex.empty:
        return None
    g = nx.Graph()
    for r in cp.itertuples():
        g.add_node(r.merchant_id, kind="point", label=r.merchant_name or r.merchant_id, city=r.city, victims=int(r.victims),
                   visitors=int(r.visitors), lift=float(r.lift), mtype=r.merchant_type)
    info = q.set_index("transaction_id")
    for r in ex.itertuples():
        a = info.loc[r.transaction_id]
        g.add_node(r.transaction_id, kind="alert", risk=a.risk_level, score=float(a.score_pct), amount=float(a.amount_tnd),
                   customer=a.customer_id, channel=a.channel, when=a.timestamp)
        g.add_edge(r.transaction_id, r.merchant_id, visits=int(r.visits))
    # Galaxy layout: points of compromise placed by co-exposure (spring layout on the point graph), alerts on orbits
    # around their point (or between points when they went through several).
    pg = nx.Graph()
    pts_all = [n for n, d in g.nodes(data=True) if d["kind"] == "point"]
    pg.add_nodes_from(pts_all)
    for a in (n for n, d in g.nodes(data=True) if d["kind"] == "alert"):
        nb = sorted(g.neighbors(a))
        for i in range(len(nb)):
            for j in range(i + 1, len(nb)):
                w = pg.get_edge_data(nb[i], nb[j], {"weight": 0})["weight"]
                pg.add_edge(nb[i], nb[j], weight=w + 1)
    ppos = nx.spring_layout(pg, k=2.2 / math.sqrt(max(len(pts_all), 1)), iterations=200, seed=11, weight="weight")
    rng = np.random.default_rng(5)
    pos = {p: np.array(ppos[p]) for p in pts_all}
    for p in pts_all:
        orbit = [a for a in g.neighbors(p) if g.degree(a) == 1]
        for i, a in enumerate(sorted(orbit, key=lambda x: -g.nodes[x]["score"])):
            ring = 0.11 + 0.045 * (i // 16)
            ang = 2 * math.pi * (i % 16) / 16 + rng.uniform(-.12, .12) + (i // 16) * 0.2
            pos[a] = pos[p] + ring * np.array([math.cos(ang), math.sin(ang)])
    for a in (n for n, d in g.nodes(data=True) if d["kind"] == "alert" and g.degree(n) > 1):
        pos[a] = np.mean([pos[p] for p in g.neighbors(a)], axis=0) + rng.normal(0, .015, 2)
    rings = []
    for comp in nx.connected_components(g):
        pts = [n for n in comp if g.nodes[n]["kind"] == "point"]
        alerts = [n for n in comp if g.nodes[n]["kind"] == "alert"]
        if pts and alerts:
            rings.append({"points": pts, "alerts": alerts, "customers": len({g.nodes[a]["customer"] for a in alerts}),
                          "amount": sum(g.nodes[a]["amount"] for a in alerts),
                          "high": sum(1 for a in alerts if g.nodes[a]["risk"] == "ELEVE")})
    rings.sort(key=lambda x: (-len(x["alerts"]), -x["high"]))
    return {"graph": g, "pos": pos, "rings": rings, "points": cp, "exposures": ex}


# ---------------------------------------------------------------- Reconstitution: replay of the hours before an alert
EVENT_FR = {"CONNEXION": "Connexion", "AJOUT_APPAREIL": "Nouvel appareil enrôlé", "AJOUT_BENEFICIAIRE": "Bénéficiaire ajouté",
            "REINITIALISATION_MOT_DE_PASSE": "Mot de passe réinitialisé", "MODIFICATION_NUMERO_TELEPHONE": "Numéro de téléphone modifié"}
EVENT_EN = {"CONNEXION": "Login", "AJOUT_APPAREIL": "New device enrolled", "AJOUT_BENEFICIAIRE": "Beneficiary added",
            "REINITIALISATION_MOT_DE_PASSE": "Password reset", "MODIFICATION_NUMERO_TELEPHONE": "Phone number changed"}


def replay_steps(transaction_id, hours=24, lang="fr"):
    """Chronological steps (transactions + digital events) before the alert, each flagged when it is a risk signal."""
    import tools
    en = lang == "en"
    r = tools._tx_row(transaction_id)
    if r is None:
        return None
    ts = r.timestamp
    start = ts - timedelta(hours=hours)
    hist = da.customer_tx(r.customer_id)
    past = hist[hist.timestamp < start]
    win = hist[(hist.timestamp >= start) & (hist.timestamp <= ts)]
    usual_avg = float(past.amount_tnd.mean()) if len(past) else None
    p95 = float(past.amount_tnd.quantile(0.95)) if len(past) else None
    known_merchants, known_devices = set(past.merchant_id.dropna()), set(past.device_id.dropna())
    known_countries = set(past[past.channel.isin(["TPE", "DAB"])].country.dropna())
    steps = []
    for t in win.itertuples():
        flags = []
        if p95 and t.amount_tnd > p95:
            flags.append(("montant au-dessus de 95 % de ses opérations" if not en else "amount above 95% of their operations"))
        if t.timestamp.hour < 6:
            flags.append("nuit" if not en else "night")
        if isinstance(t.merchant_id, str) and t.merchant_id not in known_merchants:
            flags.append("commerçant jamais vu" if not en else "never-seen merchant")
        if t.channel in ("TPE", "DAB") and t.country not in known_countries and isinstance(t.country, str):
            flags.append("pays physique jamais vu" if not en else "never-seen physical country")
        if t.status == "REFUSEE":
            flags.append(("refusée : " if not en else "declined: ") + str(t.decline_reason or ""))
        where = " · ".join(x for x in [t.merchant_category if isinstance(t.merchant_category, str) else None,
                                      t.city if isinstance(t.city, str) else None, t.country] if x)
        steps.append({"ts": t.timestamp, "kind": "tx", "icon": "🎯" if t.transaction_id == transaction_id else "💳",
                      "title": f"{t.transaction_type} {t.channel} · {t.amount_tnd:,.3f} TND".replace(",", " "),
                      "detail": where, "flags": flags, "lat": _num(getattr(t, "latitude", None)),
                      "lon": _num(getattr(t, "longitude", None)), "target": t.transaction_id == transaction_id,
                      "amount": float(t.amount_tnd)})
    ev = da.events(r.customer_id, start.to_pydatetime(), ts.to_pydatetime())
    if ev is not None:
        names = EVENT_EN if en else EVENT_FR
        for e in ev.itertuples():
            flags = []
            if e.status == "ECHEC":
                flags.append("échec" if not en else "failed")
            if isinstance(e.ip_country, str) and e.ip_country != "TN":
                flags.append(("IP " if not en else "IP ") + e.ip_country)
            if isinstance(e.device_id, str) and e.device_id not in known_devices:
                flags.append("appareil inconnu" if not en else "unknown device")
            if e.event_type in ("AJOUT_BENEFICIAIRE", "AJOUT_APPAREIL", "MODIFICATION_NUMERO_TELEPHONE", "REINITIALISATION_MOT_DE_PASSE"):
                flags.append("action sensible" if not en else "sensitive action")
            if e.channel in ("AGENCE", "CENTRE_APPEL"):
                flags.append("en agence (rassurant)" if not en else "in branch (reassuring)")
            steps.append({"ts": e.timestamp, "kind": "event", "icon": "📱",
                          "title": f"{names.get(e.event_type, e.event_type)} · {e.status}",
                          "detail": " · ".join(x for x in [e.channel, f"IP {e.ip_country}" if isinstance(e.ip_country, str) else None,
                                                          e.auth_method if isinstance(e.auth_method, str) else None] if x),
                          "flags": flags, "lat": None, "lon": None, "target": False, "amount": None})
    steps.sort(key=lambda s: (s["ts"], s["kind"] == "tx"))
    for s in steps:
        s["risky"] = any(not f.startswith(("en agence", "in branch")) for f in s["flags"])
    return {"tx": r, "steps": steps, "usual_avg": usual_avg, "p95": p95, "start": start, "end": ts,
            "n_signals": sum(1 for s in steps if s["risky"])}


def _num(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- Contre-enquête: counterfactuals on SHAP log-odds
def _logit(p):
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sig(x):
    return 1 / (1 + math.exp(-x))


def thresholds(period):
    q = da.queue()
    a = q[(q.period == period) & (q.risk_level != "FAIBLE")]
    h = a[a.risk_level == "ELEVE"]
    return {"alerte": float(a.score_model.min()) if len(a) else None, "eleve": float(h.score_model.min()) if len(h) else None}


def counterfactual(transaction_id):
    """What would have to be different? Neutralise the model's own factors (SHAP log-odds, additive) one by one.

    For an alert: remove the factors pushing towards fraud (largest first) until the score falls below the alert threshold.
    For a cleared operation: remove the reassuring factors and check whether it would have entered the queue.
    """
    q = da.queue()
    m = q[q.transaction_id == transaction_id]
    if m.empty:
        return None
    r = m.iloc[0]
    e = da.explanations()
    e = e[(e.transaction_id == transaction_id) & e.source.isin(["model_for", "model_against"])].copy()
    th = thresholds(r.period)
    score = float(r.score_model)
    alert = r.risk_level != "FAIBLE"
    pick = e[e.source == ("model_for" if alert else "model_against")].copy()
    pick["abs"] = pick.points.abs()
    pick = pick.sort_values("abs", ascending=False)
    logit, path, flip_at = _logit(score), [], None
    for f in pick.itertuples():
        logit -= float(f.points)
        new = _sig(logit)
        crossed = (new < th["alerte"]) if alert else (new >= th["alerte"])
        obs = f.observed if pd.notna(f.observed) else (f.observed_text if isinstance(f.observed_text, str) else None)
        path.append({"facteur": f.factor, "feature": f.feature, "observe": obs,
                     "contribution": float(f.points), "score_apres": new, "franchit_seuil": bool(crossed)})
        if crossed and flip_at is None:
            flip_at = len(path)
    return {"tx": r, "score": score, "alert": alert, "thresholds": th, "path": path, "flip_at": flip_at,
            "all_factors": e.sort_values("points", ascending=False)}
