"""Data, model and decision-rule guarantees the jury can check (brief §7, §8, §9, §14, §16)."""
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

import data_access as da
import tools

ROOT = Path(__file__).resolve().parents[1]


def test_no_test_labels_anywhere():
    q = da.queue()
    assert q[q.period == "test"].is_fraud.isna().all()
    assert q[q.period == "test"].fraud_scenario.isna().all()


def test_alert_budget_is_one_percent_per_period():
    q = da.queue()
    assert ((q.period == "test") & (q.risk_level != "FAIBLE")).sum() == 1876      # 1 % of 187,628
    assert ((q.period == "valid") & (q.risk_level != "FAIBLE")).sum() == 1779     # 1 % of 177,953


def test_kpis_match_the_documented_numbers():
    k = tools.get_kpis()
    rules, top = k["moteur_regles_actuel"], k["modele_top_1pct"]
    assert (rules["alertes"], rules["fraudes_detectees"], rules["fausses_alertes"]) == (3338, 117, 3221)
    assert (top["alertes"], top["fraudes_detectees"], top["fausses_alertes"]) == (1779, 718, 1061)
    assert "2 160 fausses alertes évitées" in k["comparaison_top_1pct_vs_moteur"]


def test_decision_rule_bands():
    two = [{"facteur": "a", "contribution": 1.2}, {"facteur": "b", "contribution": 0.8}]
    top = tools.recommend("ELEVE", 0.999, two, [])
    assert (top["decision"], top["confiance"]) == ("BLOQUER", "élevée")
    assert tools.recommend("ELEVE", 0.995, two, [])["confiance"] == "moyenne"
    assert tools.recommend("ELEVE", 0.999, two[:1], [])["decision"] == "ESCALADER"      # one signal only
    assert tools.recommend("MOYEN", 0.995, two, [])["decision"] == "ESCALADER"
    assert tools.recommend("FAIBLE", 0.1, [], [])["decision"] == "VALIDER"


def test_measured_fraud_rate_is_monotone_and_calibrated():
    q = da.queue()
    v = q[(q.period == "valid") & (q.risk_level != "FAIBLE")]
    rates = tools.measured_fraud_rate(np.sort(v.score_model.values))
    assert np.all(np.diff(rates) >= -1e-12)
    assert abs(tools.measured_fraud_rate(v.score_model).sum() - v.is_fraud.sum()) <= 1   # 718 expected = 718 real


def test_habits_use_the_past_only():
    r = tools.compare_to_habits("TX01555470")
    ts = pd.Timestamp(r["transaction"]["timestamp"])
    h = da.customer_tx("C000488")
    assert r["historique_avant"]["nb_operations"] == int((h.timestamp < ts).sum()) == 409
    assert r["ecarts"]["montant_moyen"] == 189.305


def test_related_cases_count_only_frauds_reported_before():
    r = tools.find_related_cases("TX01589761")
    atm = next(p for p in r["points_communs"] if p["identifiant"] == "M02076")
    assert atm["cartes_fraudees_deja_signalees"] >= 1
    assert "AVANT" in r["regle"]


def test_person_search_uses_approved_filters_only():
    import person_search
    crit = person_search.parse("le client retraité de Sfax de plus de 70 ans avec des alertes")
    assert crit == {"city": "Sfax", "segment": "Retraite", "age_min": 71, "with_alerts": True}   # "plus de 70" = 71+
    r = tools.run_tool("find_customers", crit)
    assert r["nb_clients_correspondants"] == 14
    allowed = {"customer_id", "age", "segment", "occupation", "ville", "kyc", "revenu_mensuel_tnd", "client_digital",
               "nb_alertes", "score_max", "alerte_la_plus_risquee"}
    assert all(set(c) <= allowed for c in r["clients"])


def test_submission_file_format():
    s = pd.read_csv(ROOT / "submission" / "submission.csv")
    assert list(s.columns) == ["transaction_id", "fraud_score", "is_alert"]
    assert len(s) == 187628 and s.transaction_id.is_unique and not s.isna().any().any()
    assert s.fraud_score.between(0, 1).all() and int(s.is_alert.sum()) == 1876


def test_no_secret_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    key = re.compile(r"(AZURE_OPENAI_API_KEY|api[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9]{24,}", re.I)
    leaks = [f for f in files if f.endswith((".py", ".md", ".toml", ".json", ".yml", ".yaml", ".txt", ".example", ".ipynb"))
             and key.search((ROOT / f).read_text(encoding="utf-8", errors="ignore"))]
    assert leaks == []
