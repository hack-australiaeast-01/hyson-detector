"""Data quality (notebook 05): the rules' results hold on the committed star schema, the documented counts are right, and every
rule documented in docs/DATA_QUALITY_RULES.md is the one defined in notebooks/gen_nb05.py."""
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STAR = ROOT / "app" / "data" / "star"


@pytest.fixture(scope="module")
def tx():
    d = pd.read_parquet(STAR / "fact_transactions.parquet", columns=["transaction_id", "date_key", "client_key", "channel_key", "geo_key",
                                                                       "montant_tnd", "statut", "motif_refus", "dq_status"])
    geo = pd.read_parquet(STAR / "dim_geo.parquet", columns=["geo_key", "latitude", "ville"])
    ch = pd.read_parquet(STAR / "dim_channel.parquet", columns=["channel_key", "canal"])
    return d.merge(geo, on="geo_key", how="left").merge(ch, on="channel_key", how="left")


def test_status_counts(tx):
    """1,896,472 OK + 11,756 WARNING, and no REJECTED row ever reaches the facts (they stay in quarantine)."""
    assert tx.dq_status.value_counts().to_dict() == {"OK": 1896472, "WARNING": 11756}


def test_t04_extreme_amounts_are_kept_and_flagged(tx):
    big = tx[tx.montant_tnd > 50000]
    assert len(big) == 39 and (big.dq_status == "WARNING").all()          # kept, not capped, not deleted
    assert big.montant_tnd.max() > 150000                                  # values kept as they are (not capped at 50,000)


def test_t15_missing_location_is_kept_flagged_and_never_invented(tx):
    phys = tx.canal.isin(["TPE", "DAB"])
    no_gps = tx[phys & tx.latitude.isna()]
    assert len(no_gps) == 11717 and (no_gps.dq_status == "WARNING").all()
    assert no_gps.ville.notna().all()                                      # the city is there, only the coordinates are missing


def test_error_rules_hold_on_the_facts(tx):
    assert not tx.transaction_id.duplicated().any()                       # T01
    assert tx[["date_key", "client_key", "channel_key"]].notna().all().all()   # T02 / T07: required keys present
    assert (tx.montant_tnd > 0).all()                                      # T03
    declined = tx.statut == "REFUSEE"
    assert tx.loc[declined, "motif_refus"].notna().all() and tx.loc[~declined, "motif_refus"].isna().all()   # T12


def test_documented_rules_match_the_notebook():
    src = (ROOT / "notebooks" / "gen_nb05.py").read_text(encoding="utf-8")
    code = dict(re.findall(r'\("([TCKME]\d\d)", "(ERROR|WARNING)"', src))
    doc = (ROOT / "docs" / "DATA_QUALITY_RULES.md").read_text(encoding="utf-8")
    documented = dict(re.findall(r"^\| ([TCKME]\d\d) \| (ERROR|WARNING) \|", doc, re.M))
    assert len(code) == 36 and documented == code
    assert sum(v == "ERROR" for v in code.values()) == 21 and "36 rules (21 ERROR, 15 WARNING)" in doc
