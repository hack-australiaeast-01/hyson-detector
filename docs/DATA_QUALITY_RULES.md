# Data quality rules (notebook 05)

36 rules run on every row of the 5 bronze tables (3.4 million records). Source: `notebooks/gen_nb05.py`, table `quality.rules`.

- **ERROR** = the row cannot be trusted: quarantined, kept out of the facts.
- **WARNING** = the row is kept and flagged for review.

**Result:** 0 rows rejected · 11,756 warnings (11,717 in-store payments with no location, T15 · 39 amounts above 50,000 TND, T04).

## Transactions (17)
| # | Level | Rule |
|---|---|---|
| T01 | ERROR | Transaction ID missing or duplicated |
| T02 | ERROR | Required field missing (date, customer, amount, type, channel, status) |
| T03 | ERROR | Amount zero or negative |
| T04 | WARNING | Extreme amount (above 50,000 TND) |
| T05 | ERROR | Date unreadable or outside the data period |
| T06 | ERROR | Unknown code (transaction type, channel, entry mode, status, decline reason) |
| T07 | ERROR | Unknown customer |
| T08 | ERROR | Unknown card |
| T09 | ERROR | Unknown merchant |
| T10 | ERROR | Card belongs to another customer |
| T11 | WARNING | Card expired or not yet issued on the transaction date |
| T12 | ERROR | Status and decline reason inconsistent (declined with no reason, or approved with a reason) |
| T13 | WARNING | Type and channel inconsistent (withdrawal not at an ATM, transfer not on mobile or web) |
| T14 | WARNING | Entry mode and channel inconsistent (e.g. chip payment on an online channel) |
| T15 | WARNING | In-store or ATM operation with no location |
| T16 | WARNING | Currency inconsistent with the country |
| T17 | WARNING | Coordinates outside Tunisia for an operation in Tunisia |

## Customers (8)
| # | Level | Rule |
|---|---|---|
| C01 | ERROR | Customer ID missing or duplicated |
| C02 | ERROR | Age missing or impossible (under 18 or over 105) |
| C03 | ERROR | Income missing or negative |
| C04 | WARNING | Unknown segment or KYC risk level |
| C05 | ERROR | Unknown governorate |
| C06 | WARNING | "Customer since" date in the future |
| C07 | WARNING | Retired customer under 45 |
| C08 | WARNING | Student over 35 |

## Cards (4)
| # | Level | Rule |
|---|---|---|
| K01 | ERROR | Card ID missing or duplicated |
| K02 | ERROR | Card of an unknown customer |
| K03 | ERROR | Expiry date before issue date |
| K04 | WARNING | Daily limit or ATM limit zero or negative |

## Merchants (3)
| # | Level | Rule |
|---|---|---|
| M01 | ERROR | Merchant ID missing or duplicated |
| M02 | WARNING | Category or MCC code missing |
| M03 | WARNING | Coordinates outside Tunisia for a merchant in Tunisia |

## Digital events: logins and account changes (4)
| # | Level | Rule |
|---|---|---|
| E01 | ERROR | Event ID missing or duplicated |
| E02 | ERROR | Unknown customer |
| E03 | ERROR | Date unreadable or outside the data period |
| E04 | WARNING | Unknown event type or status |

**Total: 36 rules (20 ERROR, 16 WARNING).** They check that every record is complete, unique, valid, points to things that exist (customer, card, merchant) and is consistent with itself (status vs reason, type vs channel, currency vs country, age vs segment).

---

## How the problem rows were handled, step by step

Results of the run on 2026-11-06 (table `quality.summary` in Fabric): **34 rules found 0 rows**, **2 rules triggered**: T15 (11,717 rows) and T04 (39 rows). No row reached ERROR, so **nothing was quarantined**.

### The mechanism (notebook 05), for every rule
1. Each rule is run on every row. Every failure becomes one line of `quality.issues`: table, record, rule, column, value, message.
2. Each record gets a status in `quality.row_status`: **REJECTED** if it broke at least one ERROR rule, **WARNING** if it broke only WARNING rules, **OK** otherwise.
3. **REJECTED** rows are copied to `quality.quarantine_<table>` and kept **out** of the star schema (`dq_status != 'REJECTED'`). Nothing is deleted: the raw row stays in bronze.
4. **WARNING** rows go **into** the star schema with their status: `fact_transactions.dq_status = 'WARNING'`, so any query or report can filter them or show them.
5. `quality.summary` gives the count and rate per rule, so we see the impact before using the data.

### Case 1 — T15: in-store or ATM operation with no GPS coordinates (11,717 rows)
**What was wrong:** for 9,632 card-terminal payments and 1,105 ATM withdrawals (labelled period), the city was filled but the latitude / longitude were empty.

**How it was handled, exactly:**
1. **Kept**, status WARNING; the row is flagged in `quality.issues` (rule T15).
2. **No coordinates invented.** In notebook 01 the distance and the travel speed use **the last known position of the customer** (`last(latitude, ignorenulls=True)` over the past) and the time of that position:
   - an operation **without** coordinates gets an **empty** distance and speed (missing, not 0);
   - the **next** operation that has coordinates is compared with the last real position, not with the empty one, so no fake jump is created.
3. **City-based features still work:** "first time in this city" and "first time in this country" use the city and country fields, which are filled.
4. **Speed protected from near-zero time gaps:** the time between two positions is floored at 3 minutes (0.05 h), so two payments in the same minute never produce an absurd speed.
5. **The model:** LightGBM handles missing values natively; it learns which side of each split the missing values belong to. Infinite values are turned into missing values before training.
6. **Star schema:** the place is marked `est_localise` (located or not), so the AI assistant and the reports can say when an operation has no location.

