# Hyson Detector — Architecture

Three views, all rendered by GitHub (Mermaid):

1. [Global architecture](#1-global-architecture) — Microsoft Fabric → Gold → app / Power BI → Azure OpenAI → feedback
2. [AI workflow](#2-ai-workflow-copilot-and-le-procès) — how a question becomes a sourced answer (and how Le Procès works)
3. [Page workflow](#3-page-workflow-the-whole-app) — every page of the app and the demo path

Principle everywhere: **the model scores, the AI explains, the analyst decides.**

---

## 1. Global architecture

```mermaid
flowchart LR
    subgraph SRC["Source (synthetic bank data)"]
        CSV["transactions · labels · customers<br/>cards · merchants · digital events"]
    end

    subgraph FAB["Microsoft Fabric — workspace ws-hack-fraud-australiaeast"]
        direction TB
        CJ["Copy job<br/>cj_bronze_load"]
        BR[("Bronze<br/>raw Delta tables")]
        NB1["Notebook 01_silver_features<br/>PySpark · time split<br/>73 past-only features"]
        SI[("Silver<br/>silver_transactions<br/>gold_features")]
        NB2["Notebook 02_score_explain<br/>rules + HGB / LightGBM / LambdaRank / blend<br/>champion = LightGBM · SHAP"]
        GO[("Gold<br/>gold_scores · gold_alert_queue<br/>gold_alert_explanations · gold_model_*")]
        NB3["Notebook 03e_powerbi_dashboard<br/>pbi_* tables · DAX · report as code"]
        SM["Direct Lake model<br/>sm_fraud_copilot"]
        PBI["Power BI report<br/>8 pages FR/EN"]
        SQL["SQL analytics endpoint<br/>lh_fraud"]
        OL[("OneLake Files<br/>app_feedback/decisions.csv")]
        CJ --> BR --> NB1 --> SI --> NB2 --> GO
        GO --> NB3 --> SM --> PBI
        GO --> SQL
    end

    subgraph APP["Hyson Detector — Streamlit app"]
        DA["data_access.py<br/>live T-SQL (Entra token)<br/>or parquet snapshot"]
        FX["features.py<br/>impact · drift · replay<br/>counterfactual · constellation"]
        TL["tools.py<br/>9 tools · recommend()"]
        CP["copilot.py<br/>intent routing · prefetch<br/>streaming · cache · log"]
        CR["courtroom.py<br/>prosecutor · defence · judge"]
        UI["app.py + studio.py + ui.py<br/>13 pages · FR/EN"]
    end

    AOAI["Azure OpenAI<br/>gpt-5-mini<br/>(function calling)"]
    AN(("Fraud analyst"))

    CSV --> CJ
    SQL -- "T-SQL, Entra ID" --> DA
    DA --> FX & TL
    TL --> CP & CR
    CP <--> AOAI
    CR <--> AOAI
    FX & TL & CP & CR --> UI
    PBI -. "secure embed" .-> UI
    UI <--> AN
    AN -- "decision BLOQUER / ESCALADER / VALIDER" --> TL
    TL -- "feedback loop" --> OL
    OL -. "labels for next retraining" .-> NB2
```

| Layer | Technology | Role |
|---|---|---|
| Ingestion | Fabric copy job → Lakehouse `lh_fraud` (Bronze) | Raw CSVs as Delta tables |
| Features | Notebook 01 (PySpark windows) | 73 features computed **only from the past** of each transaction; time split train ≤ May 2026 / valid Jun–Jul / test Aug–Sep |
| Scoring | Notebook 02 (LightGBM champion, SHAP) | Score, top-1 % alert queue (analyst capacity), rule + SHAP explanations, metrics vs the current rules engine |
| BI | Notebook 03e → Direct Lake → Power BI | Manager dashboard, built as code, FR/EN |
| Serving | SQL analytics endpoint | Live T-SQL from the app with the analyst's Entra token (no stored secret) |
| App | Streamlit | Alert queue, transaction view, AI investigation, steering pages |
| AI | Azure OpenAI gpt-5-mini | Explains with facts fetched by tools; never invents the score or the decision |
| Feedback | OneLake `Files/app_feedback/decisions.csv` | Analyst decisions (with time-to-decision) feed the next retraining |
| Hosted demo | Streamlit Community Cloud | Same code; reads the committed Gold snapshot (`app/data/*.parquet`) because the cloud has no Entra login |

---

## 2. AI workflow (copilot and Le Procès)

### 2.1 One question to the copilot

```mermaid
flowchart TD
    Q["Analyst question<br/>(FR or EN, transaction open)"] --> K{"Cache hit?<br/>sha256(version · lang · tx · question)"}
    K -- yes --> CA["Pre-computed gpt-5-mini answer<br/>(warmup.py: 40 answers + 6 trials)"] --> OUT
    K -- no --> I["detect_intent()<br/>analyse · habits · before · related<br/>summary · kpi · queue · general"]
    I --> P["_prefetch(): Python calls the tools the intent needs"]

    subgraph TOOLS["tools.py — 9 tools over Fabric Gold (compact JSON)"]
        T1["get_transaction<br/>score · percentile · factors"]
        T2["compare_to_habits"]
        T3["get_customer_profile"]
        T4["get_customer_history"]
        T5["get_digital_events"]
        T6["find_related_cases"]
        T7["get_alert_queue"]
        T8["get_kpis"]
        T9["record_decision"]
        R["recommend()<br/>deterministic rule:<br/>BLOQUER / ESCALADER / VALIDER<br/>+ measured precision"]
        T1 --> R
    end

    P --> TOOLS
    TOOLS --> F["FACTS block<br/>(trimmed item by item, never cut mid-JSON)"]
    F --> M["Messages<br/>1. static system prompt (prompt-cached ~1,400 tokens)<br/>2. language + intent + open tx + FACTS<br/>3. last 2 exchanges<br/>4. question"]
    M --> LLM["Azure OpenAI gpt-5-mini<br/>reasoning_effort=low · streaming<br/>timeout 60 s · 2 retries"]
    LLM -- "needs a missing fact<br/>(≤ 4 rounds)" --> TOOLS
    LLM --> A["Answer in 5 parts<br/>verdict · factors (figures) · reassuring signals<br/>system recommendation · next step"]
    LLM -. "error / no key" .-> OFF["Offline mode<br/>deterministic templates on the same tools"]
    A --> G["Guardrails<br/>off-topic refused · unknown ID handled<br/>no field names · human decides"]
    G --> OUT["Shown streamed + sources (tools) + tokens"]
    OFF --> OUT
    OUT --> LOG[("copilot_log.jsonl<br/>question · intent · tools · tokens<br/>cached tokens · rounds · latency")]
    OUT --> CACHE[("copilot_cache.json<br/>Azure answers only")]
```

Measured: ~3,300 tokens (≈1,400 served from the Azure prompt cache), 1 LLM round, ~7 s per new question; cached demo answers are instant. The recommendation is computed by `tools.recommend` (percentile ≥ 0.998 and ≥ 2 signals → BLOQUER, 94 % precision in validation), so it is identical across questions and languages.

### 2.2 Le Procès (three AI roles)

```mermaid
sequenceDiagram
    autonumber
    actor A as Analyst
    participant UI as Le Procès page
    participant T as tools.py (Fabric facts)
    participant P as AI prosecutor
    participant D as AI defence
    participant J as AI judge
    A->>UI: open a case
    UI->>T: prefetch "summary" facts + recommend()
    par same facts, in parallel threads
        T->>P: facts
        P-->>UI: strongest risk arguments (figures)
    and
        T->>D: facts
        D-->>UI: strongest reassuring arguments (figures)
    end
    UI->>J: both pleas + facts + system recommendation (plain text)
    J-->>UI: verdict, deciding argument, confidence
    UI->>A: typewriter hearing + verdict banner
    A->>T: accept or override → record_decision(source="proces", duration_s)
```

### 2.3 Other AI and analytics features

| Feature | How it works | AI used |
|---|---|---|
| Reconstitution | `features.replay_steps`: transactions + digital events in the hours before the alert, risky signals flagged | gpt-5-mini narrates (copilot intent `before`) |
| Contre-enquête | `features.counterfactual`: neutralise the top SHAP factors (log-odds) one by one → robust / sensitive | none (pure model maths) |
| Constellation | `features.constellation`: points of compromise (lift ×2.5–×4.1) + today's alerts orbiting them (networkx) | none; shown as an investigation lead (not predictive in validation) |
| Impact & processus | `features.impact`, `features.drift` (PSI) | AI cost per alert from the copilot log |

---

## 3. Page workflow (the whole app)

```mermaid
flowchart TD
    START(["Open the app"]) --> SPL["Branded splash<br/>Gold tables load (live Fabric or snapshot)"]
    SPL --> WEL["Welcome dialog (first visit)<br/>Start the tour · Explore freely"]
    WEL --> GUIDE

    subgraph W["Bienvenue"]
        GUIDE["Démarrer ici<br/>4 headline KPIs · 8-step guided tour"]
    end

    subgraph AN["Analyste"]
        QUEUE["File d'alertes<br/>filters · risk colours · alerts/day"]
        TX["Fiche transaction & copilote<br/>score · factors · recommendation<br/>chat · stopwatch · decision · HTML case file"]
        CUST["Vue client 360<br/>profile · habits · timeline · map"]
    end

    subgraph IA["Enquête IA"]
        PROC["Le Procès<br/>prosecutor · defence · judge"]
        REP["Reconstitution<br/>replay of the hours before"]
        CON["Contre-enquête<br/>what-if on SHAP factors"]
        GAL["Constellation<br/>points of compromise"]
    end

    subgraph PI["Pilotage"]
        IMP["Impact & processus<br/>TND saved · false alerts · hours · AI cost · drift"]
        MKT["Marché & benchmarks<br/>public figures · rules audit · time to detect"]
        PERF["Performance du modèle<br/>vs rules engine · recall by type · leaderboard"]
        PBI["Tableau de bord Power BI<br/>secure embed"]
        JOUR["Journal & traçabilité<br/>decisions · copilot log"]
    end

    DEMO["Sidebar: demo cases<br/>obvious fraud · subtle fraud · avoided false positive"]

    GUIDE --> QUEUE
    QUEUE -- "open an alert" --> TX
    DEMO --> TX
    TX --> CUST
    TX -- "Le Procès" --> PROC
    TX -- "Reconstitution" --> REP
    TX -. "same open case" .-> CON
    PROC -- "accept / override verdict" --> DEC
    TX -- "BLOQUER / ESCALADER / VALIDER" --> DEC[("Decision log<br/>decisions.csv → OneLake")]
    GAL -- "open an orbiting alert" --> TX
    DEC --> JOUR
    DEC --> IMP
    IMP --> PERF --> PBI
```

### Demo path (≈ 3 minutes)

```mermaid
flowchart LR
    S1["1 · Démarrer ici"] --> S2["2 · Obvious fraud<br/>TX01555470"] --> S3["3 · Ask the copilot<br/>'Pourquoi suspecte ?'"] --> S4["4 · Le Procès"] --> S5["5 · Reconstitution"] --> S6["6 · Decide < 30 s<br/>(stopwatch)"] --> S7["7 · Avoided false positive<br/>TX01575959 → Contre-enquête"] --> S8["8 · Constellation"] --> S9["9 · Impact & processus"]
```

---

## 4. Where it runs

| | Local (pitch laptop) | Hosted (Streamlit Community Cloud) |
|---|---|---|
| Data | **Live** Fabric SQL endpoint (Entra login via `az login`) | Gold snapshot committed in `app/data/*.parquet` |
| Copilot | Azure OpenAI live + cache | Azure OpenAI if the key is set in Streamlit *Secrets*; otherwise cached gpt-5-mini answers for the demo cases + offline mode |
| Decisions | written to OneLake | kept in the session's container (ephemeral) |
| Secrets | `app/.env` (git-ignored) | Streamlit *Secrets* (never in Git) |
