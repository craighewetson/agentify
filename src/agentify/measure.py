"""What loads at the start of a session, in tokens. Read-only; no model is called.

Counted (these are what /context calls memory files and skills, and they are paid for in every session):
  project   the project's root CLAUDE.md and everything it @imports
  ancestor  CLAUDE.md files in the directories above the project (Claude Code reads them too)
  user      ~/.claude/CLAUDE.md and what it imports
  memory    the project's MEMORY.md under ~/.claude/projects/
  skills    name + description of each skill (the body only loads when a skill is used)
"project_tokens" is what the project itself controls (project + its skills); the rest is the same whichever layout the project has.

Tokens are estimated from bytes. The ratio is calibrated on two real /context readings of one project: 101 KB read as 40.7k tokens
and 16.7 KB read as 7.2k tokens, about 2.4 bytes per token for dense markdown full of paths. Use --bytes-per-token to change it.
"""
import glob
import math
import os
import re
import shutil
import subprocess
import tempfile

BYTES_PER_TOKEN = 2.4
IMPORT = re.compile(r"(?:^|\s)@(\S+)")
PROJECT_SCOPES = ("project", "skills")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _imports(path, text):
    """Files named by @path outside code fences, resolved against the importing file."""
    out, fenced = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for m in IMPORT.finditer(line):
            cand = os.path.normpath(os.path.join(os.path.dirname(path), os.path.expanduser(m.group(1).rstrip(".,;:)"))))
            if os.path.isfile(cand):
                out.append(cand)
    return out


def _with_imports(path, scope, seen, depth=0):
    path = os.path.realpath(path)
    text = _read(path)
    if text is None or path in seen or depth > 5:
        return []
    seen.add(path)
    out = [{"abs": path, "bytes": len(text.encode()), "scope": scope}]
    for imp in _imports(path, text):
        out += _with_imports(imp, scope, seen, depth + 1)
    return out


def _skill_lines(skills_dir):
    out = []
    for p in sorted(glob.glob(os.path.join(skills_dir, "*", "SKILL.md"))):
        text = _read(p) or ""
        head = text.split("---")[1] if text.startswith("---") and text.count("---") >= 2 else ""
        name = re.search(r"^name:\s*(.+)$", head, re.M)
        desc = re.search(r"^description:\s*(.+)$", head, re.M)
        line = f"{name.group(1).strip() if name else os.path.basename(os.path.dirname(p))}: {desc.group(1).strip() if desc else ''}"
        out.append({"abs": p, "bytes": len(line.encode()), "scope": None})
    return out


def collect(project, identity=None, home=None):
    """Every file that loads at start. `identity` is the directory whose ancestors and memory count (when measuring a checkout of an older ref)."""
    project = os.path.abspath(project)
    identity = os.path.abspath(identity or project)
    home = home or os.path.expanduser("~")
    seen, files = set(), []
    files += _with_imports(os.path.join(project, "CLAUDE.md"), "project", seen)
    user_md = os.path.realpath(os.path.join(home, ".claude", "CLAUDE.md"))
    d = os.path.dirname(identity)
    while True:
        cand = os.path.join(d, "CLAUDE.md")
        if os.path.isfile(cand) and os.path.realpath(cand) != user_md:
            files += _with_imports(cand, "ancestor", seen)
        if d == os.path.dirname(d):
            break
        d = os.path.dirname(d)
    files += _with_imports(user_md, "user", seen)
    slug = re.sub(r"[^A-Za-z0-9]", "-", identity)
    files += _with_imports(os.path.join(home, ".claude", "projects", slug, "memory", "MEMORY.md"), "memory", seen)
    for s in _skill_lines(os.path.join(project, ".claude", "skills")):
        s["scope"] = "skills"
        files.append(s)
    for s in _skill_lines(os.path.join(home, ".claude", "skills")):
        s["scope"] = "user-skills"
        files.append(s)
    for f in files:
        f["path"] = _display(f["abs"], project, home)
    return files


def _display(path, project, home):
    if path.startswith(project + os.sep):
        return os.path.relpath(path, project)
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def tokens(nbytes, bpt=BYTES_PER_TOKEN):
    return int(math.ceil(nbytes / bpt))


def measure(project, bpt=BYTES_PER_TOKEN, identity=None, home=None):
    files = collect(project, identity, home)
    for f in files:
        f["tokens"] = tokens(f["bytes"], bpt)
        f.pop("abs", None)
    return {"project": os.path.abspath(project), "bytes_per_token": bpt, "files": files,
            "total_tokens": sum(f["tokens"] for f in files),
            "project_tokens": sum(f["tokens"] for f in files if f["scope"] in PROJECT_SCOPES)}


def measure_ref(project, ref, bpt=BYTES_PER_TOKEN, home=None):
    """The same measurement for the project as it was at a git ref, in a throwaway checkout outside the repo."""
    project = os.path.abspath(project)
    tmp = tempfile.mkdtemp(prefix="agentify-ref-")
    wt = os.path.join(tmp, "checkout")
    try:
        r = subprocess.run(["git", "-C", project, "worktree", "add", "--detach", wt, ref], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("agentify: cannot check out " + ref + ": " + r.stderr.strip()[-200:])
        return measure(wt, bpt, identity=project, home=home)
    finally:
        subprocess.run(["git", "-C", project, "worktree", "remove", "--force", wt], capture_output=True)
        subprocess.run(["git", "-C", project, "worktree", "prune"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def compare(new, old):
    d = new["project_tokens"] - old["project_tokens"]
    return {"delta_tokens": d, "saving_percent": round(100.0 * (old["project_tokens"] - new["project_tokens"]) / old["project_tokens"], 1) if old["project_tokens"] else 0.0}


def render(m, old=None, ref=None):
    rows = sorted(m["files"], key=lambda f: -f["tokens"])
    out = [f"{os.path.basename(m['project'])}: what loads at the start of a session"]
    out.append(f"  {'scope':<12}{'tokens':>8}  file")
    for f in rows:
        out.append(f"  {f['scope']:<12}{f['tokens']:>8}  {f['path']}")
    out.append(f"  {'total':<12}{m['total_tokens']:>8}   of which the project controls {m['project_tokens']}")
    if old:
        c = compare(m, old)
        out.append(f"  against {ref}: project-controlled {old['project_tokens']} -> {m['project_tokens']} tokens ({c['delta_tokens']:+d}, {c['saving_percent']}% saved)")
    out.append(f"  (estimated at {m['bytes_per_token']} bytes per token, calibrated on /context readings; --bytes-per-token to change)")
    return "\n".join(out)
