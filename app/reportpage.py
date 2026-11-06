"""Page « Rapports IA » : ask for a report in plain language, check what was understood, generate, review, edit, approve, export."""
import json
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import report_i18n as I
import report_interpret as RP
import report_sources as RS
import report_store as RSt
import ui

EXAMPLES = [("Rapport mensuel d'analyse de la fraude pour la direction", "Monthly fraud analysis report for management"),
            ("Rapport trimestriel détaillé sur la fraude aux DAB, comparé au trimestre précédent, par type de carte, avec les faiblesses "
             "cyber et opérationnelles et des recommandations", "Detailed quarterly report on ATM fraud vs the previous quarter, by card type, with "
             "cyber and operational weaknesses and recommendations"),
            ("Évaluation du risque cybersécurité sur août 2026 pour l'équipe sécurité", "Cybersecurity risk assessment for August 2026 for the security team"),
            ("Rapport d'enquête sur TX01631347", "Investigation report on TX01631347"),
            ("Rapport opérationnel du 01/06/2026 au 31/07/2026", "Operational report from 01/06/2026 to 31/07/2026"),
            ("تقرير ملخص للإدارة عن الاحتيال في الربع الثاني 2026", "Executive summary in Arabic for Q2 2026")]


def _opts(d, lang):
    return list(d), (lambda k: I.tr(lang, *d[k][:3]))


def page_reports(c):
    L, lang = c.L, c.lang
    ui.hero(L("Pilotage · rapports professionnels", "Steering · professional reports"), L("Rapports IA", "AI reports"),
            L("Demandez un rapport en langage naturel : la plateforme comprend le besoin, interroge les données, vérifie chaque chiffre, rédige pour "
              "le bon lecteur, puis attend la relecture et l'approbation d'un employé habilité. Chaque chiffre renvoie à sa preuve.",
              "Ask for a report in plain language: the platform understands the need, queries the data, verifies every figure, writes for the right "
              "reader, then waits for review and approval by an authorised employee. Every figure points to its evidence."), c.chips())
    sources = RS.available()
    if not sources:
        st.error(L("Aucune source de données disponible.", "No data source available."))
        return
    # ------------------------------------------------------------ 1. request
    ui.start_here(L("Étape 1 · décrivez le rapport souhaité", "Step 1 · describe the report you need"))
    a, b = st.columns([2, 1])
    sid = a.selectbox(L("Banque / source de données", "Bank / data source"), [s[0] for s in sources], format_func=dict(sources).get, key="rep_src")
    store = RSt.store(sid)
    tpl = store.templates()
    tsel = b.selectbox(L("Modèle enregistré (facultatif)", "Saved template (optional)"), [""] + list(tpl), key="rep_tpl",
                       format_func=lambda x: L("— aucun —", "— none —") if not x else x)
    if st.session_state.get("rep_example"):
        st.session_state["rep_req"] = st.session_state.pop("rep_example")
    req = st.text_area(L("Votre demande", "Your request"), key="rep_req", height=110,
                       placeholder=L("Ex. : Prépare un rapport trimestriel détaillé sur la fraude aux DAB, comparé au trimestre précédent, pour la direction.",
                                     "E.g. Prepare a detailed quarterly report on ATM fraud compared with the previous quarter, for management."))
    st.caption(L("Exemples (cliquez pour remplir) :", "Examples (click to fill):"))
    ex = st.columns(3)
    for i, (fr, en) in enumerate(EXAMPLES):
        if ex[i % 3].button(fr if lang == "fr" else en, key=f"rep_ex{i}", width="stretch"):
            st.session_state["rep_example"] = fr if (lang == "fr" or i == 5) else en
            st.rerun()
    if st.button(L("Analyser la demande", "Analyse the request"), type="primary", disabled=not (req or "").strip()):
        spec = RP.interpret(req, store.src, lang)
        if tsel:
            spec.update({k: v for k, v in tpl[tsel].items() if k in spec or k in ("sections", "focus")})
        if st.session_state.get("rep_ai_interp"):
            spec = RP.refine_with_ai(spec, spec["lang"])
        st.session_state["rep_spec"] = spec
        st.session_state.pop("rep_id", None)
    import copilot
    st.toggle(L("Affiner la compréhension avec l'IA (1 appel, texte de la demande seulement)", "Refine understanding with AI (1 call, request text only)"),
              key="rep_ai_interp", disabled=not copilot.configured())
    spec = st.session_state.get("rep_spec")
    if spec and spec.get("source") == sid:
        _configure(spec, store, L, lang)
    _workspace(store, L, lang)


