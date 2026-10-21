"""Put the agent-friendly layout into a project. Never overwrites a file that exists."""
import json
import os
import re
import shutil

from . import scan as scanmod

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHETYPE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "archetype")
# files copied as they are: these are the project's own copy, so a project is self-contained and agents need no installed tool
COPIED = ["tools/where.py", "tests/check_map.py", ".claude/skills/working-agreements/SKILL.md", ".claude/skills/audit-map/SKILL.md"]
NOT_ROWS = {"skills", "docs", "doc", ".claude"}


def sid(path):
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")


def draft_rows(s):
    doc = "README.md" if s["readme"] else "CLAUDE.md"
    tests_dir = next((a["dir"] for a in s["areas"] if a["kind"] == "test"), None)
    test = s["test_command"] or (tests_dir + "/" if tests_dir else "TODO test command")
    rows = []
    for a in s["areas"]:
        if a["kind"] != "source" or a["files"] == 0 or a["dir"] in NOT_ROWS:
            continue
        rows.append("\t".join([sid(a["dir"]), "TODO what this area does", a["dir"], test, "working-agreements", doc, "TODO"]))
    return rows or ["\t".join(["main", "TODO what this project does", ".", test, "working-agreements", doc, "TODO"])]


def render(text, **kv):
    for k, v in kv.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def plan(root):
    """What init would write: {relative path: content}. Existing files are left out."""
    s = scanmod.scan(root)
    rows = draft_rows(s)
    areas = [a for a in s["areas"] if a["kind"] != "doc" and a["dir"] not in NOT_ROWS and (a["files"] or a["kind"] == "test")]
    layout = "\n".join(f"- `{a['dir']}/` TODO what it is" for a in areas) or "- TODO"
    stack = ", ".join(s["stack"] + [l for l in s["languages"] if not any(l.split()[0] in x for x in s["stack"])]) or "TODO"
    src_dirs = sorted({a["dir"].split("/")[0] + "/*" for a in s["areas"] if "/" in a["dir"] and a["dir"].split("/")[0] in scanmod.GROUP_DIRS})
    out = {}
    for rel in COPIED:
        out[rel] = open(os.path.join(ARCHETYPE, rel), encoding="utf-8").read()
    # a new root CLAUDE.md lists the style guide; an existing one is never edited, so then a guide is neither created nor listed here
    guide = s["style_guides"][0] if s["style_guides"] else "docs/style.md"
    if not s["style_guides"] and not os.path.exists(os.path.join(root, "CLAUDE.md")):
        out["docs/style.md"] = open(os.path.join(ARCHETYPE, "docs", "style.md"), encoding="utf-8").read()
    out["CLAUDE.md"] = render(open(os.path.join(ARCHETYPE, "CLAUDE.md"), encoding="utf-8").read(), name=s["name"], layout=layout, style_guide=guide)
    out["map.tsv"] = render(open(os.path.join(ARCHETYPE, "map.tsv"), encoding="utf-8").read(), stack=stack, rows="\n".join(rows))
    cfg = {"root_budget": 120, "scoped_budget": 300}
    if src_dirs:
        cfg["must_be_mapped"] = src_dirs
    out[".agentify.json"] = json.dumps(cfg, indent=2) + "\n"
    return {rel: body for rel, body in out.items() if not os.path.exists(os.path.join(root, rel))}, s


def init(root, dry_run=False):
    root = os.path.abspath(root)
    files, s = plan(root)
    written = []
    for rel, body in files.items():
        if not dry_run:
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(body)
            if rel.endswith(".py"):
                os.chmod(p, 0o755)
        written.append(rel)
    skipped = [r for r in ["CLAUDE.md", "map.tsv"] + COPIED if r not in files]
    return written, skipped, s


def upgrade(root, dry_run=False):
    """Replace the project's copies of the shared files (where.py, check_map.py) with the bundled ones. Returns the paths changed."""
    changed = []
    for rel in ("tools/where.py", "tests/check_map.py"):
        dst = os.path.join(root, rel)
        if os.path.isfile(dst) and open(dst, "rb").read() != open(os.path.join(ARCHETYPE, rel), "rb").read():
            changed.append(rel)
            if not dry_run:
                shutil.copyfile(os.path.join(ARCHETYPE, rel), dst)
    return changed
