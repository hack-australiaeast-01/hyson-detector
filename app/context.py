"""Personal context: is this operation coherent with THIS customer's life? (bank CEO's question: Amm Mohamed abroad.)

For a physical operation away from the customer's usual places (abroad, or in a city he rarely visits), we read only facts the bank
already holds — never a guess about religion, health, family or opinions (sensitive data, Tunisian law 2004-63 / GDPR art. 9):

  previous trips to this place · travel preparation (airline / agency / hotel purchases) · a stay already in progress ·
  time since the last payment in Tunisia (impossible travel) · chip vs magnetic stripe · ATM vs shop · amount vs his own habits and
  income · a kind of shop he never uses · his phone already logged in from that country · many customers of the bank travelling
  there right now (seasonal wave: summer, holidays, pilgrimage season… at population level, never attributed to a person) ·
  how common this trip is for customers of the same age band and segment · a travel notice he declared.

Each signal is weighed by its fraud rate MEASURED on the 2025 labelled operations (log likelihood ratio, `context_weights.json`,
fitted by `build_context.py` and tested on 2026); only data before the operation is used. Works for any new operation
(another bank's feed, a typed operation, a CSV) as soon as it arrives: no retraining.
"""
import json
import math
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
WEIGHTS_FILE = Path(__file__).parent / "context_weights.json"
NOTICES = DATA / "travel_notices.csv"
PHYSICAL = ("TPE", "DAB")
TRAVEL_PREP = ("Compagnie aerienne", "Agence de voyage", "Hotellerie")
COUNTRY = {"TN": "Tunisie", "FR": "France", "IT": "Italie", "SA": "Arabie saoudite", "TR": "Turquie", "DE": "Allemagne", "ES": "Espagne",
           "AE": "Émirats arabes unis", "MA": "Maroc", "GB": "Royaume-Uni", "EG": "Égypte", "QA": "Qatar", "DZ": "Algérie", "RO": "Roumanie",
           "RU": "Russie", "ID": "Indonésie", "CN": "Chine", "BE": "Belgique", "CA": "Canada", "NG": "Nigeria", "VN": "Viêt Nam",
           "BR": "Brésil", "LY": "Libye", "PL": "Pologne", "UA": "Ukraine", "US": "États-Unis", "IN": "Inde", "CH": "Suisse", "NL": "Pays-Bas"}
NEVER = ["religion ou pratique religieuse", "santé", "famille ou relations", "opinions", "origine"]

