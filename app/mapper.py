"""AI-assisted mapping of any bank schema to the Hyson canonical model (rule-based, 0 tokens; optional LLM review on stats only).

propose(tables, summary) -> mapping proposal: table roles, field mappings with confidence, value translations, flags that
need a human decision, excluded (sensitive) columns. apply(tables, mapping, ...) -> canonical entities (pseudonymised ids).
Nothing is activated from a proposal: a human confirms the flagged items and approves a versioned mapping.
"""
import difflib
import hashlib
import hmac
import json
import re
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd

import canonical as cn
import discovery as dv

# ---------------------------------------------------------------- vocabulary
SYN = {  # entity.field -> source-name synonyms (normalised snake_case); French, English, camelCase and ISO-8583 habits
    "transactions.transaction_id": ["transaction_id", "txn_ref", "tx_id", "txnid", "txn_id", "trx_id", "ref_operation", "reference", "ref", "id",
                                    "operation_id", "id_transaction", "id_operation", "num_operation", "transaction_ref"],
    "transactions.timestamp": ["timestamp", "ts", "datetime", "date_operation", "created_at", "created_at_ms", "date_heure", "transaction_date",
                               "date", "time", "booking_date", "txn_time", "transaction_time", "date_transaction", "event_time"],
    "transactions.customer_id": ["customer_id", "client_id", "num_client", "client_ref", "client", "cust_id", "customer", "customer_ref",
                                 "id_client", "holder_id", "code_client"],
    "transactions.amount": ["amount", "montant", "montant_dt", "amount_minor", "amt", "valeur", "value", "montant_tnd", "txn_amount",
                            "transaction_amount", "amount_cents", "montant_operation"],
    "transactions.currency": ["currency", "devise", "ccy", "cur", "currency_code", "code_devise"],
    "transactions.card_id": ["card_id", "num_carte", "payment_card", "carte", "card", "pan", "pan_masked", "card_number", "card_ref", "id_carte"],
    "transactions.account_id": ["account_id", "num_compte", "compte", "account", "account_ref", "rib"],
    "transactions.merchant_id": ["merchant_id", "mid", "code_commercant", "commercant", "merchant", "merchant_ref", "terminal_id", "id_commercant"],
    "transactions.channel": ["channel", "canal", "channel_code", "type_canal", "source_channel", "canal_operation"],
    "transactions.transaction_type": ["transaction_type", "txn_kind", "nature", "type", "operation_type", "txn_type", "type_operation", "kind"],
    "transactions.entry_mode": ["entry_mode", "pos_entry_mode", "mode_saisie", "capture_mode", "entry", "pos_entry"],
    "transactions.status": ["status", "etat", "statut", "response_code", "result", "response", "auth_result", "code_reponse"],
    "transactions.decline_reason": ["decline_reason", "motif_refus", "reason", "motif", "reject_reason"],
    "transactions.country": ["country", "pays", "country_code", "pays_iso3", "pays_iso", "merchant_country", "code_pays"],
    "transactions.city": ["city", "ville", "merchant_city", "localite"],
    "transactions.merchant_category": ["merchant_category", "secteur", "categorie", "category", "mcc_label", "activite", "categorie_commercant"],
    "transactions.device_id": ["device_id", "device_ref", "appareil", "device", "id_appareil"],
    "transactions.is_fraud": ["is_fraud", "fraud_flag", "fraude", "fraud", "is_fraude", "fraud_label", "confirmed_fraud"],
    "transactions.risk_score": ["risk_score", "rules_score", "score", "score_risque", "fraud_score", "score_regles"],
    "customers.customer_id": ["customer_id", "client_id", "num_client", "client_ref", "client", "cust_id", "id_client", "code_client"],
    "customers.age": ["age"],
    "customers.birth_date": ["birth_date", "date_naissance", "dob", "date_of_birth"],
    "customers.birth_year": ["birth_year", "annee_naissance", "year_of_birth"],
    "customers.segment": ["segment", "tier", "client_segment", "categorie_client", "profil"],
    "customers.city": ["city", "ville", "home_city", "ville_residence"],
    "customers.region": ["region", "gouvernorat", "state", "province", "wilaya"],
    "customers.monthly_income": ["monthly_income", "revenu_mensuel", "income", "salaire", "revenu"],
    "customers.kyc_risk": ["kyc_risk", "niveau_kyc", "kyc_rating", "kyc", "risque_kyc", "kyc_level"],
    "customers.customer_since": ["customer_since", "date_entree", "since", "onboarding_date", "date_ouverture", "client_depuis"],
    "cards.card_id": ["card_id", "num_carte", "payment_card", "carte", "card", "card_ref", "id_carte"],
    "cards.customer_id": ["customer_id", "num_client", "client_ref", "client_id", "client", "holder_id", "titulaire"],
    "cards.card_type": ["card_type", "type_carte", "product", "card_product", "produit"],
    "cards.daily_limit": ["daily_limit", "plafond_jour", "plafond", "limit", "daily_limit_tnd"],
    "cards.is_international": ["is_international", "international", "intl", "internationale"],
    "merchants.merchant_id": ["merchant_id", "mid", "code_commercant", "commercant", "merchant_ref", "id_commercant"],
    "merchants.category": ["category", "categorie", "mcc_label", "secteur", "activite"],
    "merchants.mcc": ["mcc", "mcc_code", "code_mcc"],
    "merchants.city": ["city", "ville"],
    "merchants.country": ["country", "pays", "country_code"],
    "auth_events.event_id": ["event_id", "log_id", "id", "id_evenement"],
    "auth_events.timestamp": ["timestamp", "logged_at", "ts", "date_heure", "event_time", "created_at", "date"],
    "auth_events.customer_id": ["customer_id", "client_ref", "num_client", "client_id", "client", "user_id"],
    "auth_events.event_type": ["event_type", "action", "type_evenement", "event", "type"],
    "auth_events.status": ["status", "result", "statut", "resultat", "outcome"],
    "auth_events.device_id": ["device_id", "device_ref", "appareil", "device"],
    "auth_events.ip_country": ["ip_country", "pays_ip", "country", "geo_country"],
    "fraud_labels.transaction_id": ["transaction_id", "ref_operation", "txn_ref", "tx_id", "operation_id", "reference"],
    "fraud_labels.is_fraud": ["is_fraud", "fraud", "fraude", "fraud_flag", "confirmed"],
    "fraud_labels.fraud_type": ["fraud_type", "typologie", "typology", "scenario", "type_fraude", "fraud_scenario"],
    "fraud_labels.reported_at": ["reported_at", "date_signalement", "reported_date", "report_date", "date_declaration"],
    "cases.case_id": ["case_id", "case", "dossier", "id_dossier", "case_ref", "num_dossier"],
    "cases.transaction_id": ["transaction_id", "txn_ref", "ref_operation", "tx_id"],
    "cases.opened_at": ["opened_at", "date_ouverture", "created_at", "open_date"],
    "cases.outcome": ["outcome", "conclusion", "resultat", "decision", "status"],
    "cases.notes": ["notes", "analyst_notes", "commentaire", "resume", "narrative", "description"],
}
ROLE_WORDS = {"transactions": ["operation", "operations", "txn", "transaction", "transactions", "payments", "extract", "mouvements", "ops"],
              "customers": ["client", "clients", "customer", "customers", "kyc", "tiers"],
              "cards": ["carte", "cartes", "card", "cards"],
              "merchants": ["merchant", "merchants", "commercant", "commercants", "mcc"],
              "auth_events": ["auth", "auth_log", "login", "logins", "connexion", "connexions", "events", "sessions", "journal"],
              "fraud_labels": ["fraude", "fraud", "signalement", "signalements", "chargeback", "chargebacks", "labels", "reclamations"],
              "cases": ["investigation", "investigations", "case", "cases", "dossier", "dossiers", "enquete", "enquetes"]}
