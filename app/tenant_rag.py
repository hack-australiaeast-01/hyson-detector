"""Institutional memory per bank (RAG): the bank's own case notes, typology statistics and policy documents.

One index per tenant, stored in the tenant's folder; a search never reads another tenant's index. Retrieval is TF-IDF (numpy,
offline, 0 tokens). The memory informs analysts and the copilot; it is never used as training data for the model.
"""
import json
import re
import unicodedata
from collections import Counter

import numpy as np

STOP = set("le la les de des du un une et en au aux a à pour par sur dans est sont the of and to in for on is are was with by an or "
           "this that ce cet cette ces il elle ils on qui que quoi not pas ne se sa son ses leur leurs".split())


def _tok(text):
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return [w for w in re.findall(r"[a-z0-9]{2,}", t) if w not in STOP]


def chunk(text, size=700):
    paras = [p.strip() for p in re.split(r"\n\s*\n", str(text)) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = ""
        cur = (cur + "\n" + p).strip()
    if cur:
        out.append(cur)
    return out


def documents(canon, policies=None):
    docs = []
    cases = canon.get("cases")
    if cases is not None and "notes" in cases:
        for r in cases.dropna(subset=["notes"]).itertuples():
            docs.append({"id": f"case:{r.case_id}", "source": "case", "text": str(r.notes),
                         "meta": {"outcome": getattr(r, "outcome", None), "opened_at": str(getattr(r, "opened_at", ""))[:10]}})
    tx, lab = canon.get("transactions"), canon.get("fraud_labels")
    if tx is not None and "is_fraud" in tx:
        f = tx[tx["is_fraud"] == 1]
        if lab is not None and "fraud_type" in lab:
            f = f.merge(lab[["transaction_id", "fraud_type"]], on="transaction_id", how="left")
        key = "fraud_type" if "fraud_type" in f and f["fraud_type"].notna().any() else ("channel" if "channel" in f else None)
        if key:
            for k, g in f.groupby(key):
                parts = [f"Typologie {k} : {len(g)} fraudes confirmées."]
                for c in ("channel", "entry_mode", "transaction_type", "country", "merchant_category"):
                    if c in g and g[c].notna().any():
                        top = g[c].value_counts(normalize=True).head(3)
                        parts.append(f"{c} : " + ", ".join(f"{i} {v:.0%}" for i, v in top.items()) + ".")
                amt = g["amount_tnd"] if "amount_tnd" in g else g["amount"]
                parts.append(f"Montant médian {amt.median():,.0f} TND ; {100 * (g['timestamp'].dt.hour < 6).mean():.0f} % la nuit.".replace(",", " "))
                docs.append({"id": f"typology:{k}", "source": "typology", "text": " ".join(parts), "meta": {"frauds": int(len(g))}})
    for name, text in (policies or {}).items():
        for i, c in enumerate(chunk(text)):
            docs.append({"id": f"policy:{name}#{i}", "source": "policy", "text": c, "meta": {"document": name}})
    return docs


def build(docs):
    toks = [_tok(d["text"]) for d in docs]
    df = Counter(w for t in toks for w in set(t))
    vocab = {w: i for i, (w, _) in enumerate(df.most_common(30000))}
    n = max(len(docs), 1)
    idf = np.array([np.log((1 + n) / (1 + df[w])) + 1 for w in vocab], dtype=np.float32)
    M = np.zeros((len(docs), len(vocab)), dtype=np.float32)
    for i, t in enumerate(toks):
        for w, c in Counter(t).items():
            if w in vocab:
                M[i, vocab[w]] = (1 + np.log(c)) * idf[vocab[w]]
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    return {"docs": docs, "vocab": vocab, "idf": idf, "M": M}


def save(index, folder):
    folder.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(folder / "rag.npz", M=index["M"], idf=index["idf"])
    (folder / "rag.json").write_text(json.dumps({"docs": index["docs"], "vocab": index["vocab"]}, ensure_ascii=False, default=str),
                                     encoding="utf-8")


def load(folder):
    if not (folder / "rag.npz").exists():
        return None
    z = np.load(folder / "rag.npz")
    meta = json.loads((folder / "rag.json").read_text(encoding="utf-8"))
    return {"docs": meta["docs"], "vocab": meta["vocab"], "idf": z["idf"], "M": z["M"]}


def search(index, query, k=5):
    if not index or not index["docs"]:
        return []
    q = np.zeros(len(index["vocab"]), dtype=np.float32)
    for w, c in Counter(_tok(query)).items():
        j = index["vocab"].get(w)
        if j is not None:
            q[j] = (1 + np.log(c)) * index["idf"][j]
    if not q.any():
        return []
    s = index["M"] @ (q / np.linalg.norm(q))
    top = np.argsort(-s)[:k]
    return [{**index["docs"][i], "score": round(float(s[i]), 3)} for i in top if s[i] > 0.05]


def answer(index, question, lang="fr"):
    """Grounded answer from the tenant's memory: LLM if configured (cites the passages), otherwise the passages themselves."""
    hits = search(index, question, k=5)
    if not hits:
        return {"answer": "Aucun passage pertinent dans la mémoire de cette banque." if lang == "fr"
                else "No relevant passage in this bank's memory.", "sources": []}
    import copilot
    if copilot.configured():
        ctx = "\n".join(f"[{i + 1}] ({h['source']}) {h['text'][:600]}" for i, h in enumerate(hits))
        prompt = ("Answer the analyst's question using ONLY the numbered passages from this bank's own memory; cite them like [1]. "
                  "If they do not answer it, say so. No customer identifiers. Reply in " + ("French" if lang == "fr" else "English")
                  + " as JSON {\"answer\": \"...\"}.\nPassages:\n" + ctx + "\nQuestion: " + question)
        try:
            text, _ = copilot.complete_json(prompt, tag="[integration] tenant memory", max_tokens=1500)
            return {"answer": json.loads(text or "{}").get("answer", ""), "sources": hits, "mode": "ai"}
        except Exception:
            pass
    return {"answer": "\n".join(f"- [{i + 1}] {h['text'][:300]}" for i, h in enumerate(hits)), "sources": hits, "mode": "retrieval"}
