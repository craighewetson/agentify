"""A/B benchmark: do fresh agent sessions find things faster, cheaper and correctly in layout B than in layout A?

Each task is a question about the project with a known answer. Every run is a fresh headless `claude -p` session in a checkout of the
project (read-only tools, a spend cap), and its real token usage and cost come from Claude's own result. Answers are graded by regex.
This costs real money on the user's login: start with --dry-run, then a small --runs, and look at the cost before a large run.
"""
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

CLAUDE = os.environ.get("AGENTIFY_CLAUDE", "claude")
READ_ONLY = ["Read", "Skill", "Grep", "Glob", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)", "Bash(grep:*)",
             "Bash(rg:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(tools/where.py:*)", "Bash(python3 tools/where.py:*)"]
DENIED = ["Edit", "Write", "NotebookEdit", "Agent", "WebFetch", "WebSearch"]
WRAP = ("Answer this question about the project in your current directory, using only the files in it. Do not change anything. "
        "Be brief: name the exact files, commands or values.\n\nQuestion: ")


def load_tasks(path):
    doc = json.load(open(path, encoding="utf-8"))
    return doc["tasks"]


def grade(answer, task):
    ok = all(re.search(p, answer, re.I | re.S) for p in task.get("must", []))
    return ok and not any(re.search(p, answer, re.I | re.S) for p in task.get("must_not", []))


def why_wrong(answer, task):
    """Why an answer failed grading: the patterns it lacked and the forbidden ones it hit (empty when it passed)."""
    out = [f"missing {p}" for p in task.get("must", []) if not re.search(p, answer, re.I | re.S)]
    return out + [f"hit {p}" for p in task.get("must_not", []) if re.search(p, answer, re.I | re.S)]


