"""Lakehouse layout of lh_fraud (Microsoft Fabric, schema-enabled): the single source of truth for where every table lives.

Medallion + purpose schemas:
  bronze   raw data exactly as delivered by the bank (copy job cj_bronze_load) + the ingestion log
  quality  data-quality rules, issues per row, row status, summary, quarantined rows (notebook 05)
  silver   cleaned, conformed and joined operations (notebook 01)
  gold     model-ready features, scores, alert queue and explanations (notebooks 01–02)
  ml       model evaluation: metrics, leaderboard, importance, confidence intervals, robustness (notebooks 02, 04)
  mart     star schema for analysis in natural language: dimensions + facts (notebook 05)
  serving  tables shaped for one consumer: the Power BI Direct Lake model sm_fraud_copilot (notebook 03e)
  meta     data catalog (this layout, row counts, owners) and the migration log
`dbo` stays the lakehouse's default schema and is intentionally empty.

Used by the app (Fabric queries), the export scripts and notebooks/gen_nb06.py (migration + catalog).
"""

LAYERS = {
    "bronze": ("Données brutes telles que livrées par la banque", "Raw data as delivered by the bank"),
    "quality": ("Contrôles qualité ligne à ligne et quarantaine", "Row-level data quality and quarantine"),
    "silver": ("Opérations nettoyées, conformées et jointes", "Cleaned, conformed and joined operations"),
    "gold": ("Caractéristiques, scores, file d'alertes, explications", "Features, scores, alert queue, explanations"),
    "ml": ("Évaluation et robustesse du modèle", "Model evaluation and robustness"),
    "mart": ("Schéma en étoile pour l'analyse", "Star schema for analysis"),
    "serving": ("Tables servies au rapport Power BI", "Tables served to the Power BI report"),
    "meta": ("Catalogue de données et journal de migration", "Data catalog and migration log"),
}

