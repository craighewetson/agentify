#!/usr/bin/env python3
"""A stand-in for `claude -p ... --output-format stream-json`, for the bench tests: costs nothing.
It reads its behaviour from files in the working directory: FAKE_ANSWER (the reply), FAKE_COST (dollars),
FAKE_WHERE (if present: first runs tools/where.py), FAKE_FAIL (if present: exits 1). It logs its argv to $FAKE_LOG."""
import json
import os
import sys

cwd = os.getcwd()
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "cwd": cwd}) + "\n")


def rd(name, default=""):
    p = os.path.join(cwd, name)
    return open(p).read().strip() if os.path.exists(p) else default


if os.path.exists(os.path.join(cwd, "FAKE_FAIL")):
    sys.exit("fake failure")
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s"}))
if os.path.exists(os.path.join(cwd, "FAKE_WHERE")):
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "tools/where.py review page"}}]}}))
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": cwd + "/CLAUDE.md"}}]}}))
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": rd("FAKE_ANSWER", "no answer")}]}}))
cost = float(rd("FAKE_COST", "0.01"))
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": rd("FAKE_ANSWER", "no answer"), "total_cost_usd": cost, "duration_ms": 5, "num_turns": 3,
                  "usage": {"input_tokens": 2, "cache_creation_input_tokens": int(cost * 1e5), "cache_read_input_tokens": 100, "output_tokens": 10}}))
