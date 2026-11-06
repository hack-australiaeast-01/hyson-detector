"""Report Intelligence Pipeline, phase 4: analytical interpretation, deterministic (0 token).

Each insight answers: what happened, which evidence (F# / T#), why it matters, what could explain it (hypotheses, marked as such),
potential impact, what to investigate or improve, with a priority. Thresholds are fixed and documented here; small groups are
never used for a conclusion. Security findings are *indicators to verify*, never a claim that an attack or vulnerability exists.
"""
import pandas as pd

import report_analysis as RA
import report_i18n as I

MIN_FRAUDS, MIN_OPS, LIFT = 5, 30, 1.5


def _ins(a, kind, priority, area, refs, title, what, why, explain, impact, action, horizon="short"):
    a.insights.append({"id": f"I{len(a.insights) + 1}", "kind": kind, "priority": priority, "area": area, "refs": refs, "title": title,
                       "what": what, "why": why, "explain": explain, "impact": impact, "action": action, "horizon": horizon})


def _t3(fr, en, ar):
    return {"fr": fr, "en": en, "ar": ar}


def _f(a, key, prev=False, lang=None):
    f = a.get(key, prev)
    return I.fmt(f["value"], f["unit"], lang or a.lang) if f else "—"


def interpret(a):
    lg = a.lang
    F = lambda k, prev=False: _f(a, k, prev, lg)  # noqa: E731
    ref = lambda *keys: [a.get(k)["id"] for k in keys if a.get(k)]  # noqa: E731
    refp = lambda k: [a.get(k, True)["id"]] if a.get(k, True) else []  # noqa: E731
    # 1. overall change vs previous period
    cur, prev = a.val("frauds"), a.val("frauds", True)
    if cur is not None and prev and cur >= 10 and prev >= 10:
        ch = (cur - prev) / prev
        if abs(ch) >= 0.2:
            up = ch > 0
            c = I.fmt(ch, "pct_change", lg)
            _ins(a, "fact", "high" if up else "low", "trend", ref("frauds") + refp("frauds"),
                 _t3(f"Fraudes confirmées : {c} par rapport à la période précédente", f"Confirmed frauds: {c} vs the previous period",
                     f"الاحتيال المؤكد: {c} مقارنة بالفترة السابقة"),
                 _t3(f"{F('frauds')} fraudes confirmées contre {F('frauds', True)} sur la période précédente.",
                     f"{F('frauds')} confirmed frauds against {F('frauds', True)} in the previous period.",
                     f"{F('frauds')} حالة احتيال مؤكدة مقابل {F('frauds', True)} في الفترة السابقة."),
                 _t3("Une variation de cette ampleur change la charge des équipes et l'exposition financière.",
                     "A change of this size shifts team workload and financial exposure.", "تغير بهذا الحجم يؤثر على عبء الفرق والتعرض المالي."),
                 _t3("Campagne ciblée, saisonnalité ou évolution des contrôles : à vérifier.", "Targeted campaign, seasonality or a change in controls: to verify.",
                     "حملة مستهدفة أو موسمية أو تغيير في الضوابط: يحتاج تحقق."),
                 _t3(f"Montant des fraudes confirmées : {F('fraud_amount')}.", f"Confirmed fraud amount: {F('fraud_amount')}.",
                     f"مبلغ الاحتيال المؤكد: {F('fraud_amount')}."),
                 _t3("Analyser les segments qui expliquent la hausse (tableaux ci-dessous) avant d'ajuster les seuils." if up else
                     "Vérifier que la baisse n'est pas due à un retard de signalement avant de conclure.",
                     "Analyse the segments driving the rise (tables below) before adjusting thresholds." if up else
                     "Check the decrease is not a reporting delay before concluding.",
                     "تحليل الشرائح المسببة للارتفاع قبل تعديل العتبات." if up else "التحقق من أن الانخفاض ليس تأخراً في الإبلاغ."),
                 "immediate" if up else "short")
    # 2. concentrations and emerging groups in every breakdown
    for t in a.tables:
        if t["key"] not in RA.DIMS or "lift" not in t["df"] or t["df"]["lift"].isna().all():
            continue
        df = t["df"]
        n = 0
        for r in df.itertuples():
            fr = r.frauds if pd.notna(r.frauds) else 0
            if fr >= MIN_FRAUDS and r.ops >= MIN_OPS and pd.notna(r.lift) and r.lift >= LIFT and r.share_frauds >= 0.1 and n < 2:
                n += 1
                dim = t["title"][lg].split(" ", 3)[-1] if lg != "ar" else t["title"]["ar"]
                sf, so, li = I.fmt(r.share_frauds, "pct", lg), I.fmt(r.share_ops, "pct", lg), I.fmt(r.lift, "ratio", lg)
                amt = I.fmt(r.fraud_amount, "tnd", lg)
                _ins(a, "fact", "high" if r.share_frauds >= 0.3 else "medium", t["key"], [t["id"]],
                     _t3(f"Concentration : {r.grp}", f"Concentration: {r.grp}", f"تركز: {r.grp}"),
                     _t3(f"« {r.grp} » porte {sf} des fraudes confirmées pour {so} des opérations ({li}).",
                         f"\"{r.grp}\" carries {sf} of confirmed frauds for {so} of transactions ({li}).",
                         f"«{r.grp}» يمثل {sf} من الاحتيال المؤكد مقابل {so} من العمليات ({li})."),
                     _t3("Le risque n'est pas réparti uniformément : un contrôle ciblé est plus efficace qu'un durcissement général.",
                         "Risk is not evenly spread: a targeted control works better than a general tightening.",
                         "المخاطر غير موزعة بالتساوي: الرقابة المستهدفة أكثر فعالية."),
                     _t3("Point de compromission, faiblesse d'authentification ou exposition propre à ce segment : hypothèses à vérifier.",
                         "Point of compromise, weak authentication or exposure specific to this segment: hypotheses to verify.",
                         "نقطة اختراق أو ضعف في المصادقة أو تعرض خاص بهذه الشريحة: فرضيات تحتاج تحقق."),
                     _t3(f"{amt} de fraudes confirmées sur ce segment.", f"{amt} of confirmed frauds in this segment.", f"{amt} احتيال مؤكد في هذه الشريحة."),
                     _t3(f"Revoir les règles et seuils appliqués à « {r.grp} » ({dim}).", f"Review rules and thresholds applied to \"{r.grp}\" ({dim}).",
                         f"مراجعة القواعد والعتبات المطبقة على «{r.grp}»."), "short")
            was = 0 if ("prev_frauds" not in df or pd.isna(r.prev_frauds)) else r.prev_frauds
            rising = "change" in df and fr >= MIN_FRAUDS and (was == 0 or (pd.notna(r.change) and r.change >= 0.5))
            if rising and n < 3:
                n += 1
                _ins(a, "fact", "high", t["key"], [t["id"]],
                     _t3(f"Tendance émergente : {r.grp}", f"Emerging pattern: {r.grp}", f"نمط ناشئ: {r.grp}"),
                     _t3(f"« {r.grp} » passe de {I.fmt(was, 'count', lg)} à {I.fmt(fr, 'count', lg)} fraudes confirmées.",
                         f"\"{r.grp}\" goes from {I.fmt(was, 'count', lg)} to {I.fmt(fr, 'count', lg)} confirmed frauds.",
                         f"«{r.grp}» ارتفع من {I.fmt(was, 'count', lg)} إلى {I.fmt(fr, 'count', lg)} حالة احتيال مؤكدة."),
                     _t3("Une hausse rapide sur un segment précis signale souvent une nouvelle technique ou une campagne.",
                         "A fast rise in one segment often signals a new technique or a campaign.", "الارتفاع السريع في شريحة محددة يشير غالباً إلى أسلوب جديد."),
                     _t3("Nouvelle typologie, nouveau point de compromission ou simple variation aléatoire sur un petit volume : à vérifier.",
                         "New typology, new point of compromise, or random variation on a small volume: to verify.",
                         "نمط جديد أو نقطة اختراق جديدة أو تذبذب عشوائي: يحتاج تحقق."),
                     _t3(f"{I.fmt(r.fraud_amount, 'tnd', lg)} sur la période.", f"{I.fmt(r.fraud_amount, 'tnd', lg)} in the period.",
                         f"{I.fmt(r.fraud_amount, 'tnd', lg)} خلال الفترة."),
                     _t3("Ouvrir une enquête approfondie sur ce segment et surveiller chaque semaine.",
                         "Open a deep-dive investigation on this segment and monitor weekly.", "فتح تحقيق معمق ومراقبة أسبوعية."), "immediate")
    # 3. night, 3-D Secure, magnetic stripe
    ns, no = a.val("night_fraud_share"), a.val("night_ops_share")
    if ns and no and (a.val("frauds") or 0) >= 10 and ns >= 1.5 * no:
        _ins(a, "fact", "medium", "time", ref("night_fraud_share", "night_ops_share"),
             _t3("La fraude se concentre la nuit", "Fraud concentrates at night", "يتركز الاحتيال ليلاً"),
             _t3(f"{F('night_fraud_share')} des fraudes confirmées ont lieu entre 0 h et 6 h, contre {F('night_ops_share')} des opérations.",
                 f"{F('night_fraud_share')} of confirmed frauds happen between 0 and 6 h, against {F('night_ops_share')} of transactions.",
                 f"{F('night_fraud_share')} من الاحتيال المؤكد يحدث بين 0 و6 صباحاً مقابل {F('night_ops_share')} من العمليات."),
             _t3("La nuit, le client réagit moins vite et les contrôles humains sont réduits.", "At night customers react later and human checks are fewer.",
                 "ليلاً يتأخر رد فعل العميل وتقل الرقابة البشرية."),
             _t3("Fraudes automatisées ou décalage horaire de fraudeurs à l'étranger : hypothèses.", "Automated fraud or fraudsters abroad in another time "
                 "zone: hypotheses.", "احتيال آلي أو محتالون في منطقة زمنية أخرى: فرضيات."),
             _t3("Exposition sur les heures sans surveillance.", "Exposure during unmonitored hours.", "تعرض خلال ساعات بلا مراقبة."),
             _t3("Renforcer l'authentification ou les plafonds nocturnes sur les segments concernés.", "Strengthen authentication or night limits on the "
                 "affected segments.", "تعزيز المصادقة أو الحدود الليلية."), "short")
    n3, w3 = a.val("no3ds_rate"), a.val("with3ds_rate")
    if n3 and w3 and n3 >= 1.5 * w3:
        _ins(a, "fact", "high", "cyber", ref("no3ds_rate", "with3ds_rate"),
             _t3("Paiements en ligne sans 3-D Secure plus fraudés", "Online payments without 3-D Secure are more defrauded", "المدفوعات دون 3-D Secure أكثر عرضة"),
             _t3(f"Taux de fraude {F('no3ds_rate')} sans 3-D Secure contre {F('with3ds_rate')} avec.",
                 f"Fraud rate {F('no3ds_rate')} without 3-D Secure against {F('with3ds_rate')} with it.",
                 f"معدل الاحتيال {F('no3ds_rate')} دون 3-D Secure مقابل {F('with3ds_rate')} معه."),
             _t3("L'authentification forte est le levier le plus direct sur la fraude en ligne.", "Strong authentication is the most direct lever on online fraud.",
                 "المصادقة القوية هي الأداة الأكثر مباشرة."),
             _t3("Commerçants qui n'imposent pas 3-D Secure ; cartes compromises utilisées là où le contrôle est absent.",
                 "Merchants not enforcing 3-D Secure; compromised cards used where the check is absent.", "تجار لا يفرضون 3-D Secure."),
             _t3("Fraudes en ligne évitables.", "Avoidable online fraud.", "احتيال يمكن تجنبه."),
             _t3("Imposer 3-D Secure (ou refuser) au-delà d'un montant ; lister les commerçants sans 3-D Secure.",
                 "Enforce 3-D Secure (or decline) above an amount; list merchants without 3-D Secure.", "فرض 3-D Secure فوق مبلغ معين."), "immediate")
    ms, cp = a.val("magstripe_rate"), a.val("chip_rate")
    if ms and cp and ms >= 2 * cp:
        _ins(a, "fact", "medium", "cyber", ref("magstripe_rate", "chip_rate"),
             _t3("La piste magnétique reste une porte d'entrée", "Magnetic stripe remains an entry point", "الشريط المغناطيسي ما زال نقطة دخول"),
             _t3(f"Taux de fraude {F('magstripe_rate')} en piste magnétique contre {F('chip_rate')} en puce.",
                 f"Fraud rate {F('magstripe_rate')} on magnetic stripe against {F('chip_rate')} on chip.",
                 f"معدل الاحتيال {F('magstripe_rate')} بالشريط مقابل {F('chip_rate')} بالشريحة."),
             _t3("Une carte clonée ne fonctionne qu'en piste : c'est l'indicateur classique de skimming.",
                 "A cloned card only works on stripe: this is the classic skimming indicator.", "البطاقة المستنسخة تعمل بالشريط فقط."),
             _t3("Repli piste (fallback) accepté par certains terminaux ou DAB : à vérifier.", "Stripe fallback accepted by some terminals or ATMs: to verify.",
                 "قبول الشريط من بعض الأجهزة: يحتاج تحقق."),
             _t3("Fraudes de cartes clonées.", "Cloned-card fraud.", "احتيال البطاقات المستنسخة."),
             _t3("Inventorier les terminaux qui acceptent le repli piste et le restreindre.", "Inventory terminals accepting stripe fallback and restrict it.",
                 "جرد الأجهزة التي تقبل الشريط وتقييدها."), "short")
    _model_and_security(a, F, ref)
    return a.insights


