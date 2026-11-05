"""Enquête approfondie (deep search) for "suspicious but not confirmed" alerts.

1. watch()     — 0 token. Flags MEDIUM alerts whose customer already had an alert shortly before (past-only, measured
                 on the labelled validation alerts: ~53 % fraud vs ~16 % for the other medium alerts).
2. evidence()  — 0 token. Python digs everywhere (habits, digital events, linked customers, compromise points,
                 robustness, the most similar labelled alerts, analyst decisions) and keeps only short numbered lines E1…En.
3. investigate() — ONE LLM call, no tools, ~1k tokens: the model only connects the dots between the evidence lines.
                 Cached per transaction and language, logged like the copilot.
"""
import hashlib
import os
import re
import time
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd

import copilot
import data_access as da
import features as fx
import tools

BURST = {"f_key_new_merchants_24h", "f_key_contactless_24h", "f_secs_since_prev"}
SCEN = {"fr": {"CARD_TESTING": "test de carte", "ACCOUNT_TAKEOVER": "prise de contrôle de compte",
               "CARTE_CLONEE_ETRANGER": "carte clonée à l'étranger", "SKIMMING_DAB": "skimming DAB",
               "CARTE_VOLEE_SANS_CONTACT": "carte volée (sans contact)", "FRAUDE_EN_LIGNE_DISCRETE": "fraude en ligne discrète"},
        "en": {"CARD_TESTING": "card testing", "ACCOUNT_TAKEOVER": "account takeover", "CARTE_CLONEE_ETRANGER": "card cloned abroad",
               "SKIMMING_DAB": "ATM skimming", "CARTE_VOLEE_SANS_CONTACT": "stolen card (contactless)",
               "FRAUDE_EN_LIGNE_DISCRETE": "discreet online fraud"}}
PROMPT_VERSION = "deep-d5"


def reset():
    _watch_raw.cache_clear()
    watch_stats.cache_clear()
    _vectors.cache_clear()


# ================================================================= 1. watch-list (0 token)
@lru_cache(maxsize=4)
def _watch_raw(period):
    q = da.queue()
    q = q[(q.period == period) & (q.risk_level != "FAIBLE")].sort_values("timestamp")
    e = da.explanations()
    burst = set(e[(e.source == "model_for") & (e.points > 0.3) & e.feature.isin(BURST)].transaction_id)
    rows = []
    for _, g in q.groupby("customer_id"):
        ts = g.timestamp.values
        ids, amounts, risks = g.transaction_id.values, g.amount_tnd.values, g.risk_level.values
        for i, (tid, t) in enumerate(zip(ids, ts)):
            prev = (ts < t) & (ts >= t - np.timedelta64(72, "h"))
            p24 = (ts < t) & (ts >= t - np.timedelta64(24, "h"))
            rows.append({"transaction_id": tid, "prior_24h": int(p24.sum()), "prior_72h": int(prev.sum()),
                         "prior": [{"id": ids[j], "ts": pd.Timestamp(ts[j]), "amount": float(amounts[j]), "risk": risks[j]}
                                   for j in np.where(prev)[0]][-3:],
                         "burst": tid in burst})
    w = pd.DataFrame(rows).set_index("transaction_id") if rows else pd.DataFrame(
        columns=["prior_24h", "prior_72h", "prior", "burst"])
    lvl = np.where((w.prior_24h > 0) & w.burst, "priorite", np.where(w.prior_72h > 0, "creuser", ""))
    w["level"] = lvl
    return w.join(q.set_index("transaction_id")[["risk_level", "is_fraud"]])


def watch(period="test"):
    """Medium alerts the AI flags for a deeper look (0 token)."""
    w = _watch_raw(period)
    return w[(w.risk_level == "MOYEN") & (w.level != "")]


def ranked(period="test"):
    """Flagged alerts, priority first, then by model score (order of the buttons and of the warm-up)."""
    w = watch(period)
    q = da.queue().set_index("transaction_id")
    return w.assign(score=q.loc[w.index, "score_model"].values, rank=(w.level == "priorite").astype(int)) \
            .sort_values(["rank", "score"], ascending=False)