**Why:** deleting would lose 11,717 real operations; putting the city centre or 0 would create false "impossible travel" alerts; a missing value keeps the truth (we don't know where it happened).

### Case 2 — T04: amount above 50,000 TND (39 rows)
**What was wrong:** nothing, in fact. All 39 are web or mobile **transfers** (50,558 → 197,718 TND), and **none of the labelled ones is a fraud**.

**How it was handled, exactly:**
1. **Kept**, status WARNING, flagged in `quality.issues` (rule T04). **Not capped, not deleted.**
2. Used by the model **as they are**: the amount features compare each amount with the customer's own habits (ratio, statistical distance, previous maximum), so one very large transfer only stands out for a customer who never makes large transfers.
3. Visible in the star schema with `dq_status = 'WARNING'`, so they can be reviewed.

**Why:** large legitimate transfers exist (property, business). Capping them would hide the real amount exposed; deleting them would teach the model that large transfers never happen.

### Problems found outside the rules, and the exact fix
| Problem | Exact fix |
|---|---|
| **Wrong time split**: the period was taken from the month only, so Aug–Sep **2025** labelled rows were tagged "test" (234 fake test frauds) | The original `split` column is kept; validation = the 2 months before the last labelled month, computed on the full date → train Jan 2025 → May 2026 (1,542,647 rows), validation Jun → Jul 2026 (177,953), test Aug → Sep 2026 (187,628, labels empty) |
| **Data leak**: `f_merchant_risk`, `f_device_risk`, `f_beneficiary_risk` were built with fraud labels from the future | Excluded in notebook 02 (`LEAKY` set). An `assert` stops the run if any feature name contains `is_fraud`, `scenario`, `reported` or `gender` |
| **Test labels** must stay blind | Forced to empty on test rows in Spark **before** any table is written; checked = 0 |
| **Infinite values** (a distance divided by an almost-zero time) | Floor of 3 minutes on the time gap, then `±inf → missing` before training |
| **Memory**: 1.9 M rows did not fit for training | Training on all frauds + 10 % of legitimate operations, each legitimate row weighted × 10 so the real balance is kept; validation and test kept **complete** so the reported figures are on the real data |
| **Dataset ≠ brief** (bigger, other dates) | Date ranges measured on the real tables before choosing the split; all figures reported on our own validation period |

### Data from another bank (universal integration)
Problem formats are not fixed silently. They are **flagged for a person to confirm** before activation: dd/mm/yyyy dates, timestamps in milliseconds, amounts in cents, "1 234,500" decimal commas, 3-letter country codes, numeric status codes (0/1), fraud labels given only as a list of reports. An open flag **blocks** approval. Sensitive columns (gender, CVV, names, e-mail) are never mapped and are erased from the raw copy at activation.

---

## What happens when ERROR rows appear in the future

No ERROR row exists in today's data, but the pipeline is built for the day it happens (a new load, another bank, a broken export).

### What is already in place (runs on every load)
1. **Detection:** every new load goes through the same 36 rules; each failing row is logged in `quality.issues` with the rule, column, value and message.
2. **Quarantine, not deletion:** a row with an ERROR is marked REJECTED and copied to `quality.quarantine_<table>`. It does **not** reach the star schema, the AI assistant, the reports or the scores. The raw row stays in bronze, so nothing is lost and the fix can be replayed.
3. **Visibility:** `quality.summary` gives the number and rate of failures per rule for each run, so a sudden jump (e.g. 2 % unknown cards instead of 0 %) is seen immediately.
4. **Format change detection:** each bronze load is logged in `bronze_ingestion_log` with rows, columns and a **schema fingerprint**; if the bank changes its file format, the fingerprint changes.
5. **Other banks (universal integration):** the readiness report turns errors into a **gate**: too many duplicate IDs (> 1 %), required fields below 90 % filled, unreadable dates (> 5 %) or broken links between tables (< 90 %) are **blockers** → the gate is red, the bank cannot be validated, approved or activated until the data is fixed.
6. **Real-time events (webhook):** a transaction missing a required field (ID, date, amount) is refused with a clear error; a duplicate transaction ID is ignored (idempotent) and counted; every call is logged in the bank's audit trail.

### The handling procedure for an ERROR row
| Step | Who | What |
|---|---|---|
| 1. Alert | Data engineer | `quality.summary` shows a rule with failures above 0 (or above its usual rate) |
| 2. Diagnose | Data engineer | Read the rows in `quality.issues` and `quality.quarantine_<table>`: which rule, which column, which value |
| 3. Classify the cause | Data engineer + bank | **Source error** (bad export, unknown code, missing customer) → ask the bank to resend; **reference missing** (new merchant / card not yet in the reference tables) → load the reference data, then re-run; **rule too strict** (a new valid code) → update the rule's list of allowed values, document the change |
| 4. Re-run | Pipeline | Re-running notebook 05 re-checks the quarantined rows; those that now pass go into the facts automatically |
| 5. Score | Pipeline | Only after the data is clean: notebooks 01 → 02 rescore, so an error never produces a false alert |
| 6. Trace | Automatic | Every run, failure and status stays in the quality tables; for other banks every step is in the tamper-evident audit trail |

**Principle:** an ERROR row never reaches a score or an analyst; it waits in quarantine until the source is fixed. A WARNING row is used but visible. Nothing is ever deleted or silently corrected.

### Planned next (not built yet)
- **Automatic alert** (e-mail / Teams) when a rule's failure rate exceeds a threshold, instead of reading `quality.summary`.
- **Run stop**: if ERROR rows exceed a set share of a load (for example 1 %), stop the retraining pipeline `pl_hyson_retrain` before scoring.
- **Schema change stop**: compare the schema fingerprint with the previous load and stop on any change.
- **Quarantine dashboard** in the app for the data team (rule, count, trend, rows to fix).