# ---------------------------------------------------------------- 2. understood configuration (editable)
def _configure(spec, store, L, lang):
    ui.section(L("Étape 2 · ce que la plateforme a compris (modifiable)", "Step 2 · what the platform understood (editable)"))
    for q in spec.get("questions", []):
        st.warning(q)
    if spec.get("assumptions"):
        names = {"audience": L("lecteur", "audience"), "period": L("période", "period"), "depth": L("niveau", "depth")}
        st.caption(L("Valeurs déduites par défaut : ", "Defaults inferred: ") + " · ".join(f"{names.get(k, k)} = {v}" for k, v in spec["assumptions"]))
    src = store.src
    with st.form("rep_cfg"):
        c1, c2, c3 = st.columns(3)
        types, tf = _opts(I.TYPES, lang)
        typ = c1.selectbox(L("Type de rapport", "Report type"), types, index=types.index(spec["type"]), format_func=tf)
        auds, af = _opts(I.AUDIENCES, lang)
        aud = c2.selectbox(L("Lecteur", "Audience"), auds, index=auds.index(spec["audience"]), format_func=af)
        deps, df_ = _opts(I.DEPTHS, lang)
        dep = c3.selectbox(L("Niveau d'analyse", "Analysis depth"), deps, index=deps.index(spec["depth"]), format_func=df_)
        c4, c5, c6 = st.columns(3)
        p0 = c4.date_input(L("Début de période", "Period start"), pd.Timestamp(spec["period"][0]).date(), min_value=src.first_day, max_value=src.last_day)
        p1 = c5.date_input(L("Fin de période", "Period end"), pd.Timestamp(spec["period"][1]).date(), min_value=src.first_day, max_value=src.last_day)
        cmp_ = c6.toggle(L("Comparer à la période précédente", "Compare with the previous period"), spec.get("compare", False))
        c7, c8, c9 = st.columns(3)
        langs = list(I.LANGS)
        lg = c7.selectbox(L("Langue du rapport", "Report language"), langs, index=langs.index(spec["lang"]), format_func={"fr": "Français", "en": "English", "ar": "العربية"}.get)
        confs, cf = _opts(I.CONFIDENTIALITY, lang)
        conf = c8.selectbox(L("Confidentialité", "Confidentiality"), confs, index=confs.index(spec["confidentiality"]), format_func=cf)
        fmt = c9.selectbox(L("Format principal", "Main format"), list(I.FORMATS), index=list(I.FORMATS).index(spec["format"]), format_func=str.upper)
        c10, c11 = st.columns(2)
        chans = c10.multiselect(L("Canaux", "Channels"), list(I.CHANNEL), default=spec["scope"].get("channels", []),
                                format_func=lambda x: I.channel_label(x, lang), placeholder=L("Tous les canaux", "All channels"))
        cards_all = RP._distinct(src, "card_type")
        cards = c11.multiselect(L("Types de carte", "Card types"), cards_all, default=[x for x in spec["scope"].get("card_types", []) if x in cards_all],
                                placeholder=L("Tous les types de carte", "All card types"))
        secs_all = list(I.SECTIONS)
        secs = st.multiselect(L("Sections", "Sections"), secs_all, default=[s for s in spec["sections"] if s in secs_all],
                              format_func=lambda s: I.tr(lang, *I.SECTIONS[s]))
        case = st.text_input(L("Opération à investiguer (rapport d'enquête)", "Transaction to investigate (investigation report)"), spec.get("case_id") or "")
        import copilot
        c12, c13 = st.columns(2)
        agents = c12.checkbox(L("Inclure le débat des agents IA (≈ 18 000 jetons)", "Include the AI agents' debate (≈ 18,000 tokens)"),
                              spec.get("ai_agents", False), disabled=not copilot.configured())
        writer = c13.checkbox(L("Rédaction assistée par l'IA (chiffres vérifiés)", "AI-assisted writing (numbers verified)"), copilot.configured(),
                              disabled=not copilot.configured())
        go = st.form_submit_button(L("Générer le rapport", "Generate the report"), type="primary")
    if go:
        new = {**spec, "type": typ, "audience": aud, "depth": dep, "period": [str(p0), str(p1)], "compare": cmp_ and typ != "investigation", "lang": lg,
               "confidentiality": conf, "format": fmt, "scope": {**spec["scope"], "channels": chans, "card_types": cards},
               "sections": [s for s in secs_all if s in secs] or RP.sections_for({**spec, "type": typ, "depth": dep}),
               "case_id": case.strip().upper() or None, "ai_agents": agents}
        if typ != spec["type"]:
            new["sections"] = RP.sections_for(new)
        new["previous"] = [str(x) for x in RP.previous((p0, p1), spec.get("cadence", "custom"))] if new["compare"] else None
        new["purpose"] = RP.purpose(new, lg)
        new["questions"] = [q for q in spec.get("questions", []) if not (typ == "investigation" and new["case_id"])] if typ == "investigation" else []
        if p1 < p0:
            st.error(L("La fin de période est avant le début.", "Period end is before the start."))
            return
        with st.status(L("Pipeline d'analyse en cours…", "Analysis pipeline running…"), expanded=True) as stt:
            st.write(L("1 · Récupération des données · 2 · Analyse SQL · 3 · Vérification des preuves · 4 · Interprétation · 5 · Rédaction et graphiques",
                       "1 · Data retrieval · 2 · SQL analysis · 3 · Evidence verification · 4 · Interpretation · 5 · Writing and charts"))
            try:
                rid = store.create(new, st.session_state.get("rep_author") or L("analyste", "analyst"), use_ai=writer)
            except ValueError as exc:
                stt.update(label=str(exc), state="error")
                return
            stt.update(label=L("Rapport généré : à relire ci-dessous.", "Report generated: review it below."), state="complete")
        st.session_state["rep_id"] = st.session_state["rep_pick"] = rid
        st.session_state.pop("rep_spec", None)
        st.rerun()


