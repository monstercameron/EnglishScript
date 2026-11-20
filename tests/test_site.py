"""The newer pages of the site in docs/, and what they load.

tests/test_englishscript.py (ProjectPage) covers the treatise, the playground,
the grammar and the bundled compiler. This file covers what came after: the
page written in English, the comparison with JavaScript and Java, the page
library's document, the books a program in the browser can use, the loaders
and the motion.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "tools"))
import build_site  # noqa: E402

REBUILD = "run: python tools/build_site.py"
PAGES = ("index.html", "playground.html", "todo.html", "compare.html", "reference.html", "how.html",
         "vulkan.html", "page.html", "concerns.html", "editors.html", "opposition.html")


def read(name):
    return (DOCS / name).read_text(encoding="utf-8")


class WhatTheSiteServes(unittest.TestCase):
    def test_every_page_has_the_same_way_round_and_links_only_to_what_exists(self):
        for name in PAGES:
            with self.subTest(name):
                page = read(name)
                self.assertIn("assets/english.css", page)
                nav = re.search(r'<nav class="sitenav".*?</nav>', page, re.S).group(0)
                links = re.findall(r'<a class="page" href="([^"]+)"', nav)
                self.assertEqual(links[:7], ["./", "playground.html", "todo.html", "compare.html", "opposition.html",
                                             "reference.html", "how.html"])
                for target in re.findall(r'(?:href|src)="([^"#]+)(?:#[^"]*)?"', page):
                    if target.startswith(("http://", "https://", "data:")):
                        continue
                    local = DOCS / ("index.html" if target == "./" else target)
                    self.assertTrue(local.is_file(), f"{name} links to {target}, which is not there")
                for anchor in re.findall(r'href="#([^"]+)"', page):
                    self.assertIn(f'id="{anchor}"', page, f"{name} links to #{anchor}, which is not on the page")

    def test_the_pages_printed_from_markdown_are_current(self):
        for name, make in build_site.PRINTED:
            with self.subTest(name):
                self.assertEqual(read(name), make(), REBUILD)

    def test_every_program_printed_on_a_page_shows_what_the_compiler_says(self):
        for name in build_site.WRITTEN:
            with self.subTest(name):
                page = read(name)
                self.assertTrue(build_site.SNIPPET.findall(page))
                # render_page runs each one, and stops if one marked "ok" is refused or the reverse.
                self.assertEqual(build_site.render_page(page), page, REBUILD)

    def test_the_comparison_shows_refusals_and_results(self):
        page = read("compare.html")
        programs = build_site.SNIPPET.findall(page)
        self.assertEqual(sum(1 for _, expect, *_ in programs if expect == "refused"), 5)
        self.assertEqual(sum(1 for _, expect, *_ in programs if expect == "ok"), 2)
        self.assertIn("0.1 + 0.2 is 0.3.", page)
        self.assertIn("Ada has $900 and Bo has $340.", page)
        for language in ("js", "java"):
            self.assertIn(f'<pre class="code {language}">', page)

    def test_what_the_pages_fetch_is_current(self):
        for name in build_site.COPIES:
            with self.subTest(name):
                self.assertEqual((DOCS / "play" / name).read_text(encoding="utf-8"), build_site.copy_text(name), REBUILD)
        self.assertEqual((DOCS / "play" / "shelf.json").read_text(encoding="utf-8"), build_site.shelf_text(), REBUILD)
        page = read("todo.html")
        self.assertIn('const MAIN = "web_todo.english";', page)
        self.assertIn('fetch("play/shelf.json")', page)
        # Every file the page shows as a tab is the program or a chapter on the shelf.
        shelf = json.loads((DOCS / "play" / "shelf.json").read_text(encoding="utf-8"))
        for name in re.findall(r'"(tasks/\w+\.english)":', page):
            self.assertIn(name, shelf)

    def test_the_shelf_holds_every_chapter_a_bundled_example_uses(self):
        shelf = json.loads((DOCS / "play" / "shelf.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(shelf), [
            "almanac/calendar.english", "almanac/feasts.english", "almanac/numerals.english",
            "tasks/cards.english", "tasks/keeping.english", "tasks/layout.english", "tasks/showing.english"])
        examples = json.loads((DOCS / "play" / "examples.json").read_text(encoding="utf-8"))
        for example in examples:
            for chapter, book in re.findall(r"^Use the ([a-z ]+) chapter of the ([a-z ]+) book\.", example["source"], re.M):
                self.assertIn(f"{book.replace(' ', '_')}/{chapter.replace(' ', '_')}.english", shelf, example["id"])
            # A chapter beside the program would have to be a loose file, and those are cleared between runs.
            self.assertNotRegex(example["source"], r"(?m)^Use the [a-z ]+ chapter\.", example["id"])

    def test_every_bundled_example_is_a_program_in_the_repository(self):
        examples = json.loads((DOCS / "play" / "examples.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(examples), 20)
        for example in examples:
            with self.subTest(example["id"]):
                source = (ROOT / "examples" / f"{example['id']}.english").read_text(encoding="utf-8")
                self.assertEqual(example["source"], source.replace("\r\n", "\n"), REBUILD)


class TheEngine(unittest.TestCase):
    """docs/play/engine.js: what the pages ask of it is there."""

    engine = read("play/engine.js")

    def test_it_exports_what_the_pages_import(self):
        exported = set(re.findall(r"export (?:async )?(?:function|const) (\w+)", self.engine))
        for name in PAGES + ("play/snippets.js",):
            for names in re.findall(r'import \{([^}]*)\} from "\./(?:play/)?engine\.js"', read(name)):
                for wanted in (word.strip() for word in names.split(",")):
                    self.assertIn(wanted, exported, f"{name} imports {wanted}")

    def test_the_download_it_measures_is_the_one_it_loads(self):
        version = re.search(r"cdn\.jsdelivr\.net/pyodide/v(\d+\.\d+\.\d+)/full/", self.engine)
        self.assertTrue(version, "the Pyodide version is pinned")
        files = re.findall(r'\["([\w.\-]+)", (\d+)\]', self.engine)
        self.assertEqual([name for name, _ in files],
                         ["pyodide.asm.wasm", "python_stdlib.zip", "pyodide.asm.js", "pyodide-lock.json"])
        self.assertTrue(all(int(size) > 100_000 for _, size in files))

    def test_it_never_waits_only_on_a_frame(self):
        # A page in a background tab draws no frames, so a wait for one needs a way out.
        waits = re.findall(r"requestAnimationFrame", self.engine)
        self.assertEqual(len(waits), 1)
        self.assertIn("setTimeout(resolve, 150)", self.engine)
        self.assertNotIn("requestAnimationFrame", read("todo.html"))

    def test_the_bridge_is_python_that_compiles(self):
        bridge = re.search(r"const BRIDGE = `(.*?)`;", self.engine, re.S).group(1)
        code = compile(bridge, "bridge", "exec")
        self.assertIn("play", code.co_names)
        for function in ("def play(", "def check(", "def stock("):
            self.assertIn(function, bridge)

    def test_the_to_do_page_s_bridge_is_python_that_compiles(self):
        bridge = re.search(r"const BRIDGE = `(.*?)`;", read("todo.html"), re.S).group(1)
        compile(bridge, "bridge", "exec")
        self.assertIn("def open_page(", bridge)


class TheStyleSheet(unittest.TestCase):
    css = read("assets/english.css")

    def test_whatever_moves_can_be_stilled(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        still = self.css[self.css.rindex("@media (prefers-reduced-motion: reduce)"):]
        self.assertIn("animation-duration: 0.01ms !important", still)
        self.assertIn("transition-duration: 0.01ms !important", still)
        # Every animation that is used has its keyframes, and the other way about.
        used = set(re.findall(r"animation(?:-name)?:\s*([a-z][\w-]*)", self.css)) - {"none"}
        for page in ("todo.html", "compare.html"):
            used |= set(re.findall(r"animation(?:-name)?:\s*([a-z][\w-]*)", read(page))) - {"none"}
        made = set(re.findall(r"@keyframes ([\w-]+)", self.css))
        for page in ("todo.html",):
            made |= set(re.findall(r"@keyframes ([\w-]+)", read(page)))
        self.assertEqual(used - made, set(), "an animation with no keyframes")
        self.assertEqual(made - used, set(), "keyframes that nothing uses")

    def test_the_page_library_s_elements_are_dressed(self):
        from englishscript.libraries import page

        made = set(re.findall(r'element\("\w+", "(es-[\w-]+)"', (ROOT / "englishscript" / "libraries" / "page.py").read_text(encoding="utf-8")))
        self.assertGreaterEqual(len(made), 12)
        for name in made:
            self.assertIn("." + name, self.css, f"the page library makes {name}, which has no style")
        self.assertEqual(page.MOUNT, "englishscript-page")
        for name in ("todo.html", "playground.html"):
            self.assertIn(f'id="{page.MOUNT}"', read(name))


if __name__ == "__main__":
    unittest.main()
