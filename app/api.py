"""Hyson Universal Banking API (FastAPI): onboard any bank, map its schema, validate, approve, activate, stream events, query.

    pip install -r app/requirements-api.txt
    set HYSON_PLATFORM_KEY=<long random secret>      # only the platform operator can create tenants
    cd app && uvicorn api:app --port 8600            # OpenAPI docs on /docs

Security: API keys per tenant with roles (admin / analyst / ingest), stored hashed; a key only ever reaches its own tenant;
webhook events signed with HMAC-SHA256 + timestamp (replay window 5 min); request size limits; per-key rate limit;
every state change written to the tenant's hash-chained audit trail. Data stays pseudonymised (keyed hashes per tenant).
"""
import hmac
import json
import os
import time
from collections import defaultdict, deque
from typing import Literal, Optional

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import canonical as cn
import tenants as tn

app = FastAPI(title="Hyson Universal Banking API", version="1.0",
              description="Bank-agnostic fraud intelligence: discovery, AI-assisted mapping, readiness, human approval, activation.")
MAX_UPLOAD = int(os.getenv("HYSON_MAX_UPLOAD_MB", "50")) * 1024 * 1024
MAX_EVENTS_BODY = 2 * 1024 * 1024
RATE = int(os.getenv("HYSON_RATE_PER_MIN", "240"))
_hits = defaultdict(deque)


@app.middleware("http")
async def limits(request: Request, call_next):
    size = int(request.headers.get("content-length") or 0)
    limit = MAX_EVENTS_BODY if request.url.path.endswith("/events") else MAX_UPLOAD
    if size > limit:
        return JSONResponse({"detail": "payload too large"}, status_code=413)
    ident = (request.headers.get("x-api-key") or (request.client.host if request.client else "anon"))[:120]
    q, now = _hits[ident], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE:
        return JSONResponse({"detail": "rate limit"}, status_code=429)
    q.append(now)
    return await call_next(request)


class Caller:
    def __init__(self, tenant, role, key_hint):
        self.tenant, self.role, self.actor = tenant, role, f"{role}:{key_hint}"


def caller(tenant_id: str, x_api_key: str = Header(...)):
    t, role = tn.Tenant.from_key(x_api_key)
    if t is None or t.id != tenant_id:                       # a key never reaches another tenant (same 403 either way)
        raise HTTPException(403, "invalid key for this tenant")
    return Caller(t, role, x_api_key[-4:])


def need(c: Caller, perm):
    if perm not in tn.ROLES.get(c.role, set()):
        raise HTTPException(403, f"role '{c.role}' cannot {perm}")


def _err(fn, *a, **k):
    try:
        return fn(*a, **k)
    except tn.TenantError as exc:
        raise HTTPException(409 if "first" in str(exc) or "confirmation" in str(exc) else 400, str(exc))


# ---------------------------------------------------------------- models
class NewTenant(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,39}$")
    name: str = Field(min_length=2, max_length=120)


class NewKey(BaseModel):
    role: Literal["admin", "analyst", "ingest"]


class MappingChange(BaseModel):
    op: Literal["set", "confirm", "confirm_all", "role", "rate"]
    table: Optional[str] = None
    field: Optional[str] = None
    source: Optional[str] = None
    entity: Optional[str] = None
    flag: Optional[str] = None
    values: Optional[dict] = None
    scale: Optional[float] = None
    format: Optional[str] = None
    currency: Optional[str] = None
    value: Optional[float] = None


class MappingUpdate(BaseModel):
    changes: list[MappingChange] = Field(min_length=1, max_length=200)


class Control(BaseModel):
    transactions: Optional[int] = None
    frauds: Optional[int] = None
    amount: Optional[float] = None
    amount_tnd: Optional[float] = None


class Approval(BaseModel):
    approver: str = Field(min_length=2, max_length=80)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    lang: Literal["fr", "en"] = "fr"


# ---------------------------------------------------------------- platform
@app.get("/v1/health")
def health():
    return {"ok": True, "tenants": len(tn.list_tenants())}


