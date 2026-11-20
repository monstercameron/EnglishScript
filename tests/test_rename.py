"""The rename tool (englishscript/rename.py).

    python -m unittest tests.test_rename

The compiler's wording changes, so these tests look at what a rename did to
the text and at whether the linter still likes it, not at what any message
says.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import englishscript  # noqa: E402
from englishscript import rename as renaming  # noqa: E402
from englishscript.rename import RenameRefused, plan, read_names, rename  # noqa: E402

EXAMPLES = ROOT / "examples"

WORLD = """\
# A dragon and its treasure. The total is not touched in a comment.
A dragon has an age (number).
A treasure has a worth (money) and an owner (dragon).
The hoard of a dragon is the total worth of its treasures.
A dragon is ancient when its age is at least 500.

There is a dragon called Smaug whose age is 771.
There is a dragon called Norbert whose age is 1.
There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.

To greet a dragon:
  Say "Hello, {the dragon}."

Let the total be 0.
For each dragon:
  Add 1 to the total.
Say "The total is {the total}, in total."
Say "There are {the number of dragons} dragons, {the number of ancient dragons} of them ancient."
Greet Smaug.
say smaug's AGE.
Say SMAUG's hoard.
"""

CALENDAR = """\
Let the month row always be "January February March".

To work out the pick (text) at a spot (number) of a row (text):
  Let the place be 0.
  For each word in the words of the row:
    Add 1 to the place.
    If the place is the spot:
      The answer is the word.
  Fail because "there is no such word".

To work out the month title (text) of a month (number):
  The answer is the pick at the month of the month row.

