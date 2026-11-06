# Hyson Detector diagrams · Application, demo path, deployment (diagrams 8–9)

Mermaid source of the diagrams shown as images in [../ARCHITECTURE.md](../ARCHITECTURE.md). GitHub renders them below; to regenerate the PNGs run `python docs/diagrams/render.py`.

## Application pages
<!-- img: 08a_app_pages -->
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

## Demo path
<!-- img: 08b_demo_path -->
```mermaid
flowchart LR
    S1["1 · Démarrer ici"] --> S2["2 · Obvious fraud TX01555470"] --> S3["3 · Ask the copilot"] --> S4["4 · Le Procès"] --> S5["5 · Reconstitution"] --> S6["6 · Decide in under 30 s"] --> S7["7 · Avoided false positive TX01575959 → Contre-enquête"] --> S8["8 · Constellation"] --> S9["9 · Impact & Performance"]
```

## Deployment, security and CI/CD
<!-- img: 09_deployment_security -->
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
