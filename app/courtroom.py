"""Le Procès — an AI courtroom for one transaction (prosecutor vs defence, then judge).

All three roles read the SAME facts, fetched from Fabric by the copilot tools (transaction, habits, digital events,
related cases, system recommendation). The prosecutor and the defence plead in parallel; the judge weighs both and
confirms the documented system recommendation (it may flag a contradicting fact, never invent a new decision).
One LLM call per role, no tool calls, cached and logged like the copilot.
"""
import concurrent.futures as cf
import hashlib
import os
import re
import time
from datetime import datetime

import copilot

ROLES = {
    "procureur": {
        "fr": """Tu es le PROCUREUR dans le procès d'une transaction bancaire. Construis l'accusation de fraude.
Règles : uniquement les FAITS fournis ; 3 arguments maximum, chacun chiffré (montant TND, heure, nombre, comparaison aux habitudes) ;
commence chaque argument par « • » ; termine par une phrase « Réquisition : … ». 90 mots maximum. Français. Pas de noms techniques de champs.
Si les faits sont faibles, dis-le honnêtement.""",
        "en": """You are the PROSECUTOR in the trial of a bank transaction. Build the fraud case.
Rules: only the FACTS given; at most 3 arguments, each quantified (TND amount, time, count, comparison with habits);
start each argument with "• "; end with one sentence "Charge: …". 90 words max. English. No technical field names.
If the facts are weak, say so honestly.""",
    },
    "defense": {
        "fr": """Tu es l'AVOCAT DE LA DÉFENSE du client dans le procès d'une transaction bancaire. Défends l'hypothèse d'une opération légitime.
Règles : uniquement les FAITS fournis ; 3 arguments maximum, chacun chiffré (habitudes, lieu connu, puce, journée, appareil connu > 24 h, agence…) ;
commence chaque argument par « • » ; termine par « Plaidoirie : … ». 90 mots maximum. Français. Pas de noms techniques de champs.
Un appareil ou bénéficiaire connu depuis moins de 24 h n'est pas un argument. Si la défense est faible, reconnais-le honnêtement.""",
        "en": """You are the DEFENCE LAWYER of the customer in the trial of a bank transaction. Argue that the operation is legitimate.
Rules: only the FACTS given; at most 3 arguments, each quantified (habits, known place, chip, daytime, device known > 24 h, branch…);
start each argument with "• "; end with "Plea: …". 90 words max. English. No technical field names.
A device or beneficiary known for less than 24 h is not an argument. If the defence is weak, admit it honestly.""",
    },
    "juge": {
        "fr": """Tu es le JUGE. Tu as lu le réquisitoire du procureur et la plaidoirie de la défense, et les FAITS.
Rends le verdict en 4 lignes maximum, 80 mots maximum :
**Verdict : <BLOQUER|ESCALADER|VALIDER>** (confiance …) — reprends EXACTEMENT la recommandation système fournie.
Puis : quel argument l'emporte et pourquoi (chiffré) ; l'argument de l'autre partie que tu retiens ; la vérification à faire par l'analyste.
Si un fait contredit nettement la recommandation système, signale-le en une phrase sans changer le verdict. La décision finale appartient à l'analyste.
Français. Ne recopie jamais de données brutes.""",
        "en": """You are the JUDGE. You have read the prosecutor's charge, the defence plea and the FACTS.
Give the verdict in at most 4 lines, 80 words max, entirely in English:
**Verdict: <BLOCK|ESCALATE|VALIDATE>** (… confidence) — use EXACTLY the system recommendation provided.
Then: which side wins and why (quantified, say "Prosecution" or "Defence"); the argument from the other side you keep; the check the analyst should do.
If a fact clearly contradicts the system recommendation, flag it in one sentence without changing the verdict. The analyst has the final word. Never paste raw data.""",
    },
}


