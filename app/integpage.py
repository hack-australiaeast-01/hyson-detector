"""Page « Intégration bancaire » : connect any bank, let the AI understand its schema, validate, approve, activate, operate.

The console drives tenants.py (the same engine as the REST API in api.py). Three simulated banks with deliberately different
schemas are provided; any CSV / JSON-lines / Parquet / SQLite export can be uploaded instead.
"""
import json
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import canonical as cn
import mapper as mp
import tenants as tn
import ui

BANKS = Path(__file__).parent / "samples" / "banks"
DEMO = {"atlas": ("Banque Atlas", BANKS / "atlas.sqlite", "SQLite · noms français · dates jj/mm/aaaa · signalements séparés",
                  "SQLite · French names · dd/mm/yyyy dates · separate fraud reports"),
        "nordic": ("Nordic Pay", BANKS / "nordic", "6 fichiers CSV · camelCase · horodatage epoch ms · EUR en centimes · journaux d'authentification",
                   "6 CSV files · camelCase · epoch-ms timestamps · EUR in cents · authentication logs"),
        "sahel": ("Sahel Bank", BANKS / "sahel_extract.jsonl", "Un seul extrait JSON · pays ISO-3 · montants « 1 234,500 » · aucune étiquette",
                  "One JSON extract · ISO-3 countries · \"1 234,500\" amounts · no labels")}
STATUS = {"draft": ("Brouillon", "Draft", ui.MUTED), "mapped": ("Correspondance à revoir", "Mapping under review", ui.AMBER),
          "validated": ("Validée", "Validated", ui.BLUE), "approved": ("Approuvée", "Approved", ui.TEAL), "active": ("Active", "Active", ui.GREEN)}
SHORT = {"draft": ("Brouillon", "Draft"), "mapped": ("Correspondance", "Mapping"), "validated": ("Validée", "Validated"),
         "approved": ("Approuvée", "Approved"), "active": ("Active", "Active")}
GATE = {"green": ("Prête", "Ready", ui.GREEN), "amber": ("Prête avec réserves", "Ready with caveats", ui.AMBER),
        "red": ("Bloquée", "Blocked", ui.RED)}


def _control(tid):
    truth = json.loads((BANKS / "truth.json").read_text(encoding="utf-8")) if (BANKS / "truth.json").exists() else {}
    t = truth.get(tid, {})
    ctl = {k: t[k] for k in ("transactions", "frauds") if k in t}
    if tid == "nordic" and "amount_eur" in t:
        ctl["amount"] = t["amount_eur"]
    elif "amount_tnd" in t:
        ctl["amount_tnd"] = t["amount_tnd"]
    return ctl


def _tenant(tid):
    try:
        return tn.Tenant(tid)
    except tn.TenantError:
        return None


