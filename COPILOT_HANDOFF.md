yo# Handoff for GitHub Copilot — AI Banking Copilot for Fraud Detection

Give this whole file to GitHub Copilot (Chat / Agent mode) as context. Work through the tasks in order; each has an acceptance check. Full challenge brief in English: `BRIEF_SUMMARY.md` (same folder). Progress tracker: `STATUS.md`.

---

## 0. Ground rules (from the brief — the jury checks these)

1. **Past only:** a feature for a transaction may use only rows with an earlier timestamp. Use `shift(1)`, `expanding()`, Spark windows `rowsBetween(Window.unboundedPreceding, -1)` / `rangeBetween(-secs, -1)`.
2. **Never use as features:** `is_fraud`, `fraud_scenario`, `fraud_reported_date` (exception: graph features may count frauds whose `fraud_reported_date` < the transaction date), legacy `analyst_decision`, IDs as numbers, `gender`.
3. **Time split, never random.** Validate on the last ~2 labelled months.
4. **Metrics:** PR-AUC (main), precision & recall at top 1 %, comparison to the legacy rule engine (precision ~15 %, recall ~42 %), recall per `fraud_scenario`. Never accuracy.
5. **The model scores, the LLM explains.** The LLM never computes a score and never receives raw rows — only compact JSON facts from tools.
6. **No secrets in the repo.** Credentials only in a local `.env` (gitignored) and in the Fabric connection.
7. **Token / capacity efficiency is judged:** small model by default, max output tokens on every call, cache identical calls, log every call's tokens. Develop on samples, stop Spark sessions.
8. Analyst always decides: copilot recommends **BLOQUER / ESCALADER / VALIDER** with a confidence level.

---

## 1. Environment (already done)

| Item | Value |
|---|---|
| Fabric workspace | `ws-hack-fraud-australiaeast` |
| Lakehouse | `lh_fraud` (tables in schema `dbo`) |
| Source DB | Azure SQL `db-fraud-australiaeast` via Fabric connection `saitaflex_connection` (credentials NOT in repo) |
| Load | Copy job `cj_bronze_load` — full copy, succeeded |
| Notebooks imported | `01_silver_features`, `02_score_explain` (local copies in `notebooks/`) |

### Tables in `lh_fraud` and real sizes (measured 2026-11-05)

| Table | Rows | Note |
|---|---|---|
| customers | **3,500** | brief said 2,500 |
| transactions_train | **1,720,600** | brief said 333,059 |
| transactions_test | **187,628** | brief said 101,730 |
| fraud_labels_train | 1,720,600 | one label per train transaction |
| v_transactions_all | 1,908,228 | train + test, has a `split` column (`train` / `test`) |
| v_transactions_train_labeled | — | train joined with labels |
| cards, merchants, digital_events, legacy_rule_alerts_train | — | as in brief |

**Checked:** 0 test transaction IDs appear in `fraud_labels_train` → no label leak in the data.
**Consequence:** the dataset is **~4–5× bigger than the brief** and its **date ranges may differ from the brief** (Jan→Jul train / Aug→Sep test). Notebook 01 currently assigns periods by calendar month, which mislabelled labelled train rows as "test" (234 "test" frauds in the sample run). **Fix in Task 1.**

### Columns (exact)

- **transactions_train / transactions_test:** transaction_id, timestamp (datetime2), customer_id, card_id, transaction_type, channel, entry_mode, merchant_id, merchant_category, mcc, beneficiary_id, amount_tnd (decimal), original_currency, city, country, latitude, longitude, device_id, ip_country, session_id, status, decline_reason
- **v_transactions_all:** `split` + the columns above
- **fraud_labels_train:** transaction_id, is_fraud (smallint), fraud_scenario, fraud_reported_date (date)
- **customers:** customer_id, age, gender, segment, occupation, home_city, governorate, customer_since, monthly_income_tnd, avg_monthly_balance_tnd, kyc_risk_level, digital_banking_user
- **cards:** card_id, customer_id, card_type, is_international, issue_date, expiry_date, daily_limit_tnd, atm_daily_limit_tnd, contactless_enabled
- **merchants:** merchant_id, merchant_name, category, mcc, merchant_type, city, country, latitude, longitude
- **digital_events:** event_id, timestamp, customer_id, session_id, event_type, channel, device_id, ip_country, auth_method, status, beneficiary_id
- **legacy_rule_alerts_train:** alert_id, transaction_id, alert_timestamp, rules_triggered, analyst_decision

