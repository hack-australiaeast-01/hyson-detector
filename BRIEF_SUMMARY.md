# AI Banking Copilot for Fraud Detection on Microsoft Fabric — working brief (English)

Source: `Hackathon_AI_Banking_Copilot_Brief_Participants_v2.pdf` (20 pages, French). This file is everything needed to build, in order.

---

## 1. The mission in one paragraph

Build a **copilot for a fraud analyst** at a fictional Tunisian retail bank. It must **detect** suspicious transactions (score), **explain** why (numbers compared to the customer's own history), **talk** with the analyst in natural language, and help them **decide**: BLOCK / ESCALATE / VALIDATE. The analyst always makes the final decision.

**Baseline to beat:** the bank's current rule engine gives **85% false positives** (precision ~15%) and **misses 58% of frauds** (recall ~42%). You must beat it and **prove it with numbers**.

**Three golden rules**
1. The copilot speaks only from data: every claim is checkable (amount, date, id, comparison to history).
2. A transaction is judged only with its **past**. Never use information from after the transaction.
3. Show **transaction → score → explanation → decision** in under 30 seconds of demo.

**Flow:** Ingestion (Fabric) → Detection (features + model) → Explanation (factors + Azure OpenAI) → Interaction (analyst ↔ copilot) → Decision → Improvement (analyst feedback).

**Not acceptable:** static dashboard only, model without UI, scoring without explanation, generic chatbot not tied to the data, no demoable interface.

---

## 2. Stack

| Component | Role | Status |
|---|---|---|
| Microsoft Fabric (Lakehouse, Notebooks) | Ingestion, storage, features, scoring | **Expected** |
| GitHub + GitHub Copilot | Versioning + faster delivery (code, tests, UI, docs) | **Expected** |
| Azure OpenAI | Explanations + dialogue (**function calling recommended**) | Recommended |
| Streamlit | Analyst UI | Recommended |
| Python (pandas, PySpark) | Data prep, features | Recommended |
| scikit-learn / LightGBM / XGBoost / SHAP | Scoring + explainability | Free choice |

Power BI is allowed as a complement, but never replaces the interactive UI or the copilot.
Other LLMs: allowed if justified. **AI tools are allowed and encouraged — say how you used them** (rule 16.4). The jury can inspect code, notebooks and **Git history**.

---

## 3. The data (100% synthetic)

2,500 customers, 18 cities, 1 Jan → 30 Sep 2026. Amounts in **TND, 3 decimals**. Timestamps in **Tunis time**. Fraud rate **~0.65%** (heavily imbalanced). Full data dictionary in **`README.md` — read it first.**

| File | Content | Rows | Priority |
|---|---|---|---|
| `transactions_train.csv` | Jan → Jul transactions | 333,059 | **Essential** |
| `fraud_labels_train.csv` | fraud 0/1, `fraud_scenario`, `fraud_reported_date` | 333,059 | **Essential** |
| `customers.csv` | age, segment, income, city, KYC, digital usage | 2,500 | **Essential** |
| `transactions_test.csv` | Aug → Sep, **no labels** (to score) | 101,730 | **Essential** |
| `merchants.csv` | merchants, e-commerce sites, ATMs | 2,621 | Recommended |
| `cards.csv` | card type, international or not, limits, contactless | 2,940 | Recommended |
| `legacy_rule_alerts_train.csv` | current rule-engine alerts + analyst decision | 6,324 | Recommended (= your baseline) |
| `digital_events.csv` | logins, failures, new device, new beneficiary, password reset, phone change | 192,401 | Bonus (key for account takeover) |
| `sample_submission.csv` | submission format | 101,730 | If ranking |

**Minimum viable:** transactions_train + fraud_labels_train + customers.

**Join keys**
- transaction ↔ label / legacy alert: `transaction_id`
- transaction ↔ customer ↔ card: `customer_id`, `card_id`
- transaction ↔ merchant / ATM / site: `merchant_id`
- MOBILE/WEB transaction ↔ digital events of same session: `session_id`
- shared entities across customers: `device_id`, `beneficiary_id`

**Time split (mandatory, never random)**

| Period | Use |
|---|---|
| Jan → May | Train |
| Jun → Jul | Validation (honest performance) |
| Aug → Sep | Final scoring = "today's queue" in the demo, optional submission |

**Codes to know**

| Column | Values | Notes |
|---|---|---|
| `channel` | TPE (in-store), DAB (ATM), EN_LIGNE, MOBILE, WEB | MOBILE/WEB have `session_id` |
| `entry_mode` | CHIP, SANS_CONTACT, MAGSTRIPE, ECOM_3DS, ECOM_SANS_3DS, APP_AUTH | MAGSTRIPE easy to clone; contactless no PIN under 200 TND |
| `transaction_type` | ACHAT, RETRAIT, VIREMENT, PAIEMENT_FACTURE, RECHARGE | Transfers: no card/merchant, have `beneficiary_id` |
| `status` / `decline_reason` | APPROUVEE / REFUSEE + reason | Reasons: insufficient funds, limit, wrong PIN, bad CVV, bad expiry, card not international, card blocked. **Declined attempts can be fraud.** |
| `event_type` | CONNEXION, AJOUT_APPAREIL, AJOUT_BENEFICIAIRE, REINITIALISATION_MOT_DE_PASSE, MODIFICATION_NUMERO_TELEPHONE | With status SUCCES/ECHEC, channel (incl. AGENCE, CENTRE_APPEL), auth_method |

Empty cells are normal (no card for a transfer, no device in-store, no coordinates online).

---

## 4. Fraud types (`fraud_scenario`) — use for explanations and per-type recall

| Type | What happens | Signals |
|---|---|---|
| CARD_TESTING | Stolen card tested with tiny online payments, then big buys | Bursts of micro-amounts, serial declines, unusual device/IP, easy-to-resell categories |
| ACCOUNT_TAKEOVER | Fraudster takes online banking, empties account by transfers | Digital events just before: login failures, new device, phone change, new beneficiary; amount vs habits |
| CARTE_CLONEE_ETRANGER | Card copy used physically abroad | Country never visited physically, entry mode, real customer active in Tunisia at the same time |
| SKIMMING_DAB | Card copied at an ATM, then emptied by withdrawals | Close withdrawals, unusual city, odd hours, limits hit |
| CARTE_VOLEE_SANS_CONTACT | Stolen physical card used without PIN | Successive contactless payments just under the limit, unknown merchants |
| FRAUDE_EN_LIGNE_DISCRETE | Spread over days, modest amounts | Combination of weak signals: devices, IP, categories, rhythm. **Hardest.** |

**Organised fraud hint:** several victims share a common point (merchant, ATM, website, device) before being defrauded → a **graph / common-point** feature is a real plus. Only count frauds **already reported** before the transaction (`fraud_reported_date < timestamp`) — the only legitimate use of that column as a feature.

---

## 5. False-positive traps (legit behaviour that looks like fraud) — the copilot must explain these too

| Legit situation | Looks like fraud because | What settles it |
|---|---|---|
| Trip abroad (holiday, Omra, business) | New country, high amounts, magstripe on old terminals | Ticket/hotel bought before, no physical activity in Tunisia during stay, IP from visited country |
| Summer holiday in another city | Unusual city, withdrawals away from home | Coherent sequence over days, holiday merchants |
| One-off big purchase (furniture, electronics, jewellery) | > 3,000 TND | Local merchant, chip, daytime, no other signal |
| New phone | New device, sometimes followed by a transfer | OTP enrolment, no login failures, Tunisian IP |
| Forgotten password, phone change in branch | Sensitive events | Branch channel, no abnormal transfer after |
| VPN, shared computer (office, cybercafé) | Foreign IP, device shared by customers | Stable history, usual amounts |
| Ramadan evenings, Eid shopping | Late operations, higher spend | Calendar |

**2026 calendar effects**
- 18 Feb → 19 Mar: Ramadan (late activity until 1 am, groceries, Omra)
- 10 → 19 Mar: Eid clothing purchases · 20–21 Mar Eid al-Fitr, 27–28 May Eid al-Adha: reduced activity
- 18 → 26 May: big cash withdrawals (sheep purchase)
- 25th → 3rd of each month: payday, more transactions
- Jul → Aug: summer travel · 1 → 20 Sep: back to school · Saturday busier, Sunday quieter

Legacy example: one customer's 10-day Istanbul trip in July = **21 alerts, all false**.

---

## 6. Ambition levels (pick Bronze first, then climb)

| | Bronze (solid) | Silver (convincing) | Gold (expert) |
|---|---|---|---|
| Data | transactions + labels + customers | + cards, merchants, legacy alerts | + digital_events, common-point analysis |
| Features | 8–10 behavioural (amount vs habits, novelty, velocity, hour) | 20–30: geography, channel, limits, profile | + digital + graph features (shared merchant/ATM/device) |
| Detection | Heuristic score or simple model (LogReg, tree) | Gradient boosting, temporal validation, numeric comparison to rules | + **SHAP per transaction**, threshold chosen by analyst capacity |
| Copilot | Top factors injected in prompt, questions on one transaction | Function calling: customer history, habit comparison, alert queue | Multi-tool: link cases, write investigation summary, explain false positives |
| UI | Alert queue, transaction page, chat | + Customer 360 (timeline, map), decision | + common-point graph, decision log + feedback |

> "A perfectly demonstrated Bronze beats an unfinished Gold." Wire the copilot to a simple score **early**, then improve the score.

---

## 7. Feature engineering — past only

Every feature must translate into one sentence of explanation.

```python
tx = tx.sort_values(["customer_id", "timestamp"])
g = tx.groupby("customer_id")["amount_tnd"]
tx["avg_amount_before"] = g.transform(lambda s: s.shift(1).expanding().mean())   # shift(1) excludes current tx
tx["amount_ratio"] = tx["amount_tnd"] / tx["avg_amount_before"]
tx["is_new_country"] = ~tx.duplicated(["customer_id", "country"])
```

PySpark velocity (past only):
```python
from pyspark.sql import functions as F, Window
tx = spark.table("bronze_transactions_train").withColumn("ts", F.col("timestamp").cast("timestamp").cast("long"))
w1h = Window.partitionBy("card_id").orderBy("ts").rangeBetween(-3600, -1)
tx = tx.withColumn("card_tx_last_1h", F.count("*").over(w1h))
```

| Family | Features | Explanation sentence |
|---|---|---|
| Amount | ratio to past mean/median, z-score, amount / monthly income, amount / card limit | "Amount 5× the customer's usual average (151 TND)." |
| Time | hour, night, weekday, payday, Ramadan/Eid, time since previous tx | "3 am while the customer never operates at night." |
| Velocity | count & sum over 10 min / 1 h / 24 h (card, customer, device), recent declines | "7 attempts in 25 minutes, 4 declined." |
| Novelty | new country, city, merchant, category, device, beneficiary, IP country | "First physical payment outside Tunisia in the whole history." |
| Geography | distance from home, speed since previous physical tx | "Shenzhen 2 h after a Kairouan withdrawal: impossible travel." |
| Channel & security | magstripe, contactless, no 3DS, decline reason, non-international card | "Magstripe used although the card has a chip." |
| Digital banking | login failures 24 h, device enrolled recently, password reset, phone change, beneficiary added just before | "Beneficiary added 4 min before the transfer, from a device enrolled the same day." |
| Profile | age, segment, income, tenure, KYC, card type | "Retired customer with a national card: online purchase abroad is atypical." |
| Graph | merchants/ATMs shared with already-reported frauds, devices shared between customers | "12 other cards used at this ATM were defrauded within 3 weeks." |

---

## 8. Detection and scoring

1. **Heuristic points score first** (1 hour): new country +3, amount > 3× average +2, burst +3 … → first queue, baseline, plan B, easy to explain.
2. **Supervised:** Logistic regression (readable) → gradient boosting (HistGB / LightGBM / XGBoost, usually best). Handle imbalance: `class_weight`, `scale_pos_weight`, or undersample legit.
3. Hybrid (model + a few explicit business rules) is fine if justified.
4. **Validate on time:** train Jan→May, validate Jun→Jul.

**Metrics**

| Metric | Why |
|---|---|
| ~~Accuracy~~ | A model detecting nothing already has 99.3% |
| **PR-AUC (average precision)** | Main metric |
| **Precision & recall at top 1%** | Analysts can handle ~1,000 alerts over two months |
| Comparison to rule engine | Precision ~15%, recall ~42% = your reference |
| Recall per fraud type | Shows strengths and weaknesses (honesty is valued) |

**Explainability table:** for every alerted transaction store 3–5 top factors in e.g. `gold_alert_explanations`: factor name, observed value, usual value, contribution (SHAP / LogReg contributions / triggered rules). **The copilot reads this table instead of inventing.**

**Pitfalls**

| Pitfall | Fix |
|---|---|
| Features computed over the whole period (future leak) | Past windows, `shift(1)`, `expanding()` |
| `fraud_scenario` or `fraud_reported_date` as direct features | Target/analysis only (except graph trick) |
| Random train/val split | Temporal split |
| Optimising accuracy | PR-AUC, top 1% |
| IDs as numeric features | Never |
| LLM computes the score | Model scores, LLM explains |
| Thousands of rows in the prompt | Tools that return aggregates |

---

## 9. The copilot

Principle: **Question → Azure OpenAI picks a tool → tool queries Gold tables → numeric facts (JSON) → sourced answer.** The LLM asserts nothing its tools didn't return.

**Recommended tools**

| Tool | Returns |
|---|---|
| `get_alert_queue(date, n)` | Riskiest transactions of a day with score + top factors |
| `get_transaction(transaction_id)` | Detail, score, risk factors |
| `get_customer_profile(customer_id)` | Profile + habits: avg amount, countries, cities, hours, devices, beneficiaries |
| `compare_to_habits(transaction_id)` | Numeric gaps between tx and history |
| `get_customer_history(customer_id, days)` | Recent transactions and events |
| `get_digital_events(customer_id, around)` | Logins, devices, beneficiaries, phone changes around an operation |
| `find_related_cases(transaction_id)` | Other cards/customers sharing merchant, ATM, device or beneficiary |
| `record_decision(transaction_id, decision, comment)` | Saves BLOCK / ESCALATE / VALIDATE + comment |

**Suggested system prompt (keep it in French)**
```
Tu es le copilote de l'analyste fraude de la Banque. Tu réponds en français,
de façon concise, factuelle et structurée.
Règles :
- N'affirme que ce que les outils t'ont renvoyé. Cite montants, dates et identifiants.
- Si une information manque, dis-le et propose la vérification à faire.
- Ne calcule jamais toi-même un score : utilise celui fourni par le modèle.
- Distingue les faits (données) de ton interprétation.
- Si l'opération semble légitime, explique aussi pourquoi.
- Termine par une recommandation : BLOQUER, ESCALADER ou VALIDER, avec un niveau
  de confiance. La décision finale appartient à l'analyste.
```

**Answer format:** 1) Verdict (risk level + model score) · 2) Top factors (max 3, numbered, vs habits) · 3) Context (profile, recent activity, digital events) · 4) Reassuring elements · 5) Recommendation + confidence.

