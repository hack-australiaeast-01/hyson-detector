# Hyson Detector — Handoff (2026-11-06, 20:45)

Everything needed to pick the project up: what exists, where it lives, how to run it, what is left, and what not to touch.
Detailed history: [STATUS.md](STATUS.md) §7 (dated work log). Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Jury Q&A: [JURY_HANDBOOK.md](JURY_HANDBOOK.md).
The earlier [COPILOT_HANDOFF.md](COPILOT_HANDOFF.md) is the original day-1 task list, kept for history.

**Principle everywhere: the model scores, the AI explains, the employee decides.**

---

## 1. State in one table

| Item | State | Where |
|---|---|---|
| Code | ✅ pushed, `main` = `ffae177`, CI green | https://github.com/hack-australiaeast-01/hyson-detector |
| Tests | ✅ 169 pytest, offline, ~3 min | `tests/`, GitHub Actions `.github/workflows/tests.yml` |
| Public app | 🟡 runs, **AI off** until the key is pasted in Streamlit Secrets (§4.1) | https://hyson-detector.streamlit.app |
| Local app | ✅ live Microsoft Fabric + Azure OpenAI (needs `az login`) | `cd app; streamlit run app.py` |
| Fabric | ✅ workspace `ws-hack-fraud-australiaeast`, lakehouse `lh_fraud` (schemas bronze → meta), Power BI, MLflow | §3 |
| Azure AI | ✅ `aoai-fraud-australiaeast-vnxcy` (gpt-5-mini, gpt-6.1-terra, text-embedding-3-small) + Foundry agent `judge-patern` | §3 |
| Slides, rehearsal, backup video | ❌ not started | §4 |

**Headline result (validation Jun–Jul 2026, out-of-time):** at the top 1 % (1,779 alerts) the model catches **718 frauds vs 117**
for the current rules engine, with **1,061 false alerts vs 3,221**. PR-AUC 0.646 (rules 0.014). Backtest over 4 periods: top-1 %
recall **69.4 % ± 2.1**. Pitch line: *"Half the alerts, 6× more frauds caught, 67 % fewer false alerts — and it holds on every
period we tested."*

---

## 2. What was built (this session, in order)

