"""Schema discovery for any bank source: load tables, profile columns, find candidate keys and foreign keys.

Sources: a SQLite database, a folder of CSV / JSON-lines / Parquet files, single files, or uploaded (name, bytes) pairs.
Only statistics leave this module (never raw rows): kinds, null rates, cardinality, low-cardinality code values, numeric ranges.
"""
import io
import json
import re
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

MAX_ROWS = 2_000_000
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
DECIMAL_COMMA = r"^-?\d{1,3}(?:[ .]\d{3})*,\d+$|^-?\d+,\d+$"
DMY = re.compile(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{4}")
ISO2 = set("AD AE AF AL AM AO AR AT AU AZ BA BD BE BF BG BH BI BJ BR BY CA CD CF CG CH CI CL CM CN CO CR CU CY CZ DE DJ DK DO DZ EC EE EG ER ES "
           "ET FI FR GA GB GE GH GM GN GQ GR GT GW HK HN HR HT HU ID IE IL IN IQ IR IS IT JM JO JP KE KG KH KM KR KW KZ LA LB LK LR LS LT LU "
           "LV LY MA MC MD ME MG MK ML MM MN MR MT MU MV MW MX MY MZ NA NE NG NI NL NO NP NZ OM PA PE PH PK PL PS PT PY QA RO RS RU RW SA SD "
           "SE SG SI SK SL SN SO SS SV SY SZ TD TG TH TJ TM TN TR TW TZ UA UG US UY UZ VE VN YE ZA ZM ZW".split())
ISO3 = {"TUN": "TN", "FRA": "FR", "ITA": "IT", "DEU": "DE", "ESP": "ES", "BEL": "BE", "GBR": "GB", "USA": "US", "CHN": "CN", "TUR": "TR",
        "ARE": "AE", "EGY": "EG", "DZA": "DZ", "LBY": "LY", "MAR": "MA", "SAU": "SA", "CAN": "CA", "NLD": "NL", "CHE": "CH", "QAT": "QA",
        "ROU": "RO", "RUS": "RU", "PRT": "PT", "AUT": "AT", "SWE": "SE", "NOR": "NO", "DNK": "DK", "POL": "PL", "GRC": "GR", "JPN": "JP",
        "IND": "IN", "BRA": "BR", "MLT": "MT", "LBN": "LB", "JOR": "JO", "KWT": "KW", "BHR": "BH", "OMN": "OM", "SEN": "SN", "CIV": "CI"}
CURRENCIES = {"TND", "EUR", "USD", "GBP", "CHF", "MAD", "DZD", "LYD", "SAR", "AED", "QAR", "TRY", "CAD", "JPY", "CNY", "EGP", "XOF"}


# ---------------------------------------------------------------- loading
def _read_file(name, data):
    """name: file name, data: bytes or path. Returns {table: DataFrame}."""
    ext = Path(name).suffix.lower()
    stem = Path(name).stem
    buf = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
    if ext in (".sqlite", ".db", ".sqlite3"):
        if isinstance(data, (bytes, bytearray)):
            tmp = Path(tempfile.mkstemp(suffix=".sqlite")[1])
            tmp.write_bytes(data)
            path = tmp
        else:
            path = Path(data)
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            out = {n: pd.read_sql(f'SELECT * FROM "{n}" LIMIT {MAX_ROWS}', con) for n in names}
        finally:
            con.close()
        return out
    if ext in (".csv", ".txt"):
        raw = buf.read() if hasattr(buf, "read") else Path(buf).read_bytes()
        head = raw[:4096].decode("utf-8", "ignore")
        sep = max([",", ";", "\t", "|"], key=head.count)
        return {stem: pd.read_csv(io.BytesIO(raw), sep=sep, dtype=str, keep_default_na=False, na_values=[""], nrows=MAX_ROWS)}
    if ext in (".jsonl", ".ndjson"):
        return {stem: pd.read_json(buf, lines=True, dtype=False, nrows=MAX_ROWS)}
    if ext == ".json":
        raw = json.loads(buf.read() if hasattr(buf, "read") else Path(buf).read_text(encoding="utf-8"))
        rec = raw.get("records", raw.get("data", raw)) if isinstance(raw, dict) else raw
        return {stem: pd.json_normalize(rec)}
    if ext == ".parquet":
        return {stem: pd.read_parquet(buf).head(MAX_ROWS)}
    raise ValueError(f"Format non pris en charge : {ext}")


def load(source):
    """source: path (file / folder / sqlite) or list of (name, bytes). Returns {table_name: DataFrame}."""
    tables = {}
    if isinstance(source, (list, tuple)):
        for name, data in source:
            tables.update(_read_file(name, data))
    else:
        p = Path(source)
        files = sorted(x for x in p.iterdir() if x.is_file()) if p.is_dir() else [p]
        for f in files:
            if f.suffix.lower() in (".csv", ".txt", ".jsonl", ".ndjson", ".json", ".parquet", ".sqlite", ".db", ".sqlite3"):
                tables.update(_read_file(f.name, f))
    return {re.sub(r"[^A-Za-z0-9_]+", "_", k): v for k, v in tables.items()}


# ---------------------------------------------------------------- column profiling
def _strs(s):
    s = s.dropna()
    s = s.astype(str).str.strip()
    return s[s != ""]


def to_number(s):
    """Numbers written '1 234,500', '1.234,50', '1234.5' or numeric dtype -> float."""
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").astype(float)
    t = s.astype(str).str.strip().str.replace("\u00a0", " ", regex=False).str.replace("\u202f", " ", regex=False)
    comma = t.str.match(DECIMAL_COMMA)
    t = t.where(~comma, t.str.replace(r"[ .]", "", regex=True).str.replace(",", ".", regex=False))
    return pd.to_numeric(t.str.replace(" ", "", regex=False), errors="coerce")


def kind_of(s, sample=5000):
    """Value kind of a column, from values only: epoch_ms / epoch_s / datetime / number / bool / country2 / country3 / currency /
    email / code / id / text / empty."""
    v = _strs(s)
    if v.empty:
        return "empty"
    v = v.sample(min(sample, len(v)), random_state=0) if len(v) > sample else v
    up = v.str.upper()
    if v.map(lambda x: bool(EMAIL.match(x))).mean() > 0.8:
        return "email"
    if up.isin({"0", "1", "TRUE", "FALSE", "YES", "NO", "OUI", "NON", "Y", "N"}).mean() == 1 and v.nunique() <= 2:
        return "bool"
    num = to_number(v)
    if num.notna().mean() > 0.97:
        if (num.dropna() % 1 == 0).all():
            med = num.median()
            if 1e12 <= med <= 4e12:
                return "epoch_ms"
            if 9e8 <= med <= 4e9 and v.nunique() > 0.5 * len(v):
                return "epoch_s"
        if v.str.match(r"^0\d$").any() and v.nunique() <= 30:    # '00', '05': codes, not numbers
            return "code"
        return "number"
    if up.isin(CURRENCIES).mean() > 0.9:
        return "currency"
    if v.str.len().eq(2).mean() > 0.95 and up.isin(ISO2).mean() > 0.9:
        return "country2"
    if v.str.len().eq(3).mean() > 0.95 and up.isin(ISO3).mean() > 0.9:
        return "country3"
    if v.str.match(r"^\d{4}-\d{2}-\d{2}|^\d{1,2}[/.-]\d{1,2}[/.-]\d{4}").mean() > 0.9:
        return "datetime"
    if v.nunique() <= 40 and v.nunique() <= max(3, 0.05 * len(v)):
        return "code"
    if v.str.match(r"^[A-Za-z0-9_\-:]+$").mean() > 0.95 and v.str.len().median() <= 40:
        return "id"
    return "text"


def parse_datetime(s, kind=None):
    """-> (UTC-naive datetime Series, format label, dayfirst assumption flag)."""
    kind = kind or kind_of(s)
    if kind == "epoch_ms":
        return pd.to_datetime(to_number(s), unit="ms", errors="coerce"), "epoch_ms", False
    if kind == "epoch_s":
        return pd.to_datetime(to_number(s), unit="s", errors="coerce"), "epoch_s", False
    t = s.astype(str).str.strip()
    dmy = t.str.match(DMY).mean() > 0.5
    ambiguous = False
    if dmy:
        first = pd.to_numeric(t.str.extract(r"^(\d{1,2})")[0], errors="coerce")
        second = pd.to_numeric(t.str.extract(r"^\d{1,2}[/.-](\d{1,2})")[0], errors="coerce")
        dayfirst = not ((second > 12).any() and not (first > 12).any())
        ambiguous = not (first > 12).any() and not (second > 12).any()
        out = pd.to_datetime(t, errors="coerce", dayfirst=dayfirst, format="mixed")
        fmt = "dd/mm/yyyy" if dayfirst else "mm/dd/yyyy"
    else:
        out = pd.to_datetime(t, errors="coerce", format="mixed", utc=t.str.contains(r"Z$|[+-]\d{2}:?\d{2}$").any())
        fmt = "iso8601"
    if getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_convert("UTC").dt.tz_localize(None)
    return out, fmt, ambiguous


def profile_column(s):
    v = _strs(s)
    k = kind_of(s)
    info = {"kind": k, "dtype": str(s.dtype), "rows": int(len(s)), "null_rate": round(1 - len(v) / max(len(s), 1), 4),
            "distinct": int(v.nunique()), "unique": bool(len(v) == len(s) and v.nunique() == len(v))}
    if k in ("code", "bool", "currency", "country2", "country3") or v.nunique() <= 12:
        info["values"] = v.value_counts().head(15).index.astype(str).tolist()
    if k in ("number", "epoch_ms", "epoch_s"):
        x = to_number(v)
        info["stats"] = {"min": float(x.min()), "median": float(x.median()), "max": float(x.max()),
                         "integer": bool((x.dropna() % 1 == 0).all())}
    if k == "datetime":
        d, fmt, amb = parse_datetime(v, k)
        info["datetime"] = {"format": fmt, "ambiguous_day_month": amb, "parsed": round(float(d.notna().mean()), 4),
                            "min": str(d.min())[:19], "max": str(d.max())[:19]}
    if v.str.fullmatch(r"\d{13,19}").mean() > 0.9 and v.head(200).map(_luhn).mean() > 0.9:
        info["pan_like"] = True                    # raw card numbers: always hashed, never stored in clear
    return info


def _luhn(x):
    d = [int(c) for c in str(x)][::-1]
    return bool(d) and (sum(d[0::2]) + sum(sum(divmod(2 * c, 10)) for c in d[1::2])) % 10 == 0


def profile(tables):
    return {t: {"rows": int(len(df)), "columns": {c: profile_column(df[c]) for c in df.columns}} for t, df in tables.items()}


def relations(tables, prof, min_overlap=0.9):
    """Foreign keys by inclusion dependency: values of A.x found in a unique column B.k (>= min_overlap of A's distinct values)."""
    keys = {(t, c): set(_strs(tables[t][c]).unique()) for t in tables for c, p in prof[t]["columns"].items()
            if p["unique"] and p["kind"] in ("id", "code", "number", "text") and p["rows"] > 1}
    rels = []
    for t, df in tables.items():
        for c, p in prof[t]["columns"].items():
            if p["kind"] not in ("id", "text", "code", "number") or p["distinct"] < 2:
                continue
            vals = set(_strs(df[c]).unique())
            for (kt, kc), kv in keys.items():
                if kt == t:
                    continue
                inter = len(vals & kv)
                if inter and inter / len(vals) >= min_overlap:
                    rels.append({"from": f"{t}.{c}", "to": f"{kt}.{kc}", "overlap": round(inter / len(vals), 4)})
    return rels


def candidate_keys(prof):
    return {t: [c for c, p in v["columns"].items() if p["unique"] and p["kind"] in ("id", "number", "text")] for t, v in prof.items()}


def summary(tables):
    prof = profile(tables)
    return {"tables": prof, "keys": candidate_keys(prof), "relations": relations(tables, prof)}


if __name__ == "__main__":
    import sys
    tabs = load(sys.argv[1])
    s = summary(tabs)
    print(json.dumps({"keys": s["keys"], "relations": s["relations"],
                      "kinds": {t: {c: p["kind"] for c, p in v["columns"].items()} for t, v in s["tables"].items()}}, indent=1, default=str))
