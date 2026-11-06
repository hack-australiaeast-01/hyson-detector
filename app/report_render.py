"""Document Formatting Engine: report bundle -> HTML (interactive), PDF (final), DOCX (editable), XLSX (supporting data).

A bundle is the JSON-serialisable snapshot of one report version (spec, document model, evidence, charts as base64 PNG), so
every version can be re-rendered identically later. Drafts carry a "DRAFT — not approved" mark; approved versions carry the
approver and the version hash.
"""
import base64
import html as H
import io
import json
import re

import pandas as pd

import report_i18n as I

COLS = {"grp": ("Segment", "Segment", "الشريحة"), "ops": ("Opérations", "Transactions", "العمليات"), "share_ops": ("% opérations", "% transactions", "% العمليات"),
        "frauds": ("Fraudes conf.", "Conf. frauds", "احتيال مؤكد"), "share_frauds": ("% fraudes", "% frauds", "% الاحتيال"),
        "fraud_rate": ("Taux de fraude", "Fraud rate", "معدل الاحتيال"), "lift": ("Sur-représentation", "Over-representation", "التمثيل المفرط"),
        "fraud_amount": ("Montant fraudé", "Fraud amount", "مبلغ الاحتيال"), "prev_frauds": ("Fraudes (préc.)", "Frauds (prev.)", "احتيال (سابق)"),
        "change": ("Évolution", "Change", "التغير"), "t": ("Période", "Period", "الفترة"), "model_alerts": ("Alertes modèle", "Model alerts", "تنبيهات النموذج"),
        "day": ("Jour", "Day", "اليوم"), "failed": ("Échecs", "Failed", "فشل"), "sensitive": ("Changements sensibles", "Sensitive changes", "تغييرات حساسة"),
        "spike": ("Pic", "Spike", "ذروة"), "magstripe": ("Piste magnétique", "Magnetic stripe", "شريط مغناطيسي"), "transaction_id": ("Opération", "Transaction", "العملية"),
        "similarity": ("Similarité", "Similarity", "التشابه"), "status_at": ("Statut à l'époque", "Status then", "الحالة آنذاك"),
        "scenario_known": ("Typologie", "Typology", "النمط"), "amount_tnd": ("Montant (TND)", "Amount (TND)", "المبلغ"), "channel": ("Canal", "Channel", "القناة"),
        "timestamp": ("Date", "Date", "التاريخ"), "country": ("Pays", "Country", "البلد"), "status": ("Statut", "Status", "الحالة")}
PCT_COLS = {"share_ops", "share_frauds", "fraud_rate", "change", "decline_rate", "similarity"}
TND_COLS = {"fraud_amount", "amount", "amount_tnd"}


def bundle(a, doc, ai_report=None):
    def clean(v):
        if isinstance(v, (pd.Timestamp,)):
            return str(v)
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        return v.item() if hasattr(v, "item") else v
    tables = []
    for t in a.tables:
        df = t["df"]
        cols = [c for c in t["cols"] if c in df.columns]
        tables.append({k: t[k] for k in ("id", "key", "title", "sql", "period", "source")} | {
            "cols": cols, "rows": [{c: clean(r[c]) for c in cols} for _, r in df.iterrows()]})
    extra = {}
    for k in ("transaction", "system", "decision", "board", "triggers", "agents"):
        if a.extra.get(k) is not None:
            extra[k] = json.loads(json.dumps(a.extra[k], default=str))
    return {"spec": a.spec, "doc": doc, "facts": a.facts, "tables": tables, "insights": a.insights, "checks": a.checks, "limits": a.limits,
            "recs": getattr(a, "recs", {}), "extra": extra, "ai": ai_report or {"used": False},
            "charts": [{k: c[k] for k in ("id", "key", "title", "caption", "period", "source", "refs")} | {"png": base64.b64encode(c["png"]).decode()}
                       for c in a.charts]}


