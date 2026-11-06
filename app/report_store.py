"""Report Review & Approval Workflow + Export & Document Management.

Reports are stored per scope (the Hyson bank under app/data/reports, each onboarded bank inside its own tenant folder), so a
bank never sees another bank's reports. Each change creates a new version (JSON bundle, re-renderable identically); a named
employee approves one version; the approved files are stored with their SHA-256; every step goes to a hash-chained audit log.
"""
import copy
import difflib
import hashlib
import json
import re
import secrets
from datetime import datetime
from pathlib import Path

import report_compose as RC
import report_i18n as I
import report_insights as RI
import report_interpret as RP
import report_render as RR
import report_sources as RS

DEFAULT_SETTINGS = {"institution": None, "color": "#1E5BD8", "logo": None, "terminology": {}, "departments": {}, "confidentiality_labels": {},
                    "footer": "", "section_titles": {}, "ai_writer": True}


def _now():
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, src, root=None):
        self.src = src
        self.dir = Path(root) if root else Path(src.dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ settings, templates, audit
    def settings(self):
        f = self.dir / "settings.json"
        return {**DEFAULT_SETTINGS, **(json.loads(f.read_text(encoding="utf-8")) if f.exists() else {})}

    def save_settings(self, s, actor):
        keep = {k: s.get(k, v) for k, v in DEFAULT_SETTINGS.items()}
        (self.dir / "settings.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        self.audit(actor, "settings.save", {k: v for k, v in keep.items() if k != "logo"})

    def templates(self):
        d = self.dir / "templates"
        return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))} if d.exists() else {}

    def save_template(self, name, spec, actor):
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:60] or "template"
        (self.dir / "templates").mkdir(exist_ok=True)
        keep = {k: spec[k] for k in ("type", "audience", "depth", "format", "confidentiality", "sections", "focus", "compare", "lang") if k in spec}
        (self.dir / "templates" / f"{safe}.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        self.audit(actor, "template.save", {"name": safe, **keep})
        return safe

    def audit(self, actor, action, details=None):
        if self.src.tenant is not None:                       # a bank's report steps join that bank's own audit chain
            return self.src.tenant.audit(actor, "report." + action, details)
        f = self.dir / "audit.jsonl"
        prev = "0" * 64
        if f.exists():
            lines = f.read_text(encoding="utf-8").strip().splitlines()
            prev = json.loads(lines[-1])["hash"] if lines else prev
        body = {"ts": _now(), "actor": str(actor)[:80], "action": "report." + action, "details": details or {}, "prev": prev}
        body["hash"] = hashlib.sha256((prev + json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)).encode()).hexdigest()
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, ensure_ascii=False, default=str) + "\n")

    # ------------------------------------------------------------ reports
    def _rdir(self, rid):
        if not re.fullmatch(r"R\d{8}-\d{6}-[0-9a-f]{4}", rid or ""):
            raise ValueError("invalid report id")
        return self.dir / rid

    def list(self):
        out = []
        for d in sorted(self.dir.glob("R*"), reverse=True):
            f = d / "report.json"
            if f.exists():
                r = json.loads(f.read_text(encoding="utf-8"))
                out.append({k: r.get(k) for k in ("id", "title", "created", "author", "status", "versions", "approved", "type", "request")})
        return out

    def get(self, rid):
        return json.loads((self._rdir(rid) / "report.json").read_text(encoding="utf-8"))

    def version(self, rid, v=None):
        r = self.get(rid)
        v = v or r["versions"]
        return json.loads((self._rdir(rid) / f"v{v}.json").read_text(encoding="utf-8"))

    def _build(self, spec, use_ai):
        a = RI.run(spec, self.src)
        settings = self.settings()
        doc = RC.compose(a, settings)
        ai = {"used": False}
        if use_ai and settings.get("ai_writer", True):
            doc, ai = RC.ai_write(a, doc)
        return RR.bundle(a, doc, ai)

    def create(self, spec, author, use_ai=True):
        if spec.get("questions"):
            raise ValueError(" ".join(spec["questions"]))
        rid = datetime.now().strftime("R%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        d = self._rdir(rid)
        d.mkdir(parents=True)
        b = self._build(spec, use_ai)
        meta = {"id": rid, "title": b["doc"]["meta"]["title"], "created": _now(), "author": author, "status": "draft", "versions": 0, "approved": None,
                "type": spec["type"], "request": spec.get("request", ""), "comments": [], "history": []}
        (d / "report.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        self._new_version(rid, b, author, I.tr(spec["lang"], "Première version générée", "First generated version", "النسخة الأولى"))
        self.audit(author, "create", {"id": rid, "type": spec["type"], "period": spec["period"], "audience": spec["audience"],
                                      "ai_writer": b["ai"].get("used"), "checks_failed": [c["name"] for c in b["checks"] if not c["ok"]]})
        return rid

    def _new_version(self, rid, b, author, note):
        r = self.get(rid)
        v = r["versions"] + 1
        b["version"] = v
        (self._rdir(rid) / f"v{v}.json").write_text(json.dumps(b, ensure_ascii=False, default=str), encoding="utf-8")
        r["versions"], r["status"] = v, "draft"
        r["history"].append({"v": v, "at": _now(), "by": author, "note": note})
        (self._rdir(rid) / "report.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        return v

    def edit_section(self, rid, sid, text, author):
        """Employee rewrite of a section: stored as an employee statement, previous text kept in the previous version."""
        b = copy.deepcopy(self.version(rid))
        sec = next(s for s in b["doc"]["sections"] if s["id"] == sid)
        refs = sorted(set(re.findall(r"\[([FITE]\d+)\]", text)))
        sec["blocks"] = [{"t": "p", "text": para.strip(), "kind": "employee", "refs": refs} for para in text.split("\n\n") if para.strip()] + \
            [blk for blk in sec["blocks"] if blk["t"] in ("table", "chart", "kpis", "register", "checks")]
        sec["edited"] = author
        v = self._new_version(rid, b, author, I.tr(b["spec"]["lang"], f"Section « {sec['title']} » modifiée", f"Section \"{sec['title']}\" edited",
                                                   f"تعديل قسم «{sec['title']}»"))
        self.audit(author, "edit_section", {"id": rid, "section": sid, "version": v})
        return v

    def regenerate(self, rid, author, changes=None, only_section=None, use_ai=True):
        """Re-run the whole pipeline with changed settings (audience, period, depth, sections…); optionally keep every other section."""
        old = self.version(rid)
        spec = {**old["spec"], **(changes or {})}
        if changes and ("period" in changes or "cadence" in changes) and spec.get("compare"):
            spec["previous"] = [str(x) for x in RP.previous(tuple(spec["period"]), spec.get("cadence", "custom"))]
        if changes and "type" in changes:
            spec["purpose"] = RP.purpose(spec, spec["lang"])
        b = self._build(spec, use_ai)
        if only_section:
            new_sec = next((s for s in b["doc"]["sections"] if s["id"] == only_section), None)
            keep = copy.deepcopy(old)
            if new_sec is not None:
                keep["doc"]["sections"] = [new_sec if s["id"] == only_section else s for s in keep["doc"]["sections"]]
                for k in ("facts", "tables", "insights", "charts", "checks", "limits"):
                    have = {x["id"] for x in keep[k]} if k not in ("checks", "limits") else None
                    if have is not None:
                        keep[k] += [x for x in b[k] if x["id"] not in have]
            b = keep
        note = (I.tr(spec["lang"], "Section régénérée : ", "Section regenerated: ", "إعادة إنشاء قسم: ") + only_section) if only_section else \
            I.tr(spec["lang"], "Rapport régénéré", "Report regenerated", "إعادة إنشاء التقرير") + (f" ({', '.join(changes)})" if changes else "")
        v = self._new_version(rid, b, author, note)
        self.audit(author, "regenerate", {"id": rid, "version": v, "changes": changes or {}, "section": only_section})
        return v

    def comment(self, rid, author, text, section=None):
        r = self.get(rid)
        r["comments"].append({"at": _now(), "by": author, "section": section, "text": text[:2000], "version": r["versions"]})
        (self._rdir(rid) / "report.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        self.audit(author, "comment", {"id": rid, "section": section})

    def compare(self, rid, v1, v2):
        def text(b):
            lines = []
            for s in b["doc"]["sections"]:
                lines.append(f"## {s['title']}")
                for blk in s["blocks"]:
                    if blk.get("text"):
                        lines.append(blk["text"])
                    elif blk["t"] in ("finding", "risk"):
                        i = next((x for x in b["insights"] if x["id"] == blk["ref"]), None)
                        if i:
                            lines.append(f"{i['title'][b['spec']['lang']]} — {i['what'][b['spec']['lang']]}")
                    elif blk["t"] == "bullets":
                        lines += [f"• {x['text']}" for x in blk["items"]]
            return lines
        return "\n".join(difflib.unified_diff(text(self.version(rid, v1)), text(self.version(rid, v2)), f"v{v1}", f"v{v2}", lineterm=""))

    def approve(self, rid, approver, role="admin"):
        if role not in ("admin", "approver"):
            raise PermissionError("only an authorised employee can approve")
        if not str(approver or "").strip():
            raise ValueError("a named approver is required")
        r = self.get(rid)
        b = self.version(rid)
        errors = [c["name"] for c in b["checks"] if not c["ok"] and c["level"] == "error"]
        if errors:
            raise ValueError("blocking verification checks failed: " + ", ".join(errors))
        digest = hashlib.sha256(json.dumps(b, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        approval = {"by": approver, "at": _now(), "version": r["versions"], "hash": digest}
        out = self._rdir(rid) / "approved"
        out.mkdir(exist_ok=True)
        files = {}
        for fmt in I.FORMATS:
            data, _ = RR.render(b, fmt, draft=False, approval=approval)
            name = f"{rid}_v{r['versions']}.{fmt}"
            (out / name).write_bytes(data)
            files[fmt] = {"file": name, "sha256": hashlib.sha256(data).hexdigest()}
        approval["files"] = files
        r["status"], r["approved"] = "approved", approval
        (self._rdir(rid) / "report.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        self.audit(approver, "approve", {"id": rid, "version": approval["version"], "hash": digest, "files": files})
        return approval

    def export(self, rid, fmt, v=None):
        """Approved version -> the stored approved file; any other version -> rendered as a DRAFT."""
        r = self.get(rid)
        v = v or r["versions"]
        ap = r.get("approved")
        if ap and ap["version"] == v and fmt in ap.get("files", {}):
            p = self._rdir(rid) / "approved" / ap["files"][fmt]["file"]
            return p.read_bytes(), _mime(fmt), ap["files"][fmt]["file"]
        data, mime = RR.render(self.version(rid, v), fmt, draft=True)
        return data, mime, f"{rid}_v{v}_DRAFT.{fmt}"


def _mime(fmt):
    return {"pdf": "application/pdf", "html": "text/html", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[fmt]


def store(sid, root=None):
    return Store(RS.get(sid), root)
