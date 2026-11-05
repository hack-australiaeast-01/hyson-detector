# Project status — AI Banking Copilot for Fraud Detection
Updated: 2026-11-05 18:15 · ✅ done · 🟡 in progress · ❌ to do · Target level: **Gold ("Or")** (brief §6) · Full work log: §8

## 1. Pipeline & model (frozen: do not rerun notebook 02, or the demo IDs change)
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Fabric workspace `ws-hack-fraud-australiaeast`, lakehouse `lh_fraud`, copy job | ✅ | 1,908,228 transactions, 3,500 customers (larger than the brief) |
| 2 | Time split | ✅ | train 2025-01→2026-05 · valid 2026-06→07 · test 2026-08→09 (no labels) |
| 3 | NB 01: silver + `gold_features` (73 features, past-only) | ✅ | Behaviour, velocity, novelty, geography/speed, channel, digital timing, graph (already-reported frauds only), calendar |
| 4 | Leak checks | ✅ | 0 test labels, 0 duplicates, no label columns; target-encoded `*_risk` features excluded |
| 5 | NB 02: rules + HGB / LightGBM / LambdaRank / blend, champion chosen on valid | ✅ | Champion **LightGBM**: the same model scores and explains (SHAP) |
| 6 | Gold tables + submission CSV (§14) | ✅ | gold_scores, gold_alert_queue, gold_alert_explanations, gold_model_metrics/leaderboard/importance/recall_by_type, Files/submission/submission_csv |
| 7 | App ↔ Fabric | ✅ | **Live** via SQL analytics endpoint (Entra token): Gold tables, full history with lat/long, 781k digital events, related cases across the whole bank; decisions written to OneLake `Files/app_feedback`; parquet fallback |

## 2. Results (validation Jun–Jul 2026, out-of-time, final)
| | Alerts | Frauds caught | Recall | Precision |
|---|---|---|---|---|
| Current rules engine | 3,338 | 116 / 1,013 | 11.5 % | 3.5 % |
| Model, same alert volume | 3,338 | 787 | 77.7 % | 23.6 % |
| **Model, top 1 %** | **1,780** | **718** | **70.9 %** | **40.4 %** |
| Model, top 0.5 % | ~890 | ~590 | 58.2 % | 66.4 % |

- PR-AUC 0.646 (rules 0.014).
- Recall by fraud type, model vs current engine:

  | Fraud type | Model | Current engine |
  |---|---|---|
  | Stolen card, contactless | 68 % | 0 % |
  | Discreet online fraud | 68 % | 13 % |
  | ATM skimming | 74 % | 18 % |
  | Account takeover | 89 % | 10 % |
  | Card testing | 61 % | 0 % |
  | Cloned card abroad | 91 % | 100 % (legacy rule kept as a complement) |

- Pitch line: "Half the alerts, about 6× more frauds caught, about 67 % fewer false alerts (1,062 vs 3,222)."
- Demo cases:
  - TX01555470, obvious fraud: 3 night-time web transfers in 4 h (00:54, 03:30, 04:49), 3 failed logins in the previous 24 h.
  - TX01585580, subtle fraud: 7.69 TND online at 02:03 at a new merchant, after 2 other micro-purchases (card testing).
  - TX01575959, false positive avoided: 3,361 TND chip purchase in Tunis, daytime, retired customer. The current engine raised an alert; the model scores it in the bottom 0.01 %.

