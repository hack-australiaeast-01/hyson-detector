"""Fraud-analyst copilot: Azure OpenAI function calling over tools.py (brief §9).

- The model scores, the LLM only explains facts returned by tools.
- Token discipline: small max_tokens, low temperature, cache of identical questions, every call logged.
- If Azure OpenAI is not configured or fails, a deterministic offline answer is built from the same tools.
"""
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import tools

APP_DIR = Path(__file__).parent
load_dotenv(APP_DIR / ".env")
LOG_FILE = APP_DIR / "data" / "copilot_log.jsonl"
CACHE_FILE = APP_DIR / "data" / "copilot_cache.json"
MAX_TOOL_ROUNDS = 4
MAX_TOKENS = int(os.getenv("COPILOT_MAX_TOKENS", "600"))
TOOL_RESULT_CHARS = 3500

SYSTEM_PROMPT = """Tu es le copilote de l'analyste fraude de la Banque. Tu réponds en français, de façon concise, factuelle et structurée.
Règles :
- N'affirme que ce que les outils t'ont renvoyé. Cite montants (TND), dates et identifiants.
- Niveaux de risque à écrire tels quels : FAIBLE / MOYEN / ELEVE (tout en français).
- N'invente jamais un identifiant : utilise get_transaction (fourni pour la transaction ouverte), puis utilise le customer_id qu'il renvoie pour les autres outils
  (get_customer_profile avec before_transaction_id = la transaction analysée, pour n'utiliser que le passé).
- Pour analyser une transaction, appelle get_transaction PUIS compare_to_habits (écarts au passé du client : pays, ville, commerçant, heure, mode de saisie).
- Pour toute opération MOBILE/WEB ou VIREMENT, et pour toute question sur l'application, les connexions, l'appareil ou « ce qui s'est passé avant »,
  appelle aussi get_digital_events(customer_id, around=transaction_id) et cite les événements (heure, type, statut, IP pays).
- Pour les questions sur d'autres clients, commerçants, DAB ou appareils communs, appelle find_related_cases.
- Si une information manque, dis-le en une phrase et propose la vérification à faire.
- Ne calcule jamais toi-même un score : utilise celui fourni par le modèle (score_modele, percentile, niveau de risque).
- Distingue les faits (données) de ton interprétation.
- Si l'opération semble légitime, explique aussi pourquoi (puce, journée, ville et pays habituels, commerçant local, voyage cohérent...).
- N'appelle record_decision que si l'analyste demande explicitement d'enregistrer une décision.
- Un appareil ou bénéficiaire vu seulement dans les dernières 24 h n'est PAS rassurant (il peut appartenir au fraudeur) :
  seul « connu_depuis_plus_de_24h = true » est rassurant.
- Recommandation : risque ELEVE (percentile ≥ 0.99) avec au moins deux facteurs concordants (ex. échecs de connexion + bénéficiaire
  récent, déplacement impossible, rafale) → BLOQUER ; risque élevé mais un seul facteur ou facteurs contradictoires, ou risque MOYEN
  → ESCALADER ; risque FAIBLE avec éléments rassurants → VALIDER. Donne un niveau de confiance. La décision finale appartient à l'analyste.
Pour l'analyse d'une transaction, réponds en EXACTEMENT 5 sections (titres en gras, 170 mots maximum) :
1. **Verdict** : niveau de risque et score du modèle.
2. **Facteurs principaux** : trois au maximum, chacun chiffré et comparé aux habitudes du client.
3. **Contexte** : profil, activité récente, événements digitaux utiles (ou ce qui manque).
4. **Éléments rassurants** : ce qui modère le risque.
5. **Recommandation** : BLOQUER / ESCALADER / VALIDER + confiance.
Pour les autres questions (file d'alertes, KPI, comparaison au moteur de règles), réponds brièvement et chiffré, sans recommandation BLOQUER/ESCALADER/VALIDER.
Pour un résumé d'investigation, rédige un paragraphe de dossier (faits, chronologie, conclusion) de 150 mots maximum."""



def configured():
    if os.getenv("COPILOT_OFFLINE", "0") == "1":      # force offline mode (tests, no paid calls)
        return False
    return all(os.getenv(k) for k in ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"])


def _client():
    from openai import AzureOpenAI
    return AzureOpenAI(azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=os.environ["AZURE_OPENAI_API_KEY"],
                       api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))


def _log(entry):
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _is_reasoning():
    return os.getenv("AZURE_OPENAI_DEPLOYMENT", "").lower().startswith(("gpt-5", "o1", "o3", "o4"))


