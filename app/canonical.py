"""Hyson canonical data model + capability matrix (universal banking integration).

Every bank keeps its own schema; adapters map it to these entities. Modules are activated only when the data they need exists.
"""

# entity -> {field: (kind, required_for_entity, description)}
ENTITIES = {
    "transactions": {
        "transaction_id": ("id", True, "Identifiant unique de l'opération"),
        "timestamp": ("datetime", True, "Date et heure"),
        "customer_id": ("id", True, "Client"),
        "amount": ("amount", True, "Montant (devise d'origine)"),
        "currency": ("currency", False, "Devise ISO 4217"),
        "card_id": ("id", False, "Carte (masquée / pseudonymisée)"),
        "account_id": ("id", False, "Compte"),
        "merchant_id": ("id", False, "Commerçant / DAB"),
        "channel": ("code:channel", False, "Canal : TPE, DAB, EN_LIGNE, MOBILE, WEB"),
        "transaction_type": ("code:transaction_type", False, "ACHAT, RETRAIT, VIREMENT, PAIEMENT_FACTURE, RECHARGE"),
        "entry_mode": ("code:entry_mode", False, "CHIP, SANS_CONTACT, MAGSTRIPE, ECOM_3DS, ECOM_SANS_3DS, APP_AUTH"),
        "status": ("code:status", False, "APPROUVEE / REFUSEE"),
        "decline_reason": ("text", False, "Motif de refus"),
        "country": ("country", False, "Pays ISO 3166 alpha-2"),
        "city": ("text", False, "Ville"),
        "merchant_category": ("text", False, "Catégorie de commerçant"),
        "device_id": ("id", False, "Appareil"),
        "is_fraud": ("label", False, "Fraude confirmée (1/0)"),
        "risk_score": ("score", False, "Score de risque du système de la banque"),
    },
    "customers": {
        "customer_id": ("id", True, "Client"),
        "age": ("number", False, "Âge"),
        "birth_date": ("date", False, "Date de naissance (convertie en âge)"),
        "birth_year": ("number", False, "Année de naissance (convertie en âge)"),
        "segment": ("text", False, "Segment"),
        "city": ("text", False, "Ville de résidence"),
        "region": ("text", False, "Région / gouvernorat"),
        "monthly_income": ("amount", False, "Revenu mensuel"),
        "kyc_risk": ("text", False, "Niveau de risque KYC"),
        "customer_since": ("date", False, "Client depuis"),
    },
    "cards": {
        "card_id": ("id", True, "Carte"),
        "customer_id": ("id", True, "Titulaire"),
        "card_type": ("text", False, "Type de carte"),
        "daily_limit": ("amount", False, "Plafond journalier"),
        "is_international": ("bool", False, "Carte internationale"),
    },
    "merchants": {
        "merchant_id": ("id", True, "Commerçant / DAB"),
        "category": ("text", False, "Catégorie"),
        "mcc": ("text", False, "Code MCC"),
        "city": ("text", False, "Ville"),
        "country": ("country", False, "Pays"),
    },
    "auth_events": {
        "event_id": ("id", False, "Événement"),
        "timestamp": ("datetime", True, "Date et heure"),
        "customer_id": ("id", True, "Client"),
        "event_type": ("code:event_type", True, "CONNEXION, AJOUT_BENEFICIAIRE, AJOUT_APPAREIL, …"),
        "status": ("code:event_status", False, "SUCCES / ECHEC"),
        "device_id": ("id", False, "Appareil"),
        "ip_country": ("country", False, "Pays de l'adresse IP"),
    },
    "fraud_labels": {
        "transaction_id": ("id", True, "Opération"),
        "is_fraud": ("label", True, "Fraude confirmée"),
        "fraud_type": ("text", False, "Typologie"),
        "reported_at": ("datetime", False, "Date de signalement"),
    },
    "cases": {
        "case_id": ("id", True, "Dossier"),
        "transaction_id": ("id", False, "Opération"),
        "opened_at": ("datetime", False, "Ouverture"),
        "outcome": ("text", False, "Conclusion"),
        "notes": ("text", False, "Résumé d'enquête (texte)"),
    },
}

# never mapped, whatever the bank sends (sensitive or unnecessary: GDPR art. 9 / law 2004-63 / PCI DSS)
EXCLUDED = {"gender": "genre : jamais utilisé (équité)", "sexe": "genre : jamais utilisé (équité)", "religion": "donnée sensible",
            "nationality": "donnée sensible", "nationalite": "donnée sensible", "health": "donnée sensible", "ethnicity": "donnée sensible",
            "cvv": "secret de carte (PCI DSS) : refusé", "cvc": "secret de carte (PCI DSS) : refusé", "pin": "secret de carte : refusé",
            "password": "secret : refusé", "full_name": "identité directe : non nécessaire", "first_name": "identité directe : non nécessaire",
            "last_name": "identité directe : non nécessaire", "nom": "identité directe : non nécessaire", "prenom": "identité directe : non nécessaire",
            "email": "identité directe : non nécessaire", "phone": "identité directe : non nécessaire", "telephone": "identité directe : non nécessaire",
            "address": "identité directe : non nécessaire", "adresse": "identité directe : non nécessaire", "iban": "identifiant bancaire : pseudonymisé",
            "national_id": "identité directe : non nécessaire", "cin": "identité directe : non nécessaire"}
