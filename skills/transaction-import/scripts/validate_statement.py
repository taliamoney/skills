#!/usr/bin/env python3
"""Validate and reconcile a Talia bank/card statement file (talia.statement/1).

Usage: validate_statement.py FILE.json [FILE.json ...]

Stdlib only. Exits 1 if any file has errors (Talia would reject it); warnings
(figures that disagree, dates outside the period) exit 0 but are printed, since
Talia sends those to the user's review rather than rejecting them.
Investment/crypto files are out of scope here.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal

DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CCY = re.compile(r"^[A-Z]{3}$")
ZERO_DECIMALS = {"JPY", "KRW", "VND", "CLP", "ISK", "HUF"}
THREE_DECIMALS = {"BHD", "KWD", "OMR", "JOD", "TND"}

TOP = {"format", "generator", "account", "period", "opening", "closing", "transactions", "x"}
ACCOUNT = {"type", "currency", "institution", "name", "mask", "x"}
PERIOD = {"start", "end"}
TXN = {"id", "date", "amount", "description", "balance", "pending", "x"}


def check_keys(obj, allowed, path, errors):
    for k in obj:
        if k not in allowed:
            errors.append(f"{path}.{k}: unknown key (keep private data under \"x\")")


def check_date(v, path, errors):
    if not isinstance(v, str) or not DATE.match(v):
        errors.append(f"{path}: expected a date like \"2026-09-30\", got {v!r}")
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        errors.append(f"{path}: expected a date like \"2026-09-30\", got {v!r}")
        return None


def check_money(v, path, ccy, errors):
    if not isinstance(v, str) or not DECIMAL.match(v):
        kind = "a number" if isinstance(v, (int, float)) and not isinstance(v, bool) else repr(v)
        errors.append(f"{path}: expected a decimal string like \"12.50\", got {kind}")
        return None
    d = Decimal(v)
    places = 0 if ccy in ZERO_DECIMALS else 3 if ccy in THREE_DECIMALS else 2
    frac = v.split(".")[1] if "." in v else ""
    if len(frac) > places and frac[places:].strip("0"):
        errors.append(f"{path}: {v} has more than {places} decimal places for {ccy}")
    return d


def validate(doc):
    errors, warnings = [], []
    if not isinstance(doc, dict):
        return ["top level must be a JSON object"], warnings
    check_keys(doc, TOP, "$", errors)
    if doc.get("format") != "talia.statement/1":
        errors.append(f"format: must be \"talia.statement/1\", got {doc.get('format')!r}")
    for k in ("holdings", "activity", "securities", "coverage"):
        if k in doc:
            errors.append(f"{k}: investment section; this validator covers bank/card files only")

    acct = doc.get("account")
    ccy = None
    if not isinstance(acct, dict):
        errors.append("account: required object")
    else:
        check_keys(acct, ACCOUNT, "account", errors)
        if acct.get("type") not in ("banking", "credit"):
            errors.append(f"account.type: expected banking or credit, got {acct.get('type')!r}")
        ccy = acct.get("currency")
        if not isinstance(ccy, str) or not CCY.match(ccy):
            errors.append(f"account.currency: expected ISO 4217 upper case like \"USD\", got {ccy!r}")
            ccy = None
        mask = acct.get("mask")
        if mask is not None and (not isinstance(mask, str) or not 1 <= len(mask) <= 4):
            errors.append("account.mask: at most the last 4 characters of the account number")

    start = end = None
    period = doc.get("period")
    if not isinstance(period, dict):
        errors.append("period: required with transactions")
    else:
        check_keys(period, PERIOD, "period", errors)
        start = check_date(period.get("start"), "period.start", errors)
        end = check_date(period.get("end"), "period.end", errors)
        if start and end and start > end:
            errors.append("period: start is after end")

    opening = closing = None
    if "opening" in doc:
        opening = check_money(doc["opening"], "opening", ccy, errors)
    if "closing" in doc:
        closing = check_money(doc["closing"], "closing", ccy, errors)

    txns = doc.get("transactions")
    if not isinstance(txns, list):
        errors.append("transactions: required array ([] is fine)")
        return errors, warnings

    seen_ids = set()
    total = Decimal(0)
    ok_amounts = True
    prev_balance = opening
    chain_ok = True
    for i, t in enumerate(txns):
        p = f"transactions[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{p}: expected an object")
            ok_amounts = False
            continue
        check_keys(t, TXN, p, errors)
        d = check_date(t.get("date"), f"{p}.date", errors)
        amt = check_money(t.get("amount"), f"{p}.amount", ccy, errors)
        if not isinstance(t.get("description"), str) or not t["description"].strip():
            errors.append(f"{p}.description: required non-empty string")
        elif t["description"] != t["description"].strip():
            warnings.append(f"{p}.description: leading/trailing whitespace; copy the text as printed")
        if "pending" in t and not isinstance(t["pending"], bool):
            errors.append(f"{p}.pending: expected true or false")
        if "id" in t:
            if not isinstance(t["id"], str) or not t["id"]:
                errors.append(f"{p}.id: expected a non-empty string")
            elif t["id"] in seen_ids:
                errors.append(f"{p}.id: duplicate id {t['id']!r}")
            seen_ids.add(t.get("id"))
        bal = None
        if "balance" in t:
            bal = check_money(t["balance"], f"{p}.balance", ccy, errors)
        if amt is None:
            ok_amounts = False
            continue
        if d and start and end and not start <= d <= end:
            warnings.append(f"{p}.date: {t['date']} is outside period (Talia flags it for review)")
        if t.get("pending") is True:
            continue
        total += amt
        # Running-balance chain: only meaningful when file order is the statement order.
        if bal is not None and prev_balance is not None and prev_balance + amt != bal and chain_ok:
            chain_ok = False
            warnings.append(
                f"{p}: running balance {bal} != previous {prev_balance} + {amt}; "
                "a row is missing/duplicated/reordered, or the rows are not in statement order")
        if bal is not None:
            prev_balance = bal

    if ok_amounts and opening is not None and closing is not None:
        if opening + total != closing:
            warnings.append(
                f"reconciliation: opening {opening} + transactions {total} = {opening + total}, "
                f"but closing is {closing} (off by {closing - opening - total}). "
                "Look for a dropped/duplicated row, swapped debit/credit or a sign error; "
                "if the statement itself is inconsistent, leave the figures as printed")
    elif opening is None or closing is None:
        warnings.append("opening/closing: state both when the statement prints them (enables one-tap verified import)")
    return errors, warnings


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
        errors, warnings = validate(doc)
        n = len(doc.get("transactions", [])) if isinstance(doc, dict) and isinstance(doc.get("transactions"), list) else 0
        print(f"{path}: {n} transactions, {len(errors)} errors, {len(warnings)} warnings")
        for e in errors:
            print(f"  ERROR   {e}")
        for w in warnings:
            print(f"  WARNING {w}")
        failed |= bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