@app.post("/v1/tenants", status_code=201)
def create_tenant(body: NewTenant, x_platform_key: str = Header(...)):
    expected = os.getenv("HYSON_PLATFORM_KEY", "")
    if len(expected) < 16 or not hmac.compare_digest(expected, x_platform_key):
        raise HTTPException(403, "platform key required")
    t, key = _err(tn.Tenant.create, body.id, body.name, actor="platform")
    return {"tenant": t.id, "admin_key": key, "webhook_secret": t.webhook_secret(), "note": "shown once: store them in your vault"}


# ---------------------------------------------------------------- tenant
@app.get("/v1/tenants/{tenant_id}")
def tenant_info(c: Caller = Depends(caller)):
    cfg = c.tenant.config
    return {k: cfg.get(k) for k in ("id", "name", "status", "mapping_version", "approved", "activated", "model", "dashboard")}


@app.post("/v1/tenants/{tenant_id}/keys", status_code=201)
def new_key(body: NewKey, c: Caller = Depends(caller)):
    need(c, "admin")
    return {"role": body.role, "key": c.tenant.add_key(body.role, actor=c.actor), "note": "shown once"}


@app.post("/v1/tenants/{tenant_id}/sources", status_code=201)
async def upload(files: list[UploadFile] = File(...), c: Caller = Depends(caller)):
    need(c, "ingest")
    data = []
    for f in files[:20]:
        b = await f.read()
        if len(b) > MAX_UPLOAD:
            raise HTTPException(413, "file too large")
        data.append((os.path.basename(f.filename or "upload.csv"), b))
    try:
        batch = c.tenant.ingest(data, actor=c.actor, role=c.role)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"batch": batch}


@app.post("/v1/tenants/{tenant_id}/discover")
def discover(c: Caller = Depends(caller)):
    need(c, "admin")
    s = _err(c.tenant.discover, c.actor)
    return {"keys": s["keys"], "relations": s["relations"],
            "tables": {t: {"rows": v["rows"], "columns": {k: {kk: p[kk] for kk in ("kind", "null_rate", "distinct", "unique")}
                                                          for k, p in v["columns"].items()}} for t, v in s["tables"].items()}}


@app.post("/v1/tenants/{tenant_id}/mapping/propose")
def propose(c: Caller = Depends(caller)):
    need(c, "admin")
    return _mapping_view(_err(c.tenant.propose_mapping, c.actor))


@app.get("/v1/tenants/{tenant_id}/mapping")
def get_mapping(c: Caller = Depends(caller)):
    need(c, "analyst")
    m = c.tenant.mapping()
    if not m:
        raise HTTPException(404, "no mapping yet")
    return _mapping_view(m)


@app.put("/v1/tenants/{tenant_id}/mapping")
def put_mapping(body: MappingUpdate, c: Caller = Depends(caller)):
    need(c, "admin")
    return _mapping_view(_err(c.tenant.update_mapping, [x.model_dump(exclude_none=True) for x in body.changes], c.actor, c.role))


def _mapping_view(m):
    return {"version": m["version"], "roles": m["roles"], "tables": m["tables"], "unassigned_tables": m["unassigned_tables"],
            "open_flags": [{"id": tn.flag_id(f), **f} for f in tn.Tenant.open_flags(m)],
            "info_flags": [f for f in m["flags"] if f["level"] != "confirm"]}


@app.post("/v1/tenants/{tenant_id}/validate")
def validate(control: Optional[Control] = None, c: Caller = Depends(caller)):
    need(c, "admin")
    _err(c.tenant.build, c.actor)
    res = _err(c.tenant.validate, control.model_dump(exclude_none=True) if control else None, c.actor)
    info = c.tenant.build_info()
    return {"status": c.tenant.config["status"], "readiness": info["readiness"], "validation": res}