def page_integration(c):
    L = c.L
    ui.hero(L("Données · plateforme multi-banques", "Data · multi-bank platform"), L("Intégration bancaire universelle", "Universal banking integration"),
            L("Branchez n'importe quelle banque, quel que soit son schéma : l'IA découvre les tables, propose la correspondance avec notre "
              "modèle canonique, mesure la qualité, et n'active que les modules que les données permettent. Rien ne passe en production "
              "sans une approbation nominative.",
              "Connect any bank, whatever its schema: the AI discovers the tables, proposes the mapping to our canonical model, measures "
              "quality, and activates only the modules the data supports. Nothing reaches production without a named approval."), c.chips())
    ui.hint(L("Les pages Hyson (file d'alertes, procès, réseau…) tournent sur le tenant Hyson (Fabric, lakehouse lh_fraud). Chaque nouvelle "
              "banque reçoit ici son propre espace isolé : données pseudonymisées, configuration, modèle, mémoire et journal d'audit. "
              "Même moteur que l'API REST (<code>app/api.py</code>).",
              "The Hyson pages (alert queue, trial, network…) run on the Hyson tenant (Fabric, lakehouse lh_fraud). Each new bank gets its "
              "own isolated space here: pseudonymised data, configuration, model, memory and audit trail. Same engine as the REST API "
              "(<code>app/api.py</code>)."))

    existing = tn.list_tenants()
    cur = st.session_state.get("integ_tid")
    cur = cur if cur in existing else (existing[0] if existing else None)
    a, b = st.columns([2, 3])
    with a:
        if existing:
            cur = st.selectbox(L("Banque (tenant)", "Bank (tenant)"), existing, index=existing.index(cur) if cur in existing else 0,
                               format_func=lambda x: f"{tn.Tenant(x).config['name']} · {x}")
            st.session_state.integ_tid = cur
    t = _tenant(cur) if cur else None
    with b:
        if t:
            cfg = t.config
            fr, en, col = STATUS[cfg["status"]]
            st.markdown(ui.chip(L("Statut : ", "Status: ") + L(fr, en), col) + " " +
                        ui.chip(L("Correspondance v", "Mapping v") + str(cfg["mapping_version"])) + " " +
                        (ui.chip(L("Modèle v", "Model v") + str(cfg["model"]), ui.TEAL) if cfg.get("model") else ""), unsafe_allow_html=True)
            pills = []
            for s in tn.STATUSES:
                done = STATUSES_DONE(cfg["status"], s)
                c0 = STATUS[s][2] if done else ui.SOFT
                pills.append(f"<span style='display:inline-block;padding:2px 9px;border-radius:999px;font-size:.74rem;font-weight:600;"
                             f"border:1px solid {c0}55;background:{c0}{'14' if done else '00'};color:{c0}'>{'✓ ' if done else ''}"
                             f"{ui.esc(L(*SHORT[s]))}</span>")
            st.markdown("<div style='margin-top:6px;line-height:2'>" + " <span style='color:#8A97AB'>›</span> ".join(pills) + "</div>",
                        unsafe_allow_html=True)

    tabs = st.tabs([L("1 · Connecter", "1 · Connect"), L("2 · Découvrir", "2 · Discover"), L("3 · Comprendre", "3 · Understand"),
                    L("4 · Valider", "4 · Validate"), L("5 · Approuver & activer", "5 · Approve & activate"),
                    L("6 · Exploiter", "6 · Operate"), L("7 · Journal & API", "7 · Audit & API")])
    with tabs[0]:
        _connect(L)
    if t is None:
        for tb in tabs[1:]:
            with tb:
                st.info(L("Connectez d'abord une banque (onglet 1).", "Connect a bank first (tab 1)."))
        return
    with tabs[1]:
        _discover(t, L)
    with tabs[2]:
        _understand(t, L, c.lang)
    with tabs[3]:
        _validate(t, L)
    with tabs[4]:
        _approve(t, L)
    with tabs[5]:
        _operate(t, L, c.lang)
    with tabs[6]:
        _journal(t, L)


def STATUSES_DONE(status, s):
    return tn.STATUSES.index(status) >= tn.STATUSES.index(s)


# ---------------------------------------------------------------- 1 connect
def _connect(L):
    ui.section(L("Banques simulées (schémas volontairement différents)", "Simulated banks (deliberately different schemas)"))
    cols = st.columns(3)
    for col, (tid, (name, src, fr, en)) in zip(cols, DEMO.items()):
        with col:
            st.markdown(f"**{name}**  \n<span style='color:{ui.MUTED};font-size:.85rem'>{ui.esc(L(fr, en))}</span>", unsafe_allow_html=True)
            x, y = st.columns(2)
            if x.button(L("Charger", "Load"), key=f"ld_{tid}", width="stretch", help=L("Crée l'espace et charge les fichiers bruts ; "
                        "vous faites ensuite chaque étape.", "Creates the space and loads the raw files; you then run each step.")):
                tt, key = tn.Tenant.create(tid, name, actor="console", replace=True)
                tt.ingest(str(src), actor="console")
                st.session_state.integ_tid, st.session_state.integ_key = tid, key
                st.rerun()
            if y.button(L("Parcours complet", "Full run"), key=f"full_{tid}", width="stretch", type="primary",
                        help=L("Toutes les étapes en un clic (démo) : les décisions signalées sont confirmées au nom « démo ».",
                               "Every step in one click (demo): flagged decisions are confirmed under the name \"demo\".")):
                with st.spinner(L("Découverte, correspondance, validation, approbation, modèle, mémoire…",
                                  "Discovery, mapping, validation, approval, model, memory…")):
                    tt, key = tn.onboard_demo(tid, str(src), name, _control(tid), approver=L("démo", "demo"), actor="console")
                st.session_state.integ_tid, st.session_state.integ_key = tid, key
                st.rerun()
    ui.section(L("Ou votre propre export", "Or your own export"))
    up = st.file_uploader(L("Fichiers CSV, JSON-lines, JSON, Parquet ou base SQLite (plusieurs tables acceptées)",
                            "CSV, JSON-lines, JSON, Parquet files or a SQLite database (several tables accepted)"),
                          type=["csv", "txt", "jsonl", "ndjson", "json", "parquet", "sqlite", "db"], accept_multiple_files=True)
    name = st.text_input(L("Nom de la banque", "Bank name"), placeholder="Banque X")
    if st.button(L("Créer l'espace et charger", "Create the space and load"), disabled=not (up and name.strip())):
        tid = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:30] or "banque"
        tid = tid if len(tid) >= 3 else tid + "-bank"
        try:
            tt, key = tn.Tenant.create(tid, name.strip(), actor="console", replace=False)
        except tn.TenantError as exc:
            st.error(str(exc))
            return
        try:
            tt.ingest([(f.name, f.getvalue()) for f in up], actor="console")
        except Exception as exc:
            st.error(L("Lecture impossible : ", "Cannot read: ") + str(exc)[:200])
            return
        st.session_state.integ_tid, st.session_state.integ_key = tid, key
        st.rerun()
    if st.session_state.get("integ_key"):
        st.caption(L("Clé API administrateur de cette banque (affichée une seule fois, stockée hachée) :",
                     "Admin API key for this bank (shown once, stored hashed):"))
        st.code(st.session_state.pop("integ_key"), language=None)


