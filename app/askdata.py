"""Ask the data: a question in natural language → understood intent → guarded SQL on the star schema → table / chart → summary.

Flow (brief §9.1 spirit: the AI never invents numbers, it only reads what the query returned):
  1. understand: Azure OpenAI turns the question into JSON {intent, understood, sql, chart} using the documented star schema
     (offline: a rule-based translator handles the common shapes: count / sum / average · by dimension · filters);
  2. guard: sqlglot parses the SQL — exactly one SELECT, only the star-schema tables, no table functions or file access,
     a row cap — before anything runs (the Fabric SQL endpoint is read-only anyway);
  3. run: Fabric SQL endpoint (T-SQL, transpiled) when live, else DuckDB on the committed star-schema snapshot;
  4. explain: a second short call summarises ONLY the returned rows (numbers copied, never computed by the LLM);
  5. log: question, SQL, rows, tokens, latency → data/askdata_log.jsonl. Answers are cached.
"""
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

import copilot

DATA = Path(__file__).parent / "data"
STAR = DATA / "star"
LOG = DATA / "askdata_log.jsonl"
CACHE_FILE = DATA / "askdata_cache.json"
CACHE_VERSION = "a6"
MAX_ROWS = 1000
TABLES = ["fact_transactions", "fact_digital_events", "dim_date", "dim_heure", "dim_geo", "dim_client", "dim_merchant",
          "dim_channel", "dim_card"]
YESTERDAY = "2026-09-29"      # demo calendar, same as the copilot ("hier" = last full day of the live flow)

SCHEMA = """Schéma en étoile (Microsoft Fabric, lakehouse lh_fraud) — valeurs texte SANS accents sauf indication.
fact_transactions (1 ligne = 1 opération, 2025-01-01 → 2026-09-30, ~1,9 M lignes)
  transaction_id, date_key → dim_date, heure (0-23) → dim_heure, geo_key → dim_geo (LIEU de l'opération),
  client_key → dim_client, merchant_key → dim_merchant (NULL pour virements), card_key → dim_card (NULL pour virements),
  channel_key → dim_channel, montant_tnd (decimal TND), devise_origine ('TND','EUR',...), statut ('APPROUVEE','REFUSEE'),
  motif_refus ('SOLDE_INSUFFISANT','PLAFOND_DEPASSE','CODE_PIN_ERRONE','DATE_EXPIRATION_INVALIDE','CVV_INVALIDE','CARTE_NON_INTERNATIONALE' ou NULL),
  est_approuvee (bool), fraude_signalee (1/0 jusqu'au 2026-07-31 ; NULL ensuite : labels du flux test inconnus),
  score_modele (0-1, uniquement 2026-06 → 2026-09), alerte_modele (bool, top 1 % du score par période), niveau_risque ('ELEVE','MOYEN','FAIBLE'),
  alerte_regles_actuelles (bool, moteur de règles actuel), dq_status ('OK','WARNING')
fact_digital_events (connexions et actions dans l'application) : event_id, date_key, heure, client_key, type_evenement
  ('CONNEXION','AJOUT_BENEFICIAIRE','AJOUT_APPAREIL','REINITIALISATION_MOT_DE_PASSE','MODIFICATION_NUMERO_TELEPHONE'),
  statut ('SUCCES','ECHEC'), canal, pays_ip, methode_auth, appareil_id
dim_date : date_key (int AAAAMMJJ), date, annee, trimestre, mois (1-12), nom_mois ('janvier'...), annee_mois ('2026-09'),
  semaine, jour, jour_semaine_num (1=lundi), jour_semaine ('lundi'...), est_weekend, periode_de_paie (25→3 du mois), jour_ferie (nom ou NULL),
  periode_modele ('entrainement' <2026-06, 'validation' 2026-06/07, 'flux_test' 2026-08/09)
dim_heure : heure, tranche_horaire ('nuit (0h–5h)','matin (6h–11h)','après-midi (12h–17h)','soir (18h–23h)')
dim_geo : geo_key, ville, gouvernorat (24 gouvernorats tunisiens, NULL à l'étranger), region ('Grand Tunis','Nord-Est','Nord-Ouest',
  'Centre-Est','Centre-Ouest','Sud-Est','Sud-Ouest','Étranger','Non localisé'), code_pays, pays, est_tunisie, est_localise,
  latitude, longitude. Les opérations en ligne / mobile n'ont pas de lieu : ville = 'Non localisé (en ligne)'.
dim_client : client_key, customer_id, age, tranche_age ('18–24','25–34','35–44','45–59','60–69','70 et +'), segment ('Particulier',
  'Retraite','Etudiant','Professionnel','Premium'), profession, ville_residence, gouvernorat_residence, region_residence, client_depuis,
  tranche_revenu, revenu_mensuel_tnd, risque_kyc ('Faible','Moyen','Eleve'), utilise_banque_digitale
dim_merchant : merchant_key, merchant_id, nom_commercant, categorie ('Supermarche','Restaurant','Retrait DAB','Station service',
  'Pharmacie','Electronique','Bijouterie','Telecom / Recharge','Marketplace',...), mcc, type_commercant, ville_commercant, pays_commercant
dim_channel : channel_key, type_operation ('ACHAT','RETRAIT','VIREMENT','RECHARGE','PAIEMENT_FACTURE'), canal ('TPE','DAB','EN_LIGNE',
  'MOBILE','WEB'), mode_saisie ('CHIP','SANS_CONTACT','MAGSTRIPE','ECOM_3DS','ECOM_SANS_3DS','APP_AUTH'), carte_presente, a_distance,
  avec_3ds, sans_contact
dim_card : card_key, card_id, type_carte, internationale, sans_contact_active, plafond_jour_tnd, plafond_dab_jour_tnd
Villes tunisiennes = noms des gouvernorats sans accents : Tunis, Ariana, Ben Arous, Manouba, Nabeul, Zaghouan, Bizerte, Beja, Jendouba,
Kef, Siliana, Sousse, Monastir, Mahdia, Sfax, Kairouan, Kasserine, Sidi Bouzid, Gabes, Medenine, Tataouine, Gafsa, Tozeur, Kebili."""

