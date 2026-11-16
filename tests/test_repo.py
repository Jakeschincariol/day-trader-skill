import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from _load import ROOT

# v2, the day-trading pack: the eleven folders the reel's repo card shows
SKILLS = ["trader-scanner", "trader-news", "trader-entry", "trader-exit", "trader-timemachine",
          "trader-risk", "trader-budget", "trader-broker", "trader-alerts", "trader-analyst",
          "trader-pelosi"]
ABOUT = ("11 Codex skills for day trading: scan thousands of charts, track breaking news, time every "
         "entry and exit, and replay every outcome before you risk a dollar.")
# skills on the way to an order carry the safety block
ORDER_PATH = ["trader-scanner", "trader-entry", "trader-exit", "trader-timemachine", "trader-budget",
              "trader-pelosi", "trader-risk", "trader-broker", "trader-alerts"]
V1_ONLY = ["trader-copycat", "trader-screener", "trader-tax", "trader-rebalance"]


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_eleven_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT)
                       if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_codex_discovery_links_to_all_eleven_source_folders(self):
        directory = os.path.join(ROOT, ".agents", "skills")
        self.assertEqual(sorted(os.listdir(directory)), sorted(SKILLS))
        for skill in SKILLS:
            link = os.path.join(directory, skill)
            self.assertTrue(os.path.islink(link), skill)
            self.assertEqual(os.path.realpath(link), os.path.join(ROOT, skill))
            self.assertTrue(os.path.isfile(os.path.join(link, "SKILL.md")), skill)

    def test_skills_are_portable_to_another_trading_project(self):
        # Reproduce a personal install, then execute outside the source repo.
        with tempfile.TemporaryDirectory(prefix="codex skills ") as temp:
            installed = os.path.join(temp, "personal", ".agents", "skills")
            project = os.path.join(temp, "trading project")
            os.makedirs(project)
            for skill in SKILLS:
                dest = os.path.join(installed, skill)
                shutil.copytree(os.path.join(ROOT, skill), dest,
                                ignore=shutil.ignore_patterns("__pycache__"))
                tool = next(f for f in os.listdir(dest) if f.endswith(".py"))
                run = subprocess.run([sys.executable, os.path.join(dest, tool), "--help"],
                                     cwd=project, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([
                sys.executable, os.path.join(installed, "trader-entry", "entry.py"),
                "check", "TSLA", "--now", "2026-10-19 10:15", "--write", "--offline",
                os.path.join(ROOT, "tests", "fixtures", "trader-entry", "TSLA-2026-10-19-5m.json")
            ], cwd=project, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            with open(os.path.join(project, "trader", "entry.json")) as fh:
                entry = json.load(fh)
            self.assertEqual(entry["symbol"], "TSLA")
            self.assertFalse(os.path.exists(os.path.join(installed, "trader")))

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertRegex(fm, r"description: ", s)
            self.assertEqual(re.findall(r"^([a-z-]+):", fm, re.M), ["name", "description"], s)
            description = " ".join(fm.split("description: >-", 1)[1].split())
            self.assertLessEqual(len(description), 1024, s)
            self.assertNotIn("CLAUDE_SKILL_DIR", text, s)
            self.assertNotIn("/loop", text, s)
            self.assertIn("not a Codex-provided environment variable", text, s)
            self.assertGreater(len(fm), 200, "%s description is too thin" % s)
            self.assertGreater(len(text.splitlines()), 60, s)

    def test_order_path_skills_carry_the_safety_rule(self):
        for s in ORDER_PATH:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("not financial advice", low, s)
            self.assertIn("yes", low, s)

    def test_no_claude_plugin_installation_is_shipped(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, ".claude-plugin")))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "trader-broker",
                                                     "claude_desktop_config.example.json")))

    def test_readme_documents_codex_installation_and_invocation(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = " ".join(fh.read().split())
        self.assertTrue(readme.startswith("# The Day Trader skill"))
        for line in (ABOUT, "https://github.com/m33ch/day-trader-skill-codex.git",
                     ".agents/skills/", "$HOME/.agents/skills", "## Fine print"):
            self.assertIn(line, readme)
        for skill in SKILLS:
            self.assertIn("$" + skill, readme, skill)
        self.assertNotIn("/plugin install", readme)

    def test_no_em_dashes_and_no_personal_email(self):
        for path in every_text_file():
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            rel = os.path.relpath(path, ROOT)
            if not rel.startswith(os.path.join("tests", "fixtures")):  # fixtures are real data, kept as published
                self.assertNotIn("\u2014", text, rel)
            self.assertNotIn("jakeschincariol" + "@" + "gmail.com", text, rel)  # built, so this file passes too

    def test_no_v1_only_skill_is_left_behind(self):
        for path in every_text_file():
            rel = os.path.relpath(path, ROOT)
            if rel.startswith("tests" + os.sep) or rel == "README.md":
                continue  # the README points v1 users to the v1 commit
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for old in V1_ONLY:
                self.assertNotIn(old, text, rel)

    def test_every_tool_runs_on_python_3_8(self):
        # no 3.9+ only modules or syntax in the tools (the README promises 3.8)
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in os.listdir(folder):
                if not f.endswith(".py"):
                    continue
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    src = fh.read()
                for bad in ("import zoneinfo", "from zoneinfo", ".removeprefix(", ".removesuffix(",
                            "match ", "list[", "dict[", "tuple["):
                    if bad == "match ":
                        self.assertNotRegex(src, r"(?m)^\s+match \w+.*:$", "%s/%s" % (s, f))
                    elif bad.endswith("["):
                        self.assertNotRegex(src, r"(?<![\w.])%s" % re.escape(bad), "%s/%s" % (s, f))
                    else:
                        self.assertNotIn(bad, src, "%s/%s" % (s, f))

    def test_day_trading_limits_ship_in_the_example_config(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            cfg = json.load(fh)
        for k in ("max_loss_per_trade_usd", "max_daily_loss_usd", "max_trades_per_day",
                  "min_reward_risk", "require_stop", "no_entries_after", "flat_by"):
            self.assertIn(k, cfg, k)
        self.assertIs(cfg["require_stop"], True)
        self.assertIs(cfg.get("allow_short", False), False)
        self.assertIs(cfg.get("allow_margin", False), False)

    def test_paper_trading_is_the_default(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            cfg = json.load(fh)
        self.assertIs(cfg["paper"], True)
        self.assertIs(cfg.get("allow_options", False), False)


if __name__ == "__main__":
    unittest.main()
