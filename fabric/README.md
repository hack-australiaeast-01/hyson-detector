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
