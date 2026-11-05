"""Pre-compute copilot answers for the demo cases before the pitch.

    python warmup.py            # French (default)
    python warmup.py fr en      # both languages

Uses exactly the same questions as the app buttons (copilot.SUGGESTIONS), so the live demo replies instantly.
Any other question still goes to Azure OpenAI live. Answers are stored in data/copilot_cache.json.
"""
import sys
import time

import copilot
import data_access as da

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    langs = [a for a in sys.argv[1:] if a in ("fr", "en")] or ["fr"]
    q = da.queue()
    demos = q[q.demo_case.notna()].transaction_id.tolist()
    print("Source :", da.source().describe(), "| démo :", demos, "| langues :", langs)
    total = 0
    for lang in langs:
        i = 0 if lang == "fr" else 1
        jobs = [(tid, s[i]) for tid in demos for s in copilot.SUGGESTIONS] + [(demos[0], g[i]) for g in copilot.GLOBAL_QUESTIONS]
        for tid, question in jobs:
            t0 = time.time()
            out = copilot.ask(question, context_tx=tid, lang=lang)
            status = "cache" if out.get("cached") else ("ERREUR " + out["error"][:60] if out.get("error") else "ok")
            total += out["tokens"]["total"]
            print(f"{lang} | {tid} | {question[:52]:52s} | {out.get('intent', ''):8s} | {status} | "
                  f"{out['tokens']['total']} tok ({out['tokens'].get('cached_prompt', 0)} cached) | {time.time() - t0:.1f} s")
    print(f"Total tokens: {total}")
