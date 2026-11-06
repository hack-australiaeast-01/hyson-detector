# Hyson Detector — Architecture

Every layer of the solution, from the data in **Microsoft Fabric** to the models (**ML**), the language model in
**Azure AI Foundry** (**DL**) and each **AI pipeline** of the app. Diagrams are shown as images (also usable in slides, [`img/`](img/)); their editable Mermaid source is in
[`diagrams/`](diagrams/) (5 pages, rendered by GitHub) and `python docs/diagrams/render.py` regenerates the images.

Principle everywhere: **the model scores, the AI explains, the analyst decides.**

| # | View | What it answers |
|---|---|---|
| 1 | [End-to-end architecture](#1-end-to-end-architecture) | How the pieces fit: Fabric → models → Foundry → app → analyst → feedback |
| 2 | [Microsoft Fabric data platform](#2-microsoft-fabric-data-platform) | Lakehouse layers, every table, notebooks, pipeline, SQL endpoint, Power BI, MLflow |
| 3 | [ML pipeline: features, training, scoring, explanations](#3-ml-pipeline-features-training-scoring-explanations) | Notebooks 01 and 02 step by step |
| 4 | [Validation and MLOps lifecycle](#4-validation-and-mlops-lifecycle) | Notebook 04, MLflow registry, retraining pipeline, monitoring, feedback |
| 5 | [Azure AI Foundry and Azure OpenAI layer](#5-azure-ai-foundry-and-azure-openai-layer) | Project, deployment, safety filter, settings, every caller |
| 6 | [Where ML and DL are used](#6-where-ml-and-dl-are-used) | Rules vs machine learning vs deep learning, and the DL roadmap |
| 7 | [AI pipelines, one by one](#7-ai-pipelines-one-by-one) | Copilot, Le Procès, Enquête approfondie, Reconstitution, person search, data onboarding, copilot evaluation, Power BI as code |
| 8 | [Application pages and demo path](#8-application-pages-and-demo-path) | The 15 pages and how they link |
| 9 | [Deployment, security and CI/CD](#9-deployment-security-and-cicd) | Local live mode vs hosted demo, identities, secrets, GitHub → Streamlit Cloud |

---

## 1. End-to-end architecture

![End-to-end architecture](img/01_end_to_end.png)

<sub>Editable Mermaid source: [diagrams/1_platform_and_ml.md](diagrams/1_platform_and_ml.md#end-to-end-architecture)</sub>

| Layer | Technology | Role |
|---|---|---|
| Data platform | Microsoft Fabric: OneLake, Lakehouse `lh_fraud`, Delta tables, Spark notebooks, data pipeline | Ingest, clean, compute features, score, store everything the app reads |
| Machine learning | LightGBM (champion) + HGB / LambdaRank / blend (challengers), TreeSHAP, MLflow | Fraud score, explanations, model registry |
| Deep learning | gpt-5-mini (transformer LLM) deployed in Azure AI Foundry | Understands the analyst's question, writes the explanation from tool facts |
| Application | Streamlit (Python), 10 tools, 8 AI pipelines | Analyst workflow: queue → transaction → explanation → decision |
| BI | Direct Lake semantic model + Power BI report (built as code) | Manager KPIs, embedded in the app |
| Delivery | GitHub, Streamlit Community Cloud | Versioning, hosted demo, auto-redeploy on push |

---

## 2. Microsoft Fabric data platform

![Microsoft Fabric data platform](img/02_fabric_platform.png)

<sub>Editable Mermaid source: [diagrams/1_platform_and_ml.md](diagrams/1_platform_and_ml.md#microsoft-fabric-data-platform)</sub>

| Item | Content | Written by | Read by |
|---|---|---|---|
| Bronze | CSVs as delivered (train Jan 2025 → Jul 2026, test Aug → Sep 2026) | Copy job | Notebook 01 |
| `silver_transactions` | Typed, joined (customer, card, merchant), `period` from the time split, labels nulled on test | 01 | 01, app (history, related cases), Power BI |
| `gold_features` | 73 features computed with past-only windows | 01 | 02, 04 |
| `gold_scores`, `gold_alert_queue` | Score, percentile, rank, top-1 % alert, risk level, demo cases | 02 | App, 03e, 04 |
| `gold_alert_explanations` | Top factors per alert: rules + TreeSHAP for and against | 02 | App, copilot tools |
| `gold_model_*` | Metrics, leaderboard, importance, recall by fraud type | 02 | App, 03e |
| `gold_model_robustness*`, `gold_model_ci` | Rolling backtest, bootstrap intervals | 04 | App (Performance page) |
| `pbi_*` | Reporting tables (FR + EN labels) | 03e | Direct Lake model |
| `Files/app_feedback/decisions.csv` | Analyst decisions with time-to-decision | App | Next retraining |

---

## 3. ML pipeline: features, training, scoring, explanations

![ML pipeline: features, training, scoring, explanations](img/03_ml_pipeline.png)

<sub>Editable Mermaid source: [diagrams/1_platform_and_ml.md](diagrams/1_platform_and_ml.md#ml-pipeline-features-training-scoring-explanations)</sub>

| Step | Method | Why |
|---|---|---|
| Split | By time, never random (train ≤ May 2026, valid Jun–Jul, test Aug–Sep) | A random split mixes the same fraud episode between train and validation |
| Features | Spark window functions over the **past only**; graph features count only frauds reported **before** the transaction | No future information (brief §7, §8.6) |
| Excluded | `gender`, IDs, `fraud_scenario`, `fraud_reported_date` (except "already reported"), target-encoded entity risk | Fairness and leakage (checked by an `assert`) |
| Imbalance | Down-sample legit to 10 %, sample weights restore the real ratio | 0.55 % fraud rate |
| Models | Rules · HGB · **LightGBM** · LambdaRank · blend | Gradient boosting is the reference for tabular data |
| Selection | Top-1 % recall then PR-AUC on Jun–Jul; LightGBM preferred within 1 pt | One model both scores and explains |
| Threshold | Top 1 % per period (analyst capacity) | Brief §8.4 |
| Explanations | TreeSHAP contributions from the same LightGBM + business rules | Facts the copilot reads instead of inventing |

---

## 4. Validation and MLOps lifecycle

![MLOps lifecycle](img/04a_mlops_lifecycle.png)

<sub>Editable Mermaid source: [diagrams/2_mlops_foundry_ml_dl.md](diagrams/2_mlops_foundry_ml_dl.md#mlops-lifecycle)</sub>

![Notebook 04: robustness and model registry](img/04b_robustness_nb04.png)

<sub>Editable Mermaid source: [diagrams/2_mlops_foundry_ml_dl.md](diagrams/2_mlops_foundry_ml_dl.md#notebook-04-robustness-and-model-registry)</sub>

| MLOps element | Where | Status |
|---|---|---|
| Experiment tracking | MLflow experiments `02_score_explain`, `hyson-fraud-robustness` (1 run per fold) | ✅ |
| Model registry | ML model `hyson-fraud-lightgbm` v1 = production scores | ✅ |
| Orchestration | Data pipeline `pl_hyson_retrain` (01 → 02 → 03e ∥ 04, retry 1) | ✅ created, not scheduled (re-scoring changes demo IDs) |
| Reproducibility | Seeds, same sampling, `fabric/environment.yml` (runtime versions) | ✅ |
| Monitoring | PSI drift of the score distribution (Impact page), alert volume per day, fairness by segment / age (Performance page), copilot log | ✅ |
| Testing | 93 pytest tests (`tests/`) on every push (GitHub Actions) + copilot golden evaluation (18 questions) | ✅ |
| Feedback loop | `decisions.csv` → OneLake `Files/app_feedback` → labels for the next run | ✅ |
| Next | Schedule the pipeline, champion/challenger in shadow mode, drift alert with Data Activator | Roadmap |

---

## 5. Azure AI Foundry and Azure OpenAI layer

![Azure AI Foundry and Azure OpenAI layer](img/05_foundry_openai.png)

<sub>Editable Mermaid source: [diagrams/2_mlops_foundry_ml_dl.md](diagrams/2_mlops_foundry_ml_dl.md#azure-ai-foundry-and-azure-openai-layer)</sub>

| Setting | Value | Why |
|---|---|---|
| Model | `gpt-5-mini` (reasoning model) | Good French/English, function calling, low cost |
| Reasoning effort | `low` (copilot, Le Procès) · `minimal` (Enquête approfondie, one retry with `low` if the answer contradicts itself) | Latency and tokens |
| Prompt | Static system prompt first (≈ 1,400–2,000 tokens served by Azure prompt caching), then facts | ≈ 3,300 tokens and ≈ 7 s per new question, 1 LLM round |
| Safety | Azure content filter + app guardrails (off-topic refusal, unknown ID answered without LLM, no field names, decision fixed by rule) | Brief §9.8 |
| Cost control | Cache, prefetch (1 round), hourly cap on the public demo, every call logged with tokens | FinOps |

---

## 6. Where ML and DL are used

![Where ML and DL are used](img/06_ml_vs_dl.png)

<sub>Editable Mermaid source: [diagrams/2_mlops_foundry_ml_dl.md](diagrams/2_mlops_foundry_ml_dl.md#where-ml-and-dl-are-used)</sub>

| Need | Technique | Type | Why this choice |
|---|---|---|---|
| Score each transaction | LightGBM | ML | Best on tabular data, fast, exact explanations (TreeSHAP), auditable by a risk team |
| Explain the score | TreeSHAP + business rules | ML + rules | Same model that scores, numbers the copilot can cite |
| Decide | Documented rule with measured precision | Rules | Reproducible; the LLM never decides |
| Talk with the analyst | gpt-5-mini | **DL** (transformer) | Natural language FR/EN, function calling, summarising |
| Similar past cases | Cosine k-NN on SHAP vectors | ML | 0 token, explains "alerts like this were X % fraud" |
| Why not DL for the score | — | — | Tabular data where boosting is the state of the art; DL adds cost and opacity. Kept as challengers (roadmap), validated with the same backtest and registered in MLflow before any switch |

---

## 7. AI pipelines, one by one

### 7.1 Copilot question → answer

![AI pipeline 1: copilot question to answer](img/07a_copilot_pipeline.png)

<sub>Editable Mermaid source: [diagrams/3_ai_pipelines_part1.md](diagrams/3_ai_pipelines_part1.md#ai-pipeline-1-copilot-question-to-answer)</sub>

### 7.2 Le Procès (three AI roles)

![AI pipeline 2: Le Procès](img/07b_le_proces.png)

<sub>Editable Mermaid source: [diagrams/3_ai_pipelines_part1.md](diagrams/3_ai_pipelines_part1.md#ai-pipeline-2-le-proces)</sub>

### 7.3 Enquête approfondie (deep search on medium alerts)

![AI pipeline 3: Enquête approfondie](img/07c_enquete_approfondie.png)

<sub>Editable Mermaid source: [diagrams/3_ai_pipelines_part1.md](diagrams/3_ai_pipelines_part1.md#ai-pipeline-3-enquete-approfondie)</sub>

### 7.4 Reconstitution (crime-scene replay)

![AI pipeline 4: Reconstitution](img/07d_reconstitution.png)

<sub>Editable Mermaid source: [diagrams/3_ai_pipelines_part1.md](diagrams/3_ai_pipelines_part1.md#ai-pipeline-4-reconstitution)</sub>

### 7.5 Person search ("le client retraité de Sfax de plus de 70 ans avec des alertes")

![AI pipeline 5: person search](img/07e_person_search.png)

<sub>Editable Mermaid source: [diagrams/4_ai_pipelines_part2.md](diagrams/4_ai_pipelines_part2.md#ai-pipeline-5-person-search)</sub>

### 7.6 New data source onboarding (translate · measure · approve)

![AI pipeline 6: new data source onboarding](img/07f_data_onboarding.png)

<sub>Editable Mermaid source: [diagrams/4_ai_pipelines_part2.md](diagrams/4_ai_pipelines_part2.md#ai-pipeline-6-new-data-source-onboarding)</sub>

### 7.7 Copilot evaluation (golden questions)

![AI pipeline 7: copilot evaluation](img/07g_copilot_evaluation.png)

<sub>Editable Mermaid source: [diagrams/4_ai_pipelines_part2.md](diagrams/4_ai_pipelines_part2.md#ai-pipeline-7-copilot-evaluation)</sub>

### 7.8 Power BI as code (notebook 03e)

![AI pipeline 8: Power BI as code](img/07h_powerbi_as_code.png)

<sub>Editable Mermaid source: [diagrams/4_ai_pipelines_part2.md](diagrams/4_ai_pipelines_part2.md#ai-pipeline-8-power-bi-as-code)</sub>

---

## 8. Application pages and demo path

![Application pages](img/08a_app_pages.png)

<sub>Editable Mermaid source: [diagrams/5_app_and_deployment.md](diagrams/5_app_and_deployment.md#application-pages)</sub>

![Demo path](img/08b_demo_path.png)

<sub>Editable Mermaid source: [diagrams/5_app_and_deployment.md](diagrams/5_app_and_deployment.md#demo-path)</sub>

---

## 9. Deployment, security and CI/CD

![Deployment, security and CI/CD](img/09_deployment_security.png)

<sub>Editable Mermaid source: [diagrams/5_app_and_deployment.md](diagrams/5_app_and_deployment.md#deployment-security-and-cicd)</sub>

| Control | How |
|---|---|
| Identity | Fabric access with the analyst's Entra ID token (`az login`); no database password anywhere |
| Secrets | Azure OpenAI key only in `app/.env` (git-ignored) or Streamlit Secrets; scanned out of the repo and its history |
| Data minimisation | The LLM receives compact tool facts, never raw tables; person search uses approved filters; onboarding AI sees column names and statistics only |
| Labels | Test labels are NULL everywhere; graph features use frauds reported **before** the transaction |
| Traceability | Every LLM call logged (question, intent, tools, tokens, latency); every decision and data approval logged |
| Cost | Cache, 1-round prefetch, prompt caching, hourly cap on the public demo |
| Production next steps | Private endpoint + managed identity for Azure OpenAI, RBAC / row-level security, PII masking, real-time scoring with Eventstream + Eventhouse |
