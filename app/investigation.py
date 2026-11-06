"""Juridic investigation v2 (brief §2): Prosecution vs Defence on a numbered evidence board, then a Judge that weighs the evidence.

Evidence board E1…En (built in code, 0 token): the model (score, measured fraud rate, documented recommendation), the customer's habits,
the app events, the personal context (abroad), what happened AFTER the alert up to `as_of` (continuous monitoring), and the most
similar past cases from the behavioural memory with their status as known at the time (RAG).

- Prosecution and Defence (Azure OpenAI, in parallel) may only argue from the board and must cite E-numbers.
- The Judge — the Azure AI Foundry agent `judge-patern` (project proj-fraud-australiaeast), else the same model directly — grades
  each argument's evidence, lists contradictions, compares with the ML model and similar cases, names missing information, and
  returns a structured assessment. Code then checks every cited E-number exists (ungrounded claims are flagged, not shown as facts).
- The Judge may differ from the documented system recommendation only if new evidence justifies it; both are shown; the employee decides.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import time
from datetime import datetime

import pandas as pd

import copilot
import intel
import memory

FOUNDRY_PROJECT = os.getenv("FOUNDRY_PROJECT_ENDPOINT",
                            "https://aoai-fraud-australiaeast-vnxcy.services.ai.azure.com/api/projects/proj-fraud-australiaeast")
JUDGE_AGENT = os.getenv("FOUNDRY_JUDGE_AGENT", "judge-patern")
MODEL = os.getenv("INTEL_DEPLOYMENT", "gpt-6.1-terra")
VERSION = "inv-1"

ADVOCATE = {
    "prosecution": ("Tu es l'ACCUSATION dans une enquête de fraude bancaire. Cherche pourquoi ce comportement pourrait être une fraude : "
                    "motifs suspects, ressemblance avec des fraudes confirmées passées, enchaînements anormaux, liens avec d'autres cartes / "
                    "comptes, ce qui s'est passé APRÈS l'alerte."),
    "defense": ("Tu es la DÉFENSE du client dans une enquête de fraude bancaire. Cherche les explications légitimes : habitudes du client, "
                "contexte (voyage cohérent, lieu connu, puce), faux positifs passés qui ressemblent à ce cas, ce qui contredit le modèle."),
}
ADVOCATE_RULES = ("\nRègles : uniquement le TABLEAU DE PREUVES ; 3 arguments maximum, chacun commence par « • » et cite ses preuves entre "
                  "crochets, ex. [E3, E7] ; chiffre chaque argument ; distingue fait et interprétation ; si ta position est faible, dis-le. "
                  "Termine par « Conclusion : … ». 110 mots maximum. Jamais de religion, santé, famille ou raison supposée d'un voyage. {lang}")
JUDGE = """Tu es le JUGE d'une enquête de fraude bancaire. Tu reçois le TABLEAU DE PREUVES (E1…En), l'argumentation de l'ACCUSATION et
celle de la DÉFENSE. Tu ne choisis pas la partie la plus convaincante : tu pèses la qualité des preuves.
- Pour chaque argument : preuves citées, fiabilité (forte = fait mesuré ou événement daté ; moyenne = comparaison statistique ou cas
  similaires ; faible = interprétation sans preuve), raison.
- Contradictions entre les parties ; accord ou désaccord avec le modèle ML et avec les cas similaires (statut connu à la date).
- Informations manquantes et vérifications à faire.
- Recommandation : reprends la recommandation système SAUF si des preuves postérieures à l'alerte (E-numéros) justifient de la changer ;
  dans ce cas explique pourquoi. La décision finale appartient à l'employé. Jamais de religion, santé, famille, origine.
