# agentify

A small command-line tool (Python standard library only) that makes any software project quick for a coding agent to get around
in: a tiny root `CLAUDE.md`, a searchable index (`map.tsv` + `tools/where.py`), and a check that keeps the index true. Think of it
as the Maven archetype plus the linter for that layout. It is applied to itself: this repo passes `bin/agentify check .`.

## Find things fast

```bash
tools/where.py                 # one line per area; tools/where.py <words> -> code, test, skill, doc, cost
tools/where.py --stack         # stack and standing rules      tools/where.py --skills  # skills
```

`map.tsv` is the index. `tests/check_map.py` is this project's own copy of the shared check; the master is `archetype/tests/check_map.py`.

## Rules

What backs a rule: a script or test that enforces it, a section of the style guide, or `judgment: why, and when an exception is fine`.

| Rule | Backed by |
|---|---|
| `archetype/` is what `init` copies into other projects. Edit the master there, never a project's copy; `agentify upgrade` refreshes copies. | `tests/test_agentify.py` (`SelfTest`) |
| Standard library only, Python 3.9+. | judgment: nothing to install is the point; a dependency needs a one-line reason in the commit |
| `init` never overwrites an existing file. | `tests/test_agentify.py` (`InitTests`) |
| Only `bench` starts model sessions (they cost money): never run it without `--dry-run` first and an explicit go-ahead. | `tests/fake_claude.py` for tests; judgment for real runs: ask first |
| Every rule in `check_map.py` has a test that breaks the layout on purpose and expects the failure. | `tests/mutate_checks.py` (about 2 minutes; run it before a release) |
| Root `CLAUDE.md` stays under 120 lines. | `tests/check_map.py` (`bin/agentify check .`) |

## Layout

- `bin/agentify` the command; `src/agentify/` `scan.py` (read a project), `scaffold.py` (init, upgrade), `sync.py` + `hook.py` (keep the map true as the project changes), `measure.py` (startup tokens), `bench.py` (A/B with real sessions), `cli.py`.
- `archetype/` the files a project receives: `tools/where.py`, `tests/check_map.py`, a `CLAUDE.md` and `map.tsv` template, the `working-agreements` skill.
- `bench/` task files (questions with expected answers) and `bench/results/` (saved runs).
- `tests/test_agentify.py` unit tests (`python3 -m unittest discover tests`); `docs/` the design and how to adopt a project.

## Reference docs

| Topic | File |
|---|---|
| Why it is shaped this way, the layers, what the check enforces | `docs/design.md` |
| Adopting an existing project step by step (including splitting a long CLAUDE.md) | `docs/adopting-a-project.md` |
