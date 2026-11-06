"""Report Generation Agent + Visualization Generator.

compose(analysis, settings) -> document model {meta, sections[{id, title, blocks[]}], charts, facts, tables, insights, checks}
Blocks: p (text + kind + refs), bullets, kpis (fact ids), table (T#), chart (C#), evidence (E# list), callout.
Narrative is deterministic from verified facts; with Azure OpenAI an AI writer may rewrite the summary / conclusion paragraphs,
kept only if every number it writes exists in the evidence (grounding check) — marked "AI interpretation".
"""
import io
import json
import re

import pandas as pd

import report_i18n as I

AUD_SECTIONS = {"executive": {"max_rows": 5, "detail_tables": False}, "analyst": {"max_rows": 12, "detail_tables": True},
                "cyber": {"max_rows": 10, "detail_tables": True}, "operations": {"max_rows": 10, "detail_tables": True}}
KPI_ORDER = {"executive": ["ops", "amount", "frauds", "fraud_amount", "fraud_approved_amount", "fraud_rate", "model_precision", "suspected"],
             "analyst": ["ops", "frauds", "fraud_rate", "model_alerts", "model_precision", "model_recall", "rules_precision", "suspected", "decline_rate"],
             "cyber": ["logins", "failed_logins", "failed_rate", "sensitive_events", "fraud_after_sensitive", "fraud_after_failed", "no3ds_rate",
                       "magstripe_rate", "frauds"],
             "operations": ["ops", "declines", "decline_rate", "model_alerts", "alerts_per_day", "decisions", "override_rate", "decision_time",
                            "dq_warnings", "fraud_approved_amount"]}


def _p(text, kind="fact", refs=None):
    return {"t": "p", "text": text, "kind": kind, "refs": refs or []}


def _term(text, settings):
    for k, v in (settings.get("terminology") or {}).items():
        if k:
            text = re.sub(rf"\b{re.escape(k)}\b", v, text)
    return text


# ---------------------------------------------------------------- charts
def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#AEBBD0", "axes.titleweight": "bold", "axes.titlesize": 10.5})
    return plt


def _ar(s, lang):
    if lang != "ar":
        return s
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return buf.getvalue()


