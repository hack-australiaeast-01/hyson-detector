"""Repoint Fabric items from dbo to the new schemas (app/layout.py), from the backed-up definitions in fabric/backups/.

    python fabric/repoint_items.py            # dry run: shows every change
    python fabric/repoint_items.py --apply    # updateDefinition + Power BI refresh, then verifies
Semantic models: only the source of each Direct Lake partition changes (schemaName / entityName / sourceLineageTag); model table names,
measures and the report stay identical. Copy job: destination schema dbo -> bronze.
"""
import base64
import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import layout  # noqa: E402

API = "https://api.fabric.microsoft.com/v1"
BK = ROOT / "fabric" / "backups"


def env(name):
    for line in (ROOT / "app" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')


def token(res="https://api.fabric.microsoft.com"):
    return subprocess.run(f"az account get-access-token --resource {res} --query accessToken -o tsv", shell=True, capture_output=True,
                          text=True, check=True).stdout.strip()


def wait(r, H):
    while r.status_code == 202 and r.headers.get("Location"):
        time.sleep(int(r.headers.get("Retry-After", 3)))
        r = requests.get(r.headers["Location"], headers=H, timeout=60)
        st = r.json().get("status") if r.content else None
        if st in ("Succeeded", "Failed"):
            if st == "Failed":
                raise SystemExit(r.text[:500])
            break
    return r


def latest(name):
    return json.loads(sorted(BK.glob(f"{name}.2*.json"))[-1].read_text(encoding="utf-8-sig"))


def repoint_tmdl(txt):
    changes = []

    def part(m):
        entity, schema = m.group("entity"), m.group("schema")
        if schema != "dbo" or entity not in layout.TABLES:
            return m.group(0)
        s, t, *_ = layout.TABLES[entity]
        changes.append(f"dbo.{entity} -> {s}.{t}")
        return m.group(0).replace(f"entityName: {entity}", f"entityName: {t}").replace("schemaName: dbo", f"schemaName: {s}")
    txt = re.sub(r"entityName: (?P<entity>\w+)\s*\n(?P<pre>[ \t]*)schemaName: (?P<schema>\w+)", part, txt)
    for entity, (s, t, *_) in layout.TABLES.items():
        txt = txt.replace(f"sourceLineageTag: [dbo].[{entity}]", f"sourceLineageTag: [{s}].[{t}]")
    return txt, changes


def main(apply):
    ws = env("FABRIC_WORKSPACE_ID")
    H = {"Authorization": f"Bearer {token()}"}
    items = {i["displayName"]: i for i in requests.get(f"{API}/workspaces/{ws}/items", headers=H, timeout=60).json()["value"]}
    plans = []
    for name in ("sm_fraud_copilot", "Saitaflex-model"):
        d = latest(name)
        parts, changes = [], []
        for p in d["definition"]["parts"]:
            if p["path"] == ".platform":
                continue
            txt = base64.b64decode(p["payload"]).decode("utf-8")
            if p["path"].endswith(".tmdl"):
                txt, ch = repoint_tmdl(txt)
                changes += ch
            parts.append({"path": p["path"], "payload": base64.b64encode(txt.encode("utf-8")).decode(), "payloadType": "InlineBase64"})
        plans.append((name, items[name]["id"], {"definition": {"parts": parts}}, changes))
    d = latest("cj_bronze_load")
    parts, changes = [], []
    for p in d["definition"]["parts"]:
        if p["path"] == ".platform":
            continue
        txt = base64.b64decode(p["payload"]).decode("utf-8")
        if p["path"] == "copyjob-content.json":
            c = json.loads(txt)
            for a in c.get("activities", []):
                ds = a["properties"]["destination"]["datasetSettings"]
                if ds.get("schema") == "dbo" and ds.get("table") in layout.TABLES:
                    s, t, *_ = layout.TABLES[ds["table"]]
                    changes.append(f"dbo.{ds['table']} -> {s}.{t}")
                    ds["schema"], ds["table"] = s, t
            txt = json.dumps(c, indent=2)
        parts.append({"path": p["path"], "payload": base64.b64encode(txt.encode("utf-8")).decode(), "payloadType": "InlineBase64"})
    plans.append(("cj_bronze_load", items["cj_bronze_load"]["id"], {"definition": {"parts": parts}}, changes))
    for name, iid, body, ch in plans:
        print(f"{name}: {len(ch)} changes", ch[:4], "…" if len(ch) > 4 else "")
    if not apply:
        return
    for name, iid, body, ch in plans:
        r = requests.post(f"{API}/workspaces/{ws}/items/{iid}/updateDefinition", headers=H, json=body, timeout=120)
        if r.status_code >= 400:
            raise SystemExit(f"{name}: {r.status_code} {r.text[:400]}")
        wait(r, H)
        print("updated", name)
    PH = {"Authorization": f"Bearer {token('https://analysis.windows.net/powerbi/api')}"}
    for name in ("sm_fraud_copilot", "Saitaflex-model"):
        iid = items[name]["id"]
        r = requests.post(f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{iid}/refreshes", headers=PH, json={"type": "full"}, timeout=60)
        print("refresh", name, r.status_code)
        for _ in range(60):
            time.sleep(5)
            h = requests.get(f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{iid}/refreshes?$top=1", headers=PH, timeout=60).json()["value"][0]
            if h["status"] in ("Completed", "Failed", "Disabled", "Cancelled"):
                print("  ", name, h["status"], (h.get("serviceExceptionJson") or "")[:300])
                break


if __name__ == "__main__":
    main("--apply" in sys.argv)
