"""Assistant — the first page: one question box in the middle (like ChatGPT), a soft blue aura behind it.

Any question in natural language → askdata (star schema, guarded SQL) → a short summary, a chart, the table and the SQL;
a question about one transaction (TX…) → the fraud copilot on that alert. No numbers on the page until the user asks.
"""
import re

import pandas as pd
import plotly.express as px
import streamlit as st

import askdata
import copilot
import ui

CSS = """
<style>
.stApp { background: radial-gradient(1200px 700px at 50% -10%, #EAF1FF 0%, #F4F6FA 55%) fixed; }
.aura { position: fixed; left: 50%; top: 46%; width: 880px; height: 880px; transform: translate(-50%, -50%); z-index: 0;
  pointer-events: none; border-radius: 50%; filter: blur(70px); opacity: .55;
  background: radial-gradient(circle at 40% 40%, rgba(59,118,232,.30), transparent 55%),
              radial-gradient(circle at 65% 60%, rgba(14,159,138,.18), transparent 50%),
              radial-gradient(circle at 50% 50%, rgba(120,170,255,.22), transparent 62%);
  animation: aura 14s ease-in-out infinite alternate; }
@keyframes aura { 0% { transform: translate(-50%, -50%) scale(1) rotate(0deg); opacity: .45; }
                  50% { opacity: .62; } 100% { transform: translate(-52%, -47%) scale(1.08) rotate(18deg); opacity: .5; } }
.as-wrap { position: relative; z-index: 1; }
.as-hello { text-align: center; margin: 9vh auto 1.4rem; }
.as-hello .orb { width: 64px; height: 64px; margin: 0 auto 1.1rem; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #fff 0 12%, #9cc2ff 30%, #2f6be0 62%, #0b2545 100%);
  box-shadow: 0 0 0 8px rgba(59,118,232,.08), 0 0 50px rgba(59,118,232,.45); animation: breathe 4s ease-in-out infinite; }
@keyframes breathe { 50% { transform: scale(1.06); box-shadow: 0 0 0 12px rgba(59,118,232,.06), 0 0 70px rgba(59,118,232,.55); } }
.as-hello h1 { font-size: 2.15rem; font-weight: 700; margin: 0 0 .45rem; color: #0F1E36; }
.as-hello p { color: #5B6B82; margin: 0; font-size: 1.02rem; }
.as-understood { color: #5B6B82; font-size: .86rem; margin: .1rem 0 .55rem; }
.as-kpi { background: rgba(255,255,255,.85); border: 1px solid #E3E8F0; border-radius: 18px; padding: 1.1rem 1.3rem; margin: .4rem 0 .6rem;
  box-shadow: 0 8px 30px rgba(30,91,216,.08); }
.as-kpi .v { font-size: 2.3rem; font-weight: 800; color: #0B2545; letter-spacing: -.02em; }
.as-kpi .l { color: #5B6B82; font-size: .9rem; }
[data-testid="stBottomBlockContainer"] { max-width: 880px; margin: 0 auto; background: transparent !important; }
[data-testid="stBottom"] > div { background: transparent !important; }
div[data-testid="stChatInput"] { border-radius: 22px !important; box-shadow: 0 10px 40px rgba(30,91,216,.16) !important;
  border: 1px solid #cfdcf5 !important; background: rgba(255,255,255,.92) !important; }
.st-key-assist_col div[data-testid="stChatMessage"] { background: rgba(255,255,255,.78); border: 1px solid #E6ECF6;
  border-radius: 18px; padding: .9rem 1rem; backdrop-filter: blur(6px); animation: rise .35s ease; }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.st-key-assist_sugg button { border-radius: 14px !important; background: rgba(255,255,255,.8) !important; border: 1px solid #E1E8F4 !important;
  text-align: left !important; justify-content: flex-start !important; min-height: 3.1rem; transition: all .2s ease; }
.st-key-assist_sugg button:hover { border-color: #3B76E8 !important; box-shadow: 0 6px 20px rgba(30,91,216,.14); transform: translateY(-1px); }
</style>
<div class="aura"></div>
"""

