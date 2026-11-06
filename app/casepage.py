"""Page « Dossier d'enquête » — the investigation command centre for one case (brief §1, §2, §3, §4.3, §7)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import intel
import investigation
import memory
import tools
import ui

DEMO_CASE = "TX01631347"      # declined abroad, then the card keeps being used in two countries: a case that reopens by itself
STEPS = [(0, ("À l'alerte", "At the alert")), (6, ("+6 h", "+6 h")), (24, ("+24 h", "+24 h")), (72, ("+72 h", "+72 h"))]
KIND_COLOR = {"alert": ui.RED, "tx_declined": "#B42318", "tx_ok": "#94A3B8", "login_fail": ui.AMBER, "benef": ui.AMBER, "device": ui.AMBER,
              "pwd": ui.AMBER, "phone": ui.AMBER, "decision": ui.TEAL}


def _timeline(s, t0, as_of, L, lang):
    i = 1 if lang == "en" else 0
    fig = go.Figure()
    for kind, g in s.groupby("kind"):
        fig.add_trace(go.Scatter(x=g.ts, y=[intel.KIND_LABEL[kind][i]] * len(g), mode="markers", name=intel.KIND_LABEL[kind][i],
                                 marker=dict(size=[16 if k == "alert" else 11 for k in g.kind], color=KIND_COLOR.get(kind, ui.BLUE),
                                             line=dict(width=1, color="#fff"), symbol=["diamond" if k == "alert" else "circle" for k in g.kind]),
                                 text=g.detail, hovertemplate="%{x|%d/%m %H:%M}<br>%{text}<extra></extra>"))
    fig.add_vline(x=t0, line_dash="dot", line_color=ui.RED)
    fig.add_vrect(x0=as_of, x1=t0 + intel.HORIZON, fillcolor="#E2E8F0", opacity=.45, line_width=0)
    fig.update_layout(height=290, margin=dict(l=8, r=8, t=8, b=8), showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(gridcolor="#EEF2F8", range=[t0 - intel.LOOKBACK, t0 + intel.HORIZON]), yaxis=dict(title=None))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(L("Losange rouge = l'alerte · zone grise = le futur, pas encore connu à cette date.",
                 "Red diamond = the alert · grey area = the future, not known yet at that time."))


def page_case(ctx):
    L, lang = ctx.L, ctx.lang
    ui.hero(L("Enquête continue", "Continuous investigation"), L("Dossier d'enquête", "Investigation case"),
            L("Une alerte refusée n'est pas oubliée : le dossier suit la carte et le client, se rouvre quand de nouveaux faits arrivent, "
              "fait débattre accusation et défense sur des preuves numérotées, et un juge (agent Azure AI Foundry) pèse ces preuves. "
              "L'employé décide.", "A declined alert is not forgotten: the case follows the card and the customer, reopens when new facts "
              "arrive, has prosecution and defence argue on numbered evidence, and a judge (Azure AI Foundry agent) weighs it. The employee decides."),
            ctx.chips())
    q = ctx.queue
    opts = q.transaction_id.tolist()
    st.session_state.setdefault("case_tid", DEMO_CASE if DEMO_CASE in opts else opts[0])
    c1, c2 = st.columns([1.3, 2])
    tid = c1.selectbox(L("Alerte", "Alert"), opts, key="case_tid")
    a = intel._alert_row(tid)
    t0 = pd.Timestamp(a.timestamp)
    step = c2.segmented_control(L("Ce que l'on sait à la date de", "What is known as of"), [h for h, _ in STEPS], default=24,
                                format_func=lambda h: dict(STEPS)[h][1 if lang == "en" else 0], key="case_step")
    as_of = t0 + pd.Timedelta(hours=step if step is not None else 24)
    s = intel.stream(tid, as_of)
    trig = intel.triggers(tid, as_of, lang)
    know, src = intel.knowledge_status(tid)
    react = intel.reactivated(trig)
    k = st.columns(4)
    k[0].metric(L("Statut du dossier", "Case status"), L("Réactivé", "Reactivated") if react else L("Ouvert", "Open"))
    k[1].metric(L("Événements après l'alerte", "Events after the alert"), int((s.phase == "après").sum()) if len(s) else 0)
    k[2].metric(L("Déclencheurs", "Triggers"), len(trig))
    k[3].metric(L("Statut de connaissance", "Knowledge status"),
                {"suspected": L("Suspecté", "Suspected"), "confirmed_fraud": L("Fraude confirmée", "Confirmed fraud"),
                 "confirmed_legit": L("Légitime confirmé", "Confirmed legitimate")}[know],
                help=L("Une conclusion de l'IA reste « suspectée » : seuls la banque (fraude signalée) ou l'employé après contact du client "
                       "confirment.", "An AI conclusion stays \"suspected\": only the bank (fraud report) or the employee after contacting the "
                       "customer can confirm."))
    if src == "bank_label" and a.period != "test":
        st.caption(L("Statut issu de l'étiquette de la banque (période de validation) — affiché pour la démonstration.",
                     "Status from the bank's label (validation period) — shown for the demo."))
    ui.section(L("Chronologie et escalade", "Timeline and escalation"))
    if len(s):
        _timeline(s, t0, as_of, L, lang)
    if trig:
        st.markdown("".join(f"<div class='factor'><span class='dot' style='background:{ui.RED if t['weight'] >= 2 else ui.AMBER}'></span>"
                            f"<div><b>{pd.Timestamp(t['ts']):%d/%m %H:%M}</b> · {ui.esc(t['text'])}</div></div>" for t in trig), unsafe_allow_html=True)
        if react and st.session_state.get(f"case_logged_{tid}_{step}") is None:
            intel.log_case(tid, "reactivated", {"as_of": str(as_of), "triggers": [t["code"] for t in trig]}, st.session_state.get("analyst"))
            st.session_state[f"case_logged_{tid}_{step}"] = True
    else:
        st.caption(L("Rien de nouveau depuis l'alerte à cette date.", "Nothing new since the alert at this time."))

    ui.section(L("Mémoire : cas passés similaires (statut connu à la date)", "Memory: similar past cases (status known at the time)"))
    cases, stats = memory.similar(tid, k=8, lang=lang)
    if cases is None:
        st.caption(L("Mémoire comportementale indisponible pour cette opération.", "Behavioural memory unavailable for this operation."))
    else:
        rate = stats["fraud_rate_known"]
        st.markdown(L(f"**{stats['confirmed_fraud']} fraudes confirmées**, {stats['legit']} légitimes, {stats['suspected']} suspectées non vérifiées, {stats['undetermined']} indéterminées "
                      f"parmi les {stats['k']} cas passés les plus proches (sens + comportement, similarité moyenne {stats['mean_similarity']:.2f})"
                      + (f" · typologie : {', '.join(stats['scenarios'])}" if stats["scenarios"] else ""),
                      f"**{stats['confirmed_fraud']} confirmed frauds**, {stats['legit']} legitimate, {stats['suspected']} suspected not verified, {stats['undetermined']} undetermined among the "
                      f"{stats['k']} closest past cases (meaning + behaviour, mean similarity {stats['mean_similarity']:.2f})"
                      + (f" · typology: {', '.join(stats['scenarios'])}" if stats["scenarios"] else "")))
        show = cases[["timestamp", "status_label", "similarity", "scenario_known", "summary"]].copy()
        show.columns = [L("date", "date"), L("statut à la date", "status at the time"), L("similarité", "similarity"), L("typologie", "typology"),
                        L("résumé du cas", "case summary")]
        st.dataframe(show, hide_index=True, width="stretch", height=250)
        st.caption(L("Seuls les cas antérieurs sont cherchés ; une fraude signalée après l'opération examinée n'est pas comptée comme confirmée ; "
                     "les conclusions de l'IA ne sont jamais ajoutées à la mémoire.", "Only earlier cases are searched; a fraud reported after the "
                     "reviewed operation does not count as confirmed; AI conclusions are never added to the memory."))

    ui.section(L("Enquête contradictoire et jugement", "Adversarial investigation and judgment"))
    note = st.session_state.get(f"case_note_{tid}", "")
    if note:
        st.info(L("Contexte ajouté par l'employé : ", "Context added by the employee: ") + note)
    run = st.button(L("Lancer l'enquête (accusation · défense · juge)", "Run the investigation (prosecution · defence · judge)"),
                    type="primary", icon=":material/gavel:")
    key = f"case_res_{tid}_{step}_{hash(note)}"
    if run:
        with st.status(L("Les agents enquêtent…", "Agents are investigating…"), expanded=True) as box:
            def stage(role, x):
                if role in ("prosecution", "defense"):
                    box.write(L("✔ Accusation prête", "✔ Prosecution ready") if role == "prosecution" else L("✔ Défense prête", "✔ Defence ready"))
                elif role == "judge":
                    box.write(L("✔ Le juge a statué", "✔ The judge has ruled"))
            st.session_state[key] = investigation.investigate(tid, as_of, lang, note, st.session_state.get("analyst"), stage)
            box.update(label=L("Enquête terminée", "Investigation complete"), state="complete")
    res = st.session_state.get(key)
    if res is None:
        ev, *_ = investigation.board(tid, as_of, lang)
        res = {"board": ev}
    with st.expander(L(f"Tableau de preuves · {len(res['board'])} éléments (E1…E{len(res['board'])})",
                       f"Evidence board · {len(res['board'])} items"), icon=":material/fact_check:"):
        st.markdown("\n".join(f"- **{e['id']}** · *{e['kind']}* · {e['text']}" for e in res["board"]))
    if res.get("mode") == "offline":
        st.info(L("IA non connectée : le tableau de preuves, la chronologie et la mémoire restent disponibles.",
                  "AI not connected: the evidence board, timeline and memory are still available."))
    if res.get("prosecution"):
        p, d = st.columns(2)
        with p:
            st.markdown(f"<div style='border-left:4px solid {ui.RED};padding:.2rem .8rem'><b>⚖️ {L('Accusation', 'Prosecution')}</b></div>", unsafe_allow_html=True)
            st.markdown(res["prosecution"])
        with d:
            st.markdown(f"<div style='border-left:4px solid {ui.GREEN};padding:.2rem .8rem'><b>🛡️ {L('Défense', 'Defence')}</b></div>", unsafe_allow_html=True)
            st.markdown(res["defense"])
    j = res.get("judge")
    if j:
        rec = (res.get("system") or {}).get("decision")
        col = ui.DECISION.get(j.get("recommandation"), ui.BLUE)
        st.markdown(
            f"<div style='background:#fff;border:1px solid {ui.LINE};border-left:6px solid {col};border-radius:16px;padding:1rem 1.2rem;margin:.6rem 0'>"
            f"<div style='font-size:.78rem;color:{ui.MUTED};text-transform:uppercase;letter-spacing:.06em'>{L('Juge', 'Judge')} · {ui.esc(res.get('judge_model', ''))}</div>"
            f"<div style='font-size:1.4rem;font-weight:800;color:{col}'>{ui.esc(j.get('recommandation', ''))} · {L('risque', 'risk')} {ui.esc(j.get('niveau_risque', ''))} · "
            f"{L('confiance', 'confidence')} {ui.esc(j.get('confiance', ''))}</div>"
            f"<div style='color:{ui.MUTED}'>{L('Recommandation système', 'System recommendation')} : <b>{ui.esc(rec)}</b>"
            + (f" · <span style='color:{ui.AMBER}'>{L('écart', 'deviation')} : {ui.esc(j.get('ecart_avec_systeme'))}</span>" if j.get("ecart_avec_systeme") else "")
            + f"</div><div style='margin-top:.5rem'>{ui.esc(j.get('synthese', ''))}</div></div>", unsafe_allow_html=True)
        rows = [{L("partie", "side"): e.get("partie"), L("argument", "argument"): e.get("argument"),
                 L("preuves", "evidence"): ", ".join(e.get("preuves_valides", [])) or "⚠ " + L("aucune preuve valide", "no valid evidence"),
                 L("fiabilité", "reliability"): e.get("fiabilite"), L("raison", "reason"): e.get("raison")} for e in j.get("evaluation", [])]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        a1, a2 = st.columns(2)
        with a1:
            st.markdown(f"**{L('Contradictions', 'Contradictions')}**\n" + "\n".join(f"- {x}" for x in j.get("contradictions", []) or ["—"]))
            st.markdown(f"**{L('Modèle ML', 'ML model')}** : {j.get('accord_modele', '—')}\n\n**{L('Cas similaires', 'Similar cases')}** : {j.get('cas_similaires', '—')}")
        with a2:
            st.markdown(f"**{L('Informations manquantes', 'Missing information')}**\n" + "\n".join(f"- {x}" for x in j.get("informations_manquantes", []) or ["—"]))
            st.markdown(f"**{L('Vérifications', 'Checks')}**\n" + "\n".join(f"- {x}" for x in j.get("verifications", []) or ["—"]))
        if j.get("preuves_inexistantes"):
            st.warning(L("Preuves citées inexistantes (écartées) : ", "Cited evidence that does not exist (discarded): ") + ", ".join(j["preuves_inexistantes"]))
        st.caption(f"{res.get('tokens', 0)} tokens · {res.get('latency_s', '')} s" + (" · cache" if res.get("cached") else "")
                   + (f" · {L('agent Foundry indisponible, modèle direct', 'Foundry agent unavailable, direct model')}" if res.get("agent_error") else ""))

    ui.section(L("Décision de l'employé", "Employee decision"))
    with st.form(f"case_action_{tid}", clear_on_submit=True):
        act = st.radio(L("Action", "Action"), list(intel.ACTIONS), horizontal=True,
                       format_func=lambda x: intel.ACTIONS[x][1 if lang == "en" else 0])
        why = st.text_area(L("Justification / contexte (obligatoire)", "Rationale / context (required)"), height=80)
        if st.form_submit_button(L("Enregistrer", "Save"), type="primary"):
            if not why.strip():
                st.error(L("Une justification est requise (piste d'audit).", "A rationale is required (audit trail)."))
            else:
                j = (res or {}).get("judge") or {}
                intel.log_case(tid, "employee_action", {"action": act, "rationale": why.strip(), "as_of": str(as_of),
                                                        "judge_recommendation": j.get("recommandation"),
                                                        "system_recommendation": ((res or {}).get("system") or {}).get("decision")},
                               st.session_state.get("analyst"))
                if act == "context":
                    st.session_state[f"case_note_{tid}"] = why.strip()
                if act in ("accept", "escalate", "confirm_fraud", "confirm_legit", "reject"):
                    dec = {"accept": j.get("recommandation") or ((res or {}).get("system") or {}).get("decision") or "ESCALADER",
                           "escalate": "ESCALADER", "confirm_fraud": "BLOQUER", "confirm_legit": "VALIDER"}.get(act)
                    if dec:
                        tools.record_decision(tid, dec, "élevée" if act.startswith("confirm") else "moyenne", why.strip(),
                                              analyst=st.session_state.get("analyst"), source="dossier_enquete")
                st.success(L("Enregistré dans le dossier (et le journal d'audit si c'est une décision).",
                             "Saved in the case (and in the audit log if it is a decision)."))
    h = intel.history(tid)
    if len(h):
        with st.expander(L(f"Historique du dossier · {len(h)} événement(s)", f"Case history · {len(h)} event(s)"), icon=":material/history:"):
            cols = [c for c in ["ts", "event", "analyst", "action", "rationale", "recommendation", "system", "judge_model", "triggers", "knowledge"] if c in h]
            st.dataframe(h[cols].iloc[::-1], hide_index=True, width="stretch")
