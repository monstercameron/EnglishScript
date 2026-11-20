import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path

from englishscript.compiler import compile_source
from englishscript.lexer import EnglishError
from englishscript.rename import read_names


class GroupedImports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def write(self, name, text):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_source(self, source):
        result = []
        compile_source(source, self.folder).run(result.append)
        return result

    def test_chapter_separators_and_order(self):
        for name in ("battle", "party", "sound"):
            self.write(name + ".english", f'Say "{name}".\n')
        for listing in ("battle, party, sound", "battle and party and sound", "battle, party and sound", "battle, party, and sound"):
            with self.subTest(listing=listing):
                self.assertEqual(self.run_source(f"Use the {listing} chapters."), ["battle", "party", "sound"])
        self.assertEqual(self.run_source("Use the battle chapter."), ["battle"])

    def test_book_and_multiword_names(self):
        self.write("almanac/calendar.english", 'Say "calendar".\n')
        self.write("almanac/feast_days.english", 'Say "feasts".\n')
        self.assertEqual(self.run_source("Use the calendar, feast days chapters of the almanac book."), ["calendar", "feasts"])

    def test_missing_and_duplicate_point_at_offending_name(self):
        self.write("battle.english", "Say 1.\n")
        for source, target, message in (("Use the battle and absent chapters.", "absent", "no chapter"),
                                         ("Use the battle and battle chapters.", "battle chapters", "already uses")):
            with self.subTest(source=source):
                with self.assertRaises(EnglishError) as caught:
                    compile_source(source, self.folder)
                self.assertIn(message, caught.exception.message)
                self.assertEqual(caught.exception.col, source.index(target))

    def test_visibility_and_cycle(self):
        self.write("a.english", "Let depth be 3.\n")
        self.write("b.english", "Use the a chapter.\nLet width be 2.\n")
        self.assertEqual(self.run_source("Use the b and a chapters.\nSay depth + width."), ["5"])
        with self.assertRaises(EnglishError):
            compile_source("Use the b chapter.\nSay depth.", self.folder)
        self.write("a.english", "Use the b chapter.\n")
        with self.assertRaises(EnglishError) as caught:
            compile_source("Use the a and b chapters.", self.folder)
        self.assertIn("circle", caught.exception.message)

    def test_plural_words_in_names_and_books(self):
        self.write("chapters.english", 'Say "chapters".\n')
        self.write("old_libraries/calendar.english", 'Say "calendar".\n')
        self.write("old_libraries/feasts.english", 'Say "feasts".\n')
        self.assertEqual(self.run_source("Use the chapters chapter."), ["chapters"])
        self.assertEqual(self.run_source("Use the calendar chapter of the old libraries book."), ["calendar"])
        self.assertEqual(self.run_source("Use the calendar and feasts chapters of the old libraries book."), ["calendar", "feasts"])
        self.write("other.english", 'Say "other".\n')
        self.assertEqual(self.run_source("Use the chapters and other chapters."), ["chapters", "other"])

    def test_editor_and_compiler_share_complex_import_grammar(self):
        self.write("star_of_the_book_book/phases_of_the_moon.english", 'Say "moon".\n')
        self.write("star_of_the_book_book/tide_tables.english", 'Say "tides".\n')
        source = "Use the phases of the moon and tide tables chapters of the star of the book book book."
        self.assertEqual(self.run_source(source), ["moon", "tides"])
        uses = read_names(source).uses
        self.assertEqual([(u.words, u.book) for u in uses], [
            (("phases", "of", "the", "moon"), ("star", "of", "the", "book", "book")),
            (("tide", "tables"), ("star", "of", "the", "book", "book"))])
        for sentence, expected in (("Use the chapters chapter.", [("chapters",)]),
                                   ("Use the chapters and other chapters.", [("chapters",), ("other",)])):
            self.assertEqual([u.words for u in read_names(sentence).uses], expected)

    def test_bad_separator_points_to_the_bad_token(self):
        source = "Use the one, , two chapters."
        with self.assertRaises(EnglishError) as caught:
            compile_source(source, self.folder)
        self.assertEqual(caught.exception.col, source.index(",", source.index(",") + 1))

    def test_settle_and_async_ask_match_separate_imports(self):
        self.write("one.english", 'Ask "Name?" and let the caller (text) be the reply.\nSay the caller.\n')
        self.write("two.english", 'Say "second".\n')
        prefix = 'Whenever everything has settled:\n  Say "settled"\n'
        async def run(source):
            out = []
            await compile_source(prefix + source, self.folder).run_async(out=out.append, ask=lambda prompt: "Ada")
            return out
        grouped = asyncio.run(run("Use the one and two chapters."))
        separate = asyncio.run(run("Use the one chapter.\nUse the two chapter."))
        self.assertEqual(grouped, separate)
        self.assertIn("Ada", grouped)

    def test_library_group_and_reactions(self):
        for name, source in (("groupalpha", 'Say "alpha".\n'), ("groupbeta", 'Say "beta".\n')):
            module = types.ModuleType("englishscript.libraries." + name)
            module.SOURCE = source
            sys.modules[module.__name__] = module
            self.addCleanup(sys.modules.pop, module.__name__, None)
        self.assertEqual(self.run_source("Use the groupalpha and groupbeta libraries."), ["alpha", "beta"])
        self.write("one.english", "Say 1.\n")
        self.write("two.english", 'A lamp has a power (number).\nA lamp can be lit.\nThere is a lamp called Glow whose power is 1.\nWhenever a lamp becomes lit:\n  Say "lit"\n')
        program = compile_source("Use the one and two chapters.\nNow Glow is lit.", self.folder)
        self.assertTrue(program.compiler.reactive)
        out = []
        program.run(out.append)
        self.assertEqual(out, ["1", "lit"])


if __name__ == "__main__":
    unittest.main()
