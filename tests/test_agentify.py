"""agentify's own tests: every rule is proved by breaking a scratch project on purpose. Run: python3 -m unittest discover tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin", "agentify")
sys.path.insert(0, os.path.join(ROOT, "src"))
from agentify import bench, scaffold, scan  # noqa: E402


def agentify(*args):
    r = subprocess.run([sys.executable, BIN, *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def rd(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(root, rel, text=""):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def fill_todos(root):
    """What the agent does after init: describe the areas, fill the placeholders."""
    for rel in ("CLAUDE.md", "map.tsv"):
        p = os.path.join(root, rel)
        t = open(p, encoding="utf-8").read().replace("TODO", "done")
        open(p, "w", encoding="utf-8").write(t)


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="agentify-test-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.p = os.path.join(self.d, "demo")
        write(self.p, "package.json", json.dumps({"scripts": {"test": "jest"}}))
        write(self.p, "src/web/index.js", "x")
        write(self.p, "src/api/server.js", "x")
        write(self.p, "tests/a.test.js", "x")
        write(self.p, "README.md", "# demo\n")


class ScanTests(Base):
    def test_detects_stack_test_command_and_areas(self):
        s = scan.scan(self.p)
        self.assertIn("Node (package.json)", s["stack"])
        self.assertEqual(s["test_command"], "npm test")
        self.assertEqual({a["dir"] for a in s["areas"] if a["kind"] == "source"}, {"src/web", "src/api"})
        self.assertEqual([a["dir"] for a in s["areas"] if a["kind"] == "test"], ["tests"])

    def test_maven_and_python_and_odin(self):
        for manifest, label, cmd in (("pom.xml", "Java (Maven)", "mvn test"), ("Cargo.toml", "Rust (Cargo)", "cargo test"),
                                     ("go.mod", "Go (modules)", "go test ./..."), ("main.odin", "Odin", "odin test .")):
            d = os.path.join(self.d, manifest)
            write(d, manifest, "x")
            s = scan.scan(d)
            self.assertIn(label, s["stack"])
            self.assertEqual(s["test_command"], cmd)

    def test_reports_existing_claude_md_and_biggest_sections(self):
        write(self.p, "CLAUDE.md", "# t\n## small\na\n## big\n" + "line\n" * 50)
        s = scan.scan(self.p)
        self.assertEqual(s["claude_md"]["lines"], 55)
        self.assertTrue(s["biggest_sections"][0][0].endswith("big"))

    def test_a_group_directory_with_its_own_files_is_an_area_too(self):
        # a Rust or Go crate: src/*.rs are the code, src/static is only one subdirectory
        d = os.path.join(self.d, "crate")
        write(d, "Cargo.toml", "[package]")
        write(d, "src/main.rs", "fn main() {}")
        write(d, "src/lib.rs", "")
        write(d, "src/static/index.html", "x")
        dirs = {a["dir"]: a for a in scan.scan(d)["areas"]}
        self.assertIn("src", dirs)
        self.assertEqual(dirs["src"]["lang"], "Rust")
        self.assertIn("src/static", dirs)
        self.assertEqual({a["dir"] for a in scan.scan(self.p)["areas"] if a["dir"].startswith("src")}, {"src/web", "src/api"})

    def test_skips_noise_directories(self):
        write(self.p, "node_modules/x/a.js", "x")
        self.assertNotIn("node_modules", [a["dir"] for a in scan.scan(self.p)["areas"]])

    def test_json_output_is_valid(self):
        code, out = agentify("scan", "--json", self.p)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["name"], "demo")


class InitTests(Base):
    def test_writes_the_layout_and_drafts_rows_from_the_scan(self):
        code, _ = agentify("init", self.p)
        self.assertEqual(code, 0)
        for rel in ("CLAUDE.md", "map.tsv", "tools/where.py", "tests/check_map.py", ".claude/skills/working-agreements/SKILL.md", ".agentify.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.p, rel)), rel)
        rows = rd(os.path.join(self.p, "map.tsv"))
        self.assertIn("src-web\t", rows)
        self.assertIn("npm test", rows)
        self.assertEqual(json.loads(rd(os.path.join(self.p, ".agentify.json")))["must_be_mapped"], ["src/*"])

    def test_never_overwrites_and_is_idempotent(self):
        write(self.p, "CLAUDE.md", "mine\n")
        agentify("init", self.p)
        self.assertEqual(rd(os.path.join(self.p, "CLAUDE.md")), "mine\n")
        before = rd(os.path.join(self.p, "map.tsv"))
        write(self.p, "map.tsv", before + "# edited\n")
        code, out = agentify("init", self.p)
        self.assertEqual(code, 0)
        self.assertIn("# edited", rd(os.path.join(self.p, "map.tsv")))
        self.assertIn("kept   CLAUDE.md", out)

    def test_a_new_project_gets_an_empty_style_guide_that_the_root_lists(self):
        agentify("init", self.p)
        self.assertTrue(os.path.isfile(os.path.join(self.p, "docs", "style.md")))
        self.assertIn("`docs/style.md`", rd(os.path.join(self.p, "CLAUDE.md")))
        fill_todos(self.p)
        self.assertEqual(agentify("check", "--strict", self.p)[0], 0)

    def test_an_existing_style_guide_is_listed_not_replaced_or_duplicated(self):
        write(self.p, "docs/CODING_STYLE.md", "# Mine\n")
        self.assertEqual(scan.scan(self.p)["style_guides"], ["docs/CODING_STYLE.md"])
        agentify("init", self.p)
        self.assertFalse(os.path.exists(os.path.join(self.p, "docs", "style.md")))
        self.assertEqual(rd(os.path.join(self.p, "docs", "CODING_STYLE.md")), "# Mine\n")
        self.assertIn("`docs/CODING_STYLE.md`", rd(os.path.join(self.p, "CLAUDE.md")))
        fill_todos(self.p)
        self.assertEqual(agentify("check", "--strict", self.p)[0], 0)

    def test_an_existing_root_claude_md_means_no_style_file_is_made_and_the_hint_says_why(self):
        write(self.p, "CLAUDE.md", "mine\n")
        code, out = agentify("init", self.p)
        self.assertFalse(os.path.exists(os.path.join(self.p, "docs", "style.md")))
        self.assertIn("No style guide found", out)
        write(self.p, "CONTRIBUTING.md", "# How\n")
        self.assertIn("Style guide found: CONTRIBUTING.md", agentify("init", self.p)[1])

    def test_dry_run_writes_nothing(self):
        code, out = agentify("init", "--dry-run", self.p)
        self.assertIn("would write map.tsv", out)
        self.assertFalse(os.path.exists(os.path.join(self.p, "map.tsv")))

    def test_the_installed_where_py_answers(self):
        agentify("init", self.p)
        r = subprocess.run([sys.executable, os.path.join(self.p, "tools", "where.py"), "src-web"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("src/web", r.stdout)


class CheckTests(Base):
    def setUp(self):
        super().setUp()
        agentify("init", self.p)
        fill_todos(self.p)

    def run_check(self, *extra):
        return agentify("check", self.p, *extra)

    def test_a_filled_in_project_passes_strictly(self):
        code, out = self.run_check("--strict")
        self.assertEqual(code, 0, out)

    def test_placeholders_warn_but_only_strict_fails(self):
        write(self.p, "map.tsv", rd(os.path.join(self.p, "map.tsv")).replace("done what", "TODO what", 1))
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("warn", out)
        self.assertEqual(self.run_check("--strict")[0], 1)

    def test_a_missing_code_path_fails(self):
        shutil.rmtree(os.path.join(self.p, "src", "web"))
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("src/web", out)

    def test_a_missing_doc_skill_or_test_fails(self):
        t = rd(os.path.join(self.p, "map.tsv"))
        for old, new, needle in (("README.md", "NOPE.md", "doc NOPE.md"), ("working-agreements", "nope-skill", "skill nope-skill"), ("npm test", "scripts/nope.sh", "test scripts/nope.sh")):
            write(self.p, "map.tsv", t.replace(old, new))
            code, out = self.run_check()
            self.assertEqual(code, 1, needle)
            self.assertIn(needle, out)
        write(self.p, "map.tsv", t)

    def test_a_new_source_directory_must_be_mapped(self):
        write(self.p, "src/queue/worker.js", "x")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("src/queue", out)

    def test_a_test_directory_beside_the_sources_needs_no_row(self):
        write(self.p, "src/test/java/AppTest.java", "x")
        self.assertEqual(self.run_check()[0], 0)
        write(self.p, "src/queue/worker.js", "x")
        self.assertEqual(self.run_check()[0], 1)

    def test_an_unused_skill_fails_unless_general(self):
        write(self.p, ".claude/skills/deploy/SKILL.md", "---\nname: deploy\ndescription: d\n---\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("deploy", out)

    def test_the_root_claude_md_budget(self):
        write(self.p, "CLAUDE.md", rd(os.path.join(self.p, "CLAUDE.md")) + "x\n" * 130)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("within 120 lines", out)

    def test_docs_and_scoped_files_must_be_listed_in_the_root(self):
        write(self.p, "docs/extra.md", "x")
        write(self.p, "src/web/CLAUDE.md", "x")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("docs/extra.md", out)
        self.assertIn("src/web/CLAUDE.md", out)

    def test_a_dangling_path_in_the_root_claude_md_fails(self):
        write(self.p, "CLAUDE.md", rd(os.path.join(self.p, "CLAUDE.md")) + "\nSee `docs/gone.md`.\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("docs/gone.md", out)

    def test_no_map_is_a_failure_that_names_the_fix(self):
        os.remove(os.path.join(self.p, "map.tsv"))
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("agentify init", out)

    def test_no_root_claude_md_fails(self):
        os.remove(os.path.join(self.p, "CLAUDE.md"))
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("CLAUDE.md exists at the root", out)

    def test_a_map_with_no_rows_fails(self):
        write(self.p, "map.tsv", "# stack: x\n# rules: y\nid\tarea\tcode\ttest\tskill\tdoc\tcost\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertRegex(out, "FAIL  map.tsv has rows")

    def test_duplicate_ids_fail(self):
        rows = [l for l in rd(os.path.join(self.p, "map.tsv")).split("\n") if l and not l.startswith(("#", "id\t"))]
        write(self.p, "map.tsv", rd(os.path.join(self.p, "map.tsv")).rstrip("\n") + "\n" + rows[0] + "\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("ids are unique   [['" + rows[0].split("\t")[0], out)

    def test_the_scoped_claude_md_budget(self):
        write(self.p, "src/web/CLAUDE.md", "x\n" * 310)
        write(self.p, "CLAUDE.md", rd(os.path.join(self.p, "CLAUDE.md")) + "\nsee `src/web/CLAUDE.md`\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("within 300 lines", out)

    def test_each_placeholder_warning_fails_only_with_strict(self):
        breaks = (
            ("points at the lookup", lambda p: write(p, "CLAUDE.md", rd(os.path.join(p, "CLAUDE.md")).replace("where.py", "lookup"))),
            ("has no TODO placeholders", lambda p: write(p, "CLAUDE.md", rd(os.path.join(p, "CLAUDE.md")) + "\nTODO: fill me\n")),
            ("names the stack and the rules", lambda p: write(p, "map.tsv", rd(os.path.join(p, "map.tsv")).replace("# stack:", "# nothing:"))),
            ("tools/where.py is installed", lambda p: os.remove(os.path.join(p, "tools", "where.py"))),
        )
        for needle, breaker in breaks:
            self.setUp()
            breaker(self.p)
            code, out = self.run_check()
            self.assertEqual(code, 0, needle + "\n" + out)
            self.assertRegex(out, "warn  .*" + needle)
            code, out = self.run_check("--strict")
            self.assertEqual(code, 1, needle + "\n" + out)
            self.assertRegex(out, "FAIL  .*" + needle)

    def rules_md(self, *rows):
        md = rd(os.path.join(self.p, "CLAUDE.md"))
        head = md[:md.index("| Rule | Backed by |")]
        tail = md[md.index("## Layout"):]
        return head + "| Rule | Backed by |\n|---|---|\n" + "".join(f"| {r} | {b} |\n" for r, b in rows) + "\n" + tail

    def test_rules_as_bullets_warn_that_nothing_says_what_backs_them(self):
        md = rd(os.path.join(self.p, "CLAUDE.md"))
        a, b = md.index("| Rule | Backed by |"), md.index("## Layout")
        write(self.p, "CLAUDE.md", md[:a] + "- a rule\n\n" + md[b:])
        self.assertEqual(self.run_check()[0], 0)
        code, out = self.run_check("--strict")
        self.assertEqual(code, 1)
        self.assertRegex(out, "FAIL  the rules in the root CLAUDE.md say what backs each one")

    def test_a_rule_with_nothing_behind_it_warns_and_a_stated_judgment_does_not(self):
        for backing in ("", "none", "TODO: later"):
            write(self.p, "CLAUDE.md", self.rules_md(("Use few dependencies.", backing)))
            self.assertEqual(self.run_check()[0], 0, backing)
            code, out = self.run_check("--strict")
            self.assertEqual(code, 1, backing)
            self.assertRegex(out, "FAIL  every rule is backed by")
        write(self.p, "CLAUDE.md", self.rules_md(("Use few dependencies.", "judgment: fewer CVEs to chase; an exception needs a reason in the PR")))
        self.assertEqual(self.run_check("--strict")[0], 0)

    def test_a_style_guide_section_a_rule_points_at_must_exist(self):
        write(self.p, "CLAUDE.md", self.rules_md(("Few dependencies.", "`docs/style.md#dependencies`")) + "\nStyle: `docs/style.md`\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertRegex(out, r"FAIL  every style-guide section a rule points at exists.*docs/style.md")
        write(self.p, "docs/style.md", "# Style\n\n## Other\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("docs/style.md#dependencies", out)
        write(self.p, "docs/style.md", "# Style\n\n## Dependencies\n")
        self.assertEqual(self.run_check("--strict")[0], 0, self.run_check("--strict")[1])

    def test_a_stale_project_copy_is_reported_and_upgrade_refreshes_it(self):
        own = os.path.join(self.p, "tests", "check_map.py")
        write(self.p, "tests/check_map.py", rd(own) + "# old\n")
        self.assertIn("agentify upgrade", self.run_check()[1])
        self.assertEqual(agentify("upgrade", "--dry-run", self.p)[1].strip(), "would update tests/check_map.py")
        self.assertIn("# old", rd(own))
        agentify("upgrade", self.p)
        self.assertNotIn("# old", rd(own))
        self.assertIn("already current", agentify("upgrade", self.p)[1])

    def test_ignore_paths_exempts_templates(self):
        write(self.p, "templates/CLAUDE.md", "x")
        self.assertEqual(self.run_check()[0], 1)
        cfg = json.loads(rd(os.path.join(self.p, ".agentify.json")))
        cfg["ignore_paths"] = ["templates/"]
        write(self.p, ".agentify.json", json.dumps(cfg))
        self.assertEqual(self.run_check()[0], 0)


class MeasureTests(unittest.TestCase):
    """agentify measure: what loads at the start of a session, in tokens. HOME is a scratch dir so the user's own files never count."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="agentify-measure-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.home = os.path.join(self.d, "home")
        self.p = os.path.join(self.home, "work", "proj")
        write(self.p, "CLAUDE.md", "@docs/shared.md\n# proj\n" + "a" * 400 + "\n")
        write(self.p, "docs/shared.md", "b" * 800)
        write(self.p, "docs/never_loaded.md", "c" * 5000)

    def run_measure(self, *extra, project=None):
        env = dict(os.environ, HOME=self.home)
        r = subprocess.run([sys.executable, BIN, "measure", project or self.p, "--json", *extra], capture_output=True, text=True, env=env)
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else r.stdout + r.stderr)

    def test_counts_the_root_file_and_what_it_imports_but_not_other_docs(self):
        code, m = self.run_measure()
        files = {f["path"]: f for f in m["files"]}
        self.assertEqual(set(files), {"CLAUDE.md", "docs/shared.md"})
        self.assertEqual(files["docs/shared.md"]["bytes"], 800)
        self.assertEqual(m["project_tokens"], m["total_tokens"])

    def test_an_import_cycle_does_not_hang_or_double_count(self):
        write(self.p, "docs/shared.md", "@../CLAUDE.md\nx")
        code, m = self.run_measure()
        self.assertEqual(sorted(f["path"] for f in m["files"]), ["CLAUDE.md", "docs/shared.md"])

    def test_ancestor_user_and_skill_descriptions_count_but_skill_bodies_do_not(self):
        write(self.home, "work/CLAUDE.md", "d" * 240)
        write(self.home, ".claude/CLAUDE.md", "e" * 240)
        write(self.p, ".claude/skills/s/SKILL.md", "---\nname: s\ndescription: does a thing\n---\n" + "body " * 5000)
        code, m = self.run_measure()
        scopes = {f["scope"] for f in m["files"]}
        self.assertTrue({"project", "ancestor", "user", "skills"} <= scopes, scopes)
        skill = next(f for f in m["files"] if f["scope"] == "skills")
        self.assertLess(skill["bytes"], 100)
        self.assertLess(m["project_tokens"], m["total_tokens"])

    def test_budget_fails_when_the_project_is_over(self):
        self.assertEqual(self.run_measure("--budget", "100000")[0], 0)
        code, out = self.run_measure("--budget", "10")
        self.assertEqual(code, 1)

    def test_against_a_git_ref_reports_the_saving(self):
        g = lambda *a: subprocess.run(["git", "-C", self.p, *a], capture_output=True, text=True, check=True)
        g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        write(self.p, "CLAUDE.md", "z" * 9000)
        g("add", "CLAUDE.md"); g("commit", "-qm", "long")
        write(self.p, "CLAUDE.md", "z" * 900)
        g("commit", "-qam", "short")
        before = g("status", "--short").stdout
        code, m = self.run_measure("--against", "HEAD~1")
        self.assertEqual(code, 0, m)
        self.assertLess(m["delta_tokens"], 0)
        self.assertLess(m["saving_percent"], 100)
        self.assertGreater(m["saving_percent"], 80)
        self.assertEqual(g("status", "--short").stdout, before)
        self.assertNotIn(".claude/worktrees", g("worktree", "list").stdout)

    def test_the_text_report_shows_a_table_and_the_calibration(self):
        env = dict(os.environ, HOME=self.home)
        r = subprocess.run([sys.executable, BIN, "measure", self.p], capture_output=True, text=True, env=env)
        self.assertIn("CLAUDE.md", r.stdout)
        self.assertIn("bytes per token", r.stdout)