**Two reference cases from the training data (use them to test)**
- **TX00267400 (fraud):** physical payment in Shenzhen; all 155 previous physical ops in Tunisia; 783.611 TND = 5.2× average (151 TND); ATM withdrawal of 800 TND in Shenzhen 13 min earlier with magstripe; customer 37, Particulier, Kairouan; no ticket/hotel → **BLOCK card CARD001261**. Later same card used at a Kairouan ATM → clone confirmed.
- **TX00283105 (false positive avoided):** 3,086 TND in Istanbul; flights bought 19 and 24 June; no physical activity in Tunisia since 30 June; coherent Istanbul payments since 1 July; chip not magstripe; jewellery ~2× p95 but Professional with 4,893 TND income → **VALIDATE** (maybe notify customer). That trip raised 21 legacy alerts, all false.

**Questions the jury may ask live**
- Why is this transaction suspicious? / Main risk factors?
- Show me the 10 riskiest transactions from yesterday.
- Does this look like the customer's usual behaviour?
- Summarise why this alert should be prioritised.
- What happened in the app just before this transfer?
- Did other customers use the same merchant or ATM?
- Why is this alert NOT fraud?
- Write the investigation summary for the case file.
- How many useless alerts do you avoid compared to the current rule engine?

Quality of answers > number of questions.

