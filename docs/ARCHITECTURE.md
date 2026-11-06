# Hyson Detector — Architecture

Every layer of the solution, from the data in **Microsoft Fabric** to the models (**ML**), the language model in
**Azure AI Foundry** (**DL**) and each **AI pipeline** of the app. All diagrams are Mermaid (rendered by GitHub);
PNG versions for slides are in [`img/`](img/).

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

```mermaid
flowchart LR
    subgraph SRC["Source · synthetic Tunisian retail bank"]
        CSV["Transactions · labels · customers · cards<br/>merchants · digital events · legacy rule alerts"]
    end

    subgraph FAB["Microsoft Fabric · workspace ws-hack-fraud-australiaeast"]
        direction TB
        LH[("OneLake · Lakehouse lh_fraud<br/>Bronze → Silver → Gold (Delta)")]
        NB["Notebooks 01 · 02 · 03e · 04<br/>features · scoring · Power BI · robustness"]
        PL["Data pipeline pl_hyson_retrain"]
        ML["MLflow · experiment + ML model<br/>hyson-fraud-lightgbm"]
        SQL["SQL analytics endpoint"]
        PBI["Direct Lake model + Power BI report"]
        PL --> NB
        NB <--> LH
        NB --> ML
        LH --> SQL
        LH --> PBI
    end

    subgraph AIF["Azure AI Foundry · proj-fraud-australiaeast"]
        AOAI["Azure OpenAI · gpt-5-mini<br/>+ content safety filter"]
    end

    subgraph APP["Hyson Detector · Streamlit (FR/EN)"]
        direction TB
        DA["Data access · live T-SQL or Gold snapshot"]
        TL["10 tools: 9 read-only + record_decision<br/>+ decision rule"]
        AI["AI pipelines · copilot · Le Procès<br/>Enquête approfondie · person search · onboarding"]
        UI["15 pages · analyst · investigation · steering · data"]
        DA --> TL --> AI --> UI
    end

    AN(("Fraud analyst"))
    MGR(("Risk manager"))
    GH["GitHub repo"] -- "push = redeploy" --> APP

    CSV --> LH
    SQL -- "Entra ID token" --> DA
    AI <-- "function calling · facts only" --> AOAI
    PBI -. "secure embed" .-> UI
    UI <--> AN
    PBI --> MGR
    AN -- "BLOQUER / ESCALADER / VALIDER" --> TL
    TL -- "decisions.csv" --> LH
```

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

```mermaid
flowchart TB
    subgraph ING["Ingestion"]
        CJ["Copy job cj_bronze_load"]
    end

    subgraph BR["Bronze · raw Delta tables"]
        B1[("transactions_train · transactions_test")]
        B2[("fraud_labels_train · legacy_rule_alerts_train")]
        B3[("customers · cards · merchants · digital_events")]
        BV["views v_transactions_all · v_transactions_train_labeled"]
    end

    subgraph SI["Silver"]
        S1[("silver_transactions<br/>1,908,228 rows · period train / valid / test<br/>labels NULL on test")]
    end

    subgraph GO["Gold"]
        G1[("gold_features · 73 past-only features")]
        G2[("gold_scores · gold_alert_queue")]
        G3[("gold_alert_explanations · rules + SHAP")]
        G4[("gold_model_metrics · leaderboard<br/>importance · recall_by_type")]
        G5[("gold_model_robustness · _types · gold_model_ci")]
        G6[("pbi_* · 8 reporting tables")]
    end

    subgraph FI["OneLake Files"]
        F1["submission/submission_csv"]
        F2["robustness/summary.json · runtime_versions.json"]
        F3["app_feedback/decisions.csv"]
    end

    subgraph CMP["Compute · Spark notebooks"]
        N1["01_silver_features"]
        N2["02_score_explain"]
        N3["03e_powerbi_dashboard"]
        N4["04_robustness"]
    end

    subgraph SRV["Serving"]
        EP["SQL analytics endpoint lh_fraud"]
        SM["Direct Lake model sm_fraud_copilot · DAX"]
        RP["Report Fraud Copilot — Dashboard · 8 pages FR/EN"]
    end

    subgraph MLO["Data science"]
        EX["MLflow experiments<br/>02_score_explain · hyson-fraud-robustness"]
        MM["ML model hyson-fraud-lightgbm v1"]
    end

    PIPE["Data pipeline pl_hyson_retrain<br/>01 → 02 → 03e ∥ 04 · not scheduled"]

    CJ --> BR
    BR --> N1
    N1 --> S1
    N1 --> G1
    G1 --> N2 --> G2 & G3 & G4 & F1
    G2 --> N3 --> G6 --> SM --> RP
    G1 --> N4 --> G5 & F2 & EX
    N4 --> MM
    PIPE -.-> N1 & N2 & N3 & N4
    G2 & G3 & G4 & G5 & S1 --> EP
    F3 -. "labels for the next retraining" .-> N2
```

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