PROMPT = """Tu es le moteur « questions sur les données » d'une banque tunisienne. Tu transformes une question en langage naturel
(français, anglais, arabe ou derja) en UNE requête SQL DuckDB sur le schéma ci-dessous. Tu ne réponds jamais toi-même avec des chiffres.

Règles
- Un seul SELECT (WITH autorisé), uniquement les tables du schéma, jointures sur les *_key. Jamais d'INSERT/UPDATE/DELETE/DDL.
- Comparaisons de texte insensibles aux accents et à la casse : écris les valeurs comme dans le schéma (ex. ville = 'Beja').
- « à / dans <ville> » = LIEU de l'opération (dim_geo.ville) ; « clients de / habitant à <ville> » = dim_client.gouvernorat_residence.
  Si c'est ambigu, choisis le lieu de l'opération et dis-le dans "understood".
- « hier » = """ + YESTERDAY + """ ; « aujourd'hui » = 2026-09-30 ; « ce mois-ci » = 2026-09 ; « le mois dernier » = 2026-08.
- Fraudes : fraude_signalee = 1 (seulement jusqu'au 2026-07-31) ; alertes du modèle : alerte_modele = TRUE.
- Arrondis les montants à 3 décimales (TND), les pourcentages à 1 décimale. Nomme les colonnes en français lisible (snake_case).
- Classements : ORDER BY ... DESC LIMIT n (n demandé, sinon 10). Listes détaillées : LIMIT 50 maximum.
- Vie privée : jamais d'identifiant de personne (customer_id, card_id, beneficiaire_id, appareil_id, *_key) dans le SELECT final,
  jamais de ligne par client : les données clients seulement en agrégats (COUNT(DISTINCT ...), AVG, SUM). Une demande sur UN client
  nommé ou identifié → intent = "out_of_scope" (cela se fait dans la Vue client 360, accès tracé).
- « Combien / how many / quel total » sans « par … » ni « évolution » : UNE ligne de total (pas de regroupement par date).
  Regroupe seulement si la question le demande (« par ville », « évolution », « compare », « top »). Évolution : dim_date.annee_mois.
- Fraude ≠ alerte : un taux de fraude = SUM(fraude_signalee) / COUNT(*) sur les lignes WHERE fraude_signalee IS NOT NULL (période
  labellisée) ; ne mélange jamais fraude_signalee et alerte_modele. Une alerte n'est pas une fraude.
- Ajoute un dénominateur utile quand tu donnes un taux (nb total), jamais de colonne technique (keys).
- Si la question porte sur UNE transaction (TX…) ou demande pourquoi une alerte est suspecte : intent = "alert", sql = null.
- Si la question n'a rien à voir avec les données de la banque : intent = "out_of_scope", sql = null.
- Si elle demande des personnes identifiées (liste de clients, un client nommé ou identifié, revenu d'une personne) : intent = "personal", sql = null.

Réponds UNIQUEMENT en JSON :
{"intent": "data" | "alert" | "personal" | "out_of_scope", "understood": "<ce que tu as compris, 1 phrase courte en mots métier, SANS nom de table ni de colonne, langue de l'utilisateur>",
 "sql": "<requête>" | null, "chart": {"type": "bar" | "line" | "pie" | "map" | "kpi" | "table", "x": "<colonne>", "y": "<colonne>"},
 "title": "<titre court>"}

""" + SCHEMA