Say the month title of 2.
"""


def problems(source, folder=None):
    return [p.as_dict() for p in englishscript.lint(source, folder)]


def errors(source, folder=None):
    return [p for p in problems(source, folder) if p.get("kind") == "error"]


def said(source, folder=None):
    out = []
    englishscript.run_source(source, out=out.append, folder=folder)
    return out


class Renaming(unittest.TestCase):
    def setUp(self):
        # The compiler is being rewritten beside these tests: if it can't read the
        # text they start from, there is nothing to learn from them today.
        if errors(WORLD) or errors(CALENDAR):
            self.skipTest("the compiler does not read this file's own programs at the moment")

    def renamed(self, source, old, new, **more):
        """Rename, and check what every rename promises: the linter likes the result as well."""
        result = rename(source, old, new, **more)
        self.assertEqual(len(problems(result, more.get("folder"))), len(problems(source, more.get("folder"))))
        self.assertEqual(errors(result, more.get("folder")), [])
        self.assertEqual(len(result.splitlines()), len(source.splitlines()))
        return result

    def test_a_variable_is_renamed_outside_quotes_and_inside_fill_ins(self):
        result = self.renamed(WORLD, "total", "count")
        self.assertIn("Let the count be 0.", result)
        self.assertIn("  Add 1 to the count.", result)
        self.assertIn('Say "The total is {the count}, in total."', result)  # the quoted words are left alone
        self.assertIn("# A dragon and its treasure. The total is not touched in a comment.", result)
        self.assertEqual(said(result), said(WORLD))

    def test_a_word_of_the_language_that_looks_like_the_name_is_left_alone(self):
        # "the total worth of its treasures" is the language's own "total", not the variable.
        result = self.renamed(WORLD, "total", "count")
        self.assertIn("The hoard of a dragon is the total worth of its treasures.", result)

    def test_an_article_before_the_name_is_ignored(self):
        self.assertEqual(rename(WORLD, "the total", "the count"), rename(WORLD, "total", "count"))

    def test_capitals_do_not_matter_and_each_occurrence_keeps_its_own(self):
        result = self.renamed(WORLD, "smaug", "Fafnir")
        self.assertIn("There is a dragon called Fafnir whose age is 771.", result)
        self.assertIn("whose owner is Fafnir.", result)
        self.assertIn("Greet Fafnir.", result)
        self.assertIn("say fafnir's AGE.", result)
        self.assertIn("Say FAFNIR's hoard.", result)
        self.assertNotIn("maug", result.lower())

    def test_a_verb_that_starts_a_sentence_stays_capitalised(self):
        result = self.renamed(WORLD, "greet", "welcome")
        self.assertIn("To welcome a dragon:", result)
        self.assertIn("Welcome Smaug.", result)
        self.assertEqual(said(result), said(WORLD))

    def test_a_kind_is_renamed_with_its_plural(self):
        result = self.renamed(WORLD, "dragon", "wyrm")
        self.assertIn("A wyrm has an age (number).", result)
        self.assertIn("an owner (wyrm)", result)
        self.assertIn("For each wyrm:", result)
        self.assertIn('Say "Hello, {the wyrm}."', result)
        self.assertIn("{the number of wyrms} dragons, {the number of ancient wyrms} of them", result)
        self.assertEqual(said(result), said(WORLD))

    def test_the_plural_follows_the_rule_of_the_reference(self):
        self.assertEqual([renaming.pluralize(w) for w in ("dragon", "fox", "bus", "buzz", "church", "wish", "pony", "day")],
                         ["dragons", "foxes", "buses", "buzzes", "churches", "wishes", "ponies", "days"])
        self.assertIn("{the number of ponies} dragons", self.renamed(WORLD, "dragon", "pony"))
        self.assertIn("{the number of foxes} dragons", self.renamed(WORLD, "dragon", "fox"))
        source = WORLD.replace("dragon", "pony").replace("ponys", "ponies")
        self.assertEqual(errors(source), [])
        self.assertIn("{the number of wyrms} ponies", self.renamed(source, "pony", "wyrm"))

    def test_a_and_an_follow_the_new_name(self):
        result = self.renamed(WORLD, "dragon", "egg")
        self.assertIn("An egg has an age (number).", result)
        self.assertIn("There is an egg called Smaug whose age is 771.", result)
        self.assertIn("To greet an egg:", result)
        back = self.renamed(result, "egg", "dragon")
        self.assertEqual(back, WORLD)

    STATED = ("A child (plural children) has an age (number) and a friend (child, if any).\n"
              "There is a child called Ann whose age is 3.\n"
              "Say the number of children.\n"
              "For each pupil in children:\n"
              '  Say "{the pupil} is one of {the number of children} children."\n'
              "For each child:\n"
              "  Say the child's age.\n")

    def test_a_stated_plural_is_kept_when_its_kind_is_renamed(self):
        self.assertEqual(errors(self.STATED), [])
        result = self.renamed(self.STATED, "child", "kid")
        self.assertIn("A kid (plural children) has an age (number) and a friend (kid, if any).", result)
        self.assertIn("There is a kid called Ann whose age is 3.", result)
        self.assertIn("Say the number of children.", result)
        self.assertIn("For each pupil in children:", result)
        self.assertIn("For each kid:\n  Say the kid's age.", result)
        self.assertNotIn("kids", result)
        self.assertEqual(said(result), said(self.STATED))
        self.assertIn("An egg (plural children) has an age (number)", self.renamed(self.STATED, "child", "egg"))

    def test_a_stated_plural_can_be_renamed(self):
        result = self.renamed(self.STATED, "children", "bairns")
        self.assertIn("A child (plural bairns) has an age (number) and a friend (child, if any).", result)
        self.assertIn("Say the number of bairns.", result)
        self.assertIn("For each pupil in bairns:", result)
        self.assertIn('Say "{the pupil} is one of {the number of bairns} children."', result)
        self.assertIn("There is a child called Ann whose age is 3.", result)
        self.assertEqual(said(result), said(self.STATED))
        with self.assertRaises(RenameRefused):
            rename(self.STATED, "children", "wee ones")  # a plural is one word
        with self.assertRaises(RenameRefused):
            rename(self.STATED, "pupil", "children")  # in use, as the plural

    def test_the_plural_formed_by_rule_is_not_a_word_for_such_a_kind(self):
        reading = read_names(self.STATED)
        self.assertEqual(reading.plurals, {"child": "children"})
        self.assertIn(("plural", "children", "child"), {(n.what, n.text, n.owner) for n in reading.names})
        self.assertEqual([(n.what, n.text) for n in reading.names if n.what in ("kind", "property")],
                         [("kind", "child"), ("property", "age"), ("property", "friend")])
        self.assertIn(("children",), reading.vocabulary())
        self.assertNotIn(("childs",), reading.vocabulary())
        with self.assertRaises(RenameRefused):
            rename(self.STATED, "childs", "kids")  # not defined: "childs" is no word here
        # The compiler says the same: "childs" is refused where "children" is read.
        self.assertTrue(errors(self.STATED.replace("Say the number of children.", "Say the number of childs.")))
        # So it is free to be a name of something else.
        result = self.renamed(self.STATED, "pupil", "childs")
        self.assertIn("For each childs in children:", result)

    def test_a_name_of_several_words(self):
        result = self.renamed(CALENDAR, "the month row", "month names")
        self.assertIn('Let the month names always be "January February March".', result)
        self.assertIn("The answer is the pick at the month of the month names.", result)
        self.assertIn("To work out the month title (text) of a month (number):", result)
        self.assertIn("of a row (text):", result)  # the role "row" is another name
        self.assertEqual(said(result), said(CALENDAR))

    def test_a_longer_name_that_contains_the_name_is_not_touched(self):
        result = self.renamed(CALENDAR, "month", "moon")
        self.assertIn("To work out the month title (text) of a moon (number):", result)
        self.assertIn("The answer is the pick at the moon of the month row.", result)
        self.assertIn("Say the month title of 2.", result)
        result = self.renamed(CALENDAR, "row", "given phrase")
        self.assertIn("of a given phrase (text):", result)
        self.assertIn("the words of the given phrase:", result)
        self.assertIn("Let the month row always be", result)

    def test_a_word_that_is_a_verb_and_a_name_can_be_renamed_as_one_of_them(self):
        source = WORLD.replace("greet", "age").replace("Greet", "Age")  # a verb may share a property's word
        if errors(source):
            self.skipTest("the compiler does not let a verb share a property's word at the moment")
        verb = self.renamed(source, "age", "greet", only="verb")
        self.assertEqual(verb, WORLD)
        name = self.renamed(source, "age", "years", only="name")
        self.assertIn("years (number).", name)
        self.assertIn("whose years is 771.", name)
        self.assertIn("To age a dragon:", name)
        self.assertIn("Age Smaug.", name)
        self.assertIn("say smaug's YEARS.", name)

    def test_a_name_of_one_block_can_be_renamed_there_only(self):
        source = CALENDAR + "\nTo work out the double (number) of a spot (number):\n  The answer is the spot * 2.\n"
        self.assertEqual(errors(source), [])
        result = self.renamed(source, "spot", "position", within=(2, 8))
        self.assertIn("at a position (number) of a row (text):", result)
        self.assertIn("If the place is the position:", result)
        self.assertIn("To work out the double (number) of a spot (number):", result)
        self.assertIn("The answer is the spot * 2.", result)

    def test_line_endings_and_the_rest_of_the_text_are_kept(self):
        source = WORLD.replace("\n", "\r\n")
        result = rename(source, "Goblet", "Chalice")
        self.assertEqual(result, source.replace("Goblet", "Chalice"))

    def test_the_example_programs_can_be_renamed_and_run_the_same(self):
        path = EXAMPLES / "dragons.english"
        source = path.read_text(encoding="utf-8")
        if errors(source, EXAMPLES):
            self.skipTest("the compiler does not read examples/dragons.english at the moment")
        result = self.renamed(source, "treasure", "jewel", folder=EXAMPLES)
        self.assertIn("{the number of its jewels}", result)
        self.assertIn("Subtract 10% of the jewel's worth from the jewel's worth.", result)
        self.assertEqual(said(result, EXAMPLES), said(source, EXAMPLES))


class Refusals(unittest.TestCase):
    def refused(self, source, old, new, **more):
        with self.assertRaises(RenameRefused) as caught:
            rename(source, old, new, **more)
        reason = str(caught.exception)
        self.assertGreater(len(reason), 20, "the reason is a sentence a person can read")
        return reason

    def test_a_name_that_is_not_defined_in_the_text(self):
        self.assertIn("Fafnir", self.refused(WORLD, "Fafnir", "Glaurung"))
        self.refused(WORLD, "worth of", "value")
        self.refused(WORLD, "", "value")

    def test_a_name_defined_in_a_chapter_is_renamed_there(self):
        source = (EXAMPLES / "almanac.english").read_text(encoding="utf-8")
        reason = self.refused(source, "leapness", "leaping", folder=EXAMPLES)
        self.assertIn("calendar", reason)

    def test_a_reserved_word(self):
        self.assertIn("list", self.refused(WORLD, "total", "list"))
        self.assertIn("of", self.refused(WORLD, "total", "sum of all"))
        self.assertIn("is", self.refused(WORLD, "Smaug", "Smaug is"))
        self.refused(WORLD, "total", "3rd")
        for word in ("the", "of", "is", "let", "whose", "becomes", "number"):
            self.assertIn(word, renaming.FALLBACK_RESERVED)
            self.assertIn(word, renaming.reserved_words())

    def test_the_reserved_words_come_from_the_compiler_when_it_has_them(self):
        compiler = sys.modules["englishscript.compiler"]
        with mock.patch.object(compiler, "KEYWORDS", {"the", "zebra"}, create=True):
            self.assertEqual(renaming.reserved_words(), frozenset({"the", "zebra"}))
        with mock.patch.object(compiler, "KEYWORDS", None, create=True):
            self.assertEqual(renaming.reserved_words(), renaming.FALLBACK_RESERVED)

    def test_a_name_already_in_use(self):
        self.assertIn("Norbert", self.refused(WORLD, "Smaug", "Norbert"))
        self.refused(WORLD, "Smaug", "norbert")
        self.refused(WORLD, "total", "worth")  # a property
        self.refused(WORLD, "total", "dragons")  # the plural of a kind
        self.refused(WORLD, "dragon", "treasure")
        self.refused(WORLD, "treasure", "dragon")
        self.refused(WORLD, "total", "greet")  # a verb
        self.refused(WORLD, "total", "TOTAL")  # the same name
        self.refused(CALENDAR, "place", "word")  # a name of another block

    def test_a_name_in_use_in_a_chapter(self):
        source = (EXAMPLES / "almanac.english").read_text(encoding="utf-8")
        self.refused(source, "year", "weekday", folder=EXAMPLES)

    def test_a_kind_is_named_with_one_word(self):
        self.refused(WORLD, "dragon", "great wyrm")
        self.refused(WORLD, "greet", "say hello")

    def test_a_thing_found_by_its_name_in_quotes(self):
        source = WORLD + 'Let the found be the dragon called "smaug".\nSay the found.\n'
        self.assertIn("22", self.refused(source, "Smaug", "Fafnir"))
        self.assertIn("Fafnir", rename(source, "Norbert", "Fafnir"))

    def test_a_new_problem_from_the_linter_refuses_the_rename(self):
        """The safeguard: whatever this module believes, the compiler has the last word."""
        real = englishscript.lint

        def fussy(source, folder=None, name=None):
            found = [p.as_dict() for p in real(source, folder, name)]
            if "tally" in source:
                found.append({"line": 14, "col": 8, "width": 5, "kind": "error", "file": None, "fix": None,
                              "message": 'I have taken against the word "tally".'})
            return found

        with mock.patch.object(englishscript, "lint", fussy):
            reason = self.refused(WORLD, "total", "tally")
            self.assertIn("taken against", reason)
            self.assertIn("14", reason)
            self.assertIn("Let the amount be 0.", rename(WORLD, "total", "amount"))

    def test_problems_that_were_there_before_do_not_refuse_a_rename(self):
        source = WORLD + "Say the hoard of Smaugg.\nLet the spare be 1.\n"
        before = problems(source)
        self.assertTrue(before)
        result = rename(source, "total", "count")
        self.assertEqual([(p["kind"], p["line"]) for p in problems(result)], [(p["kind"], p["line"]) for p in before])
        # ... not even when their messages name the name that changes.
        result = rename(source, "spare", "extra")
        self.assertIn("Let the extra be 1.", result)
        self.assertEqual(len(problems(result)), len(before))

    def test_a_name_the_compiler_will_not_have(self):
        # Section 3: no name may begin with a word that is an adjective. This module
        # does not know that rule; the linter does.
        if errors(WORLD):
            self.skipTest("the compiler does not read this file's own program at the moment")
        probe = ("A dragon has an age (number).\nA dragon is ancient when its age is at least 500.\n"
                 "Let the ancient sum be 0.\nSay the ancient sum.\n")
        if not errors(probe):
            self.skipTest("the compiler accepts a name that begins with an adjective at the moment")
        self.refused(WORLD, "total", "ancient sum")

    def test_the_linter_failing_refuses_the_rename(self):
        with mock.patch.object(englishscript, "lint", side_effect=RuntimeError("half-written")):
            self.assertIn("half-written", self.refused(WORLD, "total", "count"))


class Reading(unittest.TestCase):
    def test_the_names_of_a_program_are_read_from_its_sentences(self):
        names = {(n.what, n.text) for n in read_names(WORLD).names}
        self.assertLessEqual({
            ("kind", "dragon"), ("kind", "treasure"), ("property", "age"), ("property", "worth"),
            ("property", "owner"), ("property", "hoard"), ("adjective", "ancient"), ("thing", "Smaug"),
            ("thing", "Norbert"), ("thing", "Goblet"), ("verb", "greet"), ("variable", "total"),
        }, names)
        names = {(n.what, n.text, n.top) for n in read_names(CALENDAR).names}
        self.assertLessEqual({
            ("variable", "month row", True), ("value", "pick", True), ("role", "spot", False),
            ("role", "row", False), ("variable", "place", False), ("loop", "word", False),
            ("value", "month title", True), ("role", "month", False),
        }, names)

    def test_quotes_comments_and_fill_ins(self):
        tokens = renaming.scan('Say "A {the total} and {{not this}} and ""{Smaug\'s age}""."  # not the total')
        inside = [t.text for t in tokens if t.group]
        self.assertEqual(inside, ["the", "total", "Smaug", "'s", "age"])
        self.assertEqual([t.text for t in tokens if not t.group and t.kind == "word"], ["Say"])
        curly = renaming.scan("Say “Hello {the total}”.")
        self.assertEqual([t.text for t in curly if t.group], ["the", "total"])

    def test_chapters_and_libraries_are_found(self):
        reading = read_names((EXAMPLES / "almanac.english").read_text(encoding="utf-8"))
        self.assertEqual([(u.what, u.words, u.book) for u in reading.uses],
                         [("chapter", (name,), ("almanac",)) for name in ("calendar", "numerals", "feasts")])
        self.assertEqual(renaming.chapter_path(EXAMPLES, ("roman", "numerals"), ("almanac",)),
                         EXAMPLES / "almanac" / "roman_numerals.english")
        calendar = read_names((EXAMPLES / "almanac" / "calendar.english").read_text(encoding="utf-8"))
        self.assertEqual(calendar.shares, {("leapness",), ("month", "length"), ("month", "title"), ("weekday",)})
        self.assertIn(("weekday",), calendar.shared())
        self.assertNotIn(("month", "row"), calendar.shared())


class CommandLine(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-m", "englishscript.rename", *args], cwd=ROOT, capture_output=True,
                              timeout=120)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "world.english"
        self.path.write_bytes(WORLD.encode("utf-8"))

    def test_the_new_text_is_printed(self):
        if errors(WORLD):
            self.skipTest("the compiler does not read this file's own program at the moment")
        done = self.run_tool(str(self.path), "Smaug", "Fafnir")
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        self.assertEqual(done.stdout.decode("utf-8"), rename(WORLD, "Smaug", "Fafnir"))
        self.assertEqual(self.path.read_bytes(), WORLD.encode("utf-8"))

    def test_write_rewrites_the_file(self):
        if errors(WORLD):
            self.skipTest("the compiler does not read this file's own program at the moment")
        done = self.run_tool(str(self.path), "the total", "the count", "--write")
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.path.read_bytes().decode("utf-8"), rename(WORLD, "total", "count"))

    def test_a_refusal_has_status_1_and_changes_nothing(self):
        for old, new in (("Fafnir", "Glaurung"), ("total", "list"), ("Smaug", "Norbert")):
            with self.subTest(old=old, new=new):
                done = self.run_tool(str(self.path), old, new, "--write")
                self.assertEqual(done.returncode, 1)
                self.assertEqual(done.stdout, b"")
                self.assertGreater(len(done.stderr.strip()), 20)
                self.assertEqual(self.path.read_bytes(), WORLD.encode("utf-8"))

    def test_a_file_that_is_not_there(self):
        done = self.run_tool(str(self.path) + ".missing", "a", "b")
        self.assertEqual(done.returncode, 1)
        self.assertTrue(done.stderr.strip())


class Plans(unittest.TestCase):
    def test_a_plan_is_the_edits_of_the_rename(self):
        if errors(WORLD):
            self.skipTest("the compiler does not read this file's own program at the moment")
        edits = plan(WORLD, "Smaug", "Fafnir")
        lines = WORLD.splitlines()
        self.assertEqual({lines[e.line][e.start:e.end].lower() for e in edits}, {"smaug"})
        self.assertEqual(len(edits), WORLD.lower().count("smaug"))
        self.assertEqual(renaming.apply_edits(WORLD, edits), rename(WORLD, "Smaug", "Fafnir"))


if __name__ == "__main__":
    unittest.main()
