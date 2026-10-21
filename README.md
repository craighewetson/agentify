# agentify

Make a software project quick for a coding agent (Claude Code and similar) to get around in, and keep it that way.
Like a Maven archetype plus a linter: `init` lays down the structure, `check` proves it is still true.

```bash
bin/agentify scan  ~/projects/foo       # stack, areas, test command, how big its CLAUDE.md is
bin/agentify init  ~/projects/foo       # add the missing files (never overwrites)
bin/agentify check ~/projects/foo       # lint; add --strict to fail on TODO placeholders
bin/agentify upgrade ~/projects/foo     # refresh the project's copies of where.py and check_map.py
bin/agentify sync ~/projects/foo        # worklist: dead, missing, undescribed and stale map rows (--write appends stub rows)
bin/agentify hook install ~/projects/foo # git pre-commit hook that runs check, so a commit cannot leave the map wrong
bin/agentify measure ~/projects/foo --against <old-ref>   # tokens loaded at session start, and the saving
bin/agentify bench ~/projects/foo --tasks bench/foo.json --a <old-ref> --b <new-ref> --dry-run   # A/B with real sessions (costs money)
```

What a project gets: a tiny root `CLAUDE.md`, scoped `CLAUDE.md` files for detail, `map.tsv` + `tools/where.py` (a searchable index: area,
code, test, skill, doc, cost), a `working-agreements` skill, and `tests/check_map.py`, which fails when the index stops being true or the
always-loaded file grows past its budget. Python 3.9+, standard library only. Tests: `python3 -m unittest discover tests`.

Design and the adoption steps: `docs/design.md`, `docs/adopting-a-project.md`. On one real project the always-loaded root file went from about 22k to about 1k tokens
(`agentify measure` shows this without a model; `docs/design.md` says what the benchmarks did and did not show).

To let Claude Code drive an adoption, copy `.claude/skills/adopt-a-project` (and `audit-map`, for checking the map against the code) into `~/.claude/skills/`.

MIT licensed: see `LICENSE`.
