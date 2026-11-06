"""Copilot tools (brief §9.2). Each tool reads the Gold exports and returns compact JSON-able facts.

The LLM never computes a score: it only reads what these functions return.
"""
import csv
import json
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import data_access as da
from person_search import find_customers

PHYSICAL = {"TPE", "DAB"}
DECISIONS = {"BLOQUER", "ESCALADER", "VALIDER"}
DECISIONS_FILE = da.DATA / "decisions.csv"


def _v(x):
    if x is None:
        return None
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if np.isnan(x) else round(float(x), 3)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    return x


def _row(r, cols):
    return {c: _v(r[c]) for c in cols if c in r.index and _v(r[c]) is not None}


def _tx_row(transaction_id):
    """Transaction facts (Fabric silver_transactions or local extract), falling back to the alert queue."""
    r = da.tx_by_id(transaction_id)
    if r is not None:
        return r
    q = da.queue()
    m = q[q.transaction_id == transaction_id]
    return None if m.empty else m.iloc[0]


def _not_found(transaction_id):
    return {"erreur": f"Transaction {transaction_id} introuvable ({da.source().describe()})."}


def _top(series, k=3):
    vc = series.dropna().value_counts()
    total = int(vc.sum())
    return [{"valeur": str(i), "nb": int(n), "part": round(n / total, 2)} for i, n in vc.head(k).items()] if total else []


# ---------------------------------------------------------------- tools
def get_alert_queue(date=None, n=10, period="test", risk_level=None):
    q = da.queue()
    q = q[q.period == period] if period in ("test", "valid") else q
    q = q[q.risk_level != "FAIBLE"]          # demo rows below the alert threshold are not alerts
    if date:
        q = q[q.date == pd.to_datetime(date).date()]
    if risk_level:
        q = q[q.risk_level == risk_level.upper()]
    days = sorted(q.date.unique())
    out = q.sort_values("score_model", ascending=False).head(max(1, min(int(n), 20)))
    alerts = [{"id": r.transaction_id, "date": f"{r.timestamp:%Y-%m-%d %H:%M}", "client": r.customer_id,
               "type": f"{r.transaction_type} {r.channel}", "montant_tnd": round(float(r.amount_tnd), 3),
               "pays": _v(r.country), "niveau": r.risk_level, "percentile": round(float(r.score_pct), 4),
               "facteurs": " | ".join(str(r.top_model_factors or "").split(" | ")[:3])} for r in out.itertuples()]
    return {"periode": period, "date": str(date) if date else "toutes", "nb_alertes": int(len(q)),
            "jours_couverts": f"{days[0]} → {days[-1]}" if days else None, "alertes": alerts}


def get_transaction(transaction_id):
    q = da.queue()
    m = q[q.transaction_id == transaction_id]
    if m.empty:
        r = _tx_row(transaction_id)
        if r is None:
            return _not_found(transaction_id)
        return {"transaction": _row(r, ["transaction_id", "timestamp", "customer_id", "transaction_type", "channel",
                                        "entry_mode", "merchant_category", "amount_tnd", "city", "country", "status"]),
                "dans_file_alertes": False,
                "note": "Hors file d'alertes : score sous le seuil des 1 % les plus risqués."}
    r = m.iloc[0]
    e = da.explanations()
    e = e[e.transaction_id == transaction_id]

    def facts(src, k):
        sub = e[e.source == src]
        sub = sub.reindex(sub.points.abs().sort_values(ascending=False).index).head(k)
        return [{k2: v for k2, v in {"facteur": f.factor,
                                     "valeur_observee": _v(f.observed) if _v(f.observed) is not None else _v(f.observed_text),
                                     "valeur_habituelle": _v(f.usual), "contribution": _v(f.points)}.items()
                 if v is not None} for f in sub.itertuples()]

    rules = facts("rules", 5)
    for_fraud = facts("model_for", 3)
    triggered = [x for x in rules if x.get("contribution", 0) > 0]
    return {
        "transaction": _row(r, ["transaction_id", "timestamp", "customer_id", "card_id", "transaction_type", "channel",
                                "entry_mode", "merchant_category", "amount_tnd", "city", "country", "status"]),
        "dans_file_alertes": True,
        "score": {"niveau_risque": r.risk_level, "score_modele": round(float(r.score_model), 4),
                  "percentile_risque_periode": _v(r.score_pct), "rang_dans_periode": int(r.rank_in_period),
                  "alerte_moteur_regles_actuel": bool(r.legacy_alert), "points_regles_metier": int(r.score_rules)},
        "facteurs_modele_pour_fraude": for_fraud,
        "facteurs_modele_rassurants": facts("model_against", 2),
        "regles_metier_declenchees": triggered,
        "regles_rassurantes": [x for x in rules if x.get("contribution", 0) < 0],
        "recommandation_systeme": recommend(r.risk_level, float(r.score_pct), for_fraud, triggered),
    }


