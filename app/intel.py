"""Continuous fraud intelligence: an alert is a case that lives on (brief §1) — rejected does not mean forgotten.

- `stream(tid, as_of)`: the event stream around a case, from the operations of the same card / customer, the app events, the model's
  alerts and the analysts' decisions — only what is known at `as_of` (time travel, never the future).
- `triggers(tid, as_of)`: what happened AFTER the alert that should reopen it (new attempts on the card, new declines, failed logins,
  new beneficiary / device / country, new alerts, amount escalation). Rules are explicit and documented.
- case file `data/cases.jsonl`: append-only record of every case event (opened, reactivated, agents' debate, Judge's assessment,
  the employee's action and rationale). Knowledge status of a case: "suspected" from the AI; "confirmed fraud" / "confirmed
  legitimate" ONLY from an employee action after contacting the customer, or from the bank's fraud report — never from the AI.
"""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import data_access as da

CASES = da.DATA / "cases.jsonl"
HORIZON = timedelta(hours=72)
LOOKBACK = timedelta(hours=24)
KIND_LABEL = {
    "alert": ("Alerte du modèle", "Model alert"), "tx_ok": ("Opération approuvée", "Approved operation"),
    "tx_declined": ("Opération refusée", "Declined operation"), "login_fail": ("Connexion échouée", "Failed login"),
    "login": ("Connexion", "Login"), "benef": ("Bénéficiaire ajouté", "Beneficiary added"), "device": ("Appareil ajouté", "Device added"),
    "pwd": ("Mot de passe réinitialisé", "Password reset"), "phone": ("Numéro de téléphone changé", "Phone number changed"),
    "decision": ("Décision analyste", "Analyst decision"), "case": ("Dossier", "Case"),
}
ACTIONS = {"accept": ("Accepter la recommandation", "Accept the recommendation"), "reject": ("Rejeter la recommandation", "Reject the recommendation"),
           "more": ("Demander une enquête complémentaire", "Request more investigation"), "context": ("Ajouter du contexte", "Add context"),
           "escalate": ("Escalader", "Escalate"), "confirm_fraud": ("Fraude confirmée par le client", "Fraud confirmed by the customer"),
           "confirm_legit": ("Opération reconnue par le client", "Operation recognised by the customer")}
KNOWLEDGE = {"confirm_fraud": "confirmed_fraud", "confirm_legit": "confirmed_legit"}


def _alert_row(tid):
    q = da.queue()
    r = q[q.transaction_id == tid]
    return r.iloc[0] if len(r) else None


def stream(tid, as_of=None):
    """All events around the case known at `as_of` (default: the alert time + horizon). Columns: ts, kind, label, detail, risky, phase."""
    a = _alert_row(tid)
    if a is None:
        return pd.DataFrame()
    t0 = pd.Timestamp(a.timestamp)
    as_of = pd.Timestamp(as_of) if as_of is not None else t0 + HORIZON
    rows = []
    h = da.customer_tx(a.customer_id).copy()
    h["timestamp"] = pd.to_datetime(h.timestamp)
    h = h[(h.timestamp >= t0 - LOOKBACK) & (h.timestamp <= min(as_of, t0 + HORIZON))]
    alerts = da.queue().set_index("transaction_id")
    for r in h.itertuples():
        same_card = r.card_id == a.card_id
        is_alert = r.transaction_id in alerts.index and alerts.loc[r.transaction_id, "risk_level"] != "FAIBLE"
        declined = str(r.status) == "REFUSEE"
        kind = "alert" if r.transaction_id == tid else ("tx_declined" if declined else "tx_ok")
        detail = (f"{r.transaction_type} {r.channel} {r.entry_mode} {float(r.amount_tnd):,.0f} TND · "
                  f"{r.city if isinstance(r.city, str) else 'en ligne'}{'' if str(r.country) == 'TN' else ' (' + str(r.country) + ')'}"
                  + (f" · {r.decline_reason}" if declined and isinstance(r.decline_reason, str) else "")
                  + ("" if same_card else " · autre carte")).replace(",", " ")
        rows.append({"ts": r.timestamp, "kind": kind, "detail": detail, "tid": r.transaction_id, "same_card": bool(same_card),
                     "model_alert": bool(is_alert), "amount": float(r.amount_tnd), "country": str(r.country), "status": str(r.status),
                     "risky": declined or is_alert or kind == "alert"})
    ev = da.events(a.customer_id)
    if ev is not None and len(ev):
        e = ev.copy()
        e["timestamp"] = pd.to_datetime(e.timestamp)
        e = e[(e.timestamp >= t0 - LOOKBACK) & (e.timestamp <= min(as_of, t0 + HORIZON))]
        kinds = {"AJOUT_BENEFICIAIRE": "benef", "AJOUT_APPAREIL": "device", "REINITIALISATION_MOT_DE_PASSE": "pwd",
                 "MODIFICATION_NUMERO_TELEPHONE": "phone"}
        for r in e.itertuples():
            k = "login_fail" if (r.event_type == "CONNEXION" and r.status == "ECHEC") else kinds.get(r.event_type, "login")
            if k == "login":
                continue                                   # successful logins are context, not events worth a line
            rows.append({"ts": r.timestamp, "kind": k, "detail": f"{r.channel} · IP {r.ip_country} · {r.auth_method or ''}".strip(" ·"),
                         "tid": None, "same_card": None, "model_alert": False, "amount": None, "country": str(r.ip_country),
                         "status": str(r.status), "risky": k != "login"})
    import tools
    d = tools.decisions()
    if len(d):
        d = d[d.transaction_id.isin([x["tid"] for x in rows if x["tid"]])].copy()
        d["ts"] = pd.to_datetime(d.decided_at, errors="coerce")
        for r in d.itertuples():
            rows.append({"ts": r.ts, "kind": "decision", "detail": f"{r.decision} ({r.analyst}) sur {r.transaction_id}", "tid": r.transaction_id,
                         "same_card": None, "model_alert": False, "amount": None, "country": None, "status": None, "risky": False})
    s = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    s["phase"] = ["avant" if t < t0 else "alerte" if k == "alert" else "après" for t, k in zip(s.ts, s.kind)]
    return s