VOCAB = {  # canonical code -> source spellings (normalised)
    "channel": {"TPE": ["pos", "tpe", "store", "in_store", "card_present", "magasin"], "DAB": ["atm", "dab", "gab", "cash"],
                "EN_LIGNE": ["ecom", "ecommerce", "e_commerce", "online", "cnp", "en_ligne", "web_card", "card_not_present"],
                "MOBILE": ["mobile", "mobile_app", "app", "wallet", "mobile_banking"],
                "WEB": ["web", "netbanking", "internet", "internet_banking", "online_banking", "banque_en_ligne"]},
    "transaction_type": {"ACHAT": ["purchase", "payment", "achat", "sale", "paiement"], "RETRAIT": ["withdrawal", "retrait", "cash_withdrawal"],
                         "VIREMENT": ["transfer", "virement", "wire", "p2p"], "PAIEMENT_FACTURE": ["bill_payment", "bill", "facture", "paiement_facture"],
                         "RECHARGE": ["top_up", "topup", "recharge", "reload"]},
    "entry_mode": {"CHIP": ["chip", "emv", "puce", "icc"], "SANS_CONTACT": ["contactless", "nfc", "tap", "sans_contact"],
                   "MAGSTRIPE": ["swipe", "magstripe", "stripe", "piste", "mag"], "ECOM_3DS": ["3ds", "ecom_3ds", "secure", "3d_secure"],
                   "ECOM_SANS_3DS": ["no3ds", "ecom_no3ds", "non_3ds", "ecom_sans_3ds"], "APP_AUTH": ["app_auth", "biometric", "biometrie"]},
    "status": {"APPROUVEE": ["approved", "success", "ok", "accepted", "acceptee", "approuvee", "authorised", "authorized", "accepte", "valide"],
               "REFUSEE": ["declined", "rejected", "rejetee", "refused", "refusee", "failed", "refuse", "rejete", "denied"]},
    "event_type": {"CONNEXION": ["login", "connexion", "sign_in", "logon", "signin"],
                   "AJOUT_BENEFICIAIRE": ["add_payee", "add_beneficiary", "ajout_beneficiaire", "new_payee"],
                   "AJOUT_APPAREIL": ["add_device", "new_device", "ajout_appareil", "device_enrolment"],
                   "REINITIALISATION_MOT_DE_PASSE": ["password_reset", "reset_password", "reinitialisation_mot_de_passe", "pwd_reset"],
                   "MODIFICATION_NUMERO_TELEPHONE": ["phone_change", "change_phone", "modification_numero_telephone", "sim_change"]},
    "event_status": {"SUCCES": ["ok", "success", "succes", "succeeded", "reussi"], "ECHEC": ["fail", "failed", "failure", "echec", "ko", "error", "denied"]},
}
LABEL_TRUE = {"1", "true", "yes", "oui", "y", "fraud", "fraude", "confirmed_fraud", "confirmed", "fraud_confirmed"}
LABEL_FALSE = {"0", "false", "no", "non", "n", "genuine", "legit", "legitimate", "not_fraud"}
DEFAULT_RATES = {"TND": 1.0, "EUR": 3.40, "USD": 3.10, "GBP": 3.95, "CHF": 3.55, "MAD": 0.31, "DZD": 0.023, "LYD": 0.64, "SAR": 0.83,
                 "AED": 0.84, "QAR": 0.85, "TRY": 0.095, "CAD": 2.27}            # indicative (TND per unit), editable per tenant
