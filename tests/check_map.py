#!/usr/bin/env python3
"""Is this project agent-friendly, and does it stay that way? No dependencies, <1s.   (agentify archetype, version 1)

map.tsv is the index an agent searches (tools/where.py). It only helps if it cannot rot, so this fails when:
  - a code path, test command, skill or doc named in a row no longer exists
  - an app or source directory, a skill, a docs/ file or a scoped CLAUDE.md is missing from the map or the root CLAUDE.md
  - a backticked path in the root CLAUDE.md does not exist
  - the root CLAUDE.md is over its line budget (it loads in every session, so it is paid for every time)
Warnings (placeholders still to fill, missing lookup pointer, a rule with nothing behind it) fail only with --strict.
Rules: the root CLAUDE.md "## Rules" section holds a table `| Rule | Backed by |`. What backs a rule is a script or test that enforces it, a section
of the project's style guide (`docs/style.md#heading`), or `judgment: <why, and when an exception is fine>`. A guide section that does not exist fails.
Settings live in .agentify.json at the project root; absent keys use the defaults below.
"""
import argparse
import glob
import json
import os
import re
import sys

DEFAULTS = {
    "root_budget": 120,                      # lines in the root CLAUDE.md
    "scoped_budget": 300,                    # lines in any directory-scoped CLAUDE.md
    "must_be_mapped": ["apps/*", "packages/*", "services/*", "src/*", "cmd/*", "lib/*"],   # globs of dirs that need a row
    "skills_not_areas": ["working-agreements", "audit-map"],   # skills that belong to no single area
    "ignore_paths": [],                      # path prefixes whose CLAUDE.md files are templates or fixtures, not scoped docs
}
FIELDS = ["id", "area", "code", "test", "skill", "doc", "cost"]
TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__", "e2e", "integration"}   # never need a row of their own (Maven has src/test next to src/main)
SKILL_DIRS = ["skills", ".claude/skills"]
SKIP = ("/.git/", "/node_modules/", "/.claude/worktrees/", "/target/", "/build/", "/dist/", "/.venv/", "/venv/")
CMD_WORDS = {"npm", "pnpm", "yarn", "npx", "mvn", "./mvnw", "gradle", "./gradlew", "cargo", "go", "pytest", "python", "python3",
             "make", "odin", "node", "bash", "sh", "dotnet", "bundle", "rake", "mix", "uv", "deno", "bun", "just", "tox", "php"}


class Report:
    def __init__(self, strict):
        self.strict, self.failed, self.warned = strict, [], []

    def check(self, name, cond, detail="", warn=False):
        if cond:
            print("  ok    " + name)
            return
        label = "warn  " if warn and not self.strict else "FAIL  "
        print("  " + label + name + (f"   [{detail}]" if detail else ""))
        (self.warned if warn and not self.strict else self.failed).append(name)


def rules_table(root_md):
    """(rule, backed_by) rows of the table under '## Rules' in the root CLAUDE.md, or None when there is no such table."""
    m = re.search(r"^## Rules[^\n]*\n(.*?)(?=^## |\Z)", root_md, re.S | re.M)
    if not m:
        return None
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in m.group(1).split("\n") if l.strip().startswith("|")]
    if not rows or not any("backed by" in c.lower() for c in rows[0]):
        return None
    col = next(i for i, c in enumerate(rows[0]) if "backed by" in c.lower())
    return [(r[0], r[col] if col < len(r) else "") for r in rows[1:] if not set("".join(r)) <= set("-: ")]


def slug(heading):
    return re.sub(r"[^a-z0-9 _-]", "", heading.lower()).strip().replace(" ", "-")