PSEUDONYMISE = {"card_id", "account_id", "customer_id", "device_id"}       # stored as salted hashes per tenant (never the raw PAN / IBAN)

# module -> (requirements, label FR, label EN). A requirement is "entity.field" or "entity.field|entity.field" (any of).
MODULES = {
    "alert_queue": (["transactions.transaction_id", "transactions.timestamp", "transactions.amount", "model|transactions.risk_score"],
                    "File d'alertes", "Alert queue"),
    "transaction_copilot": (["transactions.transaction_id", "transactions.customer_id", "transactions.timestamp", "transactions.amount"],
                            "Fiche transaction & copilote", "Transaction & copilot"),
    "investigation_case": (["transactions.transaction_id", "transactions.timestamp", "transactions.card_id|transactions.customer_id"],
                           "Dossier d'enquête", "Investigation case"),
    "customer_360": (["customers.customer_id", "transactions.customer_id"], "Vue client 360", "Customer 360"),
    "personal_context": (["transactions.country|transactions.city", "transactions.channel", "transactions.customer_id"],
                         "Contexte personnel", "Personal context"),
    "deep_search": (["transactions.transaction_id", "fraud_labels.is_fraud|transactions.is_fraud"], "Enquête approfondie", "Deep search"),
    "trial": (["transactions.transaction_id", "transactions.customer_id", "model|transactions.risk_score"], "Le Procès", "The Trial"),
    "crime_scene_replay": (["transactions.timestamp", "transactions.customer_id", "auth_events.timestamp"], "Reconstitution", "Crime-scene replay"),
    "counter_inquiry": (["model"], "Contre-enquête", "Counter-inquiry"),
    "compromise_network": (["transactions.merchant_id|transactions.device_id", "fraud_labels.is_fraud|transactions.is_fraud"],
                           "Réseau de compromission", "Compromise network"),
    "steering": (["transactions.timestamp", "transactions.amount"], "Pilotage · KPI", "Steering · KPIs"),
    "authentication_anomalies": (["auth_events.event_type", "auth_events.status"], "Anomalies d'authentification", "Authentication anomalies"),
    "institutional_rag": (["cases.notes|fraud_labels.fraud_type"], "Mémoire institutionnelle (RAG)", "Institutional memory (RAG)"),
    "behaviour_anomalies": (["transactions.customer_id", "transactions.timestamp", "transactions.amount"],
                            "Écarts aux habitudes (non supervisé)", "Behaviour anomalies (unsupervised)"),
    "tenant_model": (["transactions.timestamp", "transactions.customer_id", "transactions.amount", "fraud_labels.is_fraud|transactions.is_fraud"],
                     "Modèle propre à la banque (entraînable)", "Bank-specific model (trainable)"),
}

