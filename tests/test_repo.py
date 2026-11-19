import json
import os
import re
import unittest

from _load import ROOT
from india import config

SKILLS = ["swing-scanner", "swing-news", "swing-entry", "swing-exit", "swing-timemachine", "swing-budget",
          "swing-risk", "swing-card", "swing-alerts"]
ABOUT = ("9 Claude skills for swing trading Indian stocks: scan NSE charts, track news and results, plan entry, "
         "stop and target, replay the odds, size in rupees, and print a trade card you place yourself.")


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv", ".superpowers", "trader")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml")) or f == "LICENSE":
                yield os.path.join(base, f)


def python_files():
    for folder in SKILLS + ["india"]:
        for f in sorted(os.listdir(os.path.join(ROOT, folder))):
            if f.endswith(".py"):
                yield folder, f, os.path.join(ROOT, folder, f)


class Repo(unittest.TestCase):
    def test_nine_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_root_entries(self):
        root = sorted(d for d in os.listdir(ROOT)
                      if d != ".git" and d not in (".venv", ".superpowers", "trader", ".DS_Store"))
        self.assertEqual(root, sorted([".claude-plugin", ".gitignore", "LICENSE", "README.md", "docs", "india",
                                       "requirements-nse.txt", "tests"] + SKILLS))

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertRegex(fm, r"description: ", s)
            self.assertGreater(len(fm), 200, "%s description is too thin" % s)
            self.assertGreater(len(text.splitlines()), 60, s)

    def test_every_skill_carries_the_safety_rule(self):
        for s in SKILLS:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("not financial advice", low, s)
            self.assertTrue("never places" in low or "never place" in low, s)

    def test_plugin_manifest(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            plugin = json.load(fh)
        self.assertEqual(plugin["name"], "india-swing-skill")
        self.assertEqual(plugin["skills"], "./")
        self.assertEqual(plugin["description"], ABOUT)
        self.assertEqual(plugin["repository"], "https://github.com/Ibrahimhass/day-trader-skill")
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            market = json.load(fh)
        self.assertEqual(market["plugins"][0]["name"], "india-swing-skill")

    def test_readme(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = " ".join(fh.read().split())
        self.assertTrue(readme.startswith("# India Swing skill"))
        for line in (ABOUT, "## Fine print", "pip install -r requirements-nse.txt",
                     "cp -r india swing-* ~/.claude/skills/", "Jake Schincariol", "not financial advice"):
            self.assertIn(line, readme)
        for s in SKILLS:
            self.assertIn("/" + s, readme, s)

    def test_no_em_dashes(self):
        for path in every_text_file():
            rel = os.path.relpath(path, ROOT)
            if rel.startswith(os.path.join("tests", "fixtures")) or rel.startswith("docs"):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                self.assertNotIn(chr(0x2014), fh.read(), rel)

    def test_ampersand_symbols_quoted_in_shell_examples(self):
        # an unquoted & in bash runs the command in the background and cuts the symbol: M&M -> M
        files = [os.path.join(ROOT, "README.md")] + [os.path.join(ROOT, s, "SKILL.md") for s in SKILLS]
        files += [path for _, _, path in python_files()]
        for path in files:
            with open(path, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if "python3 " not in line or "&" not in line:
                        continue
                    outside = re.sub(r"'[^']*'", "", line.split("#")[0])
                    self.assertNotIn("&", outside, "%s:%d %s" % (os.path.relpath(path, ROOT), n, line.strip()))

    def test_python_3_8(self):
        for folder, f, path in python_files():
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            name = "%s/%s" % (folder, f)
            for bad in ("import zoneinfo", "from zoneinfo", ".removeprefix(", ".removesuffix("):
                self.assertNotIn(bad, src, name)
            self.assertNotRegex(src, r"(?m)^\s+match \w+.*:$", name)
            for gen in ("list[", "dict[", "tuple["):
                self.assertNotRegex(src, r"(?<![\w.])%s" % re.escape(gen), name)

    def test_only_nse_source_imports_nse(self):
        for folder, f, path in python_files():
            if (folder, f) == ("india", "nse_source.py"):
                continue
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(src, r"(?m)^\s*(import nse\b|from nse\b)", "%s/%s" % (folder, f))

    def test_no_broker_code(self):
        for folder, f, path in python_files():
            with open(path, encoding="utf-8") as fh:
                src = fh.read().lower()
            for bad in ("kiteconnect", "place_order", "placeorder", "api_key", "access_token"):
                self.assertNotIn(bad, src, "%s/%s" % (folder, f))

    def test_example_config_matches_defaults(self):
        with open(os.path.join(ROOT, "swing-budget", "config.example.json")) as fh:
            self.assertEqual(set(json.load(fh)), set(config.DEFAULTS))


if __name__ == "__main__":
    unittest.main()
