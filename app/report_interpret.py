"""Report Request Interpreter + Audience & Requirements Analyzer.

Natural language (FR / EN / AR) -> report specification: purpose, type, audience, period (+ comparison), scope, focus, depth,
format, sections, confidentiality, language. Rules first (0 token); an optional single LLM call may refine the specification
from the request text only (never data). Defaults are inferred and listed as assumptions; a question is asked only when an
essential element is missing (e.g. an investigation report without a transaction).
"""
import json
import re

import pandas as pd

import report_i18n as I

MONTHS = {**{m: i + 1 for i, m in enumerate(["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre",
                                             "novembre", "decembre"])},
          **{m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                             "november", "december"])},
          **{m: i + 1 for i, m in enumerate(["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر",
                                             "نوفمبر", "ديسمبر"])}}
ORD = {"premier": 1, "1er": 1, "first": 1, "deuxieme": 2, "second": 2, "2e": 2, "2eme": 2, "troisieme": 3, "third": 3, "3e": 3, "3eme": 3,
       "quatrieme": 4, "fourth": 4, "4e": 4, "4eme": 4}
TYPE_WORDS = {
    "investigation": ["enquete", "investigation", "dossier", "case report", "rapport de cas", "تحقيق"],
    "cyber": ["cyber", "securite", "security", "authentification", "authentication", "compromission", "compromise", "phishing", "intrusion",
              "الأمن السيبراني", "سيبراني"],
    "operational": ["operationnel", "operational", "traitement", "processing", "controle interne", "internal control", "workflow", "administratif",
                    "administrative", "تشغيلي"],
    "trends": ["tendance", "trend", "typolog", "emergent", "emerging", "evolution", "distribution", "repartition", "اتجاهات"],
    "periodic": ["mensuel", "monthly", "trimestriel", "quarterly", "annuel", "annual", "periodique", "periodic", "performance", "دوري", "شهري",
                 "فصلي", "سنوي"],
    "executive": ["direction", "management", "executif", "executive", "comite", "board", "dirigeant", "synthese pour", "الإدارة"],
}
AUDIENCE_WORDS = {"executive": ["direction", "management", "dirigeant", "executive", "comite", "board", "conseil", "الإدارة"],
                  "cyber": ["equipe securite", "equipe de securite", "security team", "rssi", "ciso", " soc", "departement cyber", "cybersecurity department",
                            "pour la securite", "for security", "pour la cybersecurite", "for the cybersecurity", "فريق الأمن"],
                  "operations": ["direction des operations", "operations team", "operations manager", "controle interne", "internal control", "back office",
                                 "audit interne", "فريق العمليات"],
                  "analyst": ["analyste", "analyst", "enqueteur", "investigat", "equipe fraude", "fraud team", "المحلل"]}
FOCUS_WORDS = {"card_type": ["type de carte", "types de carte", "card type", "card categor", "categories de carte", "categorie de carte", "cartes",
                             "card", "البطاقات"],
               "emerging": ["emergent", "emerging", "nouveau", "nouvelles", "new pattern", "pattern", "tendance", "trend", "typolog", "ناشئ"],
               "cyber": TYPE_WORDS["cyber"], "operational": TYPE_WORDS["operational"] + ["faiblesse", "weakness", "controle", "control"],
               "geography": ["geograph", "region", "ville", "city", "pays", "country", "gouvernorat", "جغراف"],
               "merchant": ["commercant", "merchant", "secteur", "categorie de commer", "mcc"],
               "model": ["modele", "model", "detection", "performance", "faux positif", "false positive"],
               "time": ["heure", "hour", "nuit", "night", "horaire"],
               "recommendations": ["recommand", "recommend", "توصي"]}
CHANNEL_WORDS = {"DAB": ["dab", "atm", "gab", "distributeur", "retrait", "الصراف"], "EN_LIGNE": ["en ligne", "online", "e-commerce", "ecommerce",
                                                                                                 "internet payment", "عبر الإنترنت"],
                 "TPE": ["tpe", "pos", "terminal de paiement", "magasin", "in-store", "point of sale"], "MOBILE": ["mobile", "application", "app "],
                 "WEB": ["banque en ligne", "internet banking", "netbanking", "web"]}
