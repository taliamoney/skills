#!/usr/bin/env python3
"""Validate a Talia investment/crypto statement file (talia.statement/1).

Usage: validate_investment.py FILE.json [FILE.json ...]

Stdlib only. Errors are what Talia would reject (exit 1). Warnings are figures
that disagree, which Talia sends to the user's review instead; investigate them
but never adjust a printed figure to silence one. Bank/card files are out of scope.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal

DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CCY = re.compile(r"^[A-Z]{3}$")
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
CUSIP = re.compile(r"^[A-Z0-9]{9}$")
MIC = re.compile(r"^[A-Z0-9]{4}$")
ZERO_DEC = {"JPY", "KRW", "VND", "CLP", "ISK", "HUF"}
THREE_DEC = {"BHD", "KWD", "OMR", "JOD", "TND"}

TOP = {"format", "generator", "account", "period", "coverage", "securities", "holdings", "activity", "x"}
ACCOUNT = {"type", "currency", "institution", "name", "mask", "x"}
SEC = {"symbol", "exchange", "isin", "cusip", "name", "kind", "priceMultiplier", "x"}
SEC_KINDS = {"equity", "fund", "bond", "gic", "option", "crypto", "other"}
HOLD = {"asOf", "complete", "quantities", "positions", "cash", "total", "totals", "x"}
POS = {"security", "quantity", "price", "marketValue", "costBasis", "acquiredOn", "currency", "x"}
ACT = {"kind", "date", "settles", "id", "ref", "description", "security", "quantity", "price", "amount",
       "fees", "withholding", "currency", "reinvests", "legs", "action", "ratio", "from", "actionDate", "x"}
KINDS = {"buy", "sell", "dividend", "interest", "distribution", "fee", "tax_withholding", "transfer_in",
         "transfer_out", "in_kind_in", "in_kind_out", "fx_conversion", "corporate_action", "other"}
INCOME = {"dividend", "interest", "distribution"}
NEEDS_AMOUNT = INCOME | {"fee", "tax_withholding", "transfer_in", "transfer_out"}
COV = {"securities", "cash", "flows", "income"}


class V:
    def __init__(self):
        self.errors, self.warnings = [], []
        self.ccy = None

    def err(self, path, msg):
        self.errors.append(f"{path}: {msg}")

    def warn(self, path, msg):
        self.warnings.append(f"{path}: {msg}")

    def keys(self, obj, allowed, path):
        for k in obj:
            if k not in allowed:
                self.err(f"{path}.{k}", 'unknown key (keep private data under "x")')

    def date(self, v, path):
        if isinstance(v, str) and DATE.match(v):
            try:
                return date.fromisoformat(v)
            except ValueError:
                pass
        self.err(path, f'expected a date like "2026-09-30", got {v!r}')
        return None

    def dec(self, v, path, ccy=None, money=False, nonneg=False):
        if not isinstance(v, str) or not DECIMAL.match(v):
            what = "a number" if isinstance(v, (int, float)) and not isinstance(v, bool) else repr(v)
            self.err(path, f'expected a decimal string like "12.50", got {what}')
            return None
        if nonneg and v.startswith("-"):
            self.err(path, f"must not be negative, got {v}")
            return None
        if money:
            places = 0 if ccy in ZERO_DEC else 3 if ccy in THREE_DEC else 2
            frac = v.split(".")[1] if "." in v else ""
            if len(frac) > places and frac[places:].strip("0"):
                self.err(path, f"{v} has more than {places} decimal places for {ccy}")
        return Decimal(v)

    def currency(self, v, path):
        if not isinstance(v, str) or not CCY.match(v):
            self.err(path, f'expected ISO 4217 upper case like "USD", got {v!r}')
            return None
        return v


def places(s):
    return len(s.split(".")[1]) if "." in s else 0


def validate(doc):
    v = V()
    if not isinstance(doc, dict):
        v.err("$", "top level must be a JSON object")
        return v
    v.keys(doc, TOP, "$")
    if doc.get("format") != "talia.statement/1":
        v.err("format", f'must be "talia.statement/1", got {doc.get("format")!r}')
    for k in ("transactions", "opening", "closing"):
        if k in doc:
            v.err(k, "bank/card key; investment files carry holdings/activity, never transactions/opening/closing")

    acct = doc.get("account")
    if not isinstance(acct, dict):
        v.err("account", "required object")
    else:
        v.keys(acct, ACCOUNT, "account")
        if acct.get("type") not in ("investment", "crypto"):
            v.err("account.type", f"expected investment or crypto, got {acct.get('type')!r}")
        v.ccy = v.currency(acct.get("currency"), "account.currency")
        m = acct.get("mask")
        if m is not None and not (isinstance(m, str) and re.match(r"^[A-Za-z0-9]{1,4}$", m)):
            v.err("account.mask", "at most the last 4 letters/digits of the account number")
    ccy = v.ccy

    has_h, has_a = "holdings" in doc, "activity" in doc
    if not has_h and not has_a:
        v.err("$", "needs holdings and/or activity")

    # period / coverage
    start = end = None
    period = doc.get("period")
    if period is not None:
        if not isinstance(period, dict):
            v.err("period", "expected an object")
        else:
            v.keys(period, {"start", "end", "x"}, "period")
            start = v.date(period.get("start"), "period.start")
            end = v.date(period.get("end"), "period.end")
            if start and end and start > end:
                v.err("period", "start is after end")
    if has_a and period is None:
        v.err("period", "required with activity")
    if has_a and "coverage" not in doc:
        v.err("coverage", "required with activity")
    if "coverage" in doc:
        c = doc["coverage"]
        if not has_a:
            v.err("coverage", "not allowed without activity")
        if not isinstance(c, dict):
            v.err("coverage", "expected an object")
        else:
            v.keys(c, COV | {"x"}, "coverage")
            for k in COV:
                if not isinstance(c.get(k), bool):
                    v.err(f"coverage.{k}", "required true/false")

    # securities
    secs = doc.get("securities", {})
    if not isinstance(secs, dict):
        v.err("securities", "expected an object keyed by your own security keys")
        secs = {}
    for key, s in secs.items():
        if key == "x":
            continue
        p = f"securities.{key}"
        if not isinstance(s, dict):
            v.err(p, "expected an object")
            continue
        v.keys(s, SEC, p)
        if not any(isinstance(s.get(k), str) and s[k].strip() for k in ("symbol", "isin", "cusip", "name")):
            v.err(p, "needs at least one of symbol, isin, cusip, name")
        if "exchange" in s:
            if "symbol" not in s:
                v.err(f"{p}.exchange", "requires symbol")
            if not (isinstance(s["exchange"], str) and MIC.match(s["exchange"])):
                v.err(f"{p}.exchange", f"expected a 4-character ISO 10383 MIC like XNAS, got {s['exchange']!r}")
        if "isin" in s and not (isinstance(s["isin"], str) and ISIN.match(s["isin"])):
            v.err(f"{p}.isin", f"expected a 12-character upper-case ISIN, got {s['isin']!r}")
        if "cusip" in s and not (isinstance(s["cusip"], str) and CUSIP.match(s["cusip"])):
            v.err(f"{p}.cusip", f"expected a 9-character upper-case CUSIP, got {s['cusip']!r}")
        if "kind" in s and s["kind"] not in SEC_KINDS:
            v.err(f"{p}.kind", f"expected one of {sorted(SEC_KINDS)}, got {s['kind']!r}")
        elif "kind" not in s:
            v.warn(p, "no kind: Talia will ask the user (state equity/fund/bond/gic/option/crypto/other)")
        if "priceMultiplier" in s:
            pm = v.dec(s["priceMultiplier"], f"{p}.priceMultiplier", nonneg=True)
            if pm is not None and pm == 0:
                v.err(f"{p}.priceMultiplier", "must be positive")
    mult = {}
    for key, s in secs.items():
        if isinstance(s, dict) and isinstance(s.get("priceMultiplier"), str) and DECIMAL.match(s["priceMultiplier"]):
            mult[key] = Decimal(s["priceMultiplier"])
    skind = {k: s.get("kind") for k, s in secs.items() if isinstance(s, dict)}

    def ref_ok(key, path):
        if not isinstance(key, str) or key not in secs or key == "x":
            v.err(path, f"{key!r} is not a key in securities")
            return False
        return True

    # holdings
    if has_h:
        validate_holdings(v, doc["holdings"], ccy, ref_ok, skind)
    if has_a:
        validate_activity(v, doc["activity"], ccy, start, end, ref_ok, mult, skind)
    return v


def validate_holdings(v, h, ccy, ref_ok, skind):
    if not isinstance(h, dict):
        v.err("holdings", "expected an object")
        return
    v.keys(h, HOLD, "holdings")
    v.date(h.get("asOf"), "holdings.asOf")
    if not isinstance(h.get("complete"), bool):
        v.err("holdings.complete", "required true/false (true only if positions lists every holding)")
    if "quantities" in h and h["quantities"] not in ("settled", "trade"):
        v.err("holdings.quantities", f"expected settled or trade, got {h['quantities']!r}")
    elif "quantities" not in h:
        v.warn("holdings.quantities", "not stated; Talia can't check holdings traded just before asOf (state settled/trade if you can tell)")
    positions = h.get("positions")
    if not isinstance(positions, list):
        v.err("holdings.positions", "required array ([] for an empty account)")
        positions = []
    value_by_ccy = {}
    all_values = True
    for i, p in enumerate(positions):
        path = f"holdings.positions[{i}]"
        if not isinstance(p, dict):
            v.err(path, "expected an object")
            all_values = False
            continue
        v.keys(p, POS, path)
        ref_ok(p.get("security"), f"{path}.security")
        q = v.dec(p.get("quantity"), f"{path}.quantity")
        pc = p.get("currency", ccy)
        if "currency" in p:
            v.currency(p["currency"], f"{path}.currency")
        price = v.dec(p["price"], f"{path}.price", nonneg=True) if "price" in p else None
        mv = v.dec(p["marketValue"], f"{path}.marketValue", pc, True) if "marketValue" in p else None
        if "costBasis" in p:
            v.dec(p["costBasis"], f"{path}.costBasis", pc, True)
        if "acquiredOn" in p:
            v.date(p["acquiredOn"], f"{path}.acquiredOn")
        if mv is None:
            all_values = False
        else:
            value_by_ccy[pc] = value_by_ccy.get(pc, Decimal(0)) + mv
        if q is not None and price is not None and mv is not None and skind.get(p.get("security")) not in ("bond", "option", "gic"):
            tol = abs(q) * Decimal(5) / (Decimal(10) ** (places(p["price"]) + 1)) + Decimal("0.005")
            if abs(q * price - mv) > tol:
                v.warn(path, f"quantity {p['quantity']} x price {p['price']} = {q * price}, marketValue is {p['marketValue']} "
                             "(copy as printed; fine if the statement itself doesn't multiply out)")

    cash = h.get("cash")
    cash_by_ccy = {}
    if cash is None:
        v.warn("holdings.cash", "absent: Talia will ask the user. Use [] if the account has none")
    elif not isinstance(cash, list):
        v.err("holdings.cash", "expected an array of {currency, amount}")
    else:
        for i, c in enumerate(cash):
            path = f"holdings.cash[{i}]"
            if not isinstance(c, dict):
                v.err(path, "expected {currency, amount}")
                continue
            v.keys(c, {"currency", "amount", "x"}, path)
            cc = v.currency(c.get("currency"), f"{path}.currency")
            a = v.dec(c.get("amount"), f"{path}.amount", cc, True)
            if cc and a is not None:
                cash_by_ccy[cc] = cash_by_ccy.get(cc, Decimal(0)) + a

    if "total" in h:
        t = v.dec(h["total"], "holdings.total", ccy, True)
        if t is not None and all_values and cash is not None and "totals" not in h and ccy and set(value_by_ccy) <= {ccy} and set(cash_by_ccy) <= {ccy}:
            got = value_by_ccy.get(ccy, Decimal(0)) + cash_by_ccy.get(ccy, Decimal(0))
            if got != t:
                v.warn("holdings.total", f"positions + cash = {got}, statement total is {h['total']} "
                                         f"(off by {t - got}); a position may be missing, or cash is wrong")
    else:
        v.warn("holdings.total", "not given; include the account total whenever the statement prints one")
    if "totals" in h:
        ts = h["totals"]
        if not isinstance(ts, list):
            v.err("holdings.totals", "expected an array of {currency, amount}")
        else:
            for i, t in enumerate(ts):
                path = f"holdings.totals[{i}]"
                if not isinstance(t, dict):
                    v.err(path, "expected {currency, amount}")
                    continue
                v.keys(t, {"currency", "amount", "x"}, path)
                cc = v.currency(t.get("currency"), f"{path}.currency")
                a = v.dec(t.get("amount"), f"{path}.amount", cc, True)
                if cc and a is not None and all_values and cash is not None:
                    got = value_by_ccy.get(cc, Decimal(0)) + cash_by_ccy.get(cc, Decimal(0))
                    if got != a:
                        v.warn(path, f"{cc} positions + cash = {got}, statement total is {t['amount']} (off by {a - got})")


def validate_activity(v, acts, ccy, start, end, ref_ok, mult, skind):
    if not isinstance(acts, list):
        v.err("activity", "expected an array")
        return
    ids, refs = {}, {}
    for i, a in enumerate(acts):
        if isinstance(a, dict):
            for key, bucket in (("id", ids), ("ref", refs)):
                val = a.get(key)
                if isinstance(val, str) and val.strip():
                    bucket.setdefault(val, []).append(i)
    for name, bucket in (("id", ids), ("ref", refs)):
        for val, where in bucket.items():
            if len(where) > 1:
                v.err(f"activity[{where[1]}].{name}", f"duplicate {name} {val!r} (also activity[{where[0]}])")
    for val in set(ids) & set(refs):
        v.err("activity", f"{val!r} is used as both an id and a ref; they must all differ")
    kinds_by_key = {}
    for i, a in enumerate(acts):
        if isinstance(a, dict) and a.get("kind") in INCOME:
            for k in ("id", "ref"):
                if isinstance(a.get(k), str):
                    kinds_by_key[a[k]] = a["kind"]

    for i, a in enumerate(acts):
        p = f"activity[{i}]"
        if not isinstance(a, dict):
            v.err(p, "expected an object")
            continue
        v.keys(a, ACT, p)
        kind = a.get("kind")
        if kind not in KINDS:
            v.err(f"{p}.kind", f"expected one of {sorted(KINDS)}, got {kind!r}")
            continue
        d = v.date(a.get("date"), f"{p}.date")
        if d and start and end and not start <= d <= end:
            v.err(f"{p}.date", f"{a['date']} is outside period {start}..{end} (contradicts coverage); widen period or drop the row")
        for k in ("settles", "actionDate"):
            if k in a:
                v.date(a[k], f"{p}.{k}")
        for k in ("id", "ref"):
            if k in a and not (isinstance(a[k], str) and a[k].strip()):
                v.err(f"{p}.{k}", "expected a non-empty string")
        ac = a.get("currency", ccy)
        if "currency" in a:
            v.currency(a["currency"], f"{p}.currency")
        sec = a.get("security")
        if "security" in a:
            ref_ok(sec, f"{p}.security")
        if "from" in a:
            ref_ok(a["from"], f"{p}.from")
        q = amt = price = fees = None
        if "quantity" in a:
            q = v.dec(a["quantity"], f"{p}.quantity")
        if "amount" in a:
            amt = v.dec(a["amount"], f"{p}.amount", ac, True)
        if "price" in a:
            price = v.dec(a["price"], f"{p}.price", nonneg=True)
        if "fees" in a:
            fees = v.dec(a["fees"], f"{p}.fees", ac, True, nonneg=True)
        wh = v.dec(a["withholding"], f"{p}.withholding", ac, True, nonneg=True) if "withholding" in a else None

        if kind != "fx_conversion" and "legs" in a:
            v.err(f"{p}.legs", "only for fx_conversion")
        if kind != "corporate_action":
            for k in ("action", "ratio", "from", "actionDate"):
                if k in a:
                    v.err(f"{p}.{k}", "only for corporate_action")
        if "reinvests" in a:
            if kind != "buy":
                v.err(f"{p}.reinvests", "only on a buy")
            elif a["reinvests"] not in kinds_by_key:
                v.err(f"{p}.reinvests", f"{a['reinvests']!r} is not the id/ref of a dividend, interest or distribution in this file")

        if kind in ("buy", "sell"):
            for k in ("security", "quantity", "amount"):
                if k not in a:
                    v.err(f"{p}.{k}", f"required for {kind}")
            if q is not None and q < 0:
                v.err(f"{p}.quantity", "must be a positive magnitude; the kind gives the direction")
            if amt is not None:
                if kind == "buy" and amt > 0:
                    v.err(f"{p}.amount", "a buy's amount must be negative (cash out)")
                if kind == "sell" and amt < 0:
                    v.err(f"{p}.amount", "a sell's amount must be positive (cash in)")
            if q is not None and price is not None and amt is not None:
                m = mult.get(sec, Decimal(1))
                gross = q * price * m
                f = fees or Decimal(0)
                expect = -(gross + f) if kind == "buy" else gross - f
                tol = q * m * Decimal(5) / (Decimal(10) ** (places(a["price"]) + 1)) + Decimal("0.005")
                if abs(expect - amt) > tol:
                    v.warn(p, f"{kind} arithmetic: {a['quantity']} x {a['price']}"
                              f"{' x ' + str(m) if m != 1 else ''}{' with fees ' + a['fees'] if fees else ''} = {expect}, "
                              f"amount is {a['amount']}. Omit price (don't invent fees) unless it closes")
        elif kind in NEEDS_AMOUNT:
            if "amount" not in a:
                v.err(f"{p}.amount", f"required for {kind}")
            if q is not None and q < 0:
                v.err(f"{p}.quantity", "must be a positive magnitude")
            if amt is not None:
                if kind in INCOME and amt < 0 and not (kind == "interest" and "security" in a):
                    v.warn(p, f"negative {kind}: only accrued interest paid on a bond purchase is negative")
                if kind in ("fee", "tax_withholding") and amt > 0:
                    v.warn(p, f"{kind} amount is positive; fees and withholding rows are cash out (negative)")
                if kind == "transfer_in" and amt < 0 or kind == "transfer_out" and amt > 0:
                    v.warn(p, f"{kind} amount has the wrong sign for its direction")
        elif kind in ("in_kind_in", "in_kind_out"):
            for k in ("security", "quantity"):
                if k not in a:
                    v.err(f"{p}.{k}", f"required for {kind}")
            for k in ("amount", "fees", "withholding"):
                if k in a:
                    v.err(f"{p}.{k}", f"not allowed on {kind} (no cash moves)")
            if q is not None and q < 0:
                v.err(f"{p}.quantity", "must be a positive magnitude")
        elif kind == "fx_conversion":
            for k in ("security", "quantity", "price", "amount", "currency"):
                if k in a:
                    v.err(f"{p}.{k}", "not allowed on fx_conversion; use legs")
            legs = a.get("legs")
            if not (isinstance(legs, list) and len(legs) == 2):
                v.err(f"{p}.legs", "required: exactly two legs [{currency, amount}, {currency, amount}]")
            else:
                cs = []
                signs = []
                for j, leg in enumerate(legs):
                    lp = f"{p}.legs[{j}]"
                    if not isinstance(leg, dict):
                        v.err(lp, "expected {currency, amount}")
                        continue
                    v.keys(leg, {"currency", "amount", "x"}, lp)
                    lc = v.currency(leg.get("currency"), f"{lp}.currency")
                    la = v.dec(leg.get("amount"), f"{lp}.amount", lc, True)
                    cs.append(lc)
                    if la is not None:
                        signs.append(la > 0)
                if len(cs) == 2 and cs[0] and cs[0] == cs[1]:
                    v.err(f"{p}.legs", "the two legs must be different currencies")
                if len(signs) == 2 and signs[0] == signs[1]:
                    v.warn(f"{p}.legs", "legs normally have opposite signs (one currency out, one in)")
        elif kind == "corporate_action":
            for k in ("security", "action"):
                if k not in a:
                    v.err(f"{p}.{k}", "required for corporate_action")
            if "action" in a and a["action"] not in ("split", "merger", "spinoff"):
                v.err(f"{p}.action", f"expected split, merger or spinoff, got {a['action']!r}")
            if "actionDate" in a:  # cash in lieu
                if "amount" not in a:
                    v.err(f"{p}.amount", "required for cash in lieu (actionDate)")
                for k in ("quantity", "ratio", "from"):
                    if k in a:
                        v.err(f"{p}.{k}", "not allowed on cash in lieu (actionDate)")
            elif "quantity" not in a:
                v.err(f"{p}.quantity", "required: the signed change in units")
            if "ratio" in a:
                r = a["ratio"]
                if not (isinstance(r, list) and len(r) == 2 and all(isinstance(x, str) and re.match(r"^[1-9]\d*$", x) for x in r)):
                    v.err(f"{p}.ratio", 'expected two whole-number strings [new, old] like ["2", "1"]')
            if a.get("action") == "spinoff" and "from" not in a and "actionDate" not in a:
                v.warn(p, "spinoff without from: name the parent security when the row says (answers a question Talia would ask)")
        elif kind == "other":
            pass
        if kind == "other":
            v.warn(p, "kind 'other': imported for the user to classify; use a specific kind if the wording fits")
        if kind in ("buy", "sell") and "id" not in a and "ref" not in a:
            pass


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    failed = False
    for path in argv[1:]:
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as e:
            print(f"{path}: cannot read: {e}")
            failed = True
            continue
        v = validate(doc)
        pos = len(doc.get("holdings", {}).get("positions", [])) if isinstance(doc, dict) and isinstance(doc.get("holdings"), dict) and isinstance(doc["holdings"].get("positions"), list) else 0
        act = len(doc["activity"]) if isinstance(doc, dict) and isinstance(doc.get("activity"), list) else 0
        print(f"{path}: {pos} positions, {act} activity entries, {len(v.errors)} errors, {len(v.warnings)} warnings")
        for e in v.errors:
            print(f"  ERROR   {e}")
        for w in v.warnings:
            print(f"  WARNING {w}")
        failed |= bool(v.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
