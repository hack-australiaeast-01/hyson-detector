"""Audit trail: who decided, what the system recommended at that moment, which model / prompt, and tamper evidence."""
import csv

import pandas as pd
import pytest

import tools


@pytest.fixture()
def journal(tmp_path, monkeypatch):
    path = tmp_path / "decisions.csv"
    monkeypatch.setattr(tools, "DECISIONS_FILE", path)
    return path


def test_decision_stores_who_and_what_the_system_said(journal):
    r = tools.record_decision("TX01555470", "BLOQUER", "élevée", "test", analyst="a.ben.salah", source="interface", duration_s=12.3)
    assert r["enregistre"] and r["recommandation_systeme"] == "BLOQUER"
    d = tools.decisions().iloc[-1]
    assert d.analyst == "a.ben.salah" and d.system_decision == "BLOQUER" and d.system_confidence == "élevée"
    assert d.model_version == tools.MODEL_VERSION and d.prompt_version and len(d.row_hash) == 64


def test_override_of_the_recommendation_is_visible(journal):
    tools.record_decision("TX01575959", "BLOQUER", analyst="a1")          # system says VALIDER for the avoided false positive
    d = tools.decisions().iloc[-1]
    assert (d.system_decision, d.decision) == ("VALIDER", "BLOQUER")


def test_chain_detects_an_edited_past_row(journal):
    for tid, dec in [("TX01555470", "BLOQUER"), ("TX01585580", "ESCALADER"), ("TX01575959", "VALIDER")]:
        tools.record_decision(tid, dec, analyst="a1")
    assert tools.verify_journal() == {**tools.verify_journal(), "ok": True, "rows": 3}
    rows = list(csv.reader(journal.open(encoding="utf-8")))
    rows[1][2] = "VALIDER"                                                  # someone rewrites the first decision
    with journal.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    v = tools.verify_journal()
    assert not v["ok"] and v["broken_at"] == 0


def test_old_journal_is_upgraded_and_sealed(journal):
    pd.DataFrame([{"decided_at": "2026-11-05 20:37:00", "transaction_id": "TX01575959", "decision": "VALIDER",
                   "confidence": "moyenne", "comment": "", "analyst": "analyste", "source": "interface", "duration_s": ""}]
                 ).to_csv(journal, index=False)
    tools.record_decision("TX01555470", "BLOQUER", analyst="a1")
    d = tools.decisions()
    assert list(d.columns) == tools.DECISION_COLS and len(d) == 2
    assert tools.verify_journal()["ok"]


def test_decision_event_maps_to_the_right_bank_system(journal):
    tools.record_decision("TX01555470", "BLOQUER", analyst="a1")             # night web transfer (account takeover)
    tools.record_decision("TX01585580", "BLOQUER", analyst="a1")             # online card payment (card testing)
    tools.record_decision("TX01575959", "VALIDER", analyst="a1")             # avoided false positive
    d = tools.decisions()
    transfer, card, ok = (tools.decision_event(d.iloc[i].to_dict()) for i in range(3))
    assert transfer["action"] == {"system": "core_banking", "action": "HOLD_TRANSFER"}
    assert card["action"]["action"] == "BLOCK_CARD" and card["action"]["card_id"]
    assert ok["action"]["action"] == "CLOSE_ALERT_LEGITIMATE" and not ok["four_eyes_required"]
    assert transfer["audit_ref"] == d.iloc[0].row_hash
