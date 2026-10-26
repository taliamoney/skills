#!/usr/bin/env python3
"""Build a zip of Talia statement files and print the path and a talia:// link.

Usage:
  make_bundle.py --out BUNDLE.zip --file NUMBER=PATH [--file NUMBER=PATH ...]

NUMBER is the account number as the user entered it in Talia (digits only, at least 4).
Each entry is named "<NUMBER>-<file name>" so Talia can match it to its account.
Stdlib only. Exit 1 if anything would make Talia skip or reject the bundle.
"""
import argparse
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

MAX_FILES = 200
MAX_UNPACKED = 100 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
FIXED_TIME = (1980, 1, 1, 0, 0, 0)  # deterministic zips: same input, same bytes
SKILLS = Path(__file__).resolve().parents[2]


def load_validator(skill, module):
    path = SKILLS / skill / "scripts" / f"{module}.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def deep_check(doc, bank, invest):
    """(errors, warnings, validated) from the sibling skill's validator, if present."""
    t = doc.get("account", {}).get("type") if isinstance(doc, dict) else None
    if t in ("banking", "credit"):
        if bank is None:
            return [], [], False
        e, w = bank.validate(doc)
        return e, w, True
    if t in ("investment", "crypto"):
        if invest is None:
            return [], [], False
        v = invest.validate(doc)
        return v.errors, v.warnings, True
    return ["account.type: expected banking, credit, investment or crypto"], [], True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="the zip to write")
    ap.add_argument("--file", action="append", default=[], metavar="NUMBER=PATH", required=True)
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()
    bank = load_validator("transaction-import", "validate_statement")
    invest = load_validator("investment-import", "validate_investment")
    errors, warnings, entries, names = [], [], [], set()
    skipped_validation = 0
    total = 0

    for spec in args.file:
        number, sep, raw = spec.partition("=")
        src = Path(raw).expanduser()
        if not sep or not raw:
            errors.append(f"{spec!r}: expected NUMBER=PATH")
            continue
        if not re.fullmatch(r"\d{4,}", number):
            errors.append(f"{spec}: the account number must be digits only, at least 4 (got {number!r})")
            continue
        if not src.is_file():
            errors.append(f"{src}: no such file")
            continue
        data = src.read_bytes()
        if len(data) > MAX_FILE:
            errors.append(f"{src}: {len(data)} bytes is over the 10 MB limit per file")
            continue
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            errors.append(f"{src}: not UTF-8 JSON: {e}")
            continue
        if not isinstance(doc, dict) or doc.get("format") != "talia.statement/1":
            errors.append(f'{src}: format must be "talia.statement/1"')
            continue
        mask = doc.get("account", {}).get("mask")
        if isinstance(mask, str) and not number.endswith(mask) and not mask.endswith(number):
            errors.append(f"{src}: account.mask {mask!r} does not agree with number {number} (Talia would skip it)")
        e, w, validated = deep_check(doc, bank, invest)
        skipped_validation += 0 if validated else 1
        errors += [f"{src}: {m}" for m in e]
        warnings += [f"{src}: {m}" for m in w]

        base = src.name if src.name.lower().endswith(".json") else src.name + ".json"
        name = base if base.startswith(number) and re.match(rf"^{number}(?:$|[-_ .])", base) else f"{number}-{base}"
        if name in names:
            errors.append(f"{src}: entry name {name!r} is already used; rename the file")
            continue
        names.add(name)
        total += len(data)
        entries.append((name, data))

    if len(entries) > MAX_FILES:
        errors.append(f"{len(entries)} files is over the limit of {MAX_FILES}; split into several bundles")
    if total > MAX_UNPACKED:
        errors.append(f"{total} bytes unpacked is over the 100 MB limit; split into several bundles")

    for w in warnings:
        print(f"WARNING {w}", file=sys.stderr)
    if skipped_validation:
        print(f"NOTE    {skipped_validation} file(s) not deeply validated: the matching import skill's validator "
              "was not found next to this skill. Validate them first.", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR   {e}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)

    posix = out.as_posix()
    link = "talia://import?path=" + quote(posix, safe="/:")
    print(f"Wrote {out} ({len(entries)} files)")
    for name, _ in sorted(entries):
        print(f"  {name}")
    print()
    print(f"Link:        {link}")
    print(f'macOS:       open "{link}"')
    print(f'             open -a Talia "{out}"')
    print(f'Windows:     start "" "{link}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
