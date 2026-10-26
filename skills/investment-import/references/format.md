# talia.statement/1: investment and crypto accounts

Machine-readable schema: `../schemas/talia.statement.1.json` (wins on any disagreement).

## Example

```json
{
  "format": "talia.statement/1",
  "generator": "claude investment-import 1",
  "account": { "type": "investment", "currency": "USD", "institution": "Fidelity", "mask": "4821" },
  "period": { "start": "2026-09-01", "end": "2026-09-30" },
  "coverage": { "securities": true, "cash": true, "flows": true, "income": true },

  "securities": {
    "vti": { "symbol": "VTI", "exchange": "ARCX", "isin": "US9229087690", "name": "Vanguard Total Stock Market ETF", "kind": "fund" },
    "spaxx": { "symbol": "SPAXX", "name": "Fidelity Government Money Market", "kind": "fund" }
  },

  "holdings": {
    "asOf": "2026-09-30",
    "complete": true,
    "quantities": "settled",
    "positions": [
      { "security": "vti", "quantity": "120.5", "price": "291.40", "marketValue": "35113.70", "costBasis": "30120.00" },
      { "security": "spaxx", "quantity": "1204.18", "price": "1.00", "marketValue": "1204.18" }
    ],
    "cash": [{ "currency": "USD", "amount": "0.00" }],
    "total": "36317.88"
  },

  "activity": [
    { "id": "88123", "kind": "transfer_in", "date": "2026-09-02", "amount": "3000.00", "description": "EFT FROM CHECKING" },
    { "id": "88124", "kind": "buy", "date": "2026-09-12", "settles": "2026-09-15",
      "security": "vti", "quantity": "10", "price": "288.10", "amount": "-2881.00" },
    { "id": "88140", "kind": "dividend", "date": "2026-09-25", "security": "vti", "amount": "72.35", "withholding": "12.77" },
    { "id": "88141", "kind": "buy", "reinvests": "88140", "date": "2026-09-25",
      "security": "vti", "quantity": "0.2483", "price": "291.40", "amount": "-72.35" }
  ]
}
```

## Value rules (everywhere)

| | Rule |
|---|---|
| Encoding | UTF-8 JSON, one top-level object, at most 10 MB |
| Money | decimal **string** `^-?\d+(\.\d+)?$`. No `+`, exponent, symbol, separators, spaces. Fraction digits beyond the currency's (2 USD, 0 JPY) must be zeros |
| Quantities, prices | decimal strings, any precision (stored to 8 decimals) |
| Dates | `YYYY-MM-DD`, real dates, the date the institution shows |
| Currencies | ISO 4217 upper case. Crypto assets are securities, not currencies |
| Signs | holder's side: into the account positive, out negative |
| Unknown keys | an **error**. Private data goes under `"x"` at any level |
| Order | arrays in any order |

## Envelope

| Key | Req | Notes |
|---|---|---|
| `format` | yes | `"talia.statement/1"` |
| `generator` | no | free text, not stored |
| `account.type` | yes | `investment` or `crypto` (must suit the Talia account) |
| `account.currency` | yes | must equal the Talia account's currency |
| `account.institution`, `account.name` | no | as the institution names them |
| `account.mask` | no | last 1-4 characters of the account number, never more. In a zip it must agree with the file name's number |
| `period` | with `activity` | `{start, end}` inclusive. A holdings-only file has none |

Never both `transactions`/`opening`/`closing` and `holdings`/`activity`.

## Securities

`securities` is an object: key of your choosing → security. Name each security once; positions
and activity refer to the key.

| Key | Notes |
|---|---|
| `isin`, `cusip` | include whenever shown. Upper case. ISIN = 12 characters, CUSIP = 9 |
| `symbol` | ticker as shown, without decorations like a trailing `**` |
| `exchange` | ISO 10383 MIC (`XNAS`, `XNYS`, `ARCX`, `XTSE`), 4 chars, **only if you know it**; requires `symbol`. Don't guess from the ticker |
| `name` | as the institution names it |
| `kind` | `equity`, `fund` (ETFs, mutual funds, money-market funds), `bond`, `gic` (GICs and CDs), `option`, `crypto`, `other`. **State it**; a new security without one is a question for the user |
| `priceMultiplier` | positive decimal string. `"100"` for a standard option contract, `"0.01"` for a bond quoted per 100 of face. Omit otherwise |