# human labels of each signal value (FR, EN) — the evidence shown to the analyst
LABELS = {
    ("visite_lieu", "oui"): ("A déjà payé sur place lors d'un voyage précédent", "Already paid there on a previous trip"),
    ("visite_lieu", "non"): ("Premier paiement physique à cet endroit", "First physical payment at this place"),
    ("deja_ailleurs", "oui"): ("Voyage déjà hors de chez lui auparavant", "Has travelled away from home before"),
    ("deja_ailleurs", "non"): ("Jamais de paiement physique loin de chez lui auparavant", "Never paid physically away from home before"),
    ("preparation", "oui"): ("Préparation de voyage dans les 90 jours (billet, agence ou hôtel)", "Travel preparation in the last 90 days (ticket, agency or hotel)"),
    ("preparation", "non"): ("Aucun achat de voyage dans les 90 jours", "No travel purchase in the last 90 days"),
    ("sejour", "en_cours"): ("Séjour en cours : déjà des paiements sur place ces 10 derniers jours", "Stay in progress: already paid there in the last 10 days"),
    ("sejour", "debut"): ("Premier paiement du séjour", "First payment of the stay"),
    ("absence", "impossible"): ("Paiement physique ailleurs il y a moins de 3 h : déplacement impossible", "Physical payment elsewhere less than 3 h ago: impossible travel"),
    ("absence", "moins_24h"): ("Dernier paiement physique ailleurs il y a 3 à 24 h", "Last physical payment elsewhere 3–24 h ago"),
    ("absence", "1_7j"): ("Dernier paiement physique ailleurs il y a 1 à 7 jours", "Last physical payment elsewhere 1–7 days ago"),
    ("absence", "plus_7j"): ("Pas de paiement physique ailleurs depuis plus de 7 jours", "No physical payment elsewhere for more than 7 days"),
    ("mode", "CHIP"): ("Carte lue par la puce", "Card read by the chip"),
    ("mode", "SANS_CONTACT"): ("Paiement sans contact", "Contactless payment"),
    ("mode", "MAGSTRIPE"): ("Piste magnétique (typique d'une carte copiée)", "Magnetic stripe (typical of a cloned card)"),
    ("canal", "TPE"): ("Paiement en magasin (moins risqué que le distributeur à l'étranger)", "Payment in a shop (less risky than an ATM abroad)"),
    ("canal", "DAB"): ("Retrait au distributeur à l'étranger (cible du skimming)", "Cash withdrawal at an ATM abroad (skimming target)"),
    ("montant", "habituel"): ("Montant dans ses habitudes", "Amount within his habits"),
    ("montant", "eleve"): ("Montant au-dessus de 95 % de ses opérations", "Amount above 95% of his operations"),
    ("montant", "hors_norme"): ("Montant hors norme : > 3 fois son p95 ou > son revenu mensuel", "Out-of-pattern amount: > 3× his p95 or > his monthly income"),
    ("categorie", "connue"): ("Type de commerce qu'il fréquente déjà", "A kind of shop he already uses"),
    ("categorie", "nouvelle"): ("Type de commerce jamais utilisé par ce client", "A kind of shop this customer never uses"),
    ("telephone", "sur_place"): ("Son application s'est connectée depuis ce pays, appareil connu", "His app logged in from this country on a known device"),
    ("telephone", "suspect"): ("Connexion échouée ou nouvel appareil depuis ce pays", "Failed login or new device from this country"),
    ("affluence", "pic"): ("Beaucoup de clients de la banque y voyagent en ce moment (vague saisonnière)", "Many of the bank's customers are travelling there right now (seasonal wave)"),
    ("affluence", "normale"): ("Pas de vague de voyages vers cet endroit en ce moment", "No travel wave to this place right now"),
    ("profil", "frequent"): ("Destination fréquente pour les clients de son âge et de son segment", "A frequent destination for customers of his age and segment"),
    ("profil", "rare"): ("Destination rare pour les clients de son âge et de son segment", "A rare destination for customers of his age and segment"),
    ("avis", "oui"): ("Avis de voyage déclaré par le client pour ces dates", "Travel notice declared by the customer for these dates"),
}
BANDS = [("coherent", "Voyage cohérent", "Coherent trip", "#16A34A"), ("verifier", "À confirmer", "To confirm", "#C77700"),
         ("incoherent", "Peu cohérent", "Hardly consistent", "#D92D20")]


def _age_band(age):
    a = float(age or 0)
    return "18–24" if a < 25 else "25–34" if a < 35 else "35–44" if a < 45 else "45–59" if a < 60 else "60–69" if a < 70 else "70 et +"


def place_of(tx, home_city=None):
    """Where the operation happened: the country abroad, the city in Tunisia. None if not physical or at home."""
    if tx.get("channel") not in PHYSICAL:
        return None, None
    if tx.get("country") and tx["country"] != "TN":
        return "abroad", tx["country"]
    city = tx.get("city")
    if city and home_city and city != home_city:
        return "domestic", city
    return None, None


def place_label(scope, place, lang="fr"):
    if scope == "abroad":
        name = COUNTRY.get(place, place)
        return name if lang != "en" else {"Tunisie": "Tunisia", "Italie": "Italy", "Arabie saoudite": "Saudi Arabia", "Turquie": "Turkey",
                                         "Allemagne": "Germany", "Espagne": "Spain", "Maroc": "Morocco", "Royaume-Uni": "United Kingdom",
                                         "Égypte": "Egypt", "Algérie": "Algeria"}.get(name, name)
    return place


