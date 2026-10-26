---
name: transaction-import
description: Turn a user's bank or credit-card statement (PDF or CSV) into a Talia statement file (talia.statement/1 JSON) that imports into the Talia app. Use whenever the user hands you a statement, transaction export, or asks to get bank/card transactions into Talia.
---

# Building a Talia transaction import

Goal: read a bank or card statement the user gives you (PDF, CSV, or similar) and write
one `talia.statement/1` JSON file per account and statement period that Talia imports
without asking the user to map columns, signs or dates.

This skill covers **bank (`banking`) and card (`credit`) accounts** only. Investment and
crypto statements use a different shape (holdings and activity); don't attempt them with
this skill. This skill is self-contained: everything you need is in `references/`.
The machine-readable JSON Schema is vendored at `schemas/talia.statement.1.json`; if it
disagrees with `references/format.md`, the schema wins. Format versions are immutable: a
change ships as a new version (`talia.statement/2`), never an edit to `/1`. Write `/1` files
unless the user tells you their Talia needs a newer version and you have its schema.

## Principles (these decide every judgement call)

1. **Copy, don't compute.** Every amount and balance in the file is one the statement
   prints. Never derive `opening`/`closing` from the transactions: Talia checks them
   against each other, and a computed figure hides the very error the check exists to catch.
2. **Leave out rather than guess.** Optional fields are optional because Talia asks the
   user when they're absent. A wrong value is silent; a missing one is a question.
3. **Never invent ids.** `id` is only the institution's own transaction id. No hashes, no
   row numbers.
4. **Descriptions verbatim.** No tidying, no merchant names, no categories. Talia derives
   the merchant and categorizes.
5. **Don't force reconciliation.** If opening + transactions ≠ closing as printed, write
   the figures as printed and tell the user. Never adjust a row to make it fit.

## Workflow

1. **Gather context from the user** (ask only what you can't see in the file):
   - Which Talia account is this for, and its account type (`banking` or `credit`)?
   - Currency (usually printed; confirm if not).
   - If producing several accounts for a zip: the account number *as entered in Talia*
     (last 4+ digits) for each file name.
2. **Inspect the source** (see `references/extraction.md`):
   - CSV: detect encoding, delimiter, header row, date order, sign convention, and whether
     debit/credit are separate columns.
   - PDF: extract text with layout preserved. If there is no text layer (a scan), say so
     and ask for the original PDF or a CSV; do not hand-transcribe from OCR guesses
     without telling the user.
3. **Identify the statement frame**: period start/end, opening and closing balance (printed
   on the statement; CSVs often lack them, so omit rather than compute), institution, account
   mask (last 4 only).
4. **Extract transactions** into an intermediate list in a scratch script, preserving the
   raw description text, the posted date, and the printed amount.
5. **Normalize** only these things: dates → `YYYY-MM-DD`; amounts → decimal strings with
   the holder's-side sign (money in positive, money out negative; card purchases negative,
   payments positive); drop pending rows (or set `"pending": true`).
6. **Write the JSON** with stable key order, 2-space indent, trailing newline, no timestamps
   (re-running on the same input must produce byte-identical output so Talia can skip a
   re-import cleanly). Anything you want to keep goes under `"x"`.
7. **Validate and reconcile**:
   ```
   python3 skills/transaction-import/scripts/validate_statement.py out.json
   ```
   Fix every error at its cause in the extraction (do not delete the row it names). Treat
   reconciliation warnings as real: investigate a missing or double-counted row, a sign
   flip, or a page-break artefact before concluding the statement itself is off.
8. **Report to the user**: file path(s), transaction count, period, whether opening/closing
   reconcile, any rows you were unsure about (ambiguous dates, wrapped descriptions, skipped
   pending items), and how to import (Accounts › Import statements, or the account's import
   action; zip for multiple accounts).

## Hard rules

- Money, quantities: **strings**, never JSON numbers. `"-58.21"`, not `-58.21`, not `"$58.21"`,
  not `"1,234.50"`, not `"+5"`.
- Decimal places must not exceed the currency's (2 for USD/CAD/EUR, 0 for JPY).
- Dates are real calendar dates, no time or zone. Use the **posted** date, not the
  transaction date, when both are printed.
- Unknown keys are an error. Only keys listed in `references/format.md`, plus `"x"`.
- A file is bank/card (`transactions`) **or** investment (`holdings`/`activity`), never both.
- Never put a full account number, credentials or tokens in a file (not even under `"x"`).
  `mask` is at most the last 4 characters.
- One account per file. Don't merge two accounts' rows because the PDF bundles them.
- Prefer one file per statement period. Avoid overlapping files for the same account.

## Common traps

- **Sign convention**: many CSVs show card charges as positive. Negate them. Check against
  the closing balance direction: a card balance owed is *negative*.
- **Separate debit/credit columns**: amount = credit − debit (as strings; do the subtraction
  with `decimal.Decimal`, never floats), but only when one side is empty or the
  statement prints a signed figure elsewhere.
- **Dates without a year** (PDF statements, e.g. "Sep 06"): take the year from the statement
  period; handle Dec/Jan statements that straddle a year boundary.
- **Date order**: `03/04/2026` is ambiguous. Resolve from the whole column (any value with a
  first or second part > 12), the bank's locale, or ask the user. Never guess silently.
- **Wrapped descriptions** in PDFs: join continuation lines to the row above; they are not
  transactions.
- **Page headers/footers, "continued" rows, subtotals, "balance forward"** lines are not
  transactions.
- **Foreign-currency rows**: `amount` stays in the account's currency as posted; keep the
  original amount/currency text in the description as printed or under `"x"`.
- **Holds / pending**: authorization holds that post later under another amount: include
  only the posted one.
- **Duplicate-looking rows** (two identical coffees the same day) are usually real. Keep
  both; only drop rows that are clearly repeated page overlap.
- **Running balance column**: if the statement prints one, include it per row as `balance`,
  copied, so Talia can pinpoint a missing row.

## Files

- `references/format.md`: condensed bank/card format spec with examples.
- `references/extraction.md`: concrete CSV and PDF extraction techniques and checks.
- `schemas/talia.statement.1.json`: the vendored JSON Schema (JSON Schema 2020-12) for `talia.statement/1`.
- `scripts/validate_statement.py`: stdlib-only validator and reconciler (no dependencies).
