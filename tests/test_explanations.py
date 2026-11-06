"""Explanations a banker can trust (brief §15 "Explication et copilote", incl. legitimate cases): computed, never left to the LLM."""
import data_access as da
import copilot
import tools


def test_habits_answer_is_computed_not_guessed():
    fraud = tools.compare_to_habits("TX01555470")["lecture_habitudes"]
    assert fraud["conforme_aux_habitudes"] == "Non" and len(fraud["ecarts_nets"]) >= 2
    legit = tools.habits_reading("TX01575959", "fr")
    assert legit["conforme_aux_habitudes"] == "En partie" and len(legit["ecarts_nets"]) == 1
    assert legit["elements_conformes"][0].startswith("paiement par puce")          # strongest reassurance first (shown on the page)
    assert tools.habits_reading("TX01575959", "en")["conforme_aux_habitudes"] == "Partly"


def test_risky_looking_factors_are_never_called_reassuring():
    t = tools.get_transaction("TX01575959")
    calm = [f["facteur"] for f in t["facteurs_modele_rassurants"]]
    assert not any(f.startswith("Montant de l'opération") or f.startswith("Montant / plafond") for f in calm)
    assert {f["facteur"].split(" (")[0] for f in t["facteurs_modele_non_determinants"]} == \
        {"Montant de l'opération", "Montant / plafond journalier de la carte"}
    e = da.explanations()
    for tid in e[(e.source == "model_against") & e.feature.isin(tools.COUNTER_INTUITIVE)].transaction_id.unique()[:150]:
        for f in tools.get_transaction(tid)["facteurs_modele_rassurants"]:
            if f["facteur"] == "Montant de l'opération" and "valeur_habituelle" in f:
                assert f["valeur_observee"] <= f["valeur_habituelle"], tid
            assert not (f["facteur"] == "Piste magnétique" and f.get("valeur_observee") == 1), tid


def test_sequence_names_the_new_merchant():
    ops = tools.compare_to_habits("TX01575959")["sequence_carte_24h"]["operations"]
    assert "commerçant nouveau" in ops[0] and "commerçant nouveau" not in ops[-1]   # the new one is yesterday's, not the alert's


def test_answer_polish_removes_field_names():
    en = copilot.polish("Amount (part_operations_passees_inferieures 0.997), entry_mode CHIP, SANS_CONTACT. VALIDATE (confidence: moyenne)", "en")
    assert "_" not in en.replace("SANS_CONTACT", "") and "confidence: medium" in en and "SANS_CONTACT" in en
    assert copilot.polish("heure 04:49 vs part_nuit 3.9%", "fr") == "heure 04:49 vs part des opérations de nuit 3.9%"
