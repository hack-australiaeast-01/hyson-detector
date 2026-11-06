<p align="center"><img src="app/static/brand/logo_blue.png" width="110" alt="Hyson Detector logo"></p>

# Hyson Detector — AI Banking Copilot for Fraud Detection (Microsoft Fabric + Azure OpenAI)

**Live demo:** https://hyson-detector.streamlit.app · [![tests](https://github.com/hack-australiaeast-01/hyson-detector/actions/workflows/tests.yml/badge.svg)](https://github.com/hack-australiaeast-01/hyson-detector/actions/workflows/tests.yml) · [Model card](docs/MODEL_CARD.md) · [Architecture](docs/ARCHITECTURE.md) · [Audit & bank IT](docs/AUDIT_AND_BANK_INTEGRATION.md) · [Handoff](HANDOFF.md)

A copilot for a fraud analyst: it **detects** suspicious transactions (model score), **explains** them (facts compared with the customer's own history), **answers questions** in natural language (Azure OpenAI with function calling over the Gold tables), and helps the analyst **decide** (BLOQUER / ESCALADER / VALIDER, with a decision log). The model scores, the LLM only explains, and the analyst decides.

## Architecture

Full architecture in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — 18 diagrams: end-to-end, Microsoft Fabric platform, ML pipeline, MLOps lifecycle, Azure AI Foundry / Azure OpenAI layer, where ML and DL are used, each AI pipeline (copilot, Le Procès, Enquête approfondie, Reconstitution, person search, data onboarding, copilot evaluation, Power BI as code), app pages, deployment & security. Images (also for slides) in [docs/img/](docs/img/), editable Mermaid source in [docs/diagrams/](docs/diagrams/).

```
SQL source ──copy job──► Fabric Lakehouse lh_fraud (bronze)
                              │  notebooks/01_silver_features   silver_transactions → gold_features (73 past-only features)
                              │  notebooks/02_score_explain     rules + HGB / LightGBM / LambdaRank / blend → champion LightGBM
                              ▼
            Gold: gold_scores · gold_alert_queue · gold_alert_explanations (rules + SHAP) · gold_model_* · submission
                              │  live T-SQL via lh_fraud SQL analytics endpoint (brief §11 option A, Entra token)
                              │  fallback: parquet snapshot in app/data (option B), refreshed on every live load
                              ▼
   app/ Streamlit ── tools.py (10 tools, compact JSON) ── copilot.py ── Azure OpenAI (function calling)
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

### Robustness and governance (notebook `04_robustness`, run in Fabric)

| Proof | Result |
|---|---|
| **Rolling backtest**: same features, sampling and LightGBM settings as production, re-trained 4 times on the past only, each tested on the next 2 months (Dec–Jan, Feb–Mar, Apr–May, Jun–Jul) | Top-1 % recall **69.4 % ± 2.1 pts** (worst period 66.7 %), precision 39.1 % ± 3.9, PR-AUC 0.622 ± 0.036, fraud value caught 72.5 %. Current rules on the same periods: 12.6 % recall, 3.7 % precision |
| **95 % confidence intervals** (bootstrap of whole days, 1,000 resamples, validation Jun–Jul) | Recall 70.9 % [68.3–73.0] · precision 40.4 % [34.9–45.0] · PR-AUC 0.646 [0.610–0.675] · recall gain vs rules +59.3 pts [56.2–62.0] · false alerts avoided 2,160 [1,971–2,335] |
| **Model registry** | MLflow experiment `hyson-fraud-robustness`, ML model **`hyson-fraud-lightgbm`** v1 with feature list and model card. It reproduces the production scores exactly (rank correlation 1.0, same top 1 %, max difference 0) |
| **Orchestration** | Fabric data pipeline **`pl_hyson_retrain`** (01 → 02 → 03e ∥ 04), not scheduled on purpose (re-scoring changes the demo IDs) · library versions pinned in [`fabric/environment.yml`](fabric/environment.yml) — see [`fabric/`](fabric/README.md) |
| **Fairness** | Legitimate customers wrongly alerted: gap between segments **1.4×** for the model vs **2.8×** for the current rules (age bands 1.2× vs 1.5×); alert rate 0.9–1.1 % everywhere; retirees / 60+ have lower precision (30–35 %) and recall (61–66 %) → monitored ([model card](docs/MODEL_CARD.md)) |
| **Copilot evaluation** | [`app/eval_copilot.py`](app/eval_copilot.py): 18 golden questions (brief §9.7 word for word + unknown ID, off-topic, prompt injection), 0-token checks → **18/18 pass, 99.5 % of the numbers cited are found in the tool outputs** ([report](docs/COPILOT_EVAL.md)) |

Shown in the app on **Performance du modèle → Robustesse et gouvernance**.

## Run the app

```powershell
cd app
pip install -r requirements.txt
copy .env.example .env      # fill in endpoint, key and deployment (Azure AI Foundry > project home)
python test_aoai.py         # expected output: "OK copilote | tokens: ~25"
streamlit run app.py
```

**Data: live from Fabric.** With `DATA_SOURCE=auto` (default), the app connects to the `lh_fraud` SQL analytics endpoint using your Microsoft Entra login (`az login`, otherwise a browser window opens). Requires ODBC Driver 17 or 18 for SQL Server. Gold tables are loaded at startup; customer history (since 2025, with coordinates), digital events and related cases are queried on demand. Analyst decisions are written back to OneLake (`Files/feedback/analyst_decisions/decisions.csv`). If Fabric is unreachable, the app automatically falls back to the parquet snapshot in `app/data/`.

Before the pitch: `python warmup.py` pre-computes the copilot's answers for the 3 demo cases (instant replies; any other question still goes live).

If Azure OpenAI is not configured or unavailable, the copilot switches to a **deterministic offline mode** built on the same tools, so the demo always works.

### Hosted demo (Streamlit Community Cloud)

Live link: **https://hyson-detector.streamlit.app**

- Main file `app/app.py`, Python 3.12, dependencies from `app/requirements.txt`.
- The cloud has no Entra login, so it reads the **Gold snapshot committed in `app/data/*.parquet`** (synthetic data exported from Fabric): Gold tables, the full transaction history since 2025 and the digital events of the 1,814 customers in the alert queue (no test labels). Locally the app reads Fabric live. Online, "related cases" only see those 1,814 customers (labelled "extrait local" in the answer).
- Azure OpenAI: paste the values of [`app/.streamlit/secrets.toml.example`](app/.streamlit/secrets.toml.example) into the app's **Settings → Secrets** (never in Git). Without a key, the demo cases are answered from the pre-computed gpt-5-mini cache and other questions use offline mode.
- Decisions recorded on the hosted app stay in its container (not written to OneLake).

## Data: bronze → quality → silver → gold → star schema (notebook `05_quality_star`)

- **Bronze** = raw tables loaded by the copy job; each run is logged in `bronze_ingestion_log` (rows, columns, schema fingerprint).
- **Row-by-row quality**: 41 documented rules (`dq_rules`, ERROR / WARNING) run on **every row** of the 5 bronze tables (3.4 M records). Each failure is a row of `dq_issues` (table, record, rule, column, value, message); each record gets `OK` / `WARNING` / `REJECTED` in `dq_row_status`; rejected rows go to `quarantine_<table>`; `dq_summary` gives the rate per rule. Result: **0 rejected** (no duplicate, orphan key, impossible code, inconsistent status…), 11,756 warnings (39 amounts > 50,000 TND, 11,717 card-present operations without a place).
- **Star schema** (gold, for analysis in natural language): `fact_transactions` (1.9 M, with the model's score / alert and `fraude_signalee` for the labelled period only) + `fact_digital_events` (782 k) and the dimensions `dim_date` (holidays, payday, model period), `dim_heure`, `dim_geo` (city → governorate → region, country), `dim_client` (age band, segment, residence, KYC risk; no gender), `dim_merchant`, `dim_channel`, `dim_card`. Reconciled in the notebook: bronze = accepted + quarantined, no missing key, no duplicate, no test label.
- Snapshot for the hosted app: `python app/export_star.py` → `app/data/star/*.parquet` (30 MB). Deploy a notebook: `python fabric/deploy_notebook.py notebooks/05_quality_star.ipynb --run` (backs up the current definition first).

## Pages

The app is branded **Hyson Detector** (light, bank-platform theme; FR/EN; every field is white with a visible border and a blue focus ring, and a blue « Étape 1 » marker shows where to start on multi-step pages). The sidebar groups the 21 pages as *Assistant · Analyste · Enquête IA · Pilotage · Données · Démo (optionnel)*; demo cases and system info are folded away.

00. **Assistant IA** (`assistant.py` + `askdata.py`, the first page): one question box in the middle, like a chat assistant, on a soft blue aura. Any question in natural language (French, English, derja) → Azure OpenAI writes **one SQL query on the star schema** → the query is parsed and checked (`sqlglot`: a single SELECT, only the 9 star tables, no file / function / external access, 1,000-row cap) → run on the Fabric SQL endpoint (live; read-only by design) or DuckDB on the committed snapshot → short summary of the returned rows only (numbers copied, never computed by the AI), automatic chart (KPI, line, bars, map), the table, the SQL and follow-up questions. A question about one transaction (TX…) goes to the fraud copilot. Offline (no key) a rule-based translator handles count / sum / average · by dimension · filters, and the suggested questions are pre-computed.
0b. **Contexte personnel** (`context.py`, `ctxpage.py`; also one line on the transaction page for operations abroad): is this operation coherent with THIS customer's life? Reads only facts the bank already holds — previous trips to the place, travel preparation (airline / agency / hotel in 90 days), stay in progress, time since the last payment elsewhere (impossible travel), chip / contactless / magnetic stripe, ATM vs shop, amount vs his own habits and income, his phone logged in from that country, travel waves of the bank's customers, a travel notice he declared — never his religion, health, family or reasons. Each signal is weighed by its fraud rate measured on 2025 and tested on 2026 (4,138 payments abroad never used to fit): ROC-AUC 0.858; "Voyage cohérent" = 1,577 operations at 1.1% fraud holding 1,559 of the 3,802 false alerts of the current engine abroad; "Peu cohérent" = 42% fraud. Business guardrails: an amount never reassures, one direction per signal. Works on any new operation (typed, or another bank's CSV feed read in time order) without retraining; gives a respectful contact script and records travel notices. Fit / test: `python app/build_context.py` ([report in STATUS 7.21](STATUS.md)).
0c. **Dossier d'enquête** (`casepage.py`, `intel.py`, `investigation.py`, `memory.py`; button on every transaction page): the case lives on after the alert. A time slider (at the alert · +6 h · +24 h · +72 h) shows only what was known then; reactivation triggers (new uses of the card, declines, failed logins, two places at once, new alerts, rising amounts); the 8 most similar past cases from a behavioural memory of 16,302 cases (Azure OpenAI embeddings + model features) with their status as known at the time; Prosecution and Defence argue on a numbered evidence board; the Judge — the Azure AI Foundry agent `judge-patern` — grades each argument's evidence, lists contradictions and missing information, and may deviate from the system recommendation only with post-alert evidence; every citation is checked in code. The employee accepts, rejects, asks for more, adds context, escalates or records the customer's confirmation (rationale required, append-only case file). Demo: TX01631347 → ESCALADER at the alert, BLOQUER at +24 h (card in Tozeur and Tripoli 4 min apart).
0d. **Intelligence fraude** (`steering.py`): click a bar to drill down (channel → card type → … → transactions and same-card sequences); facts K1…Kn computed in SQL (concentration, magnetic-stripe fallback, authentication events, rules vs model coverage, trend, missing data); the AI classifies 1–3 patterns (cybersecurity / administrative / technical / customer / coordinated) with evidence, confidence, next investigation and impact, fact vs hypothesis.
0e. **Rapports IA** (`reportpage.py`, `report_*.py`; also `POST /v1/tenants/{id}/reports` in the API): ask for a report in plain language — *« rapport trimestriel détaillé sur la fraude aux DAB comparé au trimestre précédent, pour la direction »*, an investigation report on a TX, a cybersecurity assessment, an operational report, in French, English or Arabic. The platform shows what it understood (type, reader, period and comparison, scope, depth, language, confidentiality, sections — all editable), then runs a pipeline that **analyses before writing**: fixed SQL per figure on the bank's data, verification (period, duplicates, sums, independent recount, label coverage), rule-based insights (what · evidence · why · hypotheses · impact · action · priority), charts with title, unit, period and source. Confirmed fraud (bank label) and suspected (model alert without label) are never mixed; security findings are indicators to verify, never claims of an attack. Every statement is tagged (verified fact, ML prediction, AI interpretation, employee-confirmed, hypothesis, recommendation, data limitation) and points to the evidence register; the optional AI writer is kept only if every number it writes is in the evidence. Review: preview, edit or regenerate a section, change the reader or period (same facts), comments, version diff; a named employee approves; PDF / DOCX / HTML / XLSX are archived with their SHA-256; institution branding, terminology and saved templates. Details: [ARCHITECTURE §12](docs/ARCHITECTURE.md#12-ai-reporting-engine-professional-evidence-based-reports).
0. **Visite guidée** (demo, optional): headline KPIs and an 8-step guided tour for a first-time user (welcome dialog on first visit, a hint on each page).
1. **File d'alertes** (alert queue): filters on period, date, channel, risk level and fraud type; risk colours; alerts per day.
2. **Fiche transaction + copilote** (transaction view): score, risk factors (observed vs usual value), reassuring factors, decision with confidence and comment, and the chat with suggested questions (brief §9.7).
3. **Vue client 360** (customer view): profile, habits, timeline of transactions and digital events, and a map when coordinates were exported.
4. **Performance**: model vs current engine, recall per fraud type, top drivers, champion vs challengers, and **Robustesse et gouvernance** (4-period backtest, confidence intervals, fairness by segment and age, copilot evaluation).
4b. **Enquête approfondie** (`deepsearch.py`): watch list of medium alerts whose customer already had an alert (≈ 53 % fraud vs 16 %), evidence board E1…En (habits, digital events, linked customers, points of compromise, 25 most similar labelled alerts), one AI call to connect the dots.
4c. **Tableau de bord Power BI**: the Fabric report (Direct Lake), embedded securely (viewer signs in with an Entra ID account).
5. **Journal**: audit trail of analyst decisions (who, what the system recommended, model / prompt version, SHA-256 hash chain with an integrity check, override rate, message to the bank's systems — simulated) and copilot traceability (questions, tools, tokens, cache). See [docs/AUDIT_AND_BANK_INTEGRATION.md](docs/AUDIT_AND_BANK_INTEGRATION.md).
6. **Le Procès** (`courtroom.py`): an AI prosecutor and an AI defence argue the same Fabric facts in parallel, an AI judge rules; the analyst accepts or overrides the verdict (logged as a decision).
7. **Reconstitution**: replays the hours before the alert step by step (transactions + digital events, risky signals in red, map, AI narration).
8. **Contre-enquête**: counterfactual — neutralises the top SHAP factors one by one; "robust" if the alert survives, "sensitive" if it flips.
9. **Réseau de compromission** (formerly Constellation; bank-style network: ■ ATM, ◆ online site, ● shop, alerts in risk colours): points of compromise (ATMs/merchants where fraud victims passed in the 30 days before fraud, lift ×2.5–×4.1) with today's alerts orbiting them. Shown as an investigation lead only: exposure was **not** predictive in validation (41 % vs 40 % precision), so it is not in the score.
10. **Impact & processus**: risk-committee view — fraud TND intercepted, legitimate TND not blocked, false alerts avoided, analyst hours (editable assumptions), transaction → decision process, recommendation mix, median alert → decision time, AI cost per alert, PSI drift.
11. **Marché & benchmarks** (`market.py`): our results next to **real public figures with their sources** (EBA/ECB, UK Finance, Banque Centrale de Tunisie, industry false-positive estimate); the same KPIs computed live on our data; a Tunisian-scale scenario with editable assumptions; fraud rate by channel and entry mode (3-D Secure lever); an **audit of the current rules engine** (which rules to switch off); and the **time to detect** (days between a fraud and its report).
12. **Nouvelle source de données** (`onboarding.py`): load a partner's file → profile → proposed mapping to our schema with confidence (rules; optional single AI call on column names and statistics only) → translation of codes, countries, dates and currencies → accuracy and drift vs our data → **human approval** → versioned data contract. Sample: `app/samples/partner_bank_sample.csv`.
12b. **Intégration bancaire** (`integpage.py` on `tenants.py`; same engine as the REST API `app/api.py`): connect **any bank, whatever its schema** — 7 steps: *Connecter* (SQLite / CSV / JSON-lines / Parquet, or one of 3 simulated banks) → *Découvrir* (tables, keys, links drawn as a graph) → *Comprendre* (AI-assisted roles and field mapping with confidence, code translation, sensitive columns excluded, decisions to confirm) → *Valider* (readiness score, every KPI executed, reconciliation with the bank's control totals, capability matrix) → *Approuver & activer* (named approval, bank-specific model trained on its own past and approved separately) → *Exploiter* (generated dashboard, alert queue with reasons, the bank's own memory, a webhook test) → *Journal & API* (hash-chained audit). Details and measured results: [ARCHITECTURE §11](docs/ARCHITECTURE.md#11-universal-banking-integration-any-bank-any-schema).
13. **Find a person**: on Vue client 360 and in the copilot, describe a customer ("retraité de Sfax de plus de 70 ans avec des alertes") → read-only search on approved filters (`person_search.py`, tool `find_customers`); IDs typed in a question override the open transaction.
14. **Nazar · agent de travail** (`nazar.py`, a floating evil-eye button on every page with a short explanation; click to open): a work agent that also talks. Commands are parsed by rules (0 token): `mes tâches` (briefing: alerts left, high-confidence blocks, deep-search priorities, journal integrity), `suivante` (opens the most urgent unhandled alert), `top 10 d'hier`, `alertes à bloquer`, `ouvre / procès / reconstitution TX…`, `C000488`, `client retraité de Sfax…`, `vérifie le journal`, `kpi`, any page name, FR/EN. `bloque TX…` / `valide celle-ci` only **prepares** the decision (system recommendation, measured fraud rate, override warning); the analyst must click Confirm, and it is then written to the hash-chained journal with source `agent_nazar`. Questions about the open alert ("pourquoi cette alerte…", "ce client…") go to the copilot, which reads the data. Small talk (hello, thanks, a joke) is answered offline; anything else becomes a short conversation on Azure OpenAI with Nazar's persona: it only sees aggregates (queue counts, validation KPIs, the open alert's ID), has no tools, never records anything, and suggests the exact command to run as a clickable chip. Without a key, commands and small talk keep working. Every message is logged with its tokens in `app/data/agent_log.jsonl` and shown on the Journal page. In **Voice** mode the window shows a **3D Nazar robot** (three.js built in code, `app/nazar_avatar.py` + `app/components/nazar_avatar/`): it follows the cursor, blinks, moves its mouth and shows a speech bubble on every reply. **Mode** Chat / Voice (voice = browser speech, free: mic input in Chrome / Edge, replies read aloud). **Brain** Nazar (commands + fraud talk on the bank's aggregates) or GPT-5 mini (general assistant, no bank data, no earlier Nazar answers, cannot record decisions).

The transaction page also has a stopwatch (alert opened → decision saved, stored as `duration_s`) and a printable HTML case file.

## Universal Banking API

```powershell
pip install -r app/requirements-api.txt
$env:HYSON_PLATFORM_KEY = "<long random secret>"     # only the platform operator can create a bank
cd app; uvicorn api:app --port 8600                   # OpenAPI docs: http://localhost:8600/docs
```

`POST /v1/tenants` (platform key) returns the bank's admin key and webhook secret once; then `sources` → `discover` → `mapping/propose` → `PUT mapping` (confirm / fix) → `validate` (with control totals) → `approve` → `activate`; `model/train` + `model/{v}/approve`; `kpis/{id}`, `alerts`, `memory/ask` for analysts; `events` for real-time operations signed with HMAC-SHA256. Keys are per bank and per role (admin / analyst / ingest), stored hashed; every step is in the bank's hash-chained audit trail. Rebuild the simulated banks: `cd app; python build_bank_fixtures.py` (needs Fabric).

## Tests

```powershell
pip install -r app/requirements-api.txt pytest
python -m pytest -q        # 166 tests, ~3 min, offline (snapshot), no Fabric / Azure OpenAI call
```

`tests/` checks: no test labels anywhere, 1 % alert budget, documented KPIs (117 / 3,221 vs 718 / 1,061), decision-rule bands, calibration of the measured fraud rate, habits computed on the past only, related cases count only frauds reported before, person search on approved filters, the hash-chained audit trail, explanations a banker can trust (habits verdict computed, risky-looking model factors never shown as reassuring), the Nazar agent (command parsing, decisions only after confirmation, logging), submission format, no secret in tracked files, the universal bank integration (3 simulated banks end to end: roles recognised, totals reconciled, sensitive columns excluded and erased, ids pseudonymised, capabilities gated by the data, approval rules, time-split model only used after approval, per-bank memory, REST API with roles, tenant isolation and signed / replay-protected webhook), the AI reporting engine (the brief's example request understood, figures reconciled with the KPIs, confirmed vs suspected never mixed, every written number grounded, same facts for every audience, PDF / DOCX / XLSX / Arabic HTML, edit → approve → archived hash, bank reports isolated through the API), copilot guardrails (unknown ID, decision, intents, demo calendar) and every page rendering in FR and EN. GitHub Actions runs them on every push. The copilot's answers themselves are evaluated by `app/eval_copilot.py` (18 golden questions, [report](docs/COPILOT_EVAL.md)).

## Rules followed

- Features use only data from before each transaction; the split is by time (never random); test labels are never used or shown.
- `gender`, IDs, `fraud_scenario` and `fraud_reported_date` are never used as features. The only exception is graph features counting frauds already reported before the transaction.
- No secrets in Git: `.env` is ignored; Fabric access uses the analyst's Entra login (no stored credential).
- Token discipline: the app detects the question type and fetches the needed facts itself (intent routing + prefetch), so most answers take **one** LLM round; static prompt first (Azure prompt caching, ~1,400 tokens reused per call); compact JSON trimmed by list items (never cut mid-JSON); last 2 exchanges only; `gpt-5-mini` with `reasoning_effort=low` and capped `max_completion_tokens`; answers cached on disk (`warmup.py`); every call logged (question, intent, tools, tokens incl. cached, rounds, latency). Measured: ~3,300 tokens and ~7 s per new question (was ~5,200 / 12 s). `COPILOT_OFFLINE=1` forces the deterministic offline mode.
- Decision: the recommendation (BLOQUER / ESCALADER / VALIDER + confidence) is computed by a documented rule in `tools.recommend` from the risk level, percentile and concordant signals, and backed by validation precision (percentile ≥ 0.998 → 94 % true frauds, ELEVE → 87 %, MOYEN → 20 %). The LLM explains it; it does not invent it.
