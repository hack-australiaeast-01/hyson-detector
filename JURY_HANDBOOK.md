# Jury handbook: technologies, facts and answers

Everything needed to present the solution and answer the jury's questions, organised by the sections and criteria of the brief. The figures are measured on our data; the brief's §§ are given in brackets.

---

## 0. The 30-second pitch

> The bank's current rules engine catches **11.5 %** of frauds and **96.5 %** of its alerts are false (measured on June–July 2026).
> Our copilot, built on **Microsoft Fabric** with a **LightGBM** model and an **Azure OpenAI** assistant, catches **70.9 %** of frauds with **half as many alerts** (1,779 vs 3,338) and **67 % fewer false alerts** (1,061 vs 3,221).
> For each alert it explains why, with figures compared to the customer's habits, answers the analyst's questions, and recommends **BLOQUER / ESCALADER / VALIDER**. The analyst always makes the final decision.

---

## 1. Technologies used (stack)

| Layer | Technology | Role | Brief status |
|---|---|---|---|
| Data platform | **Microsoft Fabric**: workspace `ws-hack-fraud-australiaeast`, Lakehouse `lh_fraud` | Storage (Delta), bronze → silver → gold | Expected |
| Ingestion | Fabric **Copy job** `cj_bronze_load` + connection `saitaflex_connection` | One-shot copy of the Azure SQL source into the lakehouse (no code, cheap on capacity) | — |
| Transformation | Fabric **Notebooks** (PySpark) `01_silver_features` | Cleaning, joins, 73 past-only features (Spark windows) | Expected |
| Scoring | Fabric Notebook `02_score_explain` (pandas, scikit-learn, **LightGBM**) | Rules + 4 models, temporal validation, Gold tables | Free choice |
| Explainability | **SHAP** contributions from LightGBM (`pred_contrib`) + business rules | 3–5 quantified factors per alert | Gold level |
| Tracking | Fabric **MLflow** (autolog disabled to save capacity) | — | Optional |
| Management dashboard | **Power BI** on Fabric (Direct Lake, `pbi_*` tables, report generated as code) | KPIs for managers, embedded in the app | Complement |
| Analyst interface | **Streamlit** (`app/app.py`), FR/EN | Queue, transaction card, customer 360, performance, journal, Power BI | Recommended |
| App ↔ Fabric connection | **SQL analytics endpoint** of `lh_fraud` via `pyodbc` + ODBC Driver 17, **Microsoft Entra** token (`azure-identity`) | Live reads (option A §11); parquet snapshot as fallback (option B) | Recommended |
| Feedback loop | **OneLake** (`azure-storage-file-datalake`) → `Files/feedback/analyst_decisions/decisions.csv` | Analyst decisions written back to Fabric | Gold level |
| Generative AI | **Azure OpenAI**: resource `aoai-fraud-australiaeast-vnxcy`, deployment **gpt-5-mini** (GlobalStandard), API `2024-12-01-preview` | Explanations + dialogue, **function calling** over 9 tools | Recommended |
| Development | **GitHub + GitHub Copilot** (VS Code chat/agent, Fabric Copilot in the notebooks) | Code, notebooks, tests, docs | Expected |
| Languages | Python 3.13, PySpark, T-SQL, DAX | — | — |

---

## 2. Business relevance (20 %): problem and value

**Problem (§2):** static rules, too many false positives, poor explanations, slow cycle.

**What we measured on the current engine (valid June–July 2026, 177,953 transactions, 1,013 frauds):**
- 3,338 alerts → **117 frauds** caught (precision **3.5 %**, recall **11.5 %**), **3,221 false alerts**.
- The brief quotes ~15 % precision / ~42 % recall; that was measured on its own training period. We use our own measurement, on our period.

**Value delivered:**

| | Alerts | Frauds caught | Recall | Precision | False alerts |
|---|---|---|---|---|---|
| Current engine | 3,338 | 117 | 11.5 % | 3.5 % | 3,221 |
| Model, **same volume** as the engine | 3,338 | **787** | 77.7 % | 23.6 % | 2,551 |
| **Model, top 1 % (analyst capacity)** | **1,779** | **718** | **70.9 %** | **40.4 %** | **1,061** |
| Model, top 0.5 % | ~890 | ~590 | 58.2 % | 66.4 % | ~300 |

- **≈ 6× more frauds** caught (718 vs 117) with **47 % fewer alerts** and **2,160 fewer false alerts**.
- Analyst capacity: the brief's ~1,000 alerts over two months is 1 % of its 101,730 test transactions, so we keep the **1 % rule** (1,876 alerts on our 187,628). If the team really caps at ~1,000, use the top 0.5 % (≈ 900 alerts, 58 % recall, 66 % precision).
- Customer trust: the false positive avoided in the demo (TX01575959, a retired customer, 3,361 TND chip purchase in Tunis) would not be blocked.

**Strategic fit (McKinsey "AI bank of the future"):**
- engagement = analyst copilot;
- AI-powered decisioning = fraud pattern detector + summarizer;
- data & tech = governed Fabric, an LLM gateway (one client, budget, cache, log), FinOps on tokens.

**Out of scope (no data for it):** AML flows (structuring, circular flows), first-party / internal fraud.

### 2.1 Real-world benchmarks and bank KPIs (page "Marché & benchmarks", `app/market.py`)

External public figures are allowed if cited (§16 rule 1). Each one is shown in the app with its link.