PREFIX = {"customer_id": "CU", "card_id": "CA", "account_id": "AC", "device_id": "DV"}


def norm(s):
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(s))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def translate_code(vocab, value):
    v = norm(value)
    for code, words in VOCAB.get(vocab, {}).items():
        if v == norm(code) or v in words:
            return code
    return None


# ---------------------------------------------------------------- scoring
def name_score(col, syns):
    c = norm(col)
    if c in syns:
        return 1.0
    toks = set(c.split("_"))
    best = max(difflib.SequenceMatcher(None, c, s).ratio() for s in syns)
    if any(len(s) > 3 and (s in c or (("_" not in s) and s in toks)) for s in syns):
        best = max(best, 0.85)
    return best


def _values(series, top=50):
    v = series.dropna().astype(str).str.strip()
    return v[v != ""].value_counts().head(top)


def value_fit(kind, field, col_prof, series):
    k = col_prof["kind"]
    if kind == "id":
        base = {"id": 0.75, "number": 0.45, "text": 0.4, "code": 0.25}.get(k, 0.0)
        return min(1.0, base + 0.2) if col_prof["unique"] else base
    if kind in ("datetime", "date"):
        return 1.0 if k in ("datetime", "epoch_ms", "epoch_s") else 0.0
    if kind == "amount":
        return 0.9 if k == "number" and col_prof["stats"]["min"] >= 0 else 0.5 if k == "number" else 0.0
    if kind in ("number", "score"):
        return 0.8 if k == "number" else 0.0
    if kind == "country":
        return 1.0 if k in ("country2", "country3") else 0.0
    if kind == "currency":
        return 1.0 if k == "currency" else 0.0
    if kind in ("label", "bool"):
        if k == "bool":
            return 1.0
        vals = {norm(x) for x in _values(series).index}
        return 0.7 if vals and vals <= LABEL_TRUE | LABEL_FALSE else 0.0
    if kind.startswith("code:"):
        vocab = kind[5:]
        vc = _values(series)
        if vc.empty:
            return 0.0
        if vocab == "status" and set(vc.index) <= {"0", "1"}:
            return 0.6                                      # numeric status convention: needs confirmation
        if vocab == "status" and all(re.fullmatch(r"\d{2}", x) for x in vc.index) and "00" in vc.index:
            return 0.85                                     # ISO 8583 response codes
        ok = sum(n for x, n in vc.items() if translate_code(vocab, x))
        return ok / vc.sum()
    if kind == "text":
        return {"text": 0.6, "code": 0.6, "id": 0.45}.get(k, 0.1)
    return 0.0


