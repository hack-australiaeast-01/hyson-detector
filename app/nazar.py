"""Nazar — the evil-eye work agent of Hyson Detector (not a chat).

One instruction -> one action in the app, with 0 tokens and no LLM:
open an alert or a customer, list alerts (top N, yesterday, to block), find customers by description,
prepare a decision (the analyst confirms it), give the work briefing, open the next alert, check the
audit log, show the KPIs, navigate, switch language. A free question about the open alert is handed to the
copilot only if the analyst asks for it. Every instruction is logged in data/agent_log.jsonl.
"""
import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import copilot
import data_access as da
import deepsearch
import person_search
import tools
import ui

AVATAR = str(Path(__file__).parent / "static" / "brand" / "nazar.png")
LOG = da.DATA / "agent_log.jsonl"
TX = re.compile(r"\bTX\d{6,}\b", re.I)
CU = re.compile(r"\bC\d{6}\b", re.I)


def _n(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9?/' ]+", " ", s.replace("-", " "))).strip()


NAV = [("journal", r"\bjournal\b|tracabilite|audit log"), ("impact", r"\bimpact\b|processus"), ("market", r"marche|benchmark"),
       ("perf", r"performance|robustesse|equite|fairness"), ("pbi", r"power ?bi|dashboard|tableau de bord"),
       ("onboard", r"nouvelle source|onboarding|new data source"), ("galaxy", r"reseau|constellation|compromission|network"),
       ("guide", r"\bguide\b|demarrer|visite|start here|tour\b"), ("queue", r"file d ?alertes|alert queue"),
       ("cust", r"client 360|vue client|customer 360"), ("deep", r"approfondie|deep ?search"),
       ("proces", r"\bproces\b|\btrial\b|tribunal"), ("replay", r"reconstitution|replay|scene"),
       ("contre", r"contre ?enquete|counter|what ?if")]
TX_PAGE = [("proces", r"\bproces\b|\btrial\b|\bjuge\b"), ("replay", r"reconstitution|replay|scene"),
           ("contre", r"contre|counter|what ?if"), ("deep", r"approfondie|deep"), ("cust", r"\bclient\b|customer|360")]
DECIDE = [("BLOQUER", r"\b(bloque[rz]?|block)\b"), ("ESCALADER", r"\b(escalade[rz]?|escalate)\b"),
          ("VALIDER", r"\b(valide[rz]?|validate|approve)\b")]
THIS = r"\b(celle ?ci|celle la|cette (alerte|transaction|operation)|l alerte ouverte|this (one|alert|transaction)|current|la courante)\b"
LIST = r"\btop\b|plus risqu|riskiest|\balertes\b|\balerts\b|\bliste\b|\blist\b|a bloquer|to block|a verifier|to check"
DEC_EN = {"BLOQUER": "BLOCK", "ESCALADER": "ESCALATE", "VALIDER": "VALIDATE"}


# ---------------------------------------------------------------- 1. instruction -> action (pure, testable)
def parse(text, current_tx=None):
    raw = (text or "").strip()
    q = _n(raw)
    m = TX.search(raw)
    tid = m.group(0).upper() if m else None
    if not q or re.search(r"^(aide|help|\?)$|que (sais|peux)|what can you", q):
        return {"kind": "help"}
    if re.search(r"\b(in english|en anglais|english)\b", q):
        return {"kind": "lang", "lang": "en"}
    if re.search(r"\b(en francais|in french|francais|french)\b", q):
        return {"kind": "lang", "lang": "fr"}
    listing = re.search(LIST, q)
    for dec, pat in DECIDE:                     # a decision needs a target: an ID or "this one", never a list
        if re.search(pat, q) and (tid or (re.search(THIS, q) and not listing)):
            return {"kind": "decide", "decision": dec, "tid": tid or current_tx}
    if re.search(r"\b(suivante?|next|prochaine?)\b", q) and not tid:
        return {"kind": "next"}
    if re.search(r"tache|todo|a faire|briefing|que dois|what should|my tasks|mes priorites", q) and not tid:
        return {"kind": "brief"}
    if tid:
        for page, pat in TX_PAGE:
            if re.search(pat, q):
                return {"kind": "open", "tid": tid, "page": page}
        return {"kind": "open", "tid": tid, "page": "tx"}
    c = CU.search(raw)
    if c:
        return {"kind": "customer", "cid": c.group(0).upper()}
    if re.search(r"integrit|desaccord|override|piste d ?audit|audit trail|(verifie|verifier|check|controle)\b.*\b(journal|log)\b", q):
        return {"kind": "audit"}
    if re.search(r"\bkpi|chiffres|resultats?\b|combien|fausses alertes|false alerts|how many", q):
        return {"kind": "kpi"}
    is_person, crit = person_search.is_person_question(raw)
    if is_person or ({k for k in crit if k not in ("with_alerts", "digital")} and re.search(r"\b(trouve|cherche|find|search|liste|list)\b", q)):
        return {"kind": "people", "crit": crit}
    if listing:
        n = re.search(r"(?:top|les|the|show|montre(?: moi)?(?: les)?)\s*(\d{1,2})\b|\b(\d{1,2})\s+(?:alertes|alerts|transactions|plus|most)", q)
        only = ("BLOQUER" if re.search(r"a bloquer|to block", q) else "ESCALADER" if re.search(r"a verifier|to check", q) else None)
        risk = "ELEVE" if re.search(r"\b(eleve|elevee|high)\b", q) else "MOYEN" if re.search(r"\b(moyen|moyenne|medium)\b", q) else None
        day = copilot._relative_day(raw)
        d = re.search(r"\b(2026-\d{2}-\d{2})\b|\b(\d{1,2})/(\d{1,2})\b", raw)
        if d and not day:
            day = d.group(1) or f"2026-{int(d.group(3)):02d}-{int(d.group(2)):02d}"
        return {"kind": "list", "n": min(int(next(x for x in n.groups() if x)), 20) if n else 10, "day": day, "only": only, "risk": risk}
    for page, pat in NAV:
        if re.search(pat, q):
            return {"kind": "go", "page": page}
    if current_tx and (raw.endswith("?") or re.search(r"^(pourquoi|why|est ce|is it|quel|what|comment|how|explique|explain)", q)):
        return {"kind": "ask", "question": raw, "tid": current_tx}
    return {"kind": "unknown"}


def _alerts():
    q = da.queue()
    a = q[(q.period == "test") & (q.risk_level != "FAIBLE")].copy()
    a["fraud_rate"] = tools.measured_fraud_rate(a.score_model)
    a["action"], a["conf"] = tools.recommend_vector(a)
    done = set(tools.decisions().transaction_id) if len(tools.decisions()) else set()
    a["decided"] = a.transaction_id.isin(done)
    return a


def _row(r, L):
    flag = "✓ " if r.decided else ""
    return {"tid": r.transaction_id, "page": "tx",
            "label": (f"{flag}{r.transaction_id} · {pd.Timestamp(r.timestamp):%d/%m %H:%M} · {r.transaction_type} {r.channel} · "
                      f"{float(r.amount_tnd):,.0f} TND · {float(r.fraud_rate):.0%} " + L("fraudes mesurées", "measured fraud") +
                      f" · {L(r.action, DEC_EN.get(r.action, r.action))}").replace(",", " ")}


def run(a, lang="fr", analyst=None):
    """Execute an action. Returns {"text", "rows"?, "open"?, "go"?, "lang"?, "confirm"?, "ask"?, "tools"}."""
    L = (lambda fr, en: en if lang == "en" else fr)
    kind = a["kind"]
    if kind == "help":
        return {"text": L(HELP_FR, HELP_EN), "tools": []}
    if kind == "lang":
        return {"text": L("Interface en français.", "Interface in English."), "lang": a["lang"], "tools": []}
    if kind == "go":
        return {"text": L("J'ouvre la page.", "Opening the page."), "go": a["page"], "tools": []}
    if kind in ("open", "decide", "ask"):
        tid = a.get("tid")
        if not tid:
            return {"text": L("Aucune alerte ouverte : précisez l'identifiant (ex. TX01555470).",
                              "No alert open: give the ID (e.g. TX01555470)."), "tools": []}
        if tools._tx_row(tid) is None:
            return {"text": L(f"Transaction {tid} introuvable.", f"Transaction {tid} not found."), "tools": ["get_transaction"]}
        if kind == "open":
            return {"text": L(f"J'ouvre {tid}.", f"Opening {tid}."), "open": (tid, a["page"]), "tools": []}
        if kind == "ask":
            return {"text": L(f"Ce n'est pas une tâche : c'est une question pour le copilote (sur {tid}, avec tokens). "
                              "Je la lui transmets si vous confirmez.",
                              f"That is not a task but a question for the copilot (about {tid}, uses tokens). "
                              "I'll pass it on if you confirm."), "ask": (tid, a["question"]), "tools": []}
        t = tools.get_transaction(tid)
        rec = t.get("recommandation_systeme") or {}
        sc = t.get("score") or {}
        amount = float(t["transaction"].get("amount_tnd") or 0)
        rate = float(tools.measured_fraud_rate([sc["score_modele"]])[0]) if sc.get("score_modele") is not None and t.get("dans_file_alertes") else None
        lines = [L(f"**Préparé : {a['decision']} {tid}** — à confirmer par vous.", f"**Prepared: {DEC_EN[a['decision']]} {tid}** — you confirm."),
                 f"- {t['transaction'].get('transaction_type', '')} {t['transaction'].get('channel', '')} · {amount:,.3f} TND · "
                 f"{t['transaction'].get('timestamp', '')}".replace(",", " ")]
        if rec:
            lines.append(L(f"- Recommandation système : **{rec['decision']}** (confiance {rec['confiance']})",
                           f"- System recommendation: **{DEC_EN.get(rec['decision'], rec['decision'])}** ({rec['confiance']} confidence)")
                         + (L(f" · {rate:.0%} de fraudes mesurées à ce score", f" · {rate:.0%} measured fraud at this score") if rate is not None else ""))
        if rec and rec.get("decision") != a["decision"]:
            lines.append(L("- ⚠ Vous vous écartez de la recommandation : ce sera visible dans le journal (désaccord).",
                           "- ⚠ You depart from the recommendation: it will show in the log (override)."))
        if (a["decision"] == "BLOQUER" and amount >= tools.FOUR_EYES_TND) or (rec.get("decision") == "BLOQUER" and a["decision"] != "BLOQUER"):
            lines.append(L("- 👥 Double contrôle requis (quatre yeux) dans le message envoyé au SI.",
                           "- 👥 Four-eyes approval required in the message sent to the bank systems."))
        return {"text": "\n".join(lines), "confirm": {"tid": tid, "decision": a["decision"], "confidence": rec.get("confiance", "moyenne")},
                "tools": ["get_transaction", "recommend"]}
    if kind == "customer":
        c = da.customers()
        if c is None or a["cid"] not in set(c.customer_id):
            return {"text": L(f"Client {a['cid']} introuvable.", f"Customer {a['cid']} not found."), "tools": ["get_customer_profile"]}
        q = da.queue()
        mine = q[q.customer_id == a["cid"]].sort_values("score_model", ascending=False)
        if len(mine):
            return {"text": L(f"J'ouvre la vue 360 de {a['cid']} sur son alerte la plus risquée ({mine.transaction_id.iloc[0]}).",
                              f"Opening {a['cid']}'s 360 view on their riskiest alert ({mine.transaction_id.iloc[0]})."),
                    "open": (mine.transaction_id.iloc[0], "cust"), "tools": ["get_customer_profile"]}
        return {"text": L(f"J'ouvre la vue 360 de {a['cid']} (aucune alerte).", f"Opening {a['cid']}'s 360 view (no alert)."),
                "go": "cust", "cust": a["cid"], "tools": ["get_customer_profile"]}
    if kind == "people":
        res = person_search.find_customers(**a["crit"], limit=8)
        rows = [{"tid": r["alerte_la_plus_risquee"], "page": "cust", "cid": r["customer_id"],
                 "label": f"{r['customer_id']} · {r['age']} {L('ans', 'y/o')} · {r['segment']} · {r['occupation']} · {r['ville']} · "
                          f"{r['nb_alertes']} {L('alerte(s)', 'alert(s)')}"} for r in res.get("clients", [])]
        crit = ", ".join(f"{k} = {v}" for k, v in res.get("criteres", {}).items())
        return {"text": L(f"**{res.get('nb_clients_correspondants', 0)} client(s)** · {crit}", f"**{res.get('nb_clients_correspondants', 0)} customer(s)** · {crit}"),
                "rows": rows, "tools": ["find_customers"]}
    if kind == "list":
        x = _alerts()
        if a.get("day"):
            x = x[x.date == pd.to_datetime(a["day"]).date()]
        if a.get("only"):
            x = x[x.action == a["only"]]
        if a.get("risk"):
            x = x[x.risk_level == a["risk"]]
        top = x.sort_values("score_model", ascending=False).head(a["n"])
        scope = " · ".join(s for s in [a.get("day") or L("flux du jour (août–sept.)", "live flow (Aug–Sep)"),
                                        L(a["only"], DEC_EN.get(a["only"], "")) if a.get("only") else "", a.get("risk") or ""] if s)
        head = L(f"**{len(top)} / {len(x)} alertes** · {scope} · triées par score", f"**{len(top)} / {len(x)} alerts** · {scope} · sorted by score")
        return {"text": head if len(x) else L(f"Aucune alerte pour : {scope}.", f"No alert for: {scope}."),
                "rows": [_row(r, L) for r in top.itertuples()], "tools": ["get_alert_queue"]}
    if kind in ("next", "brief"):
        x = _alerts()
        todo = x[~x.decided].sort_values(["fraud_rate", "score_model"], ascending=False)
        if kind == "next":
            if not len(todo):
                return {"text": L("Toutes les alertes du flux sont traitées.", "Every alert of the flow is handled."), "tools": []}
            r = todo.iloc[0]
            return {"text": L(f"Alerte suivante : {r.transaction_id} ({r.fraud_rate:.0%} de fraudes mesurées, {r.action}).",
                              f"Next alert: {r.transaction_id} ({r.fraud_rate:.0%} measured fraud, {DEC_EN.get(r.action, r.action)})."),
                    "open": (r.transaction_id, "tx"), "tools": ["get_alert_queue"]}
        return briefing(lang, x, todo)
    if kind == "audit":
        v = tools.verify_journal()
        d = tools.decisions()
        over = d[(d.system_decision.astype(str).str.len() > 0) & (d.decision != d.system_decision)] if len(d) else d
        text = [L(f"- Journal : **{'intact' if v['ok'] else 'MODIFIÉ'}** ({v['rows']} décision(s))",
                  f"- Log: **{'intact' if v['ok'] else 'ALTERED'}** ({v['rows']} decision(s))"),
                L(f"- Désaccords avec la recommandation : **{len(over)}**", f"- Overrides of the recommendation: **{len(over)}**")]
        rows = [{"tid": r.transaction_id, "page": "tx", "label": f"{r.transaction_id} · {r.system_decision} → {r.decision} · {r.analyst}"}
                for r in over.tail(5).itertuples()]
        return {"text": "\n".join(text), "rows": rows, "go_button": "journal", "tools": ["verify_journal"]}
    if kind == "kpi":
        k = tools.get_kpis()
        r, m = k["moteur_regles_actuel"], k["modele_top_1pct"]
        nb = (lambda v: f"{int(v):,}".replace(",", " "))
        head = L(f"- Fraudes détectées : **{nb(m['fraudes_detectees'])}** vs {nb(r['fraudes_detectees'])} (règles actuelles)\n"
                 f"- Fausses alertes : **{nb(m['fausses_alertes'])}** vs {nb(r['fausses_alertes'])}\n",
                 f"- Frauds caught: **{nb(m['fraudes_detectees'])}** vs {nb(r['fraudes_detectees'])} (current rules)\n"
                 f"- False alerts: **{nb(m['fausses_alertes'])}** vs {nb(r['fausses_alertes'])}\n")
        tail = L(f"- {k['comparaison_top_1pct_vs_moteur']}", "- validation June–July 2026, top 1 % of the model vs the current rules engine")
        return {"text": head + tail, "go_button": "impact", "tools": ["get_kpis"]}
    return {"text": L(UNKNOWN_FR, UNKNOWN_EN), "tools": []}


def briefing(lang="fr", x=None, todo=None):
    """What needs the analyst's attention now (0 token)."""
    L = (lambda fr, en: en if lang == "en" else fr)
    x = _alerts() if x is None else x
    todo = x[~x.decided].sort_values(["fraud_rate", "score_model"], ascending=False) if todo is None else todo
    block_hi = todo[(todo.action == "BLOQUER") & (todo.conf == "élevée")]
    try:
        w = deepsearch.watch("test")
        prio = [t for t in w[w.level == "priorite"].index if t in set(todo.transaction_id)]
    except Exception:
        prio = []
    d = tools.decisions()
    over = d[(d.system_decision.astype(str).str.len() > 0) & (d.decision != d.system_decision)] if len(d) else d
    integ = tools.verify_journal()
    nb = (lambda v: f"{int(v):,}".replace(",", " "))
    lines = [L(f"- **{nb(len(todo))} / {nb(len(x))}** alertes du flux restent à traiter", f"- **{nb(len(todo))} / {nb(len(x))}** alerts of the flow still to handle"),
             L(f"- **{len(block_hi)}** à bloquer avec confiance élevée (≈ 94–100 % de fraudes mesurées)",
               f"- **{len(block_hi)}** to block with high confidence (≈ 94–100% measured fraud)"),
             L(f"- **{len(prio)}** alertes moyennes signalées « priorité » par l'enquête approfondie",
               f"- **{len(prio)}** medium alerts flagged \"priority\" by the deep search")]
    if len(over):
        lines.append(L(f"- **{len(over)}** désaccord(s) avec la recommandation à revoir", f"- **{len(over)}** override(s) to review"))
    lines.append(L(f"- Journal d'audit : {'✅ intact' if integ['ok'] else '❌ modifié'}", f"- Audit log: {'✅ intact' if integ['ok'] else '❌ altered'}"))
    if not copilot.configured():
        lines.append(L("- ⚠ Copilote hors-ligne (clé Azure OpenAI absente) : réponses en mode règles",
                       "- ⚠ Copilot offline (no Azure OpenAI key): rule-based answers"))
    return {"text": L("**Briefing de Nazar**\n", "**Nazar's briefing**\n") + "\n".join(lines),
            "rows": [_row(r, L) for r in todo.head(3).itertuples()], "tools": ["get_alert_queue", "verify_journal"],
            "count": int(len(block_hi) + len(prio) + len(over)),
            "counts": {"block": int(len(block_hi)), "prio": int(len(prio)), "over": int(len(over)), "todo": int(len(todo))}}


def log(cmd, action, out, lang, current_tx, latency):
    try:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "command": cmd, "action": action.get("kind"),
                                "lang": lang, "context_tx": current_tx, "tools": out.get("tools", []), "tokens": 0,
                                "latency_s": round(latency, 3), "analyst": st.session_state.get("analyst")}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def history():
    if not LOG.exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()])