COUNTRIES = {"tunisie": "TN", "tunisia": "TN", "france": "FR", "italie": "IT", "italy": "IT", "allemagne": "DE", "germany": "DE", "libye": "LY",
             "libya": "LY", "algerie": "DZ", "algeria": "DZ", "maroc": "MA", "morocco": "MA", "turquie": "TR", "turkey": "TR", "espagne": "ES",
             "spain": "ES", "arabie saoudite": "SA", "saudi arabia": "SA", "emirats": "AE", "uae": "AE", "qatar": "QA", "egypte": "EG",
             "egypt": "EG", "royaume-uni": "GB", "united kingdom": "GB", "etats-unis": "US", "united states": "US", "canada": "CA"}
EN_WORDS = set("the a an report prepare generate analyze analyse about across with for and of our on in by from this last previous compare give show me make "
               "create write please management executive summary detailed quarterly monthly fraud channels card types".split())
FR_WORDS = set("le la les un une des du de rapport prepare prepare genere generer analyse sur pour avec et nos notre dans par ce cette "
               "dernier mois trimestre compare donne montre fais redige direction synthese detaille trimestriel mensuel fraude canaux cartes".split())
TX_ID = re.compile(r"\bTX\d{6,}\b", re.I)


def _has(text, words):
    return any(w in text for w in words)


def _month_end(y, m):
    return (pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)).date()


def _quarter(y, q):
    return pd.Timestamp(y, 3 * q - 2, 1).date(), _month_end(y, 3 * q)


def _last_full(kind, ref):
    ref = pd.Timestamp(ref)
    if kind == "quarter":
        q = (ref.month - 1) // 3 + 1
        y, q = (ref.year, q) if ref == pd.Timestamp(_quarter(ref.year, q)[1]) else ((ref.year, q - 1) if q > 1 else (ref.year - 1, 4))
        return _quarter(y, q)
    if kind == "year":
        y = ref.year if ref.month == 12 and ref.day == 31 else ref.year - 1
        return pd.Timestamp(y, 1, 1).date(), pd.Timestamp(y, 12, 31).date()
    m_end = ref + pd.offsets.MonthEnd(0)
    if ref != m_end:
        ref = ref - pd.offsets.MonthBegin(1) - pd.Timedelta(days=1)
    return pd.Timestamp(ref.year, ref.month, 1).date(), _month_end(ref.year, ref.month)


def parse_period(text, ref):
    """-> (start, end, cadence, how) or None. `ref` = reference 'today' (last day of available data)."""
    t = I.norm(text)
    raw = text.lower()
    m = re.findall(r"(\d{4})-(\d{2})-(\d{2})", t) or [(c, b, a) for a, b, c in re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)]
    if len(m) >= 2:
        a, b = (pd.Timestamp(int(x[0]), int(x[1]), int(x[2])).date() for x in m[:2])
        return min(a, b), max(a, b), "custom", "dates"
    mq = re.search(r"\b[qt]([1-4])\s*[-/ ]?\s*(20\d\d)\b", t) or re.search(r"\b(20\d\d)\s*[-/ ]?\s*[qt]([1-4])\b", t)
    if mq:
        q, y = (int(mq.group(1)), int(mq.group(2))) if len(mq.group(1)) == 1 else (int(mq.group(2)), int(mq.group(1)))
        return (*_quarter(y, q), "quarter", "explicit quarter")
    ma = re.search(r"الربع\s*(الأول|الثاني|الثالث|الرابع)\D*(20\d\d)?", raw)
    if ma:
        y = int(ma.group(2)) if ma.group(2) else pd.Timestamp(ref).year
        return (*_quarter(y, ["الأول", "الثاني", "الثالث", "الرابع"].index(ma.group(1)) + 1), "quarter", "explicit quarter")
    mo = re.search(r"\b(premier|1er|first|deuxieme|2e|2eme|second|troisieme|3e|3eme|third|quatrieme|4e|4eme|fourth)\s+(trimestre|quarter)"
                   r"(?:\s+(?:de\s+|of\s+)?(20\d\d))?", t)
    if mo:
        y = int(mo.group(3)) if mo.group(3) else pd.Timestamp(ref).year
        return (*_quarter(y, ORD[mo.group(1)]), "quarter", "explicit quarter")
    for name, num in MONTHS.items():
        key = name if not name.isascii() else I.norm(name)
        src = raw if not name.isascii() else t
        mm = re.search(rf"(?<![a-z]){re.escape(key)}\s*(20\d\d)?", src)
        if mm:
            y = int(mm.group(1)) if mm.group(1) else pd.Timestamp(ref).year
            return pd.Timestamp(y, num, 1).date(), _month_end(y, num), "month", "explicit month"
    if _has(t, ["dernier trimestre", "last quarter", "trimestre dernier", "past quarter"]):
        return (*_last_full("quarter", ref), "quarter", "last full quarter")
    if _has(t, ["mois dernier", "last month", "le mois passe", "past month"]):
        return (*_last_full("month", ref), "month", "last full month")
    nd = re.search(r"(\d{1,3})\s+(derniers jours|last days|days|jours)", t)
    if nd:
        n = int(nd.group(1))
        return (pd.Timestamp(ref) - pd.Timedelta(days=n - 1)).date(), pd.Timestamp(ref).date(), "custom", "last N days"
    my = re.search(r"\b(?:annee|year|en|in|annuel|annual)\s+(20\d\d)\b", t) or re.search(r"^\s*(20\d\d)\s*$", t)
    if my:
        y = int(my.group(1))
        return pd.Timestamp(y, 1, 1).date(), pd.Timestamp(y, 12, 31).date(), "year", "explicit year"
    return None


