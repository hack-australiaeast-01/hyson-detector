"""Find a customer by description ("le client retraité de Sfax de plus de 60 ans avec des alertes").

Why not free SQL from the LLM: the question is turned into a small set of *approved* filters (city, segment,
occupation, age, KYC, income, alerts), applied by a read-only function; it returns a short list of profiles and
alert counts, never raw transaction rows. Zero tokens, deterministic, FR/EN, works offline. On a real bank
database the same filters run as a parameterised query; personal identifiers stay masked.
"""
import re
import unicodedata

import pandas as pd

import data_access as da


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


SEGMENTS = {"Etudiant": ["etudiant", "etudiante", "student"], "Retraite": ["retraite", "retraitee", "retired", "pensioner", "senior"],
            "Premium": ["premium", "vip", "haut de gamme"], "Professionnel": ["professionnel", "professional", "business client", "pro "],
            "Particulier": ["particulier", "individual", "retail customer"]}
OCCUPATIONS = {"Architecte": ["architecte", "architect"], "Artisan": ["artisan", "craftsman"], "Avocat": ["avocat", "lawyer"],
               "Cadre superieur": ["cadre superieur", "cadre", "executive", "manager"],
               "Chef d'entreprise": ["chef d entreprise", "business owner", "ceo", "entrepreneur"],
               "Commercant": ["commercant", "shopkeeper", "merchant", "trader"], "Comptable": ["comptable", "accountant"],
               "Employe": ["employe", "employee", "clerk"], "Enseignant": ["enseignant", "professeur", "teacher"],
               "Fonctionnaire": ["fonctionnaire", "civil servant"], "Infirmier": ["infirmier", "infirmiere", "nurse"],
               "Ingenieur": ["ingenieur", "engineer"], "Medecin": ["medecin", "docteur", "doctor", "physician"],
               "Ouvrier": ["ouvrier", "worker", "labourer", "laborer"], "Pharmacien": ["pharmacien", "pharmacist"],
               "Secretaire": ["secretaire", "secretary"], "Technicien": ["technicien", "technician"],
               "Transporteur": ["transporteur", "chauffeur", "driver", "transporter"]}
KYC = {"Eleve": [r"kyc (eleve|haut|high)", r"(high|eleve) kyc"], "Moyen": [r"kyc (moyen|medium)"], "Faible": [r"kyc (faible|bas|low)"]}
PERSON_WORDS = r"\b(client|cliente|clients|customer|customers|personne|person|qui est|who is|titulaire|holder)\b"
ALERT_WORDS = r"(alert|suspect|signal|flagged|risque|risky|fraud)"
# the question is about the case open on screen, not a search: "ce client…", "le client a-t-il…", "même commerçant", "other customers"
ABOUT_OPEN_CASE = (r"\b(ce client|cette cliente|ce titulaire|this customer|this client|cette (transaction|operation|alerte)|"
                   r"ce (virement|paiement|retrait)|this (transaction|operation|alert|payment|transfer|withdrawal)|meme|same|"
                   r"d autres clients|autres clients|other customers|"
                   r"le client (a|est|il|avait|etait|habite|vit|voyage|paie|paye|utilise)|la cliente (a|est|elle)|"
                   r"the customer (has|is|was|did|does|lives|travels|uses))\b")


def parse(question):
    """Question -> approved filters. Returns {} when nothing person-related is recognised."""
    q = " " + _norm(question) + " "
    f = {}
    c = da.customers()
    if c is not None:
        for city in sorted(c.home_city.dropna().unique(), key=len, reverse=True):
            if f" {_norm(city)} " in q:
                f["city"] = city
                break
    for seg, words in SEGMENTS.items():
        if any(f" {w}" in q for w in words):
            f["segment"] = seg
            break
    for occ, words in OCCUPATIONS.items():
        if any(f" {w} " in q for w in words):
            f["occupation"] = occ
            break
    for lvl, pats in KYC.items():
        if any(re.search(p, q) for p in pats):
            f["kyc"] = lvl
    m = re.search(r"entre (\d{2}) et (\d{2}) ans|between (\d{2}) and (\d{2})", q)
    if m:
        a, b = [int(x) for x in m.groups() if x]
        f["age_min"], f["age_max"] = min(a, b), max(a, b)
    else:
        if m := re.search(r"(plus de|over|above|more than|older than) (\d{2})", q):
            f["age_min"] = int(m.group(2)) + 1
        if m := re.search(r"(moins de|under|below|younger than|less than) (\d{2}) (ans|years|year)?", q):
            f["age_max"] = int(m.group(2)) - 1
        if "age_min" not in f and "age_max" not in f:
            if m := re.search(r"\b(\d{2}) ?(ans|years old|year old|yo)\b|\b(age|aged|ag[ee]) (de )?(\d{2})\b", q):
                age = int(next(x for x in (m.group(1), m.group(5)) if x))
                f["age_min"] = f["age_max"] = age
    if re.search(ALERT_WORDS, q):
        f["with_alerts"] = True
    if re.search(r"digital|en ligne|application|mobile banking|banque en ligne|online banking", q):
        f["digital"] = True
    return f