# ---------------------------------------------------------------- 2 discover
def _discover(t, L):
    s = t.discovery()
    if st.button(L("Découvrir le schéma", "Discover the schema"), type="primary" if s is None else "secondary"):
        s = t.discover("console")
    if not s:
        return
    a, b, c3 = st.columns(3)
    a.metric(L("Tables", "Tables"), len(s["tables"]))
    b.metric(L("Colonnes", "Columns"), sum(len(v["columns"]) for v in s["tables"].values()))
    c3.metric(L("Liens détectés", "Links found"), len(s["relations"]))
    if s["relations"]:
        dot = ["digraph{rankdir=LR;node[shape=box,style=rounded,fontname=Inter,fontsize=11];edge[fontsize=9,color=\"#8A97AB\"]"]
        for tname, v in s["tables"].items():
            dot.append(f'"{tname}"[label="{tname}\\n{v["rows"]:,} {L("lignes", "rows")}"]'.replace(",", " "))
        for r in s["relations"]:
            ft, fc = r["from"].split(".", 1)
            tt, tc = r["to"].split(".", 1)
            dot.append(f'"{ft}"->"{tt}"[label="{fc}"]')
        st.graphviz_chart("\n".join(dot) + "}", width="stretch")
    for tname, v in s["tables"].items():
        with st.expander(f"{tname} · {v['rows']:,} {L('lignes', 'rows')}".replace(",", " ")):
            rows = []
            for col, p in v["columns"].items():
                ex = ", ".join(p.get("values", [])[:4]) if p["kind"] in ("code", "bool", "currency", "country2", "country3") else (
                    f"{p['stats']['min']:g} … {p['stats']['max']:g}" if "stats" in p else p.get("datetime", {}).get("format", ""))
                rows.append({L("Colonne", "Column"): col, L("Nature", "Kind"): p["kind"], L("Vide", "Empty"): p["null_rate"],
                             L("Distinctes", "Distinct"): p["distinct"], L("Clé", "Key"): "✓" if p["unique"] else "", L("Aperçu", "Preview"): ex})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={L("Vide", "Empty"): st.column_config.NumberColumn(format="percent")})
    st.caption(L("Seules des statistiques sont montrées (jamais d'identifiants ni de lignes brutes). Les liens sont trouvés par inclusion "
                 "des valeurs (≥ 90 % des valeurs d'une colonne présentes dans une clé d'une autre table).",
                 "Only statistics are shown (never identifiers or raw rows). Links are found by value inclusion (≥ 90% of a column's "
                 "values present in another table's key)."))