STRONG_CONTRIBUTION = 0.5   # SHAP log-odds; a model factor above this counts as a concordant risk signal
TOP_BAND = 0.998            # percentile above which a block is recommended with high confidence


def _band_precision():
    """Precision of each decision band measured on the labelled validation alerts (Jun–Jul 2026)."""
    if not hasattr(_band_precision, "cache"):
        q = da.queue()
        v = q[(q.period == "valid") & (q.risk_level != "FAIBLE") & q.is_fraud.notna()]

        def p(m):
            return round(float(v[m].is_fraud.mean()), 3) if m.any() else None
        _band_precision.cache = {"percentile_ge_0998": p(v.score_pct >= TOP_BAND), "eleve": p(v.risk_level == "ELEVE"),
                                 "moyen": p(v.risk_level == "MOYEN")}
    return _band_precision.cache


def _pav(rates, weights):
    """Pool-adjacent-violators: make the per-bin fraud rates non-decreasing with the score."""
    blocks = [[r, w, 1] for r, w in zip(rates, weights)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            r1, w1, n1 = blocks[i]
            r2, w2, n2 = blocks.pop(i + 1)
            blocks[i] = [(r1 * w1 + r2 * w2) / (w1 + w2), w1 + w2, n1 + n2]
            i = max(i - 1, 0)
        else:
            i += 1
    return [r for r, _, n in blocks for _ in range(n)]


def measured_fraud_rate(scores):
    """Share of real frauds measured in validation (Jun–Jul 2026 alerts) for alerts with a similar model score.

    The model score is a ranking, not a probability: within the top 1 % a score of 0.70 meant ~11 % frauds,
    0.97 meant ~87 %. Ten score bins on the 1,779 labelled validation alerts, made monotone (PAV).
    """
    if not hasattr(measured_fraud_rate, "table"):
        q = da.queue()
        v = q[(q.period == "valid") & (q.risk_level != "FAIBLE") & q.is_fraud.notna()]
        edges = np.unique(np.quantile(v.score_model, np.linspace(0, 1, 11)))
        b = np.clip(np.searchsorted(edges, v.score_model, side="right") - 1, 0, len(edges) - 2)
        g = v.assign(b=b).groupby("b").is_fraud.agg(["mean", "size"]).reindex(range(len(edges) - 1)).fillna(0)
        measured_fraud_rate.table = (edges, np.array(_pav(g["mean"].tolist(), g["size"].tolist())))
    edges, rates = measured_fraud_rate.table
    s = np.asarray(scores, dtype=float)
    return rates[np.clip(np.searchsorted(edges, s, side="right") - 1, 0, len(rates) - 1)]


def recommend_vector(q):
    """tools.recommend applied to a whole queue (same rule, vectorised). Returns (decision, confidence) Series."""
    e = da.explanations()
    strong = e[(e.source == "model_for") & (e.points >= STRONG_CONTRIBUTION)].groupby("transaction_id").size()
    rules = e[(e.source == "rules") & (e.points > 0)].groupby("transaction_id").size()
    sig = q.transaction_id.map(strong).fillna(0) + q.transaction_id.map(rules).fillna(0)
    hi = q.risk_level == "ELEVE"
    block = hi & (sig >= 2)
    dec = pd.Series(np.where(block, "BLOQUER", np.where(q.risk_level == "FAIBLE", "VALIDER", "ESCALADER")), index=q.index)
    conf = pd.Series(np.where(block & (q.score_pct >= TOP_BAND), "élevée", "moyenne"), index=q.index)
    return dec, conf

def recommend(level, pct, model_for, rules_triggered):
    """Deterministic, documented decision rule backed by validation precision (the LLM explains it, it does not invent it)."""
    strong = [f["facteur"] for f in model_for if (f.get("contribution") or 0) >= STRONG_CONTRIBUTION]
    signals = list(dict.fromkeys(strong + [f["facteur"] for f in rules_triggered]))
    bp = _band_precision()
    if level == "ELEVE" and len(signals) >= 2 and (pct or 0) >= TOP_BAND:
        decision, conf, prec = "BLOQUER", "élevée", bp["percentile_ge_0998"]
    elif level == "ELEVE" and len(signals) >= 2:
        decision, conf, prec = "BLOQUER", "moyenne", bp["eleve"]
    elif level in ("ELEVE", "MOYEN"):
        decision, conf, prec = "ESCALADER", "moyenne", bp["eleve"] if level == "ELEVE" else bp["moyen"]
    else:
        decision, conf, prec = "VALIDER", "élevée" if not rules_triggered else "moyenne", None
    out = {"decision": decision, "confiance": conf, "signaux_concordants": signals[:4],
           "regle": ("percentile ≥ 0.998 et ≥ 2 signaux → BLOQUER (confiance élevée) ; ELEVE et ≥ 2 signaux → BLOQUER (moyenne) ; "
                     "ELEVE sinon ou MOYEN → ESCALADER ; FAIBLE → VALIDER (moyenne si une règle métier a quand même alerté).")}
    if prec is not None:
        out["precision_mesuree_validation"] = prec
    return out


def get_customer_profile(customer_id, before_transaction_id=None):
    c = da.customers()
    out = {"customer_id": customer_id}
    if c is not None:
        m = c[c.customer_id == customer_id]
        if m.empty:
            return {"erreur": f"Client {customer_id} introuvable."}
        out["profil"] = _row(m.iloc[0], ["age", "segment", "occupation", "home_city", "governorate", "customer_since",
                                         "monthly_income_tnd", "avg_monthly_balance_tnd", "kyc_risk_level",
                                         "digital_banking_user"])
    t = da.customer_tx(customer_id)
    if before_transaction_id:
        r = _tx_row(before_transaction_id)
        if r is not None:
            t = t[t.timestamp < r.timestamp]
            out["habitudes_avant"] = before_transaction_id
    if not t.empty:
        a = t.amount_tnd
        phys = t[t.channel.isin(PHYSICAL)]
        out["habitudes"] = {
            "periode_observee": f"{t.timestamp.min():%Y-%m-%d} → {t.timestamp.max():%Y-%m-%d}",
            "nb_operations": int(len(t)),
            "montant_moyen": round(float(a.mean()), 3), "montant_median": round(float(a.median()), 3),
            "montant_p95": round(float(a.quantile(0.95)), 3),
            "pays_paiements_physiques": _top(phys.country, 4), "villes": _top(t.city, 4),
            "canaux": _top(t.channel, 5), "categories": _top(t.merchant_category, 4),
            "part_operations_nuit_0h_6h": round(float((t.timestamp.dt.hour < 6).mean()), 3),
            "nb_appareils": int(t.device_id.nunique()), "nb_beneficiaires": int(t.beneficiary_id.nunique()),
            "taux_refus": round(float((t.status == "REFUSEE").mean()), 3),
        }
    q = da.queue()
    out["nb_alertes_dans_file"] = int((q.customer_id == customer_id).sum())
    return out


def compare_to_habits(transaction_id):
    r = _tx_row(transaction_id)
    if r is None:
        return _not_found(transaction_id)
    ts = r.timestamp
    h = da.customer_tx(r.customer_id)
    past = h[h.timestamp < ts]
    out = {"transaction": _row(r, ["transaction_id", "timestamp", "amount_tnd", "channel", "entry_mode", "country",
                                   "city", "merchant_category"]),
           "historique_avant": {"nb_operations": int(len(past)),
                                "depuis": f"{past.timestamp.min():%Y-%m-%d}" if len(past) else None}}
    if past.empty:
        out["note"] = "Aucune opération antérieure connue pour ce client."
        return out
    a = past.amount_tnd
    phys_past = past[past.channel.isin(PHYSICAL)]
    prev = past.iloc[-1]
    last24 = past[past.timestamp >= ts - timedelta(hours=24)]
    card1h = past[(past.card_id == r.card_id) & (past.timestamp >= ts - timedelta(hours=1))] if _v(r.card_id) else past.iloc[0:0]
    is_phys = r.channel in PHYSICAL
    out["ecarts"] = {
        "montant": float(r.amount_tnd), "montant_moyen": round(float(a.mean()), 3),
        "montant_median": round(float(a.median()), 3), "montant_p95": round(float(a.quantile(0.95)), 3),
        "ratio_vs_moyenne": round(float(r.amount_tnd / a.mean()), 2) if a.mean() else None,
        "part_operations_passees_inferieures": round(float((a < r.amount_tnd).mean()), 3),
        "au_dessus_du_max_passe": bool(r.amount_tnd > a.max()),
        "nb_operations_physiques_passees": int(len(phys_past)),
        "pays_physiques_passes": sorted(phys_past.country.dropna().unique().tolist())[:8],
        "pays_deja_vu_en_physique": bool(r.country in set(phys_past.country)) if is_phys else None,
        "ville_deja_vue": bool(r.city in set(past.city)) if _v(r.city) else None,
        "commercant_deja_vu": bool(r.merchant_id in set(past.merchant_id)) if _v(r.merchant_id) else None,
        "categorie_deja_vue": bool(r.merchant_category in set(past.merchant_category)) if _v(r.merchant_category) else None,
        "appareil_deja_vu": bool(r.device_id in set(past.device_id)) if _v(r.device_id) else None,
        "appareil_connu_depuis_plus_de_24h": bool(r.device_id in set(past[past.timestamp < ts - timedelta(hours=24)].device_id))
                                             if _v(r.device_id) else None,
        "beneficiaire_deja_vu": bool(r.beneficiary_id in set(past.beneficiary_id)) if _v(r.beneficiary_id) else None,
        "beneficiaire_connu_depuis_plus_de_24h": bool(r.beneficiary_id in set(past[past.timestamp < ts - timedelta(hours=24)].beneficiary_id))
                                                 if _v(r.beneficiary_id) else None,
        "mode_saisie_deja_vu": bool(r.entry_mode in set(past.entry_mode)),
        "heure": int(ts.hour), "part_nuit_passee": round(float((past.timestamp.dt.hour < 6).mean()), 3),
        "minutes_depuis_operation_precedente": round((ts - prev.timestamp).total_seconds() / 60, 1),
        "operation_precedente": _row(prev, ["timestamp", "amount_tnd", "channel", "city", "country"]),
        "operations_24h_avant": int(len(last24)), "montant_24h_avant": round(float(last24.amount_tnd.sum()), 3),
        "operations_carte_1h_avant": int(len(card1h)), "refus_carte_1h_avant": int((card1h.status == "REFUSEE").sum()),
        "statut": _v(r.get("status")), "motif_refus": _v(r.get("decline_reason")),
    }
    if _v(r.card_id):
        # same card, 24 h before + the operation itself: the pattern an analyst reads first (bursts, new shops, declines)
        seq = pd.concat([past[(past.card_id == r.card_id) & (past.timestamp >= ts - timedelta(hours=24))], r.to_frame().T])
        seen = set(past[past.timestamp < ts - timedelta(hours=24)].merchant_id.dropna())
        out["sequence_carte_24h"] = {
            "nb_operations": int(len(seq)),
            "nb_commercants_distincts": int(seq.merchant_id.nunique()),
            "nb_commercants_jamais_vus": int(len(set(seq.merchant_id.dropna()) - seen)),
            "nb_sans_contact": int((seq.entry_mode == "SANS_CONTACT").sum()),
            "nb_refus": int((seq.status == "REFUSEE").sum()),
            "motifs_refus": sorted({str(x) for x in seq.decline_reason.dropna()})[:4],
            "montant_total": round(float(pd.to_numeric(seq.amount_tnd).sum()), 3),
            "operations": [f"{pd.Timestamp(x.timestamp):%m-%d %H:%M} {x.entry_mode} {_v(x.merchant_category) or x.transaction_type} "
                           f"{float(x.amount_tnd):.0f} TND {x.status}" for x in seq.tail(6).itertuples()],
        }
    if is_phys and _v(prev.get("latitude")) is not None and _v(r.get("latitude")) is not None:
        lat1, lon1, lat2, lon2 = map(np.radians, [prev.latitude, prev.longitude, r.latitude, r.longitude])
        km = 2 * 6371 * np.arcsin(np.sqrt(np.sin((lat2 - lat1) / 2) ** 2 +
                                          np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2))
        hours = max((ts - prev.timestamp).total_seconds() / 3600, 0.05)
        out["ecarts"]["distance_operation_precedente_km"] = round(float(km), 1)
        out["ecarts"]["vitesse_implicite_kmh"] = round(float(km / hours), 1)
    out["ecarts"] = {k: v for k, v in out["ecarts"].items() if v is not None}
    return out


def get_customer_history(customer_id, days=7, before_transaction_id=None):
    t = da.customer_tx(customer_id)
    if t.empty:
        return {"erreur": f"Aucune opération pour {customer_id}."}
    end = t.timestamp.max()
    if before_transaction_id:
        r = _tx_row(before_transaction_id)
        if r is not None:
            end = r.timestamp
    w = t[(t.timestamp <= end) & (t.timestamp >= end - timedelta(days=int(days)))]
    cols = ["transaction_id", "timestamp", "transaction_type", "channel", "entry_mode", "merchant_category",
            "amount_tnd", "city", "country", "status", "decline_reason"]
    out = {"customer_id": customer_id, "fenetre": f"{end - timedelta(days=int(days)):%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M}",
           "nb_operations": int(len(w)), "montant_total": round(float(w.amount_tnd.sum()), 3),
           "operations": [_row(r, cols) for _, r in w.tail(20).iloc[::-1].iterrows()]}
    if len(w) > 20:
        out["note"] = f"20 opérations les plus récentes affichées sur {len(w)}."
    ev = get_digital_events(customer_id, around=end.strftime("%Y-%m-%d %H:%M:%S"), hours_before=24 * int(days), hours_after=0)
    if ev.get("disponible"):
        out["evenements_digitaux"] = ev["evenements"]
    return out


def get_digital_events(customer_id, around=None, hours_before=48, hours_after=2):
    hours_before = max(int(hours_before or 0), 24)      # at least the model's 24 h window (login failures, new device...)
    if around and str(around).startswith("TX"):
        r = _tx_row(around)
        around = r.timestamp if r is not None else None
    center = pd.to_datetime(around) if around else None
    start = center - timedelta(hours=int(hours_before)) if center is not None else None
    end = center + timedelta(hours=int(hours_after)) if center is not None else None
    t = da.events(customer_id, start, end)
    if t is None:
        out = {"disponible": False, "note": "Événements digitaux indisponibles (mode local sans export digital_events)."}
        if center is not None:
            q = da.queue()
            m = q[(q.customer_id == customer_id) & (q.timestamp == center)]
            if not m.empty:
                e = da.explanations()
                feats = e[(e.transaction_id == m.transaction_id.iloc[0]) &
                          e.feature.fillna("").str.contains("login|device_added|benef|pwd|phone|branch")]
                out["signaux_digitaux_du_modele"] = [{"facteur": f.factor, "valeur": _v(f.observed)} for f in feats.itertuples()]
        return out
    cols = ["timestamp", "event_type", "status", "channel", "device_id", "ip_country", "auth_method", "beneficiary_id"]
    out = {"disponible": True, "customer_id": customer_id, "nb_evenements": int(len(t)),
           "echecs": int((t.status == "ECHEC").sum()) if "status" in t else None,
           "evenements": [_row(r, cols) for _, r in t.sort_values("timestamp").tail(25).iterrows()]}
    if center is not None:
        out["fenetre"] = f"{start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M}"
    return out


def find_related_cases(transaction_id, days=30):
    r = _tx_row(transaction_id)
    if r is None:
        return _not_found(transaction_id)
    alerted = da.queue().set_index("transaction_id")
    ts = r.timestamp
    start = ts - timedelta(days=int(days))
    live = da.source().mode == "fabric"
    out = {"transaction_id": transaction_id, "fenetre_jours": int(days),
           "perimetre": "toute la banque (Fabric)" if live else "clients de la file d'alertes (extrait local)",
           "points_communs": []}
    for key, name in [("merchant_id", "commerçant / DAB"), ("device_id", "appareil"), ("beneficiary_id", "bénéficiaire")]:
        val = _v(r.get(key)) if hasattr(r, "get") else None
        if not val:
            continue
        o = da.related(key, val, start.to_pydatetime(), ts.to_pydatetime(), r.customer_id)
        if o.empty:
            out["points_communs"].append({"type": name, "identifiant": val, "autres_clients": 0, "operations": 0})
            continue
        hits = o[o.transaction_id.isin(alerted.index)]
        rep = o[o.reported_fraud == 1]
        out["points_communs"].append({
            "type": name, "identifiant": val, "autres_clients": int(o.customer_id.nunique()),
            "autres_cartes": int(o.card_id.nunique()), "operations": int(len(o)),
            "cartes_fraudees_deja_signalees": int(rep.card_id.nunique()),
            "clients_fraudes_deja_signales": int(rep.customer_id.nunique()),
            "operations_en_alerte": int(len(hits)),
            "exemples_alertes": [{"transaction_id": t, "client": alerted.loc[t, "customer_id"],
                                  "date": _v(alerted.loc[t, "timestamp"]), "risque": alerted.loc[t, "risk_level"]}
                                 for t in hits.transaction_id.head(5)]})
    if not out["points_communs"]:
        out["note"] = "Aucun commerçant, appareil ou bénéficiaire identifiable sur cette opération."
    else:
        out["regle"] = "Seules les fraudes signalées AVANT la date de l'opération sont comptées (pas d'information future)."
    return out


def get_kpis():
    m = da.metrics()
    rt = da.recall_by_type()
    legacy_alerts, legacy_tp = int(m["legacy_alerts"]), int(m["frauds_caught_legacy"])
    try:                                    # exact legacy counts from Fabric (metrics table rounds recall × frauds)
        import features
        imp = features.impact()
        if imp:
            legacy_alerts, legacy_tp = imp["moteur"]["alertes"], imp["moteur"]["fraudes"]
    except Exception:
        pass
    # exact counts from the validation alert list (same numbers as the Power BI report), metrics as fallback
    va = da.queue()
    va = va[(va.period == "valid") & (va.risk_level != "FAIBLE")]   # alerts only (a demo row below threshold is not an alert)
    if len(va) and va.is_fraud.notna().any():
        budget, model_tp = int(len(va)), int(va.is_fraud.fillna(0).sum())
    else:
        budget = int(m["valid_rows"] * 0.01)
        model_tp = round(m["model_top1pct_precision"] * budget)
    return {"periode_validation": "juin → juillet 2026 (hors échantillon)",
            "moteur_regles_actuel": {"alertes": legacy_alerts, "fraudes_detectees": legacy_tp,
                                     "precision": legacy_tp / max(legacy_alerts, 1),
                                     "rappel": legacy_tp / m["valid_frauds"],
                                     "fausses_alertes": legacy_alerts - legacy_tp},
            "modele_meme_volume": {"alertes": int(m["legacy_alerts"]), "fraudes_detectees": int(m["frauds_caught_model_same_budget"]),
                                   "precision": m["model_same_budget_as_legacy_precision"],
                                   "rappel": m["model_same_budget_as_legacy_recall"]},
            "modele_top_1pct": {"alertes": budget, "fraudes_detectees": model_tp, "precision": model_tp / budget,
                                "rappel": model_tp / m["valid_frauds"], "fausses_alertes": budget - model_tp},
            "pr_auc_modele": m["pr_auc_model"], "fraudes_validation": int(m["valid_frauds"]),
            "rappel_par_typologie": [_row(x, ["fraud_scenario", "frauds", "recall_model", "recall_legacy"]) for _, x in rt.iterrows()]}


DECISION_COLS = ["decided_at", "transaction_id", "decision", "confidence", "comment", "analyst", "source", "duration_s"]


def record_decision(transaction_id, decision, confidence="moyenne", comment="", analyst="analyste", source="copilote",
                    duration_s=None):
    decision = str(decision).upper()
    if decision not in DECISIONS:
        return {"erreur": f"Décision invalide : {decision}. Valeurs : {sorted(DECISIONS)}"}
    if _tx_row(transaction_id) is None:
        return _not_found(transaction_id)
    if DECISIONS_FILE.exists():                     # upgrade an older journal (no duration column) in place
        head = DECISIONS_FILE.read_text(encoding="utf-8").splitlines()[:1]
        if head and "duration_s" not in head[0]:
            old = pd.read_csv(DECISIONS_FILE)
            old["duration_s"] = None
            old[DECISION_COLS].to_csv(DECISIONS_FILE, index=False)
    new = not DECISIONS_FILE.exists()
    with DECISIONS_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(DECISION_COLS)
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), transaction_id, decision, confidence, comment, analyst, source,
                    None if duration_s is None else round(float(duration_s), 1)])
    da.source().push_feedback(DECISIONS_FILE)          # feedback loop: journal mirrored to OneLake
    return {"enregistre": True, "transaction_id": transaction_id, "decision": decision, "confiance": confidence,
            "duree_s": None if duration_s is None else round(float(duration_s), 1)}


