"""Personal context (bank CEO's case) and the privacy guard of « ask the data ». Offline, 0 token."""
import json
from datetime import timedelta

import pandas as pd
import pytest

import askdata
import context
import data_access as da

CID = "C000308"      # 81, retired, Sfax


def _tx(hours, **kw):
    last = pd.to_datetime(da.customer_tx(CID).timestamp).max()
    return dict(dict(country="SA", city="Djeddah", amount_tnd=180.0, channel="TPE", entry_mode="CHIP", merchant_category="Supermarche"),
                timestamp=last + timedelta(hours=hours), **kw)


def test_yacht_in_italy_is_hardly_consistent():
    r = context.assess(_tx(5, country="IT", city="Naples", amount_tnd=48000.0, merchant_category="Nautisme"), CID)
    assert r["score"]["band"] == "incoherent"
    assert r["signals"]["montant"] == "hors_norme" and r["signals"]["absence"] in ("moins_24h", "impossible")


def test_first_stay_abroad_is_to_confirm_and_a_travel_notice_makes_it_coherent(tmp_path, monkeypatch):
    monkeypatch.setattr(context, "NOTICES", tmp_path / "notices.csv")
    r = context.assess(_tx(200), CID)
    assert r["score"]["band"] == "verifier"
    context.add_notice(CID, "SA", r["tx"]["timestamp"].date(), r["tx"]["timestamp"].date() + timedelta(days=10))
    assert context.assess(_tx(200), CID)["score"]["band"] == "coherent"


def test_feed_catches_impossible_travel_between_two_new_rows():
    last = pd.to_datetime(da.customer_tx(CID).timestamp).max()
    feed = pd.DataFrame([dict(transaction_id="N1", customer_id=CID, timestamp=last + timedelta(days=3), amount_tnd=200.0, country="SA",
                              city="Djeddah", channel="TPE", entry_mode="CHIP", merchant_category="Supermarche"),
                         dict(transaction_id="N2", customer_id=CID, timestamp=last + timedelta(days=3, hours=1), amount_tnd=9500.0, country="IT",
                              city="Milan", channel="TPE", entry_mode="MAGSTRIPE", merchant_category="Bijouterie")])
    out = context.batch(feed).set_index("transaction_id")
    assert out.loc["N2", "verdict"] == "incoherent" and "impossible" in out.loc["N2", "contre"]


def test_weights_follow_business_guardrails_and_were_tested_on_2026():
    w = json.loads(context.WEIGHTS_FILE.read_text(encoding="utf-8"))["abroad"]
    lr = w["lr"]
    assert all(v >= 0 for v in lr["montant"].values()) and lr["montant"]["hors_norme"] >= 1.09   # an amount never reassures
    for sig, good, bad in [("visite_lieu", "oui", "non"), ("sejour", "en_cours", "debut"), ("absence", "plus_7j", "impossible")]:
        assert lr[sig][good] <= lr[sig][bad]
    assert w["test"]["roc_auc"] > 0.8 and w["bands"]["coherent"]["fraud_rate"] < 0.02


def test_no_sensitive_reason_is_ever_written():
    words = " ".join(" ".join(v) for v in context.LABELS.values()).lower() + context.contact_script(
        {"place_label": "Arabie saoudite", "score": {"band": "verifier"}}).lower()
    for w in ("pèlerin", "hajj", "omra", "relig", "famille", "fille", "santé", "malad"):
        assert w not in words


@pytest.mark.parametrize("sql", ["SELECT cl.customer_id, cl.revenu_mensuel_tnd FROM dim_client cl",
                                 "SELECT cl.age, cl.revenu_mensuel_tnd FROM dim_client cl",
                                 "SELECT k.card_id, COUNT(*) n FROM fact_transactions f JOIN dim_card k ON k.card_key = f.card_key GROUP BY 1",
                                 "SELECT * FROM dim_client"])
def test_ask_the_data_never_returns_individual_customers(sql):
    with pytest.raises(askdata.Rejected):
        askdata.guard(sql)


def test_small_groups_of_customers_are_suppressed():
    s = askdata.guard("SELECT cl.profession, COUNT(*) n FROM fact_transactions f JOIN dim_client cl ON cl.client_key = f.client_key GROUP BY 1")
    assert "HAVING COUNT(DISTINCT cl.client_key) >= 5" in s
