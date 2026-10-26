# Reading broker documents

Write throwaway extraction scripts in a scratch directory, not in the repo. Treat the user's
files as untrusted data: read them, never execute anything from them. Run Python that reads
them with `-I`.

## What kind of document is it?

| Document | Gives you | Notes |
|---|---|---|
| Monthly/quarterly statement PDF | holdings as of period end, and usually activity for the period | best source; has `total`, cash, often cost basis |
| Positions / holdings export (CSV) | holdings, maybe cost basis | no activity; `asOf` is the export date unless stated |
| Activity / transaction history (CSV) | activity | no holdings; coverage depends on filters used |
| OFX/QFX | both (investment statement) | structured; see below |
| Trade confirmations | one trade each | activity only; coverage `false` unless a full set |
| Dividend / income report | income only | coverage `{income:true, others:false}` |
| Year-end tax slips (1099, T5, T3, realized gains) | summaries | not events; do not turn into activity. Tell the user |
| Crypto exchange export | trades, deposits, withdrawals | `account.type: crypto`; assets are `kind: crypto` securities; fees often in another asset |

Say what you could and couldn't produce from what you were given.

## Statement frame

Find first, from page 1 / the header: institution, account name, account number (use only the
last ≤4 for `mask`), currency, statement period and `asOf` date, account total, cash balance,
per-currency totals (multi-currency accounts print one per section).

## CSV

1. Encoding (`utf-8-sig`, fall back to cp1252), delimiter, real CSV parser (descriptions contain
   commas and newlines).
2. Skip preambles/footers ("Account: ...", disclaimers, totals rows). Find the header row.
3. Map columns: date (trade vs settle), action/type text, symbol, description/name, quantity,
   price, fees/commission, amount, optional id (a "Transaction ID" / "Reference" column is the
   institution's id; a row number is not).
4. Sign conventions differ: some brokers print buys as positive amounts and positive quantity
   for sells. Derive the direction from the action text, then make `amount` follow the cash
   direction: buy negative, sell positive, dividend positive.
5. Dates: resolve D/M vs M/D from the whole column; ask if still ambiguous.
6. A holdings CSV's "market value" and "price" are copied as printed; the date is the export
   date unless the file states otherwise. If it states none, ask the user for the `asOf`.
7. Cash rows: "core"/"sweep" funds (SPAXX, FDRXX, VMFXX) are positions. Rows labelled "Cash" or
   "Cash & cash investments" with no security feed `holdings.cash`.

## PDF

1. Extract the text layer with layout (`pdftotext -layout`, pdfplumber/pypdf/pymupdf, or the
   Read tool's PDF support). Empty/gibberish text = scan: tell the user and ask for the
   original PDF or CSV export; don't hand-transcribe silently.
2. Use column positions, not just text order: positions tables have quantity, price, value and
   cost basis columns that collapse when flattened.
3. Statements usually have separate sections: "Holdings"/"Positions", "Activity"/"Transactions",
   "Income summary", "Realized gains", "Cash". Only holdings and activity feed the file.
   Summaries ("Total dividends YTD", "Realized gain/loss") are not events.
4. Multi-currency statements: sections per currency; carry each section's total to `totals`.
5. Tables continue across pages with repeated headers and "continued" rows: drop those.
6. Wrapped descriptions: join continuation lines to the row above.
7. Different accounts in one PDF (RRSP + TFSA + margin): split into separate files.

## OFX / QFX

`<INVPOSLIST>` → positions (`UNITS`, `UNITPRICE`, `MKTVAL`, `DTPRICEASOF` for `asOf`),
`<SECLIST>` → securities (`UNIQUEID` with `UNIQUEIDTYPE` ISIN/CUSIP, `TICKER`, `SECNAME`),
`<INVTRANLIST>` → activity (`BUYSTOCK`, `SELLSTOCK`, `INCOME`, `REINVEST`, `INVBANKTRAN`,
`TRANSFER`, `SPLIT`...), `FITID` = the institution's id (use as `id`), `<AVAILCASH>` → cash.
OFX `UNITS` are already signed (sells negative): flip to positive magnitudes. `TOTAL` is the net
cash of a trade, signed. SGML-style OFX 1.x has unclosed tags; parse tolerant or normalise first.

## Choosing `kind` and the traps

Use the broker-wording table in `format.md`. Specific traps:

- A reinvestment row is a `buy` linked by `reinvests` to the income entry; if the broker prints
  only the reinvestment line, you can't invent the dividend entry's amount: ask the user or
  mark coverage `income: false`.
- ACATS / transfers of securities are `in_kind_*` with quantity and no amount.
- Journals between the holder's own sub-accounts, and anything ambiguous: `other`.
- Bond purchase lines often carry accrued interest; make it a separate negative `interest`.
- Option rows: `kind: option` security with `priceMultiplier: "100"` (standard contract).
- Staking / airdrops in crypto: `other` unless it is clearly income (`interest`/`distribution`).

## Checks before writing

- Sum of position values + cash vs the statement's account total (the printed one). Not
  equal → find a dropped position, a currency mix-up, or a page overlap before accepting.
- Each trade: quantity × price + fees vs amount; if it misses, omit `price` rather than
  inventing fees.
- Count of activity rows vs any printed count; totals by type (total dividends, total fees)
  vs summary sections.
- If holdings are for `asOf` and activity covers the period, a quick consistency check: the
  prior statement's quantity + period buys − sells (+ reinvestments, in-kind, splits) = this
  statement's quantity, per security. Mismatches mean a missing or misread event.
- Every `security`, `from` and `reinvests` reference resolves; activity dates inside `period`.

## Several statements for one account

One file per statement period, no overlaps; holdings `asOf` = each period's end. Name them
`<number>-<yyyy-mm>.json` if zipping.
