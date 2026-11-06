"""Reporting engine: languages (FR / EN / AR), statement kinds, number formatting."""
import re
import unicodedata

LANGS = ("fr", "en", "ar")


def tr(lang, fr, en, ar=None):
    return {"fr": fr, "en": en, "ar": ar or en}.get(lang, fr)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


# every statement in a report carries one of these kinds (brief §8)
KIND = {"fact": ("Fait vérifié", "Verified fact", "حقيقة مُتحقَّق منها", "#16A34A"),
        "ml": ("Prédiction du modèle", "ML prediction", "تنبؤ نموذج التعلم الآلي", "#1E5BD8"),
        "ai": ("Interprétation IA", "AI interpretation", "تفسير بالذكاء الاصطناعي", "#7C3AED"),
        "employee": ("Confirmé par un employé", "Employee-confirmed", "مؤكَّد من طرف موظف", "#0E9F8A"),
        "hypothesis": ("Hypothèse à vérifier", "Unverified hypothesis", "فرضية تحتاج إلى تحقق", "#C77700"),
        "recommendation": ("Recommandation", "Recommendation", "توصية", "#0B2545"),
        "limit": ("Limite des données", "Data limitation", "حدود البيانات", "#D92D20")}


def kind_label(kind, lang):
    k = KIND.get(kind, KIND["fact"])
    return tr(lang, k[0], k[1], k[2])


TYPES = {  # id -> (FR, EN, AR, default audience, default depth)
    "executive": ("Rapport de direction", "Executive management report", "تقرير الإدارة العليا", "executive", "summary"),
    "investigation": ("Rapport d'enquête de fraude", "Fraud investigation report", "تقرير تحقيق في الاحتيال", "analyst", "detailed"),
    "cyber": ("Évaluation du risque cybersécurité", "Cybersecurity risk assessment", "تقييم مخاطر الأمن السيبراني", "cyber", "detailed"),
    "operational": ("Rapport opérationnel et contrôle interne", "Operational & administrative report", "تقرير تشغيلي ورقابة داخلية",
                    "operations", "standard"),
    "trends": ("Tendances stratégiques de la fraude", "Strategic fraud trends report", "تقرير الاتجاهات الاستراتيجية للاحتيال", "executive",
               "standard"),
    "periodic": ("Rapport périodique de performance", "Periodic performance report", "تقرير الأداء الدوري", "executive", "standard"),
}
AUDIENCES = {"executive": ("Direction générale", "Senior management", "الإدارة العليا"),
             "analyst": ("Analystes fraude / enquêteurs", "Fraud analysts / investigators", "محللو الاحتيال والمحققون"),
             "cyber": ("Sécurité des systèmes d'information", "Cybersecurity / information security", "الأمن السيبراني وأمن المعلومات"),
             "operations": ("Direction des opérations / contrôle interne", "Operations / internal control", "العمليات والرقابة الداخلية")}
DEPTHS = {"summary": ("Synthèse", "Executive summary", "ملخص"), "standard": ("Analyse opérationnelle", "Operational analysis", "تحليل تشغيلي"),
          "detailed": ("Analyse détaillée", "Detailed investigation", "تحليل مفصل")}
CONFIDENTIALITY = {"public": ("Public", "Public", "عام"), "internal": ("Usage interne", "Internal use", "للاستخدام الداخلي"),
                   "confidential": ("Confidentiel", "Confidential", "سري"), "restricted": ("Diffusion restreinte", "Restricted", "توزيع محدود")}