## 3. Application & copilot (`app/`)
| # | Item (brief §) | Status | Notes |
|---|---|---|---|
| 8 | Alert queue: filters (period/date/channel/risk/fraud type), risk colours, alerts per day (§10) | ✅ | `app.py` |
| 9 | Transaction view: score, risk and reassuring factors (observed vs usual), decision + confidence + comment, no scrolling (§10) | ✅ | |
| 10 | Customer 360: profile, habits, timeline with digital events, map (§10) | ✅ | Live from Fabric |
| 11 | 9 copilot tools (§9.2): get_alert_queue, get_transaction, get_customer_profile, compare_to_habits, get_customer_history, get_digital_events, find_related_cases, get_kpis, record_decision | ✅ | `tools.py`, compact JSON, unknown IDs handled |
| 12 | Copilot: prompt §9.3, 5-part format §9.4, ≤ 4 tool rounds, cache (§9.8) | ✅ | `copilot.py` · gpt-5-mini: `reasoning_effort=low`, `max_completion_tokens` 2,400 (non-reasoning models: temperature 0.1, max_tokens 600) · offline fallback (demo always works) |
| 13 | Copilot traceability: question, tools, tokens, latency → `data/copilot_log.jsonl` + Journal page (§9.8) | ✅ | |
| 14 | Decision journal + feedback (`data/decisions.csv`) (§10) | ✅ | |
| 15 | KPI page: model vs current engine, recall per type, drivers, leaderboard (§10) | ✅ | |
| 16 | Azure OpenAI: `app/.env` (endpoint, key, deployment) | ✅ | Deployment **gpt-5-mini** answers; `copilot.py` loads `.env` itself |
| 17 | Tested live on the §9.7 questions (6 per demo case + 2 global = 20 answers) | ✅ | Pre-computed with `python warmup.py` (cache). Recommendations: TX01555470 BLOQUER · TX01585580 BLOQUER · TX01575959 VALIDER. Avg **5,224 tokens, 12 s** live, instant from cache |
| 18 | Power BI report on Gold (manager view, complement) | ✅ | Built as code by `notebooks/03b_powerbi_dashboard.ipynb`: 8 `pbi_*` tables → Direct Lake model `sm_fraud_copilot` (24 DAX measures) → report "Fraud Copilot — Dashboard", 4 pages (executive view, alert queue, why?, fraud types). Polish left: theme not applied, raw column headers/decimals in the 2 tables, donut labels. Delete the broken old `03_powerbi_dashboard` notebook in Fabric |
| 19 | GitHub: Fabric Git integration + push of the repo (README, requirements, .env.example, .gitignore ✅) | 🟡 | Local repo ✅ (commits `3ae7d57`, `2404a7d`, no secrets). Still to do: create the GitHub repo + `git push`, then Fabric Git integration (§13, §16.5) |
| 20 | GitHub Copilot usage evidence (screenshots, time saved) | 🟡 | §13, §17 |
| 21 | Slides: problem, demo, architecture, results, prototype → production, limits | ❌ | §17 |
| 22 | Pitch 5 min ×3 rehearsals + backup video | ❌ | §10, §17 |

