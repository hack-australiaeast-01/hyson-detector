"""AI reporting engine: interpretation, figures reconciled with the data, confirmed vs suspected, grounding, audiences, formats,
review / approval workflow, tenant isolation through the REST API. Offline (0 token)."""
import hashlib
import io
import json
import os
import zipfile

import pytest

BRIEF = ("Prepare a detailed quarterly report about fraud activity across our DAB channels, compare it with the previous quarter, identify the "
         "most affected card categories, investigate emerging patterns, assess potential cybersecurity or operational weaknesses, and provide "
         "recommendations for management.")


@pytest.fixture(scope="module")
def src():
    import report_sources as RS
    return RS.get("hyson")


@pytest.fixture()
def store(src, tmp_path):
    import report_store as RSt
    return RSt.Store(src, tmp_path / "reports")


def _spec(src, text, **over):
    import report_interpret as RP
    return {**RP.interpret(text, src, "fr"), **over}


def test_interprets_the_brief_example(src):
    s = _spec(src, BRIEF)
    assert (s["lang"], s["type"], s["audience"], s["depth"], s["cadence"]) == ("en", "periodic", "executive", "detailed", "quarter")
    assert s["period"] == ["2026-04-01", "2026-06-30"] and s["previous"] == ["2026-01-01", "2026-03-31"]   # last full labelled quarter
    assert s["scope"]["channels"] == ["DAB"]
    assert {"card_type", "emerging", "cyber", "operational", "recommendations"} <= set(s["focus"])
    assert {"cyber", "processing", "recommendations"} <= set(s["sections"]) and not s["questions"]


def test_interpreter_asks_only_when_essential(src):
    assert _spec(src, "Prépare un rapport d'enquête")["questions"]
    s = _spec(src, "Rapport d'enquête pour TX01631347")
    assert s["type"] == "investigation" and s["case_id"] == "TX01631347" and not s["questions"]
    ar = _spec(src, "تقرير ملخص للإدارة عن الاحتيال في الربع الثاني 2026")
    assert (ar["lang"], ar["period"], ar["depth"]) == ("ar", ["2026-04-01", "2026-06-30"], "summary")
    assert _spec(src, "Évaluation cybersécurité sur août 2026")["period"] == ["2026-08-01", "2026-08-31"]
    assert _spec(src, "Rapport opérationnel du 01/06/2026 au 31/07/2026")["period"] == ["2026-06-01", "2026-07-31"]


def test_figures_reconcile_with_the_data_and_the_documented_kpis(src):
    import report_insights as RI
    a = RI.run(_spec(src, "Rapport de performance du 01/06/2026 au 31/07/2026", type="periodic", compare=False), src)
    assert a.val("model_alerts") == 1779 and round(a.val("model_precision") * 1779) == 718            # STATUS: 718 frauds / 1,779 alerts
    n, fr = src.one("SELECT COUNT(*), SUM(is_fraud) FROM tx WHERE day BETWEEN '2026-06-01' AND '2026-07-31'")
    assert a.val("ops") == n and a.val("frauds") == fr
    assert all(c["ok"] for c in a.checks if c["level"] == "error")
    ch = next(t for t in a.tables if t["key"] == "channel")["df"]
    assert ch["ops"].sum() == n and ch["frauds"].sum() == fr


def test_confirmed_and_suspected_are_never_mixed(src):
    import report_insights as RI
    a = RI.run(_spec(src, "Rapport mensuel d'août 2026"), src)
    assert a.get("frauds") is None and a.get("fraud_rate") is None                 # no label yet -> no "confirmed fraud" figure at all
    assert a.val("suspected") == a.val("model_alerts") > 0
    assert any("2026-07-31" in x["fr"] for x in a.limits)
    assert not next(c for c in a.checks if c["name"] == "labels")["ok"]
    assert a.get("rules_alerts") is None                                            # rules engine not computed on the live stream: unknown, not 0