def _complete(client, messages):
    kwargs = dict(model=os.environ["AZURE_OPENAI_DEPLOYMENT"], messages=messages, tools=tools.TOOL_SCHEMAS)
    if _is_reasoning():  # gpt-5 / o-series: no temperature, budget includes hidden reasoning tokens
        return client.chat.completions.create(max_completion_tokens=MAX_TOKENS * 4, reasoning_effort=os.getenv("COPILOT_REASONING", "low"), **kwargs)
    return client.chat.completions.create(temperature=0.1, max_tokens=MAX_TOKENS, **kwargs)


def _load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    except (ValueError, OSError):
        return {}


def _save_cache():
    try:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, default=str), encoding="utf-8")
    except OSError:
        pass


_cache = _load_cache()


def ask(question, context_tx=None, history=None):
    """Return {"answer", "tools", "tokens", "mode", "cached", "latency_s"}."""
    key = hashlib.sha256(f"{context_tx}|{question.strip().lower()}".encode()).hexdigest()
    if key in _cache and "record_decision" not in str(_cache[key]["tools"]):
        out = {**_cache[key], "cached": True}
        _log({"ts": datetime.now(), "question": question, "context_tx": context_tx, "mode": out["mode"], "cached": True,
              "tools": out["tools"], "tokens": {"prompt": 0, "completion": 0, "total": 0}})
        return out
    start = time.time()
    if configured():
        try:
            out = _ask_llm(question, context_tx, history or [])
        except Exception as exc:
            out = _ask_offline(question, context_tx)
            out["answer"] = f"⚠️ Azure OpenAI indisponible ({type(exc).__name__}) — réponse hors-ligne.\n\n" + out["answer"]
            out["error"] = str(exc)[:300]
    else:
        out = _ask_offline(question, context_tx)
    out["latency_s"] = round(time.time() - start, 2)
    out["cached"] = False
    if not out.get("error") and "record_decision" not in str(out["tools"]):
        _cache[key] = out
        _save_cache()
    _log({"ts": datetime.now(), "question": question, "context_tx": context_tx, "mode": out["mode"], "cached": False,
          "tools": out["tools"], "tokens": out["tokens"], "latency_s": out["latency_s"], "answer": out["answer"],
          "error": out.get("error")})
    return out


def _ask_llm(question, context_tx, history):
    client = _client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    used = []
    if context_tx:
        # Pre-inject the open transaction (saves one tool round, i.e. one full re-send of the prompt).
        facts = tools.get_transaction(context_tx)
        used.append({"name": "get_transaction", "args": json.dumps({"transaction_id": context_tx}), "prefetched": True})
        messages.append({"role": "system", "content": f"Transaction ouverte par l'analyste : {context_tx}. "
                         "Utilise-la par défaut si la question ne précise pas d'identifiant. Résultat de get_transaction "
                         "(déjà fourni, ne pas le redemander) : " + json.dumps(facts, ensure_ascii=False, default=str)})
    for m in history[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})
    tokens = {"prompt": 0, "completion": 0, "total": 0}
    answer = None
    for round_ in range(MAX_TOOL_ROUNDS + 1):
        resp = _complete(client, messages)
        if resp.usage:
            tokens["prompt"] += resp.usage.prompt_tokens
            tokens["completion"] += resp.usage.completion_tokens
            tokens["total"] += resp.usage.total_tokens
        msg = resp.choices[0].message
        if msg.tool_calls and round_ < MAX_TOOL_ROUNDS:
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                            for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                result = tools.run_tool(tc.function.name, tc.function.arguments)
                used.append({"name": tc.function.name, "args": tc.function.arguments})
                content = json.dumps(result, ensure_ascii=False, default=str)[:TOOL_RESULT_CHARS]
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            continue
        answer = msg.content
        break
    return {"answer": answer or "Je n'ai pas pu formuler de réponse.", "tools": used, "tokens": tokens,
            "mode": f"Azure OpenAI ({os.environ['AZURE_OPENAI_DEPLOYMENT']})"}


# ---------------------------------------------------------------- offline (deterministic) answers
def _fmt(x):
    return f"{x:,.3f}".replace(",", " ") if isinstance(x, (int, float)) else str(x)


