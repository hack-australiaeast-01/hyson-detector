# AI Banking Copilot for Fraud Detection — Microsoft Fabric + Azure OpenAI

A copilot for a fraud analyst: it **detects** suspicious transactions (model score), **explains** them (facts compared with the customer's own history), **answers questions** in natural language (Azure OpenAI with function calling over the Gold tables), and helps the analyst **decide** (BLOQUER / ESCALADER / VALIDER, with a decision log). The model scores, the LLM only explains, and the analyst decides.

## Architecture

Full diagrams (global architecture, AI workflow, Le Procès sequence, page workflow, demo path): **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — PNG versions for slides in [docs/img/](docs/img/).

```
SQL source ──copy job──► Fabric Lakehouse lh_fraud (bronze)
                              │  notebooks/01_silver_features   silver_transactions → gold_features (73 past-only features)
                              │  notebooks/02_score_explain     rules + HGB / LightGBM / LambdaRank / blend → champion LightGBM
                              ▼
            Gold: gold_scores · gold_alert_queue · gold_alert_explanations (rules + SHAP) · gold_model_* · submission
                              │  live T-SQL via lh_fraud SQL analytics endpoint (brief §11 option A, Entra token)
                              │  fallback: parquet snapshot in app/data (option B), refreshed on every live load
                              ▼
   app/ Streamlit ── tools.py (9 tools, compact JSON) ── copilot.py ── Azure OpenAI (function calling)
                     decisions.csv (feedback)            copilot_log.jsonl (questions, tools, tokens)
```

## Results (validation, Jun–Jul 2026, out-of-time)

> **Data actually used.** The dataset delivered in Fabric is larger than the one described in the brief: **1,908,228 transactions** (train 1,720,600 from 2025-01-01, test 187,628 for Aug–Sep 2026), 3,500 customers, 32,065 legacy alerts (brief: ~435,000 transactions, 2,500 customers, 6,324 alerts). Every figure below is measured on this data. On it, the current rules engine reaches **3.5 % precision / 11.5 % recall** in Jun–Jul (3.9 % / 13 % over the whole train period), well below the brief's ~15 % / ~42 %, which describes the brief's smaller sample.

| | Alerts | Frauds caught | Recall | Precision |
|---|---|---|---|---|
| Current rules engine | 3,338 | 117 / 1,013 | 11.5 % | 3.5 % |
| Model, same alert volume | 3,338 | 787 | 77.7 % | 23.6 % |
| **Model, top 1 % (analyst capacity)** | **1,779** | **718** | **70.9 %** | **40.4 %** |
| Model, top 0.5 % | 890 | 590 | 58.2 % | 66.4 % |

PR-AUC 0.646 (rules 0.014). The model beats the rules engine on 5 of the 6 fraud types. For the sixth (CARTE_CLONEE_ETRANGER), the legacy rule is kept as a complement.

**Alert budget.** The brief's "~1,000 alerts over two months" is 1 % of its 101,730 test transactions; we keep the same **1 %** rule on our 187,628 test transactions (1,876 alerts). If the team can only review ~1,000, the top 0.5 % (≈ 900 alerts) keeps 58 % recall at 66 % precision.

**Score file (§14).** [`submission/submission.csv`](submission/submission.csv): one row per test transaction (187,628), `transaction_id,fraud_score,is_alert`, 1,876 alerts.

## Run the app

```powershell
cd app
pip install -r requirements.txt
copy .env.example .env      # fill in endpoint, key and deployment (Azure AI Foundry > project home)
python test_aoai.py         # expected output: "OK copilote | tokens: ~25"
streamlit run app.py
```

**Data: live from Fabric.** With `DATA_SOURCE=auto` (default), the app connects to the `lh_fraud` SQL analytics endpoint using your Microsoft Entra login (`az login`, otherwise a browser window opens). Requires ODBC Driver 17 or 18 for SQL Server. Gold tables are loaded at startup; customer history (since 2025, with coordinates), digital events and related cases are queried on demand. Analyst decisions are written back to OneLake (`Files/app_feedback/decisions.csv`). If Fabric is unreachable, the app automatically falls back to the parquet snapshot in `app/data/`.

Before the pitch: `python warmup.py` pre-computes the copilot's answers for the 3 demo cases (instant replies; any other question still goes live).

If Azure OpenAI is not configured or unavailable, the copilot switches to a **deterministic offline mode** built on the same tools, so the demo always works.

### Hosted demo (Streamlit Community Cloud)

Live link: **https://hyson-detector.streamlit.app**

- Main file `app/app.py`, Python 3.12, dependencies from `app/requirements.txt`.
- The cloud has no Entra login, so it reads the **Gold snapshot committed in `app/data/*.parquet`** (synthetic data exported from Fabric): Gold tables, the full transaction history since 2025 and the digital events of the 1,814 customers in the alert queue (no test labels). Locally the app reads Fabric live. Online, "related cases" only see those 1,814 customers (labelled "extrait local" in the answer).
- Azure OpenAI: paste the values of [`app/.streamlit/secrets.toml.example`](app/.streamlit/secrets.toml.example) into the app's **Settings → Secrets** (never in Git). Without a key, the demo cases are answered from the pre-computed gpt-5-mini cache and other questions use offline mode.
- Decisions recorded on the hosted app stay in its container (not written to OneLake).

## Pages

The app is branded **Hyson Detector** (light, bank-platform theme; FR/EN). The sidebar groups pages as *Bienvenue · Analyste · Enquête IA · Pilotage*, plus one-click demo cases.

0. **Démarrer ici** (guide): headline KPIs and an 8-step guided tour for a first-time user (welcome dialog on first visit, a hint on each page).
1. **File d'alertes** (alert queue): filters on period, date, channel, risk level and fraud type; risk colours; alerts per day.
2. **Fiche transaction + copilote** (transaction view): score, risk factors (observed vs usual value), reassuring factors, decision with confidence and comment, and the chat with suggested questions (brief §9.7).
3. **Vue client 360** (customer view): profile, habits, timeline of transactions and digital events, and a map when coordinates were exported.
4. **Performance**: model vs current engine, recall per fraud type, top drivers, champion vs challengers.
5. **Journal**: analyst decisions (the feedback loop) and copilot traceability (questions, tools, tokens, cache).
6. **Le Procès** (`courtroom.py`): an AI prosecutor and an AI defence argue the same Fabric facts in parallel, an AI judge rules; the analyst accepts or overrides the verdict (logged as a decision).
7. **Reconstitution**: replays the hours before the alert step by step (transactions + digital events, risky signals in red, map, AI narration).
8. **Contre-enquête**: counterfactual — neutralises the top SHAP factors one by one; "robust" if the alert survives, "sensitive" if it flips.
9. **Constellation**: points of compromise (ATMs/merchants where fraud victims passed in the 30 days before fraud, lift ×2.5–×4.1) with today's alerts orbiting them. Shown as an investigation lead only: exposure was **not** predictive in validation (41 % vs 40 % precision), so it is not in the score.
10. **Impact & processus**: risk-committee view — fraud TND intercepted, legitimate TND not blocked, false alerts avoided, analyst hours (editable assumptions), transaction → decision process, recommendation mix, median alert → decision time, AI cost per alert, PSI drift.
11. **Marché & benchmarks** (`market.py`): our results next to **real public figures with their sources** (EBA/ECB, UK Finance, Banque Centrale de Tunisie, industry false-positive estimate); the same KPIs computed live on our data; a Tunisian-scale scenario with editable assumptions; fraud rate by channel and entry mode (3-D Secure lever); an **audit of the current rules engine** (which rules to switch off); and the **time to detect** (days between a fraud and its report).

The transaction page also has a stopwatch (alert opened → decision saved, stored as `duration_s`) and a printable HTML case file.

## Rules followed

- Features use only data from before each transaction; the split is by time (never random); test labels are never used or shown.
- `gender`, IDs, `fraud_scenario` and `fraud_reported_date` are never used as features. The only exception is graph features counting frauds already reported before the transaction.
- No secrets in Git: `.env` is ignored; Fabric access uses the analyst's Entra login (no stored credential).
- Token discipline: the app detects the question type and fetches the needed facts itself (intent routing + prefetch), so most answers take **one** LLM round; static prompt first (Azure prompt caching, ~1,400 tokens reused per call); compact JSON trimmed by list items (never cut mid-JSON); last 2 exchanges only; `gpt-5-mini` with `reasoning_effort=low` and capped `max_completion_tokens`; answers cached on disk (`warmup.py`); every call logged (question, intent, tools, tokens incl. cached, rounds, latency). Measured: ~3,300 tokens and ~7 s per new question (was ~5,200 / 12 s). `COPILOT_OFFLINE=1` forces the deterministic offline mode.
- Decision: the recommendation (BLOQUER / ESCALADER / VALIDER + confidence) is computed by a documented rule in `tools.recommend` from the risk level, percentile and concordant signals, and backed by validation precision (percentile ≥ 0.998 → 94 % true frauds, ELEVE → 87 %, MOYEN → 20 %). The LLM explains it; it does not invent it.
- Token discipline: the app detects the question type and fetches the needed facts itself (intent routing + prefetch), so most answers take **one** LLM round; static prompt first (Azure prompt caching, ~1,400 tokens reused per call); compact JSON trimmed by list items (never cut mid-JSON); last 2 exchanges only; `gpt-5-mini` with `reasoning_effort=low` and capped `max_completion_tokens`; answers cached on disk (`warmup.py`); every call logged (question, intent, tools, tokens incl. cached, rounds, latency). Measured: ~3,300 tokens and ~7 s per new question (was ~5,200 / 12 s). `COPILOT_OFFLINE=1` forces the deterministic offline mode.