# ---------------------------------------------------------------- signals (pure: tx + data strictly before it)
def signals(tx, hist, profile, ip_events=None, daily=None, prof_table=None, notices=None):
    """tx: dict (timestamp, channel, entry_mode, merchant_category, amount_tnd, city, country); hist: the customer's operations BEFORE tx
    (columns timestamp, channel, entry_mode, merchant_category, amount_tnd, city, country); profile: dict (age, segment, home_city,
    monthly_income_tnd). Returns (scope, place, {signal: value})."""
    ts = pd.Timestamp(tx["timestamp"])
    scope, place = place_of(tx, profile.get("home_city"))
    if scope is None:
        return None, None, {}
    h = hist[hist.timestamp < ts] if len(hist) else hist
    phys = h[h.channel.isin(PHYSICAL)] if len(h) else h
    here = (phys.country == place) if scope == "abroad" else ((phys.country == "TN") & (phys.city == place))
    s = {}
    s["visite_lieu"] = "oui" if len(phys) and (here & (phys.timestamp < ts - timedelta(days=30))).any() else "non"
    away = (phys.country != "TN") if scope == "abroad" else ((phys.country == "TN") & (phys.city != profile.get("home_city")))
    s["deja_ailleurs"] = "oui" if len(phys) and (away & (phys.timestamp < ts - timedelta(days=30))).any() else "non"
    if scope == "abroad":
        s["preparation"] = "oui" if len(h) and (h.merchant_category.isin(TRAVEL_PREP) & (h.timestamp >= ts - timedelta(days=90))).any() else "non"
    s["sejour"] = "en_cours" if len(phys) and (here & (phys.timestamp >= ts - timedelta(days=10))).any() else "debut"
    elsewhere = phys[~here] if len(phys) else phys
    if len(elsewhere):
        hrs = (ts - elsewhere.timestamp.max()).total_seconds() / 3600
        s["absence"] = "impossible" if hrs < 3 and scope == "abroad" else "moins_24h" if hrs < 24 else "1_7j" if hrs < 168 else "plus_7j"
    else:
        s["absence"] = "plus_7j"
    s["mode"] = tx.get("entry_mode") if tx.get("entry_mode") in ("CHIP", "SANS_CONTACT", "MAGSTRIPE") else "CHIP"
    s["canal"] = tx["channel"]
    amt = float(tx.get("amount_tnd") or 0)
    p95 = float(h.amount_tnd.quantile(0.95)) if len(h) >= 20 else None
    inc = float(profile.get("monthly_income_tnd") or 0)
    if (p95 and amt > 3 * p95) or (inc and amt > inc):
        s["montant"] = "hors_norme"
    elif p95 and amt > p95:
        s["montant"] = "eleve"
    else:
        s["montant"] = "habituel"
    if tx["channel"] == "TPE" and tx.get("merchant_category"):
        s["categorie"] = "connue" if len(h) and (h.merchant_category == tx["merchant_category"]).any() else "nouvelle"
    if scope == "abroad" and ip_events is not None and len(ip_events):
        e = ip_events[(ip_events.timestamp < ts) & (ip_events.timestamp >= ts - timedelta(hours=72)) & (ip_events.ip_country == place)]
        if len(e):
            ok = (e.status == "SUCCES") & e.known_device.astype(bool)
            s["telephone"] = "sur_place" if ok.any() else "suspect"
    if daily is not None and len(daily):
        d = daily[daily.place == place]
        day = ts.normalize()
        now = d[(d.date < day) & (d.date >= day - timedelta(days=14))].n.sum()
        base = d[(d.date < day - timedelta(days=14)) & (d.date >= day - timedelta(days=379))].n.sum() / 26.0
        if base >= 2:
            s["affluence"] = "pic" if now >= 1.5 * base else "normale"
    if prof_table is not None and len(prof_table):
        r = prof_table[(prof_table.segment == profile.get("segment")) & (prof_table.tranche_age == _age_band(profile.get("age")))
                       & (prof_table.place == place)]
        share = float(r.share.iloc[0]) if len(r) else 0.0
        s["profil"] = "frequent" if share >= (0.05 if scope == "abroad" else 0.15) else "rare"
    if notices is not None and len(notices):
        n = notices[(notices.customer_id == profile.get("customer_id")) & (notices.place == place)
                    & (pd.to_datetime(notices.start) <= ts) & (pd.to_datetime(notices.end) + timedelta(days=1) > ts)]
        if len(n):
            s["avis"] = "oui"
    return scope, place, s


# ---------------------------------------------------------------- scoring (weights measured on 2025, tested on 2026)
def load_weights():
    return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8")) if WEIGHTS_FILE.exists() else None


def score(scope, sig, weights=None):
    w = (weights or load_weights() or {}).get(scope)
    if not w:
        return None
    logit = w["prior"]
    contrib = []
    for k, v in sig.items():
        lr = w["lr"].get(k, {}).get(v)
        if k == "avis" and v == "oui":
            lr = w.get("notice_lr", -2.5)                     # declared by the customer: policy weight, not measured (no data yet)
        if lr is None:
            continue
        logit += lr
        contrib.append((k, v, lr))
    p = 1 / (1 + math.exp(-logit))
    band = "coherent" if p < w["cut_low"] else "incoherent" if p >= w["cut_high"] else "verifier"
    return {"p": p, "band": band, "contrib": sorted(contrib, key=lambda x: x[2]), "measured": w["bands"].get(band, {})}


# ---------------------------------------------------------------- app helpers
_cache = {}