def charts(a, color):
    lg = a.lang
    out = []
    per = I.period_text(a.spec["period"], lg)
    src = I.tr(lg, "Source", "Source", "المصدر") + " : " + a.src.provenance

    def add(key, title, fig, caption, refs):
        out.append({"id": f"C{len(out) + 1}", "key": key, "title": title, "png": _png(fig), "caption": caption, "period": per, "source": src,
                    "refs": refs})
    plt = _mpl()
    tr = next((t for t in a.tables if t["key"] == "trend"), None)
    if tr is not None and len(tr["df"]) >= 3:
        df = tr["df"]
        fig, ax = plt.subplots(figsize=(7.4, 2.8))
        has_fr = df["frauds"].notna().any() and df["frauds"].fillna(0).sum() > 0
        y = df["frauds"].fillna(0) if has_fr else df["model_alerts"]
        lab = I.tr(lg, "Fraudes confirmées", "Confirmed frauds", "احتيال مؤكد") if has_fr else I.tr(lg, "Alertes du modèle (suspicions)",
                                                                                                    "Model alerts (suspected)", "تنبيهات النموذج")
        ax.plot(pd.to_datetime(df["t"]), y, color=color, lw=2, marker="o", ms=3, label=_ar(lab, lg))
        if has_fr and df["model_alerts"].sum() > 0:
            ax.plot(pd.to_datetime(df["t"]), df["model_alerts"], color="#C77700", lw=1.4, ls="--", label=_ar(I.tr(lg, "Alertes du modèle",
                                                                                                                   "Model alerts", "تنبيهات النموذج"), lg))
        unit = {"day": I.tr(lg, "par jour", "per day", "يومياً"), "week": I.tr(lg, "par semaine", "per week", "أسبوعياً"),
                "month": I.tr(lg, "par mois", "per month", "شهرياً")}[tr["unit"]]
        ttl = f"{lab} {unit}"
        ax.set_title(_ar(ttl, lg), loc="left")
        ax.set_ylabel(_ar(I.tr(lg, "nombre", "count", "العدد"), lg))
        ax.legend(frameon=False, fontsize=8)
        ax.grid(axis="y", color="#EEF2F8")
        fig.autofmt_xdate()
        mx = df.loc[y.idxmax(), "t"]
        cap = I.tr(lg, f"Pic le {str(mx)[:10]} ({I.fmt(y.max(), 'count', lg)}).", f"Peak on {str(mx)[:10]} ({I.fmt(y.max(), 'count', lg)}).",
                   f"الذروة في {str(mx)[:10]} ({I.fmt(y.max(), 'count', lg)}).")
        add("trend", ttl, fig, cap, [tr["id"]])
    for t in a.tables:
        if t["key"] not in ("channel", "card_type", "merchant_category", "country", "region", "entry_mode") or len(t["df"]) < 2:
            continue
        df = t["df"].head(8)
        if df["frauds"].fillna(0).sum() == 0:
            continue
        fig, ax = plt.subplots(figsize=(7.4, 0.42 * len(df) + 1.1))
        idx = range(len(df))[::-1]
        ax.barh([i + 0.2 for i in idx], df["share_ops"] * 100, height=0.38, color="#C9D9FA", label=_ar(I.tr(lg, "% des opérations",
                                                                                                             "% of transactions", "% من العمليات"), lg))
        ax.barh([i - 0.2 for i in idx], df["share_frauds"] * 100, height=0.38, color=color, label=_ar(I.tr(lg, "% des fraudes confirmées",
                                                                                                            "% of confirmed frauds", "% من الاحتيال"), lg))
        ax.set_yticks(list(idx))
        ax.set_yticklabels([_ar(str(g)[:28], lg) for g in df["grp"]])
        ax.set_xlabel("%")
        ttl = I.tr(lg, "Part des fraudes vs part des opérations ", "Share of frauds vs share of transactions ", "حصة الاحتيال مقابل حصة العمليات ") + \
            t["title"][lg].split(" ", 3)[-1] if lg != "ar" else t["title"]["ar"]
        ax.set_title(_ar(ttl, lg), loc="left")
        ax.legend(frameon=False, fontsize=8, loc="lower right")
        top = df.sort_values("lift", ascending=False).iloc[0]
        cap = I.tr(lg, f"Barre foncée plus longue que la claire = segment sur-représenté dans la fraude (ici « {top.grp} », {I.fmt(top.lift, 'ratio', lg)}).",
                   f"Dark bar longer than light = segment over-represented in fraud (here \"{top.grp}\", {I.fmt(top.lift, 'ratio', lg)}).",
                   f"الشريط الداكن أطول = شريحة ممثلة بشكل مفرط في الاحتيال («{top.grp}»، {I.fmt(top.lift, 'ratio', lg)}).")
        add(t["key"], ttl, fig, cap, [t["id"]])
        if "prev_frauds" in df and df["prev_frauds"].notna().any() and t["key"] in ("channel", "card_type"):
            fig, ax = plt.subplots(figsize=(7.4, 2.6))
            x = range(len(df))
            ax.bar([i - 0.2 for i in x], df["prev_frauds"].fillna(0), width=0.4, color="#AEBBD0", label=_ar(I.tr(lg, "Période précédente",
                                                                                                              "Previous period", "الفترة السابقة"), lg))
            ax.bar([i + 0.2 for i in x], df["frauds"].fillna(0), width=0.4, color=color, label=_ar(I.tr(lg, "Période analysée", "Period analysed",
                                                                                                   "الفترة المحللة"), lg))
            ax.set_xticks(list(x))
            ax.set_xticklabels([_ar(str(g)[:16], lg) for g in df["grp"]], rotation=20, ha="right")
            ax.set_ylabel(_ar(I.tr(lg, "fraudes confirmées", "confirmed frauds", "احتيال مؤكد"), lg))
            ttl = I.tr(lg, "Fraudes confirmées : période analysée vs précédente ", "Confirmed frauds: period vs previous ",
                       "الاحتيال المؤكد: الفترة الحالية مقابل السابقة ") + (t["title"][lg].split(" ", 3)[-1] if lg != "ar" else "")
            ax.set_title(_ar(ttl, lg), loc="left")
            ax.legend(frameon=False, fontsize=8)
            add(t["key"] + "_cmp", ttl, fig, I.tr(lg, "Comparaison à périmètre identique.", "Like-for-like comparison.", "مقارنة على نفس النطاق."),
                [t["id"]])
    au = next((t for t in a.tables if t["key"] == "auth_daily"), None)
    if au is not None and len(au["df"]) > 3:
        df = au["df"]
        fig, ax = plt.subplots(figsize=(7.4, 2.5))
        ax.plot(pd.to_datetime(df["day"]), df["failed"], color="#D92D20", lw=1.6)
        sp = df[df["spike"]]
        ax.scatter(pd.to_datetime(sp["day"]), sp["failed"], color="#D92D20", s=30, zorder=3)
        ttl = I.tr(lg, "Connexions échouées par jour", "Failed logins per day", "محاولات الدخول الفاشلة يومياً")
        ax.set_title(_ar(ttl, lg), loc="left")
        ax.set_ylabel(_ar(I.tr(lg, "nombre", "count", "العدد"), lg))
        fig.autofmt_xdate()
        add("auth", ttl, fig, I.tr(lg, "Points : jours au-dessus de la moyenne + 3 écarts-types.", "Dots: days above mean + 3 standard deviations.",
                                   "النقاط: أيام فوق المتوسط + 3 انحرافات."), [au["id"]])
    return out


# ---------------------------------------------------------------- sections
def _sec(sid, lang, blocks, settings):
    title = settings.get("section_titles", {}).get(sid) or I.label(I.SECTIONS[sid], lang)
    return {"id": sid, "title": title, "blocks": blocks, "edited": None}