```mermaid
flowchart TB
    subgraph N01["Notebook 01 · silver + features (PySpark)"]
        A1["Join transactions + labels + customers + cards + merchants"] --> A2["Time split<br/>train ≤ May 2026 · valid Jun–Jul · test Aug–Sep<br/>labels nulled on test"]
        A2 --> A3["Past-only windows<br/>rowsBetween(unbounded, -1) · rangeBetween(-t, -1)"]
        A3 --> F1["Amount vs habits<br/>ratio · z-score · / limit · / income"]
        A3 --> F2["Velocity · bursts<br/>1 h / 24 h / 7 d, declines, small amounts"]
        A3 --> F3["Novelty<br/>country · city · merchant · category · device · beneficiary"]
        A3 --> F4["Geography<br/>distance · implied speed"]
        A3 --> F5["Digital banking<br/>failed logins · new device · beneficiary added · phone change"]
        A3 --> F6["Network<br/>frauds already reported on merchant / device / beneficiary"]
        A3 --> F7["Calendar · profile<br/>night · payday · Ramadan · segment · KYC"]
        F1 & F2 & F3 & F4 & F5 & F6 & F7 --> GF[("gold_features · 73 features")]
    end

    subgraph N02["Notebook 02 · scoring + explanations (pandas · LightGBM)"]
        GF --> S1["Training sample: all frauds + 10 % legit (seed 42)<br/>weights undo the sampling, fraud weight ≤ 50"]
        S1 --> R0["Rules baseline · 19 business rules (points)"]
        S1 --> M1["HistGradientBoosting"]
        S1 --> M2["LightGBM · 600 trees · native categoricals"]
        S1 --> M3["LightGBM LambdaRank · one query per day"]
        M1 & M2 & M3 --> M4["Rank-average blend"]
        R0 & M1 & M2 & M3 & M4 --> SEL{"Champion on Jun–Jul<br/>top-1 % recall · PR-AUC<br/>LightGBM if within 1 pt"}
        SEL --> RF["Refit champion on train + valid"]
        RF --> SC["Score Aug–Sep"]
        SEL --> SV["Validation scores Jun–Jul"]
        SV & SC --> TH["Alert budget = top 1 % per period<br/>ELEVE = top 30 % of alerts · MOYEN = rest"]
        TH --> EXP["Explanations per alert<br/>TreeSHAP (pred_contrib): 3 factors for · 2 against<br/>+ up to 4 business rules fired"]
        TH --> DEMO["3 demo cases chosen automatically"]
        EXP & TH & DEMO --> OUT[("gold_scores · gold_alert_queue<br/>gold_alert_explanations · gold_model_* · submission")]
    end
```

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

```mermaid
flowchart LR
    D["Data · Fabric Lakehouse"] --> F["Features · NB 01"]
    F --> T["Train · NB 02"]
    T --> V["Validate · NB 04<br/>rolling backtest · bootstrap CI"]
    V --> R["Register · MLflow<br/>hyson-fraud-lightgbm"]
    R --> S["Score in batch · NB 02<br/>gold_scores"]
    S --> SV["Serve · SQL endpoint → app<br/>Direct Lake → Power BI"]
    SV --> M["Monitor<br/>PSI drift · alert volume · decisions"]
    M --> FB["Feedback · analyst decisions → OneLake"]
    FB --> P["Retrain · pipeline pl_hyson_retrain"]
    P --> F
```

