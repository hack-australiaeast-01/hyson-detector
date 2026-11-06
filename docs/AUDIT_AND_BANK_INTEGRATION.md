# Audit, controls and integration with the bank's IT system

What a bank's audit, IT and compliance teams will ask, what **is built** in Hyson Detector, and what the **production design** is.
Everything marked *built* can be checked in the app or the tests (`tests/test_audit_trail.py`).

## 1. Audit trail — who decided what, on which evidence

| Question from the auditor | Built | Where |
|---|---|---|
| Who took the decision? | Analyst identity stored with every decision (sidebar "Analyste connecté"; production: Entra ID single sign-on) | `tools.record_decision` |
| What did the AI recommend at that moment? | `system_decision`, `system_confidence`, `score_model` frozen in the decision row | Journal page |
| Which model and prompt produced it? | `model_version` (MLflow `hyson-fraud-lightgbm`, = production scores) and `prompt_version` (copilot prompt / cache version) | Journal page |
| How long did it take? | `duration_s` from alert opening to decision (stopwatch) | Transaction page, Impact page |
| Can someone change the log afterwards? | **Tamper-evident chain**: each row stores the SHA-256 of the previous row; editing or deleting any past decision is detected | `tools.verify_journal`, Journal page "Intégrité du journal" |
| Does the analyst follow the AI blindly? | **Override rate** (decision ≠ recommendation) and list of overrides to review | Journal page |
| What did the copilot see and say? | Every LLM call logged: question, intent, tools called, tokens (incl. cached), latency, answer | `data/copilot_log.jsonl`, Journal page |
| Who approved a new data source? | Named approval, versioned data contract, approval / rejection log | "Nouvelle source de données" page |
| What code was running? | Git history + CI tests on every push (`.github/workflows/tests.yml`); notebooks exported from Fabric | GitHub |

Production: the journal is written to append-only storage (Azure Blob immutable / WORM policy, or a Delta table in OneLake with
retention), mirrored to the bank's SIEM (Microsoft Sentinel or equivalent). Today it is a CSV mirrored to OneLake
(`Files/feedback/analyst_decisions/decisions.csv`) plus the hash chain.

## 2. Access and segregation of duties

| Role | Can | Built today | Production |
|---|---|---|---|
| Fraud analyst | Read alerts, ask the copilot, decide | Typed name | Entra ID SSO, conditional access, MFA |
| Supervisor | Second approval ("four eyes") | Rule computed in the decision message: blocks ≥ 5,000 TND and decisions that set aside a recommended BLOQUER are flagged `four_eyes_required` | Approval queue before the action is sent |
| Model validator | Read model card, backtest, fairness, drift | Pages Performance / Robustness, `docs/MODEL_CARD.md` | Independent validation before each new model version |
| Auditor | Read-only journal + logs | Export CSV, integrity check | Read-only role on the immutable store |

Data access: Fabric with the user's Entra ID token (no database password); production adds row-level security and masking of
identifiers for roles that do not need them.

## 3. Integration with the bank's systems

```
card switch / core banking ──(authorisation stream)──► Fabric Eventstream ──► scoring endpoint (MLflow model, < 100 ms)
                                                                                   │ alert
                                                                                   ▼
                                                     Hyson Detector (analyst + copilot) ──► decision journal (hash chain)
                                                                                   │ fraud_decision.v1 (JSON)
                                                                                   ▼
                                           API gateway / Azure Service Bus ──► card management: BLOCK_CARD
                                                                          ├─► core banking: HOLD_TRANSFER
                                                                          ├─► case management: OPEN_CASE / CLOSE_ALERT
                                                                          └─► customer notification (SMS / app)
```

- **Built:** the decision message `fraud_decision.v1` is generated for every decision (Journal page → "Intégration au SI de la
  banque", `tools.decision_event`): action mapped to the right system (transfer → core banking hold, card → block card,
  ESCALADER → level-2 case, VALIDER → close as legitimate), follow-ups, four-eyes flag, and the audit reference (row hash).
  **Nothing is sent** from the demo.
- **Not built (assumed limits):** real-time scoring at authorisation (today batch in Fabric notebooks), the outbound connectors,
  the supervisor approval queue, reconciliation "decided vs executed".

## 4. Data protection

| Topic | What we do |
|---|---|
| Personal data law | Tunisia: Organic Law n° 2004-63 on the protection of personal data (INPDP). The processing would be declared by the bank; purpose = fraud prevention |
| Minimisation | The LLM receives compact facts from approved tools (IDs, amounts, dates, aggregates), never raw tables; no names and no card numbers exist in the data (internal IDs such as CARD004111 only); person search uses approved filters; data onboarding sends only column names and statistics to the AI |
| Model provider | Azure OpenAI in the bank's own Azure tenant; prompts and answers are not used to train the models (Microsoft data-privacy terms for Azure OpenAI) |
| Location | Hackathon resources are in Australia East; production uses the region approved by the bank and its regulator, with a private endpoint and managed identity |
| Secrets | Key only in `.env` (git-ignored) or Streamlit Secrets; repository and history scanned |
| Demo data | 100 % synthetic |

## 5. Model risk and AI regulation

- Model card, out-of-time validation, rolling backtest with confidence intervals, fairness by segment and age, PSI drift,
  MLflow registry, retraining pipeline with a champion/challenger gate: `docs/MODEL_CARD.md`, Robustness page.
- Human oversight: the model ranks, the LLM explains, the analyst decides; override rate monitored.
- EU AI Act (reference for banks working with EU partners): AI used to **detect financial fraud** is explicitly excluded from the
  high-risk "creditworthiness / credit scoring" category (Annex III, point 5(b)); transparency and human oversight still apply here.

## 6. Resilience

| Failure | Behaviour |
|---|---|
| Azure OpenAI down or over budget | Deterministic offline copilot on the same tools; cached answers; hourly cap on the public demo |
| Fabric unreachable | Committed Gold snapshot (same figures), banner shows the source |
| Model degrades | PSI drift and alert-volume monitoring; retrain pipeline; previous MLflow version kept for rollback |
