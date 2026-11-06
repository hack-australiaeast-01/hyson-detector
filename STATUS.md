# Project status — Hyson Detector · AI Banking Copilot for Fraud Detection
Updated: 2026-11-06 01:00 · ✅ done · 🟡 in progress · ❌ to do · Target level: **Gold ("Or")** (brief §6) · Full work log: §8 · Latest: §13–14

**Live demo:** https://hyson-detector.streamlit.app · **Repo (jury):** https://github.com/hack-australiaeast-01/hyson-detector · last commit `014cd04`

## 1. Pipeline & model (frozen: do not rerun notebook 02, or the demo IDs change)
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Fabric workspace `ws-hack-fraud-australiaeast`, lakehouse `lh_fraud`, copy job | ✅ | 1,908,228 transactions, 3,500 customers (larger than the brief) |
| 2 | Time split | ✅ | train 2025-01→2026-05 · valid 2026-06→07 · test 2026-08→09 (no labels) |
| 3 | NB 01: silver + `gold_features` (73 features, past-only) | ✅ | Behaviour, velocity, novelty, geography/speed, channel, digital timing, graph (already-reported frauds only), calendar |
| 4 | Leak checks | ✅ | 0 test labels, 0 duplicates, no label columns; target-encoded `*_risk` features excluded |
| 5 | NB 02: rules + HGB / LightGBM / LambdaRank / blend, champion chosen on valid | ✅ | Champion **LightGBM**: the same model scores and explains (SHAP) |
| 6 | Gold tables + submission CSV (§14) | ✅ | gold_scores, gold_alert_queue, gold_alert_explanations, gold_model_metrics/leaderboard/importance/recall_by_type, Files/submission/submission_csv · copy in the repo: `submission/submission.csv` (187,628 rows, 1,876 alerts) |
| 7 | App ↔ Fabric | ✅ | **Live** via SQL analytics endpoint (Entra token): Gold tables, full history with lat/long, 781k digital events, related cases across the whole bank; decisions written to OneLake `Files/app_feedback`; parquet fallback |

## 2. Results (validation Jun–Jul 2026, out-of-time, final)
| | Alerts | Frauds caught | Recall | Precision |
|---|---|---|---|---|
| Current rules engine | 3,338 | 117 / 1,013 | 11.5 % | 3.5 % |
| Model, same alert volume | 3,338 | 787 | 77.7 % | 23.6 % |
| **Model, top 1 %** | **1,779** | **718** | **70.9 %** | **40.4 %** |
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

- Pitch line: "Half the alerts, about 6× more frauds caught, about 67 % fewer false alerts (1,061 vs 3,221)."
- Demo cases:
  - TX01555470, obvious fraud: 3 night-time web transfers in 4 h (00:54, 03:30, 04:49), 3 failed logins in the previous 24 h.
  - TX01585580, subtle fraud: 7.69 TND online at 02:03 at a new merchant, after 2 other micro-purchases (card testing).
  - TX01575959, false positive avoided: 3,361 TND chip purchase in Tunis, daytime, retired customer. The current engine raised an alert; the model scores it in the bottom 0.01 %.