# ---------------------------------------------------------------- 3. review, edit, approve, export
def _workspace(store, L, lang):
    reports = store.list()
    if not reports:
        return
    ui.section(L("Étape 3 · relire, modifier, approuver, exporter", "Step 3 · review, edit, approve, export"))
    ids = [r["id"] for r in reports]
    cur = st.session_state.get("rep_id") if st.session_state.get("rep_id") in ids else ids[0]
    if st.session_state.get("rep_pick") not in ids:
        st.session_state["rep_pick"] = cur
    lab = {r["id"]: f"{r['title']} · {r['created'][:16].replace('T', ' ')} · v{r['versions']} · "
                    f"{L('approuvé', 'approved') if r['status'] == 'approved' else L('projet', 'draft')}" for r in reports}
    rid = st.selectbox(L("Rapport", "Report"), ids, format_func=lab.get, key="rep_pick")
    st.session_state["rep_id"] = rid
    r = store.get(rid)
    b = store.version(rid)
    rl = b["spec"]["lang"]
    who = st.text_input(L("Votre nom (pour la traçabilité)", "Your name (for traceability)"), key="rep_author")
    ok = sum(c["ok"] for c in b["checks"])
    ai = b.get("ai", {})
    chips = [ui.chip(f"v{r['versions']}"), ui.chip(L("Approuvé", "Approved") if r["status"] == "approved" else L("Projet — non approuvé", "Draft — not approved"),
                                                   ui.GREEN if r["status"] == "approved" else ui.AMBER),
             ui.chip(L(f"Contrôles {ok}/{len(b['checks'])}", f"Checks {ok}/{len(b['checks'])}"), ui.GREEN if ok == len(b["checks"]) else ui.AMBER),
             ui.chip(L(f"{len(b['facts'])} preuves chiffrées", f"{len(b['facts'])} numeric evidence items")),
             ui.chip(L("Rédaction IA vérifiée : ", "AI writing verified: ") + (", ".join(ai.get("accepted", [])) or L("non", "no")) if ai.get("used")
                     else L("Rédaction déterministe (0 jeton)", "Deterministic writing (0 tokens)"))]
    st.markdown(" ".join(chips), unsafe_allow_html=True)
    tabs = st.tabs([L("Aperçu", "Preview"), L("Modifier", "Edit"), L("Preuves & contrôles", "Evidence & checks"), L("Versions & approbation", "Versions & approval"),
                    L("Exporter", "Export"), L("Identité & modèles", "Branding & templates")])
    import report_render as RR
    with tabs[0]:
        components.html(RR.html(b, draft=r["status"] != "approved" or r["approved"]["version"] != b.get("version"),
                                approval=r["approved"] if r["status"] == "approved" else None), height=900, scrolling=True)
    with tabs[1]:
        secs = {s["id"]: s for s in b["doc"]["sections"]}
        sid = st.selectbox(L("Section", "Section"), list(secs), format_func=lambda x: secs[x]["title"], key=f"rep_sec_{rid}")
        txt = "\n\n".join(blk["text"] for blk in secs[sid]["blocks"] if blk.get("text"))
        new = st.text_area(L("Texte de la section (gardez les références [F…] pour la traçabilité)", "Section text (keep [F…] references for traceability)"),
                           txt, height=220, key=f"rep_txt_{rid}_{sid}_{r['versions']}")
        x, y, z = st.columns(3)
        if x.button(L("Enregistrer la modification", "Save the edit"), type="primary", disabled=not who or new == txt, width="stretch"):
            store.edit_section(rid, sid, new, who)
            st.rerun()
        if y.button(L("Régénérer cette section", "Regenerate this section"), disabled=not who, width="stretch"):
            store.regenerate(rid, who, only_section=sid)
            st.rerun()
        if z.button(L("Analyse plus approfondie", "Deeper analysis"), disabled=not who or b["spec"]["depth"] == "detailed", width="stretch"):
            store.regenerate(rid, who, changes={"depth": "detailed", "sections": RP.sections_for({**b["spec"], "depth": "detailed"})})
            st.rerun()
        auds, af = _opts(I.AUDIENCES, lang)
        u, v = st.columns([2, 1])
        na = u.selectbox(L("Changer de lecteur (mêmes faits)", "Change audience (same facts)"), auds, index=auds.index(b["spec"]["audience"]), format_func=af)
        if v.button(L("Réécrire pour ce lecteur", "Rewrite for this audience"), disabled=not who or na == b["spec"]["audience"], width="stretch"):
            store.regenerate(rid, who, changes={"audience": na})
            st.rerun()
        if not who:
            st.caption(L("Indiquez votre nom ci-dessus pour modifier.", "Enter your name above to edit."))
        com = st.text_input(L("Ajouter un commentaire", "Add a comment"), key=f"rep_com_{rid}")
        if st.button(L("Commenter", "Comment"), disabled=not (who and com)):
            store.comment(rid, who, com, sid)
            st.rerun()
        for cm in reversed(r.get("comments", [])[-8:]):
            st.caption(f"💬 {cm['at'][:16].replace('T', ' ')} · {cm['by']} · v{cm['version']} · {cm.get('section') or ''} — {cm['text']}")
    with tabs[2]:
        reg = pd.DataFrame([{"ref": f["id"], L("élément", "item"): f["label"][rl], L("valeur", "value"): I.fmt(f["value"], f["unit"], rl),
                             L("nature", "kind"): I.kind_label(f["kind"], rl), L("méthode", "method"): f["method"], "SQL": f["sql"][:400]} for f in b["facts"]])
        st.dataframe(reg, hide_index=True, width="stretch")
        for c in b["checks"]:
            (st.success if c["ok"] else st.error if c["level"] == "error" else st.warning)(c["detail"])
        for lim in b["limits"]:
            st.info(lim[rl])
        if ai.get("rejected"):
            st.warning(L("Paragraphes IA rejetés (chiffres non retrouvés dans les preuves) : ", "AI paragraphs rejected (numbers not found in the evidence): ")
                       + json.dumps(ai["rejected"], ensure_ascii=False))
    with tabs[3]:
        hist = pd.DataFrame(r["history"])
        st.dataframe(hist, hide_index=True, width="stretch")
        if r["versions"] > 1:
            a1, a2 = st.columns(2)
            v1 = a1.number_input(L("Version A", "Version A"), 1, r["versions"], max(1, r["versions"] - 1))
            v2 = a2.number_input(L("Version B", "Version B"), 1, r["versions"], r["versions"])
            st.code(store.compare(rid, int(v1), int(v2)) or L("Aucune différence de texte.", "No text difference."), language="diff")
        if r["status"] == "approved":
            ap = r["approved"]
            st.success(L(f"Approuvé par {ap['by']} le {ap['at']} (v{ap['version']}, empreinte {ap['hash'][:16]}…). Fichiers archivés : ",
                         f"Approved by {ap['by']} on {ap['at']} (v{ap['version']}, fingerprint {ap['hash'][:16]}…). Archived files: ")
                       + ", ".join(f"{k.upper()} {v['sha256'][:10]}…" for k, v in ap["files"].items()))
        allowed = st.checkbox(L("Je suis habilité(e) à approuver ce rapport pour la banque", "I am authorised to approve this report for the bank"),
                              key=f"rep_auth_{rid}")
        if st.button(L(f"Approuver la version {r['versions']}", f"Approve version {r['versions']}"), type="primary",
                     disabled=not (who and allowed) or (r["status"] == "approved" and r["approved"]["version"] == r["versions"])):
            try:
                store.approve(rid, who)
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
    with tabs[4]:
        st.caption(L("Version approuvée → fichier archivé tel qu'approuvé. Sinon → export marqué PROJET.",
                     "Approved version → the archived file as approved. Otherwise → export marked DRAFT."))
        cols = st.columns(4)
        for col, fmt in zip(cols, I.FORMATS):
            data, mime, name = store.export(rid, fmt)
            col.download_button(fmt.upper(), data, file_name=name, mime=mime, width="stretch", key=f"dl_{rid}_{fmt}",
                                type="primary" if fmt == b["spec"]["format"] else "secondary")
    with tabs[5]:
        s = store.settings()
        with st.form("rep_settings"):
            inst = st.text_input(L("Nom de l'institution", "Institution name"), s.get("institution") or store.src.name)
            color = st.color_picker(L("Couleur principale", "Primary colour"), s.get("color") or "#1E5BD8")
            logo = st.file_uploader(L("Logo (PNG)", "Logo (PNG)"), type=["png"])
            footer = st.text_input(L("Pied de page", "Footer"), s.get("footer") or "")
            term = st.text_area(L("Terminologie (une règle par ligne : terme = remplacement)", "Terminology (one rule per line: term = replacement)"),
                                "\n".join(f"{k} = {v}" for k, v in (s.get("terminology") or {}).items()), height=80)
            dep = st.text_area(L("Départements destinataires (lecteur = nom)", "Recipient departments (audience = name)"),
                               "\n".join(f"{k} = {v}" for k, v in (s.get("departments") or {}).items()), height=80,
                               placeholder="executive = Direction Générale\ncyber = Direction de la Sécurité des SI")
            if st.form_submit_button(L("Enregistrer l'identité", "Save branding"), disabled=not who):
                import base64
                parse = lambda t: {k.strip(): v.strip() for k, v in (ln.split("=", 1) for ln in t.splitlines() if "=" in ln)}  # noqa: E731
                store.save_settings({**s, "institution": inst, "color": color, "footer": footer, "terminology": parse(term), "departments": parse(dep),
                                     "logo": base64.b64encode(logo.getvalue()).decode() if logo else s.get("logo")}, who)
                st.success(L("Identité enregistrée : appliquée aux prochains rapports.", "Branding saved: applied to the next reports."))
        name = st.text_input(L("Enregistrer la configuration de ce rapport comme modèle", "Save this report's configuration as a template"), key=f"tplname_{rid}")
        if st.button(L("Enregistrer le modèle", "Save template"), disabled=not (who and name)):
            st.success(L("Modèle enregistré : ", "Template saved: ") + store.save_template(name, b["spec"], who))