def run(root, strict=False):
    cfg = dict(DEFAULTS)
    cfg_path = os.path.join(root, ".agentify.json")
    if os.path.isfile(cfg_path):
        cfg.update(json.load(open(cfg_path, encoding="utf-8")))
    R = Report(strict)

    def exists(p):
        return bool(glob.glob(os.path.join(root, p)))

    def read(p):
        return open(os.path.join(root, p), encoding="utf-8").read()

    map_path = os.path.join(root, "map.tsv")
    R.check("CLAUDE.md exists at the root", os.path.isfile(os.path.join(root, "CLAUDE.md")))
    if not os.path.isfile(map_path):
        R.check("map.tsv exists", False, "run: agentify init " + root)
        return R
    rs = []
    for n, line in enumerate(read("map.tsv").split("\n"), 1):
        if line and not line.startswith("#") and not line.startswith("id\t"):
            cells = line.split("\t")
            rs.append((n, dict(zip(FIELDS, cells)), len(cells)))
    R.check("map.tsv has rows", len(rs) > 0)
    ids = [r["id"] for _, r, _ in rs]
    R.check("ids are unique", len(ids) == len(set(ids)), str(sorted({i for i in ids if ids.count(i) > 1})[:3]))

    skills_dir = next((d for d in SKILL_DIRS if os.path.isdir(os.path.join(root, d))), SKILL_DIRS[0])
    skill_names = {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(root, skills_dir, "*", "SKILL.md"))}
    bad = []
    for n, r, ncell in rs:
        if ncell != len(FIELDS):
            bad.append(f"line {n}: {ncell} columns")
            continue
        for p in r["code"].split():
            if not exists(p):
                bad.append(f"{r['id']}: code {p}")
        pathy = [t for t in r["test"].split() if "/" in t and not t.startswith(("-", "http"))]
        first = r["test"].split()[0] if r["test"].split() else ""
        if pathy and not exists(pathy[0]):
            bad.append(f"{r['id']}: test {pathy[0]}")
        elif not pathy and first not in CMD_WORDS and not exists(first):
            bad.append(f"{r['id']}: test {first}")
        for s in r["skill"].split():
            if s not in skill_names:
                bad.append(f"{r['id']}: skill {s}")
        if not exists(r["doc"]):
            bad.append(f"{r['id']}: doc {r['doc']}")
    R.check("every path, test, skill and doc in the map exists", not bad, "; ".join(bad[:6]))

    code_cells = " ".join(r["code"] for _, r, _ in rs).split()
    unmapped = []
    for g in cfg["must_be_mapped"]:
        for d in sorted(glob.glob(os.path.join(root, g))):
            rel = os.path.relpath(d, root)
            if os.path.isdir(d) and os.path.basename(d) not in TEST_DIRS and not any(rel == c.rstrip("/") or rel.startswith(c.rstrip("/*") + "/") or c.startswith(rel + "/") for c in code_cells):
                unmapped.append(rel)
    R.check("every app and source directory has a row", not unmapped, str(unmapped))
    used = {s for _, r, _ in rs for s in r["skill"].split()}
    spare = skill_names - used - set(cfg["skills_not_areas"])
    R.check("every skill is used by a row (or is a general one)", not spare, str(sorted(spare)))

    if os.path.isfile(os.path.join(root, "CLAUDE.md")):
        root_md = read("CLAUDE.md")
        nlines = len(root_md.split("\n"))
        R.check(f"root CLAUDE.md is within {cfg['root_budget']} lines", nlines <= cfg["root_budget"], f"{nlines} lines: split it into docs/ or scoped CLAUDE.md files")
        scoped = sorted({os.path.relpath(p, root) for p in glob.glob(os.path.join(root, "**", "CLAUDE.md"), recursive=True)
                         if not any(s in "/" + os.path.relpath(p, root) for s in SKIP)
                         and not any(os.path.relpath(p, root).startswith(i) for i in cfg["ignore_paths"])} - {"CLAUDE.md"})
        big = [s for s in scoped if len(read(s).split("\n")) > cfg["scoped_budget"]]
        R.check(f"scoped CLAUDE.md files are within {cfg['scoped_budget']} lines", not big, str(big))
        docs = sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, "docs", "*.md")))
        missing = [d for d in docs + scoped if d not in root_md]
        R.check("the root CLAUDE.md lists every docs/ file and scoped CLAUDE.md", not missing, str(missing))
        refs = set(re.findall(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,5})`", root_md))
        gone = sorted(r for r in refs if not r.startswith("..") and not exists(r))
        R.check("paths named in the root CLAUDE.md exist", not gone, str(gone))
        table = rules_table(root_md)
        R.check("the rules in the root CLAUDE.md say what backs each one (a table with a 'Backed by' column)", table is not None or "## Rules" not in root_md,
                "make '## Rules' a table: | Rule | Backed by |", warn=True)
        if table is not None:
            bare = [r[:40] for r, b in table if not b or b.lower().strip("`. ") in ("none", "-", "n/a") or "TODO" in b]
            R.check("every rule is backed by an enforcer, a style-guide section or a stated judgment", not bare, str(bare[:4]), warn=True)
            dead = []
            for r, b in table:
                for path, _, anchor in re.findall(r"`([A-Za-z0-9_./-]+\.md)(#([A-Za-z0-9_-]+))?`", b):
                    if not exists(path):
                        dead.append(f"{path}")
                    elif anchor and anchor not in {slug(h) for h in re.findall(r"^#+\s+(.*)$", read(path), re.M)}:
                        dead.append(f"{path}#{anchor}")
            R.check("every style-guide section a rule points at exists", not dead, str(dead))
        R.check("the root CLAUDE.md points at the lookup (tools/where.py)", "where.py" in root_md, "add the 'Find things fast' block", warn=True)
        R.check("the root CLAUDE.md has no TODO placeholders", "TODO" not in root_md, "fill the sections marked TODO", warn=True)
    comments = [l for l in read("map.tsv").split("\n") if l.startswith("# ")]
    stack = next((l for l in comments if l.startswith("# stack:")), "")
    rules = next((l for l in comments if l.startswith("# rules:")), "")
    R.check("map.tsv names the stack and the rules (no TODO)", bool(stack) and bool(rules) and "TODO" not in stack + rules, "fill the # stack: and # rules: lines", warn=True)
    R.check("no row still says TODO", not any("TODO" in " ".join(r.values()) for _, r, _ in rs), "describe each area", warn=True)
    R.check("tools/where.py is installed", os.path.isfile(os.path.join(root, "tools", "where.py")), "agentify init copies it", warn=True)
    return R


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--strict", action="store_true", help="warnings fail too")
    a = ap.parse_args()
    R = run(os.path.abspath(a.root), a.strict)
    print(("FAILED: %d" % len(R.failed)) if R.failed else ("all passed" + (f" ({len(R.warned)} warnings)" if R.warned else "")))
    sys.exit(1 if R.failed else 0)


if __name__ == "__main__":
    main()