## 3. Application & copilot (`app/`)
| # | Item (brief §) | Status | Notes |
|---|---|---|---|
| 8 | Alert queue: filters (period/date/channel/risk/fraud type), risk colours, alerts per day (§10) | ✅ | `app.py` · banner "une alerte n'est pas une fraude" + columns **Fraudes mesurées** (validation rate for that score) and **Action conseillée** (§13) |
| 9 | Transaction view: score, risk and reassuring factors (observed vs usual), decision + confidence + comment, no scrolling (§10) | ✅ | |
| 10 | Customer 360: profile, habits, timeline with digital events, map (§10) | ✅ | Live from Fabric · habits = customer's past **before the open alert** (same 409 ops / 189.305 TND as the copilot) |
| 11 | 9 copilot tools (§9.2): get_alert_queue, get_transaction, get_customer_profile, compare_to_habits, get_customer_history, get_digital_events, find_related_cases, get_kpis, record_decision | ✅ | `tools.py`, compact JSON, unknown IDs handled |
| 12 | Copilot: prompt §9.3, 5-part format §9.4, function calling, cache, guardrails (§9.8) | ✅ | `copilot.py` v4: intent routing + prefetch (1 LLM round), streaming + live tool steps, deterministic recommendation (`recommandation_systeme`), FR/EN, off-topic & injection guardrails, prompt caching, timeout/retries, offline fallback |
| 13 | Copilot traceability: question, tools, tokens, latency → `data/copilot_log.jsonl` + Journal page (§9.8) | ✅ | |
| 14 | Decision journal + feedback (`data/decisions.csv`) (§10) | ✅ | |
| 15 | KPI page: model vs current engine, recall per type, drivers, leaderboard (§10) | ✅ | |
| 16 | Azure OpenAI: `app/.env` (endpoint, key, deployment) | ✅ | Deployment **gpt-5-mini**, API 2024-12-01-preview, `reasoning_effort=low`, `max_completion_tokens` 2,400, timeout 60 s, 2 retries |
| 17 | Tested live on the §9.7 questions: 6 per demo case + 2 global, FR and EN = 40 answers | ✅ | `python warmup.py fr en` (cache). Recommendations 100 % consistent: TX01555470 BLOQUER · TX01585580 BLOQUER · TX01575959 VALIDER. Avg **3,300 tokens (≈1,400 from prompt cache), 7 s**, 1 round; instant from cache |
| 18 | Power BI report on Gold (manager view, complement) | ✅ | Built as code by `notebooks/03d_powerbi_dashboard.ipynb`: 8 `pbi_*` tables → Direct Lake model `sm_fraud_copilot` (25 DAX measures) → report "Fraud Copilot — Dashboard", 4 dark-theme pages (executive view, alert queue, why?, fraud types). 03d = final design pass (title line, slicer height, no "K" units, no "—" row, legend titles) — **run in Fabric and verified on all pages**. Local 03d also auto-attaches `lh_fraud` (`%%configure`). To do: delete old notebooks `03_`, `03b_`, `03c_` in Fabric |
| 18a | Power BI icon navigation + FR/EN | ✅ | `notebooks/03e_powerbi_dashboard.ipynb` **run in Fabric as a job (Completed)**: report rebuilt, 8 pages (4 FR + 4 EN), 4 icons; `pbi_*` = 1,779 alerts / 718 / 1,061 / 117 / 3,221 (demo FAIBLE row excluded). Job-safe: plain `pip`, PBIR-aware report update, session stop only when interactive. Do not edit the report by hand (03e overwrites it) |
| 18c | App FR/EN + icon navigation | ✅ | Sidebar "Français / English" switch translates every page; Power BI page uses the same 4 icons + titles to change report page and opens the EN report pages in English. Tested in the browser (FR + EN) |
| 18d | "Marché & benchmarks" page (FR/EN) | ✅ | `app/market.py`: 6 cited public benchmarks (EBA/ECB 2024 + Dec 2025, UK Finance 2025/2026, BCT 2024, PwC/McKinsey FP estimate) · same KPIs on our data (live Fabric SQL, snapshot `data/feat_market.parquet`) · Tunisia-scale scenario with editable assumptions · fraud rate by channel / entry mode, 3-D Secure lever · **rules-engine audit** (R04, R01, R05 to switch off: ≈ 17,483 fewer false alerts for 2 solo frauds) · **time to detect** (median 11 days, 32.8 % within 7 days). Snapshots `feat_legacy_rules`, `feat_time_to_detect`. Tested FR + EN (AppTest) and in the browser |
| 18b | Power BI embedded in the app | ✅ | Page "📈 Tableau de bord Power BI" in `app.py`: secure embed (`reportEmbed`, viewer signs in with the org account, nothing public), page picker + "Ouvrir dans Power BI". IDs in `.env.example` (`PBI_REPORT_ID`, `PBI_TENANT_ID`). Tested: page renders, no errors |
| 19 | GitHub repo + hosted demo | ✅ | Public repo **hack-australiaeast-01/hyson-detector** (owner/admin = team account), full Git history, no secret in files or history (key scanned). Streamlit Community Cloud: https://hyson-detector.streamlit.app (auto-redeploys on push). Old copy `saitaflex/hyson-detector` still public → archive it. Fabric Git integration not done (optional) |
| 20 | GitHub Copilot usage evidence (screenshots, time saved) | 🟡 | `docs/AI_TOOLS_USAGE.md` ready: Copilot log table to fill with real uses + screenshots in `docs/copilot_evidence/`; GitHub Copilot agent mode (VS Code) and Azure OpenAI usage declared (§13, §16.4, §17); commits carry the `Co-authored-by: Copilot` trailer |
| 21 | Slides: problem, demo, architecture, results, prototype → production, limits | ❌ | §17 · diagrams ready: `docs/ARCHITECTURE.md` + PNGs in `docs/img/` |
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

