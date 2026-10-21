"""agentify: scan | init | check | upgrade, in the spirit of a formatter or a linter for agent-friendliness."""
import argparse
import json
import os
import subprocess
import sys
import time

from . import __version__, bench, hook, measure, scaffold, sync
from . import scan as scanmod

CHECK = os.path.join(scaffold.ARCHETYPE, "tests", "check_map.py")


def cmd_scan(a):
    s = scanmod.scan(a.project)
    print(json.dumps(s, indent=1) if a.json else scanmod.render(s))
    return 0


def cmd_init(a):
    written, skipped, s = scaffold.init(a.project, a.dry_run)
    verb = "would write" if a.dry_run else "wrote"
    for r in written:
        print(f"  {verb} {r}")
    for r in skipped:
        print(f"  kept   {r} (already there)")
    if "CLAUDE.md" in skipped:
        print("\nCLAUDE.md already exists, so it was not touched. Add the 'Find things fast' block from "
              + os.path.join(scaffold.ARCHETYPE, "CLAUDE.md") + " and keep the file under the budget.")
    if "CLAUDE.md" in skipped:
        if s["style_guides"]:
            print("Style guide found: " + ", ".join(s["style_guides"]) + ". Point rules at its sections in the Rules table, e.g. `" + s["style_guides"][0] + "#section`.")
        else:
            print("No style guide found. When a rule needs one, create docs/style.md (see " + os.path.join(scaffold.ARCHETYPE, "docs", "style.md") + ") and list it in CLAUDE.md.")
    print("\nNext: fill every TODO (agentify check --strict lists them), split a long CLAUDE.md (see docs/adopting-a-project.md),")
    print("then run: agentify check " + a.project)
    return 0


def cmd_check(a):
    root = os.path.abspath(a.project)
    # the bundled check is the one source of truth; the project's own copy runs the same code in its own test battery
    r = subprocess.run([sys.executable, CHECK, "--root", root] + (["--strict"] if a.strict else []))
    own = os.path.join(root, "tests", "check_map.py")
    if os.path.isfile(own) and open(own, "rb").read() != open(CHECK, "rb").read():
        print("  note  the project's tests/check_map.py differs from the bundled one: run `agentify upgrade " + a.project + "`")
    return r.returncode


def cmd_sync(a):
    root = os.path.abspath(a.project)
    if not os.path.isfile(os.path.join(root, "map.tsv")):
        sys.exit("agentify sync: no map.tsv here; run: agentify init " + a.project)
    w = sync.worklist(root)
    if a.write and sync.write_stubs(root, w):
        print(f"  appended {len(w['unmapped'])} stub row(s) to map.tsv")
        w = sync.worklist(root)
    print(json.dumps(w, indent=1) if a.json else sync.render(w))
    return 0 if sync.is_clean(w) else 1


def cmd_hook(a):
    ok, msg = (hook.install if a.action == "install" else hook.uninstall)(os.path.abspath(a.project))
    print(msg)
    return 0 if ok else 1


def cmd_measure(a):
    m = measure.measure(a.project, a.bytes_per_token)
    old = measure.measure_ref(a.project, a.against, a.bytes_per_token) if a.against else None
    if old:
        m.update(measure.compare(m, old))
        m["against"] = {"ref": a.against, **{k: old[k] for k in ("total_tokens", "project_tokens", "files")}}
    print(json.dumps(m, indent=1) if a.json else measure.render(m, old, a.against))
    if a.budget is not None and m["project_tokens"] > a.budget:
        print(f"agentify: the project loads {m['project_tokens']} tokens at the start of a session, over the budget of {a.budget}", file=sys.stderr)
        return 1
    return 0


