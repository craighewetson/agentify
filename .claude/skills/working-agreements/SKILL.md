---
name: working-agreements
description: The standing rules for any agent working in this repo (what you may not do, how to work). Read at the start of any session.
---

# Working agreements

## Never
- TODO: what an agent must not do here.

## Always
- Work in your own git worktree on a `workset/*` branch; add named paths, never `git add -A`.
- Keep the index true. When you add, move or delete an app, source directory, test, skill or doc, update its row in `map.tsv` in the
  same commit (and the root `CLAUDE.md` table for a doc or scoped `CLAUDE.md`). Run `python3 tests/check_map.py --strict`; it must pass.
  After a larger change, run `agentify sync` (if installed): it lists dead paths, directories with no row, rows still saying TODO and rows
  whose code changed since the map was last committed. Read each flagged row, fix its description, test and skill, then commit the map.
  You write the descriptions; the tool only finds what is wrong. Never leave a TODO in a row you added.
- Failing test first for a defect; say plainly what you did not verify.