## 5. Next actions (as of 2026-11-06 01:00)
**Blocking for the pitch — only the team can do these:**
1. 🔴 **Azure OpenAI key in Streamlit Cloud** → share.streamlit.io → app ⋮ → Settings → Secrets → paste `app/.streamlit/secrets.toml.example` with the real key from `app/.env` → Save. Today the public app says "Copilote : Hors-ligne (règles)": demo cases answer from the gpt-5-mini cache, new questions get the offline template.
2. 🔴 **Slides** (problem, live demo, architecture from `docs/img/`, results, prototype → production, limits) — §17.
3. 🔴 **Rehearse 3× (5 min) + record a backup video** of the demo path (§10.4) — §10, §17.
4. 🟠 **Fill the GitHub Copilot usage table** in `docs/AI_TOOLS_USAGE.md` with real uses + screenshots (`docs/copilot_evidence/`) — §13 deliverable, 30 s of the pitch.
5. 🟠 **Archive `saitaflex/hyson-detector`** (older copy, still public) so the jury only finds `hack-australiaeast-01/hyson-detector` (github.com/saitaflex/hyson-detector/settings → Archive).
6. 🟡 Fabric workspace clean-up: delete old notebooks `03_`, `03b_`, `03c_` (and `03d_` if 03e is the final), check `Saitaflex-model`.
7. 🟡 Decide whether the personal e-mail in the public Git history (`saitaflex <…@gmail.com>`) is acceptable.

**Demo day checklist:**
- Open https://hyson-detector.streamlit.app 5 min before (free apps sleep; first load ≈ 20 s).
- Pitch laptop: `az login` → `cd app` → `streamlit run app.py` (live Fabric) → run the demo path once to warm the cache.
- Do not click "Rafraîchir depuis Fabric" during the pitch (≈ 15 s reload). Do not re-run notebooks 01/02 (demo IDs would change).
- Have one Aug–Sep alert ready besides the 3 demo cases (they are June cases chosen for their ground truth).

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

Verified OK: unknown ID handled ("TX99999999 introuvable"), KPI answer computed without LLM (now from exact counts: 2,160 false alerts avoided, 601 more frauds), call logged in `data/copilot_log.jsonl` with tools, tokens and latency.

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

## 9. Copilot v4 — Azure OpenAI improvements (2026-11-05 evening)

### 9.1 What was wrong (found in the real log `copilot_log_before_v3.jsonl` and the cached answers)
| # | Problem | Evidence | Fix |
|---|---|---|---|
| C1 | "Top 10 most risky" answer broken | 10,410 tokens, 2 tool calls, JSON cut at 3,500 chars → "valeur partielle", "TX0190xxxx" | Compact `get_alert_queue` rows + `_compact()` trims lists item by item (never cuts JSON) |
| C2 | Investigation summary without chronology | used only the transaction itself | prefetch habits + digital events + related cases for summaries |
| C3 | 2–3 LLM rounds per question, every question re-sent the full transaction | ~5,200 tokens, 12–15 s | intent routing + prefetch → 1 round |
| C4 | English mode appended "(Answer in English)" while the prompt said "réponds en français" | mixed languages | `lang` parameter + LANGUAGE line; cache key includes language |
| C5 | Spinner for 10–15 s | — | streaming answer + live tool steps (`st.status`) |
| C6 | Recommendation varied between questions (subtle fraud BLOQUER vs ESCALADER) | 2 of 6 answers differed | deterministic `recommandation_systeme` computed in `tools.recommend` |
| C7 | Wrong reading "plafond non dépassé" for ratio 2.24; false "contradiction" on "Nouveaux commerçants (24 h)" | FP demo answer | prompt rule "ratio > 1 = above"; clarified labels (`FACTOR_CLARIFY`) |
| C8 | Technical field / tool names in answers (`moteur_regles_actuel.fausses_alertes`, `get_digital_events`) | EN KPI answer | prompt rule + regenerated the 8 affected answers |
| C9 | KPI counted 1,780 alerts | the avoided-false-positive demo row (FAIBLE) is not an alert | 1,779 alerts / 718 frauds / 1,061 false alerts (README fixed; **Power BI still shows 1,780 → filter `risk_level <> "FAIBLE"` in 03e**) |
| C10 | No off-topic / injection guardrail, no timeout | brief §9.8 | prompt rules; client timeout 60 s, 2 retries |
| C11 | Offline answers were written to the cache (served as if they were LLM answers) | 2 entries | only Azure answers are cached; offline answers recomputed |