```mermaid
flowchart TB
    subgraph N04["Notebook 04_robustness · read-only on the pipeline"]
        P0["Same sample, categories and LightGBM settings as notebook 02"] --> BT
        subgraph BT["Rolling-origin backtest · train on the past only"]
            B1["F1 · test Dec–Jan"]
            B2["F2 · test Feb–Mar"]
            B3["F3 · test Apr–May"]
            B4["F4 · test Jun–Jul = production set-up"]
        end
        BT --> RES["Top-1 % recall 69.4 % ± 2.1 · worst 66.7 %<br/>PR-AUC 0.622 ± 0.036 · fraud value 72.5 %"]
        B4 --> AG["Agreement with gold_scores<br/>rank correlation 1.0 · same top 1 %"]
        AG --> BS["Day-block bootstrap · 1,000 resamples<br/>recall 70.9 % [68.3–73.0] · precision 40.4 % [34.9–45.0]"]
        AG --> REG["MLflow log_model → ML model hyson-fraud-lightgbm v1<br/>features.json · model_card.md"]
        RES & BS --> TB[("gold_model_robustness · gold_model_ci")]
    end
```

| MLOps element | Where | Status |
|---|---|---|
| Experiment tracking | MLflow experiments `02_score_explain`, `hyson-fraud-robustness` (1 run per fold) | ✅ |
| Model registry | ML model `hyson-fraud-lightgbm` v1 = production scores | ✅ |
| Orchestration | Data pipeline `pl_hyson_retrain` (01 → 02 → 03e ∥ 04, retry 1) | ✅ created, not scheduled (re-scoring changes demo IDs) |
| Reproducibility | Seeds, same sampling, `fabric/environment.yml` (runtime versions) | ✅ |
| Monitoring | PSI drift of the score distribution (Impact page), alert volume per day, copilot log | ✅ |
| Feedback loop | `decisions.csv` → OneLake `Files/app_feedback` → labels for the next run | ✅ |
| Next | Schedule the pipeline, champion/challenger in shadow mode, drift alert with Data Activator | Roadmap |

---

## 5. Azure AI Foundry and Azure OpenAI layer

```mermaid
flowchart LR
    subgraph RG["Resource group rg-hack-fraud-australiaeast · Australia East"]
        subgraph FP["Azure AI Foundry project proj-fraud-australiaeast"]
            RES["Azure OpenAI resource<br/>aoai-fraud-australiaeast-vnxcy"]
            DEP["Deployment gpt-5-mini<br/>Chat Completions · API 2024-12-01-preview"]
            CF["Content safety filter<br/>blocked our prompt-injection test"]
            RES --> DEP
            CF --- DEP
        end
    end

    subgraph GW["App-side LLM gateway · copilot.py"]
        CFG["Settings<br/>reasoning_effort low · max_completion_tokens<br/>timeout 60 s · 2 retries · streaming"]
        CAP["Cost guard<br/>COPILOT_HOURLY_CAP live calls / hour"]
        CACHE["Answer cache<br/>pre-computed demo answers"]
        LOG["Audit log<br/>question · intent · tools · tokens · latency"]
        OFF["Offline mode<br/>deterministic templates on the same tools"]
    end

    subgraph CALL["Callers"]
        C1["Copilot Q&A · function calling, 10 tools"]
        C2["Le Procès · 3 roles"]
        C3["Enquête approfondie · 1 call, no tools"]
        C4["Reconstitution · narration"]
        C5["Data onboarding · optional mapping refine"]
    end

    KEY["Key: app/.env locally · Streamlit Secrets online · never in Git"] -.-> GW
    C1 & C2 & C3 & C4 & C5 --> GW
    GW -- "HTTPS · facts only, no raw tables" --> DEP
    DEP -- "streamed tokens + usage (incl. cached prompt tokens)" --> GW
    CF -. "blocked → clear refusal, not cached" .-> GW
```

| Setting | Value | Why |
|---|---|---|
| Model | `gpt-5-mini` (reasoning model) | Good French/English, function calling, low cost |
| Reasoning effort | `low` (copilot, Le Procès) · `minimal` (Enquête approfondie, one retry with `low` if the answer contradicts itself) | Latency and tokens |
| Prompt | Static system prompt first (≈ 1,400–2,000 tokens served by Azure prompt caching), then facts | ≈ 3,300 tokens and ≈ 7 s per new question, 1 LLM round |
| Safety | Azure content filter + app guardrails (off-topic refusal, unknown ID answered without LLM, no field names, decision fixed by rule) | Brief §9.8 |
| Cost control | Cache, prefetch (1 round), hourly cap on the public demo, every call logged with tokens | FinOps |

---

## 6. Where ML and DL are used