def compose(a, settings=None, charts_on=True):
    settings = settings or {}
    s, lg = a.spec, a.lang
    aud = AUD_SECTIONS.get(s["audience"], AUD_SECTIONS["analyst"])
    color = settings.get("color") or "#1E5BD8"
    a.charts = charts(a, color) if charts_on and s["type"] != "investigation" else []
    F = lambda k, prev=False: (I.fmt(a.get(k, prev)["value"], a.get(k, prev)["unit"], lg) if a.get(k, prev) else None)  # noqa: E731
    fid = lambda k, prev=False: [a.get(k, prev)["id"]] if a.get(k, prev) else []  # noqa: E731
    per = I.period_text(s["period"], lg)
    secs = {}
    top = sorted(a.insights, key=lambda i: {"high": 0, "medium": 1, "low": 2}[i["priority"]])
    # summary
    if s["type"] == "investigation":
        secs["summary"] = _investigation_summary(a, lg)
    else:
        b = [_p(I.tr(lg, f"Période analysée : {per}.", f"Period analysed: {per}.", f"الفترة المحللة: {per}."), "fact")]
        line = []
        if F("ops"):
            line.append(I.tr(lg, f"{F('ops')} opérations pour {F('amount')}", f"{F('ops')} transactions worth {F('amount')}", f"{F('ops')} عملية بقيمة {F('amount')}"))
        if F("frauds") is not None:
            line.append(I.tr(lg, f"{F('frauds')} fraudes confirmées ({F('fraud_amount')}, taux {F('fraud_rate')})",
                             f"{F('frauds')} confirmed frauds ({F('fraud_amount')}, rate {F('fraud_rate')})",
                             f"{F('frauds')} حالة احتيال مؤكدة ({F('fraud_amount')}، بمعدل {F('fraud_rate')})"))
        if F("suspected"):
            line.append(I.tr(lg, f"{F('suspected')} alertes encore non confirmées", f"{F('suspected')} alerts not yet confirmed", f"{F('suspected')} تنبيه غير مؤكد"))
        if line:
            b.append(_p("; ".join(line) + ".", "fact", fid("ops") + fid("frauds") + fid("suspected")))
        if top:
            b.append({"t": "bullets", "title": I.tr(lg, "Principaux constats", "Main findings", "أهم النتائج"),
                      "items": [{"text": f"{i['title'][lg]} — {i['what'][lg]}", "kind": i["kind"], "refs": [i["id"]] + i["refs"], "priority": i["priority"]}
                                for i in top[:4 if s["depth"] != "summary" else 3]]})
        imm = a.recs.get("immediate", [])[:3]
        if imm:
            b.append({"t": "bullets", "title": I.tr(lg, "Actions prioritaires", "Priority actions", "إجراءات ذات أولوية"),
                      "items": [{"text": r["text"], "kind": "recommendation", "refs": r["refs"]} for r in imm]})
        for lim in a.limits[:2]:
            b.append(_p(lim[lg], "limit"))
        secs["summary"] = b
    # scope & methodology
    if "scope" in s["sections"]:
        sc = s.get("scope") or {}
        scope_txt = ", ".join([I.channel_label(c, lg) for c in sc.get("channels", [])] + sc.get("card_types", []) + sc.get("cities", []) +
                              sc.get("countries", [])) or I.tr(lg, "toutes les opérations", "all transactions", "جميع العمليات")
        b = [_p(I.tr(lg, f"Objet : {s['purpose']}", f"Purpose: {s['purpose']}", f"الهدف: {s['purpose']}"), "fact"),
             _p(I.tr(lg, f"Périmètre : {scope_txt} ; période {per}", f"Scope: {scope_txt}; period {per}", f"النطاق: {scope_txt}؛ الفترة {per}")
                + (I.tr(lg, f" ; comparée à {I.period_text(s['previous'], lg)}.", f"; compared with {I.period_text(s['previous'], lg)}.",
                        f"؛ مقارنة بـ {I.period_text(s['previous'], lg)}.") if s.get("compare") else "."), "fact"),
             _p(I.tr(lg, f"Données : {a.src.provenance}.", f"Data: {a.src.provenance}.", f"البيانات: {a.src.provenance}."), "fact"),
             _p(I.tr(lg, "Méthode : chaque chiffre est calculé par une requête SQL fixe sur les vues canoniques (registre en annexe) ; les fraudes "
                         "confirmées viennent des signalements de la banque, les suspicions des alertes du modèle non encore confirmées ; l'IA ne calcule "
                         "aucun chiffre, elle aide seulement à rédiger.",
                     "Method: every figure comes from a fixed SQL query on the canonical views (register in appendix); confirmed frauds come from the "
                     "bank's reports, suspected cases from model alerts not yet confirmed; AI computes no figure, it only helps to write.",
                     "المنهجية: كل رقم مستخرج من استعلام SQL ثابت؛ الاحتيال المؤكد من بلاغات البنك والاشتباه من تنبيهات النموذج؛ الذكاء الاصطناعي لا يحسب أي رقم."),
                "fact")]
        for lim in a.limits:
            b.append(_p(lim[lg], "limit"))
        secs["scope"] = b
    # KPIs
    if "kpis" in s["sections"]:
        keys = [k for k in KPI_ORDER.get(s["audience"], KPI_ORDER["analyst"]) if a.get(k)]
        keys += [k for k in ("frauds", "fraud_rate", "model_precision") if a.get(k) and k not in keys][:2]
        b = [{"t": "kpis", "refs": [a.get(k)["id"] for k in keys], "prev": {a.get(k)["id"]: a.get(k, True)["id"] for k in keys if a.get(k, True)}}]
        b += [{"t": "chart", "ref": c["id"]} for c in a.charts if c["key"] == "trend"]
        secs["kpis"] = b
    # findings
    if "findings" in s["sections"]:
        if s["type"] == "investigation":
            secs["findings"] = _investigation_findings(a, lg)
        else:
            b = []
            for i in top:
                if i["area"] in ("cyber",) and s["type"] != "cyber" and "cyber" in s["sections"]:
                    continue
                b.append({"t": "finding", "ref": i["id"]})
            if not b:
                b.append(_p(I.tr(lg, "Aucun écart significatif selon les seuils documentés (≥ 5 fraudes, ×1,5 la part des opérations).",
                                 "No significant deviation under the documented thresholds (≥ 5 frauds, ×1.5 the share of transactions).",
                                 "لا يوجد انحراف مهم وفق العتبات الموثقة."), "fact"))
            for t in a.tables:
                if t["key"] in ("channel", "card_type", "merchant_category", "country", "region", "hour_band", "entry_mode", "segment") and \
                        (aud["detail_tables"] or s["depth"] == "detailed" or t["key"] in ("channel", "card_type")):
                    if s["depth"] == "summary" and t["key"] not in ("channel",):
                        continue
                    b.append({"t": "table", "ref": t["id"], "max_rows": aud["max_rows"]})
                    b += [{"t": "chart", "ref": c["id"]} for c in a.charts if c["refs"] == [t["id"]]]
            secs["findings"] = b
    if "cyber" in s["sections"]:
        b = [_p(I.tr(lg, "Ces éléments sont des indicateurs à faire vérifier par l'équipe sécurité : une opération inhabituelle ne prouve ni une attaque ni "
                         "une vulnérabilité.", "These are indicators for the security team to verify: an unusual transaction proves neither an attack nor "
                         "a vulnerability.", "هذه مؤشرات يجب أن يتحقق منها فريق الأمن: العملية غير المعتادة لا تثبت هجوماً ولا ثغرة."), "limit")]
        keys = [k for k in KPI_ORDER["cyber"] if a.get(k)]
        if keys:
            b.append({"t": "kpis", "refs": [a.get(k)["id"] for k in keys], "prev": {}})
        b += [{"t": "finding", "ref": i["id"]} for i in top if i["area"] == "cyber"]
        for key in ("auth_daily", "atm_cities"):
            t = next((x for x in a.tables if x["key"] == key), None)
            if t is not None and key == "atm_cities":
                b.append({"t": "table", "ref": t["id"], "max_rows": 10})
        b += [{"t": "chart", "ref": c["id"]} for c in a.charts if c["key"] == "auth"]
        secs["cyber"] = b
    if "processing" in s["sections"]:
        keys = [k for k in KPI_ORDER["operations"] if a.get(k)]
        b = [{"t": "kpis", "refs": [a.get(k)["id"] for k in keys], "prev": {}}]
        t = next((x for x in a.tables if x["key"] == "decline_reasons"), None)
        if t is not None:
            b.append({"t": "table", "ref": t["id"], "max_rows": 10})
        b += [{"t": "finding", "ref": i["id"]} for i in top if i["area"] in ("operations", "exposure", "model")]
        secs["processing"] = b
    if "timeline" in s["sections"] and s["type"] == "investigation":
        secs["timeline"] = _investigation_timeline(a, lg)
    if "case" in s["sections"] and s["type"] == "investigation":
        tx = a.extra.get("transaction") or {}
        names = {"transaction_id": ("Référence", "Reference", "المرجع"), "timestamp": ("Date et heure", "Date and time", "التاريخ والوقت"),
                 "transaction_type": ("Type", "Type", "النوع"), "channel": ("Canal", "Channel", "القناة"), "entry_mode": ("Mode de saisie", "Entry mode", "طريقة الإدخال"),
                 "merchant_category": ("Catégorie de commerçant", "Merchant category", "فئة التاجر"), "amount_tnd": ("Montant (TND)", "Amount (TND)", "المبلغ"),
                 "city": ("Ville", "City", "المدينة"), "country": ("Pays", "Country", "البلد"), "status": ("Statut", "Status", "الحالة")}
        items = [{"text": f"{I.tr(lg, *names[k])} : {I.channel_label(tx[k], lg) if k == 'channel' else tx[k]}", "kind": "fact", "refs": []}
                 for k in names if tx.get(k) not in (None, "")]
        secs["case"] = ([{"t": "bullets", "title": None, "items": items}] if items else []) + \
            [_p(I.tr(lg, "Identité du client non reproduite dans ce rapport (minimisation) : consultable dans le système de la banque par les personnes habilitées.",
                     "Customer identity not reproduced in this report (minimisation): available in the bank's system to authorised staff.",
                     "لا تُذكر هوية العميل في هذا التقرير (تقليل البيانات)."), "limit")]
    if "ai" in s["sections"]:
        secs["ai"] = _ai_section(a, lg)
    # risk
    if "risk" in s["sections"]:
        rows = [{"t": "risk", "ref": i["id"]} for i in top if i["kind"] != "ml" or i["priority"] == "high"]
        secs["risk"] = rows or [_p(I.tr(lg, "Aucun risque prioritaire identifié par les règles d'analyse.", "No priority risk identified by the analysis rules.",
                                        "لم يتم تحديد مخاطر ذات أولوية."), "fact")]
        if s["type"] == "investigation":
            secs["risk"] = _investigation_risk(a, lg)
    if "recommendations" in s["sections"]:
        b = []
        for h, (fr, en, ar) in (("immediate", ("Immédiat", "Immediate", "فوري")), ("short", ("Court terme", "Short term", "قصير المدى")),
                                ("long", ("Long terme", "Long term", "طويل المدى"))):
            items = a.recs.get(h, [])
            if items:
                b.append({"t": "bullets", "title": I.tr(lg, fr, en, ar), "items": [{"text": r["text"], "kind": "recommendation", "refs": r["refs"]}
                                                                                    for r in items]})
        if s["type"] == "investigation":
            b = _investigation_recs(a, lg)
        b.append(_p(I.tr(lg, "Ces recommandations sont des propositions d'analyse ; elles ne constituent pas une décision officielle de la banque.",
                         "These recommendations are analytical proposals; they are not an official decision of the bank.",
                         "هذه التوصيات مقترحات تحليلية وليست قراراً رسمياً للبنك."), "limit"))
        secs["recommendations"] = b
    if "conclusion" in s["sections"]:
        n_high = sum(i["priority"] == "high" for i in a.insights)
        if s["type"] == "investigation":
            txt = _investigation_conclusion(a, lg)
        else:
            txt = I.tr(lg, f"{n_high} point(s) de priorité haute sur {len(a.insights)} constat(s) ; {len(a.limits)} limite(s) de données signalée(s). "
                           "Les chiffres sont reproductibles à partir du registre des preuves.",
                       f"{n_high} high-priority point(s) out of {len(a.insights)} finding(s); {len(a.limits)} data limitation(s) stated. "
                       "Figures are reproducible from the evidence register.",
                       f"{n_high} نقطة ذات أولوية عالية من أصل {len(a.insights)} نتيجة؛ {len(a.limits)} حدود بيانات. الأرقام قابلة لإعادة الإنتاج من سجل الأدلة.")
        secs["conclusion"] = [_p(txt, "fact")]
    if "appendix" in s["sections"]:
        secs["appendix"] = [{"t": "register"}, {"t": "checks"}]
    order = [x for x in s["sections"] if x in secs]
    doc = {"meta": _meta(a, settings), "sections": [_sec(x, lg, secs[x], settings) for x in order]}
    for sec in doc["sections"]:
        for blk in sec["blocks"]:
            if blk.get("text"):
                blk["text"] = _term(blk["text"], settings)
    return doc