SUGGEST = [("Combien de transactions ont eu lieu à Béja ?", "How many transactions happened in Beja?"),
           ("Évolution mensuelle du montant des opérations en ligne", "Monthly trend of online payment amounts"),
           ("Top 10 des catégories de commerçants par nombre de fraudes", "Top 10 merchant categories by number of frauds"),
           ("Montant moyen par tranche d'âge des clients retraités", "Average amount by age band for retired customers"),
           ("Taux de refus par canal en septembre 2026", "Decline rate by channel in September 2026"),
           ("Quelles régions ont le plus d'alertes du modèle hier ?", "Which regions had the most model alerts yesterday?")]


def _chart(df, spec, title):
    if df is None or not len(df):
        return
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    if len(df) == 1 and len(num) >= 1 and len(df.columns) <= 3:
        cells = "".join(f'<div style="flex:1"><div class="v">{askdata._fmt(df[c].iloc[0])}</div><div class="l">{ui.esc(c.replace("_", " "))}</div></div>'
                        for c in num[:3])
        st.markdown(f'<div class="as-kpi" style="display:flex;gap:1.5rem">{cells}</div>', unsafe_allow_html=True)
        return
    if {"latitude", "longitude"} <= set(df.columns) and num:
        y = next((c for c in num if c not in ("latitude", "longitude")), None)
        fig = px.scatter_map(df.dropna(subset=["latitude", "longitude"]), lat="latitude", lon="longitude", size=y, color=y,
                             hover_name=df.columns[0], zoom=5.2, height=420, color_continuous_scale="Blues", map_style="carto-positron")
    else:
        y = spec.get("y") if spec.get("y") in num else (num[-1] if num else None)
        x = spec.get("x") if spec.get("x") in df.columns and spec.get("x") != y else next((c for c in df.columns if c != y), None)
        if not (x and y) or len(df) > 400:
            return
        d = df.copy()
        kind = spec.get("type", "bar")
        timeish = re.search(r"mois|date|jour|heure|annee|semaine|month|day|hour|year|week", x, re.I)
        if kind == "line" or (timeish and len(d) > 3):
            fig = px.line(d.sort_values(x), x=x, y=y, markers=True, height=360)
            fig.update_traces(line=dict(color=ui.BLUE, width=3), marker=dict(size=7))
            fig.update_traces(fill="tozeroy", fillcolor="rgba(30,91,216,.08)")
        elif kind == "pie" and len(d) <= 8:
            fig = px.pie(d, names=x, values=y, hole=.62, height=360, color_discrete_sequence=px.colors.sequential.Blues_r)
        else:
            d[x] = d[x].astype(str)
            horiz = len(d) > 7 or d[x].str.len().max() > 14
            d = d.sort_values(y, ascending=horiz)
            fig = px.bar(d, x=y if horiz else x, y=x if horiz else y, orientation="h" if horiz else "v",
                         height=max(320, 30 * len(d) + 80) if horiz else 360, text_auto=".3~s")
            fig.update_traces(marker_color=ui.BLUE, marker_line_width=0, opacity=.92, textposition="outside", cliponaxis=False)
    fig.update_layout(margin=dict(l=8, r=24, t=36 if title else 8, b=8), title=dict(text=title or "", font=dict(size=14, color="#0F1E36")),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#334155"),
                      xaxis=dict(gridcolor="#EEF2F8", title=None), yaxis=dict(gridcolor="#EEF2F8", title=None), showlegend=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _render(ctx, i, msg):
    L = ctx.L
    r = msg["result"]
    if r.get("kind") == "copilot":
        st.markdown(r["answer"])
        if st.button(L("Ouvrir la fiche transaction", "Open the transaction page"), key=f"as_open_{i}", icon=":material/open_in_new:"):
            ctx.open_tx(r["tid"])
            st.rerun()
        st.caption(r.get("meta", ""))
        return
    if r.get("intent") == "personal":
        st.markdown(L("Ici, les données des clients ne sont restituées qu'en **agrégats** (comptes, moyennes, groupes d'au moins 5 clients) : "
                      "minimisation des données personnelles (loi tunisienne 2004-63, RGPD). Pour un client précis, ouvrez la **Vue client 360** "
                      "(accès tracé). Exemple : *revenu moyen des clients retraités par gouvernorat*.",
                      "Here, customer data is only returned as **aggregates** (counts, averages, groups of at least 5 customers): personal data "
                      "minimisation (Tunisian law 2004-63, GDPR). For one customer, open **Customer 360** (logged access). Example: *average income "
                      "of retired customers by governorate*."))
        return
    if r.get("intent") == "unclear":
        st.markdown(_why_offline(L, r.get("ai_down")) + "\n\n" + L("En attendant, je comprends les questions du type **combien / montant total / montant moyen / fraudes / alertes**, "
                      "avec un lieu (*à Sfax*), une période (*en août 2026*, *hier*), un canal (*en ligne*, *DAB*) et un regroupement (*par mois*, "
                      "*par ville*, *par catégorie*). Reformulez, ou choisissez une suggestion.",
                      "Meanwhile I understand **how many / total amount / average amount / frauds / alerts**, with a place "
                      "(*in Sfax*), a period (*in August 2026*, *yesterday*), a channel (*online*, *ATM*) and a grouping (*by month*, *by city*, "
                      "*by category*). Rephrase, or pick a suggestion."))
        return
    if r.get("intent") == "out_of_scope":
        st.markdown(L("Je réponds aux questions sur les données de la banque : transactions, clients, lieux, commerçants, canaux, "
                      "fraudes et alertes. Essayez par exemple : *combien de retraits à Sfax en août ?*",
                      "I answer questions about the bank's data: transactions, customers, places, merchants, channels, frauds and alerts. "
                      "Try for example: *how many withdrawals in Sfax in August?*"))
        return
    if r.get("error"):
        st.warning(L("Je n'ai pas pu répondre à cette question avec les données : ", "I couldn't answer this from the data: ") + r["error"])
        if r.get("sql"):
            with st.expander(L("Requête tentée", "Attempted query")):
                st.code(r["sql"], language="sql")
        return
    if r.get("understood"):
        st.markdown(f'<div class="as-understood">🧭 {ui.esc(r["understood"])}</div>', unsafe_allow_html=True)
    st.markdown(r.get("summary", ""))
    _chart(r.get("df"), r.get("chart") or {}, r.get("title", ""))
    df = r.get("df")
    with st.expander(L(f"Tableau · {len(df)} ligne(s)", f"Table · {len(df)} row(s)"), icon=":material/table:"):
        st.dataframe(df, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(df)))
        st.download_button("CSV", df.to_csv(index=False).encode("utf-8"), "resultat.csv", "text/csv", key=f"as_csv_{i}")
    with st.expander(L("Requête SQL générée (vérifiée, lecture seule)", "Generated SQL (checked, read-only)"), icon=":material/code:"):
        st.code(r["sql"], language="sql")
    t = r.get("tokens") or {}
    st.caption(f"{r.get('engine', '')} · {r.get('mode', '')} · {t.get('total', 0)} tokens · {r.get('latency_s', 0)} s"
               + (" · cache" if r.get("cached") else ""))
    fu = r.get("followups") or []
    if fu:
        cols = st.columns(len(fu))
        for j, f in enumerate(fu):
            if cols[j].button(f, key=f"as_fu_{i}_{j}", width="stretch"):
                st.session_state.assist_pending = f
                st.rerun()


