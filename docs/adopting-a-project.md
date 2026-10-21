# Adopting a project

```bash
agentify scan  ~/projects/foo       # what is it: stack, areas, test command, CLAUDE.md size, biggest sections
agentify init  ~/projects/foo       # add what is missing: CLAUDE.md, map.tsv (drafted from the scan), where.py, check_map.py, a skill
agentify check ~/projects/foo       # lint; --strict also fails on TODO placeholders
agentify sync ~/projects/foo        # whenever code changed: what in the map needs an agent's attention
agentify hook install ~/projects/foo # once: a commit that breaks the map is blocked
agentify upgrade ~/projects/foo     # later: refresh the project's where.py and check_map.py from the master
```

Work in a worktree or branch of the project, not its main checkout.

## Steps (for an agent to follow)

1. `agentify scan`. Read the project's existing `CLAUDE.md` / `README.md`. Do not rewrite content you have not read.
2. `agentify init --dry-run`, then `agentify init`. It never overwrites; an existing `CLAUDE.md` is left alone.
   `scan` also lists any style guide the project already has (`CONTRIBUTING.md`, `docs/*style*.md`). `init` makes an empty `docs/style.md` only when there is
   none and it is writing the root `CLAUDE.md` itself. In an existing project, point the Rules table at the guide you found (`CONTRIBUTING.md#testing`);
   if there is none, create `docs/style.md` only when a rule needs it, and list it in the root.
3. **A long `CLAUDE.md`:** `scan` lists its biggest sections. Slice by heading, losslessly, into `docs/<topic>.md` (reference) or `<dir>/CLAUDE.md`
   (only relevant when working there). Check that every original non-blank line still exists somewhere. Keep the root under the budget:
   what it is, lookup commands, rules, layout, a table of the docs. Compare a fresh session's `/context` before and after.
4. Fill `map.tsv`: describe each area, name the command that proves it works, the skill, the doc, the cost. Fill `# stack:` and `# rules:`.
5. Set `must_be_mapped`, and `skills_not_areas` for general skills, in `.agentify.json`.
6. `agentify check --strict` until it passes. Then break the map on purpose (rename a path, delete a row) and see it fail.
7. Add `python3 tests/check_map.py` to the project's own checks so it runs with the rest.
8. Add a skill only when a task needed more than a paragraph of "how we do this here" twice. A skill's description says when to use it.

## Proving it worked

Start a fresh session in the project, run `/context`, and compare the memory-files line with the old figure. Then give it a real task and look at
what it did first: one `where.py` call and a scoped `CLAUDE.md`, or a repo-wide search? Rows the agent had to rediscover by `curl` or `grep` are
missing rows or missing gotcha lines: add them.