def _cell(col, v, lang):
    if v is None:
        return "—"
    if col in PCT_COLS and isinstance(v, (int, float)):
        return I.fmt(v, "pct_change" if col == "change" else "pct", lang)
    if col in TND_COLS and isinstance(v, (int, float)):
        return I.fmt(v, "tnd", lang)
    if col == "lift" and isinstance(v, (int, float)):
        return I.fmt(v, "ratio", lang)
    if isinstance(v, bool):
        return "●" if v else ""
    if isinstance(v, (int, float)):
        return I.fmt(v, "count", lang) if float(v).is_integer() else f"{v:.3f}"
    return str(v)[:60]


def _find(b, kind, rid):
    return next((x for x in b[kind] if x["id"] == rid), None)


def _fact_line(b, f, lang, prev=None):
    s = f"{f['label'][lang]}: {I.fmt(f['value'], f['unit'], lang)}"
    if prev:
        s += f" ({I.tr(lang, 'préc.', 'prev.', 'سابق')} {I.fmt(prev['value'], prev['unit'], lang)})"
    return s


def _refs(r):
    return f" [{', '.join(r)}]" if r else ""


# ---------------------------------------------------------------- HTML
CSS = """body{font-family:'Segoe UI',Inter,Arial,sans-serif;color:#0F1E36;margin:0;background:#F4F6FA}
.page{max-width:900px;margin:0 auto;background:#fff;padding:48px 56px;box-shadow:0 2px 18px rgba(16,24,40,.08)}
.cover{border-left:6px solid VAR;padding:28px 30px;margin:-10px 0 34px;background:linear-gradient(135deg,#F5F8FF,#fff)}
.cover h1{font-size:28px;margin:6px 0 10px}.cover .inst{font-weight:700;color:VAR;letter-spacing:.08em;text-transform:uppercase;font-size:13px}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;font-size:13px;color:#33435C}.meta b{color:#0F1E36}
.cls{display:inline-block;margin-top:14px;padding:4px 12px;border:1.5px solid #D92D20;color:#D92D20;font-weight:700;font-size:12px;border-radius:4px}
.draft{background:#FFF4E5;border:1.5px dashed #C77700;color:#8A5300;padding:10px 14px;border-radius:8px;font-weight:700;margin-bottom:18px}
.ok{background:#EAF7EF;border:1.5px solid #16A34A;color:#0E6B33;padding:10px 14px;border-radius:8px;font-weight:600;margin-bottom:18px}
h2{font-size:19px;border-bottom:2px solid VAR;padding-bottom:6px;margin:34px 0 14px}h3{font-size:14px;margin:18px 0 8px}
p{line-height:1.6;font-size:14px;margin:8px 0}.k{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:999px;margin-inline-end:6px;
color:#fff;vertical-align:1px}.ref{color:#8A97AB;font-size:11px}ul{margin:6px 0 10px;padding-inline-start:20px}li{margin:4px 0;font-size:14px;line-height:1.5}
table{border-collapse:collapse;width:100%;margin:10px 0 4px;font-size:12.5px}th{background:#0B2545;color:#fff;text-align:start;padding:6px 8px;font-weight:600}
td{padding:5px 8px;border-bottom:1px solid #E3E8F0}tr:nth-child(even) td{background:#F8FAFD}.cap{font-size:11.5px;color:#5B6B82;margin:2px 0 14px}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:8px 0 14px}.kpi{border:1px solid #E3E8F0;border-radius:10px;padding:10px 12px}
.kpi .l{font-size:11.5px;color:#5B6B82}.kpi .v{font-size:20px;font-weight:800}.kpi .p{font-size:11px;color:#5B6B82}
.fd{border:1px solid #E3E8F0;border-inline-start:5px solid PRI;border-radius:10px;padding:10px 14px;margin:10px 0}.fd h4{margin:0 0 6px;font-size:14.5px}
.fd .row{font-size:13px;margin:3px 0}.fd .row b{color:#33435C}figure{margin:14px 0}figure img{max-width:100%}
.foot{font-size:11px;color:#8A97AB;border-top:1px solid #E3E8F0;margin-top:40px;padding-top:10px}"""


