# talia.statement/1: bank and card accounts

The Talia statement format, version 1, for bank and card accounts. Machine-readable
schema: `../schemas/talia.statement.1.json` (wins on any disagreement).

## Example

```json
{
  "format": "talia.statement/1",
  "generator": "claude transaction-import 1",
  "account": { "type": "credit", "currency": "CAD", "institution": "RBC", "name": "Avion Visa", "mask": "0114" },
  "period": { "start": "2026-09-05", "end": "2026-10-04" },
  "opening": "-412.18",
  "closing": "-122.51",
  "transactions": [
    { "id": "2026090500123", "date": "2026-09-06", "amount": "-58.21", "description": "LOBLAWS #1123 TORONTO ON" },
    { "date": "2026-09-20", "amount": "412.18", "description": "PAYMENT - THANK YOU" },
    { "date": "2026-10-03", "amount": "-14.99", "description": "NETFLIX.COM", "pending": true }
  ]
}
```

## Keys

| Path | Req | Notes |
|---|---|---|
| `format` | yes | exactly `"talia.statement/1"` |
| `generator` | no | free text, not stored |
| `account.type` | yes | `banking` or `credit` here (`investment`/`crypto` are a different shape) |
| `account.currency` | yes | ISO 4217 upper case; must equal the Talia account's currency |
| `account.institution`, `account.name` | no | as the institution names them |
| `account.mask` | no | last 2-4 chars of the account number, never more |
| `period.start`, `period.end` | yes with transactions | inclusive |
| `opening`, `closing` | no | **as printed**. Give both when visible |
| `transactions` | yes | `[]` is fine |
| `transactions[].date` | yes | posted date, `YYYY-MM-DD` |
| `transactions[].amount` | yes | decimal string, holder's-side sign |
| `transactions[].description` | yes | raw, untouched |
| `transactions[].id` | no | institution's own id, unique in file |
| `transactions[].balance` | no | printed running balance after the row |
| `transactions[].pending` | no | `true` rows are skipped by Talia |
| `x` (any object) | no | your private data; ignored |

Any other key is a hard error.

## Value rules

- Money: string matching `^-?\d+(\.\d+)?$`. No `+`, no exponent, no symbol, no separators,
  no spaces. Fraction digits beyond the currency's decimals must be zeros.
- Dates: real calendar dates.
- Signs, always the account holder's side: into the account positive, out negative.
  Card purchase `-58.21`; card payment `412.18`; card balance owed is negative.

## What Talia does with it

- Checks `opening + sum(posted transactions) == closing`. Disagreement goes to the user's
  review (never rejected, never adjusted).
- With only `closing`, uses the previous import's close as the opening.
- Transactions dated outside `period` are flagged, not rejected.
- Byte-identical re-import is skipped cleanly. Overlapping files are deduplicated by `id`, else
  by date + amount + description (possible duplicates go to the user).
- Derives merchant and category from the raw description.

## One tap import

Both `opening` and `closing` stated and reconciling, no transaction already in an earlier file.
Deterministic output (stable key order, no timestamps).

## Several accounts: zip

Put files in a `.zip`; each file name starts with the account number as entered in Talia
(at least 4 digits, then end of name, `-`, `_`, space or `.`), e.g. `4821-visa-2026-09.json`.
Digits only (`6963797`, not `696-3797`). `account.mask`, if present, must agree with it.
Max 200 files, 10 MB each. Ask the user for the number; you can't read it from Talia.

## Rejection messages

Talia lists each problem with a JSON path, e.g.
`transactions[12].date: expected a date like "2026-09-30", got "2026-09-31"`.
Fix the extraction and regenerate; don't patch around it.
