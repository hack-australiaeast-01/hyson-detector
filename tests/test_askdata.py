"""Ask the data (natural language → SQL on the star schema): the guard, the offline translator and the local engine. 0 token."""
import pytest

import askdata

ATTACKS = ["DELETE FROM fact_transactions", "SELECT 1; DROP TABLE dim_geo", "SELECT * FROM read_parquet('C:/x.parquet')",
           "SELECT * FROM 'data/decisions.csv'", "SELECT getenv('AZURE_OPENAI_API_KEY')", "SELECT * FROM customers",
           "COPY fact_transactions TO 'x.csv'", "ATTACH 'x.db' AS y", "SELECT * FROM main.fact_transactions", "INSTALL httpfs",
           "UPDATE dim_client SET segment = 'Premium'", "CREATE TABLE t AS SELECT 1", "PRAGMA database_list"]


@pytest.mark.parametrize("sql", ATTACKS)
def test_guard_rejects_anything_but_one_select_on_the_star_schema(sql):
    with pytest.raises(askdata.Rejected):
        askdata.guard(sql)


def test_guard_caps_rows_and_keeps_ctes():
    assert askdata.guard("SELECT transaction_id, montant_tnd FROM fact_transactions").endswith("LIMIT 1000")
    assert "LIMIT 5" in askdata.guard("WITH x AS (SELECT ville, region FROM dim_geo) SELECT ville FROM x LIMIT 5")
    with pytest.raises(askdata.Rejected):                      # SELECT * would expose client / card keys
        askdata.guard("SELECT * FROM fact_transactions")


def test_engine_cannot_read_files_even_without_the_guard():
    if not askdata.star_ready():
        pytest.skip("star snapshot missing")
    con = askdata._duck()
    with pytest.raises(Exception):
        con.execute("SELECT * FROM read_csv('data/decisions.csv')").fetchall()


def test_how_many_in_beja_offline_matches_the_raw_data():
    if not askdata.star_ready():
        pytest.skip("star snapshot missing")
    r = askdata.ask("show how many transactions been have been hapinning in béja", "en")
    assert r["intent"] == "data" and r["df"].iat[0, 0] == 39156          # = raw profile of transactions_train/_test (city = Beja)
    assert "Beja" in r["understood"]


def test_offline_translator_shapes():
    p = askdata.rule_translate("montant total par mois des opérations en ligne en 2026")
    assert "d.annee_mois" in p["sql"] and "c.canal = 'EN_LIGNE'" in p["sql"] and "d.annee = 2026" in p["sql"] and p["chart"]["type"] == "line"
    p = askdata.rule_translate("clients de Sfax retraités : montant moyen par tranche d'age")
    assert "gouvernorat_residence = 'Sfax'" in p["sql"] and "segment = 'Retraite'" in p["sql"] and "canal" not in p["sql"]   # retraités ≠ retrait
    assert askdata.rule_translate("Pourquoi TX01555470 est suspecte ?")["intent"] == "alert"


def test_fraud_labels_never_exist_for_the_test_period():
    if not askdata.star_ready():
        pytest.skip("star snapshot missing")
    df, _ = askdata.run_sql("SELECT COUNT(*) n FROM fact_transactions f JOIN dim_date d ON d.date_key = f.date_key "
                            "WHERE d.periode_modele = 'flux_test' AND f.fraude_signalee IS NOT NULL")
    assert int(df.n[0]) == 0


def test_question_language():
    assert askdata.question_lang("which customer segment has the highest decline rate?") == "en"
    assert askdata.question_lang("combien de clients premium à Sousse ?") == "fr"


def test_offline_refuses_individual_requests_and_admits_when_it_does_not_understand():
    assert askdata.rule_translate("liste des clients avec leur revenu")["intent"] == "personal"
    assert askdata.rule_translate("quel est le revenu de C000308")["intent"] == "personal"
    assert askdata.rule_translate("bonjour ça va")["intent"] == "unclear"
