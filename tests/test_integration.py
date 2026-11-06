"""Universal banking integration: three simulated banks with different schemas, end to end, offline.

Atlas (SQLite, French, dd/mm/yyyy, separate fraud reports), Nordic (CSV, camelCase, epoch ms, EUR cents, auth logs, cases),
Sahel (one JSON-lines extract, ISO-3 countries, "1 234,500" amounts, numeric status, no labels).
"""
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import pandas as pd
import pytest

APP = Path(__file__).resolve().parents[1] / "app"
BANKS = APP / "samples" / "banks"
TRUTH = json.loads((BANKS / "truth.json").read_text(encoding="utf-8"))
SOURCES = {"atlas": (BANKS / "atlas.sqlite", "Banque Atlas", {"transactions": TRUTH["atlas"]["transactions"], "frauds": TRUTH["atlas"]["frauds"],
                                                               "amount_tnd": TRUTH["atlas"]["amount_tnd"]}),
           "nordic": (BANKS / "nordic", "Nordic Pay", {"transactions": TRUTH["nordic"]["transactions"], "frauds": TRUTH["nordic"]["frauds"],
                                                       "amount": TRUTH["nordic"]["amount_eur"]}),
           "sahel": (BANKS / "sahel_extract.jsonl", "Sahel Bank", {"transactions": TRUTH["sahel"]["transactions"],
                                                                   "amount_tnd": TRUTH["sahel"]["amount_tnd"]})}


@pytest.fixture(scope="module")
def banks(tmp_path_factory):
    os.environ["HYSON_TENANTS_DIR"] = str(tmp_path_factory.mktemp("tenants"))
    import tenants as tn
    out = {tid: tn.onboard_demo(tid, str(src), name, ctl) for tid, (src, name, ctl) in SOURCES.items()}
    yield out
    os.environ.pop("HYSON_TENANTS_DIR", None)


def test_discovery_finds_keys_and_foreign_keys():
    import discovery as dv
    s = dv.summary(dv.load(BANKS / "atlas.sqlite"))
    rel = {(r["from"], r["to"]) for r in s["relations"]}
    assert ("signalements_fraude.ref_operation", "operations.ref_operation") in rel
    assert ("operations.num_carte", "cartes.num_carte") in rel
    assert s["tables"]["operations"]["columns"]["date_operation"]["kind"] == "datetime"
    nordic = dv.summary(dv.load(BANKS / "nordic"))
    assert nordic["tables"]["txn"]["columns"]["createdAtMs"]["kind"] == "epoch_ms"
    assert dv.to_number(pd.Series(["1 234,500", "12,5", "7"])).tolist() == [1234.5, 12.5, 7.0]


def test_roles_and_fields_are_recognised():
    import discovery as dv
    import mapper as mp
    roles = {b: mp.propose(dv.load(src))["roles"] for b, (src, _, _) in SOURCES.items()}
    assert roles["atlas"] == {"operations": "transactions", "clients": "customers", "cartes": "cards", "signalements_fraude": "fraud_labels"}
    assert roles["nordic"] == {"txn": "transactions", "customer": "customers", "card": "cards", "merchant": "merchants",
                               "auth_log": "auth_events", "investigation": "cases"}
    assert roles["sahel"] == {"sahel_extract": "transactions"}
    m = mp.propose(dv.load(BANKS / "nordic"))
    f = m["tables"]["txn"]["fields"]
    assert f["amount"]["source"] == "amountMinor" and f["amount"]["scale"] == 0.01 and f["amount"]["confirm"]
    assert f["status"]["values"]["00"] == "APPROUVEE" and f["status"]["values"]["05"] == "REFUSEE"
    s = mp.propose(dv.load(BANKS / "sahel_extract.jsonl"))
    assert s["tables"]["sahel_extract"]["fields"]["status"]["confirm"]          # 0/1 convention is a human decision


def test_reconciliation_with_bank_control_totals(banks):
    for tid, (t, _key) in banks.items():
        v = t.validation()
        assert v["passed"], (tid, v)
        assert all(r["ok"] for r in v["reconciliation"].values()), (tid, v["reconciliation"])
        assert t.config["status"] == "active"
        assert t.verify_audit() == (True, None)


def test_sensitive_fields_never_reach_canonical_and_ids_are_pseudonymised(banks):
    for tid, (t, _) in banks.items():
        for e, df in t.canonical().items():
            assert not set(df.columns) & {"cvv", "nom_complet", "email", "gender"}, (tid, e)
        tx = t.canonical("transactions")
        assert tx["customer_id"].str.startswith("CU-").all()
        assert not tx["customer_id"].str.contains(r"^C\d{6}$").any()
    # same real customer, different banks -> unlinkable tokens
    import mapper as mp
    assert mp.pseudonymise(pd.Series(["C000110"]), "customer_id", "a")[0] != mp.pseudonymise(pd.Series(["C000110"]), "customer_id", "b")[0]
    # data minimisation: excluded columns erased from the stored raw zone after activation
    atlas = banks["atlas"][0]
    raw = pd.read_parquet(atlas.dir / "raw" / atlas.config["batch"] / "cartes.parquet")
    assert "cvv" not in raw.columns


