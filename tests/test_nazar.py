"""Nazar, the work agent: instruction -> action, 0 tokens, decisions only after the analyst confirms."""
import pytest

import nazar
import tools

CASES = [
    ("mes tâches", None, "brief"), ("my tasks", None, "brief"), ("suivante", None, "next"), ("next", None, "next"),
    ("top 10 d'hier", None, "list"), ("alertes à bloquer", "TX01555470", "list"), ("les 5 alertes à vérifier", None, "list"),
    ("show me the 10 riskiest alerts from yesterday", None, "list"),
    ("ouvre TX01555470", None, "open"), ("procès TX01555470", None, "open"), ("reconstitution TX01585580", None, "open"),
    ("C000488", None, "customer"), ("qui est C000488 ?", None, "customer"),
    ("bloque TX01555470", None, "decide"), ("valide celle-ci", "TX01575959", "decide"), ("escalate this one", "TX01585580", "decide"),
    ("bloquer", "TX01555470", "unknown"),                      # a bare verb never decides on its own
    ("client retraité de Sfax de plus de 70 ans avec des alertes", None, "people"), ("trouve les médecins de Tunis", None, "people"),
    ("vérifie le journal", None, "audit"), ("journal", None, "go"), ("kpi", None, "kpi"), ("combien de fausses alertes ?", None, "kpi"),
    ("impact", None, "go"), ("réseau de compromission", None, "go"), ("english", None, "lang"), ("aide", None, "help"),
    ("pourquoi ce client a 3 échecs ?", "TX01555470", "ask"), ("raconte une blague", None, "unknown"),
]


@pytest.mark.parametrize("text,current,kind", CASES)
def test_parse(text, current, kind):
    assert nazar.parse(text, current)["kind"] == kind


def test_lists_use_the_demo_calendar_and_filters():
    a = nazar.parse("top 10 d'hier")
    assert (a["n"], a["day"]) == (10, "2026-09-29")
    out = nazar.run(nazar.parse("alertes à bloquer"))
    assert out["rows"] and all("BLOQUER" in r["label"] for r in out["rows"])


def test_decision_is_prepared_not_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "DECISIONS_FILE", tmp_path / "decisions.csv")
    out = nazar.run(nazar.parse("bloque TX01575959"))
    assert out["confirm"] == {"tid": "TX01575959", "decision": "BLOQUER", "confidence": "moyenne"}
    assert "écartez" in out["text"]                        # system says VALIDER: override is announced
    assert not (tmp_path / "decisions.csv").exists()       # nothing written until the analyst confirms


def test_unknown_ids_and_chat_are_refused():
    assert "introuvable" in nazar.run(nazar.parse("ouvre TX99999999"))["text"]
    assert "introuvable" in nazar.run(nazar.parse("C999999"))["text"]
    assert "agent de travail" in nazar.run(nazar.parse("raconte une blague"))["text"]


def test_briefing_counts_work_items():
    b = nazar.briefing("fr")
    assert "Briefing" in b["text"] and len(b["rows"]) == 3 and b["count"] >= 0
