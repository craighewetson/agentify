#!/usr/bin/env python3
"""Look up the project map without reading prose. About 100 tokens per answer.

  tools/where.py                  one line per area (id: what it is)
  tools/where.py review page      areas whose row contains every word (case-insensitive)
  tools/where.py --stack          stack and standing rules (the # lines of map.tsv)
  tools/where.py --skills         every skill: name and when to use it (read from skills/ or .claude/skills/)
  tools/where.py --json words     the matching rows as JSON
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ["id", "area", "code", "test", "skill", "doc", "cost"]


def rows():
    out = []
    for line in open(os.path.join(ROOT, "map.tsv"), encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or line.startswith("id\t"):
            continue
        out.append(dict(zip(FIELDS, line.split("\t"))))
    return out


def comments():
    return [l[1:].strip() for l in open(os.path.join(ROOT, "map.tsv"), encoding="utf-8")
            if l.startswith("# ") and ":" in l[:12]]


def skills():
    found = glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(ROOT, ".claude", "skills", "*", "SKILL.md"))
    for p in sorted(found):
        head = open(p, encoding="utf-8").read().split("---")[1]
        name = re.search(r"^name:\s*(.+)$", head, re.M).group(1).strip()
        desc = re.search(r"^description:\s*(.+)$", head, re.M).group(1).strip()
        yield name, desc


def show(r):
    print(f"{r['id']}: {r['area']}")
    for k in ("code", "test", "skill", "doc", "cost"):
        print(f"  {k:<5} {r[k]}")


def main(argv):
    if "--stack" in argv:
        print("\n".join(l for l in comments() if l.startswith(("stack", "rules"))))
        return 0
    if "--skills" in argv:
        for n, d in skills():
            print(f"{n}: {d[:110]}")
        return 0
    as_json = "--json" in argv
    words = [a.lower() for a in argv if not a.startswith("--")]
    rs = rows()
    if not words:
        for r in rs:
            print(f"{r['id']}: {r['area']}")
        return 0
    hit = [r for r in rs if all(w in " ".join(r.values()).lower() for w in words)]
    if as_json:
        print(json.dumps(hit, indent=1))
    else:
        for r in hit:
            show(r)
    if not hit:
        print("no area matches; run with no arguments for the list")
    return 0 if hit else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
