---
name: investment-import
description: Turn a user's brokerage, retirement or crypto statement (PDF, CSV, OFX/QFX, trade history) into a Talia statement file (talia.statement/1 JSON) with holdings and/or activity that imports into the Talia app. Use whenever the user hands you an investment account statement, positions export, trade or dividend history, or asks to get investment data into Talia. For chequing/savings/credit-card transactions use transaction-import instead.
---

# Building a Talia investment import

Goal: read an investment or crypto account's statement and write `talia.statement/1` JSON
files, one per account and period, that Talia imports without asking the user what a
column means, which broker wording is a dividend, or what the file covers.

A file has **holdings** (what the account held on a date), **activity** (what happened over
a period), or both. This skill is self-contained: `references/format.md` is the format,
`references/extraction.md` is how to read broker documents, and the vendored JSON Schema is
`schemas/talia.statement.1.json` (it wins on any disagreement). Formats are immutable per
version; a change ships as `talia.statement/2`. Write `/1` unless the user says they need a
newer version and you have its schema.

## Principles (these decide every judgement call)

1. **Copy, don't compute.** Every figure is one the statement prints. Talia checks
   quantity × price against value, positions against the account total, trades against
   their amount, and activity against holdings. A figure you calculated agrees with the
   rest by construction, so it checks nothing and hides the error it should catch.
2. **Leave out rather than guess.** Optional fields are optional because Talia handles their
   absence, usually by asking the user once. A wrong value is silent. This applies to
   `exchange` (only if you know the MIC), `price` on a trade that doesn't multiply out,
   `ratio`, `quantities`, and `kind` on a security you can't classify (ask the user).
3. **Never invent identifiers.** `id` is only the institution's own transaction id. A made-up
   id that changes between runs duplicates events; one that repeats merges different events.
   For a reinvested dividend with no id, use `ref` (never stored).
4. **Be strict about format, honest about content.** Talia rejects a file it can't read and
   lists each problem with its JSON path. It never rejects a file for figures that disagree;
   those go to the user's review. So never adjust a number to make a check pass.
5. **When in doubt, claim less.** In `coverage`, `holdings.complete`, `quantities` and `cash`,
   the safe answer is `false` / omitted. A false claim makes Talia reconstruct holdings
   wrongly; a missing claim leaves a gap another file can fill.

## Workflow

1. **Gather context from the user** (ask only what you can't see):
   - Which Talia account, and its type (`investment` or `crypto`); currency of the account.
   - For several accounts in a zip: each account's number as entered in Talia (last 4+ digits).
2. **Inventory the documents**: what does each give you? Positions on a date (holdings),
   trades/income/transfers over a period (activity), or an annual summary (probably neither;
   see extraction.md). Decide what each file will contain and the `period`/`asOf` it covers.
3. **Build the `securities` table** first: one entry per distinct security, any key you
   choose, with `kind`, and `isin`/`cusip`/`symbol`/`name` exactly as shown. Include `isin`
   or `cusip` whenever printed. `exchange` only if you know it.
4. **Holdings** (if the document has positions): `asOf` is the date the statement states
   (not today), `complete` true only if every holding is listed, `quantities` settled/trade
   if determinable, `cash` present only if you can see all of it, `total`/`totals` as
   printed. Positions copy `quantity`, `price`, `marketValue`, `costBasis` as printed.
5. **Activity** (if the document has transactions): one entry per event; map broker wording
   to `kind` using the table in `references/format.md`; net `amount` signed from the
   holder's side; `fees`/`withholding` positive and already inside `amount`; reinvested
   dividends as two entries linked by `reinvests`; FX as one entry with two `legs`.
6. **Set `coverage`** honestly, and make `period` the range you actually read; every
   activity date must fall inside it.
7. **Write the JSON** with stable key order, 2-space indent, trailing newline, no timestamps
   (same input → same bytes, so Talia recognises an already-imported file).
8. **Validate**:
   ```
   python3 skills/investment-import/scripts/validate_investment.py out.json
   ```
   Fix errors at their cause in the extraction; don't delete the row an error names.
   Investigate warnings (arithmetic that doesn't close, totals that disagree) before deciding
   the statement itself is off; if it is, leave the printed figures as printed.
9. **Report**: file path(s), what each contains (holdings as of, activity period, coverage
   claims), securities where you had to ask or leave something out, and warnings that remain.
   Import via Accounts › Import statements (a zip for several accounts).

## Hard rules

- Money, quantities, prices are **strings**: `"-2881.00"`, `"0.2483"`. Never JSON numbers,
  never `"$1,234.50"` or `"+5"`. Money has no more decimals than the currency allows; quantities
  and prices may have any precision.
- Dates `YYYY-MM-DD`, real dates, no times or zones.
- Signs from the holder's side: buys, fees, withholding rows, withdrawals negative;
  sells, dividends, deposits positive. Exceptions in format.md (accrued interest paid on a
  bond purchase is negative `interest`).
- `buy`/`sell` `quantity` is a positive magnitude; the kind gives direction. Only
  `corporate_action` (and `other`) quantities are signed.
- A file has `holdings` and/or `activity`, **never** `transactions`, `opening` or `closing`.
  `activity` requires `coverage` and `period`; `coverage` requires `activity`.
- Unknown keys are an error. Private data goes under `"x"`.
- No full account numbers, credentials or tokens, not even under `"x"`. `mask` is at most the
  last 4 characters.
- One account per file. A joint PDF covering RRSP + TFSA is two files.
- A security referenced by `security` or `from` must be a key in `securities`.

## Common traps

- **Price that doesn't multiply out**: give a trade's `price` only if quantity × price with the
  printed `fees` equals `amount` within the price's last printed decimal. Otherwise omit
  `price` and give `amount` as printed. Never invent a `fees` figure to close the gap.
- **Position `price`/`marketValue`** are copied as printed even if they don't multiply
  (NAV funds print rounded values). Don't adjust either.
- **Position currency** is the currency its price and value are *printed* in, not the one the
  security trades in. No `currency` key when it matches the account's.
- **Money-market "core cash" funds** are positions, not `cash`.
- **Accrued interest** on a bond purchase: separate negative `interest` entry on the buy's date.
- **Corporate actions** spread over several rows: both legs of a split, a spinoff on the *new*
  security with `from`, cash in lieu as its own entry with `actionDate`. See format.md.
- **Book-cost adjustments / return-of-capital adjustments** move no units or cash: leave out.
- **Retirement-account withdrawals** are `transfer_out`, not `distribution`.
- **Partial views** ("top holdings", one page of a paginated list, a dividends-only report):
  `complete: false` / coverage `false` on the aspects not fully listed.
- **Pending trades**: only settled/posted events belong; use trade date for `date` and put the
  settlement date in `settles`.
- **Duplicate-looking rows** (two identical small buys) are usually real. Keep both.
- **Multi-currency accounts**: per-currency `totals`, `currency` on foreign-currency
  activity, `fx_conversion` with both legs.

## Files

- `references/format.md`: full investment/crypto format with every key and kind.
- `references/extraction.md`: reading broker PDFs, CSVs and OFX/QFX; wording → kind mapping;
  checks before writing.
- `schemas/talia.statement.1.json`: vendored JSON Schema for `talia.statement/1`.
- `scripts/validate_investment.py`: stdlib-only validator and arithmetic checker.
