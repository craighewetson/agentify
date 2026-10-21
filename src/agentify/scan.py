"""Read a project and say what it is: stack, areas, tests, and what agent files it already has. Read-only."""
import json
import os
import re

SKIP = {".git", "node_modules", "target", "build", "dist", "out", "venv", ".venv", "__pycache__", "vendor", "bin", "obj", "coverage"}
TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__", "e2e", "integration"}
DOC_DIRS = {"docs", "doc"}
GROUP_DIRS = {"apps", "packages", "services", "src", "cmd", "lib", "modules"}   # their children are areas of their own
EXT_LANG = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin",
            ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".odin": "Odin", ".c": "C", ".cpp": "C++",
            ".swift": "Swift", ".sh": "Shell", ".zig": "Zig", ".ex": "Elixir"}


def _has(root, name):
    return os.path.exists(os.path.join(root, name))


def _any_file(root, suffixes):
    return any(f.endswith(suffixes) for f in os.listdir(root))


def detect_stack(root):
    """[(label, test command or None)] from manifests at the root."""
    out = []
    if _has(root, "package.json"):
        cmd = "npm test"
        try:
            scripts = json.load(open(os.path.join(root, "package.json"), encoding="utf-8")).get("scripts", {})
            cmd = "npm test" if "test" in scripts else None
        except (OSError, ValueError):
            pass
        out.append(("Node (package.json)", cmd))
    if _has(root, "pom.xml"):
        out.append(("Java (Maven)", "mvn test"))
    if _has(root, "build.gradle") or _has(root, "build.gradle.kts"):
        out.append(("JVM (Gradle)", "./gradlew test" if _has(root, "gradlew") else "gradle test"))
    if _has(root, "Cargo.toml"):
        out.append(("Rust (Cargo)", "cargo test"))
    if _has(root, "go.mod"):
        out.append(("Go (modules)", "go test ./..."))
    if _has(root, "pyproject.toml") or _has(root, "requirements.txt") or _has(root, "setup.py"):
        out.append(("Python", "pytest" if _has(root, "pytest.ini") or _has(root, "pyproject.toml") else "python3 -m unittest"))
    if _has(root, "Gemfile"):
        out.append(("Ruby (Bundler)", "bundle exec rake test"))
    if _has(root, "composer.json"):
        out.append(("PHP (Composer)", "composer test"))
    if _any_file(root, (".sln", ".csproj")):
        out.append((".NET", "dotnet test"))
    if _any_file(root, (".odin",)):
        out.append(("Odin", "odin test ."))
    if _has(root, "Makefile"):
        try:
            if "\ntest:" in "\n" + open(os.path.join(root, "Makefile"), encoding="utf-8", errors="replace").read():
                out.append(("Make", "make test"))
        except OSError:
            pass
    return out


def count_ext(path, limit=5000, shallow=False):
    counts, seen = {}, 0
    for base, dirs, files in os.walk(path):
        dirs[:] = [] if shallow else [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in EXT_LANG:
                counts[ext] = counts.get(ext, 0) + 1
            seen += 1
            if seen > limit:
                return counts
    return counts


def areas(root):
    """Directories worth a row in the map: [{'dir', 'kind', 'files', 'lang'}]. Children of apps/, packages/ ... count individually."""
    found = []

    def add(rel, shallow=False):
        ext = count_ext(os.path.join(root, rel), shallow=shallow)
        n = sum(ext.values())
        name = os.path.basename(rel)
        kind = "test" if name in TEST_DIRS else "doc" if name in DOC_DIRS else "source"
        lang = EXT_LANG[max(ext, key=ext.get)] if ext else ""
        found.append({"dir": rel, "kind": kind, "files": n, "lang": lang})

    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p) or name in SKIP or name.startswith("."):
            continue
        if name in GROUP_DIRS:
            kids = [k for k in sorted(os.listdir(p)) if os.path.isdir(os.path.join(p, k)) and k not in SKIP and not k.startswith(".")]
            if kids:
                if count_ext(p, shallow=True):   # code directly in src/ (a crate, a Go module) is an area as well as its subdirectories
                    add(name, shallow=True)
                for k in kids:
                    add(f"{name}/{k}")
                continue
        add(name)
    return found