def test_audience_changes_the_writing_not_the_facts(src):
    import report_insights as RI
    base = _spec(src, "Rapport trimestriel T2 2026")
    ex = {f.get("tag"): f["value"] for f in RI.run({**base, "audience": "executive"}, src).facts}
    cy = {f.get("tag"): f["value"] for f in RI.run({**base, "audience": "cyber"}, src).facts}
    common = set(ex) & set(cy)
    assert len(common) > 10 and all(ex[k] == cy[k] for k in common)


def test_every_number_written_is_grounded_and_every_reference_exists(src):
    import report_compose as RC
    import report_insights as RI
    a = RI.run(_spec(src, BRIEF), src)
    doc = RC.compose(a, charts_on=False)
    ids = {x["id"] for x in a.facts + a.tables + a.insights}
    for sec in doc["sections"]:
        for blk in sec["blocks"]:
            for txt, refs in [(blk.get("text"), blk.get("refs", []))] + [(i["text"], i["refs"]) for i in blk.get("items", [])]:
                if txt:
                    ok, bad = RC.grounded(txt, a)
                    assert ok, (sec["id"], txt, bad)
                    assert set(refs) <= ids, (sec["id"], refs)
    assert not RC.grounded("Les pertes atteignent 987 654 TND.", a)[0]          # an invented figure is rejected
    assert RC.grounded(f"{a.facts[0]['value']:.0f} opérations", a)[0]


def test_cyber_findings_are_indicators_not_claims(src):
    import report_compose as RC
    import report_insights as RI
    a = RI.run(_spec(src, "Évaluation cybersécurité sur T2 2026"), src)
    doc = RC.compose(a, charts_on=False)
    cyber = next(s for s in doc["sections"] if s["id"] == "cyber")
    assert cyber["blocks"][0]["kind"] == "limit" and "ne prouve" in cyber["blocks"][0]["text"]
    assert all(i["kind"] in ("hypothesis", "fact", "ml") for i in a.insights if i["area"] == "cyber")


def test_formats_and_arabic_rtl(src, store):
    rid = store.create(_spec(src, "تقرير ملخص للإدارة عن الاحتيال في الربع الثاني 2026"), "test", use_ai=False)
    b = store.version(rid)
    files = {fmt: store.export(rid, fmt)[0] for fmt in ("pdf", "docx", "xlsx", "html")}
    assert files["pdf"][:4] == b"%PDF"
    assert "word/document.xml" in zipfile.ZipFile(io.BytesIO(files["docx"])).namelist()
    assert b"w:bidi" in zipfile.ZipFile(io.BytesIO(files["docx"])).read("word/document.xml")
    assert "xl/workbook.xml" in zipfile.ZipFile(io.BytesIO(files["xlsx"])).namelist()
    assert b"dir='rtl'" in files["html"] and "مسودة".encode() in files["html"]
    assert b["charts"] and all(c["title"] and c["period"] and c["source"] for c in b["charts"])


def test_investigation_report_uses_the_case_evidence(src, store):
    rid = store.create(_spec(src, "Rapport d'enquête pour TX01631347"), "test", use_ai=False)
    b = store.version(rid)
    assert b["extra"]["system"]["decision"] in ("BLOQUER", "ESCALADER", "VALIDER")
    assert len(b["extra"]["board"]) >= 5 and [s["id"] for s in b["doc"]["sections"]][:2] == ["summary", "case"]
    ai = next(s for s in b["doc"]["sections"] if s["id"] == "ai")
    assert ai["blocks"][0]["kind"] == "limit"                                      # agents not run offline: said, not invented
    assert "C0" not in json.dumps(b["doc"])                                        # no customer identifier in the document