HELP_FR = """**Nazar exécute, il ne bavarde pas.** Exemples :
- `mes tâches` · `suivante` (ouvre l'alerte la plus urgente non traitée)
- `top 10 d'hier` · `alertes à bloquer` · `top 5 élevé`
- `ouvre TX01555470` · `procès TX01555470` · `reconstitution TX01585580` · `C000488`
- `bloque TX01555470` · `valide celle-ci` (vous confirmez toujours)
- `client retraité de Sfax de plus de 70 ans avec des alertes`
- `vérifie le journal` · `kpi` · `impact` · `power bi` · `english`"""
HELP_EN = """**Nazar acts, it doesn't chat.** Examples:
- `my tasks` · `next` (opens the most urgent unhandled alert)
- `top 10 yesterday` · `alerts to block` · `top 5 high`
- `open TX01555470` · `trial TX01555470` · `replay TX01585580` · `C000488`
- `block TX01555470` · `validate this one` (you always confirm)
- `retired customers in Sfax over 70 with alerts`
- `check the log` · `kpi` · `impact` · `power bi` · `français`"""
UNKNOWN_FR = ("Je suis un agent de travail : je n'exécute que des tâches sur les alertes, les clients, les décisions et les pages. "
              "Tapez `aide` pour la liste. Pour une question libre, ouvrez une alerte et posez-la au copilote.")