def run_one(cwd, task, model, budget, timeout=600):
    cmd = [CLAUDE, "-p", WRAP + task["prompt"], "--model", model, "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--max-budget-usd", str(budget), "--allowedTools", ",".join(READ_ONLY), "--disallowedTools", ",".join(DENIED)]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"task": task["id"], "error": "timeout", "correct": False, "cost": 0.0, "tokens": 0, "turns": 0, "tool_calls": 0, "where": False, "searches": 0, "reads": 0, "seconds": timeout}
    tools, result, turns = [], None, 0
    for line in r.stdout.split("\n"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("type") == "assistant":
            turns += 1
            for c in (j.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    tools.append((c.get("name", ""), json.dumps(c.get("input", {}))))
        elif j.get("type") == "result":
            result = j
    if not result:
        return {"task": task["id"], "error": "no result: " + (r.stderr or r.stdout)[-200:], "correct": False, "cost": 0.0, "tokens": 0, "turns": turns,
                "tool_calls": len(tools), "where": False, "searches": 0, "reads": 0, "seconds": round(time.time() - t0, 1)}
    u = result.get("usage") or {}
    answer = result.get("result") or ""
    return {"task": task["id"], "error": result.get("is_error") and answer[:200] or None, "correct": grade(answer, task) and not result.get("is_error"),
            "cost": float(result.get("total_cost_usd") or 0.0),
            "tokens": sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")),
            "cache_read": int(u.get("cache_read_input_tokens") or 0), "cache_create": int(u.get("cache_creation_input_tokens") or 0),
            "why": why_wrong(answer, task),
            "turns": turns, "tool_calls": len(tools),
            "where": any("where.py" in i for n, i in tools), "reads": sum(1 for n, i in tools if n == "Read"),
            "searches": sum(1 for n, i in tools if n in ("Grep", "Glob") or (n == "Bash" and re.search(r"\b(grep|rg|find)\b", i))),
            "seconds": round(time.time() - t0, 1), "answer": answer[:1500]}


def resolve_arm(project, spec, tmp, label):
    """A directory is used as it is; anything else is a git ref, checked out beside the project (so the ancestors' CLAUDE.md files are the same for both arms)."""
    if os.path.isdir(spec):
        return os.path.abspath(spec), None
    wt = os.path.join(tmp, label)
    r = subprocess.run(["git", "-C", project, "worktree", "add", "--detach", wt, spec], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"agentify: {spec} is neither a directory nor a git ref of {project}: {r.stderr.strip()[-150:]}")
    return wt, wt


def plan(tasks, runs, limit):
    return [(rep, t) for rep in range(runs) for t in (tasks[:limit] if limit else tasks)]


def bench(project, tasks, a, b, runs, model, budget, total_budget, limit=None, log=print):
    project = os.path.abspath(project)
    tmp = tempfile.mkdtemp(prefix=".agentify-bench-", dir=os.path.dirname(project))
    made, results, spent = [], [], 0.0
    try:
        arms = {}
        for label, spec in (("a", a), ("b", b)):
            arms[label], wt = resolve_arm(project, spec, tmp, label)
            if wt:
                made.append(wt)
        for rep, task in plan(tasks, runs, limit):
            order = ["a", "b"] if (rep + len(results)) % 2 == 0 else ["b", "a"]   # alternate who goes first, so neither arm always runs warm
            for arm in order:
                if spent >= total_budget:
                    log(f"stopped: spent ${spent:.2f}, the total budget of ${total_budget:.2f} is reached")
                    return {"project": project, "a": a, "b": b, "model": model, "runs": runs, "spent": round(spent, 4), "stopped_early": True, "results": results}
                r = run_one(arms[arm], task, model, budget)
                r.update({"arm": arm, "rep": rep})
                results.append(r)
                spent += r["cost"]
                log(f"  rep {rep} {task['id']:<14} {arm}  {'ok ' if r['correct'] else 'WRONG'}  ${r['cost']:.3f}  {r['turns']} turns  {r['tool_calls']} tools  where={'y' if r['where'] else 'n'}  (spent ${spent:.2f})")
        return {"project": project, "a": a, "b": b, "model": model, "runs": runs, "spent": round(spent, 4), "stopped_early": False, "results": results}
    finally:
        for wt in made:
            subprocess.run(["git", "-C", project, "worktree", "remove", "--force", wt], capture_output=True)
        subprocess.run(["git", "-C", project, "worktree", "prune"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def _med(xs):
    return statistics.median(xs) if xs else 0.0


def summarize(doc):
    rs = doc["results"]
    out = {"tasks": {}, "total": {}}
    for arm in ("a", "b"):
        mine = [r for r in rs if r["arm"] == arm]
        out["total"][arm] = {"runs": len(mine), "correct": sum(r["correct"] for r in mine), "cost": round(sum(r["cost"] for r in mine), 4),
                             "tokens": sum(r["tokens"] for r in mine), "turns": sum(r["turns"] for r in mine), "tool_calls": sum(r["tool_calls"] for r in mine),
                             "where_used": sum(r["where"] for r in mine)}
    for t in sorted({r["task"] for r in rs}):
        row = {}
        for arm in ("a", "b"):
            m = [r for r in rs if r["task"] == t and r["arm"] == arm]
            row[arm] = {"n": len(m), "correct": sum(r["correct"] for r in m), "median_cost": round(_med([r["cost"] for r in m]), 4),
                        "min_cost": round(min([r["cost"] for r in m] or [0]), 4), "max_cost": round(max([r["cost"] for r in m] or [0]), 4),
                        "median_turns": _med([r["turns"] for r in m]), "median_tools": _med([r["tool_calls"] for r in m])}
        out["tasks"][t] = row
    ta, tb = out["total"]["a"], out["total"]["b"]
    reps = sorted({r["rep"] for r in rs})
    per_rep = [(sum(r["cost"] for r in rs if r["rep"] == k and r["arm"] == "a"), sum(r["cost"] for r in rs if r["rep"] == k and r["arm"] == "b")) for k in reps]
    out["rep_change_percent"] = [round(100.0 * (y - x) / x, 1) if x else 0.0 for x, y in per_rep]
    out["cost_change_percent"] = round(100.0 * (tb["cost"] - ta["cost"]) / ta["cost"], 1) if ta["cost"] else 0.0
    # the same task in the same repeat, one run per arm: is B cheaper more often than a coin toss would make it?
    pairs = [(next(r["cost"] for r in rs if r["task"] == t and r["rep"] == k and r["arm"] == "a"), next(r["cost"] for r in rs if r["task"] == t and r["rep"] == k and r["arm"] == "b"))
             for t in sorted({r["task"] for r in rs}) for k in reps
             if any(r["task"] == t and r["rep"] == k and r["arm"] == "a" for r in rs) and any(r["task"] == t and r["rep"] == k and r["arm"] == "b" for r in rs)]
    n, wins = len(pairs), sum(1 for x, y in pairs if y < x)
    p = sum(math.comb(n, i) for i in range(wins, n + 1)) / 2 ** n if n else 1.0
    out["pairs"] = {"n": n, "b_cheaper": wins, "sign_test_p": round(p, 4)}
    out["cheaper_in_reps"] = f"{sum(1 for x, y in per_rep if y < x)} of {len(per_rep)}"
    for arm in ("a", "b"):
        mine = [r for r in rs if r["arm"] == arm and "cache_read" in r]
        total = sum(r["tokens"] for r in mine)
        out["total"][arm]["cache_read_share"] = round(sum(r["cache_read"] for r in mine) / total, 2) if total else None
    if ta["runs"] == 0 or tb["runs"] == 0:
        out["verdict"] = "NO DATA"
    elif tb["correct"] / tb["runs"] < ta["correct"] / ta["runs"]:
        out["verdict"] = "WORSE: B answers correctly less often"
    elif tb["cost"] < ta["cost"] and wins == n and p < 0.05:
        out["verdict"] = f"BETTER: B is as correct and cheaper in all {n} paired runs (sign test p={p:.3f})"
    elif tb["cost"] < ta["cost"] and wins * 2 > n:
        out["verdict"] = f"LEANS BETTER: cheaper in {wins} of {n} paired runs (sign test p={p:.3f}); too few to call, run more repeats"
    else:
        out["verdict"] = f"NOT BETTER: B is cheaper in {wins} of {n} paired runs (sign test p={p:.3f})"
    return out


def render(doc):
    s = summarize(doc)
    out = [f"{os.path.basename(doc['project'])}: A = {doc['a']}   B = {doc['b']}   model {doc['model']}   {doc['runs']} repeat(s)   spent ${doc['spent']:.2f}" + ("   STOPPED EARLY" if doc.get("stopped_early") else "")]
    out.append(f"  {'task':<16}{'correct A':>10}{'correct B':>10}{'$ med A':>10}{'$ med B':>10}{'turns A':>9}{'turns B':>9}{'tools A':>9}{'tools B':>9}")
    for t, row in s["tasks"].items():
        a, b = row["a"], row["b"]
        out.append(f"  {t:<16}{str(a['correct']) + '/' + str(a['n']):>10}{str(b['correct']) + '/' + str(b['n']):>10}{a['median_cost']:>10.3f}{b['median_cost']:>10.3f}{a['median_turns']:>9.0f}{b['median_turns']:>9.0f}{a['median_tools']:>9.0f}{b['median_tools']:>9.0f}")
    ta, tb = s["total"]["a"], s["total"]["b"]
    out.append(f"  total  A: {ta['correct']}/{ta['runs']} correct, ${ta['cost']:.3f}, {ta['tokens']} tokens, {ta['turns']} turns, {ta['tool_calls']} tool calls, where.py in {ta['where_used']} runs")
    out.append(f"  total  B: {tb['correct']}/{tb['runs']} correct, ${tb['cost']:.3f}, {tb['tokens']} tokens, {tb['turns']} turns, {tb['tool_calls']} tool calls, where.py in {tb['where_used']} runs")
    out.append(f"  B's cost is {s['cost_change_percent']:+.1f}% of A's; B was cheaper in {s['cheaper_in_reps']} repeats")
    out.append("  change in B's cost per repeat: " + ", ".join(f"{c:+.0f}%" for c in s["rep_change_percent"]) + "   (a total moved by one repeat is not a result)")
    if ta.get("cache_read_share") is not None and tb.get("cache_read_share") is not None:
        out.append(f"  share of tokens read from the cache: A {ta['cache_read_share']:.2f}, B {tb['cache_read_share']:.2f}" + ("   DIFFERENT: cost may reflect warmth, not layout" if abs(ta["cache_read_share"] - tb["cache_read_share"]) > 0.2 else ""))
    wrong = [(r["arm"], r["task"], r["why"]) for r in doc["results"] if not r["correct"] and r.get("why")]
    for arm, task, why in wrong[:4]:
        out.append(f"  not correct: {arm.upper()} {task}: {'; '.join(why)[:140]}")
    out.append("  VERDICT: " + s["verdict"])
    return "\n".join(out)
