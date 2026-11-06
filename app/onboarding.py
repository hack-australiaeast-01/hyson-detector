"""New data source onboarding: profile -> map & translate -> measure accuracy -> human approval.

The AI proposes, the data owner approves: nothing reaches the platform without a named approval, and every
mapping is versioned (data contract). Mapping is rule-based by default (0 tokens); an optional single Azure
OpenAI call can refine it from column *names and statistics only* (never raw rows, never identifiers).
"""
import difflib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import data_access as da
import features as fx
import ui

STAGING = da.DATA / "staging"
LOG = da.DATA / "onboarding_log.csv"
SAMPLE = Path(__file__).parent / "samples" / "partner_bank_sample.csv"

# ---------------------------------------------------------------- canonical schema (our silver_transactions)
TARGETS = {  # field: (required, kind, synonyms)
    "transaction_id": (True, "id", ["transaction_id", "txn_ref", "tx_id", "txnid", "reference", "ref", "operation_id", "id_transaction"]),
    "timestamp": (True, "datetime", ["timestamp", "datetime", "txn_date_time", "date_time", "date", "transaction_date", "date_heure", "time"]),
    "customer_id": (True, "id", ["customer_id", "client_no", "client_id", "cust_id", "customer", "client", "account_holder"]),
    "amount_tnd": (True, "amount", ["amount", "montant", "amt", "value", "valeur", "amount_tnd", "sum"]),
    "currency": (False, "currency", ["currency", "devise", "ccy", "cur"]),
    "channel": (True, "code", ["channel", "canal", "terminal_type", "source_channel"]),
    "entry_mode": (False, "code", ["entry_mode", "entrymode", "pos_entry", "mode_saisie", "capture_mode", "entry"]),
    "transaction_type": (True, "code", ["transaction_type", "txn_type", "type", "operation_type", "nature"]),
    "country": (False, "country", ["country", "pays", "merchant_country", "country_code"]),
    "status": (False, "code", ["status", "result", "statut", "response", "outcome"]),
    "card_id": (False, "id", ["card_id", "card_number_masked", "card_number", "pan_masked", "carte", "card"]),
    "merchant_id": (False, "id", ["merchant_id", "mid", "merchant", "commercant"]),
    "is_fraud": (False, "label", ["is_fraud", "fraud_flag", "fraud", "fraude", "label"]),
}
CODES = {
    "channel": {"TPE": ["pos", "tpe", "store", "in_store", "card_present", "magasin"], "DAB": ["atm", "dab", "gab", "cash"],
                "EN_LIGNE": ["ecom", "ecommerce", "e_commerce", "online", "cnp", "en_ligne", "web_card"],
                "MOBILE": ["mobile", "mobile_app", "app", "wallet"], "WEB": ["web", "netbanking", "internet_banking", "online_banking"]},
    "entry_mode": {"CHIP": ["chip", "emv", "puce"], "SANS_CONTACT": ["contactless", "nfc", "tap", "sans_contact"],
                   "MAGSTRIPE": ["swipe", "magstripe", "stripe", "piste"], "ECOM_3DS": ["3ds", "ecom_3ds", "secure"],
                   "ECOM_SANS_3DS": ["no3ds", "ecom_no3ds", "non_3ds", "ecom_sans_3ds"], "APP_AUTH": ["app", "app_auth", "biometric"]},
    "transaction_type": {"ACHAT": ["purchase", "payment", "achat", "sale"], "RETRAIT": ["withdrawal", "retrait", "cash_withdrawal"],
                         "VIREMENT": ["transfer", "virement", "wire"], "PAIEMENT_FACTURE": ["bill_payment", "bill", "facture"],
                         "RECHARGE": ["top_up", "topup", "recharge", "reload"]},
    "status": {"APPROUVEE": ["approved", "success", "ok", "accepted", "approuvee"], "REFUSEE": ["declined", "rejected", "failed", "refused", "refusee"]},
}
ISO3 = {"TUN": "TN", "FRA": "FR", "ITA": "IT", "DEU": "DE", "ESP": "ES", "BEL": "BE", "GBR": "GB", "USA": "US", "CHN": "CN",
        "TUR": "TR", "ARE": "AE", "EGY": "EG", "DZA": "DZ", "LBY": "LY", "MAR": "MA", "SAU": "SA", "CAN": "CA", "NLD": "NL", "CHE": "CH"}