| Real KPI (source) | Value | Ours (synthetic data, measured) |
|---|---|---|
| False alerts from rule-based monitoring (PwC / McKinsey, industry estimate) | 90–95 % | current rules **96.5 %** · our model **59.6 %** |
| Card fraud rate by value, EEA H1 2023 (EBA/ECB 2024 report) | 0.031 % | 0.28 % — deliberately higher: synthetic data (brief FAQ). Compare shapes, not amounts |
| Cross-border share: fraud value vs payment value (EBA/ECB 2024) | 28 % vs 4 % | 15.0 % vs 1.2 % — same pattern |
| Attempted unauthorised fraud stopped by UK banks (UK Finance 2025 / 2026) | 67p → 70p per £1 | fraud value stopped: model **67.7 %** vs rules **22.1 %** (different scope) |
| EU payment fraud 2024 (EBA/ECB Dec 2025) | €4.2 bn (cards €1.33 bn, +29 %) | — |
| Tunisia 2024 (BCT) | 163 m card operations, TND 27.8 bn, 5.49 m cards, 39,100 POS, 3,305 ATMs | Scenario: × EU rate → ~TND 8.6 m exposure/yr; ~TND 3.9 m more fraud stopped/yr; ~2 m fewer false alerts/yr (editable, labelled "scenario") |

**Bank KPIs from our data (live Fabric query, 1.72 m labelled transactions):**
- ATMs: 10 % of value, **25 % of fraud**; online banking (WEB): 7.5 % of value, **17.5 % of fraud**.
- Magstripe (0.81 %) and contactless (0.74 %) are ~3× riskier than chip (0.26 %); online **without 3-D Secure: 1.8× more fraud** than with it (EBA/ECB says the same about strong authentication).

**Audit of the current rules engine** (analyst verdicts on 32,065 legacy alerts):

| Rule | Alerts | Confirmed frauds | Precision | Frauds it alone caught |
|---|---|---|---|---|
| R04 > 5 transactions in 1 h | 2,584 | 0 | 0.0 % | 0 |
| R01 amount > 3,000 TND | 10,726 | 4 | 0.04 % | 2 |
| R05 transfer > 4,000 TND | 4,179 | 2 | 0.05 % | 0 |
| R03 night, amount > 300 TND | 8,403 | 34 | 0.4 % | 32 |
| R02 foreign country | 10,967 | 1,206 | 11.0 % | 1,204 |

→ **Switch off R04, R01, R05 tomorrow: ≈ 17,483 fewer false alerts for 2 frauds caught by them alone.** R02 does almost all the legacy work; it stays as a complement (it is also the only type where the legacy engine beats the model: cloned card abroad).

**Time to detect** (`fraud_reported_date`, used as a KPI, never as a model feature): median **11 days** between the fraudulent transaction and its report; only **32.8 %** reported within 7 days; **TND 693,791** of fraud reported after a week. Our model alerts at transaction time (day 0).

---

## 3. Data (§5)

| Item | Value |
|---|---|
| Customers | **3,500** (brief: 2,500), 18 cities |
| Transactions | **1,908,228** (train 1,720,600 + test 187,628), 2025-01-01 → 2026-09-30 |
| Digital events | 781,565 |
| Overall fraud rate | ~0.55 % (heavily imbalanced) |
| Tables in `lh_fraud` | customers, cards, merchants, transactions_train/test, fraud_labels_train, legacy_rule_alerts_train, digital_events, views v_transactions_all / v_transactions_train_labeled |

**Time split (§5.4, §8.3, never random):**

| Period | Dates | Rows | Frauds |
|---|---|---|---|
| train | 2025-01-01 → 2026-05-31 | 1,542,647 | 8,494 (0.551 %) |
| valid | 2026-06-01 → 2026-07-31 | 177,953 | 1,013 (0.569 %) |
| test ("today's queue") | 2026-08-01 → 2026-09-30 | 187,628 | unknown (no labels) |

- The validation start is computed from the data: the first day of the month before the last training month.
- Labels are set to NULL on test, and a check confirms 0 labels remain there.

**Fraud types in valid:** contactless stolen card 406 · discreet online 264 · ATM skimming 182 · account takeover 61 · card testing 54 · cloned card abroad 46.

**Pitfall we fixed:** the "234 test frauds" from the first run were a **bug** (the period was computed from the month without the year), not a data leak. It was fixed in notebook 01.

---

## 4. Detection quality (20 %)

### 4.1 Features: 73, **past only** (§7)