def _model_and_security(a, F, ref):
    lg = a.lang
    mp, rp = a.val("model_precision"), a.val("rules_precision")
    if mp is not None and rp is not None and mp > rp:
        _ins(a, "ml", "medium", "model", ref("model_precision", "rules_precision", "model_recall", "rules_recall"),
             _t3("Le modèle trie mieux que le moteur de règles", "The model ranks better than the rules engine", "النموذج يرتب أفضل من محرك القواعد"),
             _t3(f"Précision des alertes : {F('model_precision')} pour le modèle contre {F('rules_precision')} pour les règles ; fraudes couvertes : "
                 f"{F('model_recall')} contre {F('rules_recall')}.", f"Alert precision: {F('model_precision')} for the model against {F('rules_precision')} "
                 f"for the rules; frauds caught: {F('model_recall')} against {F('rules_recall')}.",
                 f"دقة التنبيهات: {F('model_precision')} للنموذج مقابل {F('rules_precision')} للقواعد."),
             _t3("Moins de fausses alertes = plus de temps d'analyste sur les vrais cas et moins de clients dérangés.",
                 "Fewer false alerts = more analyst time on real cases and fewer customers disturbed.", "تنبيهات خاطئة أقل = وقت أكثر للحالات الحقيقية."),
             _t3("Mesure sur les opérations dont le statut est connu ; c'est une prédiction, pas une décision.",
                 "Measured on transactions with a known status; this is a prediction, not a decision.", "مقاس على العمليات معروفة الحالة؛ هذا تنبؤ وليس قراراً."),
             _t3("Charge d'analyse et frictions client.", "Analysis workload and customer friction.", "عبء التحليل وإزعاج العملاء."),
             _t3("Prioriser la file d'alertes par le score du modèle ; garder les règles comme filet de sécurité.",
                 "Prioritise the alert queue by the model score; keep rules as a safety net.", "ترتيب التنبيهات حسب درجة النموذج."), "short")
    if a.val("suspected"):
        _ins(a, "ml", "medium", "model", ref("suspected"),
             _t3("Alertes en attente de confirmation", "Alerts awaiting confirmation", "تنبيهات في انتظار التأكيد"),
             _t3(f"{F('suspected')} alertes du modèle n'ont pas encore de statut confirmé : ce sont des suspicions, pas des fraudes.",
                 f"{F('suspected')} model alerts have no confirmed status yet: suspected, not frauds.",
                 f"{F('suspected')} تنبيه للنموذج بلا حالة مؤكدة: اشتباه وليس احتيالاً."),
             _t3("Tant qu'elles ne sont pas traitées, l'exposition réelle est inconnue.", "Until handled, the real exposure is unknown.",
                 "التعرض الحقيقي غير معروف حتى تتم المعالجة."),
             _t3("Délai normal de signalement des fraudes (souvent plusieurs semaines).", "Normal fraud-reporting delay (often several weeks).",
                 "تأخر طبيعي في الإبلاغ عن الاحتيال."),
             _t3("Exposition non mesurée.", "Unmeasured exposure.", "تعرض غير مقاس."),
             _t3("Traiter la file par ordre de score et enregistrer chaque décision.", "Work the queue by score and record each decision.",
                 "معالجة القائمة حسب الدرجة وتسجيل كل قرار."), "immediate")
    if (a.val("fraud_approved_amount") or 0) > 0:
        _ins(a, "fact", "high", "exposure", ref("fraud_approved_amount", "fraud_amount"),
             _t3("Exposition financière", "Financial exposure", "التعرض المالي"),
             _t3(f"{F('fraud_approved_amount')} de fraudes confirmées ont été acceptées sur {F('fraud_amount')} de fraudes confirmées.",
                 f"{F('fraud_approved_amount')} of confirmed frauds were approved out of {F('fraud_amount')} of confirmed frauds.",
                 f"تمت الموافقة على {F('fraud_approved_amount')} من أصل {F('fraud_amount')} احتيال مؤكد."),
             _t3("C'est la perte potentielle à recouvrer ou à absorber.", "This is the potential loss to recover or absorb.", "هذه هي الخسارة المحتملة."),
             _t3("Fraudes détectées après coup (signalement client) plutôt qu'au moment de l'autorisation.",
                 "Frauds found afterwards (customer report) rather than at authorisation.", "اكتشاف الاحتيال بعد وقوعه."),
             _t3(f"{F('fraud_approved_amount')}.", f"{F('fraud_approved_amount')}.", f"{F('fraud_approved_amount')}."),
             _t3("Mesurer la part déjà recouvrée (rétrofacturations) et réduire le délai alerte → blocage.",
                 "Measure what was recovered (chargebacks) and shorten the alert → block delay.", "قياس ما تم استرداده وتقليص زمن الاستجابة."), "immediate")
    fs = a.val("fraud_after_sensitive")
    if fs is not None and fs >= 0.05:
        _ins(a, "hypothesis", "high" if fs >= 0.15 else "medium", "cyber", ref("fraud_after_sensitive", "sensitive_events"),
             _t3("Indicateur de prise de contrôle de compte (à vérifier)", "Account-takeover indicator (to verify)", "مؤشر استيلاء على الحساب (يحتاج تحقق)"),
             _t3(f"{F('fraud_after_sensitive')} des fraudes confirmées suivent un changement sensible du compte dans les 72 h.",
                 f"{F('fraud_after_sensitive')} of confirmed frauds follow a sensitive account change within 72 h.",
                 f"{F('fraud_after_sensitive')} من الاحتيال المؤكد يلي تغييراً حساساً خلال 72 ساعة."),
             _t3("Un ajout d'appareil ou de bénéficiaire juste avant une fraude est un schéma typique de prise de contrôle.",
                 "A new device or payee just before a fraud is a typical takeover pattern.", "إضافة جهاز أو مستفيد قبل الاحتيال نمط استيلاء نموذجي."),
             _t3("Hameçonnage, vol d'identifiants ou ingénierie sociale : non démontré par ces seules données.",
                 "Phishing, stolen credentials or social engineering: not proven by these data alone.", "تصيد أو سرقة بيانات اعتماد: غير مثبت بهذه البيانات وحدها."),
             _t3("Fraudes de virement et de paiement mobile.", "Transfer and mobile payment fraud.", "احتيال التحويلات والدفع عبر الهاتف."),
             _t3("Demander à la sécurité de vérifier les journaux d'accès de ces clients ; exiger une confirmation forte après un changement sensible.",
                 "Ask security to review these customers' access logs; require strong confirmation after a sensitive change.",
                 "مراجعة سجلات الدخول وطلب تأكيد قوي بعد أي تغيير حساس."), "immediate")
    sp = next((t for t in a.tables if t["key"] == "auth_daily"), None)
    if sp is not None and sp["df"]["spike"].any():
        days = ", ".join(str(d)[:10] for d in sp["df"].loc[sp["df"]["spike"], "day"].head(5))
        _ins(a, "hypothesis", "medium", "cyber", [sp["id"]],
             _t3("Pics de connexions échouées", "Spikes of failed logins", "ارتفاعات في محاولات الدخول الفاشلة"),
             _t3(f"Jours au-dessus de la moyenne + 3 écarts-types : {days}.", f"Days above mean + 3 standard deviations: {days}.",
                 f"أيام فوق المتوسط + 3 انحرافات معيارية: {days}."),
             _t3("Peut correspondre à des essais d'identifiants en masse.", "May correspond to mass credential attempts.", "قد يتوافق مع محاولات جماعية."),
             _t3("Incident technique, campagne d'attaque ou simple panne : non déterminé.", "Technical incident, attack campaign or outage: undetermined.",
                 "عطل تقني أو هجوم: غير محدد."),
             _t3("À qualifier par la sécurité.", "To be qualified by security.", "يحتاج تقييم من الأمن."),
             _t3("Croiser ces dates avec les journaux du SOC.", "Cross these dates with SOC logs.", "مقاطعة هذه التواريخ مع سجلات مركز العمليات الأمنية."), "short")
    dr = next((t for t in a.tables if t["key"] == "decline_reasons"), None)
    if dr is not None:
        pin = dr["df"][dr["df"]["grp"].astype(str).str.contains("PIN|CVV", case=False, na=False)]
        if len(pin) and pin["share_ops"].sum() >= 0.15:
            sh = I.fmt(pin["share_ops"].sum(), "pct", lg)
            _ins(a, "hypothesis", "low", "operations", [dr["id"]],
                 _t3("Refus pour code ou CVV erronés", "Declines for wrong PIN or CVV", "رفض بسبب رمز خاطئ"),
                 _t3(f"{sh} des refus viennent d'un code PIN ou CVV erroné.", f"{sh} of declines come from a wrong PIN or CVV.", f"{sh} من الرفض بسبب رمز خاطئ."),
                 _t3("Signal à la fois de friction client et de tests de cartes.", "Signal of both customer friction and card testing.", "مؤشر إزعاج للعملاء واختبار بطاقات."),
                 _t3("Oublis de code (friction) ou essais frauduleux répétés : à distinguer par carte.", "Forgotten codes (friction) or repeated fraud "
                     "attempts: to separate per card.", "نسيان الرمز أو محاولات احتيالية متكررة."),
                 _t3("Expérience client et risque de test.", "Customer experience and testing risk.", "تجربة العميل ومخاطر الاختبار."),
                 _t3("Suivre les cartes avec plusieurs refus de code en 24 h.", "Track cards with several PIN declines within 24 h.", "متابعة البطاقات ذات الرفض المتكرر."),
                 "long")