SUMMARY_PROMPT = """Tu résumes le RÉSULTAT d'une requête pour un banquier. Règles :
- 2 à 3 phrases claires, puis 2 à 4 puces chiffrées. Copie les nombres du résultat tels quels (tu peux les arrondir), n'en invente aucun,
  ne fais aucun calcul qui ne soit pas dans le résultat (pas de total, pas de pourcentage non fourni).
- Commence par la réponse directe à la question. Si le résultat est vide, dis-le et propose une reformulation.
- Résultat d'UNE seule ligne : 1 à 2 phrases, AUCUNE puce. Plusieurs lignes : 4 puces MAXIMUM (les extrêmes, le pic, la tendance) —
  le graphique et le tableau affichent le détail, ne les recopie pas.
- Mentionne en une phrase courte le périmètre (période couverte, lieu de l'opération vs résidence du client).
- Écris les nombres lisiblement (espaces des milliers : 39 156 ; montants « 177 140 TND » ; taux « 4,8 % » en français).
- Mots métier uniquement : jamais de nom de colonne ou de table (pas de « taux_decline_pourcent », « dim geo », « dim_client »).
- Périmètre : déduis la période du SQL (filtres de date) ; sans filtre, c'est toute la période des données (janv. 2025 – sept. 2026).
- LANGUE : écris TOUT (résumé, périmètre, puces, followups) dans la langue indiquée par "langue" (en = anglais, fr = français).
- SEULEMENT si la question contient « pourquoi / why » : une dernière ligne d'hypothèse, clairement séparée des faits.
- Puces : libellés en mots métier (« refusées », « taux de refus »), pas les noms de colonnes même sans underscore ; pas de puce qui
  répète le périmètre ou un nombre déjà donné.
- "followups" = 3 questions COURTES que l'utilisateur pourrait taper ensuite, à la 1re personne ou impératives
  (ex. « Et à Tunis ? », « Évolution par mois », « Compare avec 2025 »), jamais « Voulez-vous… ». Langue : celle de la question.
Réponds en JSON : {"summary": "<markdown>", "followups": ["…", "…", "…"]}"""

LANG_SUMMARY = {
    "fr": "\n\nLANGUE : français. Étiquettes : « Périmètre : », « Piste (hypothèse, à vérifier) : ».",
    "en": "\n\nLANGUAGE: write EVERYTHING in English (summary, bullets, followups). Labels: \"Scope:\", \"Possible reason (hypothesis, to check):\". "
          "Numbers: 39,156 · 177,140 TND · 4.8%. No French word.",
}
_lock = threading.Lock()


# ---------------------------------------------------------------- guard
class Rejected(ValueError):
    pass