def _facts(transaction_id):
    facts = copilot._prefetch("summary", transaction_id, lambda n: None)
    used = [{"name": n, "args": copilot._dumps(a), "prefetched": True} for n, a, _ in facts]
    text = "\n".join(f"- {n} → {copilot._compact(r, 2600)}" for n, a, r in facts)
    reco = next((r.get("recommandation_systeme") for n, a, r in facts if n == "get_transaction" and isinstance(r, dict)), None)
    return text, used, reco


LANG_LINE = {"fr": "Rédige toute ta réponse en français.",
             "en": "Write your whole answer in English: translate every French label or value of the facts into English "
                   "(e.g. « Carte nationale utilisée à l'étranger » → national card used abroad). No French words."}
_FR_WORDS = set("le la les des du une est pour avec sur dans au aux et ou opération opérations client montant carte habitudes "
                "commerçant étranger connu jamais refus heure mais car donc cette ce".split())
_EN_WORDS = set("the and with for is was this that customer amount card habits operation merchant abroad known never declined "
                "hour but because so are has".split())


def wrong_language(text, lang):
    """True when the text is mostly in the other language (word counts on common function words)."""
    words = re.findall(r"[a-zà-ÿ]+", (text or "").lower())
    fr, en = sum(w in _FR_WORDS for w in words), sum(w in _EN_WORDS for w in words)
    return (fr > en and fr >= 3) if lang == "en" else (en > fr and en >= 3)


def _call(role, lang, facts_text, extra=""):
    client = copilot._client()
    head = "FACTS" if lang == "en" else "FAITS"
    messages = [{"role": "system", "content": ROLES[role][lang]},
                {"role": "user", "content": f"{head}:\n{facts_text}{extra}\n\n{LANG_LINE[lang]}"}]
    kwargs = dict(model=os.environ["AZURE_OPENAI_DEPLOYMENT"])
    if copilot._is_reasoning():
        kwargs.update(max_completion_tokens=1600, reasoning_effort=os.getenv("COPILOT_REASONING", "low"))
    else:
        kwargs.update(temperature=0.2, max_tokens=350)
    tok = {"prompt": 0, "completion": 0, "total": 0, "cached_prompt": 0}
    text = ""
    for attempt in range(2):                      # one corrective retry if the model answered in the other language
        resp = client.chat.completions.create(messages=messages, **kwargs)
        u = resp.usage
        details = getattr(u, "prompt_tokens_details", None)
        for k, v in (("prompt", u.prompt_tokens), ("completion", u.completion_tokens), ("total", u.total_tokens),
                     ("cached_prompt", getattr(details, "cached_tokens", 0) or 0)):
            tok[k] += v or 0
        text = (resp.choices[0].message.content or "").strip()
        if not wrong_language(text, lang) or attempt:
            break
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Rewrite exactly the same content entirely in English, same format." if lang == "en"
                      else "Réécris exactement le même contenu entièrement en français, même format."}]
    return copilot.polish(text, lang), tok


def _offline(lang, reco, transaction_id):
    import tools
    t = tools.get_transaction(transaction_id)
    en = lang == "en"
    risk = t.get("facteurs_modele_pour_fraude", []) + t.get("regles_metier_declenchees", [])
    calm = t.get("facteurs_modele_rassurants", []) + t.get("regles_rassurantes", [])

    def line(f):
        v = f.get("valeur_observee")
        u = f.get("valeur_habituelle")
        return f"• {f['facteur']}" + (f" : {v}" if v is not None else "") + ((f" (usual {u})" if en else f" (habituel {u})") if u is not None else "")
    pros = "\n".join(line(f) for f in risk[:3]) or ("• No strong risk factor." if en else "• Aucun facteur de risque fort.")
    dfn = "\n".join(line(f) for f in calm[:3]) or ("• No reassuring factor." if en else "• Aucun élément rassurant.")
    dec = (reco or {}).get("decision", "ESCALADER")
    judge = (f"**Verdict : {dec}** (confiance {(reco or {}).get('confiance', 'moyenne')}) — règle documentée du système."
             if not en else f"**Verdict: {dec}** — documented system rule.")
    return {"procureur": pros, "defense": dfn, "juge": judge}