def _excluded(col, col_prof):
    c = norm(col)
    toks = set(c.split("_"))
    for key, why in cn.EXCLUDED.items():
        if key == c or key in toks or ("_" in key and key in c):
            return why
    if col_prof["kind"] == "email":
        return cn.EXCLUDED["email"]
    return None


def _assign(table, df, tprof, entity):
    """Greedy best assignment of this table's columns to one entity's fields -> {field: (col, score)}."""
    cands = []
    for field, (kind, _req, _d) in cn.ENTITIES[entity].items():
        syns = SYN.get(f"{entity}.{field}", [field])
        for col, p in tprof["columns"].items():
            if _excluded(col, p):
                continue
            nm = name_score(col, syns)
            fit = value_fit(kind, field, p, df[col])
            sc = 0.6 * nm + 0.4 * fit
            if fit == 0:
                sc *= 0.3
            cands.append((sc, field, col))
    out, used = {}, set()
    for sc, field, col in sorted(cands, reverse=True):
        if field in out or col in used or sc < 0.5:
            continue
        out[field] = (col, round(float(sc), 3))
        used.add(col)
    return out


PRIMARY = {"transactions": "transaction_id", "customers": "customer_id", "cards": "card_id", "merchants": "merchant_id",
           "auth_events": None, "fraud_labels": "transaction_id", "cases": "case_id"}
CORE = {"transactions": ["transaction_id", "timestamp", "amount"], "customers": ["customer_id"], "cards": ["card_id", "customer_id"],
        "merchants": ["merchant_id"], "auth_events": ["timestamp", "event_type"], "fraud_labels": ["transaction_id"], "cases": ["case_id"]}