def guard(sql, max_rows=MAX_ROWS):
    """Parse and validate; returns safe DuckDB SQL or raises Rejected. Defence in depth: the Fabric endpoint is read-only too."""
    import sqlglot
    from sqlglot import exp
    if not sql or not sql.strip():
        raise Rejected("requête vide")
    try:
        trees = [t for t in sqlglot.parse(sql.strip().rstrip(";"), read="duckdb") if t is not None]
    except sqlglot.errors.ParseError as e:
        raise Rejected(f"SQL illisible : {str(e)[:120]}")
    if len(trees) != 1:
        raise Rejected("une seule requête autorisée")
    t = trees[0]
    if not isinstance(t, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise Rejected("seules les requêtes SELECT sont autorisées")
    banned = [getattr(exp, n) for n in ("Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Copy", "Merge",
                                        "Set", "Use", "Pragma", "Attach", "Detach", "Transaction", "Commit", "Rollback", "Into")
              if hasattr(exp, n)]
    if any(t.find(b) for b in banned):
        raise Rejected("instruction interdite (écriture, DDL ou configuration)")
    ctes = {c.alias_or_name.lower() for c in t.find_all(exp.CTE)}
    for tb in t.find_all(exp.Table):
        if not isinstance(tb.this, exp.Identifier) or tb.args.get("db") or tb.args.get("catalog"):
            raise Rejected("source de données non autorisée (fichier, fonction ou base externe)")
        name = tb.name.lower()
        if name not in TABLES and name not in ctes:
            raise Rejected(f"table non autorisée : {tb.name}")
    for f in t.find_all(exp.Func):
        name = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
        if re.match(r"(read_|glob|getenv|current_setting|load|install|query|sql_|system|pg_|duckdb_|http|s3)", name):
            raise Rejected(f"fonction non autorisée : {name}")
    _privacy(t)
    lim = t.args.get("limit")
    n = None
    if lim is not None:
        try:
            n = int(lim.expression.name if hasattr(lim, "expression") and lim.expression is not None else lim.name)
        except (ValueError, AttributeError):
            n = None
    if n is None or n > max_rows:
        t = t.limit(max_rows)
    return t.sql(dialect="duckdb")


IDENTIFIERS = {"customer_id", "card_id", "beneficiaire_id", "appareil_id", "event_id", "client_key", "card_key"}
K_MIN = 5          # smallest group of customers that may be shown (k-anonymity)


def _privacy(t):
    """Personal data only in aggregates (data minimisation, Tunisian law 2004-63 / GDPR art. 5): no direct identifier in the output,
    no row-level customer data, and groups of customers smaller than K_MIN are suppressed."""
    from sqlglot import exp
    outer = t if isinstance(t, exp.Select) else t.find(exp.Select)
    agg = (exp.AggFunc,)
    for e in outer.expressions:
        bare = [c for c in e.find_all(exp.Column) if c.name.lower() in IDENTIFIERS and not c.find_ancestor(*agg)]
        if bare or (isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star))):
            raise Rejected("identifiants personnels non restitués ici (seulement en agrégats) — pour un client précis : Vue client 360, accès tracé")
    tables = {tb.name.lower(): (tb.alias_or_name) for tb in t.find_all(exp.Table)}
    if "dim_client" in tables:
        grouped = bool(outer.args.get("group"))
        aggregated = grouped or any(e.find(*agg) for e in outer.expressions)
        if not aggregated:
            raise Rejected("les données clients ne sont restituées qu'en agrégats (comptes, moyennes) — pour un client précis : Vue client 360")
        alias = tables["dim_client"]
        if grouped and any(tb.alias_or_name == alias for tb in outer.find_all(exp.Table) if tb.find_ancestor(exp.Select) is outer):
            outer.having(f"COUNT(DISTINCT {alias}.client_key) >= {K_MIN}", append=True, copy=False)


# ---------------------------------------------------------------- execution
def star_ready():
    return all((STAR / f"{t}.parquet").exists() for t in TABLES)


def _duck():
    import duckdb
    con = duckdb.connect()
    con.execute("SET threads=2; SET memory_limit='200MB'")
    for t in TABLES:
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{(STAR / f'{t}.parquet').as_posix()}')")
    for s in ("SET allowed_directories=['{}']".format(STAR.as_posix()), "SET enable_external_access=false", "SET lock_configuration=true"):
        try:
            con.execute(s)
        except Exception:
            pass
    return con


def _accent_free(sql):
    """Make text comparisons accent- and case-insensitive: col = 'Béja' → lower(strip_accents(col)) = 'beja'."""
    import sqlglot
    from sqlglot import exp
    t = sqlglot.parse_one(sql, read="duckdb")

    def fix(node):
        if isinstance(node, (exp.EQ, exp.NEQ)) and isinstance(node.expression, exp.Literal) and node.expression.is_string \
                and isinstance(node.this, exp.Column):
            node.set("this", exp.Lower(this=exp.Anonymous(this="strip_accents", expressions=[node.this.copy()])))
            node.set("expression", exp.Literal.string(_n(node.expression.name)))
        if isinstance(node, exp.In) and isinstance(node.this, exp.Column) and node.expressions \
                and all(isinstance(e, exp.Literal) and e.is_string for e in node.expressions):
            node.set("this", exp.Lower(this=exp.Anonymous(this="strip_accents", expressions=[node.this.copy()])))
            node.set("expressions", [exp.Literal.string(_n(e.name)) for e in node.expressions])
        return node
    return t.transform(fix).sql(dialect="duckdb")