def test_capabilities_follow_the_data(banks):
    mods = {tid: {m for m, v in t.build_info()["modules"].items() if v["active"]} for tid, (t, _) in banks.items()}
    kpis = {tid: {k for k, v in t.build_info()["kpis"].items() if v["active"]} for tid, (t, _) in banks.items()}
    assert {"authentication_anomalies", "crime_scene_replay", "institutional_rag", "alert_queue"} <= mods["nordic"]
    assert "crime_scene_replay" not in mods["atlas"] and "authentication_anomalies" not in mods["atlas"]
    assert not {"tenant_model", "deep_search", "alert_queue", "compromise_network"} & mods["sahel"]
    assert "behaviour_anomalies" in mods["sahel"]
    assert not any(k.startswith("fraud") for k in kpis["sahel"])
    assert "bank_rules_precision" in kpis["nordic"] and "bank_rules_precision" not in kpis["atlas"]


def test_model_is_time_split_and_only_used_after_approval(banks):
    t = banks["nordic"][0]
    m = t.active_model()
    assert m["status"] == "approved" and m["approved"]["by"]
    assert m["train_period"][1] <= m["test_period"][0]
    assert m["metrics"]["pr_auc"] > m["metrics"]["base_rate"] * 3                # far better than random on later months
    assert m["metrics"]["pr_auc"] > m["baseline"]["metrics"]["pr_auc"]            # and better than the bank's own rules score
    cand = t.train_model("test")                                                 # a new candidate does not replace the approved one
    assert cand["status"] == "candidate" and t.config["model"] == m["version"]
    a = t.alerts(10)
    assert (a["score_kind"] == "model").all() and a["reasons"].map(len).gt(0).all()
    assert (banks["sahel"][0].alerts(5)["score_kind"] == "behaviour").all()


def test_approval_rules(tmp_path):
    os.environ["HYSON_TENANTS_DIR"] = str(tmp_path)
    import tenants as tn
    t, _ = tn.Tenant.create("rules-test", "Rules")
    t.ingest(str(BANKS / "sahel_extract.jsonl"))
    t.discover()
    t.propose_mapping()
    t.build()
    t.validate()
    with pytest.raises(tn.TenantError, match="confirmation"):
        t.approve("Alice")                                                       # flagged decisions not confirmed yet
    with pytest.raises(tn.TenantError, match="forbidden"):
        t.update_mapping([{"op": "confirm_all"}], actor="x", role="ingest")
    t.update_mapping([{"op": "confirm_all"}], actor="Alice")
    assert t.config["status"] == "mapped"                                        # a new mapping version must be re-validated
    t.build()
    t.validate()
    with pytest.raises(tn.TenantError, match="named approver"):
        t.approve(" ")
    t.approve("Alice")
    t.update_mapping([{"op": "set", "table": "sahel_extract", "field": "city", "source": None}], actor="Bob")
    assert t.config["status"] == "mapped" and t.config["approved"] is None      # change after approval -> back to review
    with pytest.raises(tn.TenantError):
        t.activate("Bob")
    with pytest.raises(tn.TenantError, match="excluded|unknown"):
        t.update_mapping([{"op": "set", "table": "sahel_extract", "field": "city", "source": "nope"}], actor="Bob")


def test_audit_chain_detects_tampering(banks):
    t = banks["sahel"][0]
    f = t.dir / "audit.jsonl"
    original = f.read_text(encoding="utf-8")
    lines = original.splitlines()
    e = json.loads(lines[1])
    e["actor"] = "someone-else"
    lines[1] = json.dumps(e, ensure_ascii=False)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        assert t.verify_audit() == (False, 1)
    finally:
        f.write_text(original, encoding="utf-8")


def test_memory_is_per_tenant(banks):
    atlas, sahel = banks["atlas"][0], banks["sahel"][0]
    hits = atlas.memory_search("skimming DAB", 3)
    assert hits and hits[0]["id"].startswith("typology:")
    assert sahel.memory_search("skimming DAB", 3) == []                            # Sahel has no labels: nothing to recall
    assert all(not h["id"].startswith("case:NP-") for h in atlas.memory_search("disputed operation card blocked", 5))


# ---------------------------------------------------------------- REST API
@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("HYSON_TENANTS_DIR", str(tmp_path))
    monkeypatch.setenv("HYSON_PLATFORM_KEY", "platform-secret-for-tests-0123456789")
    from fastapi.testclient import TestClient
    import api
    api._hits.clear()
    return TestClient(api.app)


