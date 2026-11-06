# Hyson Detector diagrams · AI pipelines 1–4 (copilot, Le Procès, Enquête approfondie, Reconstitution)

Mermaid source of the diagrams shown as images in [../ARCHITECTURE.md](../ARCHITECTURE.md). GitHub renders them below; to regenerate the PNGs run `python docs/diagrams/render.py`.

## AI pipeline 1: copilot question to answer
<!-- img: 07a_copilot_pipeline -->
```mermaid
flowchart TD
    Q["Analyst question · FR/EN · transaction open"] --> ID{"ID typed in the question?"}
    ID -- "TX… unknown" --> NF["Guardrail: 'introuvable' · 0 token · no decision"]
    ID -- "TX… known" --> CTX["That transaction becomes the context"]
    ID -- "none" --> CTX2["Open transaction is the context"]
    CTX & CTX2 --> K{"Cache hit?"}
    K -- yes --> CA["Pre-computed gpt-5-mini answer"]
    K -- no --> I["detect_intent<br/>analyse · habits · before · related · summary · priority<br/>kpi · queue · person · person_id · general"]
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

## AI pipeline 2: Le Procès
<!-- img: 07b_le_proces -->
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

## AI pipeline 3: Enquête approfondie
<!-- img: 07c_enquete_approfondie -->
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

## AI pipeline 4: Reconstitution
<!-- img: 07d_reconstitution -->
```mermaid
flowchart LR
    TX["Open alert"] --> RS["replay_steps(hours before)<br/>transactions + digital events merged on one timeline"]
    RS --> FL["Signals flagged in red<br/>failed login · new device · new beneficiary · burst · night"]
    FL --> PLAY["Step-by-step animation · lanes · map"]
    PLAY --> NAR["'Narrate' → copilot intent 'before'<br/>gpt-5-mini tells the sequence from the facts"]
```