| Family | Examples | Technique |
|---|---|---|
| Amount vs habits | `f_amount_ratio`, `f_amount_z`, `f_amount_over_max`, `/income`, `/card limit` | `rowsBetween(unboundedPreceding, -1)` window per customer |
| Velocity | transactions / declines / micro-amounts on the card in 10 min, 1 h, 24 h; contactless and new merchants in 24 h | `rangeBetween(-secs, -1)` |
| Novelty | new merchant, category, device, beneficiary, IP country, city, physical country | first appearance in the past |
| Geography | distance and **implied speed** since the previous located transaction (impossible travel) | haversine |
| Channel / security | magstripe, contactless near the ceiling, e-com without 3DS, domestic card used abroad, chip abroad | — |
| Digital banking | failed logins, device added, beneficiary added, password reset, phone change (24 h), minutes since each event, sequence patterns | join with `digital_events` before the transaction |
| Graph | frauds / defrauded customers / defrauded cards on the same merchant or device in 30 days | **only frauds with `fraud_reported_date` < transaction date** (the brief's §7.1 tip) |
| Profile & calendar | age, income, tenure, KYC, payday, Ramadan 2025/2026, night | — |

**Never used as features:** `is_fraud`, `fraud_scenario`, `fraud_reported_date` (except for the graph features above), the legacy decision, IDs as numbers, **gender** (fairness).

**Leak found and removed:** `f_merchant_risk`, `f_device_risk` and `f_beneficiary_risk` were target encodings over all labels. Each row saw its own label and future labels. They are excluded in notebook 02.

### 4.2 Models (§8)
- **Rules baseline:** 19 explainable rules, including 3 reassuring rules with negative points. PR-AUC on valid: 0.014.
- **Challengers:** HistGradientBoosting, **LightGBM**, **LambdaRank** (one ranking query per day = the analyst's queue), and a rank blend.
- **Class imbalance:** all frauds plus 10 % of legitimate transactions, with weight 10 to restore the true ratio (capped at 50). This also keeps memory manageable on 1.9 M rows.
- **Validation:** train on Jan 2025–May 2026, measure on Jun–Jul 2026, then refit on train + valid to score Aug–Sep.

**Leaderboard (valid):**

| Model | PR-AUC | Top-1 % precision | Top-1 % recall |
|---|---|---|---|
| **LightGBM (champion)** | 0.646 | 0.404 | 0.709 |
| Blend | 0.654 | 0.403 | 0.708 |
| HGB | 0.640 | 0.399 | 0.701 |
| LambdaRank | 0.647 | 0.399 | 0.700 |
| Rules alone | 0.014 | 0.028 | 0.049 |

**Why LightGBM rather than the blend:** the blend wins by less than one point, which is noise. LightGBM is the same model that produces the SHAP explanations, so **the score and its explanation come from one model**.

### 4.3 Metrics (§8.4)
- PR-AUC 0.646 (main metric; accuracy is meaningless at 0.55 % fraud).
- Precision / recall at the top 1 %: 40.4 % / 70.9 %. At the top 0.5 %: 66.4 % / 58.2 %.
- Same alert volume as the engine: 23.6 % / 77.7 %.

**Recall by fraud type (top 1 %):**

| Type | Model | Engine |
|---|---|---|
| Account takeover | **89 %** | 10 % |
| ATM skimming | 74 % | 18 % |
| Discreet online | 68 % | 13 % |
| Contactless stolen card | 68 % | 0 % |
| Card testing | 61 % | 0 % |
| Cloned card abroad | 91 % | **100 %** → we keep this legacy rule alongside the model (hybrid approach, §8.2) |

**Top drivers (LightGBM gain):** implied speed, amount, merchant category, channel, time since the previous transaction, new merchant, transaction type, entry mode, history length, contactless count in 24 h.

### 4.4 Test outputs
- Submission file `Files/exports/submission/submission_csv` (transaction_id, fraud_score, is_alert), one row per test transaction.
- Alerts: valid 1,779 (533 ELEVE / 1,246 MOYEN), test 1,876 (562 ELEVE / 1,314 MOYEN).

### 4.5 Robustness and governance (notebook `04_robustness`, Fabric)
- **Rolling backtest** (same features, sampling and settings as production; re-trained 4 times on the past only; 2-month tests Dec–Jan, Feb–Mar, Apr–May, Jun–Jul): top-1 % recall **69.4 % ± 2.1 pts** (worst 66.7 %), precision 39.1 % ± 3.9, PR-AUC 0.622 ± 0.036, fraud value caught 72.5 %. Current rules on the same periods: 12.6 % recall / 3.7 % precision.
- **95 % intervals** (bootstrap of whole days, 1,000 resamples, Jun–Jul): recall 70.9 % [68.3–73.0], precision 40.4 % [34.9–45.0], PR-AUC 0.646 [0.610–0.675], recall gain vs rules +59.3 pts [56.2–62.0], false alerts avoided 2,160 [1,971–2,335].
- **MLflow**: experiment `hyson-fraud-robustness`, registered ML model `hyson-fraud-lightgbm` v1 (feature list + model card); it reproduces the production scores exactly (rank correlation 1.0, same top 1 %).
- **Orchestration**: data pipeline `pl_hyson_retrain` (01 → 02 → 03e ∥ 04), deliberately not scheduled; library versions pinned in `fabric/environment.yml`.
- **Copilot evaluation**: `app/eval_copilot.py`, 18 golden questions (§9.7 word for word + unknown ID, off-topic, prompt injection), 18/18 pass, 99.5 % of the numbers cited found in the tool outputs (`docs/COPILOT_EVAL.md`).

---

## 5. Explanation and copilot (25 %)

### 5.1 Principle (§9.1)
**The model scores, the copilot explains, and the analyst decides.** The LLM never computes a score and never receives raw rows, only compact JSON facts returned by the tools.

### 5.2 The 10 tools (§9.2, `app/tools.py`)

| Tool | What it returns |
|---|---|
| `get_alert_queue` | Riskiest transactions in a period or on a day, with score and factors |
| `get_transaction` | Transaction details, score, percentile, factors for and against fraud, rules fired, legacy-engine alert or not |
| `get_customer_profile` | Profile and habits (average amount, p95, countries, cities, channels, night share, devices, beneficiaries), optionally **before** a given transaction |
| `compare_to_habits` | Deviations from the past only: ratio to the average, percentile of the amount, country / city / merchant / device / beneficiary already seen (and seen more than 24 h ago), time of day, previous transaction, 24 h activity, card bursts, distance and implied speed |
| `get_customer_history` | Recent transactions and digital events |
| `get_digital_events` | Logins, failed logins, devices, beneficiaries, password, phone number around a transaction (at least 24 h before) |
| `find_related_cases` | Other customers / cards on the same merchant, device or beneficiary across **the whole bank**, counting only frauds **already reported** at the transaction date |
| `get_kpis` | Model vs engine, alerts avoided (comparison pre-written in plain words), recall by fraud type |
| `find_customers` | Person search on approved filters (city, segment, occupation, age, KYC, digital, with alerts): counts + short profiles, never raw rows |
| `record_decision` | Saves the analyst's decision (only on explicit request) |

### 5.3 How a question is processed (`app/copilot.py`)
1. **Intent detection** (kpi, queue, summary, related, before, habits, analysis), in French or English.
2. **Prefetch:** the needed facts are fetched in Python first, so most answers need a single LLM round.
3. **Documented decision rule** (`tools.recommend`), computed in Python. The LLM restates it and explains it with facts:
   - percentile ≥ 0.998 and ≥ 2 concordant signals → **BLOQUER** (high confidence). Measured precision on valid: **94.1 %** (357 alerts).
   - ELEVE and ≥ 2 signals → **BLOQUER** (medium confidence). ELEVE band: **86.7 %** (533 alerts).
   - ELEVE otherwise, or MOYEN → **ESCALADER**. MOYEN band: **20.5 %** (1,246 alerts).
   - FAIBLE → **VALIDER**.
4. **System prompt (§9.3):**
   - only state what the facts say;
   - quote amounts, dates and IDs;
   - never compute a score;
   - separate facts from interpretation;
   - explain why it is legitimate when that is the case;
   - stay on topic, refuse prompt injection.
5. **5-part format (§9.4):** Verdict · Main factors · Context · Reassuring elements · Recommendation (at most 170 words). Separate formats are used for summaries, queues and KPIs.
6. **Streaming:** each tool step and the answer appear live in the interface.

### 5.4 Guardrails (§9.8)
- **Low temperature:** gpt-5-mini is a reasoning model and doesn't accept `temperature`. We use `reasoning_effort=low` and `max_completion_tokens` capped at 2,400. With a non-reasoning model the code switches to temperature 0.1 and `max_tokens` 600.
- **Unknown cases:** a non-existent ID gets "introuvable" plus a suggested check. Off-topic questions get a one-sentence refusal.
- **Traceability:** every call is logged in `data/copilot_log.jsonl` (question, language, intent, tools, tokens incl. cached, latency, answer) and shown on the Journal page.
- **Human decision:** the copilot recommends, the analyst clicks.
- **No secrets in Git:** the key lives only in a git-ignored `app/.env`; Fabric access uses the analyst's Entra login.
- **Offline mode:** a deterministic copilot built on the same tools takes over if Azure OpenAI is unavailable (`COPILOT_OFFLINE=1` forces it).

### 5.5 Costs and performance (token efficiency)
- About 5,000–6,500 tokens per uncached question, of which a large share is **prompt cache** (static prefix). Example: 6,428 tokens, 5,760 of them cached.
- 7–15 s live. Instant for the 20 demo answers pre-computed by `python warmup.py` (disk cache).
- Possible improvement: a non-reasoning mini deployment (gpt-4.1-mini) would be cheaper and faster.

### 5.6 Answers to the jury's questions (§9.7)

| Question | What the copilot does / key answer |
|---|---|
| "Pourquoi cette transaction est-elle suspecte ?" (TX01555470) | ELEVE, score 0.9993 (rank 1). 3 failed logins from an Italian IP (19:40, 20:50, 21:56), beneficiary BEN896882 added at 23:33 by OTP, 814.317 TND transfer at 04:49 = 4.3× the usual average (189.305 TND). 3 transfers that night (00:54, 03:30, 04:49 = 1,810 TND). → **BLOQUER** |
| "Quels sont les principaux facteurs de risque ?" | Top 3 SHAP / rule factors, each with a figure and compared to the customer's habits |
| "Montre-moi les 10 transactions les plus risquées d'hier" | `get_alert_queue` → numbered list (ID · date · amount · channel · country · level · factors) |
| "Ressemble-t-elle au comportement habituel ?" | `compare_to_habits`: ratio, p95, known country / city / merchant / device / beneficiary, time of day vs night share |
| "Résume pourquoi prioriser cette alerte" | Investigation summary: facts, timestamped chronology, conclusion |
| "Que s'est-il passé dans l'application juste avant ce virement ?" | `get_digital_events`: failed logins, new device, beneficiary added, IP country, authentication method |
| "D'autres clients par le même commerçant / DAB ?" | `find_related_cases`, bank-wide. E.g. TX01585580: merchant M01399 = 122 other customers, 1 fraud already reported, 1 related alert |
| "Pourquoi cette alerte n'est-elle **pas** une fraude ?" (TX01575959) | FAIBLE, model's bottom 0.01 %. Chip payment in a physical shop in Tunis at 09:55, a city and country already used (936 past transactions, all in TN), no burst or decline. The amount (20× the average) is a point of attention, not proof. The engine had raised an alert → **VALIDER** |
| "Rédige le résumé d'investigation" | One case-file paragraph (160 words max) |
| "Combien d'alertes inutiles évites-tu ?" | 1,061 false alerts vs 3,221 → **2,160 avoided** (−67 %), 601 more frauds caught, 1,559 fewer alerts |

**"0 frauds already reported on this device / beneficiary" — why not 3?**
- The 3 frauds on BEN896882 / DEV872235 were reported on 10, 13 and 26 June, **after** the 5 June transaction.
- Counting them would use future information (§7, §8.6).
- The correct reading is that the device and beneficiary are **brand new** (first use that same night). That is a risk signal, not reassurance.

---

## 6. Experience and demo (15 %)

### 6.1 Interface (`app/app.py`, FR/EN)

| Page | Content (§10) |
|---|---|
| Alert queue | Filters (period, dates, channel, risk level, fraud type on valid), risk colours, alerts per day, click to open |
| Transaction & copilot | Score, percentile, risk factors and reassuring factors (observed vs usual), BLOQUER / ESCALADER / VALIDER + confidence + comment, chat with suggested questions, live tool steps |
| Customer 360 | Profile, habits, timeline of transactions + digital events, **map** with the alert highlighted |
| Performance | Model vs engine, recall by fraud type, top drivers, leaderboard |
| Journal & traceability | Audit trail: who decided, system recommendation at that time, model / prompt version, hash-chain integrity check, override rate, decision message to the bank's systems (simulated); copilot log (intent, tools, tokens, cache, latency) |
| Power BI dashboard | Manager report embedded securely (organisation login, no "publish to web") |

Sidebar:
- 3 demo buttons;
- data source (🟢 Fabric live / 🟡 local);
- copilot mode and token counter;
- **Nazar** floating eye (bottom right of every page): the work agent — "mes tâches", "suivante", "top 10 d'hier", "bloque TX…" (prepared, confirmed by the analyst), plus a conversation mode ("c'est quoi un faux positif ?") on aggregates only; every message logged;
- "Rafraîchir depuis Fabric" button.

### 6.2 Demo cases (§10: frozen, chosen automatically in notebook 02)

| Case | ID | Story | Recommendation |
|---|---|---|---|
| Obvious fraud | **TX01555470** | Account takeover: 3 failed logins from IT, new beneficiary, 3 night-time transfers | BLOQUER |
| Subtle fraud | **TX01585580** | 7.685 TND online at 02:03 at a new merchant after 2 micro-purchases (card testing); the engine raised no alert | BLOQUER |
| False positive avoided | **TX01575959** | 3,360.634 TND furniture purchase by chip in Tunis, 09:55; the engine raised an alert, the model scores it in the bottom 0.01 % | VALIDER |

### 6.3 Demo script (§17, 5 min)

| Time | Content |
|---|---|
| 0:00–0:45 | The problem, in figures: the engine catches 11.5 % of frauds, 96.5 % of its alerts are false |
| 0:45–2:00 | TX01555470 → transaction card → "Pourquoi suspecte ?" → BLOQUER |
| 2:00–3:00 | TX01575959 → "Pourquoi pas une fraude ?" → VALIDER; show customer 360 (map, 936 transactions in TN) |
| 3:00–4:00 | Under the hood: Fabric pipeline → Performance page (table vs engine, recall by type) |
| 4:00–4:30 | GitHub Copilot: what it generated, time saved |
| 4:30–5:00 | Limits and next steps (§10 below) |

**Before going on stage:**
```powershell
az login
cd C:\Users\oussa\Desktop\dsi\app
python warmup.py
streamlit run app.py
```
- Check that the sidebar shows **🟢 Fabric live**.
- Have the backup video ready.

---

## 7. Technical coherence (15 %): architecture

Full diagrams: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** (global architecture, AI workflow, Le Procès, page workflow, demo path). PNGs for slides:
[end-to-end](docs/img/01_end_to_end.png) · [Fabric platform](docs/img/02_fabric_platform.png) · [ML pipeline](docs/img/03_ml_pipeline.png) · [MLOps lifecycle](docs/img/04a_mlops_lifecycle.png) · [robustness NB 04](docs/img/04b_robustness_nb04.png) · [Azure AI Foundry](docs/img/05_foundry_openai.png) · [ML vs DL](docs/img/06_ml_vs_dl.png) · AI pipelines: [copilot](docs/img/07a_copilot_pipeline.png), [Le Procès](docs/img/07b_le_proces.png), [Enquête approfondie](docs/img/07c_enquete_approfondie.png), [Reconstitution](docs/img/07d_reconstitution.png), [person search](docs/img/07e_person_search.png), [data onboarding](docs/img/07f_data_onboarding.png), [copilot evaluation](docs/img/07g_copilot_evaluation.png), [Power BI as code](docs/img/07h_powerbi_as_code.png) · [pages](docs/img/08a_app_pages.png) · [demo path](docs/img/08b_demo_path.png) · [deployment & security](docs/img/09_deployment_security.png)

```
Azure SQL (source) ──Copy job──► Fabric Lakehouse lh_fraud (bronze, Delta)
        │  NB 01 (PySpark): silver_transactions → gold_features (73 past-only features)
        │  NB 02 (pandas/LightGBM): rules + 4 models → champion → SHAP → Gold tables + submission
        ▼
Gold: gold_scores · gold_alert_queue · gold_alert_explanations · gold_model_* ── Power BI (Direct Lake, manager view)
        │  SQL analytics endpoint (T-SQL, Entra token)         ▲ OneLake Files/feedback/analyst_decisions
        ▼                                                       │ (feedback loop → future retraining)
Streamlit app ── tools.py (10 tools, JSON) ── copilot.py ── Azure OpenAI gpt-5-mini (function calling)
                                              └─ cache, log, streaming, offline mode
```

**Role of each brick:**
- **Fabric:** data, features, scoring, Gold tables, Power BI, decision storage.
- **Azure OpenAI:** explanation and dialogue only.
- **GitHub Copilot:** speeds up delivery.
- **Streamlit:** the analyst's decision tool.

**Gold tables:**

| Table | Rows | Content |
|---|---|---|
| `gold_scores` | 365,581 | valid + test |
| `gold_alert_queue` | 3,656 | alerts + demo cases, `demo_case` column, test labels set to NULL |
| `gold_alert_explanations` | 20,145 | rules + SHAP for / against |
| `gold_model_metrics` | 17 | |
| `gold_model_leaderboard` | 5 | |
| `gold_model_importance` | 20 | |
| `gold_model_recall_by_type` | 6 | |

**Capacity / FinOps:**
- One-shot copy job.
- Developed on a 300-customer sample before the full run.
- Spark session stopped at the end of every notebook.
- MLflow autolog disabled.
- Tokens capped, cached and logged.

---

## 8. GitHub and GitHub Copilot (§13, §16)

- **Repository:** `README.md`, `app/` (code), `notebooks/` (Fabric exports), `requirements.txt`, `.env.example`, a `.gitignore` excluding `.env`, data and third-party material. Commits `3ae7d57`, `2404a7d`, `7f7e7bf`, and more.
- **Public repo:** https://github.com/hack-australiaeast-01/hyson-detector (the only active copy; the first copy `saitaflex/hyson-detector` is archived and points here). Optional: Fabric Git integration (Workspace settings → Git integration → GitHub, folder `fabric/`).

**How Copilot was used** — full table with 12 real uses, commits and screenshots in [docs/AI_TOOLS_USAGE.md](docs/AI_TOOLS_USAGE.md#1-github-copilot-official-delivery-accelerator):
- **GitHub Copilot agent mode (VS Code)** — the only coding assistant used (details in [docs/AI_TOOLS_USAGE.md](docs/AI_TOOLS_USAGE.md)):
  - built the Streamlit app, the tools, the copilot and the offline mode;
  - wrote the AppTest tests and ran the live tests against Azure OpenAI;
  - found and fixed several bugs: the split bug, the target-encoding leak, a broken blend, an inconsistent KPI (1,780 → 1,779), and a percentile rounded to 3 decimals that gave 183 alerts too much confidence.
- **Fabric Copilot (notebooks):** split fix, added features, rewrote notebook 02, ran the notebooks and summarised the outputs.
- **Time saved:** 30 commits in ≈ 11 h, all co-authored by Copilot; rough team estimate ≈ 7 person-days of work. Three examples for the pitch: the split bug, copilot cost 5,200 → 3,300 tokens per question, public-app memory 856 → 520 MB.

---

## 9. Rules of the game: checklist (§16)

| Rule | Proof |
|---|---|
| No future information | Spark windows `-1`, graph features use only reported frauds, leaky target encoding removed, habits computed `before_transaction_id` |
| Test labels not used | Nulled in silver and in the Gold queue; check = 0 |
| Temporal validation | train < 2026-06-01 ≤ valid < 2026-08-01 ≤ test |
| No secrets in Git | `.env` ignored, Entra login, `git ls-files` checked |
| AI usage declared | §8 above |
| Code and history inspectable | Notebooks exported, commits |

---

## 10. Acknowledged limits and next steps (§17, 4:30–5:00)

**Limits:**
- Batch scoring: alerts are produced after the fact, not at payment authorisation.
- On cloned cards abroad, the model does slightly worse than the legacy rule (91 % vs 100 %), so the rule is kept.
- Discreet online fraud remains the hardest type (68 %).
- No data for AML or internal fraud.
- The engine figure (3.5 % / 11.5 %) differs from the brief's because it is measured on our period.
- The copilot uses a reasoning model (gpt-5-mini): slower and more tokens than a non-reasoning mini model.

**From prototype to production:**
- Real-time scoring at authorisation: Fabric Real-Time Intelligence (Eventstream → KQL database → Activator) or Event Hubs, plus a model endpoint (< 100 ms). This removes the "batch scoring" limit.
- Fabric Data Agent on the Gold tables, so managers ask KPI questions in plain language (complements the Power BI report).
- Document RAG (Azure AI Search) on the bank's procedures and BCT circulars once the bank provides them, so the copilot cites the right procedure for each fraud type. Today there are no such documents in the brief, so we don't invent them.
- Model challengers, validated with the same 4-period backtest before any switch: a sequence model on the card's recent history, an autoencoder for unseen fraud patterns. A graph neural network only if a graph signal is proven first (exposure to compromised ATMs / merchants was not predictive: 41 % vs 40 % precision).
- Case-management integration (card blocking).
- Azure OpenAI on a private endpoint with managed identity.
- RBAC and PII masking.
- Model governance: independent validation, drift monitoring, fairness checks, scheduled retraining fed by `decisions.csv`.
- Audit logs retained.

---

## 11. Likely jury questions (beyond §9.7)

| Question | Answer |
|---|---|
| Why not a random split? | It would mix the same fraud episode between train and validation and overstate performance (§8.3) |
| Why PR-AUC and not accuracy? | At 0.55 % fraud, a model that never flags anything already has 99.4 % accuracy |
| How do you know there's no leak? | Past-only windows, labels excluded, `LEAKY` assert, test check = 0, graph features use only reported frauds; we found and removed a leak ourselves (target encoding) |
| Why 1 %? | The brief's ~1,000 alerts / 2 months = 1 % of its 101,730 test rows; same 1 % on our 187,628 rows = 1,876. At ~1,000 strict capacity: top 0.5 % (≈ 900 alerts, 58 % recall, 66 % precision) |
| "Everyone in your table looks suspicious, all at 100 %" | The queue only shows the top 1 % (1,876 of 187,628 operations: 99 % never reach an analyst). An alert is "to check", not "fraud": the **Fraudes mesurées** column gives the share of real frauds measured in validation for that score (0.70 ≈ 12 %, 0.97 ≈ 88 %, ≥ 0.99 = 100 %); the score is a ranking, not a probability. Expected ≈ 649 real frauds among 1,876 alerts: 562 to block (87 % measured), 1,314 to check, mostly legitimate customers to clear fast |
| Why LightGBM? | Best trade-off on tabular data, native categoricals, exact SHAP, ties the blend within a point |
| Why not deep learning or a graph neural network? | On tabular fraud data gradient boosting is the industry reference: explainable with SHAP and stable (69.4 % ± 2.1 over 4 periods). A GNN needs a graph signal and ours says no: exposure to compromised ATMs / merchants did not predict fraud (41 % vs 40 % precision), so it is shown as an investigation lead, not scored. Sequence models and autoencoders are roadmap challengers, to adopt only if they beat the champion on the same backtest. |
| Do you use RAG? | Yes, on facts rather than documents: the copilot can only cite what its read-only tools returned from Fabric (transaction, habits, history, related cases), and the deep search retrieves the 25 most similar labelled alerts. 99.5 % of cited numbers are checked against the facts. Document RAG (Azure AI Search) comes when the bank gives us its procedures. |
| Why not a bigger model? | A fraud decision must be reproducible and auditable: the measured model scores, a documented rule recommends, the LLM only phrases what the tools retrieved, the analyst decides. A bigger LLM would add cost and latency, not detection. |
| "Maybe June–July was a lucky period" / "you picked the model on the period you report" | Rolling backtest on 4 periods, re-trained on the past only each time: top-1 % recall 69.4 % ± 2.1 (worst 66.7 %); 95 % interval on Jun–Jul 70.9 % [68.3–73.0]. The 4 candidate models were within ~1 pt, and the Aug–Sep labels stay with the jury |
| Is the model industrialised or just a notebook? | Registered in MLflow (`hyson-fraud-lightgbm`, identical to production scores), Fabric pipeline `pl_hyson_retrain` for retraining, pinned environment, drift (PSI) on the Impact page, decisions fed back to OneLake |
| Is the model fair? | Gender is never used. Alert rate 0.9–1.1 % in every segment / age band; retirees and 60+ have less fraud and lower precision (30–35 %) and recall (61–66 %): shown on the Performance page and in `docs/MODEL_CARD.md`, to monitor in production |
| Is the code tested? | 139 automated tests (`tests/`, pytest, ~30 s, offline) run by GitHub Actions on every push: no test labels, KPIs, decision rule, calibration, past-only habits, guardrails, every page FR/EN |
| How do you know the copilot doesn't invent numbers? | `eval_copilot.py`: 18 golden questions (incl. the brief's §9.7 wording), 99.5 % of the numbers cited are found in the tool outputs; unknown IDs answered "introuvable" with 0 tokens; prompt injections stopped by the Azure OpenAI filter + a clear refusal |
| "Your model calls a 3,360 TND purchase above the card limit reassuring?!" | No. SHAP says the model weighed those factors *down* for this operation (large chip purchases at known shops are rarely fraud in the data), but we never show them as reassuring: they appear as "non déterminants pour le modèle". The reassurances shown are business facts computed from the customer's past (chip, known merchant, usual city and country, plausible travel). 181 of 3,656 alerts had such a factor; a test guards it (`tests/test_explanations.py`). |
| "Does it look like the customer's habits?" — who decides yes / no? | Code, not the LLM: `compare_to_habits` lists the clear deviations (amount > p95, rare night hour, device or beneficiary known < 24 h, new country or merchant, impossible travel, magstripe, declines) and the consistent facts; 2+ deviations → **Non**, 1 → **En partie**, 0 → **Oui**. The LLM only phrases it. |
| Why does the LLM not decide? | Not reproducible and a hallucination risk: the decision follows a documented rule backed by measured precision, and the analyst decides |
| How do you avoid hallucinations? | Facts come only from tools, the rule is fixed, IDs are never invented, missing information is stated, temperature is low / reasoning effort is low |
| How much does one question cost? | ~3,300 tokens (≈ 1,400 served by the Azure prompt cache), 1 LLM round, 7–15 s; demo answers cached; every call logged; public demo capped at 60 live calls / hour |
| What if Azure OpenAI or Fabric goes down? | Deterministic offline copilot + local parquet snapshot: the demo keeps working |
| Fairness? | `gender` is never used; age / income are kept as profile features (a choice to document) |
| What does the analyst's decision feed into? | `decisions.csv` → OneLake → new labels for the next retraining |
| Why Streamlit rather than Power BI? | The brief requires interaction + copilot + decision (§4, FAQ); Power BI is the management complement, embedded in the app |
| How does this compare to real banks? | Page "Marché & benchmarks": rule engines are at 90–95 % false alerts (industry estimate), ours measures 96.5 %, our model 59.6 %; the cross-border fraud pattern matches the EBA/ECB report. Sources are linked on screen |
| Your fraud rate (0.28 %) is far above the EU's 0.031 %. Isn't that unrealistic? | Yes, by design: the hackathon data is synthetic and fraud-rich (brief FAQ: ~0.65 % vs ~0.1 % in reality). We compare shapes (shares, ratios), and the Tunisian scale-up is a labelled scenario with editable assumptions |
| What can the bank do tomorrow, without AI? | Switch off rules R04, R01 and R05: ≈ 17,483 fewer false alerts for 2 frauds they alone caught; enforce 3-D Secure online (1.8× less fraud) |
| "Be human before being AI: a retired customer who always withdraws his pension at home pays in Saudi Arabia or France — do you call him and make him feel spied on? And if it is a yacht in Italy?" (example given to us by a bank CEO) | Page **Contexte personnel**: the system reads only facts the bank already holds (previous trips, ticket or hotel bought, stay in progress, impossible travel, chip vs stripe, amount vs his own habits and income, travel waves of customers) and **never guesses why he travels** — no religion, family or health: that is sensitive data (law 2004-63, GDPR art. 9). Yacht in Italy 5 h after a payment in Tunisia, 27× his p95 → "Peu cohérent" (block, then call without saying where we think he is). First stay in Saudi Arabia, small chip payments → "À confirmer": a polite one-line check and an invitation to declare trips; once he declares one → "Voyage cohérent", a "bon séjour" notification, no call. Measured on 4,138 payments abroad in 2026: ROC-AUC 0.858, the "coherent" band (1.1% fraud) holds 1,559 of the 3,802 false alerts the current rules raise abroad. |
| Is this legal? Profiling, AI Act, data protection? | Fraud detection is a legitimate interest of the bank and not a "high-risk" use in the EU AI Act (Annex III excludes AI used to detect financial fraud); the decision stays human (GDPR art. 22). Data minimisation: the AI assistant returns customer data only as aggregates (no identifiers, no row per customer, groups < 5 customers suppressed), every question is logged with the analyst's name, gender is never used, and the context engine never infers sensitive data. In production: authorisation / declaration to the INPDP, Azure OpenAI in a region approved by the bank (here Australia East on synthetic data), Azure AI Speech in the bank's tenant instead of browser voice. |
| Can I ask anything about the data in my own words? | Yes, page **Assistant IA**: the AI writes one SQL query on the star schema, but it never runs unchecked: `sqlglot` parses it (one SELECT, only the 9 star tables, no file / function / external access, row cap), the Fabric SQL endpoint is read-only, and the local engine refuses file access even if the guard were bypassed (both tested). The SQL is shown to the user and logged; the summary is written only from the returned rows. "Combien de transactions à Béja ?" → 39,156, identical to the raw data profile. |
| Is your data clean? | Notebook 05 checks **every row** of the 5 raw tables against 41 rules: 0 rejected, 11,756 warnings (39 extreme amounts, 11,717 card-present operations without a place), each with its rule, value and message in `dq_issues`; rejected rows would go to quarantine and never reach the facts. |
| Why can't the alert copilot query the database freely? | By design: it only calls approved read-only tools with parameters (security: no injection; reliability: it can only state what tools return, §9.1; cost: aggregates, not tables; traceability: every call logged). It still answers about anyone: "le client retraité de Sfax de plus de 70 ans avec des alertes" → approved filters → `find_customers` → short list + riskiest alert, 0 tokens |
| Can it ask about a specific transaction or customer, not the open one? | Yes: an ID typed in the question (TX… or C…) overrides the open transaction; unknown IDs are reported as not found, never invented |
| Who decided, and can the log be changed afterwards? | Every decision stores the analyst, the system recommendation and score **at that moment**, the model and prompt versions, the time to decide, and a SHA-256 chained to the previous row: editing or deleting any past decision is detected ("Intégrité du journal" on the Journal page, `tools.verify_journal`, tested). Production: append-only (WORM) storage + SIEM |
| Do analysts just follow the AI? | The Journal page shows the **override rate** (decision ≠ recommendation) and lists the overrides for the supervisor. Setting aside a recommended BLOQUER, or blocking ≥ 5,000 TND, is flagged for four-eyes approval |
| How does "BLOQUER" reach the card or the transfer? | Each decision produces a `fraud_decision.v1` message mapped to the right system (card → card management BLOCK_CARD, transfer → core banking HOLD_TRANSFER, ESCALADER → level-2 case, VALIDER → close) with the audit reference; shown on the Journal page. In the demo nothing is sent; production = API gateway / Service Bus (`docs/AUDIT_AND_BANK_INTEGRATION.md`) |
| Where does customer data go? Is this "high-risk AI"? | The LLM gets compact tool facts (IDs, amounts, aggregates), no names, no card numbers, never raw tables; Azure OpenAI in the bank's tenant does not train on prompts; production region = the one approved by the bank / regulator; Tunisian personal-data law 2004-63 (INPDP declaration by the bank). The EU AI Act excludes fraud detection from the high-risk credit-scoring category (Annex III 5(b)); we keep human oversight anyway |
| What if the bank adds a new data source? | Page "Nouvelle source de données": profile → proposed mapping with confidence (rules, optional 1 AI call on names + statistics only) → translation of codes, countries, dates, currencies → accuracy (coverage, % valid, reconciliation, drift PSI vs our data) → **human approval** → versioned data contract + log. Nothing enters without a named approval |
| Isn't Nazar just one more chatbot? | It acts first: one instruction → one action (briefing, next most urgent alert, top N of a day, open a page on a case, find a customer, check the journal), parsed by rules (0 token, instant, works offline). It can also talk (concepts, investigation methods, how to use the app) on Azure OpenAI, but that mode only sees aggregates, has no tools, cannot record anything and answers by suggesting the exact command to run. It never decides alone: "bloque TX…" only prepares the decision with the system recommendation and the measured fraud rate, the analyst confirms, and it lands in the same hash-chained journal (source `agent_nazar`). Questions about an alert go to the copilot on that alert, which reads the data. Every message is logged with its tokens (`agent_log.jsonl`, Journal page). |
| Why is there a plain GPT-5 mini "brain"? Isn't that a generic chatbot? | It is optional and off by default, for general questions (explain a concept, draft a message). It is isolated: no bank facts, none of Nazar's earlier answers, no tools, no decision — asked "bloque TX…" or "combien de fraudes ?" it says it has no access and points to the Nazar brain or the transaction page (tested live). Every answer about a case comes from the copilot, grounded in the data. |
| Voice: where does the audio go? | Speech is the browser's own (free). Chrome / Edge recognition and their "online" voices are cloud services of Google / Microsoft, so in production we would use Azure AI Speech in the bank's tenant (same Azure contract as Azure OpenAI) or text only. The demo data is synthetic. |
| A declined transaction is gone — how do you see what happens next? | It is not gone: page **Dossier d'enquête** follows the card and the customer after the alert. TX01631347 (declined in Tripoli): nothing at the alert; at +6 h the case reopens by itself (failed login, card reused, the same card in Tunisia and Libya); at +24 h the Judge moves from ESCALADER to BLOQUER, citing the post-alert evidence, and says it does not prove cloning — the employee decides. The slider only shows what was known at each time. |
| Is your RAG real? Does it help? | 16,302 past cases embedded with Azure OpenAI `text-embedding-3-small` (256 dims) + a behavioural vector, searched by hybrid cosine; only earlier cases, with their status as known then (a fraud reported later is not "confirmed"). We measured it: alone it barely predicts fraud (ROC-AUC 0.57 vs 0.85 for the model) and blending does not help — so it gives precedents and typology to the agents and the employee, never a score. |
| Who is the judge? Can it invent? | An Azure AI Foundry agent (`judge-patern`, project proj-fraud-australiaeast) receives the numbered evidence board and both arguments; it must grade the reliability of each piece of evidence and cite E-numbers; our code checks every citation (non-existent ones are shown and discarded). It never confirms fraud: only the employee after contacting the customer, or the bank's report, can. |
| Can the AI explain *why* fraud concentrates somewhere (cyber, process, infrastructure)? | Page **Intelligence fraude**: drill down, then the AI reads facts K1…Kn computed in SQL and classifies 1–3 patterns. Example DAB · national card: 66 % of affected cards have 3+ cases (customer / coordinated), 23 % via magnetic stripe on chip cards (technical: fallback accepted), rules caught 2 % vs model 85 % (control gap). Without employee or switch logs, administrative and technical causes stay hypotheses with low confidence — the AI says so. |
| Why the evil eye? | "Nazar" is the Mediterranean eye that watches and protects; the agent watches the alert queue for the analyst. The icon is our own drawing (no third-party image). |
| How fast is fraud detected today? | Median 11 days from transaction to report, only 32.8 % within a week; the model alerts at transaction time |