SIGNATURE = {"customers": ["age", "birth_date", "birth_year", "segment", "monthly_income", "kyc_risk", "customer_since", "region"],
             "cards": ["card_type", "daily_limit", "is_international"], "merchants": ["mcc", "category"],
             "fraud_labels": ["fraud_type", "reported_at", "is_fraud"], "cases": ["notes", "outcome", "opened_at"],
             "transactions": ["amount", "timestamp", "channel"], "auth_events": ["event_type"]}


def _role_score(table, df, tprof, entity, fields):
    core = CORE[entity]
    if not all(f in fields for f in core):
        return 0.0
    pk = PRIMARY[entity]
    if pk and entity not in ("fraud_labels",) and not tprof["columns"][fields[pk][0]]["unique"]:
        return 0.0
    sig = [f for f in SIGNATURE[entity] if f in fields]
    if entity in ("customers", "cards", "merchants", "fraud_labels", "cases") and not sig:
        return 0.0
    conf = np.mean([fields[f][1] for f in core])
    cover = len(fields) / len(cn.ENTITIES[entity])
    hint = 0.25 if set(norm(table).split("_")) & set(ROLE_WORDS[entity]) or norm(table) in ROLE_WORDS[entity] else 0.0
    return round(0.55 * conf + 0.35 * cover + hint, 3)


def propose(tables, summary=None):
    summary = summary or dv.summary(tables)
    prof = summary["tables"]
    scores = {}
    for t, df in tables.items():
        for e in cn.ENTITIES:
            fields = _assign(t, df, prof[t], e)
            scores[(t, e)] = (_role_score(t, df, prof[t], e, fields), fields)
    roles, taken = {}, set()
    for (t, e), (sc, _) in sorted(scores.items(), key=lambda kv: -kv[1][0]):
        if sc < 0.45 or t in roles or e in taken:
            continue
        roles[t] = e
        taken.add(e)
    mapping = {"version": 1, "created": datetime.now().isoformat(timespec="seconds"), "roles": {}, "tables": {}, "flags": [],
               "relations": summary["relations"], "unassigned_tables": [t for t in tables if t not in roles]}
    tx_table = next((t for t, e in roles.items() if e == "transactions"), None)
    for t, e in roles.items():
        fields = scores[(t, e)][1]
        tp = prof[t]["columns"]
        spec = {}
        for field, (col, sc) in fields.items():
            kind = cn.ENTITIES[e][field][0]
            spec[field] = _field_spec(e, field, kind, col, sc, tp[col], tables[t][col], mapping["flags"], t)
        excluded = {c: _excluded(c, p) for c, p in tp.items() if _excluded(c, p)}
        for c, p in tp.items():
            if p.get("pan_like") and c not in excluded:
                mapping["flags"].append({"table": t, "column": c, "level": "warning", "fr": "Numéros de carte en clair détectés : "
                                         "ils seront hachés (jamais stockés en clair). Recommandé : envoyer un PAN tronqué ou un jeton.",
                                         "en": "Clear card numbers detected: they will be hashed (never stored in clear). Recommended: send "
                                         "a truncated PAN or a token."})
        if e == "fraud_labels" and "is_fraud" not in spec:
            spec["is_fraud"] = {"source": None, "rule": "presence", "confidence": 0.7, "confirm": True}
            mapping["flags"].append({"table": t, "field": "is_fraud", "level": "confirm",
                                     "fr": f"La table « {t} » n'a pas de colonne fraude : chaque ligne est lue comme une fraude confirmée.",
                                     "en": f"Table \"{t}\" has no fraud column: each row is read as a confirmed fraud."})
        mapping["roles"][t] = e
        mapping["tables"][t] = {"entity": e, "fields": spec, "excluded": excluded,
                                "ignored": [c for c in tp if c not in excluded and c not in {s.get("source") for s in spec.values()}]}
    if tx_table and "currency" not in mapping["tables"][tx_table]["fields"]:
        mapping["default_currency"] = "TND"
        mapping["flags"].append({"table": tx_table, "field": "currency", "level": "confirm",
                                 "fr": "Aucune colonne devise : montants supposés en TND.", "en": "No currency column: amounts assumed in TND."})
    for t in mapping["unassigned_tables"]:
        mapping["flags"].append({"table": t, "level": "info", "fr": f"Table « {t} » non reconnue : ignorée (à affecter manuellement si utile).",
                                 "en": f"Table \"{t}\" not recognised: ignored (assign it manually if useful)."})
    mapping["rates"] = {k: v for k, v in DEFAULT_RATES.items()}
    return mapping