def run_sql(sql):
    """Execute guarded SQL. Returns (DataFrame, engine label)."""
    checked = guard(sql)
    safe = _accent_free(checked)
    import data_access as da
    src = da.source()
    if src.mode == "fabric" and os.getenv("ASKDATA_ENGINE", "fabric") == "fabric":
        try:
            import sqlglot
            df = src.sql.query(sqlglot.transpile(checked, read="duckdb", write="tsql")[0])
            if len(df) or not star_ready():
                return df, "Fabric SQL endpoint (live)"
        except Exception:
            pass                       # dialect gap, star tables not synced yet, or 0 rows on a case-sensitive collation → local engine
    if not star_ready():
        raise Rejected("schéma en étoile indisponible (exécuter le notebook 05 puis export_star.py)")
    with _lock:
        con = _duck()
        try:
            return con.execute(safe).df(), "DuckDB · instantané du schéma en étoile"
        finally:
            con.close()


# ---------------------------------------------------------------- understanding
def _n(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()).strip()


TX_ID = re.compile(r"\bTX\d{6,}\b", re.I)
PERSONAL = re.compile(r"\b(liste|list|noms?|names?|qui sont|who are)\b.{0,30}\b(clients?|customers?|personnes?|people)\b|\bC\d{6}\b|"
                      r"revenu (de|du) client|income of", re.I)
CITIES = ["Tunis", "Ariana", "Ben Arous", "Manouba", "Nabeul", "Zaghouan", "Bizerte", "Beja", "Jendouba", "Kef", "Siliana", "Sousse",
          "Monastir", "Mahdia", "Sfax", "Kairouan", "Kasserine", "Sidi Bouzid", "Gabes", "Medenine", "Tataouine", "Gafsa", "Tozeur", "Kebili"]
MONTHS = {"janvier": 1, "january": 1, "fevrier": 2, "february": 2, "mars": 3, "march": 3, "avril": 4, "april": 4, "mai": 5, "may": 5,
          "juin": 6, "june": 6, "juillet": 7, "july": 7, "aout": 8, "august": 8, "septembre": 9, "september": 9, "octobre": 10,
          "october": 10, "novembre": 11, "november": 11, "decembre": 12, "december": 12}
GROUPS = [  # (pattern, select expression, alias, join)
    (r"par (gouvernorat|region)|by (governorate|region)", "g.region", "region", "geo"),
    (r"par ville|by city|par lieu|par localite", "g.ville", "ville", "geo"),
    (r"par mois|by month|mensuel|monthly|evolution|tendance|trend|over time", "d.annee_mois", "mois", "date"),
    (r"par jour de la semaine|by weekday|by day of week", "d.jour_semaine", "jour_semaine", "date"),
    (r"par jour|by day|daily|quotidien", "d.date", "jour", "date"),
    (r"par heure|by hour|horaire", "f.heure", "heure", None),
    (r"par canal|by channel|par canaux", "c.canal", "canal", "channel"),
    (r"par type|by type", "c.type_operation", "type_operation", "channel"),
    (r"par categorie|by category|par secteur", "m.categorie", "categorie", "merchant"),
    (r"par segment|by segment", "cl.segment", "segment", "client"),
    (r"par (tranche d.?)?age|by age", "cl.tranche_age", "tranche_age", "client"),
    (r"par motif|by (decline )?reason", "f.motif_refus", "motif_refus", None),
    (r"par pays|by country", "g.pays", "pays", "geo"),
]
JOINS = {"geo": "JOIN dim_geo g ON g.geo_key = f.geo_key", "date": "JOIN dim_date d ON d.date_key = f.date_key",
         "channel": "JOIN dim_channel c ON c.channel_key = f.channel_key", "merchant": "JOIN dim_merchant m ON m.merchant_key = f.merchant_key",
         "client": "JOIN dim_client cl ON cl.client_key = f.client_key"}