@lru_cache(maxsize=1)
def watch_stats():
    """Fraud rate of each flag level, measured on the labelled validation medium alerts (Jun–Jul 2026)."""
    w = _watch_raw("valid")
    m = w[w.risk_level == "MOYEN"]
    out = {"base": float(m.is_fraud.mean()) if len(m) else None, "n_base": int(len(m))}
    for lvl in ("priorite", "creuser"):
        s = m[m.level == lvl]
        out[lvl] = (int(len(s)), float(s.is_fraud.mean()) if len(s) else None)
    rest = m[m.level == ""]
    out["other"] = (int(len(rest)), float(rest.is_fraud.mean()) if len(rest) else None)
    return out


def reason(tid, lang="fr"):
    """One-line hover text for a flagged alert."""
    w = _watch_raw(da.queue().set_index("transaction_id").loc[tid, "period"])
    if tid not in w.index:
        return ""
    r = w.loc[tid]
    if r.risk_level != "MOYEN" or not r.level:
        return ""
    st = watch_stats()
    p = st.get(r.level, (0, None))[1]
    prev = ", ".join(f"{x['id']} ({x['ts']:%d/%m %H:%M}, {x['amount']:.0f} TND)" for x in r.prior)
    if lang == "en":
        txt = f"{r.prior_72h} earlier alert(s) for this customer in 72 h: {prev}."
        if r.burst:
            txt += " Burst of activity just before."
        if p is not None:
            txt += f" Measured: {p:.0%} of such medium alerts were fraud (vs {st['other'][1]:.0%} for the others)."
    else:
        txt = f"{r.prior_72h} alerte(s) précédente(s) pour ce client en 72 h : {prev}."
        if r.burst:
            txt += " Rafale d'activité juste avant."
        if p is not None:
            txt += f" Mesuré : {p:.0%} de ces alertes moyennes étaient des fraudes (contre {st['other'][1]:.0%} pour les autres)."
    return txt


# ================================================================= 2. analogs: most similar labelled alerts (0 token)
@lru_cache(maxsize=1)
def _vectors():
    q = da.queue()
    q = q.set_index("transaction_id")
    e = da.explanations()
    e = e[e.source.isin(["model_for", "model_against"]) & e.transaction_id.isin(q.index)]
    x = e.pivot_table(index="transaction_id", columns="feature", values="points", aggfunc="sum", fill_value=0.0)
    ch = pd.get_dummies(q.channel).astype(float) * 0.5          # same channel counts, but less than the model's reasons
    x = x.join(ch, how="outer").fillna(0.0)
    v = x.values / np.maximum(np.linalg.norm(x.values, axis=1, keepdims=True), 1e-9)
    return x.index, v, q.loc[x.index, ["period", "is_fraud", "fraud_scenario", "risk_level"]]


def analogs(tid, k=25):
    """The k labelled validation alerts whose model reasons look most like this one (leave-one-out)."""
    idx, v, meta = _vectors()
    pos = {t: i for i, t in enumerate(idx)}
    if tid not in pos or meta.risk_level.iloc[pos[tid]] == "FAIBLE":   # a cleared operation is not compared with alerts
        return None
    ref = np.where((meta.period.values == "valid") & (meta.risk_level.values != "FAIBLE") & (idx != tid))[0]
    sims = v[ref] @ v[pos[tid]]
    top = ref[np.argsort(-sims)[:k]]
    m = meta.iloc[top]
    frauds = m[m.is_fraud == 1]
    return {"k": len(m), "frauds": int(len(frauds)), "rate": float(m.is_fraud.mean()),
            "scenarios": frauds.fraud_scenario.value_counts().head(3).to_dict(),
            "similarity": float(np.sort(sims)[::-1][:k].mean())}


# ================================================================= 3. evidence board (0 token)
def _fmt_amt(x):
    return f"{x:,.0f}".replace(",", " ")