def _field_spec(entity, field, kind, col, score, cprof, series, flags, table):
    spec = {"source": col, "confidence": score, "kind": cprof["kind"], "confirm": score < 0.8}
    if kind in ("datetime", "date"):
        _, fmt, amb = dv.parse_datetime(series.dropna().head(5000), cprof["kind"])
        spec["format"] = fmt
        if amb:
            spec["confirm"] = True
            flags.append({"table": table, "field": f"{entity}.{field}", "level": "confirm",
                          "fr": f"« {col} » : jour/mois ambigu, lu comme {fmt}.", "en": f"\"{col}\": ambiguous day/month, read as {fmt}."})
    elif kind == "amount":
        minor = bool(re.search(r"minor|cents?|centimes|millimes", norm(col)))
        spec["scale"] = 0.01 if minor else 1.0
        if minor:
            spec["confirm"] = True
            flags.append({"table": table, "field": f"{entity}.{field}", "level": "confirm",
                          "fr": f"« {col} » est en unités mineures (centimes) : divisé par 100.",
                          "en": f"\"{col}\" is in minor units (cents): divided by 100."})
    elif kind.startswith("code:"):
        vocab = kind[5:]
        vals = _values(series, 200).index.tolist()
        vmap = {v: translate_code(vocab, v) for v in vals}
        if vocab == "status" and set(vals) <= {"0", "1"}:
            vmap = {"0": "APPROUVEE", "1": "REFUSEE"}
            spec["confirm"] = True
            flags.append({"table": table, "field": f"{entity}.{field}", "level": "confirm",
                          "fr": f"« {col} » : convention numérique supposée (0 = acceptée, 1 = refusée).",
                          "en": f"\"{col}\": numeric convention assumed (0 = approved, 1 = declined)."})
        elif vocab == "status" and all(re.fullmatch(r"\d{2}", v) for v in vals):
            vmap = {v: "APPROUVEE" if v == "00" else "REFUSEE" for v in vals}
            flags.append({"table": table, "field": f"{entity}.{field}", "level": "info",
                          "fr": f"« {col} » : codes réponse ISO 8583 (00 = acceptée, autres = refusée).",
                          "en": f"\"{col}\": ISO 8583 response codes (00 = approved, others = declined)."})
        unknown = [v for v, c in vmap.items() if c is None]
        if unknown:
            spec["confirm"] = True
            flags.append({"table": table, "field": f"{entity}.{field}", "level": "confirm",
                          "fr": f"« {col} » : valeurs non traduites {unknown[:6]} (à traduire ou laisser vides).",
                          "en": f"\"{col}\": untranslated values {unknown[:6]} (translate or leave empty)."})
        spec["values"] = vmap
    elif kind == "country":
        spec["format"] = "iso3" if cprof["kind"] == "country3" else "iso2"
    if field in cn.PSEUDONYMISE:
        spec["pseudonymise"] = True
    if spec["confirm"] and not any(f.get("field") == f"{entity}.{field}" for f in flags):
        flags.append({"table": table, "field": f"{entity}.{field}", "level": "confirm",
                      "fr": f"« {col} » → {field} : confiance {score:.0%}, à confirmer.",
                      "en": f"\"{col}\" → {field}: confidence {score:.0%}, please confirm."})
    return spec