**Codes:** channel = TPE (store), DAB (ATM), EN_LIGNE, MOBILE, WEB · entry_mode = CHIP, SANS_CONTACT, MAGSTRIPE, ECOM_3DS, ECOM_SANS_3DS, APP_AUTH · transaction_type = ACHAT, RETRAIT, VIREMENT, PAIEMENT_FACTURE, RECHARGE · status = APPROUVEE / REFUSEE · event_type = CONNEXION, AJOUT_APPAREIL, AJOUT_BENEFICIAIRE, REINITIALISATION_MOT_DE_PASSE, MODIFICATION_NUMERO_TELEPHONE (status SUCCES / ECHEC; channel incl. AGENCE, CENTRE_APPEL).

---

## 2. Tasks

### Task 1 — Check the date ranges, then fix the split in notebook 01  ⚠️ do first

Run in the `lh_fraud` SQL analytics endpoint:
```sql
SELECT split, MIN([timestamp]) AS first_ts, MAX([timestamp]) AS last_ts, COUNT(*) AS n
FROM v_transactions_all GROUP BY split;

SELECT FORMAT(t.[timestamp], 'yyyy-MM') AS month, COUNT(*) AS n, SUM(CAST(l.is_fraud AS INT)) AS frauds
FROM transactions_train t JOIN fraud_labels_train l ON l.transaction_id = t.transaction_id
GROUP BY FORMAT(t.[timestamp], 'yyyy-MM') ORDER BY month;
```

Then in `01_silver_features`, silver cell: **keep the `split` column** and derive `period` from it instead of calendar months:
- `split == 'test'` → `period = 'test'`
- `split == 'train'` and timestamp in the **last 2 labelled months** → `period = 'valid'`
- other train rows → `period = 'train'`
- Compute the cut-off from the data (`max(timestamp)` of train minus ~2 months), don't hard-code.
- Also force labels to NULL on test rows (defensive): `is_fraud`, `fraud_scenario`, `fraud_reported_date`.

**Accept:** per-period table shows `test` with **0 frauds**, valid ≈ last 2 train months, fraud rate ≈ 0.5–0.7 % in train and valid.

### Task 2 — Keep notebook 01 cheap on 1.9 M rows, then full run

- Run once with `SAMPLE = True` (300 customers) → all cells green.
- Set `spark.sql.shuffle.partitions` to `200` for the full run (data is 4–5× bigger than planned).
- `SAMPLE = False`, run once. Last cell stops the session.
- "Data skew" warnings in diagnostics are expected (NULL `card_id` / `merchant_id` on transfers) and harmless.

**Accept:** `gold_features` exists with ~1.9 M rows; sanity cell shows higher fraud rate for `f_new_country_phys`, `f_magstripe`, etc. than the base rate.

### Task 3 — Make notebook 02 fit in memory

Notebook 02 does `spark.table("gold_features").toPandas()`. With 1.9 M rows × ~75 columns that's ~1.2 GB+ — risky. Change it to:
- **Training set:** all frauds + a 10 % random sample of legit rows from train (and from train+valid for the refit), with `sample_weight` 10 for sampled legit rows (or keep the existing imbalance weight logic consistently).
- **Scoring:** score valid and test in Spark chunks or with a pandas UDF (`mapInPandas`) using the fitted model, or `toPandas()` only the needed feature columns per period.
- Keep everything else: rules score, model, validation metrics, legacy comparison, per-scenario recall, alert budget 1 % per period, `gold_scores`, `gold_alert_queue`, `gold_alert_explanations`, `gold_model_metrics`, `Files/submission/submission.csv`.
- Update `DEMO_IDS` in step 5: the brief's IDs (`TX00267400`, `TX00283105`) may not exist in this bigger dataset — check with `SELECT * FROM transactions_train WHERE transaction_id IN ('TX00267400','TX00283105')`; otherwise pick 3 demo cases from validation (one obvious fraud, one subtle fraud, one legacy false positive the model scores low).

**Accept:** printed JSON with `pr_auc_model`, `model_top1pct_precision/recall`, `model_same_budget_as_legacy_precision/recall` vs `legacy_precision/recall`; model beats legacy at the same alert budget.