def decisions():
    if not DECISIONS_FILE.exists():
        return pd.DataFrame(columns=["decided_at", "transaction_id", "decision", "confidence", "comment", "analyst", "source"])
    return pd.read_csv(DECISIONS_FILE)


# ---------------------------------------------------------------- function-calling schemas
def _fn(name, desc, props, required=()):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(required)}}}


_TX = {"transaction_id": {"type": "string", "description": "Identifiant, ex. TX01555470"}}
TOOL_SCHEMAS = [
    _fn("get_alert_queue", "Transactions les plus risquées (file d'alertes) avec score et facteurs principaux.",
        {"date": {"type": "string", "description": "AAAA-MM-JJ, optionnel"}, "n": {"type": "integer"},
         "period": {"type": "string", "enum": ["test", "valid"], "description": "test = flux du jour (août-sept.)"},
         "risk_level": {"type": "string", "enum": ["ELEVE", "MOYEN", "FAIBLE"]}}),
    _fn("get_transaction", "Détail d'une transaction, son score modèle et ses facteurs de risque et rassurants.", _TX, ["transaction_id"]),
    _fn("get_customer_profile", "Profil et habitudes du client : montants, pays, villes, horaires, appareils, bénéficiaires.",
        {"customer_id": {"type": "string", "description": "customer_id renvoyé par get_transaction (ex. C000488)"},
         "before_transaction_id": {"type": "string", "description": "habitudes calculées uniquement AVANT cette transaction"}},
        ["customer_id"]),
    _fn("compare_to_habits", "Écarts chiffrés entre la transaction et l'historique du client AVANT elle.", _TX, ["transaction_id"]),
    _fn("get_customer_history", "Opérations récentes du client (et événements digitaux si disponibles).",
        {"customer_id": {"type": "string"}, "days": {"type": "integer"},
         "before_transaction_id": {"type": "string", "description": "fin de fenêtre = cette transaction"}}, ["customer_id"]),
    _fn("get_digital_events", "Connexions, appareils, bénéficiaires, mot de passe, numéro autour d'une opération.",
        {"customer_id": {"type": "string"}, "around": {"type": "string", "description": "transaction_id ou date-heure"},
         "hours_before": {"type": "integer"}, "hours_after": {"type": "integer"}}, ["customer_id"]),
    _fn("find_related_cases", "Autres clients/cartes partageant le même commerçant, DAB, appareil ou bénéficiaire.",
        {**_TX, "days": {"type": "integer"}}, ["transaction_id"]),
    _fn("find_customers", "Recherche de clients par description (ville, segment, profession, âge, KYC, alertes). "
        "Lecture seule, filtres autorisés ; renvoie une liste courte de profils et leurs alertes.",
        {"city": {"type": "string"}, "segment": {"type": "string", "enum": ["Etudiant", "Particulier", "Premium", "Professionnel", "Retraite"]},
         "occupation": {"type": "string"}, "age_min": {"type": "integer"}, "age_max": {"type": "integer"},
         "kyc": {"type": "string", "enum": ["Faible", "Moyen", "Eleve"]}, "digital": {"type": "boolean"},
         "with_alerts": {"type": "boolean"}, "limit": {"type": "integer"}}),
    _fn("get_kpis", "Performance du modèle vs moteur de règles actuel (alertes évitées, fraudes détectées, par typologie).", {}),
    _fn("record_decision", "Enregistre la décision de l'analyste. À n'appeler que si l'analyste le demande explicitement.",
        {**_TX, "decision": {"type": "string", "enum": sorted(DECISIONS)},
         "confidence": {"type": "string", "enum": ["faible", "moyenne", "élevée"]}, "comment": {"type": "string"}},
        ["transaction_id", "decision"]),
]
DISPATCH = {"get_alert_queue": get_alert_queue, "get_transaction": get_transaction,
            "get_customer_profile": get_customer_profile, "compare_to_habits": compare_to_habits,
            "get_customer_history": get_customer_history, "get_digital_events": get_digital_events,
            "find_related_cases": find_related_cases, "get_kpis": get_kpis, "find_customers": find_customers, "record_decision": record_decision}


def run_tool(name, arguments):
    fn = DISPATCH.get(name)
    if fn is None:
        return {"erreur": f"Outil inconnu : {name}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        return fn(**args)
    except Exception as exc:  # tool errors are returned to the LLM, never raised into the UI
        return {"erreur": f"{type(exc).__name__}: {exc}"}