**Guardrails:** temperature 0–0.2 · clean handling of unknown id / off-topic · **log questions, tools called and answers** (regulatory traceability) · human decides · **no keys in GitHub** (env vars / ignored `.env`).

---

## 10. Analyst UI (Streamlit)

| Screen | Content | Tip |
|---|---|---|
| Alert queue | Transactions by score, filters (date, channel, type, risk level) | Colour by risk, today's alert count |
| Transaction page | Detail, score, 3 factors, decision buttons | **Demo highlight: everything visible without scrolling** |
| Customer 360 | Profile, habits, timeline of tx + digital events, map | `st.map` with lat/lon, highlight the alerted op |
| Copilot | Chat, suggested questions as buttons | Pass the open transaction as context automatically |
| Decision & feedback | Block / escalate / validate + comment, decision log | Shows the improvement loop |
| Dashboard (optional) | Alert volume, comparison to rule engine | One chart is enough |

**Smooth demo:** precompute scores + explanations in Fabric (never train in the app) · load Parquet or filtered Gold with `st.cache_data` · prepare **3 demo cases: obvious fraud, subtle fraud, avoided false positive** · record a **backup video**.

Skeleton:
```python
import pandas as pd, streamlit as st
st.set_page_config(page_title="Copilote Fraude", layout="wide")
@st.cache_data
def load_alerts(): return pd.read_parquet("gold_alert_queue.parquet")
alerts = load_alerts()
tx_id = st.sidebar.selectbox("Alerte", alerts["transaction_id"])
st.dataframe(alerts[alerts.transaction_id == tx_id])
history = st.session_state.setdefault("history", [])
for m in history: st.chat_message(m["role"]).write(m["content"])
if q := st.chat_input("Posez votre question sur cette alerte…"):
    a = ask_copilot(q, context_tx=tx_id)
    history += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    st.rerun()
```

