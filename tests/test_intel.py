"""Continuous intelligence, behavioural memory (RAG), juridic judge grounding and steering facts. Offline, 0 token."""
import pandas as pd

import intel
import investigation
import memory
import steering

DEMO = "TX01631347"       # declined abroad, then the card is used in two countries


def test_case_reopens_only_with_facts_known_at_that_time():
    t0 = pd.Timestamp(intel._alert_row(DEMO).timestamp)
    assert intel.triggers(DEMO, t0) == [] and not intel.reactivated(intel.triggers(DEMO, t0))
    at6 = intel.triggers(DEMO, t0 + pd.Timedelta(hours=6))
    assert intel.reactivated(at6) and all(t["ts"] <= t0 + pd.Timedelta(hours=6) for t in at6)
    at24 = {t["code"] for t in intel.triggers(DEMO, t0 + pd.Timedelta(hours=24))}
    assert {"two_places", "new_alerts", "declines"} <= at24
    s = intel.stream(DEMO, t0 + pd.Timedelta(hours=6))
    assert s.ts.max() <= t0 + pd.Timedelta(hours=6)                     # never the future


def test_ai_conclusions_never_become_confirmed_knowledge(tmp_path, monkeypatch):
    monkeypatch.setattr(intel, "CASES", tmp_path / "cases.jsonl")
    tid = intel.da.queue().query("period == 'test'").transaction_id.iloc[0]
    intel.log_case(tid, "investigation", {"recommendation": "BLOQUER", "knowledge": "suspected (AI)"})
    assert intel.knowledge_status(tid)[0] == "suspected"
    intel.log_case(tid, "employee_action", {"action": "confirm_fraud", "rationale": "client joint : ne reconnaît pas l'opération"}, "a.b")
    assert intel.knowledge_status(tid) == ("confirmed_fraud", "employee")


def test_memory_uses_only_the_past_and_status_known_at_that_date():
    cases, stats = memory.similar(DEMO, k=8)
    t0 = pd.Timestamp(intel._alert_row(DEMO).timestamp)
    assert len(cases) == 8 and (cases.timestamp < t0).all() and DEMO not in set(cases.transaction_id)
    assert stats["confirmed_fraud"] + stats["legit"] + stats["suspected"] + stats["undetermined"] == stats["k"]
    m, _, _ = memory._load()
    late = m[(m.is_fraud == 1) & m.fraud_reported_date.notna()].iloc[0]
    assert memory.status_at(late, late.fraud_reported_date - pd.Timedelta(days=1)) == "fraud_not_yet_known"
    assert memory.status_at(late, late.fraud_reported_date + pd.Timedelta(days=1)) == "confirmed_fraud"
    assert set(cases.scenario_known.dropna()) <= set(cases[cases.status == "confirmed_fraud"].fraud_scenario)


def test_memory_summaries_hold_no_personal_identifier():
    m, _, _ = memory._load()
    s = " ".join(m.summary.sample(500, random_state=0))
    assert not any(tok in s for tok in ("C00", "CARD", "DEV", "BEN", "gender", "homme", "femme"))


def test_judge_citations_are_checked_against_the_board():
    board = [{"id": "E1"}, {"id": "E2"}]
    j = investigation.ground({"evaluation": [{"partie": "accusation", "preuves": ["E1", "E9"]}, {"partie": "défense", "preuves": ["E7"]}]}, board)
    assert j["evaluation"][0]["preuves_valides"] == ["E1"] and not j["evaluation"][1]["ancre"] and j["preuves_inexistantes"] == ["E7", "E9"]


def test_evidence_board_is_numbered_and_includes_monitoring_and_memory():
    t0 = pd.Timestamp(intel._alert_row(DEMO).timestamp)
    ev, rec, trig, cases, stats = investigation.board(DEMO, t0 + pd.Timedelta(hours=24))
    kinds = {e["kind"] for e in ev}
    assert [e["id"] for e in ev] == [f"E{i + 1}" for i in range(len(ev))]
    assert {"modèle ML", "après l'alerte", "surveillance continue", "mémoire (cas similaires)"} <= kinds and rec.get("decision")


def test_steering_drilldown_and_facts():
    l1 = steering.breakdown.__wrapped__("fraud", (), "canal")
    assert l1.cas.sum() == steering._q("SELECT SUM(fraude_signalee) n FROM fact_transactions WHERE fraude_signalee IS NOT NULL").n.iloc[0]
    l2 = steering.breakdown.__wrapped__("fraud", (("canal", "DAB"),), "type_carte")
    assert l2.cas.sum() == l1.set_index("valeur").loc["DAB", "cas"]
    ev, _ = steering.evidence("fraud", (("canal", "DAB"),))
    assert ev[0]["id"] == "K1" and any(e["cat"] == "missing" for e in ev)
    assert steering.breakdown.__wrapped__("fraud", (), "typologie").cas.sum() == l1.cas.sum()     # every reported fraud has its typology
