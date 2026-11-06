# How we used AI tools (brief §13 "Usage de GitHub Copilot", §16 rule 4)

The brief allows and encourages AI tools and asks teams to **say how they used them**. This page is the evidence. Keep it factual: the jury can read the Git history (§16 rule 6).

## 1. GitHub Copilot (official delivery accelerator)

**GitHub Copilot agent mode in VS Code** was our development partner from the first notebook to the deployment: **36 commits** (2026-11-05 16:54 → 2026-11-06 10:30), every one carrying the `Co-authored-by: Copilot` trailer, ≈ 6,200 lines of app code + 93 automated tests. Each row below is a real request, with the commit that proves it (GitHub → commit hash) and, when useful, a screenshot in [`copilot_evidence/`](copilot_evidence/).

| # | When | Where | What we asked Copilot | What it produced | What the team did / decided | Time saved (estimate) | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | 11-05 afternoon | Fabric notebooks 01 / 02 | "Check the status and finish everything" on the pipeline | Read the exported schemas, found the **period-split bug** (Aug–Sep 2025 train rows labelled "test" → 234 fake test frauds), past-only features (73), multi-model scoring with a LightGBM champion, Gold tables, `assert` against leaks | Ran the notebooks in Fabric (Fabric Copilot helped inside the notebooks), chose the champion rule and the 1 % budget | ≈ 1 day | `3ae7d57`, `notebooks/01`, `02` |
| 2 | 11-05 17:43 | `app/data_access.py` | "Connect Fabric for the data, not just fetch files after downloading" | Live T-SQL on the lakehouse SQL endpoint with the user's Entra token, decisions written back to OneLake, parquet fallback | Signed in with `az login`, tested the app on live data | ≈ 3 h | `2404a7d` |
| 3 | 11-05 20:18 | `app/copilot.py` | "Make Azure OpenAI better — check the localhost and my status, go through all details" | Copilot v4: intent routing + prefetch (1 LLM round), streaming, deterministic recommendation, FR/EN; **≈ 5,200 → 3,300 tokens and 12 → 7 s per question** | Tested the demo cases in the browser and recorded a real decision | ≈ 4 h | `b4844cb` |
| 4 | 11-05 20:56 | `app/studio.py`, `courtroom.py`, `features.py` | "Everyone builds AI workflows — make something unexpected; bank-platform style, name it Hyson Detector, demo guide for a first-time user" | Le Procès (prosecutor / defence / judge), Reconstitution, Contre-enquête, Constellation, Impact & processus, 8-step guided tour, light bank theme | Picked all four ideas, the name, the style and the demo guide | ≈ 1.5 days | `9885aca` · [03_le_proces_verdict.png](copilot_evidence/03_le_proces_verdict.png) |
| 5 | 11-05 21:50 | Fabric notebook `03e_powerbi_dashboard` | "Is everything good for 03e?" | Found the 1,780 vs 1,779 alert count and **4 reasons the notebook failed as a Fabric job** (`%pip`, PBIR report format, update with no result, session stop); ran it in Fabric until *Completed* | Asked for the check, kept the report built as code | ≈ 3 h | `4ed9410` (`notebooks/03e`) |
| 6 | 11-05 22:38 | GitHub, Streamlit Cloud, `docs/` | "Push the work where the brief wants it, deploy on Streamlit, draw the architecture" | Secrets bridge, Gold snapshot for the cloud, cached AI answers, secret scan of files + history, repo, architecture diagrams | Deployed from the team account (`hack-australiaeast-01`) after the admin-permission issue; corrected the AI-tools declaration | ≈ 4 h | `4ed9410`, `c98dc2c`, `cb20d70` |
| 7 | 11-06 00:12 | Whole app | "Act like a judge — a hater — and find what would hit first" | 13 findings fixed: online history since 2025, "hier" in the demo calendar, red error banner, leftover *titanic* cells, 3 different "usual amounts", wording, cost cap, score file in the repo… | **Spotted that "everyone in the table looks suspicious"** → Copilot added the measured-fraud column and "an alert is not a fraud" banner | ≈ 5 h | `cc7a7ca`, `4c86ad3`, `c52f90f` · [06a](copilot_evidence/06a_queue_before_review.png) → [06b](copilot_evidence/06b_queue_after_review.png) |
| 8 | 11-06 01:41 | `app/data_access.py` | "This app has gone over its resource limits" | Measured memory per page, rebuilt the snapshot (categories, float32, freed Arrow buffers): **856 MB with one user → 520 MB with three** | Rebooted the app on Streamlit Cloud | ≈ 2 h | `2d14548` · [07a](copilot_evidence/07a_cloud_over_memory_limit.png) → [07b](copilot_evidence/07b_cloud_after_memory_fix.png) |
| 9 | 11-06 01:13 | `person_search.py`, `onboarding.py` | Ask the AI about a person; onboard a new data source | Read-only search on approved filters (0 token), IDs typed in a question; mapping → translation → accuracy / drift → human approval → data contract | Asked for both features; Copilot also caught a mis-routed demo button before the push | ≈ 6 h | `80fde81` · [08a](copilot_evidence/08a_person_search.png), [08b](copilot_evidence/08b_data_onboarding.png) |
| 10 | 11-06 02:06 → 03:43 | Fabric NB 04, `tests/`, `.github/` | Prove robustness; test everything | Rolling backtest (69.4 % ± 2.1), bootstrap CIs, MLflow model, retrain pipeline, golden-question evaluation (18/18), **49 pytest tests + GitHub Actions**, fairness, prompt-injection guard | Kept the pipeline frozen for the pitch (no re-scoring) | ≈ 6 h | `d4f2291`, `f93ad3f`, `965f769` · [09](copilot_evidence/09_robustness_backtest.png) |
| 11 | 11-06 03:31 | `tools.py`, Journal page | "See other gaps like audit or the bank system" | Audit trail (who, AI recommendation at that time, model / prompt version, **SHA-256 hash chain**), override rate, decision message to card management / core banking (simulated), audit document | Asked for it; reviewed the bank-IT design | ≈ 3 h | `d8d87df` · [10_audit_trail.png](copilot_evidence/10_audit_trail.png) |
| 12 | throughout | Git | Commits, pushes, checks before each push | 30 commits with explicit messages, secret scan + tests before every push, one bad commit detected by CI and fixed in 2 min (`ca12836`) | Chose the repo owner and what goes public | ≈ 1 h | `git log` |