### Task 4 — Get data to the app

Option A (preferred): Streamlit reads Gold via the Lakehouse **SQL analytics endpoint** (pyodbc + ODBC Driver 18, Entra auth `ActiveDirectoryInteractive` or `ActiveDirectoryDefault`). Connection string from SQL endpoint → "Copy SQL connection string".
Option B (plan B): in a notebook, export `gold_alert_queue`, `gold_alert_explanations`, `gold_model_metrics`, and per-alerted-customer history to Parquet under `Files/export/`, download, read locally. Keep the Fabric pipeline visible in the pitch.

**Accept:** a local Python function returns the top 20 alerts for a given day.

### Task 5 — Copilot tools (Python, read Gold, return compact JSON ≤ ~1 KB)

| Tool | Returns |
|---|---|
| `get_alert_queue(date, n)` | top-n alerts of the day: id, amount, channel, country, score, risk_level, top_factors |
| `get_transaction(transaction_id)` | detail + score + 3–5 factors (observed vs usual) |
| `get_customer_profile(customer_id)` | segment, age band, income, home city, avg/median amount, usual countries/cities/hours, # devices, # beneficiaries |
| `compare_to_habits(transaction_id)` | numeric gaps: amount ratio, new country/merchant/device, hour vs usual, speed |
| `get_customer_history(customer_id, days)` | aggregated recent activity (counts per day/country/channel), not raw rows |
| `get_digital_events(customer_id, around, hours=24)` | logins/failures, device added, beneficiary added, password reset, phone change, with timestamps |
| `find_related_cases(transaction_id)` | other cards/customers sharing merchant / ATM / device / beneficiary, with reported-fraud counts |
| `record_decision(transaction_id, decision, comment)` | appends to `decisions.csv` (or a Delta table) with timestamp + analyst |

Unknown ID → `{"error": "Transaction X introuvable."}`. Off-topic → polite refusal without a model call when possible.

**Accept:** unit tests call each tool on 2 known IDs and one unknown ID.

### Task 6 — Copilot loop (Azure OpenAI, function calling) through ONE wrapper

Reuse the prep-kit wrapper `agent/foundry_client.py` from the `dsi-hackathon` repo (cache, budget, token log) and add `tools=` support:
- `tools` + `tool_choice="auto"`, temperature 0–0.2, `max_tokens` 300 for answers, 100 for tool selection.
- **Max 2 tool rounds** per question (then answer with what you have).
- Auto-inject the open transaction ID as context so the model rarely needs an extra lookup.
- Log per call: timestamp, purpose, model, input/output/cached tokens, latency, tools called, question, answer → `token_log/usage.csv` (traceability is a regulatory requirement in the brief).
- Env vars (`.env`, gitignored): `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY` (or Entra), `AZURE_OPENAI_DEPLOYMENT` (small, non-reasoning, e.g. gpt-4o-mini / gpt-4.1-mini), `AZURE_OPENAI_API_VERSION=2024-10-21`, `LLM_TOKEN_BUDGET=50000`.

System prompt (French, keep stable for prompt caching):
```
Tu es le copilote de l'analyste fraude de la Banque. Tu réponds en français,
de façon concise, factuelle et structurée.
Règles :
- N'affirme que ce que les outils t'ont renvoyé. Cite montants, dates et identifiants.
- Si une information manque, dis-le et propose la vérification à faire.
- Ne calcule jamais toi-même un score : utilise celui fourni par le modèle.
- Distingue les faits (données) de ton interprétation.
- Si l'opération semble légitime, explique aussi pourquoi.
- Termine par une recommandation : BLOQUER, ESCALADER ou VALIDER, avec un niveau
  de confiance. La décision finale appartient à l'analyste.
Format : 1) Verdict (niveau + score) 2) Facteurs principaux (max 3, chiffrés vs habitudes)
3) Contexte 4) Éléments rassurants 5) Recommandation + confiance.
```

**Accept:** the 9 jury questions (below) answered with numbers from tools, no invented facts; total tokens per question logged.