def triggers(tid, as_of=None, lang="fr"):
    """Reactivation rules on what happened after the alert, up to as_of. Returns a list of {ts, code, text, weight}."""
    a = _alert_row(tid)
    s = stream(tid, as_of)
    if a is None or s.empty:
        return []
    t0 = pd.Timestamp(a.timestamp)
    after = s[(s.ts > t0) & (s.phase == "après")]
    en = lang == "en"
    out = []

    def add(rows, code, fr, en_txt, weight):
        if len(rows):
            out.append({"ts": rows.ts.min(), "code": code, "text": en_txt if en else fr, "weight": weight, "n": int(len(rows))})
    card = after[after.same_card == True]                                                  # noqa: E712
    add(card, "card_reused", f"{len(card)} nouvelle(s) opération(s) sur la même carte", f"{len(card)} new operation(s) on the same card", 1)
    add(card[card.kind == "tx_declined"], "declines", f"{int((card.kind == 'tx_declined').sum())} nouveau(x) refus sur la carte",
        f"{int((card.kind == 'tx_declined').sum())} new decline(s) on the card", 2)
    add(after[after.model_alert], "new_alerts", f"{int(after.model_alert.sum())} nouvelle(s) alerte(s) du modèle sur ce client",
        f"{int(after.model_alert.sum())} new model alert(s) for this customer", 2)
    add(after[after.kind == "login_fail"], "login_fail", f"{int((after.kind == 'login_fail').sum())} connexion(s) échouée(s)",
        f"{int((after.kind == 'login_fail').sum())} failed login(s)", 2)
    for k, fr, e_ in [("benef", "nouveau bénéficiaire", "new beneficiary"), ("device", "nouvel appareil", "new device"),
                      ("pwd", "mot de passe réinitialisé", "password reset"), ("phone", "numéro de téléphone changé", "phone number changed")]:
        add(after[after.kind == k], k, fr, e_, 2)
    if str(a.country) != "TN":
        back = card[(card.country == "TN") & card.kind.isin(["tx_ok", "tx_declined"])]
        add(back, "two_places", "la carte est aussi utilisée en Tunisie : deux lieux à la fois", "the card is also used in Tunisia: two places at once", 3)
    big = card[card.amount.fillna(0) > 2 * float(a.amount_tnd)]
    add(big, "escalation", "montants en hausse après l'alerte (> 2× le montant alerté)", "amounts rising after the alert (> 2× the alerted amount)", 2)
    return sorted(out, key=lambda x: x["ts"])


def reactivated(trigs):
    return sum(t["weight"] for t in trigs) >= 3


# ---------------------------------------------------------------- case file (append-only)
def _case_id(tid):
    return "CASE-" + hashlib.sha1(tid.encode()).hexdigest()[:8].upper()


def log_case(tid, event, payload, analyst=None):
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "case_id": _case_id(tid), "transaction_id": tid, "event": event,
           "analyst": analyst, **payload}
    with CASES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return rec


def history(tid=None):
    if not CASES.exists():
        return pd.DataFrame()
    rows = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    return df[df.transaction_id == tid] if tid is not None and len(df) else df


def knowledge_status(tid):
    """confirmed_fraud / confirmed_legit only from an employee action (after contacting the customer) or the bank's fraud report;
    otherwise 'suspected' (an AI conclusion is never knowledge)."""
    a = _alert_row(tid)
    h = history(tid)
    acts = h[h.event == "employee_action"] if len(h) else h
    for r in acts.iloc[::-1].itertuples() if len(acts) else []:
        if getattr(r, "action", None) in KNOWLEDGE:
            return KNOWLEDGE[r.action], "employee"
    if a is not None and a.period != "test" and pd.notna(a.is_fraud):
        return ("confirmed_fraud" if a.is_fraud == 1 else "confirmed_legit"), "bank_label"
    return "suspected", "ai_or_model"