def recommendations(a):
    """Actions grouped by horizon, from the insights + structural recommendations that the data justify."""
    lg = a.lang
    recs = {"immediate": [], "short": [], "long": []}
    for i in sorted(a.insights, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]]):
        recs[i["horizon"]].append({"text": i["action"][lg], "refs": [i["id"]] + i["refs"], "priority": i["priority"]})
    if a.val("labelled_share") is not None and a.val("labelled_share") < 0.999:
        recs["short"].append({"text": I.tr(lg, "Accélérer le retour des statuts de fraude (signalements clients, rétrofacturations) pour mesurer la période complète.",
                                           "Speed up the return of fraud statuses (customer reports, chargebacks) to measure the full period.",
                                           "تسريع إرجاع حالات الاحتيال لقياس الفترة كاملة."), "refs": [a.get("labelled_share")["id"]], "priority": "medium"})
    if a.src.tenant is not None and not a.src.tenant.active_model():
        recs["long"].append({"text": I.tr(lg, "Entraîner et faire approuver un modèle propre à la banque dès que les étiquettes suffisent.",
                                          "Train and approve a bank-specific model as soon as labels suffice.", "تدريب نموذج خاص بالبنك واعتماده."),
                             "refs": [], "priority": "low"})
    recs["long"].append({"text": I.tr(lg, "Réviser ce rapport chaque période avec les mêmes indicateurs pour suivre l'effet des actions.",
                                      "Review this report every period with the same indicators to track the effect of actions.",
                                      "مراجعة هذا التقرير كل فترة بنفس المؤشرات."), "refs": [], "priority": "low"})
    return recs