Réponds UNIQUEMENT en JSON :
{"evaluation": [{"partie": "accusation|défense", "argument": "…", "preuves": ["E1"], "fiabilite": "forte|moyenne|faible", "raison": "…"}],
 "contradictions": ["…"], "accord_modele": "…", "cas_similaires": "…", "informations_manquantes": ["…"],
 "niveau_risque": "élevé|moyen|faible", "confiance": "élevée|moyenne|faible",
 "recommandation": "BLOQUER|ESCALADER|VALIDER", "ecart_avec_systeme": "… ou null",
 "verifications": ["…"], "synthese": "3 phrases maximum"}
{lang}"""


# ---------------------------------------------------------------- evidence board (0 token)
def board(tid, as_of=None, lang="fr"):
    import context
    import tools
    en = lang == "en"
    a = intel._alert_row(tid)
    t = tools.get_transaction(tid)
    h = tools.compare_to_habits(tid)
    ev = []

    def add(kind, text, ts=None):
        ev.append({"id": f"E{len(ev) + 1}", "kind": kind, "text": text, "ts": ts})
    s, rec = t.get("score", {}), t.get("recommandation_systeme") or {}
    tx = t.get("transaction", {})
    add("opération", f"{tx.get('transaction_type')} {tx.get('channel')} {tx.get('entry_mode')} {tx.get('amount_tnd')} TND le {tx.get('timestamp')} · "
                     f"{tx.get('city') or 'en ligne'} ({tx.get('country')}) · statut {tx.get('status')}", tx.get("timestamp"))
    add("modèle ML", f"Niveau {s.get('niveau_risque')}, score {s.get('score_modele')}, rang {s.get('rang_dans_periode')} ; "
                     + (f"{s['fraudes_mesurees_a_ce_score']:.0%} de fraudes mesurées à ce score en validation" if s.get("fraudes_mesurees_a_ce_score") is not None else "sous le seuil d'alerte")
                     + f" ; recommandation système {rec.get('decision')} (confiance {rec.get('confiance')})")
    for f in t.get("facteurs_modele_pour_fraude", [])[:3] + t.get("regles_metier_declenchees", [])[:2]:
        add("facteur de risque", f"{f['facteur']} : {f.get('valeur_observee', '')}" + (f" (habituel {f['valeur_habituelle']})" if f.get("valeur_habituelle") is not None else ""))
    lh = h.get("lecture_habitudes") or {}
    if lh:
        add("habitudes", f"Conforme aux habitudes : {lh.get('conforme_aux_habitudes')} sur {h['historique_avant']['nb_operations']} opérations passées ; "
                         f"écarts : {'; '.join(lh.get('ecarts_nets', [])) or 'aucun'} ; conforme : {'; '.join(lh.get('elements_conformes', [])[:3]) or '—'}")
    seq = h.get("sequence_carte_24h")
    if seq:
        add("carte 24 h", f"{seq['nb_operations']} opérations sur la carte en 24 h, {seq['nb_commercants_jamais_vus']} commerçant(s) jamais vu(s), "
                          f"{seq['nb_refus']} refus")
    st = intel.stream(tid, as_of)
    before = st[(st.phase == "avant") & st.kind.isin(["login_fail", "benef", "device", "pwd", "phone"])] if len(st) else st
    for r in before.itertuples():
        add("application avant", f"{pd.Timestamp(r.ts):%m-%d %H:%M} · {intel.KIND_LABEL[r.kind][0]} · {r.detail}", r.ts)
    if a is not None and str(a.country) != "TN" and a.channel in context.PHYSICAL:
        cr = context.assess(a.to_dict(), a.customer_id, lang="fr")
        if cr.get("score"):
            pro, con = context.evidence(cr, "fr")
            add("contexte personnel", f"Lecture du voyage : {dict((b[0], b[1]) for b in context.BANDS)[cr['score']['band']]} ; cohérent : "
                                      f"{'; '.join(x['text'] for x in pro[:2]) or '—'} ; inquiétant : {'; '.join(x['text'] for x in con[:2]) or '—'}")
    after = st[st.phase == "après"] if len(st) else st
    for r in after.head(8).itertuples():
        add("après l'alerte", f"{pd.Timestamp(r.ts):%m-%d %H:%M} · {intel.KIND_LABEL[r.kind][0]} · {r.detail}", r.ts)
    if len(after) > 8:
        add("après l'alerte", f"… et {len(after) - 8} autre(s) événement(s) jusqu'au {pd.Timestamp(as_of or after.ts.max()):%m-%d %H:%M}")
    trig = intel.triggers(tid, as_of)
    if trig:
        add("surveillance continue", "Réactivation : " + " ; ".join(x["text"] for x in trig))
    cases, stats = memory.similar(tid, k=8, as_of=None, lang="fr")
    for line in memory.evidence_lines(cases, stats, "fr"):
        add("mémoire (cas similaires)", line)
    rel = tools.find_related_cases(tid)
    for pc in (rel.get("points_communs") or [])[:2]:
        add("liens", f"{pc['type']} {pc['identifiant']} : {pc.get('autres_clients', 0)} autres clients, "
                     f"{pc.get('cartes_fraudees_deja_signalees', 0)} cartes déjà fraudées, {pc.get('operations_en_alerte', 0)} alertes")
    return ev, rec, trig, cases, stats


def board_text(ev):
    return "\n".join(f"{e['id']} [{e['kind']}] {e['text']}" for e in ev)


# ---------------------------------------------------------------- LLM calls
def _lang_line(lang):
    return "Answer in English." if lang == "en" else "Réponds en français."


def _chat(system, user, max_tokens=1500):
    kw = dict(model=MODEL, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    kw.update(max_completion_tokens=max_tokens)
    try:
        r = copilot._client().chat.completions.create(**kw)
    except Exception:
        kw["model"] = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        kw["reasoning_effort"] = "low"
        r = copilot._client().chat.completions.create(**kw)
    u = r.usage
    return (r.choices[0].message.content or "").strip(), int(u.total_tokens or 0), kw["model"]


def _foundry_judge(prompt):
    """Call the Azure AI Foundry agent (managed harness): conversation + responses on the agent endpoint, Entra ID auth."""
    import requests
    from azure.identity import AzureCliCredential, DefaultAzureCredential
    try:
        tok = AzureCliCredential().get_token("https://ai.azure.com/.default").token
    except Exception:
        tok = DefaultAzureCredential(exclude_interactive_browser_credential=True).get_token("https://ai.azure.com/.default").token
    base = f"{FOUNDRY_PROJECT}/agents/{JUDGE_AGENT}/endpoint/protocols/openai"
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    conv = requests.post(f"{base}/conversations?api-version=v1", headers=H, json={}, timeout=30)
    conv.raise_for_status()
    r = requests.post(f"{base}/responses?api-version=v1", headers=H, json={"input": prompt, "conversation": conv.json()["id"]}, timeout=180)
    r.raise_for_status()
    j = r.json()
    text = " ".join(c.get("text", "") for o in j.get("output", []) if o.get("type") == "message" for c in o.get("content", []))
    return text.strip(), int((j.get("usage") or {}).get("total_tokens", 0)), f"Foundry agent {JUDGE_AGENT}"


def _parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def ground(judge, ev):
    """Every cited E-number must exist on the board; arguments citing nothing valid are marked ungrounded."""
    ids = {e["id"] for e in ev}
    bad = []
    for a in judge.get("evaluation", []) or []:
        cited = [p for p in a.get("preuves", []) if p in ids]
        a["preuves_valides"] = cited
        a["ancre"] = bool(cited)
        bad += [p for p in a.get("preuves", []) if p not in ids]
    judge["preuves_inexistantes"] = sorted(set(bad))
    return judge


_CACHE = intel.da.DATA / "investigations.json"


def _cache():
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}
    except Exception:
        return {}


def investigate(tid, as_of=None, lang="fr", context_note="", analyst=None, on_stage=None, use_agent=True):
    """Run (or replay) the investigation of `tid` as known at `as_of`."""
    stage = on_stage or (lambda *a: None)
    lang = "en" if lang == "en" else "fr"
    ev, rec, trig, cases, stats = board(tid, as_of, lang)
    key = hashlib.sha256(f"{VERSION}|{lang}|{tid}|{as_of}|{context_note}|{board_text(ev)}".encode()).hexdigest()
    cache = _cache()
    if key in cache:
        out = {**cache[key], "cached": True, "board": ev, "triggers": trig}
        stage("done", out)
        return out
    out = {"board": ev, "system": rec, "triggers": trig, "tokens": 0, "models": []}
    if not copilot.configured():
        out.update(mode="offline", prosecution=None, defense=None, judge=None)
        return out
    t0 = time.time()
    btxt = board_text(ev) + (f"\nE{len(ev) + 1} [contexte ajouté par l'employé] {context_note}" if context_note else "")
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futs = {r: pool.submit(_chat, ADVOCATE[r] + ADVOCATE_RULES.format(lang=_lang_line(lang)), f"TABLEAU DE PREUVES :\n{btxt}", 1800)
                for r in ("prosecution", "defense")}
        for r in ("prosecution", "defense"):
            out[r], tk, mdl = futs[r].result()
            out["tokens"] += tk
            out["models"].append(mdl)
            stage(r, out[r])
    prompt = (JUDGE.replace("{lang}", _lang_line(lang)) + f"\n\nRECOMMANDATION SYSTÈME : {rec.get('decision')} (confiance {rec.get('confiance')})"
              f"\n\nTABLEAU DE PREUVES :\n{btxt}\n\nACCUSATION :\n{out['prosecution']}\n\nDÉFENSE :\n{out['defense']}")
    judge_raw, judge_model = None, None
    if use_agent:
        try:
            judge_raw, tk, judge_model = _foundry_judge(prompt)
            out["tokens"] += tk
        except Exception as exc:
            out["agent_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    if not judge_raw or not _parse_json(judge_raw):
        judge_raw, tk, judge_model = _chat("Tu es un juge d'enquête de fraude. Réponds uniquement en JSON.", prompt, 2500)
        out["tokens"] += tk
    j = _parse_json(judge_raw) or {"synthese": judge_raw, "evaluation": []}
    out["judge"] = ground(j, ev + ([{"id": f"E{len(ev) + 1}"}] if context_note else []))
    out["judge_model"] = judge_model
    out["latency_s"] = round(time.time() - t0, 1)
    out["mode"] = "Azure AI Foundry + Azure OpenAI"
    stage("judge", out["judge"])
    cache[key] = {k: v for k, v in out.items() if k not in ("board", "triggers")}
    _CACHE.write_text(json.dumps(cache, ensure_ascii=False, default=str), encoding="utf-8")
    intel.log_case(tid, "investigation", {"as_of": str(as_of), "recommendation": out["judge"].get("recommandation"),
                                          "system": rec.get("decision"), "risk": out["judge"].get("niveau_risque"),
                                          "judge_model": judge_model, "tokens": out["tokens"], "knowledge": "suspected (AI)"}, analyst)
    return out