| # | Block | Commit | Key files |
|---|---|---|---|
| 1 | Fabric pipeline: silver features (73, past-only), LightGBM champion + SHAP, gold tables, submission | `3ae7d57` … `4ed9410` | `notebooks/01`, `02` |
| 2 | Analyst app + copilot with 10 tools, intent routing, 1 LLM round, offline mode, cache | `b4844cb` … `cc7a7ca` | `app/app.py`, `copilot.py`, `tools.py` |
| 3 | Studio pages: Le Procès, Reconstitution, Contre-enquête, Réseau de compromission, Impact, Marché | `9885aca`, `965f769` | `studio.py`, `courtroom.py`, `market.py` |
| 4 | Robustness & governance: backtest, bootstrap CIs, MLflow model, retrain pipeline, golden-question eval (18/18) | `d4f2291` | `notebooks/04`, `app/eval_copilot.py` |
| 5 | Audit trail (hash chain) + bank IT message, fairness, model card | `d8d87df`, `f93ad3f` | `tools.py`, `docs/AUDIT_AND_BANK_INTEGRATION.md`, `docs/MODEL_CARD.md` |
| 6 | Nazar evil-eye work agent (commands 0 token, decisions only after confirmation) + 3D robot (Voice mode) | `a46a2e2` … `2d3c63c` | `nazar.py`, `nazar_avatar.py` |
| 7 | AI assistant as first page: natural language → guarded SQL on a star schema; notebook 05 row-by-row quality (41 rules) | `e61cc16` | `assistant.py`, `askdata.py`, `notebooks/05` |
| 8 | Personal context (the bank CEO's "be human" principle): is this operation coherent with this customer's life — ROC-AUC 0.858 on 2026 | `1ef4e0a` | `context.py`, `ctxpage.py`, `build_context.py` |
| 9 | Continuous intelligence: case file that reopens on new events, behavioural memory RAG (16,302 cases), prosecution / defence / Foundry judge, steering drilldown | `6ae58c3` | `intel.py`, `memory.py`, `investigation.py`, `casepage.py`, `steering.py` |
| 10 | Lakehouse reorganised: `dbo` → bronze · quality · silver · gold · ml · mart · serving · meta (layout as code) | `90e4a61`, `dbfac78` | `app/layout.py`, `notebooks/06`, `fabric/repoint_items.py` |
| 11 | Universal banking integration: any bank, any schema → discovery, AI mapping, readiness, approval, activation, bank model, per-bank RAG, REST API | `616e067` | `canonical.py`, `discovery.py`, `mapper.py`, `readiness.py`, `tenants.py`, `tenant_model.py`, `tenant_rag.py`, `api.py`, `integpage.py` |
| 12 | Visible form fields + AI reporting engine (plain-language request → verified, audience-adapted report → approval → PDF/DOCX/HTML/XLSX, FR/EN/AR) | `ffae177` | `report_*.py`, `reportpage.py` |

**The app: 21 pages in 6 groups** — Assistant (AI assistant) · Analyste (alert queue, transaction & copilot, investigation case,
customer 360, personal context) · Enquête IA (deep search, Le Procès, reconstitution, counter-inquiry, compromise network) ·
Pilotage (fraud intelligence, **AI reports**, impact, market, model performance, Power BI, audit log) · Données (**bank
integration**, new data source) · Démo (guided tour). Nazar is the floating eye button on every page.

---

## 3. Where everything lives

### Microsoft Fabric (tenant cshift.onmicrosoft.com)
- Workspace `ws-hack-fraud-australiaeast`, lakehouse **`lh_fraud`** (schema-enabled). Map of every table: `app/layout.py` (`TABLES`,
  `fq()`), catalogue in `meta.table_catalog`, migration log `meta.migration_log`.
- Schemas: `bronze` (raw, copy job `cj_bronze_load`) · `quality` (41 rules, issues, quarantine) · `silver` · `gold` (scores, alert
  queue, explanations) · `ml` (model metrics, robustness) · `mart` (star schema for ask-the-data) · `serving` (Power BI tables) · `meta`.
- Files: `landing/partner_feeds`, `exports/app_snapshot`, `exports/submission`, `feedback/analyst_decisions`, `ml/robustness`.
- Notebooks 01 · 02 · 03e · 04 · 05 · 06; pipeline `pl_hyson_retrain` (created, **never run**); Power BI semantic model
  `sm_fraud_copilot` + report "Fraud Copilot — Dashboard" (Direct Lake, built by notebook 03e — do not edit by hand).
- Deploy a notebook: `python fabric/deploy_notebook.py notebooks/<nb>.ipynb [--run]` (backs up the current definition to
  `fabric/backups/`, git-ignored).
- The Lakehouse "tables" REST API does not work on schema-enabled lakehouses: use the SQL endpoint or OneLake DFS.

### Azure (subscription 242ac13a-…, resource group `rg-hack-fraud-australiaeast`)
- Azure OpenAI `aoai-fraud-australiaeast-vnxcy`: deployments `gpt-5-mini` (copilot, assistant, reports), `gpt-6.1-terra`
  (investigation agents), `text-embedding-3-small` (memory, 256 dims).
- Azure AI Foundry project `proj-fraud-australiaeast`, agent **`judge-patern`** (Entra token, scope `https://ai.azure.com/.default`).
- `az` sometimes asks for MFA: run the exact `az login … --claims-challenge …` command it prints.

### Configuration (names only — values are in `app/.env`, never in Git)
| Variable | Used for |
|---|---|
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` | every AI feature |
| `INTEL_DEPLOYMENT`, `EMBEDDING_DEPLOYMENT`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_JUDGE_AGENT` | investigation agents, memory, judge |
| `COPILOT_HOURLY_CAP` (400 public), `COPILOT_MAX_TOKENS`, `COPILOT_TIMEOUT`, `COPILOT_OFFLINE=1` (force rules) | cost and safety |
| `DATA_SOURCE` (`fabric` / `local`), `FABRIC_SQL_ENDPOINT`, `FABRIC_DATABASE`, `FABRIC_WORKSPACE_ID`, `FABRIC_LAKEHOUSE_ID`, `ODBC_DRIVER` | live Fabric |
| `PBI_REPORT_ID`, `PBI_TENANT_ID` | Power BI embed |
| `HYSON_PLATFORM_KEY`, `HYSON_TENANTS_DIR`, `HYSON_REPORTS_DIR`, `HYSON_RATE_PER_MIN`, `HYSON_MAX_UPLOAD_MB` | banking API, tenant / report storage |

The ready-to-paste Streamlit secrets file is kept **outside the repo** (in the Copilot session folder,
`streamlit_cloud_secrets.toml`); the template without values is `app/.streamlit/secrets.toml.example`.

### Repository map
- `app/` — Streamlit app, copilot, tools, every engine (see §2). `app/data/` = committed snapshot (Gold + star schema 30 MB +
  copilot cache) used by the public app and the tests. `app/samples/banks/` = 3 simulated banks for the integration
  (`truth.json` = control totals).
- `notebooks/` — Fabric notebooks (exported with outputs) + generators `gen_nb05.py`, `gen_nb06.py`.
- `fabric/` — deployment and repointing scripts, `environment.yml`, retrain pipeline definition.
- `docs/` — architecture (12 sections, diagrams in `docs/img` + Mermaid in `docs/diagrams`), model card, audit, copilot eval,
  GitHub Copilot usage evidence.
- `submission/submission.csv` — 187,628 rows, 1,876 alerts.

---

## 4. To do — in this order

### Before the pitch (only the team can do these)
1. 🔴 **Turn the AI on in the public app** (it shows "L'IA n'est pas connectée sur ce serveur"): share.streamlit.io →
   *hyson-detector* → ⋮ → Settings → **Secrets** → paste the whole secrets file → Save → ⋮ → **Reboot app**.
2. 🔴 **Reboot the public app after every push** (Streamlit Cloud keeps old page modules in memory; the reboot also installs the
   new report libraries).
3. 🔴 **Slides**: problem, live demo, architecture (`docs/img/`), results + robustness, the CEO's "be human" example, universal
   integration, AI reports, prototype → production, limits.
4. 🔴 **Rehearse 3 × 5 min + record a backup video** of the demo path.
5. 🟡 Restart the local app (the one on port 8501 was started before today's changes).

### Demo day checklist
- Open the public app 5 minutes before (it sleeps; first load ≈ 20 s). "Over its resource limits" → ⋮ → Reboot.
- Pitch laptop: `az login` → `cd app` → `streamlit run app.py` → the chips must show **Fabric live** and **Azure OpenAI**.
- Browser zoom 80 % on a 1366×768 projector.
- Demo cases (June, ground truth known): **TX01555470** obvious fraud → BLOQUER · **TX01585580** subtle card testing → BLOQUER ·
  **TX01575959** false positive avoided → VALIDER · **TX01631347** case file: ESCALADER at the alert, BLOQUER at +24 h ·
  **TX01589761** shared ATM (skimming) · **TX01890379** an Aug–Sep alert.
- Integration demo: page *Intégration bancaire* → "Parcours complet" on **Nordic Pay** (≈ 10 s), then show *Valider* and *Exploiter*.
- Report demo: page *Rapports IA* → example "Rapport trimestriel détaillé sur la fraude aux DAB…" → Analyser → Générer (≈ 4 s) → Aperçu → approve → PDF.
- Do **not**: run notebooks 01/02 or `pl_hyson_retrain` (re-scoring changes every demo ID), click "Rafraîchir depuis Fabric"
  during the pitch, or edit the Power BI report by hand.

### After the hackathon
1. **Rotate the Azure OpenAI key** (it was shared in chat) — then update `app/.env` and the Streamlit Secrets.
2. Publish a Fabric Environment from `fabric/environment.yml`, then schedule `pl_hyson_retrain`.
3. Fabric clean-up: old semantic model `Saitaflex-model` (last checked present at 04:00).
4. Decide whether the personal e-mail visible in the public Git history is acceptable.

---

## 5. How to run and verify

```powershell
# local app on live Fabric + Azure OpenAI
az login --tenant 2db552ee-04d3-40c4-b4a6-87474f06a6d5
cd app; streamlit run app.py

# tests (offline: snapshot data, no Fabric, no tokens)
pip install -r app/requirements-api.txt pytest
python -m pytest -q                      # 169 passed

# copilot answers (after any prompt / tool change): bump CACHE_VERSION, then
cd app; python warmup.py fr en; python eval_copilot.py     # must stay 18/18, commit app/data/copilot_cache.json

# universal banking API
$env:HYSON_PLATFORM_KEY = "<long random secret>"
cd app; uvicorn api:app --port 8600      # docs on http://localhost:8600/docs

# rebuild the simulated banks (needs Fabric)
cd app; python build_bank_fixtures.py
```

Commit routine used all along: run the tests offline, revert `app/data/*.parquet` files the app only rewrote, check that the key
is not in the index (`git grep --cached -F <key>` must return nothing), commit with the
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer, push, check CI, reboot the public app.

---

## 6. Rules the project follows (keep them)
- **Data:** features use only the past of each transaction; split by time, never random; test labels never used or shown;
  `gender`, IDs, `fraud_scenario`, `fraud_reported_date` never features (except frauds *already reported*).
- **AI:** the LLM never computes a fraud score or a figure — numbers come from SQL / tools, a documented rule recommends, the
  employee decides. AI text is grounded (copilot 99.5 % of cited numbers; reports reject any paragraph with a number not in the
  evidence). Security findings are indicators to verify, never claims of an attack.
- **Privacy:** aggregates only in ask-the-data (groups of ≥ 5), no sensitive inference in personal context (no religion,
  family or health), sensitive columns never mapped and erased at activation, ids pseudonymised per bank (HMAC).
- **Traceability:** every decision, approval, mapping version, model approval and report is in a SHA-256 hash chain.
- **Multi-bank:** each bank isolated (own keys, data, model, memory, reports, audit); nothing goes live without a named approval.

---

## 7. Known limits (say them before the jury does)
- Batch scoring, not at authorisation time; the retraining pipeline exists but has never run (frozen demo).
- The 15 original Hyson pages read the Hyson tenant; a newly onboarded bank gets its generated workspace (dashboard, queue,
  memory, real time, reports) and a capability-gated module list, not every page yet. Tenant storage is local files
  (production: one OneLake lakehouse per bank, Key Vault, Entra ID).
- Public app = committed snapshot (no live Fabric); "related cases" there only see the 1,814 alert customers.
- AI writing in reports, the agents' debate and the mapping review were tested offline only (no paid calls in tests).
- Confirmed fraud labels stop on 2026-07-31: Aug–Sep reports show suspected alerts only, and say so.
- The unsupervised behaviour score for banks without labels is weak alone (ROC-AUC 0.67–0.70): it orders the review, it does not decide.
- Fairness: alert rates are even (0.9–1.1 %) but retirees / 60+ get lower precision and recall — shown, to monitor.
- Audit / bank IT: analyst name typed (no SSO yet), four-eyes rule flagged not enforced, decision message to core banking
  generated but not sent.
- The 3D robot needs internet (three.js CDN); voice uses the browser's speech services.
- Public app memory: generating a report adds ≈ 110 MB (cap ≈ 690 MB).

---

## 8. Ideas for next steps (not started)
- Wire the Hyson pages (queue, case, trial) to tenant data so a new bank gets every page.
- Real-time scoring with Eventstream + Eventhouse; Entra ID SSO and a supervisor approval queue (four eyes).
- Azure AI Search for the bank's procedures in the RAG; Azure AI Speech instead of browser voices.
- Deep-learning challengers (sequence model, graph network, autoencoder) validated with the same 4-period backtest.
