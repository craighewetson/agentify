---
name: audit-map
description: Check that map.tsv still tells the truth, row by row, against the code. Use when asked to audit, verify or review the map, after a large change, or before relying on it. Finds descriptions, test pointers, doc pointers and costs that are wrong even though every path exists.
---

# Audit the map

`tests/check_map.py` proves the paths in `map.tsv` exist. It cannot tell that a row has become wrong: the code does something else now, the named test
covers a different area, the doc is about something else, or the code spends money or time the cost column does not admit. You can, by reading.

## Edit scope

Edit `map.tsv` rows only. Never change code, tests or docs in this pass: a mismatch is either a stale row (fix the row) or a bug in the code (report it,
do not paper over it in the map). Do not rewrite a row that is right; a row's value is the judgement ("use this, not that"), not a restatement of the code.

## Pass

1. Run `agentify sync` if it is installed, or `python3 tests/check_map.py --strict`. Fix what they list first; the rest of this pass is for what they cannot see.
2. For every row, open its `code` files and read enough to judge four claims. Do not trust the row to tell you where to look.
   - **Area**: does the description say what this code does now, including what it no longer does?
   - **Test**: does the test command or file exercise this code? Open it. A test that exists but covers a neighbour is wrong.
   - **Skill and doc**: is that skill or doc about this area?
   - **Cost**: does the code use GPU, network, a paid service, a long run or a destructive action that the cost column does not say, or the reverse?
3. A verdict of wrong needs evidence: the file and line that contradicts the row. If you cannot find evidence either way, the verdict is `unverified`,
   not wrong. Do not flag a row because you would have worded it differently.
4. With many rows and subagents available, give each row (or a few related rows) to one read-only subagent and ask for `id: ok | wrong: <claim> | evidence file:line |
   corrected text`. Then check each `wrong` yourself against the cited line before you edit anything.
5. Fix the wrong rows with the fewest words that make them true. Run `python3 tests/check_map.py --strict`.

## Report

One of: **clean** (every row read, nothing wrong), **changed** (list each row id, what was wrong, the evidence), or **blocked** (say what stopped you).
List `unverified` rows separately; they are not failures.