At least one of `symbol`, `isin`, `cusip`, `name` is required per security.

## Holdings

What the account held at the end of `asOf`.

| Key | Req | Notes |
|---|---|---|
| `asOf` | yes | the date the positions are as of, not the scrape date (unless the site shows live positions; then today) |
| `complete` | yes | `true` only if `positions` lists **every** holding, so an absent security was zero. A "top holdings" widget or one page of a list is `false` |
| `quantities` | no | `settled` or `trade`. State it when you can tell; without it Talia can't check holdings traded just before `asOf`. If the site doesn't say, the statement can: a trade dated in the last three business days before `asOf` that already shows in that position's quantity means `trade`; one that only shows in the next statement means `settled` |
| `positions` | yes | `[]` for an empty account |
| `positions[].security` | yes | key in `securities` |
| `positions[].quantity` | yes | negative for short positions |
| `positions[].price`, `marketValue`, `costBasis`, `acquiredOn`, `currency` | no | as printed. `currency` defaults to the account's |
| `cash` | no | `[{currency, amount}]`. **Present** = all the cash; `[]` = none; **absent** = couldn't see it (Talia asks). A money-market fund is a position even if the broker calls it "core cash" |
| `total` | no | account total as stated, in the account currency |
| `totals` | no | multi-currency: the total the statement prints per currency section (positions + cash in that currency): `[{"currency":"CAD","amount":"77372.37"},{"currency":"USD","amount":"100326.66"}]` |

- A position's `currency` is the one its price/value are **printed in**, not the one the
  security trades in. A Canadian broker reporting a US fund in CAD: no `currency`. In USD:
  `"currency": "USD"`.
- Copy `price` and `marketValue` as printed even if they don't multiply out (NAV funds print
  rounded values: 64.624 × 102.405 may show $6,617.93). With `total`/`totals` given, Talia can
  tell the value is right.
- Several lots of one security: separate positions each with `acquiredOn`.
- Options, bonds, GICs: give `marketValue` as shown; quantity × price isn't checked.

## Activity

One entry per event. `amount` is the **net cash** that moved, signed from the holder's side.
`fees` and `withholding` are **positive** magnitudes already included in `amount`.

| Key | Notes |
|---|---|
| `kind` (req) | see table |
| `date` (req) | trade date / date it happened |
| `settles` | settlement date, if shown |
| `id` | institution's own id only. Unique in file |
| `ref` | local name for `reinvests` to point at when the dividend has no id. Never stored. All `id`s and `ref`s differ |
| `description` | as the institution prints it |
| `security` | key in `securities` |
| `quantity` | positive magnitude (kind gives direction), except `corporate_action`/`other` which are signed |
| `price` | per unit, in `currency` |
| `amount` | net cash |
| `fees`, `withholding` | positive, inside `amount` |
| `currency` | currency of amount/fees/withholding/price, when not the account's |
| `reinvests` | on a `buy` only: the `id` or `ref` of the dividend/interest/distribution it reinvests |
| `legs` | `fx_conversion` only |
| `action`, `ratio`, `from`, `actionDate` | `corporate_action` only |