---

## 11. Reference architecture on Fabric

```
CSV files → Fabric Lakehouse (Bronze → Silver → Gold) → Fabric Notebooks (features + scoring)
          → Azure OpenAI (explanation + dialogue) → Streamlit (analyst UI)
Across everything: GitHub + GitHub Copilot (notebooks, app, prompts, tests)
```

| Layer | Where | Content |
|---|---|---|
| Bronze | Lakehouse Files + Delta | CSVs as-is: `bronze_transactions_train`, `bronze_customers`, … |
| Silver | Delta | Typed, cleaned, joined: `silver_transactions` (train + test + customer + card + merchant) |
| Gold | Delta | `gold_features`, `gold_scores` (score + factors), `gold_customer_profile`, `gold_alert_queue`, `gold_alert_explanations` |
| Scoring | Fabric notebook (PySpark/pandas, MLflow optional) | Train, temporal validation, score Aug–Sep |
| App | Streamlit + Azure OpenAI | Reads Gold, calls LLM with tools |

Bronze load (Fabric notebook) — upload CSVs to `Files/hackathon/` first:
```python
files = ["customers","cards","merchants","transactions_train","transactions_test",
         "fraud_labels_train","legacy_rule_alerts_train","digital_events"]
for f in files:
    df = spark.read.option("header", True).option("inferSchema", True).csv(f"Files/hackathon/{f}.csv")
    df.write.mode("overwrite").format("delta").saveAsTable(f"bronze_{f}")
```