# ---------------------------------------------------------------- optional LLM review (names + statistics only)
def ai_review(summary, mapping, lang="fr"):
    """ONE Azure OpenAI call: the model sees column names, kinds and low-cardinality code values (never rows, ids, amounts or
    free text) and returns remarks on doubtful mappings. Suggestions only: a human applies them."""
    import copilot
    if not copilot.configured():
        return None
    prof = {t: {c: {k: p[k] for k in ("kind", "distinct", "null_rate") if k in p} | ({"values": p["values"][:10]} if p["kind"] in
                ("code", "bool", "currency") and "values" in p else {}) for c, p in v["columns"].items()} for t, v in summary["tables"].items()}
    current = {t: {f: s.get("source") for f, s in spec["fields"].items()} | {"_entity": spec["entity"]} for t, spec in mapping["tables"].items()}
    prompt = ("You review a proposed mapping of a bank's tables to a canonical fraud model. Canonical entities and fields: "
              + json.dumps({e: list(f) for e, f in cn.ENTITIES.items()}) + "\nSource profile (no raw rows): " + json.dumps(prof, ensure_ascii=False)
              + "\nProposed mapping: " + json.dumps(current, ensure_ascii=False)
              + "\nAnswer ONLY JSON {\"suggestions\": [{\"table\", \"field\", \"source_column\", \"reason\"}]} listing only changes you are "
              "confident about (max 8). Reason in " + ("French" if lang == "fr" else "English") + ".")
    try:
        text, _ = copilot.complete_json(prompt, tag="[integration] mapping review")
        out = json.loads(text or "{}").get("suggestions", [])
    except Exception as exc:                                  # the rule-based proposal stays valid without the AI
        return {"error": str(exc)[:200]}
    valid = []
    for s in out[:8]:
        t, f, c = s.get("table"), s.get("field"), s.get("source_column")
        if t in mapping["tables"] and f in cn.ENTITIES[mapping["tables"][t]["entity"]] and (c is None or c in summary["tables"][t]["columns"]):
            valid.append({"table": t, "field": f, "source_column": c, "reason": str(s.get("reason", ""))[:300]})
    return {"suggestions": valid}


# ---------------------------------------------------------------- apply
def pseudonymise(series, field, salt):
    """Keyed hash (HMAC-SHA256, per-tenant secret salt): same value -> same token inside one tenant, unlinkable across tenants."""
    vals = series.dropna().astype(str).str.strip().unique()
    key = salt.encode() if isinstance(salt, str) else salt
    table = {v: f"{PREFIX.get(field, 'ID')}-" + hmac.new(key, f"{field}:{v}".encode(), hashlib.sha256).hexdigest()[:16] for v in vals}
    return series.astype(str).str.strip().map(table).where(series.notna())


def _convert(entity, field, spec, raw, salt):
    kind = cn.ENTITIES[entity][field][0]
    if kind in ("datetime", "date"):
        out, _, _ = dv.parse_datetime(raw, spec.get("kind"))
        if spec.get("format") in ("dd/mm/yyyy", "mm/dd/yyyy"):
            out = pd.to_datetime(raw.astype(str).str.strip(), errors="coerce", dayfirst=spec["format"] == "dd/mm/yyyy", format="mixed")
        return out.astype("datetime64[ns]")
    if kind in ("amount", "number", "score"):
        return dv.to_number(raw) * float(spec.get("scale", 1.0))
    if kind.startswith("code:"):
        vm = spec.get("values", {})
        return raw.astype(str).str.strip().map(lambda v: vm.get(v) if v in vm else translate_code(kind[5:], v)).where(raw.notna())
    if kind == "country":
        up = raw.astype(str).str.strip().str.upper()
        return up.map(lambda v: dv.ISO3.get(v, v if len(v) == 2 else None)).where(raw.notna())
    if kind == "currency":
        return raw.astype(str).str.strip().str.upper().where(raw.notna())
    if kind in ("label", "bool"):
        n = raw.astype(str).map(norm)
        return n.map(lambda v: 1 if v in LABEL_TRUE else 0 if v in LABEL_FALSE else np.nan).astype("float")
    if field in cn.PSEUDONYMISE and spec.get("pseudonymise", True):
        return pseudonymise(raw, field, salt)
    return raw.astype(str).str.strip().where(raw.notna())


