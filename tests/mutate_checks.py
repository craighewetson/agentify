#!/usr/bin/env python3
"""Proves the rule "every rule in check_map.py has a test that breaks the layout on purpose".

For each check in archetype/tests/check_map.py it makes a scratch copy of the repo in which that one check always passes, then runs the
test suite. If the suite stays green, nothing notices that check is gone: it has no break-it test. Exit 1 lists those checks.
Takes about 6 seconds per check, so it is run before a release, not on every commit.   Run: python3 tests/mutate_checks.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPIES = ("archetype/tests/check_map.py", "tests/check_map.py")
NONE = "@@no check starts with this@@"
HOOK = "    def check(self, name, cond, detail=\"\", warn=False):\n"


def check_names(source):
    """The start of each check's name, up to any {placeholder}, as the checks print it."""
    return [re.sub(r"\{.*", "", m) for m in re.findall(r'R\.check\(f?"([^"]+)"', source)]


def suite_passes(scratch, name):
    env = dict(os.environ, NEUTRALISE=name)
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "tests"], cwd=scratch, env=env, capture_output=True, text=True)
    return r.returncode == 0


def main():
    names = check_names(open(os.path.join(ROOT, COPIES[0]), encoding="utf-8").read())
    untested = []
    with tempfile.TemporaryDirectory(prefix="agentify-mutate-") as tmp:
        scratch = os.path.join(tmp, "repo")
        shutil.copytree(ROOT, scratch, ignore=shutil.ignore_patterns(".git", "__pycache__", "results"))
        for rel in COPIES:
            path = os.path.join(scratch, rel)
            text = open(path, encoding="utf-8").read()
            assert HOOK in text, f"{rel}: Report.check signature changed; update HOOK in tests/mutate_checks.py"
            open(path, "w", encoding="utf-8").write(text.replace(HOOK, HOOK + f"        if name.startswith(__import__('os').environ.get('NEUTRALISE', {NONE!r})): cond = True\n", 1))
        assert suite_passes(scratch, NONE), "the suite must pass before any check is switched off"
        for name in names:
            caught = not suite_passes(scratch, name)
            print(("  caught     " if caught else "  NOT CAUGHT ") + name)
            if not caught:
                untested.append(name)
    print(f"{len(names) - len(untested)} of {len(names)} checks have a break-it test")
    sys.exit(1 if untested else 0)


if __name__ == "__main__":
    main()