def _table(name):
    if name not in _cache:
        p = DATA / f"{name}.parquet"
        _cache[name] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    return _cache[name]


def notices():
    if NOTICES.exists():
        return pd.read_csv(NOTICES)
    return pd.DataFrame(columns=["customer_id", "place", "start", "end", "declared_at", "by"])


def add_notice(customer_id, place, start, end, by="analyste"):
    from datetime import datetime
    n = notices()
    n = pd.concat([n, pd.DataFrame([{"customer_id": customer_id, "place": place, "start": str(start), "end": str(end),
                                     "declared_at": datetime.now().isoformat(timespec="seconds"), "by": by}])], ignore_index=True)
    NOTICES.parent.mkdir(exist_ok=True)
    n.to_csv(NOTICES, index=False)


def _ip_events(customer_id, until):
    import data_access as da
    try:
        ev = da.events(customer_id)
    except Exception:
        return None
    if ev is None or not len(ev) or "ip_country" not in ev:
        return None
    ev = ev.copy()
    ev["timestamp"] = pd.to_datetime(ev.timestamp)
    seen = ev[ev.timestamp < pd.Timestamp(until) - timedelta(hours=24)].device_id.dropna().unique()
    ev["known_device"] = ev.device_id.isin(seen)
    return ev[ev.ip_country.notna() & (ev.ip_country != "TN") & (ev.event_type == "CONNEXION")]


def assess(tx, customer_id, hist=None, lang="fr"):
    """Full assessment of one operation (existing or new) for one customer of the bank."""
    import data_access as da
    c = da.customers()
    row = c[c.customer_id == customer_id] if c is not None else pd.DataFrame()
    profile = row.iloc[0].to_dict() if len(row) else {"customer_id": customer_id}
    if hist is None:
        hist = da.customer_tx(customer_id)
    hist = hist.copy()
    hist["timestamp"] = pd.to_datetime(hist.timestamp)
    tx = dict(tx)
    tx["timestamp"] = pd.Timestamp(tx["timestamp"])
    scope, place, sig = signals(tx, hist, profile, _ip_events(customer_id, tx["timestamp"]), _table("feat_ctx_daily"),
                                _table("feat_ctx_profile"), notices())
    if scope is None:
        return {"scope": None, "profile": profile}
    sc = score(scope, sig)
    return {"scope": scope, "place": place, "place_label": place_label(scope, place, lang), "signals": sig, "score": sc,
            "profile": profile, "n_history": int((hist.timestamp < tx["timestamp"]).sum()), "tx": tx}


def evidence(res, lang="fr"):
    """For / against lists in plain words, strongest first, with the measured effect."""
    i = 1 if lang == "en" else 0
    pro, con = [], []
    for k, v, lr in res["score"]["contrib"] if res.get("score") else []:
        lab = LABELS.get((k, v))
        if not lab or abs(lr) < 0.15:
            continue
        x = math.exp(abs(lr))
        item = {"text": lab[i], "effect": (f"risque ÷{x:.1f}" if lr < 0 else f"risque ×{x:.1f}") if lang != "en" else
                (f"risk ÷{x:.1f}" if lr < 0 else f"risk ×{x:.1f}"), "lr": lr, "signal": k}
        (pro if lr < 0 else con).append(item)
    return pro, sorted(con, key=lambda d: -d["lr"])


def contact_script(res, lang="fr"):
    """What to say to the customer: respectful, no detail he did not give us, no assumption about why he travels."""
    place = res.get("place_label", "")
    band = res["score"]["band"] if res.get("score") else "verifier"
    if lang == "en":
        if band == "coherent":
            return ("No call needed. Optional notification: \"We saw your card used in " + place + ". If it's you, nothing to do — have a good stay. "
                    "If not, reply STOP and we block it.\"")
        if band == "incoherent":
            return ("Block first, then call: \"Hello, this is your bank's security service. An operation that doesn't look like your usual use of "
                    "the card was attempted. To protect you we have paused the card. Can you confirm whether you are making this purchase?\" "
                    "Never mention where you think he is or why.")
        return ("Call: \"Hello, your bank here, a quick security check: was the card payment in " + place + " made by you? "
                "If yes, everything continues normally; you can also declare your trips in the app so we don't disturb you.\"")
    if band == "coherent":
        return ("Pas d'appel nécessaire. Notification facultative : « Nous avons vu un paiement par votre carte en " + place + ". Si c'est vous, "
                "rien à faire — bon séjour. Sinon, répondez STOP et nous la bloquons. »")
    if band == "incoherent":
        return ("Bloquer d'abord, puis appeler : « Bonjour, service sécurité de votre banque. Une opération qui ne ressemble pas à votre utilisation "
                "habituelle de la carte a été tentée ; par précaution, la carte est suspendue. Pouvez-vous nous confirmer si vous êtes à l'origine "
                "de cet achat ? » Ne jamais dire où l'on pense qu'il se trouve ni pourquoi.")
    return ("Appeler : « Bonjour, votre banque, une vérification de sécurité rapide : le paiement par carte en " + place + ", c'est bien vous ? "
            "Si oui, tout continue normalement ; vous pouvez aussi déclarer vos voyages dans l'application pour qu'on ne vous dérange pas. »")