def evidence(tid, lang="fr"):
    """Return (lines, meta). Each line: {"id", "kind": risk|calm|info, "text", "source"}."""
    en = lang == "en"
    L = (lambda fr, e: e) if en else (lambda fr, e: fr)
    q = da.queue().set_index("transaction_id")
    if tid not in q.index:
        return [], {}
    r = q.loc[tid]
    lines = []

    def add(kind, text, source):
        lines.append({"kind": kind, "text": text, "source": source})

    t = tools.get_transaction(tid)
    reco = t.get("recommandation_systeme") or {}
    if r.risk_level == "FAIBLE":
        add("info", L(f"Non alerté par le modèle (sous le seuil des 1 %) · recommandation système {reco.get('decision')} · "
                      f"moteur de règles actuel : {'alerte' if r.legacy_alert else 'pas d’alerte'}",
                      f"Not alerted by the model (below the top-1% threshold) · system recommendation {reco.get('decision')} · "
                      f"current rules: {'alert' if r.legacy_alert else 'no alert'}"), "score")
    else:
        add("info", L(f"Alerte {r.risk_level} · percentile {float(r.score_pct):.1%} · recommandation système {reco.get('decision')} "
                      f"(confiance {reco.get('confiance')}) · moteur actuel : {'alerte' if r.legacy_alert else 'pas d’alerte'}",
                      f"{r.risk_level} alert · percentile {float(r.score_pct):.1%} · system recommendation {reco.get('decision')} "
                      f"({reco.get('confiance')}) · current rules: {'alert' if r.legacy_alert else 'no alert'}"), "score")

    if r.risk_level == "FAIBLE":
        m = da.metrics()
        a = q[(q.period == "valid") & (q.risk_level != "FAIBLE")]
        missed = (float(m["valid_frauds"]) - a.is_fraud.sum()) / max(float(m["valid_rows"]) - len(a), 1)
        add("calm", L(f"En validation, seulement {missed:.2%} des opérations non alertées par le modèle étaient des fraudes",
                      f"In validation, only {missed:.2%} of the operations not alerted by the model were fraud"), "score")

    w = _watch_raw(r.period)
    if tid in w.index and w.loc[tid, "prior_72h"] > 0:
        x = w.loc[tid]
        prev = "; ".join(f"{p['id']} {p['ts']:%d/%m %H:%M} {p['amount']:.0f} TND {p['risk']}" for p in x.prior)
        stt = watch_stats()
        p = stt.get(x.level or "creuser", (0, None))[1] if x.risk_level == "MOYEN" else None
        add("risk", L(f"{x.prior_72h} alerte(s) du même client dans les 72 h avant ({prev})"
                      + (f" ; en validation {p:.0%} de ces cas étaient des fraudes vs {stt['other'][1]:.0%}" if p is not None else ""),
                      f"{x.prior_72h} alert(s) for the same customer in the previous 72 h ({prev})"
                      + (f"; in validation {p:.0%} of such cases were fraud vs {stt['other'][1]:.0%}" if p is not None else "")),
            "watch")

    h = tools.compare_to_habits(tid)
    ec = h.get("ecarts", {})
    if ec:
        ratio = ec.get("ratio_vs_moyenne")
        if ratio and ratio >= 2:
            add("risk", L(f"Montant {_fmt_amt(ec['montant'])} TND = ×{ratio} la moyenne du client ({_fmt_amt(ec['montant_moyen'])} TND)"
                          + (", au-dessus de son maximum passé" if ec.get("au_dessus_du_max_passe") else ""),
                          f"Amount {_fmt_amt(ec['montant'])} TND = ×{ratio} the customer's average ({_fmt_amt(ec['montant_moyen'])} TND)"
                          + (", above any past amount" if ec.get("au_dessus_du_max_passe") else "")), "habits")
        elif ratio is not None and ec.get("montant", 0) <= ec.get("montant_p95", 0):
            add("calm", L(f"Montant dans les habitudes (≤ 95e centile, ×{ratio} la moyenne)",
                          f"Amount within habits (≤ 95th percentile, ×{ratio} the average)"), "habits")
        new = [n for k, n in [("commercant_deja_vu", L("commerçant", "merchant")), ("ville_deja_vue", L("ville", "city")),
                              ("appareil_deja_vu", L("appareil", "device")), ("beneficiaire_deja_vu", L("bénéficiaire", "beneficiary")),
                              ("pays_deja_vu_en_physique", L("pays (physique)", "country (in person)"))] if ec.get(k) is False]
        known = [n for k, n in [("commercant_deja_vu", L("commerçant", "merchant")), ("ville_deja_vue", L("ville", "city")),
                                ("appareil_connu_depuis_plus_de_24h", L("appareil > 24 h", "device > 24 h"))] if ec.get(k) is True]
        if new:
            add("risk", L("Jamais vu pour ce client : " + ", ".join(new), "Never seen for this customer: " + ", ".join(new)), "habits")
        if known:
            add("calm", L("Déjà connu du client : " + ", ".join(known), "Already known for this customer: " + ", ".join(known)), "habits")
        mins = ec.get("minutes_depuis_operation_precedente")
        if ec.get("operations_24h_avant", 0) >= 4 or (mins is not None and mins < 10):
            add("risk", L(f"Rythme : {ec.get('operations_24h_avant')} opérations en 24 h, la précédente {mins} min avant",
                          f"Pace: {ec.get('operations_24h_avant')} operations in 24 h, previous one {mins} min before"), "habits")
        if ec.get("refus_carte_1h_avant", 0) > 0:
            add("risk", L(f"{ec['refus_carte_1h_avant']} refus sur la carte dans l'heure précédente",
                          f"{ec['refus_carte_1h_avant']} card declines in the previous hour"), "habits")
        if ec.get("vitesse_implicite_kmh", 0) > 500:
            add("risk", L(f"Déplacement impossible : {ec['distance_operation_precedente_km']} km depuis l'opération précédente "
                          f"(≈ {ec['vitesse_implicite_kmh']:.0f} km/h)",
                          f"Impossible travel: {ec['distance_operation_precedente_km']} km from the previous operation "
                          f"(≈ {ec['vitesse_implicite_kmh']:.0f} km/h)"), "habits")
        if ec.get("heure", 12) < 6 and ec.get("part_nuit_passee", 1) < 0.05:
            add("risk", L(f"Opération à {ec['heure']} h alors que {ec['part_nuit_passee']:.0%} de ses opérations passées sont de nuit",
                          f"Operation at {ec['heure']}:00 while {ec['part_nuit_passee']:.0%} of past operations were at night"), "habits")

    ev = tools.get_digital_events(r.customer_id, around=tid, hours_before=48, hours_after=0)
    if ev.get("disponible"):
        evs = pd.DataFrame(ev.get("evenements", []))
        if len(evs):
            fails = int((evs.get("status") == "ECHEC").sum()) if "status" in evs else 0
            types = evs[evs.event_type != "CONNEXION"].event_type.value_counts().to_dict() if "event_type" in evs else {}
            foreign = sorted({c for c in evs.get("ip_country", pd.Series(dtype=str)).dropna() if c != "TN"})
            if fails or types or foreign:
                parts = []
                if fails:
                    parts.append(L(f"{fails} échec(s) de connexion", f"{fails} failed login(s)"))
                parts += [f"{n}× {k.lower().replace('_', ' ')}" for k, n in types.items()]
                if foreign:
                    parts.append(L("IP étrangère : ", "foreign IP: ") + ", ".join(foreign))
                add("risk", L("Banque digitale, 48 h avant : ", "Digital banking, 48 h before: ") + " · ".join(parts), "digital")

    rel = tools.find_related_cases(tid, days=30)
    for pc in rel.get("points_communs", []):
        if pc.get("cartes_fraudees_deja_signalees", 0) or pc.get("operations_en_alerte", 0):
            strong = pc.get("cartes_fraudees_deja_signalees", 0) > 0 or pc.get("autres_clients", 0) <= 5   # big shops = context
            add("risk" if strong else "info", L(f"{pc['type'].capitalize()} {pc['identifiant']} partagé avec {pc['autres_clients']} autre(s) client(s) en 30 j : "
                          f"{pc.get('cartes_fraudees_deja_signalees', 0)} carte(s) déjà fraudée(s), {pc.get('operations_en_alerte', 0)} alerte(s)",
                          f"{pc['type'].capitalize()} {pc['identifiant']} shared with {pc['autres_clients']} other customer(s) in 30 d: "
                          f"{pc.get('cartes_fraudees_deja_signalees', 0)} card(s) already defrauded, {pc.get('operations_en_alerte', 0)} alert(s)"),
                "network")

    try:
        ex = fx.exposures(r.period)
        hit = ex[ex.transaction_id == tid]
        if len(hit):
            cp = fx.compromise_points(r.period).set_index("merchant_id")
            names = [f"{cp.loc[m, 'merchant_name']} (×{cp.loc[m, 'lift']:.1f})" for m in hit.merchant_id if m in cp.index][:2]
            add("info", L("Carte passée par un point de compromission dans les 30 j : " + ", ".join(names)
                          + " — piste d'enquête, non prédictif seul",
                          "Card went through a point of compromise in the last 30 d: " + ", ".join(names)
                          + " — investigation lead, not predictive on its own"), "compromise")
    except Exception:
        pass

    cf_ = fx.counterfactual(tid)
    if cf_ and cf_["path"]:
        if cf_["alert"] and cf_["flip_at"] == 1:
            add("calm", L(f"Alerte fragile : sans le seul facteur « {cf_['path'][0]['facteur']} », le score passe sous le seuil",
                          f"Fragile alert: without the single factor “{cf_['path'][0]['facteur']}”, the score drops below the threshold"),
                "counterfactual")
        elif cf_["alert"] and cf_["flip_at"] is None:
            add("risk", L(f"Alerte robuste (renforce le soupçon) : le score reste au-dessus du seuil même sans ses {len(cf_['path'])} "
                          "principaux facteurs, donc plusieurs indices indépendants",
                          f"Robust alert (strengthens the suspicion): the score stays above the threshold even without its "
                          f"{len(cf_['path'])} main factors, so several independent clues"), "counterfactual")
        elif not cf_["alert"] and cf_["flip_at"] is None:
            add("calm", L(f"Dégagement robuste : même sans ses {len(cf_['path'])} facteurs rassurants, le score reste sous le seuil d'alerte",
                          f"Robust clearance: even without its {len(cf_['path'])} reassuring factors, the score stays below the alert threshold"),
                "counterfactual")

    an = analogs(tid)
    if an:
        sc = ", ".join(f"{SCEN[lang].get(s, s)} ({n})" for s, n in an["scenarios"].items())
        add("risk" if an["rate"] >= 0.4 else "calm" if an["rate"] <= 0.15 else "info",
            L(f"Sur les {an['k']} alertes validées les plus ressemblantes, {an['frauds']} étaient des fraudes ({an['rate']:.0%})"
              + (f" : {sc}" if sc else ""),
              f"Of the {an['k']} most similar validated alerts, {an['frauds']} were fraud ({an['rate']:.0%})" + (f": {sc}" if sc else "")),
            "analogs")

    dec = tools.decisions()
    if len(dec):
        cust_tx = set(da.customer_tx(r.customer_id).transaction_id) if hasattr(da, "customer_tx") else set()
        mine = dec[dec.transaction_id.isin(cust_tx) & (dec.transaction_id != tid)]
        if len(mine):
            last = mine.iloc[-1]
            add("info", L(f"Décisions passées de l'analyste sur ce client : {len(mine)} (dernière : {last.decision} sur {last.transaction_id})",
                          f"Analyst's past decisions on this customer: {len(mine)} (last: {last.decision} on {last.transaction_id})"),
                "decisions")

    for i, x in enumerate(lines, 1):
        x["id"] = f"E{i}"
    return lines, {"reco": reco, "analogs": an, "customer": r.customer_id, "period": r.period}