### 9.2 How the copilot works now (`app/copilot.py`)
1. `detect_intent()` (FR + EN keywords): analyse · habits · before · related · summary · kpi · queue · general.
2. `_prefetch()` calls the needed tools in Python (e.g. analyse = transaction + habits + digital events for MOBILE/WEB/VIREMENT) and gives them to the LLM as **FAITS**; the LLM can still call any of the 9 tools for missing facts (≤ 4 rounds).
3. Static system prompt first (eligible for Azure prompt caching), then a dynamic message (language, intent, open transaction, facts), last 2 exchanges, question.
4. Streaming (`stream=True`, usage included): tokens shown as written, tool steps shown live; all calls logged with intent, language, tokens (incl. cached), rounds, latency.
5. Decision = `recommandation_systeme` (documented rule + measured validation precision); the LLM explains it and may flag a contradicting fact without changing it.

### 9.3 Decision rule (`tools.recommend`, measured on Jun–Jul 2026 validation alerts)
| Condition | Decision | Confidence | Validation precision | Alerts (valid + test) |
|---|---|---|---|---|
| percentile ≥ 0.998 and ≥ 2 concordant signals | BLOQUER | élevée | 94 % | 734 |
| ELEVE and ≥ 2 signals | BLOQUER | moyenne | 87 % | 361 |
| ELEVE otherwise, or MOYEN | ESCALADER | moyenne | 20 % (MOYEN) | 2,560 |
| FAIBLE | VALIDER | élevée, or moyenne if a business rule still alerted | — | 1 (demo) |

### 9.4 Results
| | Before | After (v4) |
|---|---|---|
| Tokens per new question | ~5,200 (top 10: 10,410) | **~3,300**, of which ~1,400 served from Azure prompt cache |
| LLM rounds | 2–3 | **1** |
| Latency | 12–15 s, spinner | **~7 s**, text streams after ~3–8 s; cached demo answers instant |
| Recommendation consistency (3 demo cases × 6 questions × 2 languages) | 4/6 on the subtle fraud | **100 %** |
| Languages | FR (EN mixed) | FR + EN |
| Pre-computed answers | 20 (FR) | **40 (FR + EN)** — `python warmup.py fr en` |

Verified: 12 page renders (6 pages × FR/EN) without exception on live Fabric; FR chat (suggestion from cache 0.2 s, new question 8.5 s / 3,028 tokens with 2,432 cached); off-topic question refused in one sentence; unknown ID handled. Note: Streamlit `AppTest` cannot replay the EN decision radio (translated `format_func` labels) — harness limitation, not an app error.

## 10. Hyson Detector — showcase features for bank judges (2026-11-06)

Goal: go beyond "a chat on top of a model" and speak the bank's language (KPIs, process, governance), with a friendly first-time experience.

### 10.1 What was added
| Feature | File | What it shows | Honesty notes |
|---|---|---|---|
| Brand + light theme | `ui.py`, `.streamlit/config.toml`, `app.py` | "Hyson Detector" logo, bank-platform palette, grouped sidebar (Bienvenue/Analyste/Enquête IA/Pilotage), branded splash while Fabric loads | — |
| Démarrer ici + guided tour | `studio.py` (TOUR, page_guide), `app.py` welcome dialog | 4 headline KPIs, 8-step tour, hint banner on every page | — |
| Le Procès | `courtroom.py`, `studio.page_proces` | prosecutor + defence (parallel) then judge, on the same prefetched Fabric facts; analyst accepts/overrides → decision log (`source=proces`) | judge receives the deterministic rule recommendation; ~6k tokens, cached for demo cases |
| Reconstitution | `features.replay_steps`, `studio.page_replay` | hours before the alert, step by step, risky signals in red, map, AI narration | — |
| Contre-enquête | `features.counterfactual`, `studio.page_contre` | neutralise top SHAP factors (log-odds) one by one → robust / sensitive | only the top-5 stored SHAP factors are available |
| Constellation | `features.constellation`, `studio.page_galaxy` | 29 points of compromise (lift ×2.5–×4.1, ≥ 8 victims, only frauds reported **before** the period), 294 exposed alerts, 13 networks | exposure **not predictive** in validation (41 % vs 40 %) → investigation lead, not in the score |
| Impact & processus | `features.impact/drift`, `studio.page_impact` | fraud TND caught 78,059 (68 %) vs 25,462 (22 %); legitimate TND interrupted 97,857 vs 8,081,081; false alerts 1,061 vs 3,221 (−67 %); frauds 718 vs 117 (×6.1); analyst hours; process flow; reco mix; median decision time; AI cost/alert; PSI 0.0027 | workload assumptions editable on screen |
| Stopwatch + case file | `app.py`, `tools.record_decision(duration_s)`, `studio.case_file_html` | alert → decision time; printable HTML dossier | old decisions.csv auto-upgraded with `duration_s` |