def html(b, draft=True, approval=None):
    s, doc, lang = b["spec"], b["doc"], b["spec"]["lang"]
    m, color = doc["meta"], doc["meta"]["color"]
    e = H.escape
    out = [f"<!doctype html><html lang='{lang}' dir='{'rtl' if lang == 'ar' else 'ltr'}'><head><meta charset='utf-8'><title>{e(m['title'])}</title>"
           f"<style>{CSS.replace('VAR', color).replace('PRI', '#C77700')}</style></head><body><div class='page'>"]
    if draft:
        out.append(f"<div class='draft'>{e(I.tr(lang, 'PROJET — non approuvé, ne pas diffuser', 'DRAFT — not approved, do not circulate', 'مسودة — غير معتمدة'))}</div>")
    elif approval:
        out.append(f"<div class='ok'>{e(I.tr(lang, 'Version approuvée par', 'Version approved by', 'نسخة معتمدة من'))} {e(approval['by'])} · {e(approval['at'])}"
                   f" · v{approval['version']} · {approval['hash'][:16]}</div>")
    logo = f"<img src='data:image/png;base64,{m['logo']}' style='height:46px;float:{'left' if lang == 'ar' else 'right'}'>" if m.get("logo") else ""
    out.append(f"<div class='cover'>{logo}<div class='inst'>{e(m['institution'])}</div><h1>{e(m['title'])}</h1><div class='meta'>"
               f"<div><b>{e(I.tr(lang, 'Période', 'Period', 'الفترة'))}</b> : {e(str(m['period']))}</div>"
               f"<div><b>{e(I.tr(lang, 'Généré le', 'Generated', 'تاريخ الإنشاء'))}</b> : {e(m['generated'][:16].replace('T', ' '))}</div>"
               f"<div><b>{e(I.tr(lang, 'Destinataires', 'Audience', 'الجمهور'))}</b> : {e(m['audience'])}</div>"
               f"<div><b>{e(I.tr(lang, 'Niveau', 'Depth', 'المستوى'))}</b> : {e(m['depth'])}</div></div>"
               f"<div class='cls'>{e(m['classification'])}</div><p style='font-size:12px;color:#5B6B82;margin-top:14px'>Hyson Detector · "
               f"{e(I.tr(lang, 'le modèle score, l’IA explique, l’employé décide', 'the model scores, AI explains, the employee decides', 'النموذج يقيّم والذكاء الاصطناعي يشرح والموظف يقرر'))}</p></div>")
    for sec in doc["sections"]:
        out.append(f"<h2>{e(sec['title'])}</h2>")
        if sec.get("edited"):
            out.append(f"<p class='ref'>{e(I.tr(lang, 'Section modifiée par', 'Section edited by', 'عدّلها'))} {e(sec['edited'])}</p>")
        for blk in sec["blocks"]:
            out.append(_html_block(b, blk, lang))
    out.append(f"<div class='foot'>{e(m.get('footer') or '')} {e(I.tr(lang, 'Source des données', 'Data source', 'مصدر البيانات'))} : {e(m['source'])}. "
               f"{e(I.tr(lang, 'Demande', 'Request', 'الطلب'))} : « {e(m.get('request', ''))[:300]} »</div></div></body></html>")
    return "".join(out)


def _badge(kind, lang):
    k = I.KIND.get(kind, I.KIND["fact"])
    return f"<span class='k' style='background:{k[3]}'>{H.escape(I.kind_label(kind, lang))}</span>"


