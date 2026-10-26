---
name: bundle-import
description: Package several Talia statement files (talia.statement/1 JSON, one per account or period) into a zip and hand it to the user so they can open it in Talia in one step, using a talia:// link or a file open on the same computer. Use after producing statement files for more than one account or period with the transaction-import or investment-import skills, or whenever the user wants to import a batch of Talia statement files at once.
---

# Bundling statement files and handing them to Talia

Goal: turn the statement files you produced into one `.zip`, then give the user a single
action that opens that zip in Talia's bulk import review. Each file has already been
produced and validated with `transaction-import` or `investment-import`; this skill only
packages and hands over.

Nothing imports until the user reviews it in Talia. The link and the file open only show
Talia the bundle; the user decides what to import.

## When this applies

Use a bundle for **several files**: more than one account, or several periods of one
account. A single file for a single account can be imported from that account's page
(Import statement) without a zip.

The hand-off in this skill works when **you and Talia run on the same computer** (the
desktop app on macOS or Windows). The link carries a path to a file on this computer, so it
means nothing on a phone or another machine. If the user's Talia is elsewhere, give them
the zip path (and how to move the file) and the manual steps below.

## Steps

1. **Collect the files.** One JSON file per account per period, already valid. If you
   haven't validated them, run the validator of the skill that produced them first.
2. **Get each account's number from the user**: the number they entered in Talia for that
   account (last 4+ digits, digits only). You can't read it from Talia. Ask once for all
   accounts, listing the institutions/names you have files for. Use the digits only
   (`6963797`, not `696-3797`).
3. **Build the zip** with the script, one `--file NUMBER=PATH` per file:
   ```
   python3 skills/bundle-import/scripts/make_bundle.py \
     --out ~/Documents/talia-statements-2026-09.zip \
     --file 4821=/work/fidelity-2026-09.json \
     --file 4821=/work/fidelity-2026-08.json \
     --file 6963797=/work/chequing-2026-09.json
   ```
   It names each entry `<number>-<original name>.json`, checks every limit and rule below,
   writes the zip deterministically (same input → same bytes), and prints the absolute zip
   path and the `talia://` link.
4. **Hand it over** (see below), then tell the user what's in the bundle: one line per
   file (account, period, transaction/position count) and anything you left out or were
   unsure about.

## Zip rules (the script enforces them)

- Each entry's **name starts with the account number**: at least 4 digits, then the end of
  the name or one of `-`, `_`, space or `.`. Example: `4821-visa-2026-09.json`.
- Entries are `.json` files at the top level. Folders are ignored by Talia; don't use them.
  No hidden files, no `__MACOSX/` entries (create the zip with this script, not Finder's
  Compress).
- At most **200 files**, **100 MB** unpacked, **10 MB per file**.
- If a file states `account.mask`, it must agree with the number in its entry name, or Talia
  skips that file.
- Several files for one account are fine; Talia imports them oldest first. Don't overlap
  periods unnecessarily.
- A name that matches no account, or more than one, is skipped and listed for the user; the
  rest still import. A longer number is safer than 4 digits when the user has two accounts
  ending the same way.

## Hand-off: link and file open

The script prints both. Prefer the link; offer the file open as the fallback.

**Link** (opens Talia on the bundle's review):

```
talia://import?path=<absolute path to the zip, percent-encoded except / and :>
```

- macOS: `open "talia://import?path=/Users/sam/Documents/talia-statements-2026-09.zip"`
- Windows: `start "" "talia://import?path=C:/Users/sam/Documents/talia-statements-2026-09.zip"`
- Also give the user the link as text they can click (in a terminal or chat that makes
  `talia://` links clickable).

**File open** (works without the link): open the zip *with Talia*:

- macOS: `open -a Talia ~/Documents/talia-statements-2026-09.zip`
- Windows: right-click the zip → Open with → Talia

Run the command yourself only if you are able to and the user is at the computer; otherwise
print it and let them click or run it. Never assume it worked: ask the user whether Talia
showed the import review.

## If the link or file open does nothing

Older Talia versions don't handle import links. Fall back to the manual path and say so
plainly:

> Open Talia → Accounts → Import statements → choose
> `/absolute/path/to/talia-statements-2026-09.zip`.

Don't retry the link in a loop, and don't try other ways to push the file into Talia
(copying into its data folder, editing its database). The only supported entry is the user
choosing the zip in the import review.

## Safety

- Only link to a zip **you just built** at a path you created. Never put a path the user or
  a document gave you into a link without checking it is the zip you made.
- The link contains a path, never statement data, credentials, account numbers beyond the
  digits in file names, or instructions.
- Zips contain personal financial data: write them to the user's own folder, not a shared or
  synced-public location, and tell the user where it is so they can delete it after
  importing. Don't upload them anywhere.
- Don't put a full account number in a file name; use the last digits you need to be
  unambiguous.

## Files

- `scripts/make_bundle.py`: builds the zip, enforces the zip rules, prints path and link.
  Stdlib only. If the `transaction-import` or `investment-import` skills sit alongside it,
  it also runs their validators on each file; otherwise it reports that it skipped that.