| `kind` | Needs | `amount` | Example |
|---|---|---|---|
| `buy` | `security`, `quantity`, `amount` | negative | 10 @ 288.10 + $4.95 fee: `"quantity":"10","price":"288.10","fees":"4.95","amount":"-2885.95"` |
| `sell` | `security`, `quantity`, `amount` | positive | 4 @ 110.00, $2 fee: `"amount":"438.00","fees":"2.00"` |
| `dividend`, `interest`, `distribution` | `amount` (`security` where there is one) | positive, **net** | $100 dividend, $15 withheld: `"amount":"85.00","withholding":"15.00"`. Accrued interest *paid* on a bond purchase: `interest`, **negative** amount, the bond as `security`, on the buy's date |
| `fee` | `amount` | negative | account / advisory fee |
| `tax_withholding` | `amount` | negative | tax withheld on its own row |
| `transfer_in`, `transfer_out` | `amount` | signed | deposit / withdrawal |
| `in_kind_in`, `in_kind_out` | `security`, `quantity` | none (no amount, fees, withholding) | shares moved from/to another broker |
| `fx_conversion` | `legs` | none | `"legs":[{"currency":"CAD","amount":"-1370.00"},{"currency":"USD","amount":"1000.00"}]`: both legs, signed, different currencies; **no** `security`, `quantity`, `price`, `amount` or `currency` on the entry |
| `corporate_action` | `security`, `action`, and `quantity` (or `actionDate` + `amount`) | usually none | `"action":"split"` (or `merger`, `spinoff`), `quantity` = **signed change** in units, `"ratio":["2","1"]` (new : old, whole numbers) if printed |
| `other` | whatever you know | if known | anything you can't place; imported for the user to classify, better than dropping |

### Price and fees on trades

Give `price` only when quantity × price, with the printed fees, equals `amount` within the
price's last printed decimal. Otherwise **omit `price`** and give `amount` as printed. Never
fill the gap with a computed `fees`: a few cents short on a US sale is often a regulatory fee
the statement doesn't print, and a few cents either way on a buy is often a rounded price. A
made-up fee is recorded as a fee that may not have happened. `fees` is for fees the statement
shows. Same for a trade priced in one currency and settled in another (a US fund bought in a
CAD account at a stated rate): omit `price`; keep it under `"x"` if wanted.

### Corporate actions

- **Split printed as two rows** (old line out, new line in, e.g. "RESULT OF REVERSE SPLIT"):
  write both as `corporate_action` `split` on the same security, each with its own signed
  `quantity`. Talia reads them as one split. A reverse split that rounds down and pays the
  fraction in cash is fine (9 shares, 1-for-2 → 4).
- **`ratio`** only when printed. If the row says what it was on ("STK SPLIT ON 21 SHS", +21),
  Talia works out the ratio. Don't compute it.
- **Spinoff**: `corporate_action` `spinoff` on the **new** security, `quantity` units received,
  `from` naming the parent when the row says ("SPINOFF ON 9 SHS FROM ... HONEYWELL INTL INC" →
  `"from":"hon"`). Add the parent to `securities` if absent.
- **Cash in lieu** of a fraction (often paid weeks later) is its own `corporate_action`: same
  `action`, `security` that action's security (or the new one for a spinoff's fraction),
  `actionDate` the effective date, positive `amount`, **no** `quantity`/`ratio`/`from`:
  `{"kind":"corporate_action","action":"split","date":"2026-08-19","security":"hon","actionDate":"2026-06-30","amount":"119.54","currency":"USD"}`
- **Book-cost adjustments** (return of capital, notional distributions) move no units or cash.
  No kind for them: leave out, or keep under `"x"`.

### Reinvested dividends

Two entries: the dividend, and a `buy` with `"reinvests"` naming the dividend's `id`, whose
`amount` is the reinvested cash. If the dividend has no institution id, give it
`"ref": "div-vti-0925"` (any unique name) and point `reinvests` at that. Never make up an `id`.

### Broker wording → kind