@app.get("/v1/tenants/{tenant_id}/capabilities")
def capabilities(c: Caller = Depends(caller)):
    need(c, "analyst")
    info = c.tenant.build_info()
    if not info:
        raise HTTPException(404, "not built yet")
    return {"modules": info["modules"], "kpis": info["kpis"], "readiness": {k: info["readiness"][k] for k in ("score", "gate")}}


@app.post("/v1/tenants/{tenant_id}/approve")
def approve(body: Approval, c: Caller = Depends(caller)):
    need(c, "admin")
    return _err(c.tenant.approve, body.approver, c.role)["approved"]


@app.post("/v1/tenants/{tenant_id}/activate")
def activate(body: Approval, c: Caller = Depends(caller)):
    need(c, "admin")
    return _err(c.tenant.activate, body.approver, c.role)["activated"]


@app.post("/v1/tenants/{tenant_id}/model/train")
def train(c: Caller = Depends(caller)):
    need(c, "admin")
    m = _err(c.tenant.train_model, c.actor, c.role)
    return {k: m[k] for k in ("version", "status", "metrics", "train_period", "test_period", "n_train", "frauds_train", "algorithm")
            } | {"baseline": m.get("baseline")}


@app.post("/v1/tenants/{tenant_id}/model/{version}/approve")
def approve_model(version: int, body: Approval, c: Caller = Depends(caller)):
    need(c, "admin")
    m = _err(c.tenant.approve_model, version, body.approver, c.role)
    return {"version": m["version"], "status": m["status"], "approved": m["approved"]}


@app.get("/v1/tenants/{tenant_id}/kpis/{kpi_id}")
def kpi(kpi_id: str, c: Caller = Depends(caller)):
    need(c, "analyst")
    if c.tenant.config["status"] != "active":
        raise HTTPException(409, "tenant is not active")
    df = _err(c.tenant.kpi, kpi_id)
    return {"kpi": kpi_id, "label": cn.KPIS[kpi_id][1], "rows": json.loads(df.to_json(orient="records", date_format="iso"))}


@app.get("/v1/tenants/{tenant_id}/alerts")
def alerts(n: int = 50, lang: Literal["fr", "en"] = "fr", c: Caller = Depends(caller)):
    need(c, "analyst")
    if c.tenant.config["status"] != "active":
        raise HTTPException(409, "tenant is not active")
    df = c.tenant.alerts(min(max(n, 1), 500), lang=lang)
    return {"alerts": json.loads(df.drop(columns=["is_fraud"], errors="ignore").to_json(orient="records", date_format="iso"))}


@app.post("/v1/tenants/{tenant_id}/memory/ask")
def ask(body: Question, c: Caller = Depends(caller)):
    need(c, "analyst")
    return c.tenant.memory_answer(body.question, body.lang)


@app.get("/v1/tenants/{tenant_id}/audit")
def audit(limit: int = 200, c: Caller = Depends(caller)):
    need(c, "admin")
    ok, broken = c.tenant.verify_audit()
    return {"chain_valid": ok, "broken_at": broken, "entries": c.tenant.audit_log()[-min(max(limit, 1), 2000):]}


@app.post("/v1/tenants/{tenant_id}/events")
async def events(tenant_id: str, request: Request, x_hyson_timestamp: str = Header(...), x_hyson_signature: str = Header(...)):
    """Real-time transactions in the bank's own schema: {"records": [...]}, signed: hex HMAC-SHA256(secret, f"{ts}." + body)."""
    try:
        t = tn.Tenant(tenant_id)
    except tn.TenantError:
        raise HTTPException(403, "invalid signature")
    body = await request.body()
    if not t.verify_signature(body, x_hyson_timestamp, x_hyson_signature):
        raise HTTPException(403, "invalid signature")
    try:
        records = json.loads(body).get("records")
    except (ValueError, AttributeError):
        raise HTTPException(400, "body must be JSON {\"records\": [...]}")
    if not isinstance(records, list):
        raise HTTPException(400, "records must be a list")
    res = _err(t.ingest_events, records, "webhook")
    res["scores"] = json.loads(pd.DataFrame(res["scores"]).to_json(orient="records")) if res["scores"] else []
    return res