# KPI catalogue: id -> (requirements, FR, EN, SQL over canonical views, chart, dimension or None)
KPIS = {
    "volume_by_day": (["transactions.timestamp"], "Opérations par jour", "Operations per day",
                      "SELECT CAST(timestamp AS DATE) AS jour, COUNT(*) AS operations FROM transactions GROUP BY 1 ORDER BY 1", "line", None),
    "amount_by_channel": (["transactions.channel", "transactions.amount_tnd"], "Montant par canal (TND)", "Amount by channel (TND)",
                          "SELECT channel AS canal, ROUND(SUM(amount_tnd), 3) AS montant_tnd, COUNT(*) AS operations FROM transactions GROUP BY 1 ORDER BY 2 DESC",
                          "bar", "channel"),
    "decline_rate_by_channel": (["transactions.status", "transactions.channel"], "Taux de refus par canal", "Decline rate by channel",
                                "SELECT channel AS canal, ROUND(100.0 * AVG(CASE WHEN status = 'REFUSEE' THEN 1 ELSE 0 END), 2) AS taux_refus_pct, "
                                "COUNT(*) AS operations FROM transactions GROUP BY 1 ORDER BY 2 DESC", "bar", "channel"),
    "fraud_by_channel": (["transactions.is_fraud", "transactions.channel"], "Fraudes par canal", "Frauds by channel",
                         "SELECT channel AS canal, SUM(is_fraud) AS fraudes, COUNT(*) AS operations, ROUND(100.0 * AVG(is_fraud), 3) AS taux_pct "
                         "FROM transactions WHERE is_fraud IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", "bar", "channel"),
    "fraud_by_card_type": (["transactions.is_fraud", "cards.card_type"], "Fraudes par type de carte", "Frauds by card type",
                           "SELECT c.card_type AS type_carte, SUM(t.is_fraud) AS fraudes, COUNT(*) AS operations FROM transactions t "
                           "JOIN cards c ON c.card_id = t.card_id WHERE t.is_fraud IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", "bar", "card_type"),
    "fraud_by_category": (["transactions.is_fraud", "transactions.merchant_category"], "Fraudes par catégorie de commerçant",
                          "Frauds by merchant category",
                          "SELECT merchant_category AS categorie, SUM(is_fraud) AS fraudes, COUNT(*) AS operations FROM transactions "
                          "WHERE is_fraud IS NOT NULL GROUP BY 1 HAVING SUM(is_fraud) > 0 ORDER BY 2 DESC LIMIT 15", "bar", "merchant_category"),
    "fraud_by_country": (["transactions.is_fraud", "transactions.country"], "Fraudes par pays", "Frauds by country",
                         "SELECT country AS pays, SUM(is_fraud) AS fraudes, COUNT(*) AS operations FROM transactions WHERE is_fraud IS NOT NULL "
                         "GROUP BY 1 HAVING SUM(is_fraud) > 0 ORDER BY 2 DESC LIMIT 15", "bar", "country"),
    "fraud_by_segment": (["transactions.is_fraud", "customers.segment"], "Fraudes par segment client", "Frauds by customer segment",
                         "SELECT c.segment, SUM(t.is_fraud) AS fraudes, COUNT(*) AS operations FROM transactions t JOIN customers c "
                         "ON c.customer_id = t.customer_id WHERE t.is_fraud IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", "bar", "segment"),
    "fraud_losses": (["transactions.is_fraud", "transactions.amount_tnd"], "Pertes liées aux fraudes (TND)", "Fraud losses (TND)",
                     "SELECT ROUND(SUM(amount_tnd), 3) AS montant_fraudes_tnd, COUNT(*) AS fraudes FROM transactions WHERE is_fraud = 1", "kpi", None),
    "night_share_frauds": (["transactions.is_fraud", "transactions.timestamp"], "Fraudes la nuit (0h–5h)", "Frauds at night (0–5 h)",
                           "SELECT CASE WHEN HOUR(timestamp) < 6 THEN 'nuit' ELSE 'jour' END AS moment, SUM(is_fraud) AS fraudes, COUNT(*) AS operations "
                           "FROM transactions WHERE is_fraud IS NOT NULL GROUP BY 1", "bar", None),
    "bank_rules_precision": (["transactions.is_fraud", "transactions.risk_score"], "Précision du score actuel de la banque (top 1 %)",
                             "Precision of the bank's current score (top 1%)",
                             "WITH r AS (SELECT is_fraud, NTILE(100) OVER (ORDER BY risk_score DESC) AS pct FROM transactions WHERE is_fraud IS NOT NULL "
                             "AND risk_score IS NOT NULL) SELECT ROUND(100.0 * AVG(is_fraud), 2) AS precision_pct, COUNT(*) AS alertes FROM r WHERE pct = 1",
                             "kpi", None),
    "failed_logins_by_day": (["auth_events.status", "auth_events.timestamp"], "Connexions échouées par jour", "Failed logins per day",
                             "SELECT CAST(timestamp AS DATE) AS jour, SUM(CASE WHEN status = 'ECHEC' THEN 1 ELSE 0 END) AS echecs, COUNT(*) AS evenements "
                             "FROM auth_events GROUP BY 1 ORDER BY 1", "line", None),
    "resolution_time": (["cases.opened_at", "cases.outcome"], "Dossiers par conclusion", "Cases by outcome",
                        "SELECT outcome AS conclusion, COUNT(*) AS dossiers FROM cases GROUP BY 1 ORDER BY 2 DESC", "bar", None),
}


def requirement_met(req, available):
    """available: set of 'entity.field' present after mapping (+ 'model' when a validated tenant model exists)."""
    return any(r in available for r in req.split("|"))


def capabilities(available):
    mods = {m: {"active": all(requirement_met(r, available) for r in reqs),
                "missing": [r for r in reqs if not requirement_met(r, available)], "fr": fr, "en": en}
            for m, (reqs, fr, en) in MODULES.items()}
    kpis = {k: {"active": all(requirement_met(r, available) for r in reqs),
                "missing": [r for r in reqs if not requirement_met(r, available)], "fr": fr, "en": en, "sql": sql, "chart": ch, "dim": dim}
            for k, (reqs, fr, en, sql, ch, dim) in KPIS.items()}
    return mods, kpis