def _sign(secret, body, ts=None):
    ts = str(int(ts or time.time()))
    return ts, hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def test_api_end_to_end(client):
    r = client.post("/v1/tenants", json={"id": "nordic-api", "name": "Nordic"}, headers={"x-platform-key": "wrong"})
    assert r.status_code == 403
    r = client.post("/v1/tenants", json={"id": "nordic-api", "name": "Nordic"}, headers={"x-platform-key": "platform-secret-for-tests-0123456789"})
    assert r.status_code == 201
    admin, secret = r.json()["admin_key"], r.json()["webhook_secret"]
    other = client.post("/v1/tenants", json={"id": "other-bank", "name": "Other"},
                        headers={"x-platform-key": "platform-secret-for-tests-0123456789"}).json()["admin_key"]
    H = {"x-api-key": admin}
    assert client.get("/v1/tenants/nordic-api", headers={"x-api-key": other}).status_code == 403     # isolation
    analyst = client.post("/v1/tenants/nordic-api/keys", json={"role": "analyst"}, headers=H).json()["key"]
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted((BANKS / "nordic").glob("*.csv"))]
    assert client.post("/v1/tenants/nordic-api/sources", files=files, headers={"x-api-key": analyst}).status_code == 403
    assert client.post("/v1/tenants/nordic-api/sources", files=files, headers=H).status_code == 201
    assert client.post("/v1/tenants/nordic-api/discover", headers=H).json()["relations"]
    m = client.post("/v1/tenants/nordic-api/mapping/propose", headers=H).json()
    assert m["roles"]["txn"] == "transactions" and m["open_flags"]
    v = client.post("/v1/tenants/nordic-api/validate", headers=H, json={"transactions": TRUTH["nordic"]["transactions"]}).json()
    assert v["validation"]["reconciliation"]["transactions"]["ok"]
    assert client.post("/v1/tenants/nordic-api/approve", json={"approver": "Alice"}, headers=H).status_code == 409
    m = client.put("/v1/tenants/nordic-api/mapping", json={"changes": [{"op": "confirm_all"}]}, headers=H).json()
    assert m["open_flags"] == []
    client.post("/v1/tenants/nordic-api/validate", headers=H)
    assert client.post("/v1/tenants/nordic-api/approve", json={"approver": "Alice"}, headers={"x-api-key": analyst}).status_code == 403
    assert client.post("/v1/tenants/nordic-api/approve", json={"approver": "Alice"}, headers=H).status_code == 200
    assert client.post("/v1/tenants/nordic-api/activate", json={"approver": "Alice"}, headers=H).status_code == 200
    k = client.get("/v1/tenants/nordic-api/kpis/fraud_by_channel", headers={"x-api-key": analyst})
    assert k.status_code == 200 and k.json()["rows"]
    assert client.get("/v1/tenants/nordic-api/alerts?n=5", headers={"x-api-key": analyst}).json()["alerts"][0]["score_kind"] == "bank_score"
    # signed real-time events in the bank's own schema
    rec = {"txnRef": "TXNEW0001", "createdAtMs": 1785600000000, "clientRef": "C000930", "paymentCard": "CARD001137", "amountMinor": "99900",
           "ccy": "EUR", "channelCode": "ECOM", "posEntryMode": "NO3DS", "txnKind": "PURCHASE", "responseCode": "00", "mid": "M01408",
           "countryCode": "FR", "rulesScore": 2}
    body = json.dumps({"records": [rec]}).encode()
    ts, sig = _sign(secret, body)
    r = client.post("/v1/tenants/nordic-api/events", content=body, headers={"x-hyson-timestamp": ts, "x-hyson-signature": "sha256=" + sig})
    assert r.status_code == 200 and r.json()["new"] == 1 and r.json()["scores"][0]["transaction_id"] == "TXNEW0001"
    r = client.post("/v1/tenants/nordic-api/events", content=body, headers={"x-hyson-timestamp": ts, "x-hyson-signature": "sha256=" + sig})
    assert r.json()["duplicates"] == 1                                                             # idempotent
    assert client.post("/v1/tenants/nordic-api/events", content=body,
                       headers={"x-hyson-timestamp": ts, "x-hyson-signature": "sha256=" + "0" * 64}).status_code == 403
    old, sig_old = _sign(secret, body, time.time() - 3600)
    assert client.post("/v1/tenants/nordic-api/events", content=body,
                       headers={"x-hyson-timestamp": old, "x-hyson-signature": sig_old}).status_code == 403   # replay window
    a = client.get("/v1/tenants/nordic-api/audit", headers=H).json()
    assert a["chain_valid"] and any(e["action"] == "events.ingest" for e in a["entries"])
    assert client.get("/v1/tenants/nordic-api/audit", headers={"x-api-key": analyst}).status_code == 403


@pytest.mark.parametrize("tid", ["nordic", "sahel"])
def test_console_page_renders_active_tenant(banks, tid):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP / "app.py"), default_timeout=300)
    at.session_state["page"] = "integ"
    at.session_state["welcomed"] = True
    at.session_state["lang"] = "en"
    at.session_state["integ_tid"] = tid
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
    assert any("Universal banking integration" in m.value for m in at.markdown)