# ---------------------------------------------------------------- 3 understand (mapping)
def _understand(t, L, lang):
    m = t.mapping()
    if m is None:
        if st.button(L("Proposer la correspondance", "Propose the mapping"), type="primary"):
            t.propose_mapping("console")
            st.rerun()
        st.caption(L("Correspondance par règles (noms en français/anglais/camelCase + nature des valeurs), 0 jeton.",
                     "Rule-based mapping (French/English/camelCase names + value kinds), 0 tokens."))
        return
    raw = t.raw()
    ents = [None] + list(cn.ENTITIES)
    ui.section(L("Rôle de chaque table", "Role of each table"))
    cols = st.columns(min(4, max(1, len(raw))))
    for i, tname in enumerate(raw):
        cur = m["roles"].get(tname)
        new = cols[i % len(cols)].selectbox(tname, ents, index=ents.index(cur) if cur in ents else 0, key=f"role_{tname}_{m['version']}",
                                            format_func=lambda e: L("— ignorée —", "— ignored —") if e is None else e)
        if new != cur:
            t.update_mapping([{"op": "role", "table": tname, "entity": new}], actor="console")
            st.rerun()

    flags = tn.Tenant.open_flags(m)
    ui.section(L("Décisions à confirmer", "Decisions to confirm") + f" · {len(flags)}")
    if flags:
        for f in flags:
            x, y = st.columns([6, 1])
            x.markdown(f"<span style='color:{ui.AMBER}'>●</span> **{ui.esc(f.get('table', ''))}** — {ui.esc(f[lang if lang in f else 'fr'])}",
                       unsafe_allow_html=True)
            if y.button(L("Confirmer", "Confirm"), key=f"cf_{tn.flag_id(f)}_{m['version']}"):
                t.update_mapping([{"op": "confirm", "flag": tn.flag_id(f)}], actor="console")
                st.rerun()
        if st.button(L("Tout confirmer", "Confirm all")):
            t.update_mapping([{"op": "confirm_all"}], actor="console")
            st.rerun()
    else:
        st.success(L("Aucune décision en attente.", "No pending decision."))
    for f in m["flags"]:
        if f["level"] in ("info", "warning"):
            st.caption(("⚠️ " if f["level"] == "warning" else "ℹ️ ") + f[lang if lang in f else "fr"])

    ui.section(L("Correspondance par table", "Mapping per table"))
    for tname, spec in m["tables"].items():
        with st.expander(f"{tname} → {spec['entity']} · {len(spec['fields'])} {L('champs', 'fields')}", expanded=False):
            rows = []
            for field, fs in spec["fields"].items():
                tr = []
                if fs.get("format"):
                    tr.append(fs["format"])
                if fs.get("scale", 1) != 1:
                    tr.append(f"× {fs['scale']}")
                if fs.get("values"):
                    tr.append(", ".join(f"{k}→{v or '∅'}" for k, v in list(fs["values"].items())[:4]))
                if fs.get("pseudonymise"):
                    tr.append(L("pseudonymisé (HMAC)", "pseudonymised (HMAC)"))
                if fs.get("rule") == "presence":
                    tr.append(L("présence = fraude", "presence = fraud"))
                rows.append({L("Champ canonique", "Canonical field"): field, L("Colonne source", "Source column"): fs.get("source") or "—",
                             L("Confiance", "Confidence"): fs.get("confidence", 1.0), L("Traduction", "Translation"): " · ".join(tr)})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={L("Confiance", "Confidence"): st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
            if spec.get("excluded"):
                st.markdown(" ".join(ui.chip(f"{k} — {v}", ui.RED) for k, v in spec["excluded"].items()), unsafe_allow_html=True)
            if spec.get("ignored"):
                st.caption(L("Colonnes non utilisées : ", "Unused columns: ") + ", ".join(spec["ignored"]))
            x, y, z = st.columns([2, 2, 1])
            field = x.selectbox(L("Corriger un champ", "Fix a field"), list(cn.ENTITIES[spec["entity"]]), key=f"fx_{tname}_{m['version']}")
            options = [None] + [c for c in raw[tname].columns if c not in spec.get("excluded", {})]
            curv = spec["fields"].get(field, {}).get("source")
            src = y.selectbox(L("Colonne", "Column"), options, index=options.index(curv) if curv in options else 0, key=f"fs_{tname}_{m['version']}",
                              format_func=lambda v: L("— aucune —", "— none —") if v is None else v)
            if z.button(L("Appliquer", "Apply"), key=f"fa_{tname}_{m['version']}"):
                try:
                    t.update_mapping([{"op": "set", "table": tname, "field": field, "source": src}], actor="console")
                    st.rerun()
                except tn.TenantError as exc:
                    st.error(str(exc))
    import copilot
    if copilot.configured() and st.button(L("Demander une revue à l'IA (noms et statistiques seulement)", "Ask the AI for a review (names and statistics only)")):
        with st.spinner("…"):
            res = mp.ai_review(t.discovery() or t.discover("console"), m, lang)
        if res and res.get("suggestions"):
            st.dataframe(pd.DataFrame(res["suggestions"]), hide_index=True, width="stretch")
            st.caption(L("Suggestions seulement : appliquez-les ci-dessus si vous êtes d'accord.", "Suggestions only: apply them above if you agree."))
        else:
            st.info(L("L'IA ne propose aucun changement.", "The AI suggests no change.") if res and "error" not in res else str(res))


# ---------------------------------------------------------------- 4 validate
def _validate(t, L):
    if t.mapping() is None:
        st.info(L("Proposez d'abord la correspondance (onglet 3).", "Propose the mapping first (tab 3)."))
        return
    ctl0 = _control(t.id) if t.id in DEMO else {}
    st.caption(L("Totaux de contrôle fournis par la banque (rapprochement). Laissez 0 pour ignorer.",
                 "Control totals provided by the bank (reconciliation). Leave 0 to skip."))
    a, b, c3 = st.columns(3)
    n = a.number_input(L("Nombre d'opérations", "Number of operations"), min_value=0, value=int(ctl0.get("transactions", 0)))
    f = b.number_input(L("Fraudes déclarées", "Reported frauds"), min_value=0, value=int(ctl0.get("frauds", 0)))
    amt_key = "amount" if "amount" in ctl0 else "amount_tnd"
    amt = c3.number_input(L("Montant total (devise source)" if amt_key == "amount" else "Montant total (TND)",
                            "Total amount (source currency)" if amt_key == "amount" else "Total amount (TND)"),
                          min_value=0.0, value=float(ctl0.get(amt_key, 0.0)), format="%.3f")
    if st.button(L("Construire et valider", "Build and validate"), type="primary"):
        with st.spinner(L("Traduction, contrôles qualité, test de chaque indicateur…", "Translation, quality checks, testing every KPI…")):
            t.build("console")
            t.validate({k: v for k, v in {"transactions": n, "frauds": f, amt_key: amt}.items() if v}, "console")
    info, val = t.build_info(), t.validation()
    if not info:
        return
    r = info["readiness"]
    fr, en, col = GATE[r["gate"]]
    x, y, z, w = st.columns(4)
    with x:
        ui.kpi(L("Score de préparation", "Readiness score"), f"{r['score']}/100", f"<span style='color:{col}'>● {L(fr, en)}</span>")
    with y:
        ui.kpi(L("Opérations", "Operations"), f"{r['entities'].get('transactions', 0):,}".replace(",", " "))
    with z:
        ui.kpi(L("Modules activables", "Modules available"), f"{sum(v['active'] for v in info['modules'].values())}/{len(info['modules'])}")
    with w:
        ui.kpi(L("Indicateurs", "KPIs"), f"{sum(v['active'] for v in info['kpis'].values())}/{len(info['kpis'])}")
    for i in r["issues"]:
        (st.error if i["level"] == "blocker" else st.warning if i["level"] == "warning" else st.info)(L(i["fr"], i["en"]))
    if val and val.get("reconciliation"):
        ui.section(L("Rapprochement avec les totaux de la banque", "Reconciliation with the bank's totals"))
        st.dataframe(pd.DataFrame([{L("Contrôle", "Check"): k, L("Attendu", "Expected"): v["expected"], L("Trouvé", "Found"): v["found"],
                                    "OK": "✓" if v["ok"] else "✗"} for k, v in val["reconciliation"].items()]), hide_index=True, width="stretch")
    ui.section(L("Matrice des capacités : ce que les données permettent", "Capability matrix: what the data supports"))
    hum = lambda r: r.replace("|", L(" ou ", " or ")).replace("model", L("modèle approuvé", "approved model"), 1) if r.startswith("model") else \
        r.replace("|", L(" ou ", " or "))
    rows = [{L("Module", "Module"): L(v["fr"], v["en"]), L("Actif", "Active"): "✓" if v["active"] else "✗",
             L("Manque", "Missing"): ", ".join(hum(x) for x in v["missing"])} for v in info["modules"].values()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander(L("Détail des contrôles", "Check details")):
        st.json(r["checks"], expanded=False)


# ---------------------------------------------------------------- 5 approve & activate
def _approve(t, L):
    cfg = t.config
    m = t.mapping()
    who = st.text_input(L("Votre nom (approbateur)", "Your name (approver)"), key="integ_who")
    if cfg["status"] == "active":
        st.success(L("Banque active : la correspondance v", "Bank active: mapping v") + str(cfg["activated"]["mapping_version"]) +
                   L(" est en production. Toute modification crée une nouvelle version à revalider et réapprouver.",
                     " is in production. Any change creates a new version to re-validate and re-approve."))
    a, b = st.columns(2)
    if cfg["status"] != "active" and a.button(L("Approuver la correspondance v", "Approve mapping v") + str(cfg["mapping_version"]),
                                              disabled=cfg["status"] != "validated", width="stretch"):
        try:
            t.approve(who)
            st.rerun()
        except tn.TenantError as exc:
            st.error(str(exc))
    if cfg["status"] != "active" and b.button(L("Activer en production", "Activate in production"), disabled=cfg["status"] != "approved",
                                              type="primary", width="stretch"):
        try:
            t.activate(who or "?")
            st.rerun()
        except tn.TenantError as exc:
            st.error(str(exc))
    if cfg["status"] == "validated" and m and tn.Tenant.open_flags(m):
        st.warning(L(f"{len(tn.Tenant.open_flags(m))} décision(s) à confirmer dans l'onglet 3 avant approbation.",
                     f"{len(tn.Tenant.open_flags(m))} decision(s) to confirm in tab 3 before approval."))
    if cfg.get("approved"):
        st.caption(L("Approuvée par ", "Approved by ") + f"{cfg['approved']['by']} · {cfg['approved']['at']} · v{cfg['approved']['mapping_version']}")
    if cfg.get("activated"):
        st.caption(L("Activée par ", "Activated by ") + f"{cfg['activated']['by']} · {cfg['activated']['at']}" +
                   L(" · colonnes sensibles effacées de la zone brute.", " · sensitive columns erased from the raw zone."))

    ui.section(L("Modèle propre à la banque", "Bank-specific model"))
    info = t.build_info()
    if not info or not info["modules"]["tenant_model"]["active"]:
        st.info(L("Pas d'étiquettes de fraude : pas de modèle supervisé. La file utilise le score de la banque s'il existe, sinon les "
                  "écarts aux habitudes (non supervisé, présenté comme tel).",
                  "No fraud labels: no supervised model. The queue uses the bank's score if any, otherwise departures from habits "
                  "(unsupervised, presented as such)."))
        return
    if st.button(L("Entraîner un modèle candidat", "Train a candidate model")):
        with st.spinner("…"):
            try:
                t.train_model(who or "console")
            except tn.TenantError as exc:
                st.error(str(exc))
    for mdl in reversed(t.models()):
        me, base = mdl["metrics"], mdl.get("baseline", {}).get("metrics")
        st.markdown(f"**v{mdl['version']}** · {L(*{'candidate': ('candidat, en attente d’approbation', 'candidate, awaiting approval'), 'approved': ('approuvé', 'approved')}.get(mdl['status'], (mdl['status'],) * 2))}"
                    f" · {L('entraîné sur', 'trained on')} {mdl['train_period'][0]} → {mdl['train_period'][1]}"
                    f" · {L('testé sur', 'tested on')} {mdl['test_period'][0]} → {mdl['test_period'][1]}")
        rows = [{L("Mesure (mois de test)", "Metric (test months)"): "PR-AUC", L("Modèle", "Model"): me["pr_auc"],
                 L("Score actuel de la banque", "Bank's current score"): base["pr_auc"] if base else None,
                 L("Hasard", "Random"): me["base_rate"]},
                {L("Mesure (mois de test)", "Metric (test months)"): L("Précision top 1 %", "Precision top 1%"),
                 L("Modèle", "Model"): me["top_1pct"]["precision"], L("Score actuel de la banque", "Bank's current score"):
                 base["top_1pct"]["precision"] if base else None, L("Hasard", "Random"): me["base_rate"]},
                {L("Mesure (mois de test)", "Metric (test months)"): L("Fraudes trouvées top 5 %", "Frauds found top 5%"),
                 L("Modèle", "Model"): me["top_5pct"]["recall"], L("Score actuel de la banque", "Bank's current score"):
                 base["top_5pct"]["recall"] if base else None, L("Hasard", "Random"): 0.05}]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if mdl["status"] == "candidate" and st.button(L("Approuver ce modèle", "Approve this model") + f" v{mdl['version']}", key=f"am_{mdl['version']}"):
            try:
                t.approve_model(mdl["version"], who)
                st.rerun()
            except tn.TenantError as exc:
                st.error(str(exc))
    st.caption(L("Régression logistique sur des signaux génériques calculés uniquement sur le passé de chaque client ; découpage temporel ; "
                 "jamais de ré-entraînement automatique ; la mémoire (RAG) ne sert jamais d'entraînement.",
                 "Logistic regression on generic signals computed only from each customer's past; time split; never retrained "
                 "automatically; the memory (RAG) is never used for training."))


# ---------------------------------------------------------------- 6 operate
def _operate(t, L, lang):
    cfg = t.config
    if cfg["status"] != "active":
        st.info(L("Activez la banque (onglet 5) pour ouvrir l'espace de travail.", "Activate the bank (tab 5) to open the workspace."))
        return
    dash = cfg.get("dashboard") or {}
    ui.section(L("Tableau de bord généré pour cette banque", "Dashboard generated for this bank"))
    kpis = dash.get("kpis", [])
    kinds = [k for k in kpis if cn.KPIS[k][4] == "kpi"]
    charts = [k for k in kpis if cn.KPIS[k][4] != "kpi"]
    if kinds:
        cols = st.columns(len(kinds))
        for col, k in zip(cols, kinds):
            df = t.kpi(k)
            row = df.iloc[0]
            fmt = lambda v: f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", " ") if isinstance(v, float) else f"{v:,}".replace(",", " ")
            with col:
                pct = lambda c: " %" if str(c).endswith("_pct") else ""
                ui.kpi(L(cn.KPIS[k][1], cn.KPIS[k][2]), fmt(row.iloc[0]) + pct(row.index[0]),
                       " · ".join(f"{ui.esc(str(c).replace('_', ' '))} : <b>{fmt(v)}{pct(c)}</b>" for c, v in list(row.items())[1:]))
    for i in range(0, len(charts), 2):
        cols = st.columns(2)
        for col, k in zip(cols, charts[i:i + 2]):
            df = t.kpi(k)
            with col:
                st.markdown(f"**{L(cn.KPIS[k][1], cn.KPIS[k][2])}**")
                if df.empty:
                    st.caption("—")
                    continue
                x, y = df.columns[0], df.columns[1]
                fig = (px.line(df, x=x, y=y, height=230) if cn.KPIS[k][4] == "line" else px.bar(df, x=x, y=y, height=230))
                fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
                fig.update_traces(**({"line_color": ui.BLUE} if cn.KPIS[k][4] == "line" else {"marker_color": ui.BLUE}))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"k_{t.id}_{k}")

    ui.section(L("File d'alertes (30 derniers jours)", "Alert queue (last 30 days)"))
    al = t.alerts(15, lang=lang)
    kind = al["score_kind"].iat[0] if len(al) else ""
    st.caption({"model": L("Score du modèle approuvé de la banque.", "Score from the bank's approved model."),
                "bank_score": L("Score actuel de la banque (aucun modèle Hyson approuvé pour l'instant).",
                                "The bank's current score (no approved Hyson model yet)."),
                "behaviour": L("Écart aux habitudes du client (non supervisé) : ce n'est pas une probabilité de fraude.",
                               "Departure from the customer's habits (unsupervised): not a fraud probability.")}.get(kind, ""))
    show = al.drop(columns=["is_fraud", "score_kind"], errors="ignore").copy()
    show["reasons"] = show["reasons"].map(lambda r: " · ".join(r))
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        "score": st.column_config.ProgressColumn(L("score", "score"), min_value=0, max_value=float(max(1.0, show["score"].max())), format="%.3f"),
        "transaction_id": L("opération", "operation"), "timestamp": L("date", "date"), "customer_id": L("client (pseudonyme)", "customer (pseudonym)"),
        "amount_tnd": st.column_config.NumberColumn(L("montant (TND)", "amount (TND)"), format="%.2f"), "channel": L("canal", "channel"),
        "country": L("pays", "country"), "reasons": L("pourquoi", "why")})

    ui.section(L("Mémoire de la banque (RAG)", "The bank's memory (RAG)"))
    up = st.file_uploader(L("Ajouter des procédures internes (texte / markdown)", "Add internal procedures (text / markdown)"),
                          type=["txt", "md"], accept_multiple_files=True, key=f"pol_{t.id}")
    if up and st.button(L("Indexer", "Index")):
        n = t.build_memory({f.name: f.getvalue().decode("utf-8", "ignore") for f in up}, actor="console")
        st.success(L(f"{n} passages indexés.", f"{n} passages indexed."))
    q = st.text_input(L("Question à la mémoire de cette banque", "Question to this bank's memory"),
                      placeholder=L("Ex. : comment se présentent nos fraudes au DAB ?", "E.g. what do our ATM frauds look like?"))
    if q:
        res = t.memory_answer(q, lang)
        st.markdown(res["answer"])
        if res["sources"]:
            st.caption(L("Sources : ", "Sources: ") + ", ".join(f"{h['id']} ({h['score']:.2f})" for h in res["sources"]))

    ui.section(L("Temps réel : opération reçue par webhook", "Real time: operation received by webhook"))
    st.caption(L("Simule une opération envoyée par la banque dans SON format (traduite par la correspondance active, puis notée).",
                 "Simulates an operation sent by the bank in ITS format (translated by the active mapping, then scored)."))
    if st.button(L("Envoyer une opération test", "Send a test operation")):
        m = t.mapping(cfg["activated"]["mapping_version"])
        tname = next(k for k, e in m["roles"].items() if e == "transactions")
        raw = t.raw()[tname]
        rec = raw.sample(1, random_state=None).iloc[0].to_dict()
        idcol = m["tables"][tname]["fields"]["transaction_id"]["source"]
        rec[idcol] = f"LIVE-{pd.Timestamp.now():%H%M%S%f}"
        rec = {k: (None if pd.isna(v) else v) for k, v in rec.items()}
        res = t.ingest_events([json.loads(json.dumps(rec, default=str))], actor="console", lang=lang)
        st.json(res)


