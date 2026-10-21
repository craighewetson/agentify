#!/usr/bin/env python3
"""Build the audit fixture: a small made-up project ("ledgerlite") whose map.tsv passes `agentify check` but is wrong in four rows.

Writes <out>/a (no audit skill) and <out>/b (with it). The four wrong rows and why (the other six are right):
  storage  says SQLite; the code appends JSON lines to a file
  export   says CSV or XLSX; the code only writes CSV
  notify   says cost none; the code sends mail over SMTP (network)
  auth     names tests/test_cli.py; the auth tests are in tests/test_auth.py
Run: python3 bench/fixtures/make_audit_fixture.py <out> [--easy|--hard]
--hard: 18 rows, longer files, six subtler wrong rows and bait that only looks wrong (listed in LEVELS['hard'] and the comments on HARD_*).
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCH = os.path.join(ROOT, "archetype")
WRONG = ["storage", "export", "notify", "auth"]

CODE = {
    "parser": 'def parse(line):\n    """\'2026-03-01,coffee,-3.50\' -> (date, memo, cents)."""\n    day, memo, amount = line.split(",")\n    return day, memo, round(float(amount) * 100)\n',
    "storage": 'import json\n\n\ndef append(path, entry):\n    with open(path, "a") as f:\n        f.write(json.dumps(entry) + "\\n")\n\n\ndef load(path):\n    with open(path) as f:\n        return [json.loads(line) for line in f]\n',
    "report": 'def totals_by_month(entries):\n    out = {}\n    for day, memo, cents in entries:\n        out[day[:7]] = out.get(day[:7], 0) + cents\n    return out\n',
    "export": 'import csv\n\n\ndef export(entries, path, fmt="csv"):\n    if fmt != "csv":\n        raise ValueError("only csv is supported")\n    with open(path, "w", newline="") as f:\n        csv.writer(f).writerows(entries)\n',
    "cli": 'import sys\nfrom . import parser, storage\n\n\ndef main(argv):\n    storage.append(argv[1], parser.parse(argv[2]))\n\n\nif __name__ == "__main__":\n    main(sys.argv)\n',
    "auth": 'import hashlib\n\n\ndef check(password, stored_hash):\n    return hashlib.sha256(password.encode()).hexdigest() == stored_hash\n',
    "rates": 'import json\nimport urllib.request\n\n\ndef rate(currency):\n    with urllib.request.urlopen("https://rates.example.invalid/" + currency) as r:\n        return json.load(r)["rate"]\n',
    "notify": 'import smtplib\n\n\ndef overdrawn(address, balance):\n    with smtplib.SMTP("mail.example.invalid") as s:\n        s.sendmail("ledger@example.invalid", address, "Balance is " + str(balance))\n',
    "tags": 'def tag(memo):\n    return [w[1:] for w in memo.split() if w.startswith("#")]\n',
    "search": 'def find(entries, text):\n    return [e for e in entries if text.lower() in e[1].lower()]\n',
}
DESC = {
    "parser": "turn a CSV line into (date, memo, cents)",
    "storage": "keep ledger entries in a SQLite database",
    "report": "monthly totals from a list of entries",
    "export": "write a ledger out as CSV or XLSX",
    "cli": "the ledger command: parse one line and append it to the ledger file",
    "auth": "check a password against a stored SHA-256 hash",
    "rates": "fetch a currency exchange rate from the rates service",
    "notify": "email the owner when the balance goes negative",
    "tags": "pull #hashtags out of a memo",
    "search": "case-insensitive search of entry memos",
}
COST = {"rates": "network", "notify": "none"}
TEST_OF = {"auth": "tests/test_cli.py"}   # the wrong pointer


