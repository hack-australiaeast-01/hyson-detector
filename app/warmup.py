"""Pre-compute copilot answers for the demo cases (run once before the pitch): python warmup.py

Answers are cached in data/copilot_cache.json, so the live demo replies instantly. Any new question still goes live.
"""
import sys
import time

import copilot
import data_access as da

QUESTIONS = ["Pourquoi cette transaction est-elle suspecte ?",
             "Cette transaction ressemble-t-elle au comportement habituel du client ?",
             "Que s'est-il passé juste avant cette opération ?",
             "D'autres clients sont-ils passés par le même commerçant ou appareil ?",
             "Pourquoi cette alerte pourrait-elle ne pas être une fraude ?",
             "Rédige le résumé d'investigation pour le dossier."]
GLOBAL = ["Combien d'alertes inutiles évites-tu par rapport au moteur de règles actuel ?",
          "Montre-moi les 10 transactions les plus risquées du flux du jour."]

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    q = da.queue()
    demos = q[q.demo_case.notna()].transaction_id.tolist()
    print("Source :", da.source().describe(), "| démo :", demos)
    jobs = [(tid, question) for tid in demos for question in QUESTIONS] + [(demos[0], g) for g in GLOBAL]
    for tid, question in jobs:
        t0 = time.time()
        out = copilot.ask(question, context_tx=tid)
        status = "cache" if out.get("cached") else ("ERREUR " + out["error"][:60] if out.get("error") else "ok")
        print(f"{tid} | {question[:55]:55s} | {status} | {out['tokens']['total']} tokens | {time.time() - t0:.1f} s")
