# talia-skills

Skills for agents working with the Talia app. Each skill is a directory under
`skills/` with a `SKILL.md` (frontmatter `name` + `description`) and optional
`references/` and `scripts/`.

| Skill | Use it to |
|---|---|
| [`transaction-import`](skills/transaction-import/SKILL.md) | Turn a bank/card statement (PDF, CSV) into a `talia.statement/1` JSON file Talia can import |

Skills are self-contained: they must not reference Talia's source code or internal docs,
which agents using this repository can't see. Each skill vendors the
schemas it needs (e.g. `skills/transaction-import/schemas/`).