**Streamlit ↔ Fabric:** Option A — query Gold via the Lakehouse **SQL analytics endpoint** with Entra auth. Option B (plan B) — export Gold to Parquet and read locally, while clearly showing the Fabric pipeline upstream.

If Fabric or Azure OpenAI is unreachable: tell organisers immediately, keep working locally (pandas, Parquet), switch back ASAP.

---

## 12. Plan and roles

| Phase | Time share | Milestone |
|---|---|---|
| 1. Framing + ingestion | 10% | Data in Fabric (Bronze), roles assigned, level chosen |
| 2. Exploration + features | 20% | Gold feature table + 2–3 business insights to tell |
| 3. Scoring | 20% | Score validated on Jun→Jul, compared to rule engine |
| 4. Explanation + copilot | 25% | Copilot answers the first 4 jury questions |
| 5. UI + integration | 15% | End-to-end demo works |
| 6. Pitch + rehearsal | 10% | Timed pitch, frozen demo cases, backup video |

Roles (can be combined): Data engineer (Lakehouse, Bronze/Silver/Gold, export) · Data scientist (features, model, validation, factors) · AI engineer (tools, system prompt, guardrails, question tests) · Front/UX (Streamlit, demo path) · Product owner/pitch (vision, demo cases, storytelling, timing).

**Two-day mapping (suggestion)**
- **Day 1 AM:** Bronze load, read README.md, Silver join, heuristic score → first `gold_alert_queue`.
- **Day 1 PM:** past-only features, LogReg + HistGB, Jun–Jul validation vs legacy, `gold_alert_explanations`. Streamlit skeleton reading the heuristic queue.
- **Day 2 AM:** copilot tools + function calling, the 2 reference cases, decision log, Customer 360.
- **Day 2 PM:** freeze demo cases, submission CSV, README, pitch rehearsal ×3, backup video.