def _meta(a, settings):
    s, lg = a.spec, a.lang
    return {"title": settings.get("title_override") or I.label(I.TYPES[s["type"]], lg) + (f" — {s['case_id']}" if s.get("case_id") else ""),
            "institution": settings.get("institution") or a.src.institution, "period": I.period_text(s["period"], lg) if s["type"] != "investigation"
            else (a.extra.get("transaction", {}).get("timestamp") or ""), "generated": a.generated,
            "classification": settings.get("confidentiality_labels", {}).get(s["confidentiality"]) or I.label(I.CONFIDENTIALITY[s["confidentiality"]], lg),
            "audience": (settings.get("departments") or {}).get(s["audience"]) or I.label(I.AUDIENCES[s["audience"]], lg),
            "depth": I.label(I.DEPTHS[s["depth"]], lg), "lang": lg, "color": settings.get("color") or "#1E5BD8", "logo": settings.get("logo"),
            "footer": settings.get("footer") or "", "source": a.src.provenance, "request": s.get("request", "")}


# ---------------------------------------------------------------- investigation report parts
def _investigation_summary(a, lg):
    tx, sysd = a.extra.get("transaction"), a.extra.get("system") or {}
    if not tx:
        return [_p(a.limits[0][lg] if a.limits else "—", "limit")]
    F = lambda k: I.fmt(a.get(k)["value"], a.get(k)["unit"], lg) if a.get(k) else "—"  # noqa: E731
    b = [_p(I.tr(lg, f"Opération {a.spec['case_id']} du {str(tx.get('timestamp'))[:16]} : {tx.get('transaction_type') or ''} "
                     f"{I.channel_label(tx.get('channel'), lg)}, {F('case_amount')}, {tx.get('city') or ''} ({tx.get('country') or ''}), statut {tx.get('status')}.",
                 f"Transaction {a.spec['case_id']} on {str(tx.get('timestamp'))[:16]}: {tx.get('transaction_type') or ''} {I.channel_label(tx.get('channel'), lg)}, "
                 f"{F('case_amount')}, {tx.get('city') or ''} ({tx.get('country') or ''}), status {tx.get('status')}.",
                 f"العملية {a.spec['case_id']} بتاريخ {str(tx.get('timestamp'))[:16]}: {I.channel_label(tx.get('channel'), lg)}، {F('case_amount')}، "
                 f"{tx.get('city') or ''} ({tx.get('country') or ''})، الحالة {tx.get('status')}."), "fact", [a.get("case_amount")["id"]] if a.get("case_amount") else [])]
    if a.get("case_score"):
        b.append(_p(I.tr(lg, f"Score du modèle {F('case_score')}" + (f" ; {F('case_measured')} de fraudes mesurées à ce score en validation" if a.get("case_measured") else "")
                         + (f" ; recommandation du système : {sysd.get('decision')} (confiance {sysd.get('confiance')})." if sysd.get("decision") else "."),
                         f"Model score {F('case_score')}" + (f"; {F('case_measured')} frauds measured at this score in validation" if a.get("case_measured") else "")
                         + (f"; system recommendation: {sysd.get('decision')} (confidence {sysd.get('confiance')})." if sysd.get("decision") else "."),
                         f"درجة النموذج {F('case_score')}" + (f"؛ توصية النظام: {sysd.get('decision')}." if sysd.get("decision") else ".")),
                    "ml", [x["id"] for x in a.facts if x["key"] in ("case_score", "case_measured")]))
    d = a.extra.get("decision")
    if d:
        b.append(_p(I.tr(lg, f"Décision de l'employé : {d.get('decision')} le {str(d.get('decided_at'))[:16]} ({d.get('analyst') or '—'}).",
                         f"Employee decision: {d.get('decision')} on {str(d.get('decided_at'))[:16]} ({d.get('analyst') or '—'}).",
                         f"قرار الموظف: {d.get('decision')} بتاريخ {str(d.get('decided_at'))[:16]}."), "employee"))
    else:
        b.append(_p(I.tr(lg, "Aucune décision d'employé enregistrée : ce rapport n'est pas une décision.", "No employee decision recorded: this report is not a decision.",
                         "لا يوجد قرار موظف مسجل: هذا التقرير ليس قراراً."), "limit"))
    return b