NAMES = {"tunisia": "TN", "tunisie": "TN", "france": "FR", "italy": "IT", "italie": "IT", "germany": "DE", "allemagne": "DE",
         "spain": "ES", "espagne": "ES", "turkey": "TR", "turquie": "TR"}
DEFAULT_RATES = {"TND": 1.0, "EUR": 3.40, "USD": 3.10}     # indicative, editable on screen


def _n(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", s)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _snake(col):
    return _n(re.sub(r"([a-z])([A-Z])", r"\1_\2", str(col)))


def _code_map(field, value):
    v = _n(value)
    for code, words in CODES.get(field, {}).items():
        if v == _n(code) or v in words:
            return code
    return None


def _country(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    v = str(value).strip()
    if len(v) == 2:
        return v.upper()
    if len(v) == 3 and v.upper() in ISO3:
        return ISO3[v.upper()]
    return NAMES.get(_n(v))


def _value_score(kind, field, s):
    s = s.dropna()
    s = s[s.astype(str).str.strip() != ""]
    if s.empty:
        return 0.0
    if kind == "datetime":
        return float(pd.to_datetime(s.astype(str), errors="coerce", dayfirst=True, format="mixed").notna().mean())
    if kind == "amount":
        x = pd.to_numeric(s, errors="coerce")
        return float(x.notna().mean() * (x.dropna() >= 0).mean()) if x.notna().any() else 0.0
    if kind == "code":
        return float(s.map(lambda v: _code_map(field, v) is not None).mean())
    if kind == "country":
        return float(s.map(lambda v: _country(v) is not None).mean())
    if kind == "currency":
        return float(s.astype(str).str.upper().isin(list(DEFAULT_RATES) + ["GBP", "CHF"]).mean())
    if kind == "label":
        return float(s.astype(str).isin(["0", "1", "True", "False", "true", "false"]).mean())
    if kind == "id":
        return min(1.0, s.nunique() / max(len(s), 1) * 1.2) if field == "transaction_id" else 0.6
    return 0.0


def propose_mapping(df):
    """Rule-based mapping: name similarity (60 %) + value fit (40 %). Returns {target: (source, confidence)}."""
    scores = []
    for tgt, (_, kind, syns) in TARGETS.items():
        for col in df.columns:
            c = _snake(col)
            name = max(difflib.SequenceMatcher(None, c, s).ratio() for s in syns)
            if any(s == c or (len(s) > 3 and s in c) for s in syns):
                name = max(name, 0.92)
            val = _value_score(kind, tgt, df[col])
            scores.append((0.6 * name + 0.4 * val, tgt, col))
    out, used = {}, set()
    for sc, tgt, col in sorted(scores, reverse=True):
        if tgt in out or col in used or sc < 0.45:
            continue
        out[tgt] = (col, round(sc, 2))
        used.add(col)
    return out


def translate(df, mapping, rates):
    """Apply the mapping -> canonical frame + per-field validity and the values that could not be translated."""
    out, report = pd.DataFrame(index=df.index), {}
    cur = df[mapping["currency"]].astype(str).str.upper() if mapping.get("currency") else pd.Series("TND", index=df.index)
    for tgt, src in mapping.items():
        if not src or tgt == "currency":
            continue
        kind = TARGETS[tgt][1]
        raw = df[src]
        present = raw.notna() & (raw.astype(str).str.strip() != "")
        if kind == "datetime":
            val = pd.to_datetime(raw.astype(str), errors="coerce", dayfirst=True, format="mixed")
        elif kind == "amount":
            val = pd.to_numeric(raw, errors="coerce") * cur.map(rates).astype(float)
        elif kind == "code":
            val = raw.map(lambda v: _code_map(tgt, v) if pd.notna(v) else None)
        elif kind == "country":
            val = raw.map(_country)
        elif kind == "label":
            val = raw.astype(str).str.lower().map({"1": 1, "true": 1, "0": 0, "false": 0})
        else:
            val = raw.where(present)
        out[tgt] = val
        ok = present & pd.Series(val, index=df.index).notna()
        bad = raw[present & ~ok].astype(str).value_counts().head(5).to_dict()
        report[tgt] = {"source": src, "present": int(present.sum()), "valid": int(ok.sum()),
                       "validity": float(ok.sum() / max(present.sum(), 1)), "untranslated": bad}
    if "currency" in mapping and mapping["currency"]:
        unknown = sorted(set(cur.unique()) - set(rates))
        report["currency"] = {"source": mapping["currency"], "present": int(len(cur)), "valid": int(cur.isin(rates).sum()),
                              "validity": float(cur.isin(rates).mean()), "untranslated": {u: int((cur == u).sum()) for u in unknown}}
    return out, report


@st.cache_data(ttl=3600, show_spinner=False)
def reference(_mode):
    """Our labelled history: channel mix and amount distribution (bins), used to measure drift of a new source."""
    return fx._q("onboard_ref", """
        SELECT channel, CASE WHEN amount_tnd < 20 THEN 1 WHEN amount_tnd < 50 THEN 2 WHEN amount_tnd < 100 THEN 3
                             WHEN amount_tnd < 250 THEN 4 WHEN amount_tnd < 500 THEN 5 WHEN amount_tnd < 1000 THEN 6
                             WHEN amount_tnd < 3000 THEN 7 ELSE 8 END AS bin, COUNT(*) AS n
        FROM dbo.silver_transactions WHERE period <> 'test' GROUP BY channel,
             CASE WHEN amount_tnd < 20 THEN 1 WHEN amount_tnd < 50 THEN 2 WHEN amount_tnd < 100 THEN 3
                  WHEN amount_tnd < 250 THEN 4 WHEN amount_tnd < 500 THEN 5 WHEN amount_tnd < 1000 THEN 6
                  WHEN amount_tnd < 3000 THEN 7 ELSE 8 END""")


BINS = [-np.inf, 20, 50, 100, 250, 500, 1000, 3000, np.inf]


def psi(expected, actual):
    e = np.clip(np.asarray(expected, float) / max(np.sum(expected), 1), 1e-4, None)
    a = np.clip(np.asarray(actual, float) / max(np.sum(actual), 1), 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def accuracy(canon, report, ref):
    """Scores shown to the approver: mapping quality, reconciliation, drift vs our data."""
    req = [t for t, (r, _, _) in TARGETS.items() if r]
    mapped_req = [t for t in req if t in report]
    validity = np.mean([report[t]["validity"] for t in mapped_req]) if mapped_req else 0.0
    res = {"coverage": len(mapped_req) / len(req), "validity": float(validity), "missing_required": [t for t in req if t not in report]}
    if ref is not None and not ref.empty and "channel" in canon and "amount_tnd" in canon:
        ref = ref.assign(n=pd.to_numeric(ref.n, errors="coerce"))
        chans = sorted(set(ref.channel.dropna()) | set(canon.channel.dropna()))
        res["psi_channel"] = psi([ref[ref.channel == c].n.sum() for c in chans], [(canon.channel == c).sum() for c in chans])
        b = pd.cut(canon.amount_tnd.dropna(), BINS, labels=range(1, 9)).value_counts().reindex(range(1, 9), fill_value=0)
        res["psi_amount"] = psi(ref.groupby("bin").n.sum().reindex(range(1, 9), fill_value=0).values, b.values)
    if "is_fraud" in canon:
        res["fraud_rate"] = float(canon.is_fraud.mean())
    res["score"] = res["coverage"] * res["validity"]
    worst_psi = max(res.get("psi_channel", 0), res.get("psi_amount", 0))
    res["gate"] = ("green" if res["coverage"] == 1 and res["validity"] >= 0.95 and worst_psi < 0.2
                   else "amber" if res["coverage"] == 1 and res["validity"] >= 0.85 else "red")
    return res


def ai_refine(df, lang):
    """Optional: ONE Azure OpenAI call on column names + statistics (no raw rows, no identifiers). Returns {target: source}."""
    import copilot
    if not copilot.configured():
        return None, "Azure OpenAI non configuré."
    profile = []
    for c in df.columns:
        s = df[c].dropna().astype(str)
        info = {"column": c, "dtype": str(df[c].dtype), "distinct": int(s.nunique()), "null_rate": round(float(df[c].isna().mean()), 3)}
        if s.nunique() <= 12:                                  # low-cardinality codes only (never IDs or free text)
            info["values"] = sorted(s.unique().tolist())[:12]
        elif pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.9:
            x = pd.to_numeric(df[c], errors="coerce")
            info["stats"] = {"min": float(x.min()), "median": float(x.median()), "max": float(x.max())}
        profile.append(info)
    target_desc = {t: k for t, (_, k, _) in TARGETS.items()}
    prompt = ("Map the source columns of a bank transaction file to our target schema. Answer ONLY with a JSON object "
              "{target_field: source_column_or_null}. Targets (field: kind): " + json.dumps(target_desc) +
              "\nSource profile: " + json.dumps(profile, ensure_ascii=False))
    client = copilot._client()
    import os
    kw = dict(model=os.environ["AZURE_OPENAI_DEPLOYMENT"], messages=[{"role": "user", "content": prompt}],
              response_format={"type": "json_object"})
    resp = (client.chat.completions.create(max_completion_tokens=2000, reasoning_effort="low", **kw) if copilot._is_reasoning()
            else client.chat.completions.create(max_tokens=400, temperature=0, **kw))
    used = getattr(resp, "usage", None)
    copilot._log({"ts": datetime.now(), "question": "[onboarding] schema mapping", "intent": "onboarding", "mode": "Azure OpenAI",
                  "cached": False, "tools": [], "tokens": {"prompt": getattr(used, "prompt_tokens", 0),
                                                           "completion": getattr(used, "completion_tokens", 0),
                                                           "total": getattr(used, "total_tokens", 0)}})
    m = json.loads(resp.choices[0].message.content or "{}")
    return {k: v for k, v in m.items() if k in TARGETS and (v is None or v in df.columns)}, getattr(used, "total_tokens", 0)


def _log_event(row):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)


# ---------------------------------------------------------------- page
def page_onboarding(c, mode):
    L = c.L
    ui.hero(L("Données · intégration", "Data · onboarding"), L("Nouvelle source de données", "New data source"),
            L("Chargez un fichier d'une autre banque ou d'un partenaire : la plateforme le profile, propose la correspondance avec notre "
              "schéma et traduit les codes, mesure la qualité et l'écart avec nos données, puis attend votre approbation.",
              "Load a file from another bank or partner: the platform profiles it, proposes the mapping to our schema and translates "
              "the codes, measures quality and drift against our data, then waits for your approval."), c.chips())

    # ---- 1. load
    up = st.file_uploader(L("Fichier CSV (échantillon)", "CSV file (sample)"), type=["csv"])
    use_sample = st.toggle(L("Utiliser l'échantillon « banque partenaire » (synthétique)", "Use the \"partner bank\" sample (synthetic)"),
                           value=up is None)
    if up is not None and not use_sample:
        df, name = pd.read_csv(up), Path(up.name).stem
    elif SAMPLE.exists():
        df, name = pd.read_csv(SAMPLE), "partner_bank_sample"
    else:
        st.info(L("Chargez un fichier CSV.", "Load a CSV file."))
        return
    df = df.head(50_000)

    # ---- 2. profile
    ui.section(L("2 · Profil de la source", "2 · Source profile"))
    prof = pd.DataFrame({"column": df.columns, "type": [str(t) for t in df.dtypes],
                         "empty": [float(df[x].isna().mean() + (df[x].astype(str).str.strip() == "").mean()) for x in df.columns],
                         "distinct": [int(df[x].nunique()) for x in df.columns],
                         "examples": [", ".join(map(str, df[x].dropna().astype(str).unique()[:3])) if df[x].nunique() <= 20
                                      else L("(masqué : identifiant / valeur libre)", "(masked: identifier / free value)") for x in df.columns]})
    a, b, c3 = st.columns(3)
    a.metric(L("Lignes", "Rows"), f"{len(df):,}".replace(",", " "))
    b.metric(L("Colonnes", "Columns"), len(df.columns))
    c3.metric(L("Cellules vides", "Empty cells"), f"{prof['empty'].mean():.1%}")
    st.dataframe(prof, hide_index=True, width="stretch",
                 column_config={"column": L("Colonne", "Column"), "empty": st.column_config.NumberColumn(L("Vide", "Empty"), format="percent"),
                                "distinct": L("Distinctes", "Distinct"), "examples": L("Exemples", "Examples")})

    # ---- 3. mapping + translation (human-editable)
    ui.section(L("3 · Correspondance proposée et traduction", "3 · Proposed mapping and translation"))
    key = f"map_{name}_{len(df)}"
    if key not in st.session_state:
        proposal = propose_mapping(df)
        st.session_state[key] = {t: v[0] for t, v in proposal.items()}
        st.session_state[key + "_conf"] = {t: v[1] for t, v in proposal.items()}
    conf = st.session_state.get(key + "_conf", {})
    left, right = st.columns([3, 1])
    with right:
        if st.button(L("Affiner avec l'IA (1 appel)", "Refine with AI (1 call)"), width="stretch", icon=":material/auto_awesome:"):
            try:
                m, tok = ai_refine(df, c.lang)
                if m is None:
                    st.warning(tok)
                else:
                    st.session_state[key].update({k: v for k, v in m.items() if v})
                    st.success(L(f"Proposition IA appliquée · {tok} tokens", f"AI proposal applied · {tok} tokens"))
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {str(exc)[:160]}")
        st.caption(L("Par défaut : règles (0 token). L'IA ne voit que les noms de colonnes et des statistiques, jamais les lignes.",
                     "Default: rules (0 tokens). The AI only sees column names and statistics, never the rows."))
    with left:
        opts = [None] + list(df.columns)
        cols = st.columns(3)
        for i, (tgt, (req, kind, _)) in enumerate(TARGETS.items()):
            cur = st.session_state[key].get(tgt)
            lab = f"{tgt}{' *' if req else ''}" + (f" · {conf[tgt]:.0%}" if tgt in conf and conf.get(tgt) and cur else "")
            st.session_state[key][tgt] = cols[i % 3].selectbox(lab, opts, index=opts.index(cur) if cur in opts else 0, key=f"{key}_{tgt}",
                                                               format_func=lambda o: "—" if o is None else o)
    mapping = {t: s for t, s in st.session_state[key].items() if s}
    rates = dict(DEFAULT_RATES)
    if mapping.get("currency"):
        found = sorted(df[mapping["currency"]].dropna().astype(str).str.upper().unique())
        rc = st.columns(min(len(found), 4) or 1)
        for i, ccy in enumerate(found[:4]):
            rates[ccy] = rc[i].number_input(L(f"Taux {ccy} → TND", f"Rate {ccy} → TND"), 0.0, 100.0, float(DEFAULT_RATES.get(ccy, 1.0)),
                                            0.01, key=f"rate_{ccy}", help=L("Indicatif, à confirmer par la trésorerie", "Indicative, confirm with treasury"))
    canon, report = translate(df, mapping, rates)

    # ---- 4. accuracy
    ui.section(L("4 · Précision de la traduction et compatibilité avec nos données", "4 · Translation accuracy and fit with our data"))
    acc = accuracy(canon, report, reference(mode))
    color = {"green": ui.GREEN, "amber": getattr(ui, "AMBER", "#F59E0B"), "red": ui.RED}[acc["gate"]]
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        ui.kpi(L("Champs obligatoires couverts", "Required fields covered"), f"{acc['coverage']:.0%}",
               (L("manquants : ", "missing: ") + ", ".join(acc["missing_required"])) if acc["missing_required"] else L("tous présents", "all present"))
    with g2:
        ui.kpi(L("Valeurs traduites valides", "Valid translated values"), f"{acc['validity']:.1%}", L("moyenne des champs obligatoires", "mean over required fields"))
    with g3:
        ui.kpi(L("Écart de distribution (PSI)", "Distribution drift (PSI)"),
               f"{max(acc.get('psi_channel', 0), acc.get('psi_amount', 0)):.2f}",
               L(f"canaux {acc.get('psi_channel', 0):.2f} · montants {acc.get('psi_amount', 0):.2f} · &lt; 0,10 stable, &gt; 0,25 fort",
                 f"channels {acc.get('psi_channel', 0):.2f} · amounts {acc.get('psi_amount', 0):.2f} · &lt; 0.10 stable, &gt; 0.25 strong"))
    with g4:
        st.markdown(f'<div class="kpi" style="border-left:4px solid {color}"><div class="lab">{L("Verdict", "Verdict")}</div>'
                    f'<div class="val" style="color:{color}">{ {"green": L("Prêt", "Ready"), "amber": L("À revoir", "Review"), "red": L("Bloqué", "Blocked")}[acc["gate"]] }</div>'
                    f'<div class="cmp">{L("≥ 95 % valides, PSI &lt; 0,2, champs obligatoires", "≥ 95% valid, PSI &lt; 0.2, required fields")}</div></div>',
                    unsafe_allow_html=True)
    rep = pd.DataFrame([{"field": t, "source": r["source"], "validity": r["validity"], "valid": r["valid"], "present": r["present"],
                         "untranslated": ", ".join(f"{k} ({v})" for k, v in r["untranslated"].items()) or "—",
                         "confidence": conf.get(t)} for t, r in report.items()])
    st.dataframe(rep, hide_index=True, width="stretch",
                 column_config={"field": L("Champ cible", "Target field"), "source": L("Colonne source", "Source column"),
                                "validity": st.column_config.ProgressColumn(L("Valides", "Valid"), min_value=0, max_value=1, format="percent"),
                                "untranslated": L("Valeurs non traduites", "Untranslated values"),
                                "confidence": st.column_config.NumberColumn(L("Confiance proposition", "Proposal confidence"), format="percent")})
    if "amount_tnd" in canon:
        st.caption(L(f"Rapprochement : {len(df)} lignes en entrée = {len(canon)} en sortie · total converti "
                     f"{canon.amount_tnd.sum():,.0f} TND".replace(",", " "),
                     f"Reconciliation: {len(df)} rows in = {len(canon)} out · converted total TND {canon.amount_tnd.sum():,.0f}"))
    if "fraud_rate" in acc:
        st.caption(L(f"Labels présents : taux de fraude {acc['fraud_rate']:.2%}. Après approbation, la performance du modèle sur cette "
                     "source se mesure dans Fabric (rescoring du notebook 02) avant toute mise en production.",
                     f"Labels present: fraud rate {acc['fraud_rate']:.2%}. After approval, model performance on this source is measured "
                     "in Fabric (notebook 02 rescoring) before any production use."))
    with st.expander(L("Aperçu des données traduites (10 lignes)", "Preview of translated data (10 rows)")):
        st.dataframe(canon.head(10), hide_index=True, width="stretch")

    # ---- 5. approval
    ui.section(L("5 · Approbation (obligatoire)", "5 · Approval (required)"))
    who = st.text_input(L("Approuvé par (nom, rôle)", "Approved by (name, role)"), key="onboard_who")
    ok = st.checkbox(L("J'ai vérifié la correspondance, les taux de change et les valeurs non traduites.",
                       "I have checked the mapping, the exchange rates and the untranslated values."), key="onboard_ok")
    a1, a2 = st.columns(2)
    if a1.button(L("Approuver et intégrer", "Approve and onboard"), type="primary", width="stretch",
                 disabled=not (ok and who.strip() and acc["gate"] != "red")):
        version = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = STAGING / f"{_n(name)}_{version}"
        folder.mkdir(parents=True, exist_ok=True)
        contract = {"source": name, "version": version, "approved_by": who.strip(), "approved_at": datetime.now().isoformat(timespec="seconds"),
                    "mapping": mapping, "rates_to_tnd": rates, "accuracy": {k: v for k, v in acc.items() if k != "missing_required"},
                    "rows": int(len(canon))}
        (folder / "data_contract.json").write_text(json.dumps(contract, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        canon.to_parquet(folder / "translated.parquet", index=False)
        _log_event({"ts": contract["approved_at"], "source": name, "version": version, "decision": "APPROVED", "by": who.strip(),
                    "rows": len(canon), "validity": round(acc["validity"], 4), "gate": acc["gate"]})
        st.success(L(f"Approuvé. Contrat de données v{version} et données traduites enregistrés dans {folder.name}/ "
                     "(étape suivante : dépôt dans OneLake → bronze → silver par le pipeline Fabric).",
                     f"Approved. Data contract v{version} and translated data saved in {folder.name}/ "
                     "(next step: drop to OneLake → bronze → silver by the Fabric pipeline)."))
    if a2.button(L("Rejeter", "Reject"), width="stretch", disabled=not who.strip()):
        _log_event({"ts": datetime.now().isoformat(timespec="seconds"), "source": name, "version": "", "decision": "REJECTED",
                    "by": who.strip(), "rows": len(df), "validity": round(acc["validity"], 4), "gate": acc["gate"]})
        st.warning(L("Rejet enregistré dans le journal.", "Rejection logged."))
    if acc["gate"] == "red":
        st.caption(L("Approbation impossible tant que le verdict est « Bloqué ».", "Approval disabled while the verdict is \"Blocked\"."))
    if LOG.exists():
        st.dataframe(pd.read_csv(LOG).iloc[::-1], hide_index=True, width="stretch")