def rule_translate(question):
    """Offline translator for the common shapes. Returns the same JSON as the LLM, or None."""
    q = _n(question)
    if TX_ID.search(question):
        return {"intent": "alert", "understood": "Question sur une transaction précise.", "sql": None}
    if PERSONAL.search(q):
        return {"intent": "personal", "understood": "", "sql": None}
    joins, where, understood = set(), [], []
    if re.search(r"\bmontant moyen|moyenne|average|panier moyen", q):
        measure, label = "ROUND(AVG(f.montant_tnd), 3)", "montant_moyen_tnd"
    elif re.search(r"\bmontant|volume|total|somme|amount|combien de tnd|how much", q):
        measure, label = "ROUND(SUM(f.montant_tnd), 3)", "montant_total_tnd"
    elif re.search(r"fraude|fraud", q):
        measure, label = "SUM(f.fraude_signalee)", "fraudes_signalees"
        where.append("f.fraude_signalee IS NOT NULL")
    elif re.search(r"alerte|alert", q):
        measure, label = "SUM(CASE WHEN f.alerte_modele THEN 1 ELSE 0 END)", "alertes_modele"
    else:
        measure, label = "COUNT(*)", "nb_transactions"
    if re.search(r"refus|declin|rejet", q):
        where.append("f.statut = 'REFUSEE'")
    group = next(((e, a, j) for p, e, a, j in GROUPS if re.search(p, q)), None)
    resid = re.search(r"client|habitant|resid|living|who live", q)
    for city in CITIES:
        if re.search(rf"\b{_n(city)}\b", q):
            if resid:
                joins.add("client"); where.append(f"cl.gouvernorat_residence = '{city}'"); understood.append(f"clients résidant à {city}")
            else:
                joins.add("geo"); where.append(f"g.ville = '{city}'"); understood.append(f"opérations réalisées à {city}")
    for word, val in [(r"\ben ligne\b|online|e-?commerce", "EN_LIGNE"), (r"\bdab\b|\batm\b|\bretraits?\b|withdrawal", "DAB"), (r"\btpe\b|en magasin|in store", "TPE"),
                      (r"\bmobile\b", "MOBILE")]:
        if re.search(word, q):
            joins.add("channel"); where.append(f"c.canal = '{val}'")
    for seg in ["Retraite", "Etudiant", "Premium", "Professionnel"]:
        if re.search(rf"\b{_n(seg)}s?\b|\b{dict(Retraite='retired', Etudiant='student', Premium='premium', Professionnel='professional')[seg]}s?\b", q):
            joins.add("client"); where.append(f"cl.segment = '{seg}'")
    year = re.search(r"\b(2025|2026)\b", q)
    month = next((v for k, v in MONTHS.items() if re.search(rf"\b{k}\b", q)), None)
    if re.search(r"\bhier\b|yesterday", q):
        joins.add("date"); where.append(f"d.date = DATE '{YESTERDAY}'"); understood.append(f"le {YESTERDAY}")
    else:
        if month:
            joins.add("date"); where.append(f"d.mois = {month}")
        if year:
            joins.add("date"); where.append(f"d.annee = {year.group(1)}")
    if not (group or where or label != "nb_transactions" or re.search(r"\bcombien|how many|nombre|total|count", q)):
        return {"intent": "unclear", "understood": "", "sql": None}
    top = re.search(r"\btop ?(\d{1,2})\b|\b(\d{1,2}) (premiers|premieres|first|plus|most)\b", q)
    if group:
        joins.add(group[2]) if group[2] else None
        sql = f"SELECT {group[0]} AS {group[1]}, {measure} AS {label} FROM fact_transactions f " + " ".join(JOINS[j] for j in sorted(joins))
        sql += (" WHERE " + " AND ".join(where) if where else "") + f" GROUP BY {group[0]} ORDER BY "
        sql += (f"{group[0]}" if group[1] in ("mois", "jour", "heure") else f"{label} DESC")
        if top:
            sql += f" LIMIT {int(next(x for x in top.groups() if x))}"
        chart = {"type": "line" if group[1] in ("mois", "jour", "heure") else "bar", "x": group[1], "y": label}
    else:
        sql = f"SELECT {measure} AS {label} FROM fact_transactions f " + " ".join(JOINS[j] for j in sorted(joins))
        sql += (" WHERE " + " AND ".join(where) if where else "")
        chart = {"type": "kpi", "x": None, "y": label}
    return {"intent": "data", "understood": "Compris (mode règles) : " + label.replace("_", " ") +
            (" · " + " · ".join(understood) if understood else "") + (f" · {group[1].replace('_', ' ')}" if group else ""),
            "sql": sql, "chart": chart, "title": label.replace("_", " ").capitalize()}


