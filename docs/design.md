# Design

## The problem

A coding agent starts every session cold. If the project's instructions are one long file, the agent pays for all of it every time
(one real project's was 1,234 lines, about 22k tokens) and still cannot answer "which test covers this page?" without searching. Prose
also rots: nothing notices when a path in it stops existing.

## The four layers (cheapest first)

1. **Always loaded, tiny.** The root `CLAUDE.md`, under 120 lines: what the product is, how to look things up, the standing rules, a table of the docs.
2. **Scoped, loaded when you work there.** A `CLAUDE.md` in a directory is read only when work happens in that directory, so detail sits next to the code.
3. **Looked up, not read.** `map.tsv`: one row per area with its code, the command that proves it, the skill, the doc and the cost (GPU, network, money).
   `tools/where.py <words>` prints the matching rows, about 100 tokens an answer, in the same shape every time.
4. **On demand.** Skills (`.claude/skills/<name>/SKILL.md`: the description is always visible, the body loads when it fits) and `docs/*.md`.

## What the check enforces (`tests/check_map.py`)

Failures: a path, test command, skill or doc named in the map that does not exist; an app/source directory with no row; a skill no row
uses (unless listed as general); a `docs/*.md` or scoped `CLAUDE.md` the root does not list; a backticked path in the root that does not
exist; the root over its line budget; a missing `map.tsv`. Warnings (failures with `--strict`): TODO placeholders, no lookup pointer, no `where.py`.

Rules get the same treatment, softly. The root `CLAUDE.md` keeps its rules in a table `| Rule | Backed by |`, where "backed by" is a script or test that
enforces the rule, a section of the project's own style guide (`docs/style.md#dependencies`), or `judgment: why, and when an exception is fine`. A rule with
nothing behind it is a warning, never a failure, because many rules cannot be checked by a machine and the right ones differ by language and project (a Java
Spring Boot service wants few dependencies and prompt fixes for known vulnerabilities; this tool wants the standard library only). A pointer to a guide section
that does not exist is a failure, like any dead path. Nothing in the tool knows a language: the style guide is the project's.

It checks that the index is **true**, not that it is **good**: it cannot tell that a description has become wrong. That judgement stays with the agent that changes the area.

## Decisions

- **Each project carries its own copy** of `where.py` and `check_map.py`, so it is self-contained: an agent needs no installed tool and the check
  runs in the project's own test battery. `agentify check` runs the bundled master, and warns when the copy differs; `agentify upgrade` refreshes it.
- **One file, no dependencies.** Standard library only, so it runs anywhere Python 3.9+ does.
- **Settings in `.agentify.json`**: `root_budget`, `scoped_budget`, `must_be_mapped` (globs of directories that need a row), `skills_not_areas`, `ignore_paths`.
- **`init` never overwrites.** It writes only what is missing, so it is safe on a project that has half of this already.
- **The mechanical part is a tool; the judgement is a skill.** Scanning, scaffolding and linting are code. Writing area descriptions and splitting a long
  `CLAUDE.md` losslessly is done by an agent following `docs/adopting-a-project.md`, with `agentify check` as the finish line.
- **Test commands** in the map may be a runner (`npm test`, `mvn test`, `cargo test`...) or a path; a path must exist.

## Measuring whether it worked

Two tiers, because "fewer tokens at the start" and "finds things faster" are different claims.

- **`agentify measure <project> [--against REF] [--budget N]`** (free, deterministic, no model). Lists every file that loads at the start of a session
  (root `CLAUDE.md` and its `@imports`, ancestor and user `CLAUDE.md`, the project's `MEMORY.md`, skill names and descriptions) with tokens, and the
  saving against a git ref. Tokens are estimated from bytes at 2.4 bytes per token, calibrated on two real `/context` readings of one project
  (101 KB read as 40.7k, 16.7 KB read as 7.2k). `--budget` makes it a gate. It proves the always-loaded cost fell; it cannot prove the agent got faster.
- **`agentify bench`** (costs real money). Fresh headless `claude -p` sessions answer fixed questions in checkout A and checkout B, read-only, each capped.
  It records Claude's own token usage and dollar cost, turns, tool calls (including whether `where.py` was used and how many searches), and grades each
  answer by regex. A and B run alternately so neither always runs warm. The verdict is conservative: fewer correct answers is "WORSE" whatever the cost; "BETTER" needs B cheaper in every paired run (the same task in the same repeat)
  and a sign test with p < 0.05, which takes at least 5 pairs, otherwise it is "LEANS BETTER" or "NOT BETTER" with the count and p printed. Both arms are checked out beside the project, so the ancestors' `CLAUDE.md` files are the same.
  Always `--dry-run` first, then a small `--runs`, then read the cost before a large run.

A task file is JSON: `tasks` of `{id, prompt, must: [regex], must_not: [regex]}`; see `bench/audit-map.json`. Write questions whose answers are in both layouts, so a wrong answer
means the agent could not find it. Results go to `bench/results/`; run the benchmark on a pinned "before" commit against the adopted layout.

What the benchmarks of real projects showed (two projects, 3 repeats, 8 to 9 questions each; the project names are left out):

- **Correctness:** one project 24 of 24 in both layouts. The other 27 of 27 before and 24 of 27 after, so the verdict was "WORSE": the new layout lost some answers.
- **Cost:** no reliable saving. One project +6% (cheaper in 10 of 24 paired runs); the other -41% in total, but that was one repeat (-57%, +10%, +18% per repeat).
- **What does hold:** the always-loaded cost fell a lot (`agentify measure`), and the agent used `where.py` in about half the runs. Treat "fewer tokens at the start" as proven and "cheaper and
  faster to answer" as not shown.

## Keeping it true as the project changes

Three layers, because a map rots the moment code moves and nobody notices:

1. **A standing rule** (archetype `working-agreements` skill and root `CLAUDE.md`): whoever adds, moves or deletes an area, test, skill or doc
   updates its `map.tsv` row in the same commit. The agent that made the change is the one who knows what it means, so it writes the words.
2. **`agentify sync [--write] [--json]`** is a worklist, never an editor. It lists: rows whose code, doc, skill or test no longer exists;
   directories with no row (with a stub row, which `--write` appends); rows still saying TODO; skills no row uses; docs not in the root file; and
   *stale* rows, where the code changed (commits since `map.tsv` was last committed, or uncommitted edits) while the map did not. Touching `map.tsv`
   marks every row reviewed, so this is a prompt to read, not proof the words are right. Exit 1 while the list is non-empty.
3. **`agentify hook install`** adds a git pre-commit hook that runs `check` (not `--strict`, so a TODO row can be committed as work in progress,
   but a dead path or a missing row cannot). It never overwrites a hook that is not its own and `git commit --no-verify` skips it.

Not done on purpose: no command rewrites descriptions. A generated description is a restatement of the code, which the agent can read anyway;
the value of a row is the judgement ("use this, not that"), and only an agent that read the change can supply it.

## The audit skill, and what the evidence says

`check` and `sync` cannot see a row that is wrong while every path exists. The `audit-map` skill (archetype, copied by `init`) is the procedure for reading each row
against its code: area, test, skill and doc, cost, with a file and line as evidence for every "wrong" and `unverified` when there is none.

Measured on a made-up project (`bench/fixtures/make_audit_fixture.py`; both arms pass `check --strict` and `sync`), fresh sessions with and without the skill, 3 repeats each:

- **Easy** (10 rows, 4 wrong): both arms found all four every time. A plain "audit this map" prompt is enough on a small map; the skill showed no gain (`bench/results/audit-map-easy.json`).
- **Hard** (18 rows, 6 wrong, 12 right including bait that only looks wrong): neither arm raised a false alarm. Without the skill, 4 of 6 wrong rows were found in every run; with it, 5, 6 and 5.
  The difference was mostly one row, a doc pointer whose document is about something else: found in 3 of 3 runs with the skill, 0 of 3 without. A wrong dedupe key (a pure reading of code) was missed by both
  in 5 of 6 runs (`bench/results/audit-map-hard.json`).

Read this as early, not settled. Three repeats, one model, one made-up project. The skill's checklist names the same kinds of claim the fixture seeds, so it partly teaches to the test; whether real maps drift in those
ways is the open question. The benchmark sessions cannot spawn subagents, so the per-row fan-out the skill describes is untested.

## Reading a bench result (before you trust or quote a number)

These come from pstack's "explain the number" and its benchmark checklist, applied to what `bench` can actually check.

- **How many pairs, and is it more than luck?** The report prints the paired count and the sign-test p. Three pairs all in B's favour is p = 0.125: a lean, not a result.
- **Is the total moved by one repeat?** The report prints B's cost change per repeat. A total of -41% made of -57%, +10%, +18% is one lucky repeat (this happened in the first full run on one of the projects).
- **Is the cache the same for both?** The report prints the share of tokens read from the cache for each arm and flags a gap over 0.2: cost then reflects warmth, not layout. A and B alternate order to limit this, but only the share shows whether it worked.
- **Did it fail for the reason you think?** Each wrong answer records which pattern it missed or hit (`why`), and the saved answer is 1500 characters, enough to read the line that was graded.
- **Is the question real?** A question both layouts answer perfectly (the easy audit fixture) cannot tell them apart; a tie there is a property of the task, not of the layouts.
- **Is it the same thing you will do?** Sessions deny subagents and edits, so a result about reading says nothing about changing code.