def previous(p, cadence):
    s, e = pd.Timestamp(p[0]), pd.Timestamp(p[1])
    if cadence == "quarter":
        ps = s - pd.DateOffset(months=3)
        return ps.date(), (s - pd.Timedelta(days=1)).date()
    if cadence == "month":
        ps = s - pd.DateOffset(months=1)
        return ps.date(), (s - pd.Timedelta(days=1)).date()
    if cadence == "year":
        return (s - pd.DateOffset(years=1)).date(), (s - pd.Timedelta(days=1)).date()
    n = (e - s).days + 1
    return (s - pd.Timedelta(days=n)).date(), (s - pd.Timedelta(days=1)).date()


def interpret(request, src, ui_lang="fr"):
    """-> spec dict (all fields filled, `assumptions` and `questions` lists)."""
    text = request or ""
    t = I.norm(text)
    raw = text.lower()
    spec = {"request": text, "assumptions": [], "questions": [], "interpreted_by": "rules", "source": src.id}
    # language
    words = re.findall(r"[a-z]+", t)
    en_w = sum(w in EN_WORDS for w in words)
    fr_w = sum(w in FR_WORDS for w in words)
    if _has(t, ["en arabe", "in arabic"]) or (re.search(r"[\u0600-\u06FF]", text) and not _has(t, ["en francais", "in english", "en anglais"])):
        lang = "ar"
    elif _has(t, ["in english", "en anglais"]):
        lang = "en"
    elif _has(t, ["en francais", "in french"]):
        lang = "fr"
    elif en_w != fr_w:
        lang = "en" if en_w > fr_w else "fr"
    else:
        lang = ui_lang if ui_lang in I.LANGS else "fr"
    spec["lang"] = lang
    # type
    tx_ids = [x.upper() for x in TX_ID.findall(text)]
    scores = {k: sum(1 for w in ws if (w in raw if not w.isascii() else w in t)) for k, ws in TYPE_WORDS.items()}
    if tx_ids or scores["investigation"]:
        typ = "investigation"
    else:
        order = ["periodic", "cyber", "operational", "trends", "executive"]
        typ = max(order, key=lambda k: (scores[k], -order.index(k))) if any(scores[k] for k in order) else "executive"
        if scores["periodic"] and _has(t, ["mensuel", "monthly", "trimestriel", "quarterly", "annuel", "annual"]):
            typ = "periodic"
    spec["type"] = typ
    spec["case_id"] = tx_ids[0] if tx_ids else None
    if typ == "investigation" and not tx_ids:
        spec["questions"].append(I.tr(lang, "Quelle opération (identifiant TX…) le rapport d'enquête doit-il couvrir ?",
                                      "Which transaction (TX… id) should the investigation report cover?",
                                      "ما هي العملية (المعرّف TX…) التي يجب أن يغطيها تقرير التحقيق؟"))
    # audience
    aud = next((a for a, ws in AUDIENCE_WORDS.items() if any((w in raw if not w.isascii() else w in t) for w in ws)), None)
    if aud is None:
        aud = I.TYPES[typ][3]
        spec["assumptions"].append(("audience", aud))
    spec["audience"] = aud
    # period
    ref_any = pd.Timestamp(src.last_day)
    needs_labels = typ in ("executive", "trends", "periodic")
    ref = pd.Timestamp(src.labelled_until) if needs_labels and src.labelled_until else ref_any
    p = parse_period(text, ref_any)
    if p:
        start, end, cadence, how = p
    else:
        cadence = "quarter" if _has(t, ["trimestr", "quarter", "فصلي"]) or typ == "trends" else "year" if _has(t, ["annuel", "annual", "سنوي"]) \
            else "month"
        start, end = _last_full(cadence, ref)
        how = "default"
        spec["assumptions"].append(("period", f"{start} → {end}"))
    first, last = pd.Timestamp(src.first_day).date(), pd.Timestamp(src.last_day).date()
    if pd.Timestamp(end).date() < first or pd.Timestamp(start).date() > last:
        spec["questions"].append(I.tr(lang, f"Aucune donnée sur cette période : les données vont du {first} au {last}. Quelle période ?",
                                      f"No data in that period: data runs from {first} to {last}. Which period?",
                                      f"لا توجد بيانات في هذه الفترة: البيانات من {first} إلى {last}. ما الفترة المطلوبة؟"))
    spec["period"] = [str(start), str(end)]
    spec["cadence"] = cadence
    spec["period_how"] = how
    compare = _has(t, ["compar", "vs", "versus", "par rapport", "previous", "precedent", "evolution", "قارن", "مقارنة"]) or typ in ("periodic", "trends")
    spec["compare"] = bool(compare) and typ != "investigation"
    spec["previous"] = [str(x) for x in previous((start, end), cadence)] if spec["compare"] else None
    # scope
    chans = [c for c, ws in CHANNEL_WORDS.items() if any((w in raw if not w.isascii() else re.search(rf"(?<![a-z]){re.escape(w)}", t)) for w in ws)]
    if "WEB" in chans and "EN_LIGNE" in chans and "banque en ligne" in t and not _has(t, ["paiement en ligne", "online payment"]):
        chans.remove("EN_LIGNE")
    cards = [c for c in _distinct(src, "card_type") if I.norm(c) in t]
    if not cards:
        for brand in ("visa", "mastercard", "nationale"):
            if re.search(rf"\b{brand}\b", t) and not _has(t, ["types de carte", "card types"]):
                cards += [c for c in _distinct(src, "card_type") if brand in I.norm(c)]
    cities = [c for c in _distinct(src, "city") if len(c) > 3 and re.search(rf"\b{re.escape(I.norm(c))}\b", t)]
    countries = sorted({iso for name, iso in COUNTRIES.items() if re.search(rf"\b{re.escape(name)}\b", t)} - ({"TN"} if cities else set()))
    spec["scope"] = {"channels": chans, "card_types": sorted(set(cards)), "cities": cities[:5], "countries": countries}
    # focus, depth, format, confidentiality
    spec["focus"] = [f for f, ws in FOCUS_WORDS.items() if any((w in raw if not w.isascii() else w in t) for w in ws)]
    if _has(t, ["detaill", "detailed", "approfondi", "in-depth", "technique", "technical", "مفصل"]):
        depth = "detailed"
    elif _has(t, ["synthese", "summary", "bref", "brief", "court", "short", "ملخص"]):
        depth = "summary"
    else:
        depth = I.TYPES[typ][4]
        spec["assumptions"].append(("depth", depth))
    spec["depth"] = depth
    spec["format"] = "docx" if _has(t, ["docx", "word", "editable", "modifiable"]) else "xlsx" if _has(t, ["excel", "xlsx", "tableur"]) \
        else "html" if _has(t, ["html", "interactif", "interactive"]) else "pdf"
    spec["confidentiality"] = ("restricted" if _has(t, ["restreint", "restricted"]) else "confidential" if _has(t, ["confidentiel", "confidential", "سري"])
                               else "public" if _has(t, ["public"]) else "confidential" if typ in ("investigation", "cyber") else "internal")
    spec["sections"] = sections_for(spec)
    spec["purpose"] = purpose(spec, lang)
    spec["ai_agents"] = False
    return spec