# ================================================================= 4. the single LLM call
SYSTEM = {
    "fr": """Tu es enquêteur fraude senior dans une banque tunisienne. On te donne des PREUVES numérotées (E1…), calculées sur les données de la banque.
Relie les preuves entre elles pour trouver le scénario le plus probable. Réponds en français, 110 mots maximum, exactement ces 5 lignes :
**Hypothèse** : scénario le plus probable + force (faible / moyenne / forte)
**Preuves décisives** : 2 ou 3 identifiants E avec la raison en une phrase
**Ce qui affaiblit** : la meilleure preuve contraire (identifiant E) ou « aucune »
**Vérification** : une action concrète et courte pour l'analyste
**Orientation** : UN seul mot choisi parmi RENFORCER, LEVER ou INCERTAIN, cohérent avec ton hypothèse (fraude probable → RENFORCER ; opération probablement légitime → LEVER), suivi de « — l'analyste décide »
Une preuve [+] soutient la fraude, une preuve [-] l'affaiblit : ne cite jamais une preuve [+] dans « Ce qui affaiblit ».
Uniquement les preuves fournies, aucun fait inventé, pas de données brutes, pas de consignes recopiées.""",
    "en": """You are a senior fraud investigator in a Tunisian bank. You are given numbered EVIDENCE (E1…), computed on the bank's data.
Connect the evidence to find the most likely scenario. Answer in English, 110 words max, exactly these 5 lines:
**Hypothesis**: most likely scenario + strength (weak / medium / strong)
**Decisive evidence**: 2 or 3 E ids with the reason in one sentence
**What weakens it**: the best counter-evidence (E id) or "none"
**Check**: one short, concrete action for the analyst
**Direction**: ONE word chosen from STRENGTHEN, LIFT or UNCERTAIN, consistent with your hypothesis (likely fraud → STRENGTHEN; likely legitimate → LIFT), followed by "— the analyst decides"
A [+] line supports fraud, a [-] line weakens it: never cite a [+] line under "What weakens it".
Only the evidence given, no invented facts, no raw data, never repeat these instructions.""",
}