def _html_block(b, blk, lang):
    e, t = H.escape, blk["t"]
    if t == "p":
        return f"<p>{_badge(blk['kind'], lang)}{e(blk['text'])}<span class='ref'>{e(_refs(blk.get('refs')))}</span></p>"
    if t == "bullets":
        head = f"<h3>{e(blk['title'])}</h3>" if blk.get("title") else ""
        return head + "<ul>" + "".join(f"<li>{_badge(i['kind'], lang)}{e(i['text'])}<span class='ref'>{e(_refs(i.get('refs')))}</span></li>"
                                       for i in blk["items"]) + "</ul>"
    if t == "kpis":
        cells = []
        for rid in blk["refs"]:
            f = _find(b, "facts", rid)
            if not f:
                continue
            pv = _find(b, "facts", blk.get("prev", {}).get(rid)) if blk.get("prev", {}).get(rid) else None
            ptxt = f"<div class='p'>{e(I.tr(lang, 'période préc.', 'prev. period', 'الفترة السابقة'))} {e(I.fmt(pv['value'], pv['unit'], lang))}</div>" if pv else ""
            cells.append(f"<div class='kpi'><div class='l'>{e(f['label'][lang])} <span class='ref'>[{f['id']}]</span></div>"
                         f"<div class='v'>{e(I.fmt(f['value'], f['unit'], lang))}</div>{ptxt}</div>")
        return f"<div class='kpis'>{''.join(cells)}</div>"
    if t == "table":
        tb = _find(b, "tables", blk["ref"])
        if not tb:
            return ""
        rows = tb["rows"][:blk.get("max_rows", 12)]
        head = "".join(f"<th>{e(I.tr(lang, *COLS.get(c, (c, c, c))))}</th>" for c in tb["cols"])
        body = "".join("<tr>" + "".join(f"<td>{e(_cell(c, r.get(c), lang))}</td>" for c in tb["cols"]) + "</tr>" for r in rows)
        return (f"<h3>{e(tb['title'][lang])} <span class='ref'>[{tb['id']}]</span></h3><table><tr>{head}</tr>{body}</table>"
                f"<div class='cap'>{e(I.tr(lang, 'Source', 'Source', 'المصدر'))} : {e(tb['source'])} · {e(I.period_text(tb['period'], lang))}</div>")
    if t == "chart":
        c = _find(b, "charts", blk["ref"])
        if not c:
            return ""
        return (f"<figure><img src='data:image/png;base64,{c['png']}' alt='{e(c['title'])}'><div class='cap'><b>[{c['id']}]</b> {e(c['caption'])} · "
                f"{e(c['period'])} · {e(c['source'])}</div></figure>")
    if t in ("finding", "risk"):
        i = _find(b, "insights", blk["ref"])
        if not i:
            return ""
        pr = I.PRIORITY[i["priority"]]
        lab = lambda fr, en, ar: e(I.tr(lang, fr, en, ar))  # noqa: E731
        rows = [(lab("Constat", "What happened", "ماذا حدث"), i["what"][lang]), (lab("Pourquoi c'est important", "Why it matters", "لماذا يهم"), i["why"][lang])]
        if t == "finding":
            rows.append((lab("Explications possibles (hypothèses)", "Possible explanations (hypotheses)", "تفسيرات محتملة (فرضيات)"), i["explain"][lang]))
        rows += [(lab("Impact potentiel", "Potential impact", "الأثر المحتمل"), i["impact"][lang]), (lab("Action", "Action", "الإجراء"), i["action"][lang])]
        return (f"<div class='fd' style='border-inline-start-color:{pr[3]}'><h4>{_badge(i['kind'], lang)}{e(i['title'][lang])} "
                f"<span class='ref'>[{i['id']}] · {e(I.tr(lang, *pr[:3]))} · {e(', '.join(i['refs']))}</span></h4>"
                + "".join(f"<div class='row'><b>{k}</b> : {e(v)}</div>" for k, v in rows) + "</div>")
    if t == "evidence":
        return "<ul>" + "".join(f"<li><b>{e(x['id'])}</b> [{e(x.get('kind', ''))}] {e(x['text'])}</li>" for x in b["extra"].get("board", [])) + "</ul>"
    if t == "register":
        head = "".join(f"<th>{e(x)}</th>" for x in (I.tr(lang, "Réf.", "Ref.", "المرجع"), I.tr(lang, "Élément", "Item", "العنصر"),
                                                     I.tr(lang, "Valeur", "Value", "القيمة"), I.tr(lang, "Nature", "Kind", "النوع"),
                                                     I.tr(lang, "Méthode", "Method", "الطريقة"), I.tr(lang, "Période", "Period", "الفترة")))
        rows = "".join(f"<tr><td>{f['id']}</td><td>{e(f['label'][lang])}</td><td>{e(I.fmt(f['value'], f['unit'], lang))}</td>"
                       f"<td>{e(I.kind_label(f['kind'], lang))}</td><td>{e(f['method'])}</td><td>{e(' → '.join(f['period']))}</td></tr>" for f in b["facts"])
        rows += "".join(f"<tr><td>{tb['id']}</td><td>{e(tb['title'][lang])}</td><td>{len(tb['rows'])} {e(I.tr(lang, 'lignes', 'rows', 'صفوف'))}</td>"
                        f"<td>{e(I.kind_label('fact', lang))}</td><td>SQL</td><td>{e(' → '.join(tb['period']))}</td></tr>" for tb in b["tables"])
        return f"<h3>{e(I.tr(lang, 'Registre des preuves', 'Evidence register', 'سجل الأدلة'))}</h3><table><tr>{head}</tr>{rows}</table>"
    if t == "checks":
        return f"<h3>{e(I.tr(lang, 'Contrôles de vérification', 'Verification checks', 'فحوص التحقق'))}</h3><ul>" + "".join(
            f"<li>{'✔' if c['ok'] else '⚠'} {e(c['detail'])}</li>" for c in b["checks"]) + "</ul>"
    return ""


