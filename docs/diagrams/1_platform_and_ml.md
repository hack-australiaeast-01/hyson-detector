# Hyson Detector diagrams · Platform and ML (diagrams 1–3)

Mermaid source of the diagrams shown as images in [../ARCHITECTURE.md](../ARCHITECTURE.md). GitHub renders them below; to regenerate the PNGs run `python docs/diagrams/render.py`.

## End-to-end architecture
<!-- img: 01_end_to_end -->
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

## Microsoft Fabric data platform
<!-- img: 02_fabric_platform -->
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

## ML pipeline: features, training, scoring, explanations
<!-- img: 03_ml_pipeline -->
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