def _llm(messages, max_tokens=1800, effort="low"):
    kw = dict(model=os.environ["AZURE_OPENAI_DEPLOYMENT"], messages=messages, response_format={"type": "json_object"})
    if copilot._is_reasoning():
        kw.update(max_completion_tokens=max_tokens, reasoning_effort=effort)
    else:
        kw.update(temperature=0, max_tokens=700)
    r = copilot._client().chat.completions.create(**kw)
    u = r.usage
    return json.loads(r.choices[0].message.content or "{}"), {
        "prompt": int(getattr(u, "prompt_tokens", 0) or 0), "completion": int(getattr(u, "completion_tokens", 0) or 0),
        "total": int(getattr(u, "total_tokens", 0) or 0),
        "cached_prompt": int(getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0)}


def _add(a, b):
    return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}


def _result_brief(df, limit=40):
    head = df.head(limit)
    out = {"lignes": int(len(df)), "colonnes": list(df.columns), "donnees": json.loads(head.to_json(orient="records", date_format="iso", force_ascii=False))}
    if len(df) > limit:
        out["note"] = f"{len(df) - limit} lignes de plus non montrées"
    return copilot._sanitize(out)


# ---------------------------------------------------------------- cache + log
def _load_cache():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    except Exception:
        return {}


_cache = _load_cache()


def _log(rec):
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- main entry
def ask(question, lang="fr", history=None, analyst=None):
    """Returns {intent, understood, sql, engine, df, chart, title, summary, followups, tokens, latency_s, mode, error?}."""
    t0 = time.time()
    question = (question or "").strip()[:500]
    tokens = {"prompt": 0, "completion": 0, "total": 0, "cached_prompt": 0}
    key = hashlib.sha256(f"{CACHE_VERSION}|{lang}|{_n(question)}".encode()).hexdigest()
    out = {"question": question, "intent": "data", "tokens": tokens}
    cached = _cache.get(key)
    llm = copilot.configured() and os.getenv("COPILOT_OFFLINE", "0") != "1"
    if cached and star_ready():
        plan, mode = cached["plan"], cached["mode"]
    elif llm:
        mode = "Azure OpenAI"
        msgs = [{"role": "system", "content": PROMPT},
                {"role": "user", "content": json.dumps({"question": copilot._sanitize(question), "langue": lang,
                                                        "historique": [h.get("question") for h in (history or [])][-3:]}, ensure_ascii=False)}]
        try:
            plan, tk = _llm(msgs)
            tokens = _add(tokens, tk)
        except Exception as exc:
            plan, mode = rule_translate(question), f"règles (Azure OpenAI indisponible : {type(exc).__name__})"
            out["ai_down"] = f"error:{type(exc).__name__}"
    else:
        plan, mode = rule_translate(question), L(lang, "règles (hors-ligne)", "rules (offline)")
        out["ai_down"] = copilot.ai_status()
    out.update(intent=plan.get("intent", "data"), understood=re.sub(r"\(?\b(dim|fact)_\w+(\.\w+)?\)?", "", copilot.polish(plan.get("understood", ""))).strip(), title=plan.get("title", ""),
               chart=plan.get("chart") or {}, mode=mode)
    if out["intent"] != "data" or not plan.get("sql"):
        out["latency_s"] = round(time.time() - t0, 2)
        _log({"ts": datetime.now(), "analyst": analyst, "question": question, "intent": out["intent"], "mode": mode, "tokens": tokens})
        return out
    sql = plan["sql"]
    try:
        df, engine = run_sql(sql)
    except Exception as exc:
        if llm and not cached and not isinstance(exc, Rejected):          # one repair round with the error message
            try:
                plan2, tk = _llm(msgs + [{"role": "assistant", "content": json.dumps(plan, ensure_ascii=False)},
                                         {"role": "user", "content": f"Erreur à l'exécution : {str(exc)[:300]}. Corrige la requête (même format JSON)."}])
                tokens = _add(tokens, tk)
                plan, sql = plan2, plan2.get("sql")
                df, engine = run_sql(sql)
            except Exception as exc2:
                exc = exc2
                df = None
        else:
            df = None
        if df is None:
            out.update(sql=sql, error=str(exc)[:300], latency_s=round(time.time() - t0, 2), tokens=tokens)
            _log({"ts": datetime.now(), "analyst": analyst, "question": question, "sql": sql, "error": str(exc)[:300], "mode": mode, "tokens": tokens})
            return out
    df = df.convert_dtypes(dtype_backend="numpy_nullable") if len(df.columns) else df
    out.update(sql=guard(sql), engine=engine, df=df)
    qlang = question_lang(question, lang)
    if cached:
        out.update(summary=cached["summary"], followups=cached.get("followups", []), cached=True)
    elif llm:
        try:
            s, tk = _llm([{"role": "system", "content": SUMMARY_PROMPT + LANG_SUMMARY[qlang]},
                          {"role": "user", "content": json.dumps({"question": question, "compris": out["understood"], "sql": out["sql"],
                                                                  "periode_des_donnees": "2025-01-01 → 2026-09-30 (fraudes connues jusqu'au 2026-07-31)",
                                                                  "resultat": _result_brief(df, 25), "langue": qlang}, ensure_ascii=False, default=str)}],
                         max_tokens=900, effort="minimal")
            tokens = _add(tokens, tk)
            summ = s.get("summary", "")
            if not re.search(r"pourquoi|why|explique|explain|raison|reason", _n(question)):      # hypothesis only when asked
                summ = "\n".join(l for l in summ.splitlines() if not re.match(r"\W*(piste|possible reason|hypoth)", _n(l)))
            out.update(summary=copilot.polish(summ.strip(), qlang), followups=[copilot.polish(f, qlang) for f in s.get("followups", []) if isinstance(f, str)][:3])
        except Exception:
            out.update(summary=offline_summary(df, lang), followups=[])
    else:
        out.update(summary=offline_summary(df, lang), followups=[])
    out["tokens"] = tokens
    out["latency_s"] = round(time.time() - t0, 2)
    if llm and not cached and out.get("summary"):
        _cache[key] = {"plan": {**plan, "sql": out["sql"]}, "mode": mode, "summary": out["summary"], "followups": out["followups"]}
        try:
            CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    _log({"ts": datetime.now(), "analyst": analyst, "question": question, "intent": out["intent"], "sql": out["sql"], "engine": engine, "rows": int(len(df)),
          "mode": mode, "cached": bool(cached), "tokens": tokens, "latency_s": out["latency_s"]})
    return out