# ---------------------------------------------------------------- plain-text view of blocks (PDF / DOCX)
def _items(b, blk, lang):
    """-> list of ('h3'|'p'|'li'|'table'|'img'|'cap', payload, kind)."""
    t = blk["t"]
    if t == "p":
        return [("p", blk["text"] + _refs(blk.get("refs")), blk["kind"])]
    if t == "bullets":
        return ([("h3", blk["title"], None)] if blk.get("title") else []) + [("li", i["text"] + _refs(i.get("refs")), i["kind"]) for i in blk["items"]]
    if t == "kpis":
        rows = []
        for rid in blk["refs"]:
            f = _find(b, "facts", rid)
            if f:
                pv = _find(b, "facts", blk.get("prev", {}).get(rid)) if blk.get("prev", {}).get(rid) else None
                rows.append([f"{f['label'][lang]} [{f['id']}]", I.fmt(f["value"], f["unit"], lang), I.fmt(pv["value"], pv["unit"], lang) if pv else ""])
        hdr = [I.tr(lang, "Indicateur", "Indicator", "المؤشر"), I.tr(lang, "Valeur", "Value", "القيمة"), I.tr(lang, "Période préc.", "Previous", "السابق")]
        return [("table", [hdr] + rows, None)] if rows else []
    if t == "table":
        tb = _find(b, "tables", blk["ref"])
        if not tb:
            return []
        hdr = [I.tr(lang, *COLS.get(c, (c, c, c))) for c in tb["cols"]]
        rows = [[_cell(c, r.get(c), lang) for c in tb["cols"]] for r in tb["rows"][:blk.get("max_rows", 12)]]
        return [("h3", f"{tb['title'][lang]} [{tb['id']}]", None), ("table", [hdr] + rows, None),
                ("cap", f"{I.tr(lang, 'Source', 'Source', 'المصدر')} : {tb['source']} · {I.period_text(tb['period'], lang)}", None)]
    if t == "chart":
        c = _find(b, "charts", blk["ref"])
        return [("img", base64.b64decode(c["png"]), None), ("cap", f"[{c['id']}] {c['caption']} · {c['period']} · {c['source']}", None)] if c else []
    if t in ("finding", "risk"):
        i = _find(b, "insights", blk["ref"])
        if not i:
            return []
        pr = I.tr(lang, *I.PRIORITY[i["priority"]][:3])
        out = [("h3", f"{i['title'][lang]} [{i['id']}] · {pr} · {I.kind_label(i['kind'], lang)}", None),
               ("li", f"{I.tr(lang, 'Constat', 'What happened', 'ماذا حدث')} : {i['what'][lang]} [{', '.join(i['refs'])}]", i["kind"]),
               ("li", f"{I.tr(lang, 'Pourquoi', 'Why it matters', 'لماذا يهم')} : {i['why'][lang]}", "fact")]
        if t == "finding":
            out.append(("li", f"{I.tr(lang, 'Hypothèses', 'Hypotheses', 'فرضيات')} : {i['explain'][lang]}", "hypothesis"))
        return out + [("li", f"{I.tr(lang, 'Impact', 'Impact', 'الأثر')} : {i['impact'][lang]}", "fact"),
                      ("li", f"{I.tr(lang, 'Action', 'Action', 'الإجراء')} : {i['action'][lang]}", "recommendation")]
    if t == "evidence":
        return [("li", f"{x['id']} [{x.get('kind', '')}] {x['text']}", "fact") for x in b["extra"].get("board", [])]
    if t == "register":
        hdr = [I.tr(lang, "Réf.", "Ref.", "المرجع"), I.tr(lang, "Élément", "Item", "العنصر"), I.tr(lang, "Valeur", "Value", "القيمة"),
               I.tr(lang, "Nature", "Kind", "النوع"), I.tr(lang, "Méthode", "Method", "الطريقة")]
        rows = [[f["id"], f["label"][lang][:60], I.fmt(f["value"], f["unit"], lang), I.kind_label(f["kind"], lang), f["method"][:70]] for f in b["facts"]]
        rows += [[tb["id"], tb["title"][lang][:60], f"{len(tb['rows'])}", I.kind_label("fact", lang), "SQL"] for tb in b["tables"]]
        return [("table", [hdr] + rows, None)]
    if t == "checks":
        return [("h3", I.tr(lang, "Contrôles de vérification", "Verification checks", "فحوص التحقق"), None)] + \
            [("li", ("✔ " if c["ok"] else "⚠ ") + c["detail"], "fact") for c in b["checks"]]
    return []


