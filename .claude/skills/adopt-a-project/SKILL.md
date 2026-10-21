---
name: adopt-a-project
description: Make a project agent-friendly with agentify (small root CLAUDE.md, scoped CLAUDE.md files, a map.tsv index with where.py, a check that keeps it true). Use when starting a project, when asked to "agentify" a project, or to restructure a long CLAUDE.md.
---

# Adopt a project with agentify

`agentify` is the command in this repo's `bin/` (put it on your PATH, or call `bin/agentify`). The full steps are in `docs/adopting-a-project.md`; this is the short form.

1. Work in a worktree or branch of the target project. Run `agentify scan <project>`, then read its current `CLAUDE.md` and README. Do not rewrite content you have not read.
2. `agentify init <project> --dry-run`, then `agentify init <project>`. It never overwrites a file. `scan` also lists an existing style guide; point the Rules table at it.
3. A long `CLAUDE.md` (scan shows its biggest sections): split it **losslessly** by heading into `docs/<topic>.md` or `<dir>/CLAUDE.md`, and check that every original non-blank line
   survives. The root stays under 120 lines: what it is, lookup commands, rules, layout, a table of the docs.
4. Fill every TODO: one `map.tsv` row per area (code, the command that proves it, skill, doc, cost), `# stack:` and `# rules:`, and the root sections. In the Rules table, say what backs each
   rule: a script or test, a style-guide section, or `judgment: why, and when an exception is fine`.
5. Set `must_be_mapped` and `skills_not_areas` in `.agentify.json`; add `python3 tests/check_map.py` to the project's own checks.
6. `agentify check <project> --strict` until it passes. Break the map on purpose to see it fail, then restore it.
7. Prove it: `agentify measure` for the startup cost, and what a fresh agent does first on a real task (one `where.py` call, or a repo-wide search?).

## Keeping it true afterwards

- Change an area, test, skill or doc and update its `map.tsv` row in the same commit (the `working-agreements` skill says so).
- `agentify sync` after larger changes: a worklist of dead paths, unmapped directories, TODO rows and rows whose code changed. You write the descriptions; it only finds what is wrong.
- `agentify hook install <project>` once per repo: a pre-commit hook runs `check`, so a commit cannot leave the map wrong.
- Now and then, run the `audit-map` skill: it reads each row against the code, which `check` and `sync` cannot do.