UNKNOWN_EN = ("I'm a work agent: I only run tasks on alerts, customers, decisions and pages. Type `help` for the list. "
              "For a free question, open an alert and ask the copilot.")


# ---------------------------------------------------------------- 2. UI (sidebar card + dialog)
def sidebar_card(ctx):
    L = ctx.L
    try:
        c = briefing(ctx.lang)["counts"]
        watch = (f'{c["block"]} {L("à bloquer", "to block")} · {c["prio"]} {L("à creuser", "to dig")}'
                 + (f' · {c["over"]} {L("désaccord(s)", "override(s)")}' if c["over"] else ""))
    except Exception:
        watch = ""
    st.markdown(f'<div class="nazar-card">{_img(42)}<div><b>Nazar</b><span>'
                f'{L("agent de travail · veille sur la file", "work agent · watching the queue")}</span>'
                f'<span class="nz-n">{watch}</span></div></div>', unsafe_allow_html=True)
    st.button(L("Ouvrir Nazar", "Open Nazar"), key="nazar_open_btn", on_click=lambda: st.session_state.update(nazar_open=True),
              icon=":material/visibility:", width="stretch")


def _img(size):
    import base64
    p = Path(AVATAR)
    if not p.exists():
        return "🧿"
    return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" width="{size}" height="{size}" alt="Nazar">'


