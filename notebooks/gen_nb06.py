"""Generates notebooks/06_lakehouse_layout.ipynb — reorganises lh_fraud from dbo into medallion + purpose schemas.

    python notebooks/gen_nb06.py copy       # phase 1: create schemas, copy every table, verify, write meta.table_catalog
    python notebooks/gen_nb06.py finalize   # phase 2 (after every consumer points to the new names): drop dbo tables, move Files
The mapping comes from app/layout.py (single source of truth).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import layout  # noqa: E402

PHASE = sys.argv[1] if len(sys.argv) > 1 else "copy"
assert PHASE in ("copy", "finalize")
CELLS = []


def md(s):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": s.strip("\n").splitlines(keepends=True)})


def code(s):
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip("\n").splitlines(keepends=True)})


code('''
%%configure -f
{"defaultLakehouse": {"name": "lh_fraud"}}
''')
md(f'''
# 06 · Lakehouse layout — from `dbo` to medallion + purpose schemas (phase **{PHASE}**)

| Schema | Role |
|---|---|
''' + "\n".join(f"| `{s}` | {fr} |" for s, (fr, en) in layout.LAYERS.items()) + '''

`dbo` remains the default schema and ends empty. Phase **copy** creates the schemas, copies every table (Delta, V-Order) and verifies
row counts and columns; phase **finalize** runs only after the app, notebooks, copy job and Power BI model point to the new names:
it re-verifies, drops the `dbo` tables and reorganises `Files/`. Every step is written to `meta.migration_log`.
''')
code(f'''
import json
from datetime import datetime
from pyspark.sql import functions as F

PHASE = "{PHASE}"
TABLES = json.loads(r\'\'\'{json.dumps(layout.TABLES, ensure_ascii=False)}\'\'\')
LAYERS = json.loads(r\'\'\'{json.dumps(layout.LAYERS, ensure_ascii=False)}\'\'\')
FILES = json.loads(r\'\'\'{json.dumps(layout.FILES)}\'\'\')
RUN = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
log = []

def note(step, obj, status, detail=""):
    log.append((RUN, PHASE, step, obj, status, str(detail)[:500]))
    print(f"{{status:8s}} {{step:10s}} {{obj}} {{detail}}")

def exists(name):
    try:
        spark.table(name).limit(0).collect()
        return True
    except Exception:
        return False
''')
md("## Schemas")
code('''
for s in list(LAYERS):
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {s}")
    note("schema", s, "OK")
''')
if PHASE == "copy":
    md("## Copy every table and verify (rows + columns)")
    code('''
for old, (schema, new, producer, desc) in TABLES.items():
    src, dst = f"dbo.{old}", f"{schema}.{new}"
    if not exists(src):
        note("copy", dst, "SKIP", "source absent (already migrated?)")
        continue
    df = spark.table(src)
    df.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(dst)
    a, b = spark.table(src).count(), spark.table(dst).count()
    same_cols = spark.table(src).columns == spark.table(dst).columns
    note("copy", f"{src} -> {dst}", "OK" if (a == b and same_cols) else "MISMATCH", f"{a} / {b} rows, columns {'=' if same_cols else '≠'}")
assert not [l for l in log if l[4] == "MISMATCH"], "verification failed"
''')
else:
    md("## Finalize: re-verify, drop `dbo`, reorganise `Files/`")
    code('''
for old, (schema, new, producer, desc) in TABLES.items():
    src, dst = f"dbo.{old}", f"{schema}.{new}"
    if not exists(src):
        note("drop", src, "SKIP", "already gone")
        continue
    a, b = spark.table(src).count(), spark.table(dst).count()
    if a != b:
        note("drop", src, "KEPT", f"{a} vs {b} rows — not dropped")
        continue
    spark.sql(f"DROP TABLE {src}")
    note("drop", src, "OK", f"{b} rows now only in {dst}")
assert not [l for l in log if l[4] == "KEPT"], "some dbo tables kept"

def mv(a, b):
    try:
        if notebookutils.fs.exists(a):
            notebookutils.fs.mkdirs("/".join(b.split("/")[:-1]))
            notebookutils.fs.mv(a, b, True)
            note("files", f"{a} -> {b}", "OK")
        else:
            note("files", a, "SKIP", "absent")
    except Exception as exc:
        note("files", a, "ERROR", exc)
for old, new in FILES.items():
    mv(f"Files/{old}", f"Files/{new}")
for d in ["landing/partner_feeds", "exports", "feedback", "ml"]:
    notebookutils.fs.mkdirs(f"Files/{d}")
notebookutils.fs.put("Files/README.md", """# lh_fraud · Files
- `landing/partner_feeds/` — files received from other banks, before validation (page « Nouvelle source de données »)
- `exports/app_snapshot/` — Gold snapshot for the hosted demo app
- `exports/submission/` — score file for the jury (brief §14)
- `feedback/analyst_decisions/` — analyst decisions written back by the app (hash-chained journal)
- `ml/robustness/` — backtest summary and runtime versions (notebook 04)
Tables: see meta.table_catalog (bronze · quality · silver · gold · ml · mart · serving · meta).
""", True)
note("files", "Files/README.md", "OK")
''')
md("## Catalog")
code('''
rows = []
for old, (schema, new, producer, desc) in TABLES.items():
    name = f"{schema}.{new}"
    n = spark.table(name).count() if exists(name) else None
    cols = len(spark.table(name).columns) if exists(name) else None
    rows.append((schema, new, name, LAYERS[schema][1], desc, producer, f"dbo.{old}", n, cols, RUN))
spark.createDataFrame(rows, "schema_name string, table_name string, full_name string, layer_role string, description string, "
                            "producer string, previous_name string, row_count long, column_count int, cataloged_at string") \\
     .write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("meta.table_catalog")
spark.createDataFrame(log, "run_ts string, phase string, step string, object string, status string, detail string") \\
     .write.mode("append").format("delta").saveAsTable("meta.migration_log")
display(spark.table("meta.table_catalog").orderBy("schema_name", "table_name"))
print("schemas:", [r.namespace if hasattr(r, "namespace") else r[0] for r in spark.sql("SHOW SCHEMAS").collect()])
''')

nb = {"cells": CELLS, "metadata": {"kernel_info": {"name": "synapse_pyspark"},
                                   "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
out = Path(__file__).parent / "06_lakehouse_layout.ipynb"
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", out, "phase", PHASE)
