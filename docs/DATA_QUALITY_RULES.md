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

## Problematic cases and how they were handled

### Caught by the rules (checked in Fabric, run of 2026-11-06)
Only 2 of the 36 rules found anything; the 34 others found 0 rows (no duplicate, no orphan key, no impossible code, no inconsistent status).

| Rule | Rows | What it really was | How we handled it | Why |
|---|---|---|---|---|
| **T15** in-store / ATM operation with no location | 11,717 (0.61 %) | The **city is present**, only the GPS coordinates are missing (in the labelled period: 9,632 card-terminal payments + 1,105 ATM withdrawals) | **Kept** with status WARNING. City-based indicators (new city, country) still work; distance and travel speed stay **empty (missing), never invented**; LightGBM handles missing values natively and learns from them. In the star schema the place is marked "not geolocated" | Rejecting them would delete 11,717 genuine operations; inventing coordinates (e.g. the city centre) would create false travel speeds and false alerts |
| **T04** extreme amount (> 50,000 TND) | 39 (0.002 %) | **All web or mobile transfers**, 50,558 → 197,718 TND; **none of the labelled ones is a fraud** | **Kept** with status WARNING, not capped, not deleted; visible for review | Large legitimate transfers exist (property, business). Deleting or capping them would teach the model that large = impossible and would hide real exposure |

**Rule of thumb applied:** ERROR → quarantine (the row is unusable); WARNING → keep, flag and let the analyst see it. Nothing is silently fixed or deleted: the raw data stays in bronze, every failure is a row of `quality.issues`, every record has a status in `quality.row_status`.

### Found while building the pipeline (not by the rules)
| Problem | What happened | How we handled it |
|---|---|---|
| **Wrong time split** | The period was computed from the month only, ignoring the year: Aug–Sep **2025** labelled rows were tagged "test" (234 fake test frauds) | Split rebuilt on the full date: train Jan 2025 → May 2026, validation Jun → Jul 2026, test Aug → Sep 2026 |
| **Data leak** | 3 features (`f_merchant_risk`, `f_device_risk`, `f_beneficiary_risk`) used fraud labels from the future | Removed; a check in notebook 02 stops the run if a label, scenario, report date or gender column becomes a feature |
| **Test labels** | The test period must stay blind | Labels forced empty on test rows before writing any table (check = 0) |
| **Infinite values** | Divisions such as distance ÷ time give infinity when two operations share the same second | Turned into missing values before training |
| **Memory** | 1.9 M rows did not fit in memory for training | All frauds + 10 % of legitimate operations (weight × 10 so the balance stays real); validation and test kept complete |
| **Dataset ≠ brief** | Bigger than the brief (1.9 M transactions, 3,500 customers) with different dates | Dates measured on the real data before any split; all figures reported on our own validation period |

### Other banks' data (universal integration)
Formats that would break a pipeline are detected and **flagged for a human to confirm** before anything goes live: dd/mm/yyyy dates, timestamps in milliseconds, amounts in cents, "1 234,500" decimal commas, 3-letter country codes, numeric status codes (0/1), labels given only as a list of fraud reports. Sensitive columns (gender, CVV, names, e-mail) are never used and are erased at activation.