**Total (rough team estimate): ≈ 7 person-days of work delivered in ≈ 11 hours.** Every change was run and tested before commit (AppTest on every page FR/EN, 93 automated tests, live Fabric / Azure OpenAI checks, browser screenshots).

**What Copilot did *not* decide:** the model and the alert threshold, the demo cases, the product ideas and design, what goes public, the pitch.

**Pitch (≈ 30 s, brief §17 "4:00–4:30"):**
> "GitHub Copilot agent mode was our pair-programmer: 36 commits, every one co-authored by Copilot. Three examples: it found the split bug that turned 2025 transactions into fake test frauds; it cut our copilot's cost from 5,200 to 3,300 tokens per question; and when the public app crashed on memory, it brought it from 856 to 520 MB. Roughly seven days of work — and every change was tested before commit, 93 automated tests. Copilot built and checked; we decided."

## 2. GitHub Copilot agent mode (VS Code) — what the agent built, tested and reviewed

What the Copilot agent was used for in this project (facts):

| Area | What the Copilot agent did | What the team checked / decided |
|---|---|---|
| Brief | Read the 20-page brief and wrote the English working summary (`BRIEF_SUMMARY.md`) | Team read the original PDF |
| Data audit | Read the exported table schemas; found the period-split bug (234 "test" frauds) and confirmed via SQL that test labels were not leaked (0 test IDs in labels) | Team ran the queries in Fabric |
| Notebooks | First versions of `01_silver_features` and `02_score_explain` (past-only features, temporal split, rules baseline, model, explanations) | Team ran, fixed and extended them in Fabric |
| Power BI | Power BI built as code: `03*_powerbi_dashboard.ipynb` (pbi_* tables → Direct Lake model with DAX measures → report JSON, dark theme, icon navigation, FR/EN pages) | Team chose the design and reviewed every page |
| App | Streamlit app, 10 copilot tools, Azure OpenAI copilot (intent routing, prefetch, streaming, cache), Hyson Detector pages (Le Procès, Reconstitution, Contre-enquête, Réseau de compromission, Impact), FR/EN, Power BI embed | Team tested the demo path |
| Tests & deploy | pytest suite (`tests/`, 93 tests) + GitHub Actions CI, AppTest on every page FR/EN, browser screenshots, live Azure OpenAI tests, secret scan, GitHub repo + push, Streamlit Cloud preparation, architecture diagrams (`docs/ARCHITECTURE.md`) | Team reviewed results and deployed |
| Market research | Searched public sources (EBA/ECB, UK Finance, BCT) and built the "Marché & benchmarks" page: cited benchmarks, same KPIs on our data, Tunisian scenario, rules-engine audit, time to detect | Team checked the sources and the wording of every comparison |
| Audit & bank IT | Audit trail with hash chain, override rate, decision message to the bank's systems (simulated), `docs/AUDIT_AND_BANK_INTEGRATION.md` | Team asked for the bank's audit / IT view |
| Reviews | Token-cost review of the copilot (§7.2 of `STATUS.md`), consistency checks between app, dashboard and docs | Team decided which fixes to apply |

**Decided by the team, not by the agent:** the final model and threshold, the demo cases, the design choices, the pitch. Every agent change was run and reviewed before commit.

## 3. Azure OpenAI (in the product, not in development)

The copilot inside the app. Every call is logged (`app/data/copilot_log.jsonl`: question, tools called, tokens, latency) and shown on the "Journal & traçabilité" page. This is product usage, not development help: keep it separate in the pitch.

## 4. Rules we followed with AI tools

- Every generated piece of code was run and checked before it was kept.
- No secrets were ever pasted into an AI tool or the repo (`.env` is git-ignored).
- Data stays synthetic; external public figures (benchmarks) are cited with their source.
- The model scores, the LLM explains, the analyst decides.