def _investigation_findings(a, lg):
    b = [_p(I.tr(lg, "Tableau de preuves (texte tel qu'enregistré par la plateforme) :", "Evidence board (text as recorded by the platform):",
                 "لوحة الأدلة (النص كما سجلته المنصة):"), "fact"), {"t": "evidence"}]
    sim = a.extra.get("similar")
    if sim is not None and hasattr(sim, "columns") and len(sim):
        cols = [c for c in ("transaction_id", "similarity", "status_at", "scenario_known", "amount_tnd", "channel") if c in sim.columns]
        df = sim[cols].copy()
        t = a.table("similar", {"fr": "Cas passés les plus proches (statut connu à l'époque)", "en": "Closest past cases (status as known then)",
                                "ar": "أقرب الحالات السابقة"}, df, "memory.similar(k=8)", a.spec["period"], cols)
        b.append({"t": "table", "ref": t["id"], "max_rows": 8})
    h = a.extra.get("history")
    if h is not None and len(h):
        cols = [c for c in ("transaction_id", "timestamp", "amount_tnd", "channel", "country", "status") if c in h.columns]
        t = a.table("history", {"fr": "Opérations précédentes du client", "en": "Customer's previous transactions", "ar": "عمليات العميل السابقة"},
                    h[cols], "tenant canonical transactions (same pseudonymised customer, before the operation)", a.spec["period"], cols)
        b.append({"t": "table", "ref": t["id"], "max_rows": 10})
    for m in a.extra.get("memory") or []:
        b.append(_p(f"[{m['id']}] {m['text'][:300]}", "fact"))
    return b