HARD_CODE = {
    "parser": 'def parse(line):\n    """\'2026-03-01,coffee,-3.50\' -> (date, memo, cents)."""\n    day, memo, amount = line.strip().split(",")\n    return day, memo, to_cents(amount)\n\n\ndef to_cents(text):\n    sign = -1 if text.startswith("-") else 1\n    whole, _, frac = text.lstrip("+-").partition(".")\n    return sign * (int(whole or 0) * 100 + int((frac + "00")[:2]))\n\n\ndef parse_all(lines):\n    return [parse(l) for l in lines if l.strip() and not l.startswith("#")]\n',
    "storage": '"""Ledger storage. Entries live in a SQLite database (one table, `entries`)."""\nimport json\n\n\ndef append(path, entry):\n    with open(path, "a") as f:\n        f.write(json.dumps(entry) + "\\n")\n\n\ndef load(path):\n    try:\n        with open(path) as f:\n            return [json.loads(line) for line in f if line.strip()]\n    except FileNotFoundError:\n        return []\n\n\ndef count(path):\n    return len(load(path))\n',
    "report": 'def totals_by_month(entries):\n    out = {}\n    for day, memo, cents in entries:\n        out[day[:7]] = out.get(day[:7], 0) + cents\n    return out\n\n\ndef biggest(entries, n=3):\n    return sorted(entries, key=lambda e: e[2])[:n]\n\n\ndef balance(entries):\n    return sum(c for _, _, c in entries)\n',
    "export": 'import csv\n\ntry:\n    import openpyxl\nexcept ImportError:\n    openpyxl = None\n\n\ndef export(entries, path, fmt="csv"):\n    if fmt == "xlsx":\n        if openpyxl is None:\n            raise RuntimeError("xlsx needs openpyxl")\n        wb = openpyxl.Workbook()\n        for e in entries:\n            wb.active.append(list(e))\n        wb.save(path)\n    elif fmt == "csv":\n        with open(path, "w", newline="") as f:\n            csv.writer(f).writerows(entries)\n    else:\n        raise ValueError(fmt)\n',
    "cli": 'import sys\nfrom . import parser, storage, report\n\n\ndef main(argv):\n    cmd, path = argv[1], argv[2]\n    if cmd == "add":\n        storage.append(path, parser.parse(argv[3]))\n    elif cmd == "balance":\n        print(report.balance(storage.load(path)))\n    else:\n        sys.exit("usage: ledger add|balance FILE [LINE]")\n\n\nif __name__ == "__main__":\n    main(sys.argv)\n',
    "auth": 'import hashlib\nimport hmac\n\n\ndef digest(password):\n    return hashlib.sha256(password.encode()).hexdigest()\n\n\ndef check(password, stored_hash):\n    return hmac.compare_digest(digest(password), stored_hash)\n',
    "rates": 'import json\nimport time\nimport urllib.request\n\n_cache = {}\n\n\ndef rate(currency, ttl=3600):\n    hit = _cache.get(currency)\n    if hit and time.time() - hit[0] < ttl:\n        return hit[1]\n    value = _fetch(currency)\n    _cache[currency] = (time.time(), value)\n    return value\n\n\ndef _fetch(currency):\n    with urllib.request.urlopen("https://rates.example.invalid/" + currency) as r:\n        return json.load(r)["rate"]\n',
    "notify": 'import json\nimport urllib.request\n\nDEFAULTS = {"webhook": "https://hooks.example.invalid/ledger", "enabled": True}\n\n\ndef overdrawn(balance, cfg=None):\n    cfg = {**DEFAULTS, **(cfg or {})}\n    if balance >= 0 or not cfg["enabled"]:\n        return False\n    req = urllib.request.Request(cfg["webhook"], data=json.dumps({"balance": balance}).encode())\n    urllib.request.urlopen(req)\n    return True\n',
    "tags": 'def tag(memo):\n    return [w[1:] for w in memo.split() if w.startswith("#") and len(w) > 1]\n\n\ndef by_tag(entries):\n    out = {}\n    for e in entries:\n        for t in tag(e[1]):\n            out.setdefault(t, []).append(e)\n    return out\n',
    "search": 'def find(entries, text):\n    return [e for e in entries if text.lower() in e[1].lower()]\n\n\ndef between(entries, first, last):\n    return [e for e in entries if first <= e[0] <= last]\n',
    "retry": 'import time\n\n\ndef with_backoff(fn, tries=4, base=0.5):\n    for n in range(tries):\n        try:\n            return fn()\n        except OSError:\n            if n == tries - 1:\n                raise\n            time.sleep(base * 2 ** n)\n',
    "upload": 'from .retry import with_backoff\n\nMAX_TRIES = 3\n\n\ndef upload(send, blob):\n    """Send a blob with `send`; a failed send is tried again."""\n    return with_backoff(lambda: send(blob), tries=MAX_TRIES)\n',
    "dedupe": 'def key(entry):\n    day, memo, cents = entry\n    return (day, memo.strip().lower(), cents)\n\n\ndef dedupe(entries):\n    seen, out = set(), []\n    for e in entries:\n        if key(e) not in seen:\n            seen.add(key(e))\n            out.append(e)\n    return out\n',
    "importer": 'from . import dedupe, parser, storage\n\n\ndef import_file(src, ledger):\n    existing = storage.load(ledger)\n    for e in dedupe.dedupe(parser.parse_all(open(src))):\n        if e not in existing:\n            storage.append(ledger, e)\n',
    "archive": 'import os\nimport shutil\nimport time\n\n\ndef archive(path, dest):\n    """Move a ledger file out of the way."""\n    shutil.move(path, dest)\n\n\ndef purge(folder, older_than_days):\n    cutoff = time.time() - older_than_days * 86400\n    for name in os.listdir(folder):\n        full = os.path.join(folder, name)\n        if os.path.getmtime(full) < cutoff:\n            os.remove(full)\n',
    "budget": 'def overspent(entries, limits):\n    spent = {}\n    for day, memo, cents in entries:\n        spent[day[:7]] = spent.get(day[:7], 0) + min(cents, 0)\n    return {m: -v for m, v in spent.items() if -v > limits.get(m, float("inf"))}\n',
    "currency": 'from . import rates\n\n\ndef convert(cents, src, dst):\n    return round(cents * rates.rate(src) / rates.rate(dst))\n',
    "schedule": 'import datetime\n\n\ndef due(rules, today):\n    """rules: [(day_of_month, memo, cents)] -> the entries to post today."""\n    return [(today.isoformat(), memo, cents) for dom, memo, cents in rules if dom == today.day]\n\n\ndef next_run(rule, today):\n    first = today.replace(day=rule[0]) if rule[0] >= today.day else (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=rule[0])\n    return first\n',
}
HARD_DESC = {
    "parser": "turn a CSV line into (date, memo, cents)",
    "storage": "append-only JSON-lines ledger file",
    "report": "monthly totals, balance and the biggest entries",
    "export": "write a ledger as CSV, or as XLSX when openpyxl is installed",
    "cli": "the ledger command: add a line or print the balance",
    "auth": "check a password against a stored SHA-256 hash",
    "rates": "exchange rates from the rates service, cached for an hour",
    "notify": "tell the owner about a negative balance; local only, sends nothing",
    "tags": "pull #hashtags out of a memo and group entries by tag",
    "search": "memo search and date-range filter",
    "retry": "retry a flaky call with exponential backoff",
    "upload": "send a blob and retry a failed send up to 5 times",
    "dedupe": "drop repeated entries with the same date and memo",
    "importer": "read a CSV file into the ledger, skipping entries already there",
    "archive": "move old ledger files to an archive; never deletes anything",
    "budget": "monthly spending limits and overspend flags",
    "currency": "convert an amount between currencies with the cached rates",
    "schedule": "post recurring entries on their day of the month",
}
HARD_COST = {"rates": "network", "currency": "network", "notify": "none", "upload": "network"}
HARD_TEST_OF = {"retry": "tests/test_dedupe.py", "auth": "tests/test_integration.py"}
HARD_DOC_OF = {"importer": "docs/import.md", "export": "docs/export.md"}