def _answer(ctx, question, history):
    L, lang = ctx.L, ctx.lang
    tid = askdata.TX_ID.search(question)
    if tid and ctx.queue is not None and tid.group(0).upper() in set(ctx.queue.transaction_id):
        tid = tid.group(0).upper()
        out = copilot.ask(question, context_tx=tid, lang=lang)
        return {"kind": "copilot", "tid": tid, "answer": out["answer"],
                "meta": f"{L('Copilote fraude', 'Fraud copilot')} · {out['mode']} · {out['tokens']['total']} tokens"}
    r = askdata.ask(question, lang, history, analyst=st.session_state.get("analyst"))
    if r.get("intent") == "alert":
        t = askdata.TX_ID.search(question)
        tid = t.group(0).upper() if t else st.session_state.get("tx")
        out = copilot.ask(question, context_tx=tid, lang=lang)
        return {"kind": "copilot", "tid": tid, "answer": out["answer"],
                "meta": f"{L('Copilote fraude', 'Fraud copilot')} · {out['mode']} · {out['tokens']['total']} tokens"}
    return r


def _why_offline(L, reason):
    if reason == "no_key":
        return L("⚠️ **L'IA n'est pas connectée sur ce serveur** (clé Azure OpenAI absente des paramètres). L'administrateur l'ajoute dans "
                 "les *Secrets* de l'application.", "⚠️ **The AI is not connected on this server** (no Azure OpenAI key in the settings). "
                 "The administrator adds it in the app's *Secrets*.")
    if reason == "cap":
        return L("⏳ **Limite horaire d'appels IA atteinte** (protection des coûts de la démo publique) : réponses par règles pendant "
                 "quelques minutes.", "⏳ **Hourly AI call limit reached** (public demo cost guard): rule-based answers for a few minutes.")
    if reason and str(reason).startswith("error"):
        return L("⚠️ **Azure OpenAI ne répond pas** pour l'instant (" + str(reason)[6:] + ") : réponse par règles.",
                 "⚠️ **Azure OpenAI is not answering** right now (" + str(reason)[6:] + "): rule-based answer.")
    return L("Mode hors-ligne.", "Offline mode.")


