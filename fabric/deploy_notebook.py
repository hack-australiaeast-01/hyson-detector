"""Deploy a local notebook to the Fabric workspace and (optionally) run it as a job, polling to completion.

    python fabric/deploy_notebook.py notebooks/05_quality_star.ipynb --run
Auth: the Azure CLI login (az login). Workspace / lakehouse ids come from app/.env (FABRIC_WORKSPACE_ID).
"""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.fabric.microsoft.com/v1"


def env(name):
    if os.getenv(name):
        return os.environ[name]
    for line in (ROOT / "app" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"{name} missing")


def token():
    return subprocess.run("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv",
                          shell=True, capture_output=True, text=True, check=True).stdout.strip()


def call(method, url, **kw):
    r = requests.request(method, url, headers={"Authorization": f"Bearer {token()}"}, timeout=60, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {url} -> {r.status_code} {r.text[:400]}")
    return r


def wait_lro(r):
    while r.status_code == 202 and r.headers.get("Location"):
        time.sleep(int(r.headers.get("Retry-After", 5)))
        r = call("GET", r.headers["Location"])
        if r.json().get("status") in ("Succeeded", "Failed"):
            if r.json()["status"] == "Failed":
                raise SystemExit(f"operation failed: {r.text[:400]}")
            break
    return r


def main():
    path, run = Path(sys.argv[1]), "--run" in sys.argv
    ws, name = env("FABRIC_WORKSPACE_ID"), path.stem
    part = {"path": "notebook-content.ipynb", "payload": base64.b64encode(path.read_bytes()).decode(), "payloadType": "InlineBase64"}
    items = call("GET", f"{API}/workspaces/{ws}/items?type=Notebook").json()["value"]
    item = next((i for i in items if i["displayName"] == name), None)
    if item:
        backup = ROOT / "fabric" / "backups"
        backup.mkdir(exist_ok=True)
        r = wait_lro(call("POST", f"{API}/workspaces/{ws}/items/{item['id']}/getDefinition?format=ipynb"))
        (backup / f"{name}.{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps(r.json()), encoding="utf-8")
        wait_lro(call("POST", f"{API}/workspaces/{ws}/items/{item['id']}/updateDefinition",
                      json={"definition": {"format": "ipynb", "parts": [part]}}))
        print("updated", name, item["id"])
    else:
        wait_lro(call("POST", f"{API}/workspaces/{ws}/items",
                      json={"displayName": name, "type": "Notebook", "definition": {"format": "ipynb", "parts": [part]}}))
        items = call("GET", f"{API}/workspaces/{ws}/items?type=Notebook").json()["value"]
        item = next(i for i in items if i["displayName"] == name)
        print("created", name, item["id"])
    if not run:
        return
    r = call("POST", f"{API}/workspaces/{ws}/items/{item['id']}/jobs/instances?jobType=RunNotebook")
    loc, t0 = r.headers["Location"], time.time()
    print("job started")
    while True:
        time.sleep(20)
        s = call("GET", loc).json()
        print(f"  {time.time() - t0:5.0f}s {s.get('status')}", flush=True)
        if s.get("status") in ("Completed", "Failed", "Cancelled", "Deduped"):
            if s.get("failureReason"):
                print(json.dumps(s["failureReason"], indent=1)[:2000])
            sys.exit(0 if s["status"] == "Completed" else 1)


if __name__ == "__main__":
    main()