def apply(tables, mapping, salt, rates=None, now=None):
    """-> (canonical {entity: DataFrame}, report {entity.field: {present, valid, untranslated}})."""
    rates = rates or mapping.get("rates") or DEFAULT_RATES
    out, report = {}, {}
    for t, spec in mapping["tables"].items():
        if t not in tables:
            continue
        e, df = spec["entity"], tables[t]
        frame = pd.DataFrame(index=df.index)
        for field, fs in spec["fields"].items():
            if fs.get("source") is None:
                if fs.get("rule") == "presence":
                    frame[field] = 1
                continue
            raw = df[fs["source"]]
            val = _convert(e, field, fs, raw, salt)
            frame[field] = val
            present = raw.notna() & (raw.astype(str).str.strip() != "")
            ok = present & pd.Series(val, index=df.index).notna()
            report[f"{e}.{field}"] = {"source": f"{t}.{fs['source']}", "present": int(present.sum()), "valid": int(ok.sum()),
                                      "untranslated": raw[present & ~ok].astype(str).value_counts().head(5).to_dict()}
        out[e] = frame.reset_index(drop=True)
    tx = out.get("transactions")
    if tx is not None:
        if "currency" not in tx:
            tx["currency"] = mapping.get("default_currency", "TND")
        if "amount" in tx:
            tx["amount_tnd"] = tx["amount"] * tx["currency"].map({k.upper(): float(v) for k, v in rates.items()}).astype(float)
        lab = out.get("fraud_labels")
        if lab is not None and "is_fraud" not in tx and "transaction_id" in lab:
            pos = set(lab.loc[lab.get("is_fraud", 1) == 1, "transaction_id"].astype(str))
            tx["is_fraud"] = tx["transaction_id"].astype(str).isin(pos).astype(int)
            report["transactions.is_fraud"] = {"source": "fraud_labels (jointure)", "present": len(tx), "valid": len(tx), "untranslated": {}}
        if "is_fraud" in tx:
            tx["is_fraud"] = tx["is_fraud"].astype("Int64")
        me = out.get("merchants")
        if me is not None and "merchant_id" in tx and "merchant_id" in me:      # descriptive attributes held in the merchant table
            ref = me.drop_duplicates("merchant_id").set_index("merchant_id")
            for src, dst in (("category", "merchant_category"), ("city", "city"), ("country", "country")):
                if dst not in tx and src in ref:
                    tx[dst] = tx["merchant_id"].map(ref[src])
                    n = int(tx[dst].notna().sum())        # an attribute the merchant table leaves empty is not a translation error
                    report[f"transactions.{dst}"] = {"source": f"merchants.{src} (jointure)", "present": n, "valid": n, "untranslated": {}}
    cu = out.get("customers")
    if cu is not None and "age" not in cu:
        year = (now or pd.Timestamp.now()).year
        if "birth_year" in cu:
            cu["age"] = year - pd.to_numeric(cu["birth_year"], errors="coerce")
        elif "birth_date" in cu:
            cu["age"] = year - pd.to_datetime(cu["birth_date"], errors="coerce").dt.year
    return out, report


def available_fields(canon, report, min_valid=0.9):
    """'entity.field' usable by modules: mapped AND at least min_valid of the present values translated."""
    av = set()
    for e, df in canon.items():
        for f in df.columns:
            r = report.get(f"{e}.{f}")
            if r is None or r["present"] == 0 or r["valid"] / r["present"] >= min_valid:
                if df[f].notna().any():
                    av.add(f"{e}.{f}")
    return av