def _investigation_timeline(a, lg):
    items = []
    tx = a.extra.get("transaction") or {}
    for e in a.extra.get("board") or []:
        if e.get("ts"):
            items.append((str(e["ts"])[:16], e["text"], e["id"]))
    for t in a.extra.get("triggers") or []:
        items.append((str(t.get("ts"))[:16], t.get("text"), "surveillance"))
    items.sort(key=lambda x: x[0])
    if not items:
        return [_p(I.tr(lg, "Pas d'événement daté autour de l'opération.", "No dated event around the transaction.", "لا توجد أحداث مؤرخة."), "fact")]
    return [{"t": "bullets", "title": None, "items": [{"text": f"{ts} — {txt}", "kind": "fact", "refs": [r]} for ts, txt, r in items[:25]]},
            _p(I.tr(lg, f"Opération alertée : {str(tx.get('timestamp'))[:16]}.", f"Alerted transaction: {str(tx.get('timestamp'))[:16]}.",
                    f"العملية المنبهة: {str(tx.get('timestamp'))[:16]}."), "fact")]


def _ai_section(a, lg):
    ag = a.extra.get("agents")
    if not ag or not ag.get("judge"):
        return [_p(I.tr(lg, "Le débat des agents IA (accusation, défense, juge) n'a pas été exécuté pour ce rapport. Il peut être lancé depuis la page « Dossier "
                            "d'enquête » ou en cochant l'option à la génération (≈ 18 000 jetons).",
                        "The AI agents' debate (prosecution, defence, judge) was not run for this report. Run it from the \"Investigation case\" page or "
                        "tick the option when generating (≈ 18,000 tokens).", "لم يتم تشغيل نقاش وكلاء الذكاء الاصطناعي لهذا التقرير."), "limit")]
    j = ag["judge"] if isinstance(ag["judge"], dict) else {}
    b = [_p(I.tr(lg, "Arguments produits par des agents IA à partir du tableau de preuves ; ils ne constituent pas une décision.",
                 "Arguments produced by AI agents from the evidence board; they are not a decision.", "حجج من وكلاء الذكاء الاصطناعي وليست قراراً."), "limit")]
    for role, (fr, en, ar) in (("prosecution", ("Accusation", "Prosecution", "الادعاء")), ("defense", ("Défense", "Defence", "الدفاع"))):
        if ag.get(role):
            b.append(_p(f"{I.tr(lg, fr, en, ar)} : {str(ag[role])[:1800]}", "ai"))
    if j:
        b.append(_p(I.tr(lg, "Juge", "Judge", "القاضي") + f" ({ag.get('judge_model') or '—'}) : {j.get('synthese', '')} — "
                    + I.tr(lg, "recommandation", "recommendation", "التوصية") + f" {j.get('recommandation', '—')}", "ai"))
        for c in (j.get("contradictions") or [])[:5]:
            b.append(_p(I.tr(lg, "Contradiction : ", "Contradiction: ", "تناقض: ") + str(c), "ai"))
        for m in (j.get("informations_manquantes") or j.get("verifications") or [])[:5]:
            b.append(_p(I.tr(lg, "À vérifier : ", "To verify: ", "للتحقق: ") + str(m), "hypothesis"))
    return b


