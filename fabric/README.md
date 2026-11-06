# Fabric items (as code)

| File | Fabric item | What it does |
|---|---|---|
| [`pl_hyson_retrain.json`](pl_hyson_retrain.json) | Data pipeline **pl_hyson_retrain** | Orchestrates the retraining: `01_silver_features` → `02_score_explain` → (`03e_powerbi_dashboard` ∥ `04_robustness`), 1 retry each. **Not scheduled**: re-running 01/02 re-scores everything and changes the demo IDs; run it after the pitch or for a real retraining. |
| [`environment.yml`](environment.yml) | Environment (to create) | Library versions of the runtime that produced the scores and the registered model; attach it to the notebooks so every run is reproducible. |

Related items created in the workspace `ws-hack-fraud-australiaeast`:

- Notebook **04_robustness** (`../notebooks/04_robustness.ipynb`): rolling backtest, bootstrap intervals, MLflow.
- MLflow experiment **hyson-fraud-robustness** (one run per backtest fold + `production-lightgbm`).
- ML model **hyson-fraud-lightgbm** (version 1): the fold-4 model, identical to the production scores in `gold_scores`
  (rank correlation 1.0, same top 1 %, max difference 0), logged with its features list and model card.
- Delta tables `gold_model_robustness`, `gold_model_robustness_types`, `gold_model_ci`.

## Lakehouse layout (schema-enabled `lh_fraud`)

| Schema | Role |
|---|---|
| `bronze` | raw data as delivered (copy job `cj_bronze_load` now writes here) + `ingestion_log` |
| `quality` | 41 row-level rules, issues, row status, summary, quarantine (notebook 05) |
| `silver` | `transactions` — cleaned, conformed, joined (notebook 01) |
| `gold` | `features`, `scores`, `alert_queue`, `alert_explanations` (01–02) |
| `ml` | model metrics, leaderboard, importance, recall by type, CIs, robustness (02, 04) |
| `mart` | star schema `dim_*` × 7 + `fact_transactions`, `fact_digital_events` (05) |
| `serving` | `pbi_*` × 8 for the Direct Lake model `sm_fraud_copilot` (03e) |
| `meta` | `table_catalog` (role, producer, previous name, rows, columns) + `migration_log` |

`dbo` (default schema) is empty. The mapping is code: [`app/layout.py`](../app/layout.py); notebooks carry a generated `T` mapping cell.
Tools: [`deploy_notebook.py`](deploy_notebook.py) (backs up the current definition, deploys, optionally runs and polls) ·
[`repoint_items.py`](repoint_items.py) (moves semantic-model partitions and copy-job destinations to the new schemas from the backups) ·
`notebooks/gen_nb06.py copy | finalize` (migration: copy → verify → repoint → drop, logged in `meta.migration_log`).
Backups of every definition changed are in `fabric/backups/` (git-ignored).
