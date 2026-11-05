# AI Banking Copilot for Fraud Detection — Microsoft Fabric + Azure OpenAI

A copilot for a fraud analyst: it **detects** suspicious transactions (model score), **explains** them (facts compared with the customer's own history), **answers questions** in natural language (Azure OpenAI with function calling over the Gold tables), and helps the analyst **decide** (BLOQUER / ESCALADER / VALIDER, with a decision log). The model scores, the LLM only explains, and the analyst decides.

## Architecture

```
SQL source ──copy job──► Fabric Lakehouse lh_fraud (bronze)
                              │  notebooks/01_silver_features   silver_transactions → gold_features (73 past-only features)
                              │  notebooks/02_score_explain     rules + HGB / LightGBM / LambdaRank / blend → champion LightGBM
                              ▼
            Gold: gold_scores · gold_alert_queue · gold_alert_explanations (rules + SHAP) · gold_model_* · submission
                              │  parquet export (Files/app_export)   [plan B of brief §11; plan A = SQL endpoint]
                              ▼
   app/ Streamlit ── tools.py (9 tools, compact JSON) ── copilot.py ── Azure OpenAI (function calling)
                     decisions.csv (feedback)            copilot_log.jsonl (questions, tools, tokens)
```

## Results (validation, Jun–Jul 2026, out-of-time)

| | Alerts | Frauds caught | Recall | Precision |
|---|---|---|---|---|
| Current rules engine | 3,338 | 116 / 1,013 | 11.5 % | 3.5 % |
| Model, same alert volume | 3,338 | 787 | 77.7 % | 23.6 % |
| **Model, top 1 % (analyst capacity)** | **1,779** | **~719** | **70.9 %** | **40.4 %** |

PR-AUC 0.646 (rules 0.014). The model beats the rules engine on 5 of the 6 fraud types. For the sixth (CARTE_CLONEE_ETRANGER), the legacy rule is kept as a complement.

## Run the app

```powershell
cd app
pip install -r requirements.txt
copy .env.example .env      # fill in endpoint, key and deployment (Azure AI Foundry > project home)
python test_aoai.py         # expected output: "OK copilote | tokens: ~25"
streamlit run app.py
```

The app reads `app/data/*.parquet`, which you download from `lh_fraud` › Files › `app_export`. Expected files: `gold_alert_queue`, `gold_alert_explanations`, `gold_model_metrics`, `gold_model_leaderboard`, `gold_model_recall_by_type`, `gold_model_importance`, `customer_history`, `customers`, `digital_events` (optional).

If Azure OpenAI is not configured or unavailable, the copilot switches to a **deterministic offline mode** built on the same tools, so the demo always works.

## Pages

1. **File d'alertes** (alert queue): filters on period, date, channel, risk level and fraud type; risk colours; alerts per day.
2. **Fiche transaction + copilote** (transaction view): score, risk factors (observed vs usual value), reassuring factors, decision with confidence and comment, and the chat with suggested questions (brief §9.7).
3. **Vue client 360** (customer view): profile, habits, timeline of transactions and digital events, and a map when coordinates were exported.
4. **Performance**: model vs current engine, recall per fraud type, top drivers, champion vs challengers.
5. **Journal**: analyst decisions (the feedback loop) and copilot traceability (questions, tools, tokens, cache).

## Rules followed

- Features use only data from before each transaction; the split is by time (never random); test labels are never used or shown.
- `gender`, IDs, `fraud_scenario` and `fraud_reported_date` are never used as features. The only exception is graph features counting frauds already reported before the transaction.
- No secrets in Git: `.env` is ignored. Token discipline: `max_tokens` 600, temperature 0.1, cache, and a log of every call.