def _lines(path):
    try:
        t = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    return {"lines": len(t.split("\n")), "bytes": len(t.encode()), "approx_tokens": len(t.encode()) // 4}


def headings(path):
    """Sections of a markdown file with their size, biggest first: what to move out of a long CLAUDE.md."""
    try:
        L = open(path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError:
        return []
    marks = [i for i, l in enumerate(L) if l.startswith("#")]
    secs = [(L[a].strip(), (b if b else len(L)) - a) for a, b in zip(marks, marks[1:] + [None])]
    return sorted(secs, key=lambda s: -s[1])


STYLE_WORDS = re.compile(r"style|convention|coding[-_ ]?standard|guideline|contributing", re.I)


def style_guides(root):
    """Existing style or contributing guides (markdown) at the root or in docs/, as relative paths."""
    found = []
    for d in ("", "docs", "doc"):
        folder = os.path.join(root, d)
        if os.path.isdir(folder):
            found += [os.path.join(d, f) for f in sorted(os.listdir(folder)) if f.lower().endswith(".md") and STYLE_WORDS.search(f)]
    return found


def scan(root):
    root = os.path.abspath(root)
    stack = detect_stack(root)
    ext = count_ext(root)
    langs = [EXT_LANG[e] for e in sorted(ext, key=ext.get, reverse=True)[:3]]
    skills_dir = next((d for d in ("skills", ".claude/skills") if os.path.isdir(os.path.join(root, d))), None)
    return {
        "root": root,
        "name": os.path.basename(root),
        "stack": [s for s, _ in stack],
        "test_command": next((c for _, c in stack if c), None),
        "languages": langs,
        "areas": areas(root),
        "git": os.path.isdir(os.path.join(root, ".git")),
        "claude_md": _lines(os.path.join(root, "CLAUDE.md")),
        "agents_md": _lines(os.path.join(root, "AGENTS.md")),
        "readme": _lines(os.path.join(root, "README.md")),
        "biggest_sections": headings(os.path.join(root, "CLAUDE.md"))[:5],
        "style_guides": style_guides(root),
        "has_map": os.path.isfile(os.path.join(root, "map.tsv")),
        "has_where": os.path.isfile(os.path.join(root, "tools", "where.py")),
        "has_check": os.path.isfile(os.path.join(root, "tests", "check_map.py")),
        "skills_dir": skills_dir,
        "skills": sorted(os.listdir(os.path.join(root, skills_dir))) if skills_dir else [],
    }


def render(s):
    out = [f"{s['name']}  ({s['root']})", f"  stack      {', '.join(s['stack']) or 'no manifest found'}   languages: {', '.join(s['languages']) or '-'}",
           f"  tests      {s['test_command'] or 'no test command found'}"]
    for k, label in (("claude_md", "CLAUDE.md"), ("agents_md", "AGENTS.md"), ("readme", "README.md")):
        v = s[k]
        out.append(f"  {label:<10} " + (f"{v['lines']} lines, ~{v['approx_tokens']} tokens" if v else "none"))
    if s["biggest_sections"]:
        out.append("  biggest CLAUDE.md sections: " + "; ".join(f"{h.lstrip('# ')} ({n})" for h, n in s["biggest_sections"]))
    out.append("  style guide " + (", ".join(s["style_guides"]) or "none"))
    out.append(f"  agentified map.tsv={'yes' if s['has_map'] else 'no'}  where.py={'yes' if s['has_where'] else 'no'}  check_map.py={'yes' if s['has_check'] else 'no'}  skills={len(s['skills'])}")
    out.append("  areas:")
    for a in s["areas"]:
        out.append(f"    {a['dir']:<30} {a['kind']:<7} {a['files']:>5} files  {a['lang']}")
    return "\n".join(out)
