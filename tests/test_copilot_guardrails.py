"""Copilot guardrails (brief §9.1, §9.8) in offline mode: deterministic, no paid call."""
import copilot


def test_unknown_id_is_never_invented():
    r = copilot.ask("Pourquoi TX99999999 est-elle suspecte ?", None, lang="fr")
    assert "introuvable" in r["answer"]
    assert r["tokens"]["total"] == 0
    assert "BLOQUER" not in r["answer"] and "ESCALADER" not in r["answer"]


def test_offline_answer_repeats_the_system_decision():
    r = copilot.ask("Pourquoi cette transaction est-elle suspecte ?", "TX01555470", lang="fr")
    assert "BLOQUER" in r["answer"]
    fp = copilot.ask("Pourquoi cette transaction est-elle suspecte ?", "TX01575959", lang="fr")
    assert "VALIDER" in fp["answer"]


def test_intent_routing():
    assert copilot.detect_intent("Montre-moi les 10 transactions les plus risquées d'hier.", None) == "queue"
    assert copilot.detect_intent("Résume pourquoi cette alerte doit être priorisée.", "TX01585580") == "priority"
    assert copilot.detect_intent("Rédige le résumé d'investigation pour le dossier.", "TX01585580") == "summary"
    assert copilot.detect_intent("Combien d'alertes inutiles évites-tu par rapport au moteur de règles actuel ?", None) == "kpi"
    assert copilot.detect_intent("le client retraité de Sfax de plus de 70 ans avec des alertes", None) == "person"


def test_yesterday_means_the_demo_calendar():
    assert copilot._relative_day("les plus risquées d'hier") == "2026-09-29"