QUICK = [("mes tâches", "my tasks"), ("suivante", "next"), ("top 10 d'hier", "top 10 yesterday"),
         ("alertes à bloquer", "alerts to block"), ("vérifie le journal", "check the log"), ("aide", "help")]


@st.dialog("🧿 Nazar · agent de travail / work agent", width="large")
def panel(ctx):
    L, lang = ctx.L, ctx.lang
    st.markdown(f'<div style="display:flex;gap:.9rem;align-items:center;margin:-.3rem 0 .6rem">{_img(54)}<div>'
                f'<b>{L("L’œil qui veille sur la file d’alertes.", "The eye that watches the alert queue.")}</b><br>'
                f'<span style="color:{ui.MUTED};font-size:.88rem">{L("Une instruction → une action. Aucun token, chaque action est tracée, "
                "vous confirmez toute décision.", "One instruction → one action. No tokens, every action is logged, you confirm every decision.")}'
                f'</span></div></div>', unsafe_allow_html=True)
    logbook = st.session_state.setdefault("nazar_log", [])
    cmd = None
    qc = st.columns(len(QUICK))
    for i, (fr, en) in enumerate(QUICK):
        if qc[i].button(L(fr, en), key=f"nz_q_{i}", width="stretch"):
            cmd = L(fr, en)
    with st.form("nazar_cmd", clear_on_submit=True, border=False):
        a, b = st.columns([5, 1])
        typed = a.text_input(L("Instruction", "Instruction"), label_visibility="collapsed",
                             placeholder=L("ex. top 10 d'hier · ouvre TX01555470 · bloque celle-ci · client retraité de Sfax…",
                                           "e.g. top 10 yesterday · open TX01555470 · block this one · retired customers in Sfax…"))
        if b.form_submit_button(L("Exécuter", "Run"), type="primary", width="stretch") and typed.strip():
            cmd = typed.strip()
    if not logbook and not cmd:
        cmd = L("mes tâches", "my tasks")
    if cmd:
        t0 = time.time()
        act = parse(cmd, st.session_state.get("tx"))
        out = run(act, lang, st.session_state.get("analyst"))
        log(cmd, act, out, lang, st.session_state.get("tx"), time.time() - t0)
        if any(k in out for k in ("open", "go", "lang")):          # navigation: act now, close the dialog
            _navigate(ctx, out)
        logbook.append({"cmd": cmd, "out": out})
    for i in range(len(logbook) - 1, max(len(logbook) - 5, 0) - 1, -1):
        e = logbook[i]
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(f"`{e['cmd']}`")
        with st.chat_message("assistant", avatar=AVATAR):
            _show(ctx, e, i)


