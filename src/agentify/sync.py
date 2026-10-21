"""agentify sync: what in map.tsv needs an agent's attention, as a worklist. Mechanical findings only; descriptions stay the agent's job."""
import glob
import importlib.util
import json
import os
import subprocess

from . import scaffold
from . import scan as scanmod


def _check_map():
    spec = importlib.util.spec_from_file_location("agentify_check_map", os.path.join(scaffold.ARCHETYPE, "tests", "check_map.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _git(root, *args):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def read_rows(root, fields):
    p = os.path.join(root, "map.tsv")
    rows = []
    for line in open(p, encoding="utf-8").read().split("\n"):
        if line and not line.startswith("#") and not line.startswith("id\t"):
            c = line.split("\t")
            if len(c) == len(fields):
                rows.append(dict(zip(fields, c)))
    return rows


def stale_rows(root, rows):
    """Rows whose code changed (committed after map.tsv was last committed, or edited now) while map.tsv stayed as it was."""
    if _git(root, "rev-parse", "--is-inside-work-tree") != "true":
        return []
    if _git(root, "status", "--porcelain", "--", "map.tsv"):
        return []                                    # the map is being edited right now: it is being reviewed
    base = _git(root, "log", "-1", "--format=%H", "--", "map.tsv")
    if not base:
        return []
    out = []
    for r in rows:
        paths = [p for p in r["code"].split() if p not in (".", "./") and glob.glob(os.path.join(root, p))]
        if not paths:
            continue
        log = _git(root, "log", "--format=%h %s", f"{base}..HEAD", "--", *paths) or ""
        commits = [l for l in log.split("\n") if l]
        dirty = bool(_git(root, "status", "--porcelain", "--", *paths))
        if commits or dirty:
            out.append({"id": r["id"], "code": r["code"], "commits": len(commits), "recent": commits[:3], "uncommitted": dirty})
    return out


def worklist(root):
    root = os.path.abspath(root)
    cm = _check_map()
    cfg = dict(cm.DEFAULTS)
    if os.path.isfile(os.path.join(root, ".agentify.json")):
        cfg.update(json.load(open(os.path.join(root, ".agentify.json"), encoding="utf-8")))
    rows = read_rows(root, cm.FIELDS)

    def exists(p):
        return bool(glob.glob(os.path.join(root, p)))

    skills_dir = next((d for d in cm.SKILL_DIRS if os.path.isdir(os.path.join(root, d))), cm.SKILL_DIRS[0])
    skills = {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(root, skills_dir, "*", "SKILL.md"))}
    dead = []
    for r in rows:
        for p in r["code"].split():
            if not exists(p):
                dead.append({"id": r["id"], "field": "code", "path": p})
        if not exists(r["doc"]):
            dead.append({"id": r["id"], "field": "doc", "path": r["doc"]})
        dead += [{"id": r["id"], "field": "skill", "path": s} for s in r["skill"].split() if s not in skills]
        t = [x for x in r["test"].split() if "/" in x and not x.startswith(("-", "http"))]
        if t and not exists(t[0]):
            dead.append({"id": r["id"], "field": "test", "path": t[0]})

    covered = " ".join(r["code"] for r in rows).split()
    s = scanmod.scan(root)
    test = s["test_command"] or "TODO test command"
    doc = "README.md" if s["readme"] else "CLAUDE.md"
    unmapped = []
    for g in cfg["must_be_mapped"]:
        for d in sorted(glob.glob(os.path.join(root, g))):
            rel = os.path.relpath(d, root)
            if os.path.isdir(d) and not any(rel == c.rstrip("/") or rel.startswith(c.rstrip("/*") + "/") or c.startswith(rel + "/") for c in covered):
                row = "\t".join([scaffold.sid(rel), "TODO what this area does", rel, test, "working-agreements", doc, "TODO"])
                unmapped.append({"dir": rel, "row": row})

    used = {x for r in rows for x in r["skill"].split()}
    unused_skills = sorted(skills - used - set(cfg["skills_not_areas"]))
    todo = [r["id"] for r in rows if "TODO" in " ".join(r.values())]
    root_md = open(os.path.join(root, "CLAUDE.md"), encoding="utf-8").read() if os.path.isfile(os.path.join(root, "CLAUDE.md")) else ""
    docs = sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, "docs", "*.md")))
    unlisted = [d for d in docs if d not in root_md]
    return {"dead": dead, "unmapped": unmapped, "describe": todo, "unused_skills": unused_skills, "unlisted_docs": unlisted,
            "stale": stale_rows(root, rows)}


def is_clean(w):
    return not any(w[k] for k in ("dead", "unmapped", "describe", "unused_skills", "unlisted_docs", "stale"))


def write_stubs(root, w):
    """Append the stub rows for unmapped directories. Never edits or removes an existing row."""
    if not w["unmapped"]:
        return 0
    p = os.path.join(root, "map.tsv")
    text = open(p, encoding="utf-8").read()
    text = text if text.endswith("\n") else text + "\n"
    open(p, "w", encoding="utf-8").write(text + "\n".join(u["row"] for u in w["unmapped"]) + "\n")
    return len(w["unmapped"])


def render(w):
    if is_clean(w):
        return "map.tsv is in sync with the project: nothing to do."
    L = ["map.tsv needs attention (each item is for you, the agent, to resolve; then run `agentify check --strict`):"]
    for d in w["dead"]:
        L.append(f"  fix or remove   row {d['id']}: {d['field']} {d['path']} no longer exists")
    for u in w["unmapped"]:
        L.append(f"  add a row       {u['dir']} has no row. Stub (`agentify sync --write` appends it):")
        L.append("                  " + u["row"].replace("\t", "<TAB>"))
    for i in w["describe"]:
        L.append(f"  describe        row {i} still says TODO")
    for sk in w["unused_skills"]:
        L.append(f"  link a skill    skill {sk} is used by no row")
    for d in w["unlisted_docs"]:
        L.append(f"  list a doc      {d} is not in the root CLAUDE.md")
    for r in w["stale"]:
        why = f"{r['commits']} commit(s) since map.tsv was last committed" + (", plus uncommitted edits" if r["uncommitted"] else "") if r["commits"] else "uncommitted edits"
        L.append(f"  review a row    {r['id']} ({r['code']}): code changed, {why}; is its description, test and skill still right?")
        L += [f"                  {c}" for c in r["recent"]]
    if w["stale"]:
        L.append("Touching map.tsv (committed or not) marks every row reviewed, so only do it after reading the rows above.")
    return "\n".join(L)