def _board(lines):
    tag = {"risk": "+", "calm": "-", "info": "·"}
    return "\n".join(f"{x['id']} [{tag[x['kind']]}] {x['text']}" for x in lines)


def _offline(lines, meta, lang):
    en = lang == "en"
    risk = [x for x in lines if x["kind"] == "risk"]
    calm = [x for x in lines if x["kind"] == "calm"]
    an = meta.get("analogs") or {}
    scen = next(iter(an.get("scenarios", {})), None)
    rate = an.get("rate")
    force = ("forte" if rate >= 0.5 else "moyenne" if rate >= 0.25 else "faible") if rate is not None else "moyenne"
    orient = ("RENFORCER" if rate >= 0.4 else "LEVER" if rate <= 0.15 else "INCERTAIN") if rate is not None else "INCERTAIN"
    if en:
        force = {"forte": "strong", "moyenne": "medium", "faible": "weak"}[force]
        orient = {"RENFORCER": "STRENGTHEN", "LEVER": "LIFT", "INCERTAIN": "UNCERTAIN"}[orient]
        return (f"**Hypothesis**: {SCEN['en'].get(scen, 'unclear scenario')} ({force})\n"
                f"**Decisive evidence**: {' + '.join(x['id'] for x in risk[:3]) or 'none'}\n"
                f"**What weakens it**: {calm[0]['id'] if calm else 'none'}\n"
                f"**Check**: call the customer to confirm the operation before deciding\n"
                f"**Direction**: {orient} — the analyst decides")
    return (f"**Hypothèse** : {SCEN['fr'].get(scen, 'scénario incertain')} ({force})\n"
            f"**Preuves décisives** : {' + '.join(x['id'] for x in risk[:3]) or 'aucune'}\n"
            f"**Ce qui affaiblit** : {calm[0]['id'] if calm else 'aucune'}\n"
            f"**Vérification** : appeler le client pour confirmer l'opération avant de décider\n"
            f"**Orientation** : {orient} — l'analyste décide")


