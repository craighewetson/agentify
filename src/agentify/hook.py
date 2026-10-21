"""A git pre-commit hook that runs the map check, so a commit cannot leave map.tsv wrong."""
import os
import subprocess

MARK = "# agentify-hook"
SCRIPT = f"""#!/bin/sh
{MARK} (installed by `agentify hook install`; remove with `agentify hook uninstall`; skip once with git commit --no-verify)
root=$(git rev-parse --show-toplevel) || exit 0
if [ -f "$root/tests/check_map.py" ]; then
  out=$(python3 "$root/tests/check_map.py" --root "$root" 2>&1)
elif command -v agentify >/dev/null 2>&1; then
  out=$(agentify check "$root" 2>&1)
else
  exit 0
fi
if [ $? -ne 0 ]; then
  echo "$out" | grep -v '^  ok'
  echo "agentify: the map is out of step with the project, so this commit is blocked. Run: agentify sync $root"
  exit 1
fi
"""


def _path(root):
    r = subprocess.run(["git", "-C", root, "rev-parse", "--git-path", "hooks"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return os.path.join(root, r.stdout.strip(), "pre-commit")


def install(root):
    p = _path(root)
    if not p:
        return False, f"agentify hook: {root} is not a git repository"
    if os.path.exists(p) and MARK not in open(p, encoding="utf-8").read():
        return False, f"agentify hook: {p} exists and is not agentify's; add a call to `agentify check` there yourself"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(SCRIPT)
    os.chmod(p, 0o755)
    return True, f"installed {p}"


def uninstall(root):
    p = _path(root)
    if not p:
        return False, f"agentify hook: {root} is not a git repository"
    if not os.path.exists(p):
        return True, "no pre-commit hook installed"
    if MARK not in open(p, encoding="utf-8").read():
        return False, f"agentify hook: {p} is not agentify's; left alone"
    os.remove(p)
    return True, f"removed {p}"