def _investigation_risk(a, lg):
    sysd = a.extra.get("system") or {}
    b = []
    if sysd.get("signaux_concordants"):
        b.append({"t": "bullets", "title": I.tr(lg, "Signaux concordants (modèle + règles)", "Concordant signals (model + rules)", "إشارات متوافقة"),
                  "items": [{"text": str(x), "kind": "ml", "refs": []} for x in sysd["signaux_concordants"]]})
    if a.get("case_similar_rate"):
        f = a.get("case_similar_rate")
        b.append(_p(I.tr(lg, f"{I.fmt(f['value'], 'pct', lg)} des cas passés similaires au statut connu étaient des fraudes confirmées (contexte, pas une preuve).",
                         f"{I.fmt(f['value'], 'pct', lg)} of similar past cases with a known status were confirmed frauds (context, not proof).",
                         f"{I.fmt(f['value'], 'pct', lg)} من الحالات المشابهة كانت احتيالاً مؤكداً (سياق وليس دليلاً)."), "fact", [f["id"]]))
    if sysd.get("regle"):
        b.append(_p(I.tr(lg, "Règle de recommandation documentée : ", "Documented recommendation rule: ", "قاعدة التوصية: ") + sysd["regle"], "ml"))
    return b or [_p("—", "fact")]


def _investigation_recs(a, lg):
    sysd = a.extra.get("system") or {}
    items = []
    if sysd.get("decision") in ("BLOQUER", "ESCALADER"):
        items.append(I.tr(lg, "Contacter le client par un canal sûr avant toute conclusion ; ne pas révéler les signaux de détection.",
                          "Contact the customer through a safe channel before concluding; do not disclose detection signals.", "التواصل مع العميل عبر قناة آمنة."))
    if a.extra.get("triggers"):
        items.append(I.tr(lg, "Examiner les opérations postérieures à l'alerte sur la même carte.", "Review transactions after the alert on the same card.",
                          "مراجعة العمليات اللاحقة على نفس البطاقة."))
    items.append(I.tr(lg, "Enregistrer la décision et sa justification dans le journal (traçabilité).", "Record the decision and its rationale in the journal (traceability).",
                      "تسجيل القرار ومبرره في السجل."))
    return [{"t": "bullets", "title": I.tr(lg, "Prochaines étapes", "Next steps", "الخطوات التالية"),
             "items": [{"text": x, "kind": "recommendation", "refs": []} for x in items]}]