def question_lang(question, default="fr"):
    q = " " + _n(question) + " "
    en = len(re.findall(r" (the|how|many|which|what|show|is|are|why|did|does|in|of|by|per|with|customers?|transactions?) ", q))
    fr = len(re.findall(r" (le|la|les|des|du|de|combien|quel|quelle|quels|est|sont|par|avec|clients?|pourquoi|dans) ", q))
    return "en" if en > fr else "fr" if fr > en else default


def L(lang, fr, en):
    return en if lang == "en" else fr


def _fmt(v):
    if hasattr(v, "item") and not isinstance(v, str):
        v = v.item()
    if isinstance(v, float) and v.is_integer() and abs(v) >= 1000:
        v = int(v)
    if isinstance(v, float):
        return f"{v:,.3f}".replace(",", " ").rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return str(v)


def offline_summary(df, lang="fr"):
    if df is None or not len(df):
        return L(lang, "Aucune ligne ne correspond. Essayez une période ou un lieu plus large.", "No row matches. Try a wider period or place.")
    if df.shape == (1, 1):
        return L(lang, f"**{_fmt(df.iat[0, 0])}** ({df.columns[0].replace('_', ' ')}).", f"**{_fmt(df.iat[0, 0])}** ({df.columns[0].replace('_', ' ')}).")
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    cat = [c for c in df.columns if c not in num]
    if cat and num:
        top = df.sort_values(num[-1], ascending=False).iloc[0]
        return L(lang, f"{len(df)} ligne(s). En tête : **{top[cat[0]]}** avec **{_fmt(top[num[-1]])}** ({num[-1].replace('_', ' ')}).",
                 f"{len(df)} row(s). Top: **{top[cat[0]]}** with **{_fmt(top[num[-1]])}** ({num[-1].replace('_', ' ')}).")
    return L(lang, f"{len(df)} ligne(s).", f"{len(df)} row(s).")