def narrative(res, lang="fr"):
    """Optional: one short Azure OpenAI call that turns the computed evidence into 3 sentences. Facts only, no sensitive inference."""
    import copilot
    if not copilot.configured() or not res.get("score"):
        return None
    pro, con = evidence(res, lang)
    p = res["profile"]
    facts = {"lieu": res["place_label"], "type_lieu": "étranger" if res["scope"] == "abroad" else "ville de Tunisie hors domicile",
             "verdict": dict((b[0], b[1 if lang != "en" else 2]) for b in BANDS)[res["score"]["band"]],
             "fraude_mesuree_dans_ce_niveau": res["score"]["measured"].get("fraud_rate"),
             "profil": {"tranche_age": _age_band(p.get("age")), "segment": p.get("segment")},
             "operation": {k: str(res["tx"].get(k)) for k in ("timestamp", "amount_tnd", "channel", "entry_mode", "merchant_category")},
             "elements_coherents": [x["text"] for x in pro], "elements_inquietants": [x["text"] for x in con]}
    sysmsg = ("Tu aides un analyste fraude à lire le contexte personnel d'une opération. 3 phrases maximum, puis une recommandation d'action. "
              "Uniquement à partir des faits fournis. INTERDIT : supposer ou mentionner une religion, un pèlerinage, une maladie, une famille, "
              "une origine ou une opinion ; ne jamais dire pourquoi le client voyage. Parle de « voyage », « séjour », « habitudes ». "
              + ("Answer in English." if lang == "en" else "Réponds en français."))
    kw = dict(model=copilot.os.environ["AZURE_OPENAI_DEPLOYMENT"],
              messages=[{"role": "system", "content": sysmsg},
                        {"role": "user", "content": json.dumps(copilot._sanitize(facts), ensure_ascii=False, default=str)}])
    if copilot._is_reasoning():
        kw.update(max_completion_tokens=900, reasoning_effort="minimal")
    else:
        kw.update(temperature=0, max_tokens=250)
    try:
        r = copilot._client().chat.completions.create(**kw)
        return copilot.polish((r.choices[0].message.content or "").strip(), lang)
    except Exception:
        return None


def batch(df, lang="fr"):
    """New operations from a bank feed (our schema): assessed in time order, each against the customer's history AND the earlier rows
    of the same feed — usable the moment the data arrives."""
    import data_access as da
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df.timestamp)
    df = df.sort_values("timestamp")
    out = []
    seen = {}
    for r in df.to_dict("records"):
        cid = r.get("customer_id")
        if cid not in seen:
            try:
                seen[cid] = da.customer_tx(cid)[["timestamp", "channel", "entry_mode", "merchant_category", "amount_tnd", "city", "country"]].copy()
            except Exception:
                seen[cid] = pd.DataFrame(columns=["timestamp", "channel", "entry_mode", "merchant_category", "amount_tnd", "city", "country"])
            seen[cid]["timestamp"] = pd.to_datetime(seen[cid].timestamp)
        res = assess(r, cid, hist=seen[cid], lang=lang)
        sc = res.get("score") or {}
        pro, con = evidence(res, lang) if sc else ([], [])
        out.append({"transaction_id": r.get("transaction_id"), "customer_id": cid, "timestamp": r["timestamp"], "lieu": res.get("place_label"),
                    "montant_tnd": r.get("amount_tnd"), "verdict": sc.get("band", "domicile / en ligne"), "proba_fraude": round(sc["p"], 3) if sc else None,
                    "pour": " · ".join(x["text"] for x in pro[:2]), "contre": " · ".join(x["text"] for x in con[:2])})
        seen[cid] = pd.concat([seen[cid], pd.DataFrame([{k: r.get(k) for k in seen[cid].columns}])], ignore_index=True)
    return pd.DataFrame(out)