def test_review_and_approval_workflow(src, store):
    rid = store.create(_spec(src, "Rapport mensuel de juillet 2026"), "Alice", use_ai=False)
    v2 = store.edit_section(rid, "conclusion", "Conclusion revue par le service fraude [F6].", "Bob")
    assert v2 == 2 and store.version(rid)["doc"]["sections"][-2]["blocks"][0]["kind"] == "employee"
    assert "Conclusion revue" in store.compare(rid, 1, 2)
    store.comment(rid, "Bob", "À valider par la direction", "conclusion")
    v3 = store.regenerate(rid, "Bob", changes={"audience": "operations"})
    assert store.version(rid, v3)["spec"]["audience"] == "operations"
    with pytest.raises(ValueError):
        store.approve(rid, " ")
    with pytest.raises(PermissionError):
        store.approve(rid, "Eve", role="analyst")
    ap = store.approve(rid, "Carla")
    data, _, name = store.export(rid, "pdf")
    assert "DRAFT" not in name and hashlib.sha256(data).hexdigest() == ap["files"]["pdf"]["sha256"]
    lines = [json.loads(x) for x in (store.dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    prev = "0" * 64
    for e in lines:                                                                 # hash chain intact
        h = e.pop("hash")
        assert e["prev"] == prev and hashlib.sha256((prev + json.dumps(e, sort_keys=True, ensure_ascii=False, default=str)).encode()).hexdigest() == h
        prev = h
    assert [e["action"] for e in lines][-1] == "report.approve"


def test_bank_reports_through_the_api_are_isolated(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("HYSON_TENANTS_DIR", str(tmp_path / "tenants"))
    monkeypatch.setenv("HYSON_PLATFORM_KEY", "platform-secret-for-tests-0123456789")
    import tenants as tn
    banks = Path(__file__).resolve().parents[1] / "app" / "samples" / "banks"
    t, admin = tn.onboard_demo("nordic-rep", str(banks / "nordic"), "Nordic Pay", train=True)
    _, other = tn.onboard_demo("sahel-rep", str(banks / "sahel_extract.jsonl"), "Sahel", train=False)
    analyst = t.add_key("analyst")
    from fastapi.testclient import TestClient
    import api
    api._hits.clear()
    c = TestClient(api.app)
    body = {"request": "Monthly fraud report for July 2026 for management", "lang": "en"}
    assert c.post("/v1/tenants/nordic-rep/reports", json=body, headers={"x-api-key": other}).status_code == 403
    r = c.post("/v1/tenants/nordic-rep/reports", json=body, headers={"x-api-key": analyst})
    assert r.status_code == 201, r.text
    rid = r.json()["report_id"]
    assert (t.dir / "reports" / rid / "v1.json").exists()                           # stored inside the bank's own folder
    b = json.loads((t.dir / "reports" / rid / "v1.json").read_text(encoding="utf-8"))
    n = int(((t.canonical("transactions")["timestamp"] >= "2026-07-01") & (t.canonical("transactions")["timestamp"] < "2026-08-01")).sum())
    assert next(f for f in b["facts"] if f["key"] == "ops")["value"] == n
    assert c.post(f"/v1/tenants/nordic-rep/reports/{rid}/approve", json={"approver": "Alice"}, headers={"x-api-key": analyst}).status_code == 403
    assert c.post(f"/v1/tenants/nordic-rep/reports/{rid}/approve", json={"approver": "Alice"}, headers={"x-api-key": admin}).status_code == 200
    pdf = c.get(f"/v1/tenants/nordic-rep/reports/{rid}/export?format=pdf", headers={"x-api-key": analyst})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert c.get("/v1/tenants/nordic-rep/reports", headers={"x-api-key": other}).status_code == 403
    assert any(e["action"] == "report.approve" for e in t.audit_log()) and t.verify_audit() == (True, None)
    q = c.post("/v1/tenants/nordic-rep/reports", json={"request": "Investigation report please", "lang": "en"}, headers={"x-api-key": analyst})
    assert q.status_code == 422 and q.json()["detail"]["questions"]
    os.environ.pop("HYSON_TENANTS_DIR", None)