```mermaid
flowchart TB
    subgraph R["Deterministic rules · 0 cost, fully explainable"]
        R1["19 business rules (points) · baseline + explanations"]
        R2["Decision rule tools.recommend<br/>BLOQUER / ESCALADER / VALIDER + measured precision"]
        R3["Person search filters · onboarding code mapping"]
    end

    subgraph ML["Machine learning · tabular data"]
        L1["LightGBM gradient-boosted trees · fraud score (champion)"]
        L2["HGB · LambdaRank · blend (challengers)"]
        L3["TreeSHAP · per-alert contributions"]
        L4["Isotonic-style calibration (PAV) · measured fraud rate per score"]
        L5["k-nearest analogs (cosine on SHAP vectors) · Enquête approfondie"]
        L6["PSI drift · counterfactuals on SHAP (Contre-enquête)"]
    end

    subgraph DL["Deep learning · language"]
        D1["gpt-5-mini transformer LLM (Azure AI Foundry)<br/>understands questions, calls tools, writes explanations"]
    end

    subgraph RD["Deep learning roadmap · as MLflow challengers"]
        X1["Sequence model (GRU / Transformer) on each card's history"]
        X2["Graph neural network on shared devices / beneficiaries / merchants"]
        X3["Autoencoder anomaly score as an extra feature (unseen fraud patterns)"]
    end

    L1 --> L3 --> D1
    R2 --> D1
    L1 -. "compare in the same backtest" .-> RD
```

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

```mermaid
flowchart TD
    Q["Analyst question · FR/EN · transaction open"] --> ID{"ID typed in the question?"}
    ID -- "TX… unknown" --> NF["Guardrail: 'introuvable' · 0 token · no decision"]
    ID -- "TX… known" --> CTX["That transaction becomes the context"]
    ID -- "none" --> CTX2["Open transaction is the context"]
    CTX & CTX2 --> K{"Cache hit?"}
    K -- yes --> CA["Pre-computed gpt-5-mini answer"]
    K -- no --> I["detect_intent<br/>analyse · habits · before · related · summary<br/>kpi · queue · person · person_id · general"]
    I --> P["Prefetch: Python calls the tools the intent needs<br/>'hier' = 2026-09-29 in the demo calendar"]
    P --> T["9 read-only tools on Fabric Gold (+ record_decision on request)<br/>get_transaction · compare_to_habits · get_customer_profile<br/>get_customer_history · get_digital_events · find_related_cases<br/>get_alert_queue · get_kpis · find_customers"]
    T --> RC["recommend(): BLOQUER / ESCALADER / VALIDER<br/>+ precision measured in validation"]
    T & RC --> M["Messages: cached system prompt + language + intent + FACTS + last 2 exchanges"]
    M --> LLM["gpt-5-mini · streaming · ≤ 4 extra tool rounds"]
    LLM -- "content filter" --> REF["Clear refusal · not cached"]
    LLM --> A["Answer: verdict · factors · context · reassuring · recommendation"]
    LLM -. "error / no key" .-> OFF["Offline deterministic answer"]
    A & CA & NF & OFF & REF --> LOG[("copilot_log.jsonl · copilot_cache.json")]
```

### 7.2 Le Procès (three AI roles)

```mermaid
sequenceDiagram
    autonumber
    actor A as Analyst
    participant UI as Le Procès page
    participant T as Tools (Fabric facts)
    participant P as AI prosecutor
    participant D as AI defence
    participant J as AI judge
    A->>UI: open a case
    UI->>T: prefetch summary facts + recommend()
    par same facts in parallel threads
        T->>P: facts
        P-->>UI: strongest risk arguments with figures
    and
        T->>D: facts
        D-->>UI: strongest reassuring arguments with figures
    end
    UI->>J: both pleas + facts + system recommendation
    J-->>UI: verdict, deciding argument, confidence
    UI->>A: hearing replay + verdict banner
    A->>T: accept or override → record_decision(source = proces)
```

### 7.3 Enquête approfondie (deep search on medium alerts)