def _navigate(ctx, out):
    if "lang" in out:
        st.session_state.lang = out["lang"]
    if "cust" in out:
        st.session_state.cust_override = out["cust"]
    if "open" in out:
        ctx.open_tx(*out["open"])
    elif "go" in out:
        ctx.go(out["go"])
    st.rerun()


def _show(ctx, e, i):
    L, out = ctx.L, e["out"]
    st.markdown(out["text"])
    for j, r in enumerate(out.get("rows", [])[:8]):
        a, b = st.columns([6, 1])
        a.caption(r["label"])
        if r.get("tid") and b.button(L("Ouvrir", "Open"), key=f"nz_o_{i}_{j}", width="stretch"):
            _navigate(ctx, {"open": (r["tid"], r.get("page", "tx"))})
        elif not r.get("tid") and r.get("cid") and b.button(L("Ouvrir", "Open"), key=f"nz_c_{i}_{j}", width="stretch"):
            _navigate(ctx, {"go": "cust", "cust": r["cid"]})
    if out.get("go_button") and st.button(L("Ouvrir la page", "Open the page"), key=f"nz_g_{i}"):
        _navigate(ctx, {"go": out["go_button"]})
    c = out.get("confirm")
    if c and not e.get("done"):
        a, b = st.columns(2)
        if a.button(L(f"✅ Confirmer {c['decision']}", f"✅ Confirm {DEC_EN[c['decision']]}"), key=f"nz_ok_{i}", type="primary",
                    width="stretch"):
            opened = st.session_state.get("opened", {}).get(c["tid"])
            res = tools.record_decision(c["tid"], c["decision"], c["confidence"], L("via l'agent Nazar", "via the Nazar agent"),
                                        analyst=st.session_state.get("analyst"), source="agent_nazar",
                                        duration_s=(time.time() - opened) if opened else None)
            e["done"] = (L(f"Décision {c['decision']} enregistrée · empreinte {res.get('empreinte', '')}…",
                           f"Decision {DEC_EN[c['decision']]} saved · fingerprint {res.get('empreinte', '')}…")
                         if res.get("enregistre") else str(res))
            st.rerun(scope="fragment")
        if b.button(L("Annuler", "Cancel"), key=f"nz_no_{i}", width="stretch"):
            e["done"] = L("Annulé : rien n'a été enregistré.", "Cancelled: nothing was saved.")
            st.rerun(scope="fragment")
    elif c:
        st.success(e["done"])
    if out.get("ask"):
        tid, question = out["ask"]
        if st.button(L("Envoyer au copilote", "Send to the copilot"), key=f"nz_ask_{i}"):
            st.session_state.copilot_question = question
            _navigate(ctx, {"open": (tid, "tx")})
