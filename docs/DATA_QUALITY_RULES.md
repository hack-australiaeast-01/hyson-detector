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
