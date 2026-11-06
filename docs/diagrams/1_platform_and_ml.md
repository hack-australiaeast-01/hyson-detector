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
flowchart LR
    SRC[("Bank database<br/>Azure SQL")] -->|"cj_bronze_load"| BR
    subgraph LH["lh_fraud · schema-enabled lakehouse · dbo empty"]
        direction LR
        subgraph BR["bronze · raw"]
            B1[("transactions_train / _test<br/>v_transactions_*<br/>customers · cards · merchants<br/>digital_events · fraud_labels_train<br/>legacy_rule_alerts_train<br/>ingestion_log")]
        end
        subgraph QU["quality · 05"]
            Q1[("rules · issues<br/>row_status · summary<br/>quarantine_* × 5")]
        end
        subgraph SI["silver · 01"]
            S1[("transactions<br/>1.9 M rows")]
        end
        subgraph GO["gold · 01–02"]
            G1[("features (73)<br/>scores · alert_queue<br/>alert_explanations")]
        end
        subgraph ML["ml · 02, 04"]
            M1[("model_metrics · leaderboard<br/>importance · recall_by_type<br/>ci · robustness")]
        end
        subgraph MA["mart · 05"]
            D1[("dim_* × 7<br/>fact_transactions<br/>fact_digital_events")]
        end
        subgraph SV["serving · 03e"]
            P1[("pbi_* × 8")]
        end
        subgraph MT["meta · 06"]
            X1[("table_catalog<br/>migration_log")]
        end
        BR -->|"41 rules / row"| QU
        BR --> SI --> GO --> ML
        QU -->|"accepted rows"| MA
        GO --> MA
        GO --> SV
    end
    SV -->|"Direct Lake"| PBI["Power BI<br/>sm_fraud_copilot"]
    GO & SI & MA -->|"SQL endpoint"| APP["Streamlit app<br/>copilot · agents"]
    APP -->|"decisions"| FB["Files/feedback/<br/>analyst_decisions"]
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
        F1 & F2 & F3 & F4 & F5 & F6 & F7 --> GF[("gold.features · 73 features")]
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
        EXP & TH & DEMO --> OUT[("gold.scores · gold.alert_queue<br/>gold.alert_explanations · ml.model_* · Files/exports/submission")]
    end
```