def run(spec, src=None):
    """Phases 1-4 -> Analysis (facts, tables, checks, limits, insights, recommendations)."""
    import report_sources as rs
    src = src or rs.get(spec["source"])
    a = RA.Analysis(spec, src)
    period = spec["period"]
    if spec["type"] == "investigation":
        RA.investigation_case(a)
        a.recs = {"immediate": [], "short": [], "long": []}
        a.check("case", "transaction" in a.extra, a.L("Opération retrouvée dans les données.", "Transaction found in the data.", "تم العثور على العملية."), "error")
        return a
    ov = RA.overview(a, period)
    prev = spec.get("previous") if spec.get("compare") else None
    if prev:
        RA.overview(a, prev, prev=True)
    dims = ["channel"]
    focus = set(spec.get("focus") or [])
    if spec["type"] in ("trends", "periodic", "executive") or "card_type" in focus:
        dims.append("card_type")
    if spec["type"] in ("trends", "executive", "periodic") or "merchant" in focus:
        dims.append("merchant_category")
    if spec["type"] in ("trends",) or "geography" in focus:
        dims += ["country", "region"]
    if spec["depth"] == "detailed" or "time" in focus:
        dims.append("hour_band")
    if spec["type"] == "cyber" or "cyber" in focus:
        dims.append("entry_mode")
    if spec["type"] == "operational":
        dims.append("segment")
    for d in dict.fromkeys(dims):
        RA.breakdown(a, d, period, prev)
    RA.trend(a, period)
    if spec["type"] == "cyber" or "cyber" in focus:
        RA.cyber(a, period)
    elif spec["type"] in ("trends", "periodic", "executive"):
        RA._entry_rates(a, period)
    if spec["type"] == "operational" or "operational" in focus:
        RA.operational(a, period)
    RA.verify(a, ov)
    interpret(a)
    a.recs = recommendations(a)
    a.check("evidence_links", all(all(any(x["id"] == r for x in a.facts + a.tables + a.insights) for r in i["refs"]) for i in a.insights),
            a.L("Chaque constat renvoie à une preuve existante.", "Every finding points to existing evidence.", "كل نتيجة تشير إلى دليل موجود."), "error")
    return a
