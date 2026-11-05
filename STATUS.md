# Project status — AI Banking Copilot for Fraud Detection
Updated: 2026-11-05 17:00 · ✅ done · 🟡 in progress · ❌ to do · Target level: **Gold ("Or")** (brief §6)

## 1. Pipeline & model (frozen: do not rerun notebook 02, or the demo IDs change)
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Fabric workspace `ws-hack-fraud-australiaeast`, lakehouse `lh_fraud`, copy job | ✅ | 1,908,228 transactions, 3,500 customers (larger than the brief) |
| 2 | Time split | ✅ | train 2025-01→2026-05 · valid 2026-06→07 · test 2026-08→09 (no labels) |
| 3 | NB 01: silver + `gold_features` (73 features, past-only) | ✅ | Behaviour, velocity, novelty, geography/speed, channel, digital timing, graph (already-reported frauds only), calendar |
| 4 | Leak checks | ✅ | 0 test labels, 0 duplicates, no label columns; target-encoded `*_risk` features excluded |
| 5 | NB 02: rules + HGB / LightGBM / LambdaRank / blend, champion chosen on valid | ✅ | Champion **LightGBM**: the same model scores and explains (SHAP) |
| 6 | Gold tables + submission CSV (§14) | ✅ | gold_scores, gold_alert_queue, gold_alert_explanations, gold_model_metrics/leaderboard/importance/recall_by_type, Files/submission/submission_csv |
| 7 | App export (parquet) in `app/data/` | 🟡 | 6 gold files + customer_history + customers ✅ · `digital_events` ❌ · latitude/longitude missing from customer_history (map disabled) |

## 2. Results (validation Jun–Jul 2026, out-of-time, final)
| | Alerts | Frauds caught | Recall | Precision |
|---|---|---|---|---|
| Current rules engine | 3,338 | 116 / 1,013 | 11.5 % | 3.5 % |
| Model, same alert volume | 3,338 | 787 | 77.7 % | 23.6 % |
| **Model, top 1 %** | **1,779** | **~719** | **70.9 %** | **40.4 %** |
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

- Pitch line: "Half the alerts, about 6× more frauds caught, about 67 % fewer false alerts (1,060 vs 3,222)."
- Demo cases:
  - TX01555470, obvious fraud: 3 night-time web transfers in 4 h (00:54, 03:30, 04:49), 3 failed logins in the previous 24 h.
  - TX01585580, subtle fraud: 7.69 TND online at 02:03 at a new merchant, after 2 other micro-purchases (card testing).
  - TX01575959, false positive avoided: 3,361 TND chip purchase in Tunis, daytime, retired customer. The current engine raised an alert; the model scores it in the bottom 0.01 %.

## 3. Application & copilot (`app/`)
| # | Item (brief §) | Status | Notes |
|---|---|---|---|
| 8 | Alert queue: filters (period/date/channel/risk/fraud type), risk colours, alerts per day (§10) | ✅ | `app.py` |
| 9 | Transaction view: score, risk and reassuring factors (observed vs usual), decision + confidence + comment, no scrolling (§10) | ✅ | |
| 10 | Customer 360: profile, habits, timeline, map (§10) | 🟡 | Map shown once lat/long are exported; digital events shown once `digital_events` is exported |
| 11 | 9 copilot tools (§9.2): get_alert_queue, get_transaction, get_customer_profile, compare_to_habits, get_customer_history, get_digital_events, find_related_cases, get_kpis, record_decision | ✅ | `tools.py`, compact JSON, unknown IDs handled |
| 12 | Copilot: prompt §9.3, 5-part format §9.4, temperature 0.1, max_tokens 600, ≤ 4 tool rounds, cache (§9.8) | ✅ | `copilot.py` + offline fallback (demo always works) |
| 13 | Copilot traceability: question, tools, tokens, latency → `data/copilot_log.jsonl` + Journal page (§9.8) | ✅ | |
| 14 | Decision journal + feedback (`data/decisions.csv`) (§10) | ✅ | |
| 15 | KPI page: model vs current engine, recall per type, drivers, leaderboard (§10) | ✅ | |
| 16 | Azure OpenAI: `app/.env` (endpoint, key, deployment) + `python test_aoai.py` | ❌ | **Your step**: Foundry project `proj-fraud-australiaeast` |
| 17 | Tested live with Azure OpenAI on the 9 questions of §9.7 | ❌ | After #16 |
| 18 | Power BI report on Gold (manager view, complement) | ❌ | Optional, 1 h |
| 19 | GitHub: Fabric Git integration + push of the repo (README, requirements, .env.example, .gitignore ✅) | ❌ | §13, §16.5 |
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
- Streamlit = analyst tool + copilot (parquet export, plan B §11); Power BI = manager KPIs (complement only).
- Out of scope (no data): AML flows, first-party/internal fraud.
- Dataset differs from the brief (3,500 customers, 2025-01→2026-09, 1.9 M tx). The current engine measured on our valid period = 3.5 % precision / 11.5 % recall (the brief's 15 % / 42 % is on its own train period).

## 5. Next actions
1. `app/.env` + `python test_aoai.py`, then `streamlit run app.py` and test the 3 demo cases with the LLM.
2. (Optional, recommended) export `digital_events` + `customer_history` with latitude/longitude (cell in §6) → re-download.
3. GitHub: Fabric Git integration + `git init` / push (the `.gitignore` already excludes `.env` and data).
4. Power BI (1 h), slides, 3 rehearsals, backup video.

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
