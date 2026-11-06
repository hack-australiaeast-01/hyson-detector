# Model card — `hyson-fraud-lightgbm` (v1)

One-page summary for a model-risk / validation team. Registered in Microsoft Fabric (MLflow ML model `hyson-fraud-lightgbm`,
experiment `hyson-fraud-robustness`); identical to the production scores in `gold_scores` (rank correlation 1.0).

| Item | Value |
|---|---|
| Purpose | Rank card and digital-banking operations by fraud risk so a fraud analyst reviews the riskiest 1 % first. The analyst decides; the model does not block anything by itself. |
| Users | Fraud analysts (alert queue, copilot), risk managers (Power BI, Impact page) |
| Type | LightGBM gradient-boosted trees, 600 trees, learning rate 0.03, 63 leaves, native categoricals, class weights (fraud weight ≤ 50) |
| Data | Synthetic Tunisian retail bank (organisers' dataset): 1.9 M transactions, 3,500 customers, Jan 2025 → Sep 2026. Train Jan 2025 → May 2026 (all frauds + 10 % of legitimate rows, re-weighted), validation Jun–Jul 2026, scoring Aug–Sep 2026 (no labels) |
| Features | 73 features computed on the **past only** (amount vs habits, velocity, novelty, geography/speed, digital banking events, frauds already reported on the same merchant/device/beneficiary, calendar, profile) + 9 categoricals |
| Never used | `gender`, identifiers, `fraud_scenario`, `fraud_reported_date` (except "already reported before the transaction"), legacy analyst decisions, target-encoded entity risk (checked by an `assert`) |
| Decision threshold | Top 1 % of each period (analyst capacity) → alert; top 30 % of alerts → ELEVE. Recommendation BLOQUER / ESCALADER / VALIDER by a documented rule with measured precision (`tools.recommend`) |
| Explanations | TreeSHAP contributions of the same model (3 for, 2 against per alert) + business rules fired; calibrated "measured fraud rate" per score (validation, monotone bins) |

## Performance (validation Jun–Jul 2026, 177,953 operations, 1,013 frauds)

| Metric | Value [95 % CI, day-block bootstrap] | Current rules engine |
|---|---|---|
| PR-AUC | 0.646 [0.610–0.675] | 0.014 |
| Top-1 % recall | 70.9 % [68.3–73.0] | 11.5 % (3,338 alerts) |
| Top-1 % precision | 40.4 % [34.9–45.0] | 3.5 % |
| False alerts | 1,061 · 2,160 avoided [1,971–2,335] | 3,221 |
| Fraud value caught | 68 % of fraud TND | 22 % |

**Stability (rolling backtest, re-trained on the past only):** top-1 % recall 66.7 % (Dec–Jan) · 68.8 % (Feb–Mar) · 71.2 % (Apr–May) · 70.9 % (Jun–Jul) → **69.4 % ± 2.1**.

**By fraud type (recall top 1 % vs rules):** account takeover 89 % vs 10 % · cloned card abroad 91 % vs 100 % (legacy rule kept) · ATM skimming 74 % vs 18 % · stolen contactless 68 % vs 0 % · discreet online 68 % vs 13 % · card testing 61 % vs 0 %.

## Fairness (validation; alert rate on the live flow)

| Group | Alert rate | Precision | Recall |
|---|---|---|---|
| Segments | 0.88–1.12 % | 30 % (retirees) → 46 % (premium) | 61 % (retirees) → 76 % (professionals) |
| Age bands | 0.95–1.09 % | 35 % (60+) → 42 % (30–44) | 65 % (18–29) → 75 % (30–44) |

False alerts on legitimate operations (Performance page): the gap between the most and least disturbed group is 1.4× across segments and 1.2× across age bands for the model, vs 2.8× and 1.5× for the current rules engine. Retirees and over-60s have less fraud and lower precision/recall: monitor in production (dedicated threshold or review) and explain alerts to these customers carefully. Gender is not used and not reported.

## Limits and monitoring

- Synthetic, fraud-rich data (≈ 0.55 % fraud vs ≈ 0.1 % in reality); results must be re-validated on real data.
- Batch scoring (not at authorisation time); label delay not simulated in the backtest.
- Champion chosen among 4 models on the validation period (all within ~1 pt; mitigated by the backtest).
- Monitoring: PSI drift of the score distribution (Impact page), alert volume per day, analyst decisions fed back to OneLake.
- Retraining: Fabric pipeline `pl_hyson_retrain` (01 → 02 → 03e ∥ 04); a new version replaces v1 only if it beats it on the same backtest.

Owner: Hyson Detector team · Version 1 · 2026-11-06 · Source: `notebooks/02_score_explain.ipynb`, `notebooks/04_robustness.ipynb`.