| The broker says | `kind` |
|---|---|
| YOU BOUGHT, BUY, PURCHASE, BOUGHT | `buy` |
| YOU SOLD, SELL, SALE, REDEMPTION | `sell` |
| DIVIDEND RECEIVED, CASH DIV, QUALIFIED DIVIDEND | `dividend` |
| REINVESTMENT, DIV REINVEST, DRIP | `buy` with `reinvests` (the dividend is its own entry) |
| INTEREST, INTEREST EARNED, CREDIT INTEREST | `interest` |
| CAP GAIN, LT/ST CAPITAL GAIN DISTRIBUTION, RETURN OF CAPITAL | `distribution` |
| FOREIGN TAX PAID, NRA TAX, TAX WITHHELD (own row) | `tax_withholding` |
| ADVISORY FEE, MANAGEMENT FEE, ACCOUNT FEE, ADR FEE | `fee` |
| ELECTRONIC FUNDS TRANSFER, DEPOSIT, CONTRIBUTION, JOURNALED IN | `transfer_in` |
| WITHDRAWAL, WIRE OUT, DISTRIBUTION TO YOU, JOURNALED OUT | `transfer_out` |
| TRANSFER OF SECURITIES IN/OUT, ACATS, RECEIVED IN KIND | `in_kind_in` / `in_kind_out` |
| CURRENCY CONVERSION, FX, FOREIGN EXCHANGE | `fx_conversion` (combine the two legs into one entry) |
| STOCK SPLIT, REVERSE SPLIT, MERGER, SPIN-OFF, EXCHANGE ... RESULT OF REVERSE SPLIT | `corporate_action` |
| CASH-LIEU, CASH IN LIEU OF FRAC SHARES | `corporate_action` with `actionDate`, not `other` |
| BOUGHT ... ACCR. INT. (second row on a bond purchase) | `interest`, negative, on the buy's date |
| ADJUST ... TO BOOK COST, RETURN OF CAPITAL ADJUSTMENT | none: leave out, or under `"x"` |
| JOURNAL between the holder's own sub-accounts, anything ambiguous | `other`, with the institution's description |

A "distribution" paid **to the holder out of a retirement account** (IRA/RRIF withdrawal) is
`transfer_out`, not `distribution`. `distribution` is income from a fund.

## Coverage

Required with `activity`, not allowed without it. States which kinds of change `activity`
lists **completely** for `period`:

| Key | `true` means you included every… |
|---|---|
| `securities` | change in a quantity: buys, sells, reinvestments, in-kind moves, corporate actions |
| `cash` | change in cash: trades, income, fees, withholding, conversions, transfers |
| `flows` | movement into or out of the account, in cash or in kind |
| `income` | dividend, interest and distribution |

Full history for the period: all four `true`. A dividends-only page:
`{"securities":false,"cash":false,"flows":false,"income":true}`. **When in doubt, `false`.**
Every `activity` date must fall inside `period` or the file is rejected (an event outside it
contradicts the coverage claim), so set `period` to the range you actually read.

## What Talia checks

- Position `quantity × price` vs `marketValue` (within the price's rounding; not bonds,
  options, GICs); positions + cash vs `total`; each currency's positions + cash vs `totals`.
- Each event's arithmetic (buy: quantity × price + fees = −amount) and sign.
- Activity against holdings across files, using coverage.
- Disagreements go to the user's review, never rejected, never adjusted.

## One-tap import (no questions for the user)

- Holdings: say what the cash is (`"cash": []` if none), give `total`/`totals` when shown,
  state `quantities`, give every security a `kind`.
- Activity: institution ids wherever they exist, specific kinds rather than `other`, `price`
  only when it closes, spinoff `from` and cash-in-lieu `actionDate`, both FX legs.
- Deterministic output: same data → same bytes.

## Several accounts: zip

Files in a `.zip`, each file name starting with the account number as entered in Talia
(at least 4 digits, then end of name, `-`, `_`, space or `.`): `4821-brokerage.json`,
`30117755-rrsp.json`. Digits only. `account.mask`, if present, must agree. Several files per
account are fine (imported oldest first). Max 200 files, 100 MB unpacked, 10 MB per file.
Ask the user for the number; you can't read it from Talia.

## Rejection messages

Talia lists each problem with its JSON path, e.g.
`activity[3].amount: expected a decimal string like "12.50", got a number` or
`holdings.positions[0].security: "vxus" is not a key in securities`. Fix the extraction and
regenerate; don't patch around the message. "Update Talia to import this file" means the
file's `format` is newer than the user's Talia: write `talia.statement/1` or ask them to update.