# ---------------------------------------------------------------- 7 audit & API
def _journal(t, L):
    ok, broken = t.verify_audit()
    (st.success if ok else st.error)(L("Chaîne d'audit intègre (chaque entrée scelle la précédente, SHA-256)." if ok else
                                       f"Chaîne d'audit rompue à l'entrée {broken}.",
                                       "Audit chain intact (each entry seals the previous one, SHA-256)." if ok else f"Audit chain broken at entry {broken}."))
    log = pd.DataFrame(t.audit_log())
    if not log.empty:
        log["details"] = log["details"].map(lambda d: json.dumps(d, ensure_ascii=False, default=str)[:160])
        log["hash"] = log["hash"].str[:12] + "…"
        st.dataframe(log[["ts", "actor", "action", "details", "hash"]].iloc[::-1], hide_index=True, width="stretch")
    ui.section("API REST")
    st.code("""cd app && uvicorn api:app --port 8600          # docs: http://localhost:8600/docs
POST /v1/tenants                         (x-platform-key)   create a bank -> admin key + webhook secret
POST /v1/tenants/{id}/sources            (ingest|admin)     upload CSV / JSONL / Parquet / SQLite
POST /v1/tenants/{id}/discover           (admin)            tables, keys, foreign keys
POST /v1/tenants/{id}/mapping/propose    (admin)            AI-assisted mapping + flags to confirm
PUT  /v1/tenants/{id}/mapping            (admin)            set / confirm / role / rate  -> new version
POST /v1/tenants/{id}/validate           (admin)            readiness + KPI tests + reconciliation
POST /v1/tenants/{id}/approve | activate (admin, named)     human approval, then production
POST /v1/tenants/{id}/model/train | /model/{v}/approve      candidate model, approved by a named admin
GET  /v1/tenants/{id}/capabilities | kpis/{kpi} | alerts    (analyst)
POST /v1/tenants/{id}/memory/ask                            (analyst) this bank's memory only
POST /v1/tenants/{id}/events   HMAC-SHA256 signed, 5-min replay window, idempotent
GET  /v1/tenants/{id}/audit                                 (admin) hash-chained trail""", language="text")
