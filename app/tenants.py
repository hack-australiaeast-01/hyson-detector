"""Multi-tenant workspaces for the universal banking integration.

Each bank (tenant) gets an isolated folder: raw zone (parquet, minimised after activation), versioned mappings, canonical data,
readiness report, capability matrix, dashboard configuration, candidate/approved models, its own RAG index and a hash-chained
audit trail. API keys are stored as SHA-256 hashes with a role (admin / analyst / ingest).

Lifecycle: draft -> mapped -> validated -> approved -> active. Any mapping change after approval sends the tenant back to
"mapped": nothing reaches production without a named human approval of the exact mapping version.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import canonical as cn
import data_access as da
import discovery as dv
import mapper as mp
import readiness as rd
import tenant_model as tm
import tenant_rag as rag

ROOT = Path(os.getenv("HYSON_TENANTS_DIR", str(da.DATA / "tenants")))
TID = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
ROLES = {"admin": {"admin", "analyst", "ingest"}, "analyst": {"analyst"}, "ingest": {"ingest"}}
STATUSES = ["draft", "mapped", "validated", "approved", "active"]


class TenantError(Exception):
    pass


def root():
    return Path(os.getenv("HYSON_TENANTS_DIR", str(ROOT)))


def list_tenants():
    r = root()
    return sorted(p.name for p in r.iterdir() if (p / "config.json").exists()) if r.exists() else []


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


class Tenant:
    def __init__(self, tid):
        if not TID.match(tid or ""):
            raise TenantError("invalid tenant id")
        self.id = tid
        self.dir = root() / tid
        if not (self.dir / "config.json").exists():
            raise TenantError("unknown tenant")

    # ------------------------------------------------------------ creation, keys, audit
    @classmethod
    def create(cls, tid, name, actor="platform", replace=False):
        if not TID.match(tid or ""):
            raise TenantError("invalid tenant id (a-z, 0-9, '-', 3-40 chars)")
        d = root() / tid
        if d.exists():
            if not replace:
                raise TenantError("tenant already exists")
            shutil.rmtree(d)
        d.mkdir(parents=True)
        (d / "secret.json").write_text(json.dumps({"salt": secrets.token_hex(32), "webhook_secret": secrets.token_urlsafe(32)}))
        (d / "keys.json").write_text("[]")
        cfg = {"id": tid, "name": name, "created": _now(), "status": "draft", "mapping_version": 0, "approved": None, "activated": None,
               "rates": dict(mp.DEFAULT_RATES), "default_currency": "TND", "model": None, "dashboard": None}
        (d / "config.json").write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
        t = cls(tid)
        key = t.add_key("admin", actor=actor)
        t.audit(actor, "tenant.create", {"name": name})
        return t, key

    @property
    def config(self):
        return json.loads((self.dir / "config.json").read_text(encoding="utf-8"))

    def _save_config(self, cfg):
        tmp = self.dir / "config.json.tmp"
        tmp.write_text(json.dumps(cfg, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(self.dir / "config.json")

    def _secret(self):
        return json.loads((self.dir / "secret.json").read_text())

    def add_key(self, role, actor="admin"):
        if role not in ROLES:
            raise TenantError("unknown role")
        key = f"hy_{self.id}_{secrets.token_urlsafe(24)}"
        keys = json.loads((self.dir / "keys.json").read_text())
        keys.append({"id": secrets.token_hex(4), "role": role, "sha256": _hash(key), "created": _now()})
        (self.dir / "keys.json").write_text(json.dumps(keys, indent=1))
        if (self.dir / "audit.jsonl").exists():
            self.audit(actor, "key.create", {"role": role})
        return key

    def role_of(self, key):
        h = _hash(key or "")
        for k in json.loads((self.dir / "keys.json").read_text()):
            if hmac.compare_digest(k["sha256"], h):
                return k["role"]
        return None

    @staticmethod
    def from_key(key):
        """API key -> (tenant, role). Keys look like hy_<tenant>_<random>."""
        m = re.match(r"^hy_([a-z0-9][a-z0-9-]{2,39})_[A-Za-z0-9_\-]{20,}$", key or "")
        if not m:
            return None, None
        try:
            t = Tenant(m.group(1))
        except TenantError:
            return None, None
        role = t.role_of(key)
        return (t, role) if role else (None, None)

    def audit(self, actor, action, details=None):
        f = self.dir / "audit.jsonl"
        prev = "0" * 64
        if f.exists():
            lines = f.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                prev = json.loads(lines[-1])["hash"]
        body = {"ts": _now(), "actor": str(actor)[:80], "action": action, "details": details or {}, "prev": prev}
        body["hash"] = hashlib.sha256((prev + json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)).encode()).hexdigest()
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, ensure_ascii=False, default=str) + "\n")

    def audit_log(self):
        f = self.dir / "audit.jsonl"
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []

    def verify_audit(self):
        prev = "0" * 64
        for i, e in enumerate(self.audit_log()):
            h = e.pop("hash")
            if e["prev"] != prev or hashlib.sha256((prev + json.dumps(e, sort_keys=True, ensure_ascii=False, default=str)).encode()).hexdigest() != h:
                return False, i
            prev = h
        return True, None

    def _require(self, role, needed):
        if needed not in ROLES.get(role or "", set()):
            raise TenantError(f"forbidden: role '{role}' cannot {needed}")

    # ------------------------------------------------------------ ingestion and discovery
    def ingest(self, source, actor="ingest", role="admin"):
        """source: path or list of (name, bytes). Stored as parquet tables in raw/<batch>/ (the bank's own schema)."""
        self._require(role, "ingest")
        tables = dv.load(source)
        if not tables:
            raise TenantError("no readable table")
        batch = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        d = self.dir / "raw" / batch
        d.mkdir(parents=True)
        for name, df in tables.items():
            df.astype({c: "string" for c in df.columns if df[c].dtype == object}).to_parquet(d / f"{name}.parquet", index=False)
        cfg = self.config
        cfg["batch"] = batch
        self._save_config(cfg)
        self.audit(actor, "source.ingest", {"batch": batch, "tables": {k: int(len(v)) for k, v in tables.items()}})
        return batch

    def raw(self):
        b = self.config.get("batch")
        if not b:
            raise TenantError("no source ingested")
        return {p.stem: pd.read_parquet(p) for p in sorted((self.dir / "raw" / b).glob("*.parquet"))}

    def discover(self, actor="system"):
        s = dv.summary(self.raw())
        (self.dir / "discovery.json").write_text(json.dumps(s, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        self.audit(actor, "source.discover", {"tables": list(s["tables"]), "relations": len(s["relations"])})
        return s

    def discovery(self):
        f = self.dir / "discovery.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    # ------------------------------------------------------------ mapping (versioned)
    def propose_mapping(self, actor="system"):
        tables = self.raw()
        m = mp.propose(tables, self.discovery() or dv.summary(tables))
        m["confirmed"] = []
        return self._store_mapping(m, actor, "mapping.propose")

    def _store_mapping(self, m, actor, action):
        cfg = self.config
        m["version"] = cfg["mapping_version"] + 1
        m["author"] = actor
        m["created"] = _now()
        (self.dir / "mappings").mkdir(exist_ok=True)
        (self.dir / "mappings" / f"v{m['version']}.json").write_text(json.dumps(m, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        cfg["mapping_version"] = m["version"]
        cfg["status"] = "mapped"
        cfg["approved"] = None
        self._save_config(cfg)
        self.audit(actor, action, {"version": m["version"], "roles": m["roles"], "open_flags": len(self.open_flags(m))})
        return m

    def mapping(self, version=None):
        v = version or self.config["mapping_version"]
        f = self.dir / "mappings" / f"v{v}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    @staticmethod
    def open_flags(m):
        done = set(m.get("confirmed", []))
        return [f for f in m["flags"] if f["level"] == "confirm" and _flag_id(f) not in done]

    def update_mapping(self, changes, actor, role="admin"):
        """changes: [{"op": "set", "table", "field", "source"|None, "values"?: {...}, "scale"?: x, "format"?: str}
                     {"op": "confirm", "flag": flag_id} | {"op": "confirm_all"} | {"op": "role", "table", "entity"|None}
                     {"op": "rate", "currency", "value"}]"""
        self._require(role, "admin")
        m = self.mapping()
        if m is None:
            raise TenantError("no mapping")
        tables = self.raw()
        for ch in changes:
            op = ch.get("op")
            if op == "confirm":
                m.setdefault("confirmed", []).append(ch["flag"])
            elif op == "confirm_all":
                m["confirmed"] = sorted({*m.get("confirmed", []), *(_flag_id(f) for f in m["flags"] if f["level"] == "confirm")})
            elif op == "rate":
                m.setdefault("rates", {})[str(ch["currency"]).upper()] = float(ch["value"])
            elif op == "role":
                t, e = ch["table"], ch.get("entity")
                if t not in tables or (e and e not in cn.ENTITIES):
                    raise TenantError("unknown table or entity")
                if e:
                    summ = self.discovery() or dv.summary(tables)
                    fields = mp._assign(t, tables[t], summ["tables"][t], e)
                    spec = {f: mp._field_spec(e, f, cn.ENTITIES[e][f][0], c, s, summ["tables"][t]["columns"][c], tables[t][c], m["flags"], t)
                            for f, (c, s) in fields.items()}
                    m["tables"][t] = {"entity": e, "fields": spec, "excluded": {}, "ignored": []}
                    m["roles"][t] = e
                else:
                    m["tables"].pop(t, None)
                    m["roles"].pop(t, None)
            elif op == "set":
                t, f = ch["table"], ch["field"]
                if t not in m["tables"]:
                    raise TenantError("table has no role")
                e = m["tables"][t]["entity"]
                if f not in cn.ENTITIES[e]:
                    raise TenantError("unknown canonical field")
                src = ch.get("source")
                if src is None:
                    m["tables"][t]["fields"].pop(f, None)
                    continue
                if src not in tables[t].columns:
                    raise TenantError("unknown source column")
                if src in m["tables"][t].get("excluded", {}):
                    raise TenantError("excluded (sensitive) column cannot be mapped")
                summ = self.discovery() or dv.summary(tables)
                spec = mp._field_spec(e, f, cn.ENTITIES[e][f][0], src, 1.0, summ["tables"][t]["columns"][src], tables[t][src], [], t)
                for k in ("values", "scale", "format"):
                    if k in ch:
                        spec[k] = ch[k]
                spec["confirm"] = False
                spec["confidence"] = 1.0
                spec["set_by"] = actor
                m["tables"][t]["fields"][f] = spec
            else:
                raise TenantError(f"unknown op {op}")
        return self._store_mapping(m, actor, "mapping.update")

    # ------------------------------------------------------------ build, validate, configure
    def build(self, actor="system"):
        m = self.mapping()
        canon, rep = mp.apply(self.raw(), m, self._secret()["salt"], m.get("rates"))
        d = self.dir / "canonical"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        for e, df in canon.items():
            df.to_parquet(d / f"{e}.parquet", index=False)
        readiness = rd.report(canon, rep)
        av = mp.available_fields(canon, rep)
        mods, kpis = cn.capabilities(av | ({"model"} if self.active_model() else set()))
        out = {"mapping_version": m["version"], "built": _now(), "translation": rep, "readiness": readiness, "available": sorted(av),
               "modules": mods, "kpis": {k: {kk: vv for kk, vv in v.items() if kk != "sql"} for k, v in kpis.items()}}
        (self.dir / "build.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        self.audit(actor, "data.build", {"version": m["version"], "rows": readiness["entities"], "readiness": readiness["score"],
                                         "gate": readiness["gate"]})
        return out

    def build_info(self):
        f = self.dir / "build.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def canonical(self, entity=None):
        d = self.dir / "canonical"
        if entity:
            p = d / f"{entity}.parquet"
            return pd.read_parquet(p) if p.exists() else None
        return {p.stem: pd.read_parquet(p) for p in d.glob("*.parquet")} if d.exists() else {}

    def _duck(self):
        import duckdb
        con = duckdb.connect()
        for e, df in self.canonical().items():
            con.register(e, df)
        con.execute("SET enable_external_access = false")
        return con

    def kpi(self, kid):
        info = self.build_info()
        if not info or kid not in cn.KPIS:
            raise TenantError("unknown KPI")
        if not info["kpis"][kid]["active"]:
            raise TenantError("KPI not available for this data: missing " + ", ".join(info["kpis"][kid]["missing"]))
        con = self._duck()
        try:
            return con.execute(cn.KPIS[kid][3]).df()
        finally:
            con.close()

    def validate(self, control=None, actor="system"):
        """Run every enabled KPI on the canonical data (a KPI that fails is disabled) and reconcile with the bank's control totals."""
        info = self.build_info() or self.build(actor)
        tx = self.canonical("transactions")
        res = {"kpis": {}, "reconciliation": {}}
        for kid, k in info["kpis"].items():
            if not k["active"]:
                continue
            try:
                df = self.kpi(kid)
                res["kpis"][kid] = {"ok": True, "rows": int(len(df))}
            except Exception as exc:
                res["kpis"][kid] = {"ok": False, "error": str(exc)[:200]}
        if control and tx is not None:
            rec = {}
            if "transactions" in control:
                rec["transactions"] = {"expected": control["transactions"], "found": int(len(tx))}
            if "frauds" in control and "is_fraud" in tx:
                rec["frauds"] = {"expected": control["frauds"], "found": int(tx["is_fraud"].fillna(0).sum())}
            if "amount" in control:
                rec["amount"] = {"expected": control["amount"], "found": round(float(tx["amount"].sum()), 2), "tolerance": 0.01 * max(1, len(tx)) ** 0.5}
            if "amount_tnd" in control and "amount_tnd" in tx:
                rec["amount_tnd"] = {"expected": control["amount_tnd"], "found": round(float(tx["amount_tnd"].sum()), 3),
                                     "tolerance": 0.01 * max(1, len(tx)) ** 0.5}
            for v in rec.values():
                v["ok"] = abs(v["found"] - v["expected"]) <= v.get("tolerance", 0)
            res["reconciliation"] = rec
        ok_kpi = all(v["ok"] for v in res["kpis"].values())
        ok_rec = all(v["ok"] for v in res["reconciliation"].values())
        res["passed"] = ok_kpi and ok_rec and info["readiness"]["gate"] != "red"
        res["validated"] = _now()
        (self.dir / "validation.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        cfg = self.config
        if res["passed"] and cfg["status"] in ("mapped", "validated"):
            cfg["status"] = "validated"
        cfg["dashboard"] = {"kpis": [k for k, v in res["kpis"].items() if v["ok"]],
                            "modules": [m for m, v in info["modules"].items() if v["active"]], "mapping_version": info["mapping_version"]}
        self._save_config(cfg)
        self.audit(actor, "data.validate", {"passed": res["passed"], "kpis_ok": sum(v["ok"] for v in res["kpis"].values()),
                                            "reconciliation": {k: v["ok"] for k, v in res["reconciliation"].items()}})
        return res

    def validation(self):
        f = self.dir / "validation.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    # ------------------------------------------------------------ approval and activation (human, admin only)
    def approve(self, approver, role="admin"):
        self._require(role, "admin")
        if not str(approver or "").strip():
            raise TenantError("a named approver is required")
        cfg, m = self.config, self.mapping()
        if cfg["status"] != "validated":
            raise TenantError("validate the data first")
        if self.open_flags(m):
            raise TenantError(f"{len(self.open_flags(m))} mapping decisions still need confirmation")
        cfg["status"] = "approved"
        cfg["approved"] = {"by": approver, "at": _now(), "mapping_version": m["version"],
                           "readiness": self.build_info()["readiness"]["score"]}
        self._save_config(cfg)
        self.audit(approver, "mapping.approve", cfg["approved"])
        return cfg

    def activate(self, approver, role="admin"):
        self._require(role, "admin")
        cfg = self.config
        if cfg["status"] != "approved" or cfg["approved"]["mapping_version"] != cfg["mapping_version"]:
            raise TenantError("approve the current mapping version first")
        self._minimise_raw()
        cfg["status"] = "active"
        cfg["activated"] = {"by": approver, "at": _now(), "mapping_version": cfg["mapping_version"]}
        self._save_config(cfg)
        self.audit(approver, "tenant.activate", cfg["activated"])
        return cfg

    def _minimise_raw(self):
        """Data minimisation: once a mapping is approved, excluded (sensitive) columns are erased from the stored raw zone."""
        m = self.mapping()
        b = self.dir / "raw" / self.config["batch"]
        for t, spec in m["tables"].items():
            p = b / f"{t}.parquet"
            if p.exists() and spec.get("excluded"):
                df = pd.read_parquet(p)
                df.drop(columns=[c for c in spec["excluded"] if c in df], errors="ignore").to_parquet(p, index=False)

    # ------------------------------------------------------------ model (candidate -> approved), alerts
    def train_model(self, actor, role="admin"):
        self._require(role, "admin")
        info = self.build_info()
        if not info or not info["modules"]["tenant_model"]["active"]:
            raise TenantError("labels are required to train a bank-specific model")
        version = len(list((self.dir / "models").glob("v*.json"))) + 1 if (self.dir / "models").exists() else 1
        model = tm.train(self.canonical("transactions"), self.canonical("auth_events"), version=version)
        if "error" in model:
            raise TenantError(model["error"])
        (self.dir / "models").mkdir(exist_ok=True)
        (self.dir / "models" / f"v{version}.json").write_text(json.dumps(model, indent=1, default=str), encoding="utf-8")
        self.audit(actor, "model.train", {"version": version, "metrics": model["metrics"], "baseline": model.get("baseline", {}).get("metrics")})
        return model

    def models(self):
        d = self.dir / "models"
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("v*.json"))] if d.exists() else []

    def approve_model(self, version, approver, role="admin"):
        self._require(role, "admin")
        if not str(approver or "").strip():
            raise TenantError("a named approver is required")
        p = self.dir / "models" / f"v{int(version)}.json"
        if not p.exists():
            raise TenantError("unknown model version")
        model = json.loads(p.read_text(encoding="utf-8"))
        model["status"] = "approved"
        model["approved"] = {"by": approver, "at": _now()}
        p.write_text(json.dumps(model, indent=1, default=str), encoding="utf-8")
        cfg = self.config
        cfg["model"] = int(version)
        self._save_config(cfg)
        self.audit(approver, "model.approve", {"version": int(version), "metrics": model["metrics"]})
        info = self.build(approver)                            # the "model" capability changes the module matrix
        cfg = self.config
        if cfg.get("dashboard"):
            cfg["dashboard"]["modules"] = [k for k, v in info["modules"].items() if v["active"]]
            self._save_config(cfg)
        return model

    def active_model(self):
        v = self.config.get("model")
        p = self.dir / "models" / f"v{v}.json"
        return json.loads(p.read_text(encoding="utf-8")) if v and p.exists() else None

    def score(self, tx=None, lang="fr"):
        """-> DataFrame transaction_id, timestamp, amount_tnd, score, score_kind, reasons."""
        tx = self.canonical("transactions") if tx is None else tx
        auth = self.canonical("auth_events")
        model = self.active_model()
        X = tm.features(tx, auth)
        if model:
            s, kind = tm.predict(model, X), "model"
            why = tm.reasons(model, X, lang)
        elif "risk_score" in tx and tx["risk_score"].notna().any():
            s, kind = tx["risk_score"].fillna(0).to_numpy(dtype=float), "bank_score"
            why = [[] for _ in range(len(tx))]
        else:
            b, _ = tm.behaviour_score(tx, auth)
            s, kind = b.to_numpy(), "behaviour"
            why = _behaviour_reasons(X, lang)
        cols = [c for c in ("transaction_id", "timestamp", "customer_id", "amount_tnd", "channel", "country", "is_fraud") if c in tx]
        out = tx[cols].copy()
        out["score"] = np.round(s, 4)
        out["score_kind"] = kind
        out["reasons"] = why
        return out

    def alerts(self, n=50, days=30, lang="fr"):
        sc = self.score(lang=lang)
        recent = sc[sc["timestamp"] >= sc["timestamp"].max() - pd.Timedelta(days=days)]
        return recent.sort_values("score", ascending=False).head(n)

    # ------------------------------------------------------------ institutional memory
    def build_memory(self, policies=None, actor="system"):
        pol_dir = self.dir / "policies"
        if policies:
            pol_dir.mkdir(exist_ok=True)
            for name, text in policies.items():
                safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:80]
                (pol_dir / safe).write_text(text, encoding="utf-8")
        allp = {p.name: p.read_text(encoding="utf-8") for p in pol_dir.glob("*")} if pol_dir.exists() else {}
        docs = rag.documents(self.canonical(), allp)
        rag.save(rag.build(docs), self.dir / "memory")
        self.audit(actor, "memory.build", {"documents": len(docs), "policies": len(allp)})
        return len(docs)

    def memory_search(self, q, k=5):
        return rag.search(rag.load(self.dir / "memory"), q, k)

    def memory_answer(self, q, lang="fr"):
        return rag.answer(rag.load(self.dir / "memory"), q, lang)

    # ------------------------------------------------------------ real-time events (webhook)
    def verify_signature(self, body: bytes, ts: str, signature: str, tolerance=300):
        try:
            if abs(time.time() - int(ts)) > tolerance:
                return False
        except (TypeError, ValueError):
            return False
        mac = hmac.new(self._secret()["webhook_secret"].encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, (signature or "").removeprefix("sha256="))

    def webhook_secret(self, role="admin"):
        self._require(role, "admin")
        return self._secret()["webhook_secret"]

    def ingest_events(self, records, actor="webhook", lang="fr"):
        """New transactions in the bank's own schema -> translated with the ACTIVE mapping -> appended -> scored."""
        cfg = self.config
        if cfg["status"] != "active":
            raise TenantError("tenant is not active")
        m = self.mapping(cfg["activated"]["mapping_version"])
        t = next((t for t, e in m["roles"].items() if e == "transactions"), None)
        if not records or len(records) > 1000:
            raise TenantError("1 to 1000 records per call")
        df = pd.DataFrame(records)
        missing = [s["source"] for s in m["tables"][t]["fields"].values() if s.get("source") and s["source"] not in df]
        req = {m["tables"][t]["fields"][f]["source"] for f in ("transaction_id", "timestamp", "amount") if f in m["tables"][t]["fields"]}
        if req & set(missing):
            raise TenantError(f"missing required source fields: {sorted(req & set(missing))}")
        for c in missing:
            df[c] = None
        sub = {"version": m["version"], "tables": {t: m["tables"][t]}, "roles": {t: "transactions"},
               "default_currency": m.get("default_currency"), "rates": m.get("rates")}
        canon, rep = mp.apply({t: df}, sub, self._secret()["salt"], m.get("rates"))
        new = canon["transactions"]
        old = self.canonical("transactions")
        dup = new["transaction_id"].isin(set(old["transaction_id"]))
        new = new[~dup]
        if len(new):
            allx = pd.concat([old, new], ignore_index=True)
            allx.to_parquet(self.dir / "canonical" / "transactions.parquet", index=False)
            scored = self.score(allx, lang=lang).tail(len(new))
        else:
            scored = pd.DataFrame(columns=["transaction_id", "score", "score_kind", "reasons"])
        self.audit(actor, "events.ingest", {"received": len(records), "new": int(len(new)), "duplicates": int(dup.sum())})
        return {"received": len(records), "new": int(len(new)), "duplicates": int(dup.sum()),
                "scores": scored[["transaction_id", "score", "score_kind", "reasons"]].to_dict("records")}


def _flag_id(f):
    return hashlib.sha1(json.dumps({k: f.get(k) for k in ("table", "field", "column", "en")}, sort_keys=True).encode()).hexdigest()[:10]


def flag_id(f):
    return _flag_id(f)


def _behaviour_reasons(X, lang):
    cols = [("z_amount", 1.5), ("new_country", 0.5), ("new_device", 0.5), ("new_merchant", 0.5), ("night", 0.5), ("count_24h", 3),
            ("sensitive_events_72h", 0.5), ("failed_logins_24h", 1)]
    hits = [(tm._label(c, lang), (X[c] >= thr).to_numpy()) for c, thr in cols if c in X]
    return [[lab for lab, m in hits if m[i]][:3] for i in range(len(X))]


def onboard_demo(tid, source, name, control=None, approver="démo", actor="démo", train=True):
    """Whole path for a simulated bank (used by the page's one-click demo and the tests). Returns the tenant and its admin key."""
    t, key = Tenant.create(tid, name, actor=actor, replace=True)
    t.ingest(source, actor=actor)
    t.discover(actor)
    t.propose_mapping(actor)
    t.update_mapping([{"op": "confirm_all"}], actor=approver)
    t.build(actor)
    t.validate(control, actor)
    if t.config["status"] == "validated":
        t.approve(approver)
        t.activate(approver)
    if train and t.build_info()["modules"]["tenant_model"]["active"]:
        mdl = t.train_model(actor)
        t.approve_model(mdl["version"], approver)
    t.build_memory(actor=actor)
    return t, key
