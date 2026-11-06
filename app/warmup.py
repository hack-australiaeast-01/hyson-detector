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
        if "--no-trial" not in sys.argv:
            import courtroom
            for tid in demos:                       # Le Procès: prosecutor + defence + judge for each demo case
                t0 = time.time()
                out = courtroom.trial(tid, lang)
                total += out["tokens"].get("total", 0)
                print(f"{lang} | {tid} | {'Le Procès (3 rôles)':52s} | proces   | {'cache' if out.get('cached') else 'ok'} | "
                      f"{out['tokens'].get('total', 0)} tok | {time.time() - t0:.1f} s")
        if "--no-deep" not in sys.argv:
            import deepsearch
            w = deepsearch.watch("test")
            w = w.assign(score=q.set_index("transaction_id").loc[w.index, "score_model"].values,
                         rank=(w.level == "priorite").astype(int)).sort_values(["rank", "score"], ascending=False)
            # the 6 flagged alerts shown as buttons, the page's default alert, and the demo cases
            for tid in dict.fromkeys(list(w.head(6).index) + list(w.index[:1]) + demos):
                t0 = time.time()
                out = deepsearch.investigate(tid, lang)
                total += out["tokens"].get("total", 0)
                print(f"{lang} | {tid} | {'Enquête approfondie (1 appel)':52s} | deep     | {'cache' if out.get('cached') else 'ok'} | "
                      f"{out['tokens'].get('total', 0)} tok | {time.time() - t0:.1f} s")
    print(f"Total tokens: {total}")