def investigate(tid, lang="fr", on_token=None):
    """Evidence board (0 token) + one LLM call. Returns {"lines", "meta", "answer", "tokens", "mode", "cached", "latency_s"}."""
    lang = "en" if lang == "en" else "fr"
    emit = on_token or (lambda t: None)
    start = time.time()
    lines, meta = evidence(tid, lang)
    board = _board(lines)
    key = hashlib.sha256(f"{PROMPT_VERSION}|{lang}|{tid}|{board}".encode()).hexdigest()
    cache = copilot._cache
    if key in cache and (copilot.configured() or os.getenv("COPILOT_OFFLINE", "0") != "1"):
        out = {**cache[key], "lines": lines, "meta": meta, "cached": True, "latency_s": round(time.time() - start, 2)}
        emit(out["answer"])
        copilot._log({"ts": datetime.now(), "question": "Enquête approfondie", "context_tx": tid, "lang": lang, "intent": "deepsearch",
                      "mode": out["mode"], "cached": True, "tools": [], "tokens": {"prompt": 0, "completion": 0, "total": 0}})
        return out
    tokens = {"prompt": 0, "completion": 0, "total": 0, "cached_prompt": 0}
    if not copilot.configured():
        answer, mode = _offline(lines, meta, lang), "hors-ligne (règles)"
        emit(answer)
    else:
        mode = f"Azure OpenAI ({os.environ['AZURE_OPENAI_DEPLOYMENT']})"
        try:
            answer, tokens = _call(lang, board, emit)
            if _contradicts(answer):              # rare: hypothesis and direction disagree -> one retry with more reasoning
                emit(None)
                answer, t2 = _call(lang, board, emit, effort="low")
                tokens = {k: tokens.get(k, 0) + t2.get(k, 0) for k in t2}
                tokens["retry"] = 1
        except Exception as exc:
            answer, mode = _offline(lines, meta, lang), "hors-ligne (règles)"
            emit(answer)
            tokens["error"] = str(exc)[:200]
    out = {"answer": answer, "tokens": tokens, "mode": mode, "n_evidence": len(lines)}
    if mode.startswith("Azure") and answer.strip():
        cache[key] = out
        copilot._save_cache()
    copilot._log({"ts": datetime.now(), "question": "Enquête approfondie", "context_tx": tid, "lang": lang, "intent": "deepsearch",
                  "mode": mode, "cached": False, "tools": [], "tokens": tokens, "rounds": 1,
                  "latency_s": round(time.time() - start, 2), "answer": answer})
    return {**out, "lines": lines, "meta": meta, "cached": False, "latency_s": round(time.time() - start, 2)}