---

## 13. Deliverables

| Deliverable | Content |
|---|---|
| Working app | Alert/transaction queue, explicit score or prioritisation, simple navigation demoable in minutes |
| **Copilot (mandatory)** | Chat, free or semi-guided questions, contextual answers, clear explanations |
| Demo | Real (from data) or simulated case, **live interaction** in the pitch, clear justification |
| Technical walkthrough | Architecture, Fabric's role, model choice, validation performance |
| GitHub Copilot usage | Concrete examples: generated components, tests, refactoring, time saved |
| GitHub repo | Code, exported Fabric notebooks, `requirements.txt`, README on how to run |
| Score file (optional) | See below |

**Optional score submission** — one row per `transactions_test.csv` transaction:
```
transaction_id,fraud_score,is_alert
TX00333060,0.0213,0
TX00333061,0.9731,1
```
`fraud_score` required (higher = more suspicious), `is_alert` optional. Jury computes **PR-AUC** + precision/recall at **top 1%**. Bonus ranking only; **top teams' code is checked for future leakage.**

---

## 14. Judging grid

| Criterion | What the jury looks at | Weight |
|---|---|---|
| Business relevance | Prioritisation, decision support, fewer false positives | 20% |
| Detection quality | Approach, temporal validation, vs rule engine, no leakage | 20% |
| **Explanation & copilot** | Grounded, numeric, useful answers — **including legit cases** | **25%** |
| Experience & demo | Fluidity, clarity, storytelling, live interaction | 15% |
| Tech coherence | Clear roles of Fabric, Azure OpenAI, GitHub Copilot; readable architecture | 15% |
| Delivery | Pitch + answers to jury questions | 5% |

(Organisers also told us token use on Foundry/Azure OpenAI and Fabric capacity count — keep the cache, budget and token log.)

**Rules:** synthetic data is enough (cite any external public data) · no post-transaction info for scoring · test labels hidden, validate on Jun–Jul · AI tools allowed and encouraged — **state how you used them** · no secrets in the repo · jury may inspect code, notebooks and Git history.

---

## 15. Pitch (5 min, live demo in the centre)

| Time | Content |
|---|---|
| 0:00–0:45 | Problem in numbers: 85% false positives, 58% of frauds missed |
| 0:45–3:00 | Live: alert → transaction page → question to copilot → decision. Then an avoided false positive |
| 3:00–4:00 | Under the hood: Fabric pipeline, model, validation vs rule engine |
| 4:00–4:30 | How GitHub Copilot (and other AI tools) saved time |
| 4:30–5:00 | Known limits and next steps |

> "Less noise, more explanation, more value for the analyst."

---

## 16. How our existing kit maps to this (Desktop\dsi-hackathon)

| Need | Kit piece | Change needed |
|---|---|---|
| Bronze/Silver/Gold notebooks | `notebooks/01–03` | Point at the 8 CSVs; add past-only window features; temporal split Jan–May / Jun–Jul |
| Leakage check | `src/profile_data.py` | Drop `fraud_scenario`, `fraud_reported_date`, legacy alert outcome from features |
| Training + metrics | `src/train.py` | Add **PR-AUC + precision/recall @ top 1%**, recall per `fraud_scenario`, legacy rule comparison |
| Per-transaction factors | permutation importance + percentiles | Upgrade to **SHAP per transaction** (Gold level) or LogReg contributions → `gold_alert_explanations` |
| LLM wrapper | `agent/foundry_client.py` | Keep (cache, budget, token log). Add `tools=` support for function calling |
| Agent | `agent/qa_agent.py` (router, 1 tool) | Swap tools for the 8 listed above; keep "small model routes, max 2 calls" |
| UI | FastAPI `app/` | **Rebuild in Streamlit** (recommended); keep rule-based fallback text if LLM fails |
| Decisions | `docs/decisions.md` | Log: model choice, threshold = analyst capacity (~1,000 alerts / 2 months), Streamlit vs FastAPI |
| Secrets | `.env.example` | Rename to `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY` if organisers use those names |

**First 3 actions now:** 1) open `README.md` of the dataset; 2) load the 8 CSVs to Bronze; 3) build the heuristic score + `gold_alert_queue` so the UI and copilot can start in parallel.
