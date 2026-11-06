# Hyson Detector diagrams · MLOps, Azure AI Foundry, ML vs DL (diagrams 4–6)

Mermaid source of the diagrams shown as images in [../ARCHITECTURE.md](../ARCHITECTURE.md). GitHub renders them below; to regenerate the PNGs run `python docs/diagrams/render.py`.

## MLOps lifecycle
<!-- img: 04a_mlops_lifecycle -->
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

## Notebook 04: robustness and model registry
<!-- img: 04b_robustness_nb04 -->
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

## Azure AI Foundry and Azure OpenAI layer
<!-- img: 05_foundry_openai -->
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

## Where ML and DL are used
<!-- img: 06_ml_vs_dl -->
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
