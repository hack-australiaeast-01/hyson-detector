"""Export the star schema built by notebook 05 from Fabric to app/data/star/*.parquet (snapshot for the hosted app, DuckDB).

    cd app && python export_star.py
Needs `az login` and the Fabric SQL endpoint (.env). Columns not needed for analysis are dropped to keep the snapshot small.
"""
import sys
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import askdata
import data_access as da

DROP = {"fact_transactions": ["horodatage", "beneficiaire_id"], "fact_digital_events": ["horodatage", "event_id", "appareil_id"]}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    f = da.FabricSQL()
    askdata.STAR.mkdir(parents=True, exist_ok=True)
    for t in askdata.TABLES:
        t0 = time.time()
        cols = [c for c in f.query(f"SELECT TOP 0 * FROM {t}").columns if c not in DROP.get(t, [])]
        df = f.query(f"SELECT {', '.join(cols)} FROM {t}")
        for c in df.columns:
            if df[c].dtype == object and df[c].nunique(dropna=True) < 0.2 * max(len(df), 1):
                df[c] = df[c].astype("category")
            elif pd.api.types.is_float_dtype(df[c]) and c not in ("montant_tnd", "latitude", "longitude", "score_modele"):
                df[c] = pd.to_numeric(df[c], downcast="float")
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), askdata.STAR / f"{t}.parquet", compression="zstd")
        print(f"{t:22s} {len(df):>9,} rows  {(askdata.STAR / f'{t}.parquet').stat().st_size / 1e6:6.1f} MB  {time.time() - t0:5.1f}s", flush=True)