```mermaid
flowchart LR
    W["watch() · 0 token<br/>MEDIUM alerts whose customer had an alert in the previous 72 h<br/>≈ 53 % fraud vs 16 % (validation)"] --> E
    subgraph E["evidence() · 0 token · numbered lines E1…En"]
        E1["Habits and amount gap"]
        E2["Digital events around the operation"]
        E3["Linked customers · points of compromise"]
        E4["Robustness: counterfactual on SHAP factors"]
        E5["25 most similar labelled alerts (cosine k-NN)"]
        E6["Previous analyst decisions"]
    end
    E --> LLM["investigate() · ONE gpt-5-mini call, no tools<br/>reasoning minimal · connects the dots"]
    LLM --> CHK{"Hypothesis and direction consistent?"}
    CHK -- no --> RT["One retry · reasoning low"]
    CHK -- yes --> OUT["Hypothesis · strengthen / lift · next check"]
    RT --> OUT
    OUT --> CL[("Cached per transaction + language · logged")]
```

### 7.4 Reconstitution (crime-scene replay)

```mermaid
flowchart LR
    TX["Open alert"] --> RS["replay_steps(hours before)<br/>transactions + digital events merged on one timeline"]
    RS --> FL["Signals flagged in red<br/>failed login · new device · new beneficiary · burst · night"]
    FL --> PLAY["Step-by-step animation · lanes · map"]
    PLAY --> NAR["'Narrate' → copilot intent 'before'<br/>gpt-5-mini tells the sequence from the facts"]
```

### 7.5 Person search ("le client retraité de Sfax de plus de 70 ans avec des alertes")

```mermaid
flowchart LR
    Q["Question in natural language"] --> PR["parse() · 0 token<br/>city · segment · occupation · age · KYC · digital · with alerts"]
    PR --> FC["find_customers() · read-only on approved filters<br/>never free SQL from the LLM"]
    FC --> RES["Count + up to 5 compact profiles<br/>alerts, riskiest alert, no raw rows"]
    RES --> PH{"Azure OpenAI on?"}
    PH -- yes --> LLM["gpt-5-mini phrases the list · no decision"]
    PH -- no --> OFF["Deterministic answer"]
    LLM & OFF --> OPEN["'Ouvrir' → customer on their riskiest alert"]
```

### 7.6 New data source onboarding (translate · measure · approve)

```mermaid
flowchart LR
    LD["Load CSV or partner-bank sample"] --> PF["Profile<br/>types · empty cells · ranges · IDs masked"]
    PF --> MAP["Map columns to our schema<br/>rules + synonyms, confidence per field"]
    MAP -. "optional" .-> AIR["'Affiner avec l'IA' · ONE call<br/>column names + statistics only"]
    AIR --> MAP
    MAP --> TR["Translate<br/>codes POS→TPE · countries TUR→TR · dates · EUR→TND (editable rates)"]
    TR --> ACC["Accuracy<br/>required fields · % valid values · reconciliation · PSI drift vs our data"]
    ACC --> G{"Verdict"}
    G -- "Prêt / À revoir" --> AP["Human approval · name + checkbox"]
    G -- "Bloqué" --> STOP["Approval disabled · untranslated values listed"]
    AP --> DC[("Versioned data contract + translated parquet + approval log")]
    DC -. "documented next step" .-> NEXT["OneLake Files → Bronze → pipeline pl_hyson_retrain → re-score"]
```

### 7.7 Copilot evaluation (golden questions)

```mermaid
flowchart LR
    GS["14 golden questions<br/>brief §9.7 + unknown ID + off-topic + prompt injection"] --> ASK["copilot.ask() exactly as in the app"]
    ASK --> RE["Re-run the tools it used → facts it saw"]
    RE --> CK["0-token checks<br/>decision = system rule · key facts · numbers grounded ≥ 90 %<br/>5 sections · English only · refusals · no prompt / key leak"]
    CK --> REP[("docs/COPILOT_EVAL.md · copilot_eval.json<br/>14/14 pass · 99.3 % numbers grounded")]
    REP --> APPV["Shown on Performance → Robustesse et gouvernance"]
```

### 7.8 Power BI as code (notebook 03e)

```mermaid
flowchart LR
    G[("gold_alert_queue · gold_alert_explanations · gold_model_*")] --> T["pbi_* tables · FR + EN labels<br/>exact counts from gold_scores × labels"]
    T --> SM["Direct Lake model sm_fraud_copilot<br/>semantic-link-labs · DAX measures · relationship"]
    SM --> RJ["Report JSON generated in Python<br/>8 pages FR/EN · icon navigation"]
    RJ --> API["Fabric REST updateDefinition"]
    API --> RP["Report 'Fraud Copilot — Dashboard'"]
    RP --> EMB["Embedded in the app (viewer signs in with Entra ID)"]
```