def _shape(s, lang):
    if lang != "ar":
        return s
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _ar_lines(text, font, size, width):
    """Arabic for PDF: wrap in logical order (by measured width), then reorder each line for display."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    lines = []
    for para in text.split("\n"):
        cur = []
        for w in para.split():
            trial = " ".join(cur + [w])
            if cur and stringWidth(_shape(trial, "ar"), font, size) > width:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        lines.append(" ".join(cur))
    return [_shape(x, "ar") for x in lines]


def _fonts():
    import matplotlib
    from pathlib import Path
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    d = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", str(d / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(d / "DejaVuSans-Bold.ttf")))


def pdf(b, draft=True, approval=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    _fonts()
    lang, doc = b["spec"]["lang"], b["doc"]
    m = doc["meta"]
    al = TA_RIGHT if lang == "ar" else TA_LEFT
    col = colors.HexColor(m["color"])
    st = {k: ParagraphStyle(k, fontName="DejaVu-Bold" if bold else "DejaVu", fontSize=sz, leading=sz * 1.35, alignment=al, textColor=tc, spaceAfter=sa)
          for k, bold, sz, tc, sa in (("h1", True, 22, colors.HexColor("#0F1E36"), 10), ("h2", True, 14, col, 8), ("h3", True, 10.5, colors.HexColor("#0F1E36"), 4),
                                      ("p", False, 9.5, colors.HexColor("#0F1E36"), 5), ("cap", False, 7.5, colors.HexColor("#5B6B82"), 8),
                                      ("cell", False, 7.5, colors.HexColor("#0F1E36"), 0), ("hcell", True, 7.5, colors.white, 0))}
    width = A4[0] - 4 * cm

    def P(txt, s="p", w=None):
        sty = st[s]
        if lang != "ar":
            return Paragraph(H.escape(str(txt)).replace("\n", "<br/>"), sty)
        return Paragraph("<br/>".join(H.escape(x) for x in _ar_lines(str(txt), sty.fontName, sty.fontSize, (w or width) - 4)), sty)
    buf = io.BytesIO()
    mark = I.tr(lang, "PROJET — non approuvé", "DRAFT — not approved", "مسودة — غير معتمدة") if draft else ""

    def deco(c, d):
        c.saveState()
        c.setFont("DejaVu", 7.5)
        c.setFillColor(colors.HexColor("#5B6B82"))
        c.drawString(2 * cm, 1.2 * cm, _shape(f"{m['institution']} · {m['classification']}", lang))
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"{d.page}")
        if mark:
            c.setFont("DejaVu-Bold", 40)
            c.setFillColor(colors.Color(0.85, 0.45, 0, alpha=0.12))
            c.translate(A4[0] / 2, A4[1] / 2)
            c.rotate(35)
            c.drawCentredString(0, 0, _shape(mark, lang))
        c.restoreState()
    story = [Spacer(1, 2.5 * cm), P(m["institution"].upper(), "h3"), P(m["title"], "h1"), Spacer(1, 0.3 * cm)]
    for k, v in ((I.tr(lang, "Période", "Period", "الفترة"), m["period"]), (I.tr(lang, "Généré le", "Generated", "تاريخ الإنشاء"), m["generated"][:16].replace("T", " ")),
                 (I.tr(lang, "Destinataires", "Audience", "الجمهور"), m["audience"]), (I.tr(lang, "Niveau", "Depth", "المستوى"), m["depth"]),
                 (I.tr(lang, "Classification", "Classification", "التصنيف"), m["classification"])):
        story.append(P(f"{k} : {v}"))
    if approval:
        story.append(P(f"{I.tr(lang, 'Approuvé par', 'Approved by', 'اعتمده')} {approval['by']} · {approval['at']} · v{approval['version']} · {approval['hash'][:16]}"))
    elif draft:
        story.append(P(mark, "h3"))
    story.append(Spacer(1, 0.6 * cm))
    story.append(P(I.tr(lang, "Hyson Detector — le modèle score, l'IA explique, l'employé décide.", "Hyson Detector — the model scores, AI explains, the employee decides.",
                        "Hyson Detector — النموذج يقيّم والذكاء الاصطناعي يشرح والموظف يقرر."), "cap"))
    story.append(PageBreak())
    for sec in doc["sections"]:
        story.append(P(sec["title"], "h2"))
        for blk in sec["blocks"]:
            for kind, payload, sk in _items(b, blk, lang):
                if kind in ("p", "li"):
                    tag = f"[{I.kind_label(sk, lang)}] " if sk and sk != "fact" else ""
                    story.append(P(("• " if kind == "li" else "") + tag + payload))
                elif kind in ("h3", "cap"):
                    story.append(P(payload, kind))
                elif kind == "img":
                    img = Image(io.BytesIO(payload))
                    ratio = img.imageHeight / img.imageWidth
                    img.drawWidth, img.drawHeight = 16 * cm, 16 * cm * ratio
                    story.append(img)
                elif kind == "table":
                    if all(len(r) > 2 and not r[-1] for r in payload[1:]) and payload[0][-1] == I.tr(lang, "Période préc.", "Previous", "السابق"):
                        payload = [r[:-1] for r in payload]
                    if lang == "ar":
                        payload = [list(reversed(r)) for r in payload]
                    cw = width / max(len(payload[0]), 1)
                    data = [[P(x, "hcell" if i == 0 else "cell", cw) for x in row] for i, row in enumerate(payload)]
                    tbl = Table(data, repeatRows=1, colWidths=[cw] * len(payload[0]), hAlign="RIGHT" if lang == "ar" else "LEFT")
                    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2545")),
                                             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6FA")]),
                                             ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E3E8F0")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                    story += [tbl, Spacer(1, 0.2 * cm)]
    story.append(Spacer(1, 0.4 * cm))
    story.append(P(f"{I.tr(lang, 'Source des données', 'Data source', 'مصدر البيانات')} : {m['source']}", "cap"))
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm, title=m["title"],
                      author="Hyson Detector").build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


def docx(b, draft=True, approval=None):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    lang, doc = b["spec"]["lang"], b["doc"]
    m = doc["meta"]
    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10)

    def rtl(par):
        if lang == "ar":
            par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            par._p.get_or_add_pPr().append(par._p.makeelement(qn("w:bidi"), {}))
            for r in par.runs:
                r._r.get_or_add_rPr().append(r._r.makeelement(qn("w:rtl"), {}))
        return par
    sec0 = d.sections[0]
    sec0.footer.paragraphs[0].text = f"{m['institution']} · {m['classification']}" + (" · " + I.tr(lang, "PROJET — non approuvé", "DRAFT — not approved",
                                                                                                      "مسودة") if draft else "")
    rtl(d.add_paragraph(m["institution"].upper()))
    h = d.add_heading(m["title"], 0)
    rtl(h)
    for k, v in ((I.tr(lang, "Période", "Period", "الفترة"), m["period"]), (I.tr(lang, "Généré le", "Generated", "تاريخ الإنشاء"), m["generated"][:16].replace("T", " ")),
                 (I.tr(lang, "Destinataires", "Audience", "الجمهور"), m["audience"]), (I.tr(lang, "Classification", "Classification", "التصنيف"), m["classification"])):
        rtl(d.add_paragraph(f"{k} : {v}"))
    if draft:
        p = d.add_paragraph()
        r = p.add_run(I.tr(lang, "PROJET — non approuvé, ne pas diffuser", "DRAFT — not approved, do not circulate", "مسودة — غير معتمدة"))
        r.bold, r.font.color.rgb = True, RGBColor(0xC7, 0x77, 0x00)
        rtl(p)
    elif approval:
        rtl(d.add_paragraph(f"{I.tr(lang, 'Approuvé par', 'Approved by', 'اعتمده')} {approval['by']} · {approval['at']} · v{approval['version']} · {approval['hash'][:16]}"))
    d.add_page_break()
    for sec in doc["sections"]:
        rtl(d.add_heading(sec["title"], 1))
        for blk in sec["blocks"]:
            for kind, payload, sk in _items(b, blk, lang):
                if kind in ("p", "li"):
                    p = d.add_paragraph(style="List Bullet" if kind == "li" else None)
                    if sk and sk != "fact":
                        tag = p.add_run(f"[{I.kind_label(sk, lang)}] ")
                        tag.bold, tag.font.color.rgb = True, RGBColor.from_string(I.KIND.get(sk, I.KIND["fact"])[3][1:])
                    p.add_run(payload)
                    rtl(p)
                elif kind == "h3":
                    rtl(d.add_heading(payload, 3))
                elif kind == "cap":
                    p = d.add_paragraph()
                    r = p.add_run(payload)
                    r.italic, r.font.size = True, Pt(8)
                    rtl(p)
                elif kind == "img":
                    d.add_picture(io.BytesIO(payload), width=Cm(16))
                elif kind == "table":
                    tbl = d.add_table(rows=len(payload), cols=len(payload[0]))
                    tbl.style = "Light Grid Accent 1"
                    for i, row in enumerate(payload):
                        for j, v in enumerate(row):
                            tbl.cell(i, j).text = str(v)
                    if lang == "ar":
                        tbl._tbl.tblPr.append(tbl._tbl.makeelement(qn("w:bidiVisual"), {}))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def xlsx(b):
    lang = b["spec"]["lang"]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([{"id": f["id"], "item": f["label"][lang], "value": f["value"], "unit": f["unit"], "kind": I.kind_label(f["kind"], lang),
                       "period": " → ".join(f["period"]), "method": f["method"], "source": f["source"], "sql": f["sql"], "computed_at": f["computed_at"]}
                      for f in b["facts"]]).to_excel(w, sheet_name="Evidence", index=False)
        for tb in b["tables"]:
            pd.DataFrame(tb["rows"], columns=tb["cols"]).to_excel(w, sheet_name=f"{tb['id']} {tb['key']}"[:31], index=False)
        pd.DataFrame([{"id": i["id"], "priority": i["priority"], "kind": I.kind_label(i["kind"], lang), "title": i["title"][lang], "what": i["what"][lang],
                       "evidence": ", ".join(i["refs"]), "action": i["action"][lang]} for i in b["insights"]]).to_excel(w, sheet_name="Findings", index=False)
        pd.DataFrame(b["checks"]).to_excel(w, sheet_name="Checks", index=False)
    return buf.getvalue()


def render(b, fmt, draft=True, approval=None):
    if fmt == "html":
        return html(b, draft, approval).encode("utf-8"), "text/html"
    if fmt == "pdf":
        return pdf(b, draft, approval), "application/pdf"
    if fmt == "docx":
        return docx(b, draft, approval), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == "xlsx":
        return xlsx(b), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    raise ValueError(fmt)