FORMATS = ("pdf", "docx", "html", "xlsx")
SECTIONS = {  # id -> (FR, EN, AR)
    "summary": ("Résumé exécutif", "Executive summary", "الملخص التنفيذي"),
    "scope": ("Périmètre et méthodologie", "Scope and methodology", "النطاق والمنهجية"),
    "kpis": ("Indicateurs clés", "Key performance indicators", "مؤشرات الأداء الرئيسية"),
    "case": ("Identification du cas", "Case identification", "تعريف الحالة"),
    "timeline": ("Chronologie de l'enquête", "Investigation timeline", "التسلسل الزمني للتحقيق"),
    "findings": ("Constats détaillés", "Detailed findings", "النتائج التفصيلية"),
    "cyber": ("Indicateurs de sécurité", "Security indicators", "مؤشرات الأمن"),
    "processing": ("Traitement des opérations et contrôles", "Transaction processing and controls", "معالجة العمليات والضوابط"),
    "ai": ("Résultats de l'investigation IA", "AI investigation results", "نتائج التحقيق بالذكاء الاصطناعي"),
    "risk": ("Évaluation des risques", "Risk assessment", "تقييم المخاطر"),
    "recommendations": ("Recommandations", "Recommendations", "التوصيات"),
    "conclusion": ("Conclusion", "Conclusion", "الخلاصة"),
    "appendix": ("Annexes : registre des preuves", "Appendices: evidence register", "الملاحق: سجل الأدلة"),
}
PRIORITY = {"high": ("Priorité haute", "High priority", "أولوية عالية", "#D92D20"),
            "medium": ("Priorité moyenne", "Medium priority", "أولوية متوسطة", "#C77700"),
            "low": ("À suivre", "Monitor", "للمتابعة", "#5B6B82")}
CHANNEL = {"TPE": ("TPE (paiement en magasin)", "POS (in-store)", "نقاط البيع"), "DAB": ("DAB (distributeurs)", "ATM", "الصراف الآلي"),
           "EN_LIGNE": ("Paiement en ligne", "Online card payment", "الدفع عبر الإنترنت"), "MOBILE": ("Application mobile", "Mobile app", "تطبيق الهاتف"),
           "WEB": ("Banque en ligne", "Internet banking", "الخدمات المصرفية عبر الإنترنت")}


def channel_label(c, lang):
    v = CHANNEL.get(str(c))
    return tr(lang, *v) if v else str(c)


def label(d, lang):
    return tr(lang, *d[:3])


# ---------------------------------------------------------------- numbers
def _group(n, sep):
    s = f"{abs(int(round(n))):,}".replace(",", sep)
    return ("-" if n < 0 else "") + s


def fmt(v, unit="count", lang="fr"):
    """Display value; never invents a value (None -> '—')."""
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    sep = "\u202f" if lang == "fr" else ","
    dec = "," if lang == "fr" else "."
    if unit == "count":
        return _group(v, sep)
    if unit == "tnd":
        whole = _group(v, sep)
        return f"{whole} TND"
    if unit in ("pct", "pct_change"):
        x = v * 100
        digits = 2 if abs(x) < 1 else 1
        s = f"{abs(x):.{digits}f}".replace(".", dec)
        sign = ("+" if x > 0 else "−" if x < 0 else "") if unit == "pct_change" else ("−" if x < 0 else "")
        return f"{sign}{s}\u202f%" if lang == "fr" else f"{sign}{s}%"
    if unit == "ratio":
        return f"×{v:.1f}".replace(".", dec)
    if unit == "hours":
        return f"{v:.1f} h".replace(".", dec)
    if unit == "score":
        return f"{v:.3f}".replace(".", dec)
    return str(v)


def fdate(d, lang="fr"):
    import pandas as pd
    d = pd.Timestamp(d)
    return d.strftime("%d/%m/%Y") if lang in ("fr", "ar") else d.strftime("%d %b %Y")


def period_text(p, lang):
    return tr(lang, f"du {fdate(p[0], lang)} au {fdate(p[1], lang)}", f"{fdate(p[0], lang)} to {fdate(p[1], lang)}",
              f"من {fdate(p[0], lang)} إلى {fdate(p[1], lang)}")


NUM = re.compile(r"(?<![\w.])[-−]?\d[\d\u202f\u00a0 ,.]*\d(?![\w])|(?<![\w.,])\d(?![\w.,])")


def numbers_in(text, lang):
    """Every number written in a text, as floats (handles '1 234,5', '1,234.5', '12,3 %')."""
    out = []
    for m in NUM.finditer(text or ""):
        s = m.group(0).replace("−", "-").replace("\u202f", "").replace("\u00a0", "").replace(" ", "")
        if lang == "fr":
            s = s.replace(".", "").replace(",", ".") if re.search(r",\d{1,2}$", s) or "," in s and s.count(",") == 1 and len(s.split(",")[1]) != 3 \
                else s.replace(",", "").replace(".", "")
        else:
            s = s.replace(",", "")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out