---

## 8. Application pages and demo path

```mermaid
flowchart TD
    START(["Open the app"]) --> SPL["Branded splash · Gold tables load"]
    SPL --> WEL["Welcome dialog · guided tour or explore"]
    WEL --> GUIDE

    subgraph W["Bienvenue"]
        GUIDE["Démarrer ici · KPIs · 8-step tour"]
    end
    subgraph AN["Analyste"]
        QUEUE["File d'alertes · measured fraud rate · suggested action"]
        TX["Fiche transaction & copilote · stopwatch · decision · case file"]
        CUST["Vue client 360 · habits before the alert · timeline · map · person search"]
    end
    subgraph IA["Enquête IA"]
        DEEP["Enquête approfondie · watch list · evidence board"]
        PROC["Le Procès · prosecutor / defence / judge"]
        REP["Reconstitution · replay + narration"]
        CON["Contre-enquête · what-if on SHAP factors"]
        GAL["Constellation · points of compromise"]
    end
    subgraph PI["Pilotage"]
        IMP["Impact & processus · TND · workload · AI cost · drift"]
        MKT["Marché & benchmarks"]
        PERF["Performance du modèle · robustness & governance"]
        PBI["Tableau de bord Power BI"]
        JOUR["Journal & traçabilité"]
    end
    subgraph DO["Données"]
        ONB["Nouvelle source de données · translate, measure, approve"]
    end

    GUIDE --> QUEUE
    QUEUE -- "open an alert" --> TX
    QUEUE -- "AI flag" --> DEEP
    TX --> CUST
    TX --> PROC & REP & CON
    GAL -- "open an orbiting alert" --> TX
    DEEP --> TX
    PROC -- "accept / override" --> DEC[("Decision log → OneLake")]
    TX -- "BLOQUER / ESCALADER / VALIDER" --> DEC
    DEC --> JOUR & IMP
    IMP --> PERF --> PBI
```

```mermaid
flowchart LR
    S1["1 · Démarrer ici"] --> S2["2 · Obvious fraud TX01555470"] --> S3["3 · Ask the copilot"] --> S4["4 · Le Procès"] --> S5["5 · Reconstitution"] --> S6["6 · Decide < 30 s"] --> S7["7 · Avoided false positive TX01575959 → Contre-enquête"] --> S8["8 · Constellation"] --> S9["9 · Impact & Performance"]
```

---

## 9. Deployment, security and CI/CD

```mermaid
flowchart TB
    subgraph LOC["Pitch laptop · live mode"]
        L1["Streamlit app"] -- "az login → Entra ID token" --> L2["Fabric SQL endpoint · live Gold + full history"]
        L1 -- "key from app/.env (git-ignored)" --> L3["Azure OpenAI"]
        L1 -- "decisions" --> L4["OneLake Files/app_feedback"]
    end

    subgraph CLOUD["Hosted demo · hyson-detector.streamlit.app"]
        C1["Streamlit Community Cloud"] --> C2["Gold snapshot committed in app/data<br/>Gold tables + history + digital events of alert customers · no test labels"]
        C1 -- "key from Streamlit Secrets" --> C3["Azure OpenAI · hourly cap"]
    end

    subgraph CICD["Delivery"]
        DEV["VS Code + GitHub Copilot agent"] --> GH["GitHub hack-australiaeast-01/hyson-detector"]
        GH -- "push to main" --> C1
        GH -. "notebooks exported from Fabric" .-> NB["notebooks/ · fabric/ (pipeline, environment)"]
    end
```

| Control | How |
|---|---|
| Identity | Fabric access with the analyst's Entra ID token (`az login`); no database password anywhere |
| Secrets | Azure OpenAI key only in `app/.env` (git-ignored) or Streamlit Secrets; scanned out of the repo and its history |
| Data minimisation | The LLM receives compact tool facts, never raw tables; person search uses approved filters; onboarding AI sees column names and statistics only |
| Labels | Test labels are NULL everywhere; graph features use frauds reported **before** the transaction |
| Traceability | Every LLM call logged (question, intent, tools, tokens, latency); every decision and data approval logged |
| Cost | Cache, 1-round prefetch, prompt caching, hourly cap on the public demo |
| Production next steps | Private endpoint + managed identity for Azure OpenAI, RBAC / row-level security, PII masking, real-time scoring with Eventstream + Eventhouse |