class BenchTests(unittest.TestCase):
    """agentify bench against a fake claude (tests/fake_claude.py): the plumbing, the grading and the verdict, at no cost."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="agentify-bench-test-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.p = os.path.join(self.d, "proj")
        self.log = os.path.join(self.d, "fake.log")
        self.env = dict(os.environ, AGENTIFY_CLAUDE=os.path.join(HERE, "fake_claude.py"), FAKE_LOG=self.log)
        self.tasks = os.path.join(self.d, "tasks.json")
        with open(self.tasks, "w") as f:
            json.dump({"tasks": [{"id": "t1", "prompt": "where is X?", "must": ["src/x\\.py"], "must_not": ["wrong"]},
                                 {"id": "t2", "prompt": "where is Y?", "must": ["src/y\\.py"]}]}, f)
        os.makedirs(self.p)
        self.g("init", "-q"); self.g("config", "user.email", "t@t"); self.g("config", "user.name", "t")
        self.layout("old", cost="0.050", answer="it is in src/x.py and src/y.py", where=False)
        self.layout("new", cost="0.010", answer="it is in src/x.py and src/y.py", where=True)

    def g(self, *a):
        return subprocess.run(["git", "-C", self.p, *a], capture_output=True, text=True, check=True).stdout

    def layout(self, tag, cost, answer, where):
        write(self.p, "FAKE_COST", cost)
        write(self.p, "FAKE_ANSWER", answer)
        for name in ("FAKE_WHERE",):
            q = os.path.join(self.p, name)
            if where:
                write(self.p, name, "1")
            elif os.path.exists(q):
                os.remove(q)
        self.g("add", "-A"); self.g("commit", "-qm", tag, "--allow-empty"); self.g("tag", "-f", tag)

    def bench(self, *extra, a="old", b="new"):
        r = subprocess.run([sys.executable, BIN, "bench", self.p, "--tasks", self.tasks, "--a", a, "--b", b, "--out", os.path.join(self.d, "out.json"), *extra],
                           capture_output=True, text=True, env=self.env)
        return r.returncode, r.stdout + r.stderr

    def test_dry_run_starts_nothing_and_states_the_worst_case(self):
        code, out = self.bench("--dry-run", "--runs", "3")
        self.assertEqual(code, 0, out)
        self.assertIn("12 headless sessions", out)
        self.assertIn("Worst case", out)
        self.assertFalse(os.path.exists(self.log))

    def test_a_cheaper_correct_layout_is_better_and_the_temp_checkouts_are_cleaned_up(self):
        code, out = self.bench("--runs", "3")
        self.assertEqual(code, 0, out)
        self.assertIn("VERDICT: BETTER", out)
        doc = json.loads(rd(os.path.join(self.d, "out.json")))
        self.assertEqual(len(doc["results"]), 12)
        self.assertTrue(all(r["correct"] for r in doc["results"]))
        self.assertEqual(sum(1 for r in doc["results"] if r["arm"] == "b" and r["where"]), 6)
        self.assertNotIn(".agentify-bench", self.g("worktree", "list"))
        self.assertEqual([x for x in os.listdir(self.d) if x.startswith(".agentify-bench")], [])

    def test_cheaper_in_every_pair_is_not_called_better_when_there_are_too_few_pairs(self):
        code, out = self.bench("--runs", "2")
        self.assertIn("VERDICT: LEANS BETTER: cheaper in 4 of 4 paired runs (sign test p=0.062)", out)
        code, out = self.bench("--runs", "1")
        self.assertIn("LEANS BETTER", out)

    def test_the_result_says_why_an_answer_was_wrong_and_what_the_cache_did(self):
        self.layout("hedge", cost="0.001", answer="src/x.py, but wrong", where=True)
        code, out = self.bench("--runs", "1", b="hedge")
        self.assertIn("not correct: B t1: hit wrong", out)
        self.assertIn("not correct: B t2: missing src/y", out)
        self.assertIn("share of tokens read from the cache", out)
        self.assertIn("change in B's cost per repeat", out)

    def test_cheaper_but_wrong_is_worse(self):
        self.layout("bad", cost="0.001", answer="no idea", where=True)
        code, out = self.bench("--runs", "1", b="bad")
        self.assertIn("VERDICT: WORSE", out)

    def test_not_cheaper_is_not_better(self):
        self.layout("dear", cost="0.500", answer="it is in src/x.py and src/y.py", where=False)
        code, out = self.bench("--runs", "1", b="dear")
        self.assertIn("VERDICT: NOT BETTER", out)

    def test_must_not_fails_an_answer(self):
        self.layout("hedge", cost="0.001", answer="src/x.py and src/y.py, but wrong", where=True)
        code, out = self.bench("--runs", "1", b="hedge")
        self.assertIn("VERDICT: WORSE", out)

    def test_the_total_budget_stops_the_run(self):
        code, out = self.bench("--runs", "5", "--total-budget", "0.10")
        self.assertIn("stopped", out)
        doc = json.loads(rd(os.path.join(self.d, "out.json")))
        self.assertTrue(doc["stopped_early"])
        self.assertLess(len(doc["results"]), 20)

    def test_sessions_are_read_only_and_capped(self):
        self.bench("--runs", "1", "--limit-tasks", "1", "--max-budget-usd", "0.25")
        argv = json.loads(rd(self.log).split("\n")[0])["argv"]
        self.assertIn("--no-session-persistence", argv)
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "0.25")
        self.assertIn("Edit", argv[argv.index("--disallowedTools") + 1])
        self.assertNotIn("Edit", argv[argv.index("--allowedTools") + 1].split(","))

    def test_a_failed_session_counts_as_wrong_not_as_a_crash(self):
        self.layout("broken", cost="0.001", answer="x", where=False)
        write(self.p, "FAKE_FAIL", "1")
        self.g("add", "-A"); self.g("commit", "-qm", "fail"); self.g("tag", "-f", "failing")
        code, out = self.bench("--runs", "1", b="failing")
        self.assertEqual(code, 0, out)
        self.assertIn("VERDICT: WORSE", out)

    def test_report_rerenders_a_saved_result(self):
        self.bench("--runs", "1")
        r = subprocess.run([sys.executable, BIN, "bench", "--report", os.path.join(self.d, "out.json")], capture_output=True, text=True)
        self.assertIn("VERDICT", r.stdout)

    def test_a_directory_can_be_an_arm(self):
        code, out = self.bench("--runs", "1", a=self.p, b=self.p)
        self.assertEqual(code, 0, out)

    def test_an_unknown_ref_is_a_clear_error(self):
        code, out = self.bench("--runs", "1", b="no-such-ref")
        self.assertNotEqual(code, 0)
        self.assertIn("neither a directory nor a git ref", out)


class GradeTests(unittest.TestCase):
    def test_every_must_pattern_has_to_match_and_no_must_not(self):
        task = {"must": ["src/x\\.py", "run_all"], "must_not": ["dunno"]}
        self.assertTrue(bench.grade("see SRC/X.PY and tests/run_all.sh", task))
        self.assertFalse(bench.grade("see src/x.py only", task))
        self.assertFalse(bench.grade("src/x.py run_all, dunno", task))
        self.assertTrue(bench.grade("anything", {}))


def git(root, *args):
    r = subprocess.run(["git", "-C", root, "-c", "user.email=t@t", "-c", "user.name=t", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


class Agentified(Base):
    """demo project, initialised, placeholders filled, committed"""
    def setUp(self):
        super().setUp()
        agentify("init", self.p)
        fill_todos(self.p)
        git(self.p, "init", "-q")
        git(self.p, "add", "-A")
        git(self.p, "commit", "-qm", "start")


class SyncTests(Agentified):
    def test_a_project_in_step_has_nothing_to_do(self):
        code, out = agentify("sync", self.p)
        self.assertEqual(code, 0, out)
        self.assertIn("in sync", out)

    def test_a_new_source_directory_is_listed_with_a_stub_row(self):
        write(self.p, "src/jobs/run.js", "x")
        code, out = agentify("sync", self.p)
        self.assertEqual(code, 1)
        self.assertIn("src/jobs", out)
        self.assertIn("src-jobs<TAB>", out)

    def test_write_appends_the_stub_row_and_check_then_wants_it_described(self):
        write(self.p, "src/jobs/run.js", "x")
        before = rd(os.path.join(self.p, "map.tsv"))
        agentify("sync", "--write", self.p)
        after = rd(os.path.join(self.p, "map.tsv"))
        self.assertTrue(after.startswith(before.rstrip("\n")))
        self.assertIn("src-jobs\t", after)
        self.assertEqual(agentify("check", self.p)[0], 0)
        self.assertEqual(agentify("check", "--strict", self.p)[0], 1)   # the TODO is the agent's to describe
        code, out = agentify("sync", self.p)
        self.assertIn("describe", out)
        self.assertEqual(agentify("sync", "--write", self.p)[0], 1)     # still waiting for the description
        self.assertEqual(rd(os.path.join(self.p, "map.tsv")), after)    # and writing twice adds nothing

    def test_a_dead_path_is_reported_and_never_deleted_for_you(self):
        shutil.rmtree(os.path.join(self.p, "src", "web"))
        before = rd(os.path.join(self.p, "map.tsv"))
        code, out = agentify("sync", "--write", self.p)
        self.assertEqual(code, 1)
        self.assertIn("src/web", out)
        self.assertIn("no longer exists", out)
        self.assertEqual(rd(os.path.join(self.p, "map.tsv")), before)

    def test_a_row_whose_code_changed_since_the_map_was_updated_is_flagged(self):
        write(self.p, "src/api/server.js", "changed")
        git(self.p, "add", "-A")
        git(self.p, "commit", "-qm", "api: add a route")
        code, out = agentify("sync", self.p)
        self.assertEqual(code, 1)
        self.assertIn("src-api", out)
        self.assertIn("api: add a route", out)
        self.assertNotIn("src-web", out)
        # the agent reviews the row and touches the map: no longer stale
        with open(os.path.join(self.p, "map.tsv"), "a", encoding="utf-8") as f:
            f.write("# reviewed\n")
        git(self.p, "add", "-A")
        git(self.p, "commit", "-qm", "map: reviewed")
        self.assertEqual(agentify("sync", self.p)[0], 0)

    def test_uncommitted_edits_to_the_code_count_as_changes(self):
        write(self.p, "src/web/index.js", "edited")
        code, out = agentify("sync", self.p)
        self.assertEqual(code, 1)
        self.assertIn("src-web", out)

    def test_editing_the_map_marks_the_rows_reviewed(self):
        write(self.p, "src/api/server.js", "changed")
        git(self.p, "add", "-A")
        git(self.p, "commit", "-qm", "api: change")
        self.assertEqual(agentify("sync", self.p)[0], 1)
        with open(os.path.join(self.p, "map.tsv"), "a", encoding="utf-8") as f:
            f.write("# looked at it\n")                       # not committed yet
        self.assertEqual(agentify("sync", self.p)[0], 0)

    def test_a_stub_goes_on_its_own_line_even_if_the_map_has_no_final_newline(self):
        p = os.path.join(self.p, "map.tsv")
        text = rd(p).rstrip("\n")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        write(self.p, "src/jobs/run.js", "x")
        agentify("sync", "--write", self.p)
        self.assertTrue(any(l.startswith("src-jobs\t") for l in rd(p).split("\n")))

    def test_without_git_only_the_structural_checks_run(self):
        d = os.path.join(self.d, "nogit")
        shutil.copytree(self.p, d)
        shutil.rmtree(os.path.join(d, ".git"))
        self.assertEqual(agentify("sync", d)[0], 0)

    def test_json_is_a_worklist(self):
        write(self.p, "src/jobs/run.js", "x")
        code, out = agentify("sync", "--json", self.p)
        w = json.loads(out)
        self.assertEqual(w["unmapped"][0]["dir"], "src/jobs")
        self.assertEqual(w["dead"], [])


class HookTests(Agentified):
    def hook(self, *a):
        return agentify("hook", *a, self.p)

    def test_install_blocks_a_commit_that_breaks_the_map_and_allows_a_good_one(self):
        self.assertEqual(self.hook("install")[0], 0)
        write(self.p, "x.txt", "x")
        git(self.p, "add", "x.txt")
        git(self.p, "commit", "-qm", "fine")
        shutil.rmtree(os.path.join(self.p, "src", "api"))
        git(self.p, "add", "-A")
        r = subprocess.run(["git", "-C", self.p, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "break"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("map", r.stdout + r.stderr)

    def test_install_is_idempotent_and_uninstall_removes_only_ours(self):
        self.hook("install")
        self.hook("install")
        hooks = git(self.p, "rev-parse", "--git-path", "hooks").strip()
        path = os.path.join(self.p, hooks, "pre-commit")
        self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(self.hook("uninstall")[0], 0)
        self.assertFalse(os.path.exists(path))

    def test_a_hook_that_is_not_ours_is_left_alone(self):
        hooks = git(self.p, "rev-parse", "--git-path", "hooks").strip()
        path = os.path.join(self.p, hooks, "pre-commit")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write(os.path.dirname(path), "pre-commit", "#!/bin/sh\necho mine\n")
        code, out = self.hook("install")
        self.assertEqual(code, 1)
        self.assertIn("not agentify", out)
        self.assertIn("mine", rd(path))
        self.assertEqual(self.hook("uninstall")[0], 1)
        self.assertIn("mine", rd(path))

    def test_not_a_git_repository_is_a_clear_error(self):
        d = os.path.join(self.d, "plain")
        os.makedirs(d)
        code, out = agentify("hook", "install", d)
        self.assertEqual(code, 1)
        self.assertIn("git", out)


class AuditFixtureTests(Base):
    def test_the_fixture_passes_check_and_sync_yet_four_rows_are_wrong(self):
        """The audit skill is only worth having if the mechanical tools cannot see what it finds."""
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bench", "fixtures", "make_audit_fixture.py"), self.d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for arm in ("a", "b"):
            self.assertEqual(agentify("check", "--strict", os.path.join(self.d, arm))[0], 0)
            self.assertIn("nothing to do", agentify("sync", os.path.join(self.d, arm))[1])
        self.assertFalse(os.path.exists(os.path.join(self.d, "a", ".claude", "skills", "audit-map")))
        self.assertTrue(os.path.isfile(os.path.join(self.d, "b", ".claude", "skills", "audit-map", "SKILL.md")))
        tsv = rd(os.path.join(self.d, "a", "map.tsv"))
        self.assertIn("SQLite", tsv)
        self.assertNotIn("sqlite", rd(os.path.join(self.d, "a", "src", "ledgerlite", "storage.py")).lower())
    def test_the_hard_fixture_also_passes_the_mechanical_tools_and_its_own_tests_run(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "bench", "fixtures", "make_audit_fixture.py"), self.d, "--hard"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a = os.path.join(self.d, "a")
        self.assertIn("nothing to do", agentify("sync", a)[1])
        t = subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", "discover", "tests"], cwd=a, env=dict(os.environ, PYTHONPATH="src"), capture_output=True, text=True)
        self.assertEqual(t.returncode, 0, t.stderr)
        self.assertEqual(len([l for l in rd(os.path.join(a, "map.tsv")).split("\n") if l and not l.startswith(("#", "id\t"))]), 18)


class SelfTest(unittest.TestCase):
    def test_agentify_passes_its_own_check_strictly(self):
        code, out = agentify("check", ROOT, "--strict")
        self.assertEqual(code, 0, out)

    def test_the_project_copy_equals_the_archetype_master(self):
        self.assertEqual(scaffold.upgrade(ROOT, dry_run=True), [])


if __name__ == "__main__":
    unittest.main()