def is_person_question(question):
    """True only for a real search ("les clients retraités de Sfax…"), not for a question about the open case."""
    f = parse(question)
    criteria = {k for k in f if k not in ("with_alerts", "digital")}
    if not criteria or re.search(ABOUT_OPEN_CASE, _norm(question)):
        return False, f
    return bool(re.search(PERSON_WORDS, _norm(question)) or len(criteria) >= 2), f


def find_customers(city=None, segment=None, occupation=None, age_min=None, age_max=None, kyc=None, digital=None,
                   with_alerts=None, limit=5):
    """Read-only search on approved filters. Returns matching count + up to `limit` compact profiles with their alerts."""
    c = da.customers()
    if c is None:
        return {"erreur": "Table clients indisponible."}
    m = c.copy()
    crit = {}
    for key, col, val in [("city", "home_city", city), ("segment", "segment", segment), ("occupation", "occupation", occupation),
                          ("kyc", "kyc_risk_level", kyc)]:
        if val:
            m = m[m[col].astype(str).str.lower() == str(val).lower()]
            crit[key] = val
    if age_min is not None:
        m = m[m.age >= int(age_min)]
        crit["age_min"] = int(age_min)
    if age_max is not None:
        m = m[m.age <= int(age_max)]
        crit["age_max"] = int(age_max)
    if digital:
        m = m[m.digital_banking_user.astype(bool)]
        crit["digital"] = True
    q = da.queue()
    al = (q.groupby("customer_id").agg(nb_alertes=("transaction_id", "size"), score_max=("score_model", "max"),
                                       derniere_alerte=("timestamp", "max"))
          if q is not None and len(q) else pd.DataFrame(columns=["nb_alertes", "score_max", "derniere_alerte"]))
    m = m.merge(al, left_on="customer_id", right_index=True, how="left")
    m["nb_alertes"] = m.nb_alertes.fillna(0).astype(int)
    if with_alerts:
        m = m[m.nb_alertes > 0]
        crit["with_alerts"] = True
    m = m.sort_values(["nb_alertes", "score_max", "age"], ascending=[False, False, True])
    top_tx = {}
    if q is not None and len(q):
        best = q.sort_values("score_model", ascending=False).drop_duplicates("customer_id")
        top_tx = dict(zip(best.customer_id, best.transaction_id))
    rows = []
    for r in m.head(max(1, min(int(limit), 20))).itertuples():
        rows.append({"customer_id": r.customer_id, "age": int(r.age), "segment": r.segment, "occupation": r.occupation,
                     "ville": r.home_city, "kyc": r.kyc_risk_level, "revenu_mensuel_tnd": round(float(r.monthly_income_tnd), 0),
                     "client_digital": bool(r.digital_banking_user), "nb_alertes": int(r.nb_alertes),
                     "score_max": None if pd.isna(r.score_max) else round(float(r.score_max), 4),
                     "alerte_la_plus_risquee": top_tx.get(r.customer_id)})
    return {"criteres": crit, "nb_clients_correspondants": int(len(m)), "clients": rows,
            "note": "Recherche en lecture seule sur filtres autorisés ; aucune donnée brute de transaction renvoyée."}


def answer_offline(res, lang="fr"):
    """Deterministic answer (no LLM) for a person search."""
    if "erreur" in res:
        return res["erreur"]
    n, rows, crit = res["nb_clients_correspondants"], res["clients"], res["criteres"]
    crit_txt = ", ".join(f"{k} = {v}" for k, v in crit.items())
    if n == 0:
        return (f"Aucun client ne correspond à : {crit_txt}. Élargissez un critère (âge, ville)." if lang != "en"
                else f"No customer matches: {crit_txt}. Widen one criterion (age, city).")
    head = (f"**{n} client(s)** correspondent à : {crit_txt}." if lang != "en" else f"**{n} customer(s)** match: {crit_txt}.")
    lines = []
    for r in rows:
        al = (f"{r['nb_alertes']} alerte(s), la plus risquée {r['alerte_la_plus_risquee']}" if lang != "en"
              else f"{r['nb_alertes']} alert(s), riskiest {r['alerte_la_plus_risquee']}") if r["nb_alertes"] else \
             ("aucune alerte" if lang != "en" else "no alert")
        lines.append(f"- **{r['customer_id']}** · {r['age']} {'ans' if lang != 'en' else 'y/o'} · {r['segment']} · {r['occupation']} · "
                     f"{r['ville']} · {'risque KYC' if lang != 'en' else 'KYC risk'} {r['kyc']} · {al}")
    more = "" if n <= len(rows) else (f"\n\n… et {n - len(rows)} autre(s). Précisez un critère pour réduire la liste." if lang != "en"
                                      else f"\n\n… and {n - len(rows)} more. Add a criterion to narrow the list.")
    return head + "\n" + "\n".join(lines) + more
