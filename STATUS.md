# Project status — Hyson Detector · AI Banking Copilot for Fraud Detection
Updated: **2026-11-06 10:55** · ✅ done · 🟡 in progress · ❌ to do · Target level: **Gold ("Or")** (brief §6)

**Live demo:** https://hyson-detector.streamlit.app · **Repo (jury):** https://github.com/hack-australiaeast-01/hyson-detector ·
**Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (18 diagrams) · **Audit & bank IT:** [docs/AUDIT_AND_BANK_INTEGRATION.md](docs/AUDIT_AND_BANK_INTEGRATION.md) · **Jury Q&A:** [JURY_HANDBOOK.md](JURY_HANDBOOK.md)

Sections 1–6 = **current state** (kept up to date). Section 7 = **work log** (dated history; figures there are as of that time).

## 0. At a glance — deliverables (brief §13)
| Deliverable | Status | Where / evidence |
|---|---|---|
| Working application | ✅ | 15 pages FR/EN + **Nazar work agent** · local = **live Fabric** · public = https://hyson-detector.streamlit.app (Gold snapshot) |
| Copilot (mandatory) | ✅ · 🟡 online key | `app/copilot.py` + 10 tools · **18/18 golden questions (incl. the brief's §9.7 wording), 99.5 % of cited numbers grounded** · public app still "Hors-ligne (règles)" until the key is in Streamlit Secrets (§5.1) |
| Data pipeline on Fabric | ✅ | Lakehouse `lh_fraud`, notebooks 01 · 02 · 03e · 04, pipeline `pl_hyson_retrain`, MLflow model `hyson-fraud-lightgbm` |
| Validation vs current rules | ✅ | Top 1 %: 718 frauds vs 117, 1,061 false alerts vs 3,221 · backtest 69.4 % ± 2.1 recall over 4 periods |
| Technical walkthrough | ✅ | `docs/ARCHITECTURE.md`, `docs/MODEL_CARD.md`, `docs/AUDIT_AND_BANK_INTEGRATION.md`, `README.md`, `JURY_HANDBOOK.md` |
| Automated tests | ✅ | 94 pytest tests (`tests/`, offline, ~60 s: 30 page renders FR/EN, data/model, guardrails, **audit trail**, **Nazar agent**, **explanations**) run by GitHub Actions on every push |
| Usage of GitHub Copilot | ✅ | `docs/AI_TOOLS_USAGE.md`: 12 real uses with commit + screenshot (`docs/copilot_evidence/`), 30/30 commits co-authored by Copilot, ≈ 7 person-days in ≈ 11 h (estimate), 30-second pitch script |
| GitHub repo | ✅ | Code, Fabric notebooks (exported with outputs), `requirements.txt` (root + `app/`), README, tests + CI, no secret in files or history |
| Score file (optional, brief §14) | ✅ | `submission/submission.csv` (187,628 rows, 1,876 alerts) |
| Pitch (slides, rehearsal, backup video) | ❌ | §5 |

## 1. Pipeline & model on Microsoft Fabric (frozen: do not re-run notebooks 01/02, or the demo IDs change)
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Workspace `ws-hack-fraud-australiaeast`, lakehouse `lh_fraud`, copy job `cj_bronze_load` | ✅ | 1,908,228 transactions, 3,500 customers, 781k digital events (larger than the brief) |
| 2 | Time split | ✅ | train 2025-01 → 2026-05 · valid 2026-06 → 07 · test 2026-08 → 09 (labels NULL) |
| 3 | NB 01 `silver_transactions` + `gold_features` | ✅ | 73 features, past-only windows: amount vs habits, velocity, novelty, geography/speed, digital banking, network (frauds already reported), calendar/profile |
| 4 | Leak checks | ✅ | 0 test labels anywhere, leak `assert`, target-encoded `*_risk` excluded (never in the 18,280 SHAP rows), no early stopping on valid |
| 5 | NB 02 scoring + explanations | ✅ | Rules · HGB · **LightGBM (champion)** · LambdaRank · blend; refit on train+valid for Aug–Sep; top 1 % per period; TreeSHAP (3 for, 2 against) + up to 4 rules per alert |
| 6 | Gold tables + submission | ✅ | `gold_scores`, `gold_alert_queue` (3,656), `gold_alert_explanations`, `gold_model_*`, `Files/submission/submission_csv` · repo copy `submission/submission.csv` |
| 7 | NB 04 robustness + MLflow | ✅ | Rolling backtest (4 × 2 months), day-block bootstrap CIs, `gold_model_robustness` / `gold_model_ci`; ML model **`hyson-fraud-lightgbm` v1** = production scores (rank corr 1.0) |
| 8 | Data pipeline + environment | ✅ | `pl_hyson_retrain` (01 → 02 → 03e ∥ 04, retry 1) **created, never run, not scheduled**; versions pinned in `fabric/environment.yml` (Environment item not published) |
| 9 | Power BI as code (NB 03e) | ✅ | `pbi_*` tables → Direct Lake `sm_fraud_copilot` (DAX) → report "Fraud Copilot — Dashboard", 8 pages FR/EN, icon navigation; exact counts 1,779 / 718 / 1,061 / 117 / 3,221. Do not edit the report by hand (03e rewrites it). 03/03b/03c/03d = older versions |
| 10 | App ↔ Fabric | ✅ | Local: **live** T-SQL on the SQL endpoint with the Entra token, decisions written to OneLake `Files/app_feedback`. Public: committed snapshot (Gold + 999,946 history rows + 402,553 events of the 1,814 alert customers, no test labels) |

## 2. Results (validation Jun–Jul 2026, out-of-time, final)
| | Alerts | Frauds caught | False alerts | Recall | Precision |
|---|---|---|---|---|---|
| Current rules engine | 3,338 | 117 / 1,013 | 3,221 | 11.5 % | 3.5 % |
| Model, same alert volume | 3,338 | 787 | 2,551 | 77.7 % | 23.6 % |
| **Model, top 1 % (analyst capacity)** | **1,779** | **718** | **1,061** | **70.9 %** | **40.4 %** |
| Model, top 0.5 % | ~890 | ~590 | ~300 | 58.2 % | 66.4 % |

- PR-AUC **0.646** [0.610–0.675] (rules 0.014) · recall 70.9 % [68.3–73.0] · precision 40.4 % [34.9–45.0] · false alerts avoided 2,160 [1,971–2,335] (95 % day-block bootstrap).
- **Robustness:** re-trained on the past only and tested on 4 periods → top-1 % recall **69.4 % ± 2.1** (worst 66.7 %), fraud value caught 72.5 %; rules 12.6 % / 3.7 % on the same periods.
- Fraud value: 78,059 TND caught (68 %) vs 25,462 TND (22 %) for the rules; legitimate payments flagged 97,857 TND vs 8.08 M TND.
- Recall by fraud type, model vs current engine:

  | Fraud type | Model | Current engine |
  |---|---|---|
  | Stolen card, contactless | 68 % | 0 % |
  | Discreet online fraud | 68 % | 13 % |
  | ATM skimming | 74 % | 18 % |
  | Account takeover | 89 % | 10 % |
  | Card testing | 61 % | 0 % |
  | Cloned card abroad | 91 % | 100 % (legacy rule kept as a complement) |

- In the Aug–Sep queue (1,876 alerts) the validation predicts ≈ 649 real frauds: 562 "Bloquer" (87 % measured), 1,314 "Vérifier".
- Demo cases (June, chosen automatically in NB 02 for their ground truth):
  - TX01555470, obvious fraud: 3 night-time web transfers in 4 h, 3 failed logins from an Italian IP, beneficiary added at 23:33 → BLOQUER.
  - TX01585580, subtle fraud: 7.685 TND online at 02:03 at a new merchant after 2 micro-purchases (card testing) → BLOQUER.
  - TX01575959, false positive avoided: 3,360.634 TND chip purchase in Tunis, daytime, retired customer; legacy alert, model bottom 0.01 % → VALIDER.
- Pitch line: "Half the alerts, 6× more frauds caught, 67 % fewer false alerts — and it holds on every period we tested."

## 3. Application & copilot (`app/`, Streamlit, FR/EN)
| # | Page / component | Status | Notes |
|---|---|---|---|
| 11 | Shell | ✅ | Hyson Detector brand + team logo, light bank theme, sidebar groups Bienvenue · Analyste · Enquête IA · Pilotage · Données, FR/EN switch, splash, welcome dialog, 3 demo-case buttons |
| 12 | Démarrer ici | ✅ | 4 headline KPIs, 8-step guided tour, hint on every page |
| 13 | File d'alertes | ✅ | Filters, risk colours, alerts/day; banner "une alerte n'est pas une fraude"; columns **Fraudes mesurées** (validation rate for that score) and **Action conseillée**; deep-search flags |
| 14 | Fiche transaction & copilote | ✅ | Score, measured fraud at this score, factors for/against (observed vs usual), recommendation, chat with suggested questions, decision + stopwatch, printable case file |
| 15 | Vue client 360 | ✅ | Habits **before the open alert** (same 409 ops / 189.305 TND as the copilot), timeline with digital events, map, "Rechercher un client par description" |
| 16 | Enquête approfondie | ✅ | Watch list of medium alerts (≈ 53 % fraud vs 16 %), evidence board E1…En (incl. 25 nearest labelled alerts), one-call AI synthesis |
| 17 | Le Procès | ✅ | AI prosecutor + defence (parallel) → judge; analyst accepts/overrides → decision log |
| 18 | Reconstitution | ✅ | Hours before the alert step by step, red signals, map, AI narration |
| 19 | Contre-enquête | ✅ | Neutralise top SHAP factors → robust / sensitive |
| 20 | Réseau de compromission (ex-Constellation) | ✅ | 29 points of compromise, 294 exposed alerts; shown as an investigation lead (not predictive in validation) |
| 21 | Impact & processus | ✅ | TND caught / flagged, workload (editable), process flow, recommendation mix, decision time, AI cost per alert, PSI drift |
| 22 | Marché & benchmarks | ✅ | 6 cited public benchmarks, Tunisia-scale scenario, rules-engine audit, time to detect |
| 23 | Performance du modèle | ✅ | Model vs rules, recall by type, drivers, leaderboard + **Robustesse et gouvernance** (backtest, CIs, MLflow, copilot evaluation) + **fairness** (false-alert rate by segment / age band: gap model 1.4× / 1.2× vs rules 2.8× / 1.5×) + acknowledged-limits card |
| 24 | Tableau de bord Power BI | ✅ | Secure embed (viewer signs in), page picker |
| 25 | Journal & traçabilité | ✅ | **Audit trail**: analyst identity (sidebar; production = Entra ID SSO), system recommendation + score at decision time, model / prompt version, SHA-256 hash chain + integrity check, override rate, `fraud_decision.v1` message to the bank's systems (simulated, four-eyes flag); copilot log (question, tools, tokens) |
| 26b | **Nazar · agent de travail** (`nazar.py`) | ✅ | Sidebar card (our evil-eye icon, live count to block / to dig / overrides) → dialog with quick buttons + one instruction field. Rule-based parser, **0 token**: briefing, next most urgent alert, top N of a day / risk / action, open any page on a TX, customer ID, person search, journal check, KPIs, FR/EN. Decisions are **prepared** (recommendation, measured fraud rate, override warning) and saved only after the analyst confirms (source `agent_nazar`, hash chain). Questions on the open alert → copilot. **Conversation mode**: small talk offline (0 token); other messages → Azure OpenAI with Nazar's persona, aggregates only, no tools, never records, suggests commands as chips. Log `agent_log.jsonl` (with tokens), shown on the Journal page |
| 26 | Nouvelle source de données | ✅ | Profile → map/translate (rules, optional 1 AI call on names + stats) → accuracy + PSI → **human approval** → versioned data contract |
| 27 | 10 tools (`tools.py`) | ✅ | get_alert_queue · get_transaction (+ measured fraud at this score, alerts in the period) · get_customer_profile · compare_to_habits (+ decline reason, 24 h card sequence) · get_customer_history · get_digital_events · find_related_cases · get_kpis (comparison in plain words) · find_customers · record_decision |
| 28 | Copilot engine (`copilot.py`) | ✅ | Intent routing (incl. priority, person / customer ID / typed TX ID), prefetch → 1 LLM round, streaming, deterministic `recommandation_systeme`, demo calendar ("hier" = 2026-09-29), guardrails: off-topic refusal, unknown ID answered with 0 token, Azure content-filter refusal, no field names; cache, log, offline mode, hourly cap |
| 29 | Azure OpenAI (Azure AI Foundry) | ✅ | Project `proj-fraud-australiaeast`, resource `aoai-fraud-australiaeast-vnxcy`, deployment **gpt-5-mini**, API 2024-12-01-preview, `reasoning_effort=low`, `max_completion_tokens` 2,400, timeout 60 s, 2 retries; ≈ 3,300 tokens (≈ 1,400–2,000 prompt-cached) and ≈ 7 s per new question |
| 30 | Evaluation & cache | ✅ | `eval_copilot.py`: 18/18 (live re-run 10:15), 99.4 % grounded (`docs/COPILOT_EVAL.md`); `tests/` 94 tests + GitHub Actions; `warmup.py fr en`: 40 answers + 6 trials pre-computed |
| 31 | Traceability | ✅ | `copilot_log.jsonl`, `agent_log.jsonl` (Nazar), `decisions.csv` (hash-chained, → OneLake), `onboarding_log.csv` · `docs/AUDIT_AND_BANK_INTEGRATION.md` |
| 32 | GitHub + Streamlit Cloud | ✅ | Repo owned by the team account; push to `main` redeploys; snapshot fits the 690 MB limit (peak ≈ 520 MB) — after a crash use **Reboot** |
| 33 | Architecture & docs | ✅ | 18 diagrams (images + Mermaid source in `docs/diagrams/`), README, JURY_HANDBOOK, `fabric/README.md` |
| 34 | GitHub Copilot usage evidence | ✅ | `docs/AI_TOOLS_USAGE.md` §1: 12 real uses (when, where, ask, result, team decision, time-saved estimate, commit + screenshot); pitch script; handbook §8 aligned |
| 35 | Slides | ❌ | Problem, live demo, architecture (`docs/img/`), results, robustness, prototype → production, limits |
| 36 | Pitch 5 min × 3 rehearsals + backup video | ❌ | Brief §10, §17 |

## 4. Decision log
- Time split, never random; valid = last 2 labelled months (brief §8.3).
- No gender, IDs, `fraud_scenario`, `fraud_reported_date` (except "already reported" network features) or legacy decisions as features (brief §8.6).
- Target-encoded entity risk dropped (not point-in-time).
- Train = all frauds + 10 % of legitimate transactions (weight 10); valid/test kept complete.
- Champion = LightGBM when within 1 pt of the best top-1 % recall, so one model both scores and explains.
- Alert budget = 1 % per period (analyst capacity; = the brief's ~1,000 alerts on its 101,730 test rows).
- **ML for the score, DL (LLM) only for language**: gradient boosting is the reference on tabular data and auditable; deep-learning scoring models are roadmap challengers (sequence model, GNN, autoencoder) to validate with the same backtest.
- The model scores, the LLM explains only from tool facts, a documented rule recommends, the analyst decides. Offline deterministic mode if the LLM is unavailable.
- The pipeline is **frozen** for the pitch: robustness, MLflow and evaluation were added without re-scoring.
- Streamlit = analyst tool + copilot (Fabric live = brief §11 option A; snapshot for the hosted demo = option B); Power BI = manager KPIs (complement).
- Out of scope (no data): AML flows, first-party / internal fraud.
- Dataset differs from the brief (3,500 customers, 2025-01 → 2026-09, 1.9 M tx); the current engine measured on our validation period = 3.5 % precision / 11.5 % recall.

## 5. Next actions (checked 2026-11-06 03:00)
**Blocking for the pitch — only the team can do these:**
1. 🔴 **Azure OpenAI key in Streamlit Cloud** — still "Copilote : Hors-ligne (règles)" on the public app (checked 03:00). share.streamlit.io → app ⋮ → Settings → Secrets → paste `app/.streamlit/secrets.toml.example` with the real key from `app/.env` → Save.
2. 🔴 **Slides** (problem, live demo, architecture images, results + robustness, prototype → production, limits).
3. 🔴 **Rehearse 3× (5 min) + record a backup video** of the demo path (§7.4.4).
4. ✅ ~~Fill the GitHub Copilot usage table~~ — done 04:10 (12 rows, commits + 10 screenshots); adjust the time-saved estimates if the team sees them differently.
5. ✅ ~~Archive `saitaflex/hyson-detector`~~ — archived 04:05, description and homepage point to `hack-australiaeast-01/hyson-detector`.
6. 🟡 Fabric clean-up — notebooks 03/03b/03c/03d are gone; semantic model `Saitaflex-model` still present (checked 04:00).
7. 🟡 Decide whether the personal e-mail in the public Git history is acceptable.
8. 🟡 After the pitch only: publish an Environment from `fabric/environment.yml`, then schedule `pl_hyson_retrain` (re-scoring changes the demo IDs).

**Demo day checklist:**
- Open https://hyson-detector.streamlit.app 5 min before (free apps sleep; first load ≈ 20 s). If it shows "over its resource limits": share.streamlit.io → ⋮ → **Reboot**.
- **After any push, Reboot the public app** (share.streamlit.io → ⋮ → Reboot): Streamlit Cloud re-runs `app.py` but keeps already-imported page modules (`studio.py`…) in memory, so new page designs only appear after a reboot (seen 04:10: new sidebar label, old Constellation page).
- Pitch laptop: `az login` → `cd app` → `streamlit run app.py` (sidebar shows Fabric live) → run the demo path once.
- Do not click "Rafraîchir depuis Fabric" during the pitch (≈ 15 s reload). Do not run notebooks 01/02 or the pipeline.
- Keep one Aug–Sep alert ready besides the 3 June demo cases (e.g. TX01890379, declined for limit exceeded).
- Projector at 1366×768: set the browser zoom to **80 %** so the transaction page (score → factors → recommendation → *Enregistrer la décision*) fits without scrolling (brief §10). At 1920×1080 it fits at 100 % (checked 10:00).
- After any change to the copilot prompt or tools: bump `CACHE_VERSION`, run `python warmup.py fr en` then `python eval_copilot.py` (must be 18/18) and commit `app/data/copilot_cache.json` — the public app serves these answers.
- For "même commerçant ou DAB ?" use **TX01589761** (ATM skimming: same ATM M02076, 4 other customers, 3 cards already reported) — most alerts have no shared point.

## 6. Known limits (say them before the jury does)
- ≈ 62 % of alerts have no business-rule factor → their explanation rests on model factors; the "concordant signals" of the recommendation count strong model factors (precision of each band is measured and shown).
- Demo cases are June (validation) cases chosen for their ground truth; keep an Aug–Sep alert ready.
- Champion picked among 4 models on the same validation period that is reported (they are within ~1 pt; test labels are with the jury) — mitigated by the 4-period backtest (69.4 % ± 2.1).
- gpt-5-mini has no temperature setting (brief §9.8 asks 0–0.2): stability comes from the deterministic recommendation rule + low reasoning effort.
- Online, "related cases" only see the 1,814 alert customers (answer says "extrait local"); live Fabric sees the whole bank.
- Batch scoring, not at authorisation time.
- The 3D Nazar robot loads three.js from a CDN (jsdelivr, pinned 0.160.0): with no internet at the venue the robot does not appear; Nazar's text side still works.
- Voice uses the browser's speech services (Chrome / Edge cloud recognition and online voices); production would use Azure AI Speech in the bank's tenant.
- The fraud score is classical ML; deep learning is used only through the LLM (no DL scoring model yet).
- Data onboarding stops at the approved data contract: OneLake → Bronze → re-scoring is documented, not run live.
- The retraining pipeline exists but has never run (frozen demo); the Environment is pinned in a file, not published.
- Fairness: alert rates are even (0.9–1.1 %), but retirees / 60+ get lower precision (30–35 %) and recall (61–66 %) — shown, to monitor.
- The Power BI page needs an Entra ID account of the tenant: a jury member without access sees a sign-in screen (the app pages carry the same KPIs).
- Explanations of alerts without a business rule stay model-driven (e.g. TX01890379 still lists model factors before its decline reason).
- Audit / bank IT: the analyst name is typed (no SSO yet), the four-eyes rule is only flagged (no supervisor approval queue), the decision message to card management / core banking is generated but **not sent**, the journal is a hash-chained CSV mirrored to OneLake (production: WORM storage + SIEM). See `docs/AUDIT_AND_BANK_INTEGRATION.md`.

## 7. Work log (dated history — figures as of that time; current state = §1–§6)

### 7.1 Fabric pipeline and first app (2026-11-05 afternoon)
> State at 2026-11-05 ~18:00. Since then: pushed to GitHub, notebooks replaced by the Fabric exports, 10 tools, 15 pages, ≈ 3,300 tokens per question.

#### 7.1.1 Data pipeline in Fabric (notebooks 01 and 02)
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

#### 7.1.2 Analyst application (`app/`)
| File | Content |
|---|---|
| `app.py` | Streamlit, 5 pages: alert queue (filters, risk colours, alerts/day, click-to-open), transaction card (score, risk and reassuring factors with observed vs usual, decision form, chat with 6 suggested questions), customer 360 (profile, habits, timeline incl. digital events, map with the alert highlighted), performance (model vs engine, recall per type, drivers, leaderboard), journal (decisions + copilot log). Sidebar: demo buttons, data source, copilot mode, token counter, "Rafraîchir depuis Fabric" |
| `data_access.py` | Source layer. **Fabric live**: pyodbc + ODBC Driver 17, Entra token (`AzureCliCredential`, else browser) on `lh_fraud` SQL endpoint; small Gold tables loaded once; customer history / digital events / related cases queried with server-side filters; decisions uploaded to OneLake `Files/app_feedback/decisions.csv`. **Fallback**: parquet in `app/data` (refreshed on each live load). Test labels nulled; `gender` dropped |
| `tools.py` | 9 tools returning compact JSON: `get_alert_queue`, `get_transaction`, `get_customer_profile` (habits optionally before a transaction), `compare_to_habits` (past only: ratio, p95, countries, city/merchant/device/beneficiary seen and seen > 24 h, night share, previous op, 24 h activity, card bursts, distance and implied speed), `get_customer_history`, `get_digital_events` (≥ 24 h window), `find_related_cases` (bank-wide, counts only frauds **reported before** the transaction), `get_kpis`, `record_decision` |
| `copilot.py` | Azure OpenAI function calling (≤ 4 tool rounds), brief §9.3 prompt + explicit decision rule, 5-part format, open transaction pre-injected, tool output capped (3,500 chars), disk cache (`copilot_cache.json`), log of every call (`copilot_log.jsonl`), deterministic offline mode (also used if the LLM fails), `COPILOT_OFFLINE=1` switch |
| `warmup.py` | Pre-computes 20 answers (6 questions × 3 demo cases + 2 global) |
| `test_aoai.py` | Connectivity check |
| `requirements.txt`, `.env.example` | Dependencies; config template (no secrets) |

#### 7.1.3 Azure OpenAI
- Found with `az cognitiveservices`: resource `aoai-fraud-australiaeast-vnxcy`, only deployment **gpt-5-mini** (GlobalStandard, 70k TPM).
- `.env` written locally from `az ... keys list` (git-ignored, key never printed); `test_aoai.py` → "OK copilote".
- gpt-5-mini is a reasoning model: rejects temperature/max_tokens → code uses `max_completion_tokens` + `reasoning_effort=low`.
- Prompt iterations from live tests: no invented IDs, always compare to habits, call digital events for web/transfers, recent device/beneficiary (< 24 h) is not reassuring, BLOQUER/ESCALADER/VALIDER rule, French level names, no recommendation on KPI questions.
- Measured: ~5,200 tokens and ~12 s per uncached question (was ~7,500 / 16 s before pre-injection); unknown ID handled.

#### 7.1.4 Verification done
- All 5 pages rendered headless (`streamlit.testing.AppTest`) on local data and on live Fabric: no exception.
- Decision written via the UI → `decisions.csv` → mirrored in OneLake (read back, then deleted).
- Live answers on the demo cases: TX01555470 BLOQUER (3 failed logins from IT IP, beneficiary added 23:33, 814 TND = 4.3× usual) · TX01585580 BLOQUER · TX01575959 VALIDER (chip, Tunis, daytime, 936 past ops all in TN).
- Server health check `http://localhost:8501/_stcore/health` → ok.

#### 7.1.5 Repository and docs
- Deleted 6 outdated docs (they wrongly called the split bug a data leak).
- `README.md`: architecture, results, run steps, live Fabric mode, token discipline.
- `.gitignore`: `.env`, `app/data/`, parquet, zip, test/, third-party McKinsey files.
- Local git: `3ae7d57` (initial app + notebooks), `2404a7d` (live Fabric). Not pushed. Left uncommitted on purpose (other session): `COPILOT_HANDOFF.md` edits, `notebooks/03c_powerbi_dashboard.ipynb`.
- `notebooks/` holds older local copies: replace them with the final Fabric versions (Fabric Git integration or download) before pushing.

#### 7.1.6 How to run (demo day)
```powershell
az login                                  # Fabric + Azure OpenAI access
cd C:\Users\oussa\Desktop\dsi\app
python warmup.py                          # optional: instant answers for the demo questions
streamlit run app.py                      # http://localhost:8501 — sidebar must show "🟢 Fabric live"
```
Demo path: sidebar "Fraude évidente" → ask "Pourquoi … suspecte ?" → BLOQUER → "Faux positif évité" → "Pourquoi … pas une fraude ?" → VALIDER → Performance page.

### 7.2 First review findings (2026-11-05 evening)
> All six findings were fixed the same evening; token figures were then reduced further by copilot v4 (§7.3).

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

### 7.3 Copilot v4 — Azure OpenAI improvements (2026-11-05 evening)
#### 7.3.1 What was wrong (found in the real log `copilot_log_before_v3.jsonl` and the cached answers)
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

#### 7.3.2 How the copilot works now (`app/copilot.py`)
1. `detect_intent()` (FR + EN keywords): analyse · habits · before · related · summary · kpi · queue · general.
2. `_prefetch()` calls the needed tools in Python (e.g. analyse = transaction + habits + digital events for MOBILE/WEB/VIREMENT) and gives them to the LLM as **FAITS**; the LLM can still call any of the 9 tools for missing facts (≤ 4 rounds).
3. Static system prompt first (eligible for Azure prompt caching), then a dynamic message (language, intent, open transaction, facts), last 2 exchanges, question.
4. Streaming (`stream=True`, usage included): tokens shown as written, tool steps shown live; all calls logged with intent, language, tokens (incl. cached), rounds, latency.
5. Decision = `recommandation_systeme` (documented rule + measured validation precision); the LLM explains it and may flag a contradicting fact without changing it.

#### 7.3.3 Decision rule (`tools.recommend`, measured on Jun–Jul 2026 validation alerts)
| Condition | Decision | Confidence | Validation precision | Alerts (valid + test) |
|---|---|---|---|---|
| percentile ≥ 0.998 and ≥ 2 concordant signals | BLOQUER | élevée | 94 % | 734 |
| ELEVE and ≥ 2 signals | BLOQUER | moyenne | 87 % | 361 |
| ELEVE otherwise, or MOYEN | ESCALADER | moyenne | 20 % (MOYEN) | 2,560 |
| FAIBLE | VALIDER | élevée, or moyenne if a business rule still alerted | — | 1 (demo) |

#### 7.3.4 Results
| | Before | After (v4) |
|---|---|---|
| Tokens per new question | ~5,200 (top 10: 10,410) | **~3,300**, of which ~1,400 served from Azure prompt cache |
| LLM rounds | 2–3 | **1** |
| Latency | 12–15 s, spinner | **~7 s**, text streams after ~3–8 s; cached demo answers instant |
| Recommendation consistency (3 demo cases × 6 questions × 2 languages) | 4/6 on the subtle fraud | **100 %** |
| Languages | FR (EN mixed) | FR + EN |
| Pre-computed answers | 20 (FR) | **40 (FR + EN)** — `python warmup.py fr en` |

Verified: 12 page renders (6 pages × FR/EN) without exception on live Fabric; FR chat (suggestion from cache 0.2 s, new question 8.5 s / 3,028 tokens with 2,432 cached); off-topic question refused in one sentence; unknown ID handled. Note: Streamlit `AppTest` cannot replay the EN decision radio (translated `format_func` labels) — harness limitation, not an app error.

### 7.4 Hyson Detector — showcase features for bank judges (2026-11-06)
Goal: go beyond "a chat on top of a model" and speak the bank's language (KPIs, process, governance), with a friendly first-time experience.

#### 7.4.1 What was added
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

#### 7.4.2 Corrections made on the way
- Legacy engine catches **117** frauds (exact recount from `silver_transactions`), not 116; `get_kpis` now uses `features.impact()` → 3,221 false alerts. Cached KPI answers regenerated (no more "3,222").
- Plotly log funnel rendered "NaN×10^Infinity" → replaced by step cards (`ui.flow`).
- Metric deltas with a unicode minus were shown red/up → ASCII "-".
- Judge pasted raw JSON / wrote "BLOQUER" in English mode → plain-text recommendation + language rule (cache key `proces-p2`).

#### 7.4.3 Verification
- AppTest: 24 renders (12 pages × FR/EN), 0 exceptions; interactions (hearing, accept verdict, replay, narrate, contre verdicts, stopwatch, dossier, tour, welcome dialog) OK.
- Playwright (Edge) screenshots of every new page checked visually.
- `python warmup.py fr en`: 40 copilot answers + 6 trials cached → demo is instant.

#### 7.4.4 Demo path (≈ 3 min)
Démarrer ici → Fraude évidente TX01555470 → ask "Pourquoi suspecte ?" → Le Procès → Reconstitution → decide (< 30 s on the stopwatch) → Faux positif évité TX01575959 → Contre-enquête (robust clearance) → Constellation → Impact & processus.

### 7.5 Marché & benchmarks — the "killing blow" page (2026-11-06)
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

### 7.6 Fraud-number audit (2026-11-06) — Fabric = source of truth
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

### 7.7 Judge review, deployment and polish (2026-11-05 22:30 → 2026-11-06 01:00)
#### 7.7.1 Delivery
| Item | Result |
|---|---|
| GitHub | Public repo **https://github.com/hack-australiaeast-01/hyson-detector** (created with the team account so it is owner/admin; first push went to `saitaflex/hyson-detector`, now archived and pointing here). Notebooks = Fabric exports with outputs; `submission/submission.csv`; secret scan of files + history clean |
| Streamlit Cloud | **https://hyson-detector.streamlit.app**, main file `app/app.py`, Python 3.12, redeploys on every push. Reads the committed Gold snapshot (no Entra login in the cloud). Secrets bridge accepts keys at root or under a `[section]`; `secrets.toml.example` provided |
| Architecture | `docs/ARCHITECTURE.md` (rewritten 2026-11-06 02:40): **18 diagrams** — end-to-end, Fabric platform, ML pipeline, MLOps lifecycle + NB 04, Azure AI Foundry / OpenAI layer, ML vs DL map (+ DL roadmap), 8 AI pipelines one by one, app pages, demo path, deployment & security — shown as images (`docs/img/`), editable Mermaid source in `docs/diagrams/` (5 pages ≤ 4 diagrams: GitHub stops rendering after ~7 per page), `python docs/diagrams/render.py` regenerates the images; linked from README and JURY_HANDBOOK §7 |
| AI tools declaration | `docs/AI_TOOLS_USAGE.md`: development assistant = **GitHub Copilot agent mode (VS Code)** only; Azure OpenAI = in-product copilot |
| Logo | Team PNG logo (cropped, white + blue variants, favicon) in sidebar, splash, welcome dialog, "Démarrer ici", printable case file, README (`app/static/brand/`) |
| New page (other session) | **Enquête approfondie** (`app/deepsearch.py`): watch list of medium alerts whose customer already had an alert (≈ 53 % fraud vs 16 % for other medium alerts, validation), evidence board E1…En, one-call AI synthesis (cached) |

#### 7.7.2 "Hostile judge" review — findings and fixes
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

#### 7.7.2b Streamlit Cloud memory limit (2026-11-06 01:30)
- **Symptom:** public app showed "This app has gone over its resource limits" after the full-history snapshot (J1) was added.
- **Cause:** history + events loaded as plain strings = ~600 MB, peak 856 MB with one user (Community Cloud floor: 690 MB).
- **Fix (`data_access.py`, snapshot files):** text columns stored and loaded as categories, coordinates float32, unused `session_id` dropped, Arrow buffers freed on load (`self_destruct` + `release_unused`), per-customer caches 96/128 entries. Data in memory 334 MB → ~80 MB.
- **Measured** (real Streamlit server in cloud mode, 15 pages + 3 demo cases, 3 sessions): peak **520 MB**, 0 exceptions; same figures as live Fabric. After a crash the app needs a manual **Reboot** (share.streamlit.io → ⋮ → Reboot): it does not restart on push.

#### 7.7.3 Verification
- AppTest: 28 renders (14 pages × FR/EN) with no exception in **cloud mode** (no `.env`, no Fabric) and key pages in **live Fabric** mode.
- Public app checked with Playwright after each push: snapshot label, no error banner, full history in Client 360, new queue columns, logo.
- Live copilot re-tested on §9.7 questions (yesterday's top 10, why suspicious on a random Aug–Sep alert, why not fraud, unknown ID, off-topic).

### 7.8 Ask about a person + new data source onboarding (2026-11-06)
#### 7.8.1 "Ask the AI about someone in the tables" (`app/person_search.py`, `copilot.py`, `tools.py`)
- **Gap found:** the copilot always answered about the transaction open on screen; an ID or a person typed in the question was ignored.
- **Now:** (1) a `TX…` ID in the question overrides the open transaction; (2) a `C…` customer ID → profile + 30-day history; (3) a description ("le client retraité de Sfax de plus de 70 ans avec des alertes", "doctor customers from Tunis aged between 30 and 40") → approved filters (city, segment, occupation, age, KYC, digital, with alerts) → new read-only tool `find_customers` → short list with alert counts and the riskiest alert. 0 tokens offline; with Azure OpenAI the facts are prefetched and the LLM is told not to issue BLOCK/VALIDATE for a person search.
- **UI:** "Rechercher un client par description" box on Vue client 360; "Ouvrir" jumps to the customer on their riskiest alert.
- **Tested:** 7 questions FR/EN offline (no paid call); unknown ID → "introuvable"; AppTest search + open.
- **Routing guard (review fix):** questions about the open case ("ce client…", "le client a-t-il…", "même commerçant", "other customers", "this transaction") are never treated as a person search — the demo button "D'autres clients sont-ils passés par le même commerçant…" was being routed to a list of *commerçant* customers. 15 routing cases checked (demo buttons, §9.7 questions, descriptions, IDs).
- **Jury answer — why not free SQL:** security (no injection, only approved tables), reliability (the LLM only states what tools return, §9.1), cost (aggregates, not tables), traceability (every call logged). On a real bank database the same filters run as parameterised queries with personal data masked.

#### 7.8.2 New data source onboarding (`app/onboarding.py`, page "Nouvelle source de données", group Données)
1. Load a CSV (or the synthetic `app/samples/partner_bank_sample.csv`: English columns, POS/ATM/ECOM codes, EUR + TND, ISO3 countries, dd/mm/yyyy).
2. Profile (types, empty cells, distinct values; identifiers masked).
3. Proposed mapping to our schema with a confidence per field (rules: name similarity 60 % + value fit 40 %, 0 tokens), editable; optional "Affiner avec l'IA" = 1 Azure OpenAI call on column names + statistics only (logged with tokens). Codes, countries, dates and currencies are translated (rates editable, indicative).
4. Accuracy: required-field coverage, % valid translated values, untranslated values listed, row/total reconciliation, drift vs our data (PSI channel mix + amount bands, reference = live Fabric query, snapshot `feat_onboard_ref`), fraud rate if labels exist. Verdict Prêt / À revoir / Bloqué (≥ 95 % valid, PSI < 0.2, all required fields).
5. **Human approval required** (name + checkbox; disabled when Bloqué) → versioned data contract (`data/staging/<source>_<version>/data_contract.json`) + translated parquet + `data/onboarding_log.csv` (approved / rejected, by whom). Next step (documented, not live): drop to OneLake → bronze → silver via the Fabric pipeline, then rescoring in notebook 02 before production.
- **Tested:** sample → 12/12 columns mapped, 100 % valid, PSI 0.10, verdict Prêt, approval writes contract + log (test artefacts deleted afterwards); a broken file (no channel, unknown codes) → Bloqué, approval disabled. AppTest FR + EN, no exception.

**Restart the app** (Ctrl+C, `streamlit run app.py`): new modules are only loaded at start. Onboarding outputs (`data/staging/`, `data/onboarding_log.csv`) are git-ignored.

### 7.9 Robustness, MLflow, pipeline and copilot evaluation (2026-11-06 01:35 → 02:15)
Goal: prove the result is not a lucky period and that the solution is industrialisable, **without touching the frozen pipeline** (no re-run of 01/02, demo IDs unchanged).

| Item | What | Result |
|---|---|---|
| Notebook **04_robustness** (Fabric job, 10 min, Completed) | Same features, sample (all frauds + 10 % legit, seed 42), category dictionaries and LightGBM settings as notebook 02; re-trained 4 times on the past only; tests of 2 months: Dec–Jan, Feb–Mar, Apr–May, Jun–Jul | Top-1 % recall 66.7 / 68.8 / 71.2 / 70.9 % → **69.4 % ± 2.1**; precision 39.1 % ± 3.9; PR-AUC 0.622 ± 0.036; fraud value caught 72.5 %; rules 12.6 % / 3.7 % on the same periods |
| Confidence intervals | Day-block bootstrap (1,000 resamples of whole days) on the production validation scores | Recall 70.9 % [68.3–73.0] · precision 40.4 % [34.9–45.0] · PR-AUC 0.646 [0.610–0.675] · recall gain +59.3 pts [56.2–62.0] · false alerts avoided 2,160 [1,971–2,335] |
| Agreement check | Fold-4 model vs `gold_scores` (valid) | Rank correlation **1.0**, same top 1 %, max difference **0** → the registered model *is* the production model |
| MLflow | Experiment `hyson-fraud-robustness` (1 run per fold + `production-lightgbm`), registered ML model **`hyson-fraud-lightgbm`** v1 with `features.json` and `model_card.md` | Visible in the workspace (MLModel item) |
| Tables | `gold_model_robustness`, `gold_model_robustness_types`, `gold_model_ci`; `Files/robustness/summary.json`, `runtime_versions.json` | App snapshots `feat_robustness.parquet`, `feat_model_ci.parquet` |
| Data pipeline | **`pl_hyson_retrain`**: 01 → 02 → (03e ∥ 04), retry 1; definition in `fabric/pl_hyson_retrain.json` | Created, **0 runs, not scheduled** (re-scoring changes demo IDs) |
| Environment | `fabric/environment.yml`: versions of the runtime that produced the scores (Python 3.13.11, LightGBM 4.6.0, scikit-learn 1.6.1, MLflow 2.22.0…) | To attach when an Environment item is created (not published tonight) |
| Copilot evaluation | `app/eval_copilot.py`: 14 golden questions (3 demo cases FR, EN, "pas une fraude", "juste avant", résumé, a random Aug–Sep alert, yesterday's top 10, KPI, person search, unknown ID, off-topic, prompt injection); 0-token checks: decision = system recommendation, key facts, ≥ 90 % numbers found in tool outputs, 5 sections, English-only, refusals | **14/14 pass, 99.3 % of the cited numbers grounded** → `docs/COPILOT_EVAL.md`, `app/data/copilot_eval.json` |
| App | "Performance du modèle" → new section **Robustesse et gouvernance** (4 KPIs, per-period table, CI table, copilot evaluation line, method) | AppTest FR + EN, no exception |

**Copilot fixes found by the evaluation:**
- Unknown ID typed in the question (`TX99999999`) produced a 5-section "analysis" ending with ESCALADER → now a **0-token guardrail answer** "introuvable … ni analyse ni décision".
- Prompt-injection question was blocked by the Azure OpenAI content filter but shown as "Azure OpenAI indisponible" → now a **clear refusal** (mode "garde-fou (filtre Azure OpenAI)", logged, not cached).
- KPI answer did arithmetic itself (2,160 = 3,221 − 1,061; 67.1 %) → `get_kpis` now returns `comparaison_top_1pct_vs_moteur` (false alerts avoided, reduction, extra frauds, fewer alerts, ×6.1) so every number is cited from a tool.

Also: `.env.example` documents every setting the app reads (`COPILOT_HOURLY_CAP`, `COPILOT_OFFLINE`, `COPILOT_TIMEOUT`, `COPILOT_REASONING`, `DEEP_REASONING`, `ODBC_DRIVER`).

**Pitch line (15 s):** "We froze the model and invested in proof: four periods, ±2 points; confidence intervals; the exact production model registered in MLflow; a retraining pipeline in Fabric; and a copilot evaluated on 14 reference questions where 99 % of the numbers it cites come from the data."

### 7.10 Architecture rewrite and STATUS clean-up (2026-11-06 02:20 → 03:00)
- `docs/ARCHITECTURE.md` rewritten: **18 diagrams** — end-to-end, Fabric platform (every table), ML pipeline (NB 01/02), MLOps lifecycle + NB 04, Azure AI Foundry / Azure OpenAI layer, where ML and DL are used (+ DL roadmap), the 8 AI pipelines one by one, app pages, demo path, deployment & security; each with a method table.
- GitHub stops rendering Mermaid after ~7 diagrams per page → `ARCHITECTURE.md` shows images (`docs/img/`, also for slides); editable Mermaid source split into `docs/diagrams/` (5 pages ≤ 4 diagrams, all render); `python docs/diagrams/render.py` regenerates the images. Checked on GitHub: 18/18 images, 18/18 diagrams.
- STATUS restructured: current state (§0–§6) separated from the dated work log (§7); obsolete Fabric export cell removed (replaced by the full snapshot, §7.7); open items re-checked against Fabric, GitHub and the public app.

### 7.11 Gap check (2026-11-06 03:00 → 03:45)
Checked: links in all Markdown files (0 broken) · fresh clone of the public repo, every page FR/EN without `.env` or Fabric (0 exception) · submission format (187,628 unique rows, header, scores in [0, 1], 1,876 alerts = queue) · the brief's §9.7 questions word for word · fairness by segment / age · repo hygiene (§13, §16).

| Gap found | Fix |
|---|---|
| "Résume pourquoi cette alerte doit être priorisée" answered with a generic 5-section analysis | New intent **priority**: 4 figures (rank / alerts in the period, measured fraud at this score, strongest signals, exposure) + recommendation, ≤ 120 words; `get_transaction` returns `fraudes_mesurees_a_ce_score` and `nb_alertes_periode` |
| "Même commerçant ou DAB ?" weak on most alerts (no shared point) | Demo case **TX01589761** (ATM M02076: 4 other customers, 3 already-reported frauds) in the checklist and the golden set |
| Golden evaluation did not use the brief's exact wording for 4 questions | +4 cases (habits, priority, "juste avant ce virement", same ATM) → **18/18**, 99.5 % grounded |
| No fairness analysis (banks ask) | `features.fairness()` (Fabric SQL, snapshot `feat_fairness.parquet`) → table on Performance → Robustesse et gouvernance; `docs/MODEL_CARD.md` |
| No model card in the repo | `docs/MODEL_CARD.md` (purpose, data, features, exclusions, performance + CIs, backtest, fairness, limits, monitoring) |
| No automated tests / CI (brief §13 cites tests) | `tests/` (44 tests, offline) + `.github/workflows/tests.yml` + `pytest.ini`; found that "plus de 70 ans" is parsed as 71+ (documented in the test) |
| No `requirements.txt` at the root | `requirements.txt` → `-r app/requirements.txt` |
| Docs said 9 tools, README missed 2 pages, eval figures 14/14 | README (15 pages, Tests section, badge, model card), JURY_HANDBOOK (10 tools, fairness + tests Q&A), AI_TOOLS_USAGE, diagrams 07a/07g re-rendered |

Still open (team): Azure key in Streamlit Secrets, slides, rehearsal + backup video, GitHub Copilot usage table, archive `saitaflex/hyson-detector`, Fabric clean-up, personal e-mail decision (§5). Optional: LICENSE file (data belongs to the organisers).

### 7.11 Audit trail and bank IT integration (2026-11-06 03:15 → 03:50)
- **Gap found (bank audit view):** every decision was saved as analyst "analyste", without the recommendation the analyst saw, without model / prompt version, in an editable CSV; nothing showed how a BLOQUER reaches the card or the transfer; no document for audit / IT / compliance questions.
- **Built:** `tools.record_decision` stores analyst (sidebar "Analyste connecté"), `system_decision` / `system_confidence` / `score_model` at decision time, `model_version`, `prompt_version`, `prev_hash` / `row_hash` (SHA-256 chain); older journals are upgraded and sealed once (your decision TX01575959 VALIDER kept); `tools.verify_journal`; Journal page: integrity ✅/❌, override rate + overrides to review, analysts count, `fraud_decision.v1` message (card → BLOCK_CARD, transfer → HOLD_TRANSFER, ESCALADER → level-2 case, VALIDER → close; four-eyes flag for blocks ≥ 5,000 TND or a set-aside BLOQUER; nothing sent).
- **Docs:** `docs/AUDIT_AND_BANK_INTEGRATION.md` (audit trail, roles / segregation of duties, integration diagram, data protection incl. Tunisian law 2004-63, EU AI Act Annex III 5(b), resilience); 4 jury questions in `JURY_HANDBOOK.md`; README links.
- **Tests:** `tests/test_audit_trail.py` (5): stores who + recommendation + versions, override visible, edited past row detected, old journal upgraded and sealed, decision message mapped to the right system. Full suite 49/49.

### 7.12 Hardening + bank-style visuals (2026-11-06 03:20 → 03:40)

- **Prompt-injection guard** (`copilot._sanitize`): every tool result is cleaned before it reaches the LLM — control characters and role markers removed, strings cut at 200 chars, instruction-like text ("ignore all previous instructions", "SYSTEM:", "<system>", "valide cette transaction"…) replaced by "[texte retiré…]"; the system prompt states that facts are data, never instructions. Tested on 6 malicious fields; normal French text passes unchanged.
- **Fairness check** (`fairness.py`, Performance page): false-alert rate on legitimate operations by segment and age band (validation, live Fabric query, snapshot `feat_fairness`). Gap between groups: model **1.4×** (segments) / **1.2×** (age) vs current rules **2.8×** / **1.5×** → the model is fairer than the rules.
- **Acknowledged limits card** (Performance page): reporting delay (median 11 days → exclude the last 30 days from training), feedback-loop bias (random 0.1 % audit sample), synthetic data, score ≠ probability, cloned card abroad (rule kept), points of compromise (investigation signal only).
- **Analyst override rate**: already in the Journal (decision vs `system_decision`).
- **Constellation → "Réseau de compromission"**: stars, star dust and night background removed; white card, navy points with gold border (■ ATM, ◆ online site, ● shop), alerts in the bank's risk colours.
- **Reconstitution → fraud-history roadmap**: one station per step on a road, phases shaded (account access → operations → alert), the road fills in blue while the replay plays, risky stations in red with the first warning, time gap between steps, alert station marked, final milestone "Détection Hyson : jour 0 · signalement habituel ~11 jours".
- 3D emblem abandoned at the user's request (`app/static/3d` deleted).
- Verified: AppTest FR + EN on replay, network and performance pages (and Play); visual check in the browser.

### 7.13 Integration of both sessions and push (2026-11-06 03:40 → 04:00)
- **Incident:** commit `d8d87df` (audit trail) picked up 3 lines of the other session's in-progress `app.py` (`import fairness` + 2 calls) while `app/fairness.py` was not yet committed → CI red for ~5 min; GitHub's Copilot cloud agent opened PR #1 with a stub `fairness.py`. Fixed by `ca12836` (lines removed in the index only, working copy untouched, 49/49 on the exact tree), then this push commits the real `fairness.py`; PR #1 closed as superseded.
- **Conflict resolved:** the old fairness table (`features.fairness()`, alert rate / precision / recall) and the new `fairness.py` (false-alert rate model vs rules) wrote the **same snapshot** `feat_fairness.parquet` with different columns → the old block would crash the Performance page online. Old block and `features.fairness()` removed; `fairness.py` kept (its snapshot committed).
- **Pushed together:** prompt-injection guard (`copilot._sanitize`), fairness + limits cards, "Réseau de compromission" and the Reconstitution roadmap (§7.12), 3D emblem removed; data files only rewritten by the live app (identical content) left out.
- **Checks:** full suite on the exact tree pushed (offline snapshot, as CI and Streamlit Cloud), GitHub Actions green, public app checked after redeploy.

### 7.14 GitHub Copilot usage evidence and old repo archived (2026-11-06 04:00 → 04:10)
- `docs/AI_TOOLS_USAGE.md` §1 filled from the real history: 12 uses (pipeline audit and split bug, live Fabric, copilot v4, showcase pages, 03e as a Fabric job, deployment, hostile-judge review, memory fix, person search + onboarding, robustness + tests, audit trail, Git), each with the request, result, team decision, time-saved estimate and commit; 10 screenshots in `docs/copilot_evidence/` (before / after where it matters); 30-second pitch script. Handbook §8 aligned.
- `saitaflex/hyson-detector` archived (read-only), description + homepage → `hack-australiaeast-01/hyson-detector`; GitHub CLI switched back to the team account.
- Local app on :8501 was started at 00:44 and runs older code (e.g. Journal without the integrity check) → **restart it before the pitch** (Ctrl+C, `streamlit run app.py`).

### 7.15 New network / Reconstitution design not visible online (2026-11-06 04:10 → 04:25)
- **Symptom:** the user's style update (Réseau de compromission, Reconstitution roadmap) looked "not pushed": the public app showed the new sidebar name but the old Constellation (stars, dark background) and the old timeline.
- **Cause:** it *was* pushed (`965f769`, 03:43); Streamlit Cloud re-ran `app.py` on push but kept the old `studio.py` module loaded. No lost work: working tree clean, no stash / branch / other copy, VS Code history and git objects only hold older versions.
- **Fix:** checked the pushed code on a fresh server (new designs, 0 errors), then the user rebooted the public app → both pages verified online. Demo checklist: reboot after every push.

### 7.16 Nazar — evil-eye work agent (2026-11-06 04:25 → 04:50)
- **Ask:** a helper that does work, not a chatbot, with the evil eye as the agent. Built `app/nazar.py`: one instruction → one action, parsed by rules (0 token, instant, works offline), FR/EN.
- **Actions:** `mes tâches` (briefing: alerts left, 377 high-confidence blocks, 53 deep-search priorities, journal integrity, copilot mode), `suivante`, `top 10 d'hier`, `alertes à bloquer`, `ouvre / procès / reconstitution / contre-enquête TX…`, `C000488`, person search, `vérifie le journal`, `kpi`, page names; anything else → handed to the copilot on the open alert, or a refusal ("I'm a work agent").
- **Safety:** `bloque TX…` / `valide celle-ci` only *prepare* the decision (system recommendation, measured fraud rate at that score, override warning); it is saved only after **Confirm**, through the same `record_decision` (source `agent_nazar`, hash chain intact). List words never trigger a decision; a decision needs a TX ID or "celle-ci".
- **Icon:** our own evil-eye drawing (`app/static/brand/nazar*.png`, drawn in code). The downloaded pngtree image stays out of Git (licence; `.gitignore`).
- **Checks:** `tests/test_nazar.py` (33 tests: parsing, every action, decisions only after confirmation, log) → full suite 82/82 offline; browser test on a copy: briefing, list, prepared block with override warning, cancel, confirm (journal still "intacte"), open → navigates, Journal shows the agent section, 0 exceptions.
- **After this push:** Reboot the public app so the new module loads.

### 7.17 Nazar can talk + model / RAG / roadmap answers (2026-11-06 09:50 → 10:10)
- **Nazar conversation mode** (built in another session, pushed here): small talk (hello, thanks, a joke, who are you) answered offline with a little personality; anything that is not a command → a short chat on Azure OpenAI (persona prompt, last 6 turns, facts = queue counts + validation KPIs + the open alert's ID only, prompt-injection guard, content-filter refusal, answers cached). Suggested commands become clickable chips. Without a key: "type `aide`". Tokens logged per message and shown on the Journal page.
- **Kept safe:** a decision still needs a TX ID or "celle-ci" and a Confirm click ("bloque tout" → conversation, never a decision); questions on the open alert ("cette alerte", "ce client") still go to the copilot, which reads the data.
- **Push isolation:** the chat calls `copilot.polish`, which belongs to the jury-test session's unfinished copilot changes → guarded (`hasattr`) so this push works on its own; only the Journal-caption hunk of `app.py` was staged.
- **Tests:** `tests/test_nazar.py` 33 → 40 (small talk, chat offline never decides, chat facts = aggregates without customer IDs) → full suite 89/89 on the exact tree pushed.
- **Jury handbook:** "Why not deep learning or a GNN?", "Do you use RAG?" (yes, on facts), "Why not a bigger model?"; roadmap now names Fabric Real-Time Intelligence (scoring at authorisation), a Fabric Data Agent for managers and document RAG (Azure AI Search) once the bank provides procedures.

### 7.18 Test against the jury grid (brief §15) + explanation fixes (2026-11-06 09:20 → 10:30)
| Criterion (weight) | Test run | Result |
|---|---|---|
| Business relevance (20 %) | Headline numbers cross-checked in every doc and page | Consistent everywhere (718 / 1,061 / 3,221 / 2,160 / PR-AUC 0.646; 0.622 = backtest average, a different metric) |
| Detection quality (20 %) | KPIs **recomputed with sklearn from raw `gold_scores` + `fraud_labels_train` in Fabric**; leak scan of notebooks 01/02; `submission.csv` vs Fabric | PR-AUC 0.6459 (rules 0.0143), top 1 % 718 frauds / 1,061 false, rules 117 / 3,221 — all reproduced; windows past-only, network features use `rdate < d`; 0 test rows with a label; submission = 187,628 rows, scores identical to Fabric (max diff 1e-16) |
| Explanation & copilot (25 %) | `eval_copilot.py --fresh` (18 live golden questions) + scan of all 72 cached answers | Found and fixed 5 defects a banker would catch (below) → **18/18**, 99.4 % grounded, 0 defects in cached answers |
| Experience & demo (15 %) | Browser run of the §17 path on live Fabric + Azure OpenAI; 15 pages × FR/EN | Alert → answer (cache 0.9 s, free live question 8.5 s) → decision saved: 15 s; transaction page fits one screen at 1920×1080 (zoom 80 % at 1366×768); 0 exceptions on 30 page renders |
| Tech coherence (15 %) | Fabric REST item list; doc links; fresh `git clone` run without `.env` | All Fabric items present (copy job, lakehouse, 4 notebooks, pipeline, MLflow model + experiments, semantic model, report); 0 broken links in 16 docs; fresh clone runs on the snapshot (3.6 s first load) |
| Delivery (5 %) + rules §16 | Secret scan of **all 71 commits** incl. notebook outputs | 0 keys, tokens or passwords; slides / rehearsal / video still to do (§5) |

**Defects found and fixed (explanations, incl. the legitimate case TX01575959):**
1. The copilot listed **"KYC faible"** as reassuring (the field is the KYC *risk* level) → prompt rule + labels "risque KYC" in the app.
2. **181 / 3,656 alerts** showed a risky-looking model factor as *reassuring* (amount above the customer's usual, above the card limit, magnetic stripe) — including the false-positive demo case ("3,360 TND, sous plafond") → `tools.COUNTER_INTUITIVE`: shown as "non déterminants pour le modèle", never as reassuring; the page now shows business reassurances computed from the past (chip, known merchant, usual city / country, plausible travel).
3. "Does it look like the customer's habits?" was hedged and miscounted → verdict computed in code (`compare_to_habits` → `lecture_habitudes`: Non / En partie / Oui + deviations + consistent facts), the LLM only phrases it; the new merchant in the 24 h card sequence is named.
4. Technical field names leaked ("part_operations_passees_inferieures", even accented) and English answers said "confidence: moyenne" → deterministic `copilot.polish` on every answer (0 token).
5. Answers ended with chatbot offers ("si vous voulez, je peux…") and an ATM case called the victims "fraudeurs" → explicit formats for timeline and related-cases questions, field renamed `clients_victimes_de_fraude_deja_signales`.
- Transaction page: duplicate factor removed (rule + model saying the same thing), whole numbers without ".0", decision button on the first screen.
- Cache rebuilt cleanly (`CACHE_VERSION` v6, `warmup.py fr en`: 64 answers + 6 trials + 18 deep searches, 223k tokens); `tests/test_explanations.py` (4 tests) → 93/93.
- Still open: a *fresh* live answer can occasionally end with an offer despite the rule (seen once on a free question); cached demo answers are clean.

### 7.19 3D Nazar robot, voice and GPT-5 mini brain (2026-11-06 10:20 → 10:55)
- **Built in another session:** a 3D robot drawn in code with three.js (`app/components/nazar_avatar/index.html`, bidirectional Streamlit component without npm, `app/nazar_avatar.py`): glossy shell, visor with blue eyes, sound-meter mouth, headphones, Hyson logo on the chest. Follows the cursor, blinks, speaks in a bubble on every reply, waves on open and on click (0 token). Mode Chat / Voice (browser speech: mic in Chrome / Edge, replies read aloud). Brain Nazar / GPT-5 mini. The avatar is optional: any failure shows a caption and Nazar keeps working.
- **Review before push (2 fixes):** (1) the speech bubble wrote reply text with `innerHTML` after stripping only `>` — a reply holding `<img src=x onerror=…` followed by "Nazar" ran script **in the app page** (the component iframe is same-origin; proven in a browser on the original file) → text escaped first, re-tested: shown as text. (2) GPT-5 mini mode, described as having no bank data, still received the last Nazar answers (IDs, amounts) as history → it now only sees its own turns (test with a fake client). Prompt: the user is an analyst, not a customer.
- **Checks:** robot renders in the Nazar window (live Fabric), "salut" → bubble and reply; GPT-5 mini live: explains skimming; "bloque TX01555470" → no Confirm button, says it has no access and points to the Nazar brain; "combien de fraudes ?" → no invented figure; 0 page errors. Full suite 94/94 offline. Not tested: speaking into a real microphone.