### 10.2 Corrections made on the way
- Legacy engine catches **117** frauds (exact recount from `silver_transactions`), not 116; `get_kpis` now uses `features.impact()` → 3,221 false alerts. Cached KPI answers regenerated (no more "3,222").
- Plotly log funnel rendered "NaN×10^Infinity" → replaced by step cards (`ui.flow`).
- Metric deltas with a unicode minus were shown red/up → ASCII "-".
- Judge pasted raw JSON / wrote "BLOQUER" in English mode → plain-text recommendation + language rule (cache key `proces-p2`).

### 10.3 Verification
- AppTest: 24 renders (12 pages × FR/EN), 0 exceptions; interactions (hearing, accept verdict, replay, narrate, contre verdicts, stopwatch, dossier, tour, welcome dialog) OK.
- Playwright (Edge) screenshots of every new page checked visually.
- `python warmup.py fr en`: 40 copilot answers + 6 trials cached → demo is instant.

### 10.4 Demo path (≈ 3 min)
Démarrer ici → Fraude évidente TX01555470 → ask "Pourquoi suspecte ?" → Le Procès → Reconstitution → decide (< 30 s on the stopwatch) → Faux positif évité TX01575959 → Contre-enquête (robust clearance) → Constellation → Impact & processus.

## 11. Marché & benchmarks — the "killing blow" page (2026-11-06)

**Why:** every team shows precision/recall on synthetic data; few answer the jury's real question, "how does it compare to real banks, and what does the bank do with it?" (business relevance = 20 %).

**What (`app/market.py`, FR/EN, sidebar → Pilotage):**
1. Six real public benchmarks with links (EBA/ECB 2024 and Dec 2025, UK Finance 2025/2026, BCT 2024, PwC/McKinsey false-positive estimate).
2. The same KPIs computed live on our data (Fabric SQL; parquet snapshot offline): false alerts rules 96.5 % vs model 59.6 %; cross-border 15.0 % of fraud vs 1.2 % of value (EU: 28 % vs 4 %); fraud value stopped 67.7 % vs 22.1 %.
3. Tunisian-scale scenario (BCT 2024 volume × editable fraud rate): ~TND 8.6 m exposure/yr, ~TND 3.9 m more fraud stopped/yr, ~2 m fewer false alerts/yr — labelled as a scenario.
4. Fraud rate by channel and entry mode: ATMs 25 % of fraud for 10 % of value; online without 3-D Secure 1.8× riskier.
5. Rules-engine audit: R04, R01, R05 have < 1 % precision → switch off = ≈ 17,483 fewer false alerts for 2 frauds caught by them alone; R02 (foreign country) catches 1,206 of 1,242 legacy frauds.
6. Time to detect: median 11 days to report, 32.8 % within 7 days, TND 693,791 reported after a week; the model alerts at day 0.

**Honesty rules:** every external figure has its source and year; our fraud rate (0.28 %) is shown as deliberately higher than the EU's (synthetic data, brief FAQ); "different scope" is stated where a comparison is only indicative; the 90–95 % figure is labelled an industry estimate; no public Tunisian fraud rate exists, so the scale-up uses the EU rate as an editable assumption.

**Verification:** AppTest renders the page with no exception in FR and EN; checked visually in the browser on live Fabric data.

**Pitch line (20 s):** "Real banks' rule engines generate 90–95 % false alerts; we measured 96.5 % on this bank's and cut it to 59.6 %. And without any AI, the bank can switch off three rules tomorrow: 17,000 fewer false alerts, two frauds lost."

## 12. Fraud-number audit (2026-11-06) — Fabric = source of truth

Read-only SQL on `lh_fraud`, then compared with the app (`tools.get_kpis`, `features.impact`, `market.py`), the Power BI tables and the docs.

**Canonical numbers (validation Jun–Jul 2026, 177,953 transactions, 1,013 frauds):**