# logical name (historical dbo name) -> (schema, table, producer, description)
TABLES = {
    # bronze — source names kept on purpose (traceable to the bank's database db-fraud-australiaeast)
    "transactions_train": ("bronze", "transactions_train", "cj_bronze_load", "Opérations janv. 2025 → juil. 2026"),
    "transactions_test": ("bronze", "transactions_test", "cj_bronze_load", "Opérations août → sept. 2026 (labels détenus par le jury)"),
    "customers": ("bronze", "customers", "cj_bronze_load", "Clients (3 500)"),
    "cards": ("bronze", "cards", "cj_bronze_load", "Cartes"),
    "merchants": ("bronze", "merchants", "cj_bronze_load", "Commerçants et DAB"),
    "digital_events": ("bronze", "digital_events", "cj_bronze_load", "Événements de la banque digitale"),
    "fraud_labels_train": ("bronze", "fraud_labels_train", "cj_bronze_load", "Fraudes signalées (période d'entraînement)"),
    "legacy_rule_alerts_train": ("bronze", "legacy_rule_alerts_train", "cj_bronze_load", "Alertes du moteur de règles actuel"),
    "v_transactions_all": ("bronze", "v_transactions_all", "cj_bronze_load", "Vue source : toutes les opérations"),
    "v_transactions_train_labeled": ("bronze", "v_transactions_train_labeled", "cj_bronze_load", "Vue source : opérations labellisées"),
    "bronze_ingestion_log": ("bronze", "ingestion_log", "05_quality_star", "Journal des chargements (lignes, colonnes, empreinte du schéma)"),
    # quality
    "dq_rules": ("quality", "rules", "05_quality_star", "41 règles documentées (ERROR / WARNING)"),
    "dq_issues": ("quality", "issues", "05_quality_star", "Une ligne par anomalie : table, enregistrement, règle, valeur"),
    "dq_row_status": ("quality", "row_status", "05_quality_star", "Statut de chaque enregistrement : OK / WARNING / REJECTED"),
    "dq_summary": ("quality", "summary", "05_quality_star", "Taux d'échec par règle"),
    "quarantine_transactions": ("quality", "quarantine_transactions", "05_quality_star", "Opérations rejetées"),
    "quarantine_customers": ("quality", "quarantine_customers", "05_quality_star", "Clients rejetés"),
    "quarantine_cards": ("quality", "quarantine_cards", "05_quality_star", "Cartes rejetées"),
    "quarantine_merchants": ("quality", "quarantine_merchants", "05_quality_star", "Commerçants rejetés"),
    "quarantine_digital_events": ("quality", "quarantine_digital_events", "05_quality_star", "Événements rejetés"),
    # silver
    "silver_transactions": ("silver", "transactions", "01_silver_features", "Opérations nettoyées + client + carte + commerçant"),
    # gold
    "gold_features": ("gold", "features", "01_silver_features", "73 caractéristiques calculées sur le passé uniquement"),
    "gold_scores": ("gold", "scores", "02_score_explain", "Score du modèle de chaque opération"),
    "gold_alert_queue": ("gold", "alert_queue", "02_score_explain", "File d'alertes (top 1 % par période)"),
    "gold_alert_explanations": ("gold", "alert_explanations", "02_score_explain", "Facteurs SHAP et règles par alerte"),
    # ml
    "gold_model_metrics": ("ml", "model_metrics", "02_score_explain", "Métriques de validation"),
    "gold_model_leaderboard": ("ml", "model_leaderboard", "02_score_explain", "Comparaison des modèles"),
    "gold_model_importance": ("ml", "model_importance", "02_score_explain", "Importance des variables"),
    "gold_model_recall_by_type": ("ml", "model_recall_by_type", "02_score_explain", "Rappel par typologie de fraude"),
    "gold_model_ci": ("ml", "model_ci", "04_robustness", "Intervalles de confiance (bootstrap par jour)"),
    "gold_model_robustness": ("ml", "model_robustness", "04_robustness", "Backtest glissant sur 4 périodes"),
    "gold_model_robustness_types": ("ml", "model_robustness_types", "04_robustness", "Backtest par typologie"),
    # mart (star schema)
    "dim_date": ("mart", "dim_date", "05_quality_star", "Calendrier (jours fériés, paie, période du modèle)"),
    "dim_heure": ("mart", "dim_heure", "05_quality_star", "Heures et tranches horaires"),
    "dim_geo": ("mart", "dim_geo", "05_quality_star", "Ville → gouvernorat → région → pays"),
    "dim_client": ("mart", "dim_client", "05_quality_star", "Profil client (sans genre)"),
    "dim_merchant": ("mart", "dim_merchant", "05_quality_star", "Commerçants"),
    "dim_channel": ("mart", "dim_channel", "05_quality_star", "Type d'opération × canal × mode de saisie"),
    "dim_card": ("mart", "dim_card", "05_quality_star", "Cartes"),
    "fact_transactions": ("mart", "fact_transactions", "05_quality_star", "Fait : opérations + score + alerte"),
    "fact_digital_events": ("mart", "fact_digital_events", "05_quality_star", "Fait : événements de l'application"),
    # serving (Power BI contract: names kept, the semantic model maps them)
    **{f"pbi_{t}": ("serving", f"pbi_{t}", "03e_powerbi_dashboard", f"Power BI · {t}")
       for t in ["alerts", "compare", "factors", "importance", "kpi", "leaderboard", "recall_type", "recall_wide"]},
}

FILES = {  # old Files/ path -> new Files/ path
    "app_export": "exports/app_snapshot",
    "submission": "exports/submission",
    "app_feedback": "feedback/analyst_decisions",
    "robustness": "ml/robustness",
}
FEEDBACK_FILE = "Files/feedback/analyst_decisions/decisions.csv"


def fq(logical):
    """Fully-qualified name in the lakehouse / SQL endpoint, e.g. fq('gold_alert_queue') -> 'gold.alert_queue'."""
    s, t, *_ = TABLES[logical]
    return f"{s}.{t}"