def _ask_offline(question, context_tx):
    q = question.lower()
    used = []

    def call(name, **kw):
        used.append({"name": name, "args": json.dumps(kw, ensure_ascii=False)})
        return tools.run_tool(name, kw)

    if any(w in q for w in ["moteur", "kpi", "évit", "evit", "performance", "combien d'alertes"]):
        k = call("get_kpis")
        lg, md = k["moteur_regles_actuel"], k["modele_top_1pct"]
        text = (f"**Validation {k['periode_validation']}** — {k['fraudes_validation']} fraudes.\n\n"
                f"- Moteur actuel : {lg['alertes']} alertes, {lg['fraudes_detectees']} fraudes détectées "
                f"(précision {lg['precision']:.1%}, rappel {lg['rappel']:.1%}), {lg['fausses_alertes']} fausses alertes.\n"
                f"- Modèle, top 1 % : {md['alertes']} alertes, {md['fraudes_detectees']} fraudes "
                f"(précision {md['precision']:.1%}, rappel {md['rappel']:.1%}), {md['fausses_alertes']} fausses alertes.\n\n"
                f"→ **{lg['fausses_alertes'] - md['fausses_alertes']} fausses alertes évitées** et "
                f"**{md['fraudes_detectees'] - lg['fraudes_detectees']} fraudes de plus**, avec {lg['alertes'] - md['alertes']} alertes de moins.")
        return {"answer": text, "tools": used, "tokens": {"prompt": 0, "completion": 0, "total": 0}, "mode": "hors-ligne (règles)"}

    if any(w in q for w in ["file", "plus risqu", "top 10", "10 transactions"]):
        a = call("get_alert_queue", n=10)
        lines = [f"- {x['transaction_id']} · {x['timestamp']} · {_fmt(x['amount_tnd'])} TND · {x['channel']} · "
                 f"{x['risk_level']} · {x.get('top_model_factors', '')}" for x in a["alertes"]]
        text = f"**{a['nb_alertes']} alertes** ({a['jours_couverts']}). Les 10 plus risquées :\n" + "\n".join(lines)
        return {"answer": text, "tools": used, "tokens": {"prompt": 0, "completion": 0, "total": 0}, "mode": "hors-ligne (règles)"}

    if not context_tx:
        return {"answer": "Ouvrez une transaction (ou citez un identifiant TX…) pour que je l'analyse.", "tools": used,
                "tokens": {"prompt": 0, "completion": 0, "total": 0}, "mode": "hors-ligne (règles)"}

    t = call("get_transaction", transaction_id=context_tx)
    if "erreur" in t:
        return {"answer": t["erreur"], "tools": used, "tokens": {"prompt": 0, "completion": 0, "total": 0}, "mode": "hors-ligne (règles)"}
    c = call("compare_to_habits", transaction_id=context_tx)
    tx, s = t["transaction"], t.get("score", {})
    e = c.get("ecarts", {})
    p = call("get_customer_profile", customer_id=tx["customer_id"], before_transaction_id=context_tx).get("profil", {})

    if any(w in q for w in ["commerçant", "commercant", "dab", "appareil", "autres clients", "related", "même"]):
        r = call("find_related_cases", transaction_id=context_tx)
        lines = [f"- {pc['type']} {pc['identifiant']} : {pc['autres_clients']} autre(s) client(s), "
                 f"{pc['operations_en_alerte']} opération(s) en alerte sur {r['fenetre_jours']} j" for pc in r["points_communs"]]
        text = "**Points communs avec d'autres clients**\n" + ("\n".join(lines) or r.get("note", "Aucun.")) + \
               f"\n\n_Périmètre : {r['perimetre']}._"
        return {"answer": text, "tools": used, "tokens": {"prompt": 0, "completion": 0, "total": 0}, "mode": "hors-ligne (règles)"}

    if any(w in q for w in ["avant", "application", "connexion", "digital"]):
        d = call("get_digital_events", customer_id=tx["customer_id"], around=context_tx)
        h = call("get_customer_history", customer_id=tx["customer_id"], days=1, before_transaction_id=context_tx)
        ops = "\n".join(f"- {o['timestamp']} · {o.get('transaction_type', '')} {o.get('channel', '')} · {_fmt(o['amount_tnd'])} TND"
                        for o in h.get("operations", [])[:8])
        sig = "\n".join(f"- {x['facteur']} : {x['valeur']}" for x in d.get("signaux_digitaux_du_modele", []))
        evs = "\n".join(f"- {x['timestamp']} · {x['event_type']} · {x.get('status', '')} · {x.get('channel', '')}"
                        for x in d.get("evenements", []))
        text = (f"**Dans les 24 h avant {context_tx}**\n\nOpérations :\n{ops or '- aucune'}\n\n"
                f"Événements digitaux :\n{evs or sig or '- non disponibles'}")
        return {"answer": text, "tools": used, "tokens": {"prompt": 0, "completion": 0, "total": 0}, "mode": "hors-ligne (règles)"}

    risky = [f for f in t["facteurs_modele_pour_fraude"]] + t["regles_metier_declenchees"]
    calm = t["facteurs_modele_rassurants"] + t["regles_rassurantes"]
    facts = []
    if e.get("ratio_vs_moyenne"):
        facts.append(f"Montant {_fmt(tx['amount_tnd'])} TND, soit {e['ratio_vs_moyenne']}× la moyenne "
                     f"habituelle du client ({_fmt(e['montant_moyen'])} TND, {c['historique_avant']['nb_operations']} opérations passées)")
    if e.get("vitesse_implicite_kmh", 0) > 900:
        facts.append(f"Déplacement impossible : {e['distance_operation_precedente_km']} km depuis l'opération précédente "
                     f"({e['vitesse_implicite_kmh']} km/h)")
    for f in risky:
        if len(facts) >= 3:
            break
        if "valeur_observee" not in f:
            continue
        usual = f" (habituel {f['valeur_habituelle']})" if "valeur_habituelle" in f else ""
        facts.append(f"{f['facteur']} = {f['valeur_observee']}{usual}")
    reassure = []
    if e.get("pays_deja_vu_en_physique"):
        reassure.append(f"pays {tx.get('country')} déjà fréquenté physiquement")
    if e.get("ville_deja_vue"):
        reassure.append(f"ville {tx.get('city')} habituelle")
    if tx.get("entry_mode") == "CHIP":
        reassure.append("paiement par puce")
    if 7 <= e.get("heure", 0) <= 21:
        reassure.append(f"en journée ({e.get('heure')} h)")
    if e.get("refus_carte_1h_avant", 0) == 0 and e.get("operations_carte_1h_avant", 0) <= 1:
        reassure.append("aucune rafale ni refus dans l'heure")
    reassure += [f"{f['facteur']} = {f['valeur_observee']}" for f in calm[:2] if "valeur_observee" in f]
    level = s.get("niveau_risque", "FAIBLE")
    reco = {"ELEVE": ("BLOQUER", "élevée"), "MOYEN": ("ESCALADER", "moyenne")}.get(level, ("VALIDER", "moyenne à élevée"))
    pct = s.get("percentile_risque_periode")
    legacy = ""
    if s.get("alerte_moteur_regles_actuel"):
        legacy = " · alerte du moteur de règles actuel" + (" (probablement injustifiée)" if level == "FAIBLE" else "")
    if pct is None:
        rank = "n/d"
    elif pct >= 0.5:
        rank = f"parmi les {max(1 - pct, 0.0001):.2%} les plus risquées de la période".replace("0.01%", "< 0.01 %")
    else:
        rank = f"moins risquée que {max(1 - pct, 0):.2%} des opérations de la période"
    if level == "FAIBLE":   # avoided false positive: lead with what reassures, keep the alarming fact as a point of attention
        body = (f"2. **Éléments rassurants** : {', '.join(reassure) if reassure else 'aucun'}.\n"
                f"3. **Point d'attention** : {facts[0] if facts else 'aucun'}.\n")
    else:
        body = (f"2. **Facteurs principaux** :\n" + "\n".join(f"   - {x}" for x in facts[:3]) + "\n"
                f"3. **Éléments rassurants** : {', '.join(reassure) if reassure else 'aucun'}.\n")
    text = (f"1. **Verdict** : risque {level} — score modèle {s.get('score_modele')}, {rank}{legacy}.\n" + body +
            f"4. **Contexte** : client {p.get('age', '?')} ans, {p.get('segment', '?')}, {p.get('home_city', '?')}, "
            f"revenu {_fmt(p.get('monthly_income_tnd', 0))} TND ; {c.get('historique_avant', {}).get('nb_operations', 0)} "
            f"opérations depuis {c.get('historique_avant', {}).get('depuis')} ; {e.get('operations_24h_avant', 0)} dans les 24 h.\n"
            f"5. **Recommandation** : **{reco[0]}** (confiance {reco[1]}). La décision finale appartient à l'analyste.")
    if "résumé" in q or "resume" in q or "dossier" in q:
        text = f"**Résumé d'investigation — {context_tx}** ({datetime.now():%Y-%m-%d})\n\n" + text
    return {"answer": text, "tools": used, "tokens": {"prompt": 0, "completion": 0, "total": 0}, "mode": "hors-ligne (règles)"}


def usage_summary():
    if not LOG_FILE.exists():
        return {"appels": 0, "tokens": 0, "caches": 0}
    rows = [json.loads(line) for line in LOG_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"appels": len(rows), "tokens": sum(r.get("tokens", {}).get("total", 0) for r in rows),
            "caches": sum(1 for r in rows if r.get("cached")), "rows": rows}