| | Alerts | Frauds | False alerts | Precision | Recall |
|---|---|---|---|---|---|
| Current rules | 3,338 | 117 | 3,221 | 3.5 % | 11.5 % |
| Model, same volume | 3,338 | 787 | 2,551 | 23.6 % | 77.7 % |
| Model, top 1 % | 1,779 | 718 | 1,061 | 40.4 % | 70.9 % |

→ 2,160 false alerts avoided · 601 more frauds · recall ×6.7 at equal volume · PR-AUC 0.646.

**Checked OK:** silver 1,542,647 train + 177,953 valid + 187,628 test; 9,507 frauds = labels table; 0 test labels anywhere (silver, labels, queue); recall by type recomputed = `gold_model_recall_by_type`; legacy analyst verdicts = labels (0 mismatch); time-to-detect dates (0 negative, 0 missing); the target-encoded `f_*_risk` columns exist in `gold_features` but **never appear in 18,280 SHAP explanations** → not used by the model.

**Fixed:**
- `gold_model_metrics.frauds_caught_legacy` = 116 vs 117 in the data → the app already recounts (`features.impact`); **03e now recomputes legacy and top-1 % counts from `gold_scores` × labels** (Power BI showed 116 / 1,780 / 1,062 / 602).
- `tools.get_kpis` rounded precision/recall to 4 decimals → 0.1155 displayed as 11.6 %; now exact (11.5 %).
- Docs aligned (README, STATUS, JURY_HANDBOOK); market-page caption: legacy alerts cover Jan 2025 – Jul 2026, not training only.

**Follow-up (2026-11-06):**
1. ✅ `03e_powerbi_dashboard` re-run in Fabric (job Completed): Power BI shows 117 / 1,779 / 1,061 / 2,160 / 601, icons, FR/EN.
2. ✅ Repo notebooks 01/02/03d/03e replaced by the versions exported from Fabric (with outputs); Data Wrangler "titanic" leftover cells removed from 02 (repo + Fabric).
3. Still optional, for code readability: in notebook 01, stop creating `f_merchant_risk`, `f_device_risk`, `f_beneficiary_risk` (or add a comment "not used: not point-in-time") so a reviewer does not flag them. Re-running 01/02 would change demo IDs, so only edit the code comment if the pipeline stays frozen.

## 13. Judge review, deployment and polish (2026-11-05 22:30 → 2026-11-06 01:00)

### 13.1 Delivery
| Item | Result |
|---|---|
| GitHub | Public repo **https://github.com/hack-australiaeast-01/hyson-detector** (created with the team account so it is owner/admin; first push went to `saitaflex/hyson-detector`, now a stale copy). Notebooks = Fabric exports with outputs; `submission/submission.csv`; secret scan of files + history clean |
| Streamlit Cloud | **https://hyson-detector.streamlit.app**, main file `app/app.py`, Python 3.12, redeploys on every push. Reads the committed Gold snapshot (no Entra login in the cloud). Secrets bridge accepts keys at root or under a `[section]`; `secrets.toml.example` provided |
| Architecture | `docs/ARCHITECTURE.md`: global architecture, AI copilot workflow, Le Procès sequence, page workflow, demo path (Mermaid, rendered by GitHub) + PNGs in `docs/img/` for slides; linked from README and JURY_HANDBOOK §7 |
| AI tools declaration | `docs/AI_TOOLS_USAGE.md`: development assistant = **GitHub Copilot agent mode (VS Code)** only; Azure OpenAI = in-product copilot |
| Logo | Team PNG logo (cropped, white + blue variants, favicon) in sidebar, splash, welcome dialog, "Démarrer ici", printable case file, README (`app/static/brand/`) |
| New page (other session) | **Enquête approfondie** (`app/deepsearch.py`): watch list of medium alerts whose customer already had an alert (≈ 53 % fraud vs 16 % for other medium alerts, validation), evidence board E1…En, one-call AI synthesis (cached) |