## 4. Decision log
- Time split, never random; valid = last 2 labelled months (§8.3).
- No gender, IDs, fraud_scenario, fraud_reported_date (except "already reported" graph features) or legacy decisions as features (§8.6).
- Target-encoded entity risk dropped (not point-in-time).
- Train = all frauds + 10 % of legitimate transactions (weight 10); valid/test kept complete.
- Champion = LightGBM when within 1 pt of the best top-1 % recall, so one model both scores and explains.
- Alert budget = 1 % per period (analyst capacity, §8.4).
- The model scores, the LLM explains only from tool JSON, the analyst decides (§9.1). Offline deterministic mode if the LLM is unavailable.
- Streamlit = analyst tool + copilot, reading Fabric **live** (SQL analytics endpoint, option A §11) with a parquet fallback (option B); Power BI = manager KPIs (complement only).
- Out of scope (no data): AML flows, first-party/internal fraud.
- Dataset differs from the brief (3,500 customers, 2025-01→2026-09, 1.9 M tx). The current engine measured on our valid period = 3.5 % precision / 11.5 % recall (the brief's 15 % / 42 % is on its own train period).

## 5. Next actions
1. Before the pitch: `az login` (Fabric access), `python warmup.py`, `streamlit run app.py`; rehearse the 3 demo cases.
2. (Optional) Ask organisers for a non-reasoning mini deployment (gpt-4.1-mini) → fewer tokens and faster live answers.
3. GitHub: create the repo on github.com → `git remote add origin <url>` → `git push -u origin main` (local repo already committed) → Fabric Git integration (folder `fabric/`).
4. Power BI polish (theme, table headers), slides, 3 rehearsals, backup video.

## 7. Review findings (2026-11-05 evening) — status after fixes
- R1 ✅ open transaction pre-injected + tool output capped → 5,224 tokens / 12 s avg (was ~7,500 / 16 s); non-reasoning deployment still recommended.
- R2 ✅ app now reads Fabric live: copilot and transaction page use the same full history (usual amount 189.305 TND everywhere).
- R3 ✅ offline mode leads with reassuring factors when risk is FAIBLE; tiny percentiles shown as « < 0.01 % ».
- R4 ✅ prompt fixes the level vocabulary (FAIBLE / MOYEN / ELEVE).
- R5 ✅ README documents the gpt-5-mini settings.
- R6 ✅ `COPILOT_OFFLINE=1` forces offline mode.
Checked by running the copilot: offline path on 4 cases, plus **one live call**. That call was made by accident, because `copilot.py` loads `.env` at import.

| # | Finding | Impact | Fix |
|---|---|---|---|
| R1 | **5,505 tokens per question** (4,911 prompt + 594 completion), 20 s latency, gpt-5-mini (a reasoning model) | Tokens are judged; 9 jury questions ≈ 50k tokens; 20 s feels slow in a live demo | (a) Ask organisers for a **non-reasoning mini** deployment (gpt-4.1-mini / gpt-4o-mini): fewer tokens and faster. (b) Pre-inject `get_transaction` JSON for the open transaction (saves 1 tool round = one full re-send of the prompt). (c) Shorten tool descriptions / drop unused tools from `TOOL_SCHEMAS` per page. (d) Cap each tool's JSON (top 3 factors, no lists > 5). Target < 2,000 tokens/question. |
| R2 | **Two different "usual amounts"** for TX01555470: 189.305 TND (Gold explanation = full past history) vs 236.433 TND (`compare_to_habits` = exported history since 2026-03-01 only) | A judge comparing the transaction page and the chat sees two numbers → hurts "answers grounded in data" (25 %) | Make `compare_to_habits` read the Gold feature values (`f_avg_amt_before`, etc.) or label it "moyenne depuis mars 2026" |
| R3 | Offline answer for the false positive TX01575959 lists "Montant 20.26× la moyenne" under **Facteurs principaux** while the verdict is FAIBLE, and prints "score 0.0, plus risquée que 0.00 %" | Confusing on the "avoided false positive" demo case | In offline mode, lead with reassuring factors when risk = FAIBLE; format tiny scores as "< 0.01 %" |
| R4 | LLM wrote "RISK ELEVE" (mixed language) | Cosmetic | Add "Niveaux : FAIBLE / MOYEN / ELEVE" to the system prompt |
| R5 | README says "temperature 0.1"; with gpt-5-mini the code uses no temperature and `max_completion_tokens` 2,400 | Jury may read the repo | Update README to say which mode is used |
| R6 | `copilot.py` silently goes live whenever `.env` exists | Accidental paid calls during tests (happened once) | Add `COPILOT_OFFLINE=1` env switch for tests |

Verified OK: unknown ID handled ("TX99999999 introuvable"), KPI answer computed without LLM (2,162 false alerts avoided, 603 more frauds; exact counts from the alert list = 2,160 and 602, as on the dashboard; app rounds from recall), call logged in `data/copilot_log.jsonl` with tools, tokens and latency.

## 6. Fabric cell: complete customer export (run alone at the end of notebook 02, never "Run all")
```python
from pyspark.sql import functions as F
q_cust = spark.table("gold_alert_queue").select("customer_id").distinct()
cols = ["transaction_id", "timestamp", "period", "customer_id", "card_id", "merchant_id", "beneficiary_id", "device_id",
        "session_id", "transaction_type", "channel", "entry_mode", "merchant_category", "amount_tnd", "city", "country",
        "latitude", "longitude", "ip_country", "status", "decline_reason"]
(spark.table("silver_transactions").filter(F.col("timestamp") >= "2026-03-01").join(q_cust, "customer_id").select(*cols)
      .coalesce(1).write.mode("overwrite").parquet("Files/app_export/customer_history"))
(spark.table("digital_events").join(q_cust, "customer_id").filter(F.col("timestamp") >= "2026-03-01")
      .coalesce(1).write.mode("overwrite").parquet("Files/app_export/digital_events"))
```


## 8. Detailed work log (what was done, how, and why)

### 8.1 Data pipeline in Fabric (notebooks 01 and 02)
| Step | What was done | Why / result |
|---|---|---|
| Diagnostic SQL | Date ranges per `split` + frauds per month on the SQL endpoint | Found train = 2025-01→2026-07, test = 2026-08→09 (not the brief's dates) |
| Split bug fixed (NB 01) | `period` was built from `F.month()` only, so it ignored the year: Aug–Sep **2025** train rows were labelled "test" (the "234 test frauds"). Now: keep `split`; `valid` = first day of the month before `max(train)` → 2026-06-01, computed on the full train table; labels nulled on test | Not a data leak, a code bug. Result: train 1,542,647 rows / 8,494 frauds (0.551 %), valid 177,953 / 1,013 (0.569 %), test 187,628 / NULL |
| Session error | `NameError: SAMPLE` came from running one cell after `mssparkutils.session.stop()` | Always "Run all" |
| Features 57 → 68 → 73 | Fabric Copilot added digital timings, sequence flags, graph distinct counts; we added `f_new_category`, `f_key_contactless_24h`, `f_key_new_merchants_24h`, `f_round_amount`, `f_benef_n_customers_before`, Ramadan 2025 | Contactless recall 63 → 68 %, card testing 50 → 61 % |
| Leak found and removed | `f_merchant_risk`, `f_device_risk`, `f_beneficiary_risk` were target-encoded on all train labels (each row saw its own label and future labels) | Excluded in NB 02 (`LEAKY` set); point-in-time version documented but not needed |
| NB 02 rewritten | Memory-safe load (all frauds + 10 % legit, weight 10; valid/test complete) instead of `toPandas()` on 1.9 M rows; inf → NaN; leak assert; MLflow autolog off; `%%configure` attaches `lh_fraud` (fixed "No default context") | Runs in ~10 min without OOM |
| Champion vs challengers | HGB, LightGBM, LambdaRank (one query per day), rank blend; blend bug fixed (rules weight dominated the top) | LightGBM PR-AUC 0.646; champion forced to LightGBM when within 1 pt so **the same model scores and explains** (SHAP via `pred_contrib`) |
| Explanations | Per alert: up to 5 rule factors (observed vs usual), 3 SHAP factors for fraud, 2 against (= reassuring), French labels | Feeds the transaction page and the copilot |
| Gold outputs | `gold_scores` (valid+test only), `gold_alert_queue` (3,656, `demo_case` column), `gold_alert_explanations` (20,145), `gold_model_metrics`, `gold_model_leaderboard`, `gold_model_importance`, `gold_model_recall_by_type`, `Files/submission/submission_csv` | Test labels nulled in Spark before writing (check = 0) |
| Demo cases | Picked from valid by rule: highest-scored fraud, fraud caught with weak rules, legacy alert the model scores lowest | TX01555470, TX01585580, TX01575959 |

### 8.2 Analyst application (`app/`)
| File | Content |
|---|---|
| `app.py` | Streamlit, 5 pages: alert queue (filters, risk colours, alerts/day, click-to-open), transaction card (score, risk and reassuring factors with observed vs usual, decision form, chat with 6 suggested questions), customer 360 (profile, habits, timeline incl. digital events, map with the alert highlighted), performance (model vs engine, recall per type, drivers, leaderboard), journal (decisions + copilot log). Sidebar: demo buttons, data source, copilot mode, token counter, "Rafraîchir depuis Fabric" |
| `data_access.py` | Source layer. **Fabric live**: pyodbc + ODBC Driver 17, Entra token (`AzureCliCredential`, else browser) on `lh_fraud` SQL endpoint; small Gold tables loaded once; customer history / digital events / related cases queried with server-side filters; decisions uploaded to OneLake `Files/app_feedback/decisions.csv`. **Fallback**: parquet in `app/data` (refreshed on each live load). Test labels nulled; `gender` dropped |
| `tools.py` | 9 tools returning compact JSON: `get_alert_queue`, `get_transaction`, `get_customer_profile` (habits optionally before a transaction), `compare_to_habits` (past only: ratio, p95, countries, city/merchant/device/beneficiary seen and seen > 24 h, night share, previous op, 24 h activity, card bursts, distance and implied speed), `get_customer_history`, `get_digital_events` (≥ 24 h window), `find_related_cases` (bank-wide, counts only frauds **reported before** the transaction), `get_kpis`, `record_decision` |
| `copilot.py` | Azure OpenAI function calling (≤ 4 tool rounds), brief §9.3 prompt + explicit decision rule, 5-part format, open transaction pre-injected, tool output capped (3,500 chars), disk cache (`copilot_cache.json`), log of every call (`copilot_log.jsonl`), deterministic offline mode (also used if the LLM fails), `COPILOT_OFFLINE=1` switch |
| `warmup.py` | Pre-computes 20 answers (6 questions × 3 demo cases + 2 global) |
| `test_aoai.py` | Connectivity check |
| `requirements.txt`, `.env.example` | Dependencies; config template (no secrets) |

### 8.3 Azure OpenAI
- Found with `az cognitiveservices`: resource `aoai-fraud-australiaeast-vnxcy`, only deployment **gpt-5-mini** (GlobalStandard, 70k TPM).
- `.env` written locally from `az ... keys list` (git-ignored, key never printed); `test_aoai.py` → "OK copilote".
- gpt-5-mini is a reasoning model: rejects temperature/max_tokens → code uses `max_completion_tokens` + `reasoning_effort=low`.
- Prompt iterations from live tests: no invented IDs, always compare to habits, call digital events for web/transfers, recent device/beneficiary (< 24 h) is not reassuring, BLOQUER/ESCALADER/VALIDER rule, French level names, no recommendation on KPI questions.
- Measured: ~5,200 tokens and ~12 s per uncached question (was ~7,500 / 16 s before pre-injection); unknown ID handled.

### 8.4 Verification done
- All 5 pages rendered headless (`streamlit.testing.AppTest`) on local data and on live Fabric: no exception.
- Decision written via the UI → `decisions.csv` → mirrored in OneLake (read back, then deleted).
- Live answers on the demo cases: TX01555470 BLOQUER (3 failed logins from IT IP, beneficiary added 23:33, 814 TND = 4.3× usual) · TX01585580 BLOQUER · TX01575959 VALIDER (chip, Tunis, daytime, 936 past ops all in TN).
- Server health check `http://localhost:8501/_stcore/health` → ok.

### 8.5 Repository and docs
- Deleted 6 outdated docs (they wrongly called the split bug a data leak).
- `README.md`: architecture, results, run steps, live Fabric mode, token discipline.
- `.gitignore`: `.env`, `app/data/`, parquet, zip, test/, third-party McKinsey files.
- Local git: `3ae7d57` (initial app + notebooks), `2404a7d` (live Fabric). Not pushed. Left uncommitted on purpose (other session): `COPILOT_HANDOFF.md` edits, `notebooks/03c_powerbi_dashboard.ipynb`.
- `notebooks/` holds older local copies: replace them with the final Fabric versions (Fabric Git integration or download) before pushing.

### 8.6 How to run (demo day)
```powershell
az login                                  # Fabric + Azure OpenAI access
cd C:\Users\oussa\Desktop\dsi\app
python warmup.py                          # optional: instant answers for the demo questions
streamlit run app.py                      # http://localhost:8501 — sidebar must show "🟢 Fabric live"
```
Demo path: sidebar "Fraude évidente" → ask "Pourquoi … suspecte ?" → BLOQUER → "Faux positif évité" → "Pourquoi … pas une fraude ?" → VALIDER → Performance page.