def cmd_bench(a):
    if a.report:
        print(bench.render(json.load(open(a.report, encoding="utf-8"))))
        return 0
    if not (a.tasks and a.a and a.b):
        sys.exit("agentify bench: --tasks, --a and --b are required (or --report FILE)")
    tasks = bench.load_tasks(a.tasks)
    n = len(bench.plan(tasks, a.runs, a.limit_tasks)) * 2
    worst = min(n * a.max_budget_usd, a.total_budget)
    print(f"bench: {n} headless sessions ({a.runs} repeat(s) x {len(bench.plan(tasks, 1, a.limit_tasks))} task(s) x 2 arms) with {a.model}; "
          f"each capped at ${a.max_budget_usd}, the whole run at ${a.total_budget}. Worst case about ${worst:.2f}.")
    if a.dry_run:
        print("dry run: nothing was started")
        return 0
    doc = bench.bench(a.project, tasks, a.a, a.b, a.runs, a.model, a.max_budget_usd, a.total_budget, a.limit_tasks)
    out = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bench", "results",
                                time.strftime("%Y%m%d-%H%M%S-") + os.path.basename(os.path.abspath(a.project)) + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print(bench.render(doc))
    print("saved " + out)
    return 0


def cmd_upgrade(a):
    changed = scaffold.upgrade(os.path.abspath(a.project), a.dry_run)
    for c in changed:
        print(("  would update " if a.dry_run else "  updated ") + c)
    if not changed:
        print("  already current")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="agentify", description="Make a project quick for a coding agent to get around in.")
    p.add_argument("--version", action="version", version="agentify " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, h in (("scan", cmd_scan, "report what the project is (read-only)"),
                        ("init", cmd_init, "add the missing agent files (never overwrites)"),
                        ("check", cmd_check, "lint: is it agent-friendly, and still true?"),
                        ("measure", cmd_measure, "tokens loaded at the start of a session; --against REF shows the saving"),
                        ("bench", cmd_bench, "A/B: do fresh agent sessions do better in layout B than A? (costs money; --dry-run first)"),
                        ("sync", cmd_sync, "worklist: what in map.tsv is dead, missing, undescribed or stale (--write appends stub rows)"),
                        ("hook", cmd_hook, "install | uninstall a git pre-commit hook that runs check"),
                        ("upgrade", cmd_upgrade, "refresh the project's copies of where.py and check_map.py")):
        sp = sub.add_parser(name, help=h)
        if name == "hook":
            sp.add_argument("action", choices=["install", "uninstall"])
        sp.add_argument("project", nargs="?", default=".")
        sp.set_defaults(fn=fn)
        if name == "sync":
            sp.add_argument("--json", action="store_true")
            sp.add_argument("--write", action="store_true", help="append stub rows for unmapped directories (never edits or deletes a row)")
        if name == "scan":
            sp.add_argument("--json", action="store_true")
        if name in ("init", "upgrade"):
            sp.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
        if name == "measure":
            sp.add_argument("--json", action="store_true")
            sp.add_argument("--against", metavar="REF", help="also measure the project at this git ref and show the saving")
            sp.add_argument("--budget", type=int, metavar="TOKENS", help="exit 1 if the project-controlled startup tokens exceed this")
            sp.add_argument("--bytes-per-token", type=float, default=measure.BYTES_PER_TOKEN)
        if name == "bench":
            sp.add_argument("--tasks", metavar="FILE", help="JSON file of questions with expected answers")
            sp.add_argument("--a", metavar="DIR_OR_REF", help="the baseline: a directory or a git ref of the project")
            sp.add_argument("--b", metavar="DIR_OR_REF", help="the candidate")
            sp.add_argument("--runs", type=int, default=3, help="repeats of every task per arm (the model varies run to run)")
            sp.add_argument("--limit-tasks", type=int, metavar="K", help="only the first K tasks")
            sp.add_argument("--model", default="sonnet")
            sp.add_argument("--max-budget-usd", type=float, default=0.40, help="cap for one session")
            sp.add_argument("--total-budget", type=float, default=5.0, help="stop the whole run after this much")
            sp.add_argument("--dry-run", action="store_true", help="say what would run and the worst-case cost; start nothing")
            sp.add_argument("--out", metavar="FILE")
            sp.add_argument("--report", metavar="FILE", help="print the summary of a saved result")
        if name == "check":
            sp.add_argument("--strict", action="store_true", help="warnings fail too")
    a = p.parse_args(argv)
    if not os.path.isdir(a.project):
        sys.exit(f"agentify: {a.project} is not a directory")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