### 13.2 "Hostile judge" review — findings and fixes
| # | Finding (what a judge would hit first) | Fix | Verified |
|---|---|---|---|
| J1 | Hosted app only had history since **June 2026** and **no digital events**: "5 past operations, 236 TND average, no failed logins" for the obvious fraud | Snapshot = full history since 2025 (999,946 rows) + 402,553 digital events for the 1,814 alert customers; categories in memory; `reported_date` only for train/valid frauds (0 on test) | Same values as live Fabric: 409 ops / 189.305 TND / 3 failed logins; ~500 MB RAM |
| J2 | §9.7 "**les 10 plus risquées d'hier**" answered "no alerts on 2026-11-04" (real clock) | Demo calendar: today = last day of the live flow (2026-09-30), "hier" = 2026-09-29; date passed to `get_alert_queue` in prefetch | Live: 10 alerts of 2026-09-29, 1 tool call, 3,426 tokens |
| J3 | Red **"RuntimeError: FABRIC_SQL_ENDPOINT non configuré"** in the public sidebar | No endpoint → snapshot mode without error, label "Instantané Gold exporté de Fabric (parquet)" | Checked on the public app |
| J4 | **Titanic** Data Wrangler cells left in notebook 02 | Removed (repo + Fabric definition, no re-run) | 13 cells |
| J5 | **Three different "usual amounts"** (card 189 · copilot online 236 · Client 360 273, the last one including operations after the alert) | Client 360 habits = past before the open alert | 409 / 189.305 TND everywhere |
| J6 | "8.0 M TND **bloqués** à tort": the legacy engine alerts, it does not block | "mis en alerte à tort" (guide + impact) | — |
| J7 | Random live alert explained with jargon ("vitesse 21 km/h élevée", amount *below* average as a risk), missed the decline reason | `compare_to_habits` adds `statut`, `motif_refus`, `sequence_carte_24h` (ops, new merchants, contactless, declines); prompt: business facts first, a model factor is not an anomaly by itself | Better (PLAFOND_DEPASSE / SOLDE_INSUFFISANT now cited); still model-driven when no business rule fired |
| J8 | Brief says 435 k tx / 6,324 legacy alerts / 15 % / 42 %; we show 1.9 M / 32,065 / 3.5 % / 11.5 % | README + handbook: dataset delivered in Fabric is larger; baseline recomputed (2025 → 3.9 % / 13 % over train, 3.5 % / 11.5 % in valid) | Fabric SQL |
| J9 | "~1,000 alerts / 2 months" vs our 1,876 | Documented: 1,000 = 1 % of the brief's 101,730 test rows; top 0.5 % option (≈ 900 alerts, 58 % recall, 66 % precision) | — |
| J10 | Public chat can burn Azure credits | `COPILOT_HOURLY_CAP` (60 live calls/h) → cache / offline beyond | — |
| J11 | Score file only in OneLake | `submission/submission.csv` in the repo (187,628 unique IDs, 1,876 alerts, no nulls) | — |
| J12 | Token figures inconsistent (5–6 k vs 3,300) | Handbook aligned on ≈ 3,300 (≈ 1,400 prompt-cached) | — |
| J13 | **"Everyone in the table looks suspicious, all at 100 %"** (percentile column = 99–100 % on every row of a top-1 % queue) | Banner "une alerte n'est pas une fraude" (1,876 of 187,628 ops; ≈ 649 expected frauds: 562 to block, 1,314 to check); column **Fraudes mesurées** = fraud rate measured in validation for that score (10 bins, monotone/PAV: 0.70 ≈ 12 %, 0.83 ≈ 29 %, 0.97 ≈ 88 %, ≥ 0.99 = 100 %); column **Action conseillée** (same rule as the copilot, `tools.recommend_vector`); transaction page shows "Fraudes mesurées à ce score" | Calibration check: 718 expected = 718 real on validation; public app checked |

Also checked clean: no leakage (past-only windows, labels excluded, test labels NULL everywhere, no early stopping on valid), off-topic and unknown-ID handling live, no secret in the repo.

### 13.2b Streamlit Cloud memory limit (2026-11-06 01:30)
- **Symptom:** public app showed "This app has gone over its resource limits" after the full-history snapshot (J1) was added.
- **Cause:** history + events loaded as plain strings = ~600 MB, peak 856 MB with one user (Community Cloud floor: 690 MB).
- **Fix (`data_access.py`, snapshot files):** text columns stored and loaded as categories, coordinates float32, unused `session_id` dropped, Arrow buffers freed on load (`self_destruct` + `release_unused`), per-customer caches 96/128 entries. Data in memory 334 MB → ~80 MB.
- **Measured** (real Streamlit server in cloud mode, 15 pages + 3 demo cases, 3 sessions): peak **520 MB**, 0 exceptions; same figures as live Fabric. After a crash the app needs a manual **Reboot** (share.streamlit.io → ⋮ → Reboot): it does not restart on push.