HARD_TESTS = {   # one real assertion per module, so no test column can be faulted as a placeholder
    "parser": "self.assertEqual(parser.parse('2026-03-01,coffee,-3.50'), ('2026-03-01', 'coffee', -350))",
    "storage": "p = tempfile.mktemp(); storage.append(p, ['d', 'm', 1]); self.assertEqual(storage.load(p), [['d', 'm', 1]])",
    "report": "self.assertEqual(report.balance([('d', 'm', 5), ('d', 'n', -2)]), 3)",
    "export": "p = tempfile.mktemp(); export.export([('d', 'm', 1)], p); self.assertIn('d,m,1', open(p).read())",
    "cli": "p = tempfile.mktemp(); cli.main(['x', 'add', p, '2026-03-01,tea,-1.00']); self.assertEqual(len(storage.load(p)), 1)",
    "auth": "self.assertTrue(auth.check('pw', auth.digest('pw'))); self.assertFalse(auth.check('no', auth.digest('pw')))",
    "rates": "rates._cache['EUR'] = (time.time(), 1.1); self.assertEqual(rates.rate('EUR'), 1.1)",
    "notify": "self.assertFalse(notify.overdrawn(-5, {'enabled': False}))",
    "tags": "self.assertEqual(tags.tag('lunch #work #fun'), ['work', 'fun'])",
    "search": "self.assertEqual(search.find([('d', 'Coffee', 1)], 'coff'), [('d', 'Coffee', 1)])",
    "retry": "calls = []; self.assertEqual(retry.with_backoff(lambda: calls.append(1) or 7), 7)",
    "upload": "self.assertEqual(upload.upload(lambda b: b.upper(), 'x'), 'X')",
    "dedupe": "self.assertEqual(dedupe.dedupe([('d', 'a', 1), ('d', 'A ', 1), ('d', 'a', 2)]), [('d', 'a', 1), ('d', 'a', 2)])",
    "importer": "src, led = tempfile.mktemp(), tempfile.mktemp(); open(src, 'w').write('2026-03-01,tea,-1.00\\n2026-03-01,tea,-1.00\\n'); importer.import_file(src, led); self.assertEqual(len(storage.load(led)), 1)",
    "archive": "d = tempfile.mkdtemp(); f = os.path.join(d, 'a'); open(f, 'w').close(); os.utime(f, (0, 0)); archive.purge(d, 1); self.assertFalse(os.path.exists(f))",
    "budget": "self.assertEqual(budget.overspent([('2026-03-01', 'x', -500)], {'2026-03': 100}), {'2026-03': 500})",
    "currency": "rates._cache.update(EUR=(time.time(), 2.0), USD=(time.time(), 1.0)); self.assertEqual(currency.convert(100, 'EUR', 'USD'), 200)",
    "schedule": "self.assertEqual(schedule.due([(5, 'rent', -100)], datetime.date(2026, 3, 5)), [('2026-03-05', 'rent', -100)])",
}