def trial(transaction_id, lang="fr", on_stage=None):
    """Run (or replay from cache) the trial. Returns {"procureur", "defense", "juge", "recommendation", "tokens", ...}."""
    lang = "en" if lang == "en" else "fr"
    stage = on_stage or (lambda role, text: None)
    key = hashlib.sha256(f"proces-p3|{copilot.CACHE_VERSION}|{lang}|{transaction_id}".encode()).hexdigest()
    cache = copilot._cache
    if key in cache and (copilot.configured() or os.getenv("COPILOT_OFFLINE", "0") != "1"):
        out = {**cache[key], "cached": True}
        for role in ("procureur", "defense", "juge"):
            stage(role, out[role])
        return out
    start = time.time()
    facts_text, used, reco = _facts(transaction_id)
    if not copilot.configured():
        out = _offline(lang, reco, transaction_id)
        for role in ("procureur", "defense", "juge"):
            stage(role, out[role])
        out.update(mode="hors-ligne (règles)", tokens={"total": 0}, recommendation=reco, cached=False,
                   latency_s=round(time.time() - start, 2))
        return out
    tokens = {"prompt": 0, "completion": 0, "total": 0, "cached_prompt": 0}
    out = {}
    with cf.ThreadPoolExecutor(max_workers=2) as pool:      # prosecutor and defence plead at the same time
        futs = {role: pool.submit(_call, role, lang, facts_text) for role in ("procureur", "defense")}
        for role in ("procureur", "defense"):
            out[role], tok = futs[role].result()
            for k in tokens:
                tokens[k] += tok.get(k, 0)
            stage(role, out[role])
    dec_en = {"BLOQUER": "BLOCK", "ESCALADER": "ESCALATE", "VALIDER": "VALIDATE"}
    conf_en = {"faible": "low", "moyenne": "medium", "élevée": "high"}
    r = reco or {}
    if lang == "en":
        reco_txt = (f"{dec_en.get(r.get('decision'), r.get('decision'))} ({conf_en.get(r.get('confiance'), r.get('confiance'))} "
                    f"confidence); concordant signals: {', '.join(r.get('signaux_concordants', [])) or 'none'}")
        labels = ("SYSTEM RECOMMENDATION", "PROSECUTION CHARGE", "DEFENCE PLEA")
    else:
        reco_txt = (f"{r.get('decision')} (confiance {r.get('confiance')}) ; signaux concordants : "
                    f"{', '.join(r.get('signaux_concordants', [])) or 'aucun'}")
        labels = ("RECOMMANDATION SYSTÈME", "RÉQUISITOIRE DU PROCUREUR", "PLAIDOIRIE DE LA DÉFENSE")
    extra = (f"\n\n{labels[0]} : {reco_txt}\n\n{labels[1]} :\n{out['procureur']}\n\n{labels[2]} :\n{out['defense']}")
    out["juge"], tok = _call("juge", lang, facts_text, extra)
    for k in tokens:
        tokens[k] += tok.get(k, 0)
    stage("juge", out["juge"])
    out.update(mode=f"Azure OpenAI ({os.environ['AZURE_OPENAI_DEPLOYMENT']})", tokens=tokens, recommendation=reco,
               tools=used, latency_s=round(time.time() - start, 2), cached=False)
    cache[key] = out
    copilot._save_cache()
    copilot._log({"ts": datetime.now(), "question": "Le Procès (procureur · défense · juge)", "context_tx": transaction_id,
                  "lang": lang, "intent": "proces", "mode": out["mode"], "cached": False, "tools": used, "tokens": tokens,
                  "rounds": 3, "latency_s": out["latency_s"], "answer": out["juge"]})
    return out