def page_assistant(ctx):
    L, lang = ctx.L, ctx.lang
    st.markdown(CSS, unsafe_allow_html=True)
    chat = st.session_state.setdefault("assist", [])
    pending = st.session_state.pop("assist_pending", None)
    typed = st.chat_input(L("Posez votre question…", "Ask your question…"))      # root level → pinned to the bottom
    _, mid, _ = st.columns([1, 3.2, 1])
    with mid, st.container(key="assist_col"):
        status = copilot.ai_status()
        if status in ("no_key", "cap"):
            st.markdown(f'<div style="text-align:center;margin-top:1rem;font-size:.85rem;color:#C77700">{_why_offline(L, status).replace('**', '').replace('*', '')}</div>',
                        unsafe_allow_html=True)
        if not chat and not pending and not typed:
            st.markdown(f'<div class="as-hello"><div class="orb"></div><h1>{L("Que voulez-vous savoir ?", "What do you want to know?")}</h1>'
                        f'<p>{L("Posez une question sur les transactions, les clients, les lieux ou les alertes — en français, en anglais ou en derja.", "Ask about transactions, customers, places or alerts — in French, English or Arabic.")}</p></div>',
                        unsafe_allow_html=True)
            with st.container(key="assist_sugg"):
                cols = st.columns(2)
                for k, (fr, en) in enumerate(SUGGEST):
                    if cols[k % 2].button(L(fr, en), key=f"as_s_{k}", width="stretch"):
                        pending = L(fr, en)
        for i, m in enumerate(chat):
            with st.chat_message("user", avatar=":material/person:"):
                st.markdown(m["question"])
            with st.chat_message("assistant", avatar=":material/auto_awesome:"):
                _render(ctx, i, m)
        q = typed or pending
        if q:
            with st.chat_message("user", avatar=":material/person:"):
                st.markdown(q)
            with st.chat_message("assistant", avatar=":material/auto_awesome:"):
                with st.spinner(L("Je comprends la question, j'interroge les données…", "Understanding the question, querying the data…")):
                    res = _answer(ctx, q, [{"question": m["question"]} for m in chat])
                chat.append({"question": q, "result": res})
                _render(ctx, len(chat) - 1, chat[-1])
        if chat and st.button(L("Nouvelle conversation", "New conversation"), icon=":material/refresh:", key="as_reset"):
            st.session_state.assist = []
            st.rerun()