def _distinct(src, col):
    try:
        return src.q(f"SELECT DISTINCT {col} AS v FROM tx WHERE {col} IS NOT NULL LIMIT 400")["v"].tolist()
    except Exception:
        return []


def default_sections(typ, depth):
    if typ == "investigation":
        s = ["summary", "case", "timeline", "findings", "ai", "risk", "recommendations", "conclusion", "appendix"]
    else:
        s = ["summary", "scope", "kpis", "findings"] + {"cyber": ["cyber"], "operational": ["processing"]}.get(typ, []) + \
            ["risk", "recommendations", "conclusion", "appendix"]
    if depth == "summary":
        s = [x for x in s if x not in ("timeline",)]
    return s


def sections_for(spec):
    s = default_sections(spec["type"], spec["depth"])
    if spec["type"] != "investigation":
        extra = [x for x, f in (("cyber", "cyber"), ("processing", "operational")) if f in (spec.get("focus") or []) and x not in s]
        i = s.index("risk")
        s = s[:i] + extra + s[i:]
    return s


def purpose(spec, lang):
    typ = spec["type"]
    if typ == "investigation":
        return I.tr(lang, f"Établir les faits de l'opération {spec.get('case_id') or '…'} et éclairer la décision.",
                    f"Establish the facts of transaction {spec.get('case_id') or '…'} and support the decision.",
                    f"إثبات وقائع العملية {spec.get('case_id') or '…'} ودعم القرار.")
    return {"executive": I.tr(lang, "Donner à la direction la situation de la fraude, l'exposition financière et les décisions à prendre.",
                              "Give management the fraud situation, financial exposure and the decisions required.",
                              "إطلاع الإدارة على وضع الاحتيال والتعرض المالي والقرارات المطلوبة."),
            "cyber": I.tr(lang, "Identifier les indicateurs de sécurité liés à la fraude et les vérifications à mener.",
                          "Identify security indicators linked to fraud and the checks to run.", "تحديد مؤشرات الأمن المرتبطة بالاحتيال والتحققات اللازمة."),
            "operational": I.tr(lang, "Repérer les anomalies de traitement et les faiblesses de contrôle.",
                                "Spot processing anomalies and control weaknesses.", "رصد شذوذات المعالجة ونقاط ضعف الرقابة."),
            "trends": I.tr(lang, "Comprendre comment la fraude évolue et où elle se concentre.", "Understand how fraud evolves and where it concentrates.",
                           "فهم كيفية تطور الاحتيال وأين يتركز."),
            "periodic": I.tr(lang, "Suivre la performance de détection et l'exposition sur la période, comparée à la précédente.",
                             "Monitor detection performance and exposure over the period, against the previous one.",
                             "متابعة أداء الكشف والتعرض خلال الفترة مقارنة بالفترة السابقة.")}[typ]


