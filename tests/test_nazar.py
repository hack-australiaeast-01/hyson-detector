"""Nazar, the work agent: commands -> actions (0 tokens), small talk offline, free chat on aggregates only;
decisions are only ever prepared and saved after the analyst confirms."""
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
    ("bloquer", "TX01555470", "chat"),                         # a bare verb never decides on its own
    ("client retraité de Sfax de plus de 70 ans avec des alertes", None, "people"), ("trouve les médecins de Tunis", None, "people"),
    ("vérifie le journal", None, "audit"), ("journal", None, "go"), ("kpi", None, "kpi"), ("combien de fausses alertes ?", None, "kpi"),
    ("impact", None, "go"), ("réseau de compromission", None, "go"), ("english", None, "lang"), ("aide", None, "help"),
    ("pourquoi ce client a 3 échecs ?", "TX01555470", "ask"), ("raconte une blague", None, "smalltalk"),
    ("salut", None, "smalltalk"), ("merci", None, "smalltalk"), ("c'est quoi un faux positif ?", None, "chat"),
    ("bloque tout", "TX01555470", "chat"), ("block them all", None, "chat"),
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


def test_unknown_ids_are_refused():
    assert "introuvable" in nazar.run(nazar.parse("ouvre TX99999999"))["text"]
    assert "introuvable" in nazar.run(nazar.parse("C999999"))["text"]


def test_small_talk_and_chat_never_decide(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "DECISIONS_FILE", tmp_path / "decisions.csv")
    joke = nazar.run(nazar.parse("raconte une blague"))
    assert joke["text"] and not joke.get("tokens") and "confirm" not in joke
    off = nazar.run(nazar.parse("bloque tout"), current_tx="TX01555470")   # offline in tests: no LLM, no decision
    assert "aide" in off["text"] and not off.get("tokens") and "confirm" not in off
    assert not (tmp_path / "decisions.csv").exists()


def test_chat_facts_are_aggregates_only():
    import re
    facts = nazar._chat_facts("fr", "TX01555470")
    assert len(facts) < 2500 and not re.search(r"\bC\d{6}\b", facts)   # no customer IDs, no raw rows


def test_briefing_counts_work_items():
    b = nazar.briefing("fr")
    assert "Briefing" in b["text"] and len(b["rows"]) == 3 and b["count"] >= 0


def test_gpt_brain_never_sees_bank_answers(monkeypatch):
    """The plain GPT-5 mini mode gets no bank facts and no earlier Nazar answers (they hold IDs and amounts)."""
    import types
    import copilot
    sent = []
    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda **kw: (
        sent.append(kw["messages"]) or types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))],
                                                            usage=types.SimpleNamespace(total_tokens=1))))))
    monkeypatch.setattr(copilot, "configured", lambda: True)
    monkeypatch.setattr(copilot, "_client", lambda: fake)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test")
    history = [{"cmd": "top 3", "out": {"text": "TX01555470 · 814 TND · C000488", "brain": "nazar"}},
               {"cmd": "hello", "out": {"text": "Hi there", "brain": "gpt"}}]
    nazar.chat("explain phishing", "en", "TX01555470", history, brain="gpt")
    flat = " ".join(m["content"] for m in sent[-1])
    assert "TX01555470" not in flat and "C000488" not in flat and "FAITS" not in flat and "Hi there" in flat
    nazar.chat("et la file ?", "fr", "TX01555470", history, brain="nazar")
    assert "FAITS" in " ".join(m["content"] for m in sent[-1])          # Nazar's own brain keeps the aggregates