Jury questions to test:
1. Pourquoi cette transaction est-elle suspecte ?
2. Montre-moi les 10 transactions les plus risquées d'hier.
3. Cette transaction ressemble-t-elle au comportement habituel du client ?
4. Résume pourquoi cette alerte doit être priorisée.
5. Que s'est-il passé dans l'application juste avant ce virement ?
6. D'autres clients sont-ils passés par le même commerçant ou le même DAB ?
7. Pourquoi cette alerte n'est-elle pas une fraude ?
8. Rédige le résumé d'investigation pour le dossier.
9. Combien d'alertes inutiles évites-tu par rapport au moteur de règles actuel ? (answer from `gold_model_metrics`, no LLM math)

### Task 7 — Streamlit app (`app/streamlit_app.py`)

Screens (sidebar navigation):
1. **File d'alertes:** table sorted by score, filters (date, channel, risk level), colour by risk, count of today's alerts.
2. **Fiche transaction:** detail, score, 3 factors observed vs usual, buttons BLOQUER / ESCALADER / VALIDER + comment → `record_decision`. Everything visible without scrolling.
3. **Vue client 360:** profile, habits, timeline of transactions + digital events, `st.map` with the alerted point highlighted.
4. **Copilote:** `st.chat_message` / `st.chat_input`, suggested-question buttons, open transaction passed as context, show tokens used per answer.
5. **Journal des décisions** + small KPI panel: alerts vs legacy, frauds caught (validation), tokens used.

Rules: precompute everything in Fabric; `@st.cache_data` for loads; never train in the app; if the LLM fails or budget is reached, show the rule-based factors from `gold_alert_explanations` instead of an error.

**Accept:** demo path alert → fiche → question → decision in < 30 s; works with LLM disabled.

### Task 8 — Repo, docs, pitch

- Repo layout: `notebooks/` (exported from Fabric), `app/`, `copilot/` (wrapper + tools), `tests/`, `docs/` (architecture, decisions, pitch), `requirements.txt`, `.env.example`, `README.md` (how to run), `.gitignore` (`.env`, `token_log/`, `*.parquet`, data).
- Connect the Fabric workspace to the repo (Workspace settings → Git integration) so notebooks are versioned.
- `docs/decisions.md`: model choice, alert threshold = analyst capacity (1 %), Streamlit, no gender feature, sampling for training, small LLM. Status PROPOSED until the team accepts.
- Collect **GitHub Copilot usage evidence as you go** (screenshots, what it generated, time saved) — required in the pitch.
- 3 frozen demo cases + backup video. Pitch 5 min: problem in numbers → live demo (fraud, then avoided false positive) → under the hood (Fabric, model, validation vs legacy) → Copilot usage → limits & next steps.

---

## 3. Feature list already implemented in notebook 01 (keep names stable — app & tools rely on them)

`f_amount, f_amount_ratio, f_amount_z, f_amount_over_max, f_amount_over_income, f_amount_over_limit, f_n_before, f_avg_amt_before, f_std_amt_before, f_max_amt_before, f_night_share_before, f_secs_since_prev, f_hour, f_is_night, f_unusual_night, f_dow, f_payday, f_ramadan, f_key_tx_10m, f_key_tx_1h, f_key_declines_1h, f_key_small_tx_1h, f_cust_tx_24h, f_cust_amt_24h, f_new_merchant, f_new_device, f_new_beneficiary, f_new_ip_country, f_new_city_phys, f_new_country_phys, f_is_foreign, f_ip_foreign, f_same_country_7d, f_dist_prev_km, f_speed_kmh, f_declined, f_magstripe, f_contactless, f_ecom_no3ds, f_chip_abroad, f_contactless_near_limit, f_card_not_intl_abroad, f_age, f_income, f_balance, f_tenure_days, f_intl_card, f_digital_user, f_login_fail_24h, f_device_added_24h, f_benef_added_24h, f_pwd_reset_24h, f_phone_change_24h, f_branch_events_24h, f_mins_since_benef_added, f_merchant_frauds_30d, f_device_frauds_30d`

`key` = `card_id` if present else `customer_id`. Home country is detected as the most frequent `country` value.

---

## 4. Known risks

- Copilot + app = 40 % of the grade and not started → start Task 5–7 in parallel with Tasks 1–3 (use `score_rules` until the model is ready).
- Bigger data than the brief → watch capacity; sample during development.
- Rule points are hand-picked: present them as a transparent baseline, not as the final model.
- Do not claim things not built (RAG / vector DB, voice, autonomous agents).
