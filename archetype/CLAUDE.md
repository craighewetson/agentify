# {{name}}

TODO: two or three sentences: what this product is and who uses it.

## Find things fast (do this before reading anything long)

```bash
tools/where.py                 # one line per area; tools/where.py <words> -> code, test, skill, doc, cost
tools/where.py --stack         # tech stack and standing rules      tools/where.py --skills  # every skill and when to use it
```

`map.tsv` is the index (one row per area); `tests/check_map.py` fails if anything in it stops existing, or if an app, doc or
skill is missing from it. Skill descriptions load on their own. Directory-scoped `CLAUDE.md` files load when you work there.

## Rules that apply everywhere

What backs a rule: a script or test that enforces it, a section of the project's style guide (`docs/style.md#section`), or `judgment: why, and when an exception is fine`.

| Rule | Backed by |
|---|---|
| TODO: the 4 to 6 rules an agent must not get wrong here. | TODO: enforcer, style-guide section or judgment |
| Keep the index true: add, move or delete an area, test, skill or doc and update its `map.tsv` row in the same commit. | `tests/check_map.py`, the pre-commit hook (`agentify hook install`), `skills/working-agreements` |
| This file stays under 120 lines; new detail goes in a scoped `CLAUDE.md` or `docs/`. | `tests/check_map.py` |

## Layout

{{layout}}

## Reference docs (open the one that fits)

| Topic | File |
|---|---|
| Working rules | `.claude/skills/working-agreements/SKILL.md` |
| Style: what a linter cannot enforce | `{{style_guide}}` |