HARD_EXTRA = {
    "docs/export.md": "# Exporting a ledger\n\n`export(entries, path, fmt)` writes CSV, or XLSX when openpyxl is installed.\n",
    "docs/import.md": "# Exporting a ledger\n\nUse `ledger export FILE out.csv` to write the ledger as CSV.\n",
    "tests/test_integration.py": "import unittest\n\nfrom ledgerlite import auth, parser\n\n\nclass T(unittest.TestCase):\n    def test_auth_round_trip(self):\n        self.assertTrue(auth.check('pw', auth.digest('pw')))\n\n    def test_parse(self):\n        self.assertEqual(parser.parse('2026-03-01,coffee,-3.50')[2], -350)\n",
}
LEVELS = {
    "easy": dict(code=CODE, desc=DESC, cost=COST, test_of=TEST_OF, doc_of={}, extra={}, wrong=WRONG),
    "hard": dict(code=HARD_CODE, desc=HARD_DESC, cost=HARD_COST, test_of=HARD_TEST_OF, doc_of=HARD_DOC_OF, extra=HARD_EXTRA,
                 wrong=["notify", "retry", "upload", "dedupe", "importer", "archive"]),
}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)


def build(dest, with_skill, level):
    L = LEVELS[level]
    for n, body in L["code"].items():
        write(os.path.join(dest, "src", "ledgerlite", n + ".py"), body)
        real = HARD_TESTS.get(n) if level == "hard" else None
        body = real or "self.assertTrue(True)"
        write(os.path.join(dest, "tests", f"test_{n}.py"), f"# tests for ledgerlite.{n}\nimport datetime, os, tempfile, time, unittest\n\nfrom ledgerlite import {n}" + "".join(f", {m}" for m in ("storage", "rates") if real and m in real and m != n) + f"\n\n\nclass T(unittest.TestCase):\n    def test_{n}(self):\n        {body}\n" if real else f"# tests for ledgerlite.{n}\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_{n}(self):\n        self.assertTrue(True)\n")
    for rel, body in L["extra"].items():
        write(os.path.join(dest, rel), body)
    write(os.path.join(dest, "src", "ledgerlite", "__init__.py"), "")
    write(os.path.join(dest, "README.md"), "# ledgerlite\n\nA tiny personal ledger library.\n")
    rows = ["\t".join([n, L["desc"][n], f"src/ledgerlite/{n}.py", "python3 " + L["test_of"].get(n, f"tests/test_{n}.py"), "working-agreements",
                      L["doc_of"].get(n, "README.md"), L["cost"].get(n, "none")]) for n in L["code"]]
    doc_rows = "".join(f"| {rel} | `{rel}` |\n" for rel in sorted(L["extra"]) if rel.startswith("docs/"))
    write(os.path.join(dest, "map.tsv"), "# project map: one row per area.\n# stack: Python 3 standard library only\n# rules: none beyond the table in CLAUDE.md\nid\tarea\tcode\ttest\tskill\tdoc\tcost\n" + "\n".join(rows) + "\n")
    write(os.path.join(dest, "CLAUDE.md"), "# ledgerlite\n\nA tiny personal ledger library.\n\n## Find things fast\n\n`tools/where.py <words>` searches `map.tsv`.\n\n"
          "## Rules\n\n| Rule | Backed by |\n|---|---|\n| Keep the index true. | `tests/check_map.py` |\n\n## Reference docs\n\n| Topic | File |\n|---|---|\n| About | `README.md` |\n" + doc_rows)
    write(os.path.join(dest, ".agentify.json"), '{"must_be_mapped": ["src/*"]}\n')
    for rel in ("tools/where.py", "tests/check_map.py", ".claude/skills/working-agreements/SKILL.md") + ((".claude/skills/audit-map/SKILL.md",) if with_skill else ()):
        os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(ARCH, rel), os.path.join(dest, rel))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    level = next((a[2:] for a in sys.argv[1:] if a in ("--easy", "--hard")), "easy")
    out = os.path.abspath(args[0])
    for arm, skill in (("a", False), ("b", True)):
        shutil.rmtree(os.path.join(out, arm), ignore_errors=True)
        build(os.path.join(out, arm), skill, level)
        r = subprocess.run([sys.executable, os.path.join(out, arm, "tests", "check_map.py"), "--root", os.path.join(out, arm), "--strict"], capture_output=True, text=True)
        assert r.returncode == 0, "the fixture's map must pass the check, or it proves nothing:\n" + r.stdout
    print(f"wrote {out}/a (no skill) and {out}/b (audit-map skill) [{level}]; both pass `check --strict` and these rows are wrong: {', '.join(LEVELS[level]['wrong'])}")


if __name__ == "__main__":
    main()