def refine_with_ai(spec, lang):
    """Optional: ONE call on the request text only; returns a corrected spec (validated against the allowed values)."""
    import copilot
    if not copilot.configured():
        return spec
    allowed = {"type": list(I.TYPES), "audience": list(I.AUDIENCES), "depth": list(I.DEPTHS), "format": list(I.FORMATS),
               "confidentiality": list(I.CONFIDENTIALITY), "focus": list(FOCUS_WORDS), "channels": list(CHANNEL_WORDS)}
    prompt = ("A bank employee asked for a report. Correct this rule-based interpretation only if it is clearly wrong. Return ONLY JSON with "
              "the same keys {type, audience, depth, format, confidentiality, focus, channels, compare}. Allowed values: " + json.dumps(allowed)
              + "\nRequest: " + spec["request"][:800] + "\nCurrent: " + json.dumps({k: spec[k] for k in ("type", "audience", "depth", "format",
                                                                                                         "confidentiality", "focus", "compare")}
                                                                                     | {"channels": spec["scope"]["channels"]}))
    try:
        txt, _ = copilot.complete_json(prompt, tag="[report] interpret", max_tokens=800)
        r = json.loads(txt or "{}")
    except Exception:
        return spec
    out = dict(spec)
    for k in ("type", "audience", "depth", "format", "confidentiality"):
        if r.get(k) in allowed[k]:
            out[k] = r[k]
    if isinstance(r.get("focus"), list):
        out["focus"] = [f for f in r["focus"] if f in allowed["focus"]]
    if isinstance(r.get("channels"), list):
        out["scope"] = {**out["scope"], "channels": [c for c in r["channels"] if c in allowed["channels"]]}
    if isinstance(r.get("compare"), bool) and out["type"] != "investigation":
        out["compare"] = r["compare"]
        out["previous"] = [str(x) for x in previous(tuple(pd.Timestamp(x).date() for x in out["period"]), out["cadence"])] if r["compare"] else None
    if out["type"] != spec["type"]:
        out["sections"] = sections_for(out)
        out["purpose"] = purpose(out, lang)
    out["interpreted_by"] = "rules + AI"
    return out