### 13.3 Verification
- AppTest: 28 renders (14 pages × FR/EN) with no exception in **cloud mode** (no `.env`, no Fabric) and key pages in **live Fabric** mode.
- Public app checked with Playwright after each push: snapshot label, no error banner, full history in Client 360, new queue columns, logo.
- Live copilot re-tested on §9.7 questions (yesterday's top 10, why suspicious on a random Aug–Sep alert, why not fraud, unknown ID, off-topic).

### 13.4 Known limits to assume in Q&A
- ≈ 62 % of alerts have no business-rule factor → their explanation rests on model factors; the "concordant signals" of the recommendation count strong model factors (precision of each band is measured and shown).
- Demo cases are June (validation) cases chosen for their ground truth; keep an Aug–Sep alert ready.
- Champion picked among 4 models on the same validation period that is reported (they are within ~1 pt; test labels are with the jury).
- gpt-5-mini has no temperature setting (brief §9.8 asks 0–0.2): stability comes from the deterministic recommendation rule + low reasoning effort.
- Online, "related cases" only see the 1,814 alert customers (answer says "extrait local"); live Fabric sees the whole bank.
- Batch scoring, not at authorisation time.

## 14. Ask about a person + new data source onboarding (2026-11-06)

### 14.1 "Ask the AI about someone in the tables" (`app/person_search.py`, `copilot.py`, `tools.py`)
- **Gap found:** the copilot always answered about the transaction open on screen; an ID or a person typed in the question was ignored.
- **Now:** (1) a `TX…` ID in the question overrides the open transaction; (2) a `C…` customer ID → profile + 30-day history; (3) a description ("le client retraité de Sfax de plus de 70 ans avec des alertes", "doctor customers from Tunis aged between 30 and 40") → approved filters (city, segment, occupation, age, KYC, digital, with alerts) → new read-only tool `find_customers` → short list with alert counts and the riskiest alert. 0 tokens offline; with Azure OpenAI the facts are prefetched and the LLM is told not to issue BLOCK/VALIDATE for a person search.
- **UI:** "Rechercher un client par description" box on Vue client 360; "Ouvrir" jumps to the customer on their riskiest alert.
- **Tested:** 7 questions FR/EN offline (no paid call); unknown ID → "introuvable"; AppTest search + open.
- **Routing guard (review fix):** questions about the open case ("ce client…", "le client a-t-il…", "même commerçant", "other customers", "this transaction") are never treated as a person search — the demo button "D'autres clients sont-ils passés par le même commerçant…" was being routed to a list of *commerçant* customers. 15 routing cases checked (demo buttons, §9.7 questions, descriptions, IDs).
- **Jury answer — why not free SQL:** security (no injection, only approved tables), reliability (the LLM only states what tools return, §9.1), cost (aggregates, not tables), traceability (every call logged). On a real bank database the same filters run as parameterised queries with personal data masked.

### 14.2 New data source onboarding (`app/onboarding.py`, page "Nouvelle source de données", group Données)
1. Load a CSV (or the synthetic `app/samples/partner_bank_sample.csv`: English columns, POS/ATM/ECOM codes, EUR + TND, ISO3 countries, dd/mm/yyyy).
2. Profile (types, empty cells, distinct values; identifiers masked).
3. Proposed mapping to our schema with a confidence per field (rules: name similarity 60 % + value fit 40 %, 0 tokens), editable; optional "Affiner avec l'IA" = 1 Azure OpenAI call on column names + statistics only (logged with tokens). Codes, countries, dates and currencies are translated (rates editable, indicative).
4. Accuracy: required-field coverage, % valid translated values, untranslated values listed, row/total reconciliation, drift vs our data (PSI channel mix + amount bands, reference = live Fabric query, snapshot `feat_onboard_ref`), fraud rate if labels exist. Verdict Prêt / À revoir / Bloqué (≥ 95 % valid, PSI < 0.2, all required fields).
5. **Human approval required** (name + checkbox; disabled when Bloqué) → versioned data contract (`data/staging/<source>_<version>/data_contract.json`) + translated parquet + `data/onboarding_log.csv` (approved / rejected, by whom). Next step (documented, not live): drop to OneLake → bronze → silver via the Fabric pipeline, then rescoring in notebook 02 before production.
- **Tested:** sample → 12/12 columns mapped, 100 % valid, PSI 0.10, verdict Prêt, approval writes contract + log (test artefacts deleted afterwards); a broken file (no channel, unknown codes) → Bloqué, approval disabled. AppTest FR + EN, no exception.

**Restart the app** (Ctrl+C, `streamlit run app.py`): new modules are only loaded at start. Onboarding outputs (`data/staging/`, `data/onboarding_log.csv`) are git-ignored.