def _contradicts(answer):
    """0-token consistency check between the hypothesis line and the direction line."""
    hyp = re.search(r"(?im)^\W*(hypoth[eè]se|hypothesis)\W*:?(.*)$", answer)
    ori = re.search(r"(?im)^\W*(orientation|direction)\W*:?\W*(\w+)", answer)
    if not hyp or not ori:
        return False
    legit = re.search(r"l[ée]gitime|legitimate|non frauduleu|not fraud", hyp.group(2), re.I)
    strengthen = ori.group(2).upper() in ("RENFORCER", "STRENGTHEN")
    lift = ori.group(2).upper() in ("LEVER", "LIFT")
    return bool((legit and strengthen) or (not legit and re.search(r"fraud", hyp.group(2), re.I) and lift))


def _call(lang, board, emit, effort=None):
    client = copilot._client()
    messages = [{"role": "system", "content": SYSTEM[lang]},
                {"role": "user", "content": ("PREUVES ([+] risque, [-] rassurant, [·] contexte) :\n" if lang == "fr"
                                             else "EVIDENCE ([+] risk, [-] reassuring, [·] context):\n") + board}]
    kwargs = dict(model=os.environ["AZURE_OPENAI_DEPLOYMENT"], messages=messages, stream=True,
                  stream_options={"include_usage": True})
    if copilot._is_reasoning():
        kwargs.update(max_completion_tokens=1400, reasoning_effort=effort or os.getenv("DEEP_REASONING", "minimal"))
    else:
        kwargs.update(temperature=0.1, max_tokens=300)
    try:
        stream = client.chat.completions.create(**kwargs)
    except Exception as exc:                 # older API versions do not accept "minimal"
        if kwargs.get("reasoning_effort") != "minimal" or "reasoning_effort" not in str(exc):
            raise
        kwargs["reasoning_effort"] = "low"
        stream = client.chat.completions.create(**kwargs)
    answer, usage = "", None
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            answer += chunk.choices[0].delta.content
            emit(chunk.choices[0].delta.content)
    tokens = {"prompt": 0, "completion": 0, "total": 0, "cached_prompt": 0}
    if usage:
        details = getattr(usage, "prompt_tokens_details", None)
        tokens = {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens, "total": usage.total_tokens,
                  "cached_prompt": getattr(details, "cached_tokens", 0) or 0}
    return answer.strip(), tokens
