# How we used AI tools (brief §13 "Usage de GitHub Copilot", §16 rule 4)

The brief allows and encourages AI tools and asks teams to **say how they used them**. This page is the evidence. Keep it factual: the jury can read the Git history (§16 rule 6).

## 1. GitHub Copilot (official delivery accelerator)

Fill one row per real use as you go, with a screenshot in `docs/copilot_evidence/` (file name in the last column). Never invent a row.

| # | When (date/time) | Where (file / notebook / Fabric) | What we asked Copilot | What it produced | What we changed after review | Time saved (estimate) | Screenshot |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |
| 4 | | | | | | | |
| 5 | | | | | | | |

Ideas for rows the jury likes (only if you really did them):
- Generating a Streamlit component or a page skeleton, then adapting it.
- Writing unit tests for the copilot tools (`tools.py`) or the data access layer.
- Refactoring a long notebook cell into functions.
- Writing / translating docs (README, FR ↔ EN labels).
- Commit messages and Git operations (the Copilot agent handled our commits and pushes, with the `Co-authored-by: Copilot` trailer).
- Explaining an error message (e.g. a Spark or Fabric error) and the fix.

**Pitch slide (≈30 s, §17 "4:00–4:30"):** 3 concrete examples from the table, one number ("≈ X h saved"), one sentence on review: "every suggestion was read and tested before commit".

## 2. GitHub Copilot agent mode (VS Code) — what the agent built, tested and reviewed

What the Copilot agent was used for in this project (facts):

| Area | What the Copilot agent did | What the team checked / decided |
|---|---|---|
| Brief | Read the 20-page brief and wrote the English working summary (`BRIEF_SUMMARY.md`) | Team read the original PDF |
| Data audit | Read the exported table schemas; found the period-split bug (234 "test" frauds) and confirmed via SQL that test labels were not leaked (0 test IDs in labels) | Team ran the queries in Fabric |
| Notebooks | First versions of `01_silver_features` and `02_score_explain` (past-only features, temporal split, rules baseline, model, explanations) | Team ran, fixed and extended them in Fabric |
| Power BI | Power BI built as code: `03*_powerbi_dashboard.ipynb` (pbi_* tables → Direct Lake model with DAX measures → report JSON, dark theme, icon navigation, FR/EN pages) | Team chose the design and reviewed every page |
| App | Streamlit app, 9 copilot tools, Azure OpenAI copilot (intent routing, prefetch, streaming, cache), Hyson Detector pages (Le Procès, Reconstitution, Contre-enquête, Constellation, Impact), FR/EN, Power BI embed | Team tested the demo path |
| Tests & deploy | AppTest on every page FR/EN, browser screenshots, live Azure OpenAI tests, secret scan, GitHub repo + push, Streamlit Cloud preparation, architecture diagrams (`docs/ARCHITECTURE.md`) | Team reviewed results and deployed |
| Market research | Searched public sources (EBA/ECB, UK Finance, BCT) and built the "Marché & benchmarks" page: cited benchmarks, same KPIs on our data, Tunisian scenario, rules-engine audit, time to detect | Team checked the sources and the wording of every comparison |
| Reviews | Token-cost review of the copilot (§7.2 of `STATUS.md`), consistency checks between app, dashboard and docs | Team decided which fixes to apply |

**Decided by the team, not by the agent:** the final model and threshold, the demo cases, the design choices, the pitch. Every agent change was run and reviewed before commit.

## 3. Azure OpenAI (in the product, not in development)

The copilot inside the app. Every call is logged (`app/data/copilot_log.jsonl`: question, tools called, tokens, latency) and shown on the "Journal & traçabilité" page. This is product usage, not development help: keep it separate in the pitch.

## 4. Rules we followed with AI tools

- Every generated piece of code was run and checked before it was kept.
- No secrets were ever pasted into an AI tool or the repo (`.env` is git-ignored).
- Data stays synthetic; external public figures (benchmarks) are cited with their source.
- The model scores, the LLM explains, the analyst decides.
