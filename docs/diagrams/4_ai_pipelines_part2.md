# Hyson Detector diagrams · AI pipelines 5–8 (person search, data onboarding, copilot evaluation, Power BI as code)

Mermaid source of the diagrams shown as images in [../ARCHITECTURE.md](../ARCHITECTURE.md). GitHub renders them below; to regenerate the PNGs run `python docs/diagrams/render.py`.

## AI pipeline 5: person search
<!-- img: 07e_person_search -->
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

## AI pipeline 6: new data source onboarding
<!-- img: 07f_data_onboarding -->
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

## AI pipeline 7: copilot evaluation
<!-- img: 07g_copilot_evaluation -->
```mermaid
flowchart LR
    GS["14 golden questions<br/>brief §9.7 + unknown ID + off-topic + prompt injection"] --> ASK["copilot.ask() exactly as in the app"]
    ASK --> RE["Re-run the tools it used → facts it saw"]
    RE --> CK["0-token checks<br/>decision = system rule · key facts · numbers grounded ≥ 90 %<br/>5 sections · English only · refusals · no prompt / key leak"]
    CK --> REP[("docs/COPILOT_EVAL.md · copilot_eval.json<br/>14/14 pass · 99.3 % numbers grounded")]
    REP --> APPV["Shown on Performance → Robustesse et gouvernance"]
```

## AI pipeline 8: Power BI as code
<!-- img: 07h_powerbi_as_code -->
```mermaid
flowchart LR
    G[("gold_alert_queue · gold_alert_explanations · gold_model_*")] --> T["pbi_* tables · FR + EN labels<br/>exact counts from gold_scores × labels"]
    T --> SM["Direct Lake model sm_fraud_copilot<br/>semantic-link-labs · DAX measures · relationship"]
    SM --> RJ["Report JSON generated in Python<br/>8 pages FR/EN · icon navigation"]
    RJ --> API["Fabric REST updateDefinition"]
    API --> RP["Report 'Fraud Copilot — Dashboard'"]
    RP --> EMB["Embedded in the app (viewer signs in with Entra ID)"]
```