def _investigation_conclusion(a, lg):
    sysd = a.extra.get("system") or {}
    d = a.extra.get("decision")
    return I.tr(lg, f"Recommandation du système : {sysd.get('decision') or '—'}. Décision finale : "
                    + (f"{d.get('decision')} (employé)." if d else "à prendre par un employé habilité."),
                f"System recommendation: {sysd.get('decision') or '—'}. Final decision: " + (f"{d.get('decision')} (employee)." if d else "to be taken by an authorised employee."),
                f"توصية النظام: {sysd.get('decision') or '—'}. القرار النهائي: " + (f"{d.get('decision')}." if d else "يتخذه موظف مخول."))


# ---------------------------------------------------------------- optional AI writer, grounded
def allowed_numbers(a):
    vals = set()
    for f in a.facts:
        if f["value"] is None:
            continue
        v = f["value"]
        for x in (v, round(v), round(v, 1), round(v, 2), v * 100, round(v * 100, 1), round(v * 100, 2), round(v * 100)):
            vals.add(round(float(x), 2))
    for t in a.tables:
        for c in t["df"].select_dtypes("number").columns:
            for v in t["df"][c].dropna().head(40):
                for x in (v, round(v), v * 100, round(v * 100, 1)):
                    vals.add(round(float(x), 2))
    for i in a.insights:
        for txt in i["what"].values():
            for n in I.numbers_in(txt, a.lang):
                vals.add(round(n, 2))
    for p in (a.spec.get("period") or []) + (a.spec.get("previous") or []):
        for part in str(p).split("-"):
            vals.add(float(int(part)))
    return vals


def grounded(text, a):
    """Every number written must exist in the evidence (dates, times and evidence ids are not figures)."""
    ok = allowed_numbers(a)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?h\b", " ", text or "")
    bad = [n for n in I.numbers_in(text, a.lang) if not (abs(n) <= 12 or round(n, 2) in ok or any(abs(n - v) <= max(0.051, abs(v) * 0.002) for v in ok))]
    return not bad, bad


def ai_write(a, doc):
    """One Azure OpenAI call rewriting the summary opener and the conclusion for the audience, from verified evidence only."""
    import copilot
    if not copilot.configured():
        return doc, {"used": False, "reason": "not configured"}
    lg = a.lang
    ev = {"facts": [{"id": f["id"], "label": f["label"][lg], "value": I.fmt(f["value"], f["unit"], lg), "kind": f["kind"]} for f in a.facts][:60],
          "findings": [{"id": i["id"], "kind": i["kind"], "priority": i["priority"], "title": i["title"][lg], "what": i["what"][lg], "why": i["why"][lg],
                        "action": i["action"][lg]} for i in a.insights][:12], "limits": [x[lg] for x in a.limits]}
    prompt = ("You write two paragraphs of a professional bank report for: " + I.label(I.AUDIENCES[a.spec["audience"]], "en") + ". Report type: "
              + I.label(I.TYPES[a.spec["type"]], "en") + ". Language: " + {"fr": "French", "en": "English", "ar": "Modern Standard Arabic"}[lg]
              + ". Use ONLY the evidence below; copy numbers exactly as written; cite ids like [F3] or [I2]; separate facts from hypotheses; never "
              "present anything as an official bank decision; no customer identifiers. Return JSON {\"summary\": \"4-6 sentences\", \"conclusion\": "
              "\"2-4 sentences\"}.\nEVIDENCE: " + json.dumps(ev, ensure_ascii=False))
    try:
        txt, tokens = copilot.complete_json(prompt, tag="[report] writer", max_tokens=2500)
        out = json.loads(txt or "{}")
    except Exception as exc:
        return doc, {"used": False, "reason": str(exc)[:160]}
    report = {"used": True, "tokens": tokens, "accepted": [], "rejected": []}
    for sid, key in (("summary", "summary"), ("conclusion", "conclusion")):
        para = str(out.get(key) or "").strip()
        if not para:
            continue
        ok, bad = grounded(para, a)
        cited = re.findall(r"\[([FIT]\d+)\]", para)
        ids = {x["id"] for x in a.facts + a.insights + a.tables}
        if ok and all(c in ids for c in cited):
            sec = next((s for s in doc["sections"] if s["id"] == sid), None)
            if sec:
                sec["blocks"].insert(0 if sid == "summary" else 0, {"t": "p", "text": para, "kind": "ai", "refs": sorted(set(cited))})
                report["accepted"].append(sid)
        else:
            report["rejected"].append({"section": sid, "ungrounded_numbers": bad[:5], "unknown_refs": [c for c in cited if c not in ids]})
    return doc, report
