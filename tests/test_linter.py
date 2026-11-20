"""The linter: every problem at once, warnings, and advice.  python -m unittest discover tests"""
import io
import json
import random
import re
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from englishscript import EnglishError, Problem, compile_source, lint  # noqa: E402
from englishscript.compiler import KEYWORDS, pluralize  # noqa: E402
from englishscript.lexer import RULES  # noqa: E402
from englishscript.__main__ import main  # noqa: E402

DRAGONS = (ROOT / "examples" / "dragons.english").read_text(encoding="utf-8")
EXAMPLES = sorted((ROOT / "examples").glob("*.english"))


def errors(source):
    return [p for p in lint(source) if p.kind == "error"]


def warnings(source):
    return [p for p in lint(source) if p.kind == "warning"]


class TheInterface(unittest.TestCase):
    def test_a_problem_has_twelve_fields_and_renders_like_an_error(self):
        problems = lint("Say 1.\nSay $5 + 5.\n")
        self.assertEqual(len(problems), 1)
        problem = problems[0]
        self.assertIsInstance(problem, Problem)
        self.assertEqual(problem.as_dict(), {
            "line": 2, "col": 4, "width": 6, "kind": "error",
            "message": "I can't add a plain number to money.", "hint": "If you meant money, write $5.",
            "sentence": "Say $5 + 5.", "file": None, "category": "kinds",
            "rule": "Arithmetic needs values that go together: money with money, and plain numbers with plain "
                    "numbers or money.",
            "see": "5.3", "fix": None,
        })
        with self.assertRaises(EnglishError) as caught:
            compile_source("Say 1.\nSay $5 + 5.\n")
        self.assertEqual(problem.render("demo.english"), caught.exception.render("demo.english"))

    def test_the_sentence_is_the_line_as_written(self):
        problem = lint("Say $5 + 5.   # adds money to a number\n")[0]
        self.assertEqual(problem.sentence, "Say $5 + 5.   # adds money to a number")

    def test_nothing_to_say_about_an_empty_or_good_program(self):
        self.assertEqual(lint(""), [])
        self.assertEqual(lint("\n\n# only a comment\n"), [])
        for path in EXAMPLES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                try:
                    compile_source(source, path.parent)  # its chapters are beside it
                except EnglishError as error:
                    # An example still being written: the linter finds what the compiler does.
                    self.assertIn(error.line.number, [p.line for p in lint(source, path.parent) if p.kind == "error"])
                else:
                    self.assertEqual(lint(source, path.parent), [])

    def test_it_never_runs_the_program_or_asks(self):
        source = 'Say "said".\nAsk "?" and let x (text) be the reply.\nSay x.\nWrite x to the file "never.txt".\n'
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(out):
            import os
            here = os.getcwd()
            os.chdir(folder)
            try:
                self.assertEqual(lint(source), [])
                self.assertFalse(Path("never.txt").exists())
            finally:
                os.chdir(here)
        self.assertEqual(out.getvalue(), "")

    def test_problems_come_in_order_of_line_and_column(self):
        problems = lint("say 1.\nSay $5 + 5.\nLet x be 1.\nSay y.\n")
        self.assertEqual([(p.line, p.kind) for p in problems],
                         [(1, "warning"), (2, "error"), (3, "warning"), (4, "error")])

    def test_it_never_raises_whatever_it_is_given(self):
        rng = random.Random(20261120)
        sources = [path.read_text(encoding="utf-8") for path in EXAMPLES]
        for number in range(300):
            source = rng.choice(sources)
            lines = source.splitlines()
            how = number % 6
            if how == 0:
                source = source[:rng.randrange(len(source) + 1)]
            elif how == 1:
                rng.shuffle(lines)
                source = "\n".join(lines)
            elif how == 2:
                for _ in range(rng.randrange(1, 8)):
                    if lines:
                        del lines[rng.randrange(len(lines))]
                source = "\n".join(lines)
            elif how == 3:
                for _ in range(rng.randrange(1, 8)):
                    if lines:
                        k = rng.randrange(len(lines))
                        lines.insert(k, lines[k])
                source = "\n".join(lines)
            else:
                chars = list(source)
                for _ in range(rng.randrange(1, 25)):
                    if chars:
                        k = rng.randrange(len(chars))
                        if how == 4:
                            del chars[k]
                        else:
                            chars.insert(k, chars[k])
                source = "".join(chars)
            with self.subTest(number=number):
                problems = lint(source)
                self.assertIsInstance(problems, list)
                self.assertTrue(all(isinstance(p, Problem) for p in problems))
                self.assertFalse(any(p.message.startswith("The linter could not") for p in problems))
                # The linter agrees with the compiler on whether there is an error at all.
                try:
                    compile_source(source)
                    refused = False
                except EnglishError:
                    refused = True
                self.assertEqual(refused, any(p.kind == "error" for p in problems))
        for odd in ("\0", "\t\t:", ":", ".", '"', "(" * 5000 + "1" + ")" * 5000, "Say " + "(" * 3000):
            with self.subTest(odd=odd[:10]):
                self.assertIsInstance(lint(odd), list)

    def test_a_sentence_cut_short_is_refused_not_crashed_on(self):
        # Sentences that stop after the word that should lead on; each was once a crash
        # of the linter, or could be, whichever examples the random test above picks.
        stubs = [
            "A knight is", "A knight can", "A knight can be", "A knight has", "A knight has a",
            "A knight (plural", "A knight (plural knights)", "A knight (plural knights) has",
            "A knight is brave when", "A knight's purse is", "A knight's purse is never",
            "There is", "There is a", "There is a knight", "There is a knight called",
            "There is a knight called Gawain whose", "There is a knight called Gawain whose purse is",
            "Let", "Let the", "Let the count", "Let the count be", "Set", "Set the count to",
            "Add 1 to", "Subtract 1 from", "Multiply the count by", "The hoard of", "The hoard of a",
            "The hoard of a dragon is", "To", "To work", "To work out", "To work out the",
            "Use", "Use the", "Whenever", "Whenever a knight becomes", "For each", "Now", "Ask",
            "This chapter shares", "This chapter shares only",
        ]
        prelude = "A knight has a purse (money).\nA dragon has an age (number).\n"
        for stub in stubs:
            for source in (stub, stub + ".", stub + ":", prelude + stub, prelude + stub + "."):
                with self.subTest(source=source):
                    problems = lint(source)
                    self.assertFalse(any(p.message.startswith("The linter could not") for p in problems))
                    self.assertTrue(any(p.kind == "error" for p in problems))


class EveryError(unittest.TestCase):
    def test_every_refused_sentence_is_reported(self):
        source = "Say $5 + 5.\nSay 1.\nSay nobody.\nIf 1 is 1:\n  Say $1 + 1.\n  Say 2.\n  Say somebody.\n"
        self.assertEqual([p.line for p in errors(source)], [1, 3, 5, 7])

    def test_a_refused_sentence_takes_its_block_with_it(self):
        source = "If $1 is 1:\n  Say nobody.\nOtherwise:\n  Say nobody.\nSay somebody."
        self.assertEqual([p.line for p in errors(source)], [1, 5])

    def test_layout_problems_do_not_hide_later_ones(self):
        source = (
            "Let x be 1.\n"
            "Say x\n"                 # no period
            "Say \"open.\n"           # an unclosed quote
            "If x is 1:\n"            # a block with nothing under it
            "Say 2.\n"
            "    Say 3.\n"            # indented under a sentence that doesn't open a block
            "\tSay 4.\n"              # a tab
            "Say $1 + 1.\n"
        )
        lines = [p.line for p in errors(source)]
        self.assertEqual(lines, [2, 3, 4, 6, 7, 8])

    def test_a_missing_period_does_not_stop_a_later_mistake(self):
        source = "Let x be 1.\nSay x.\nSay x\nSay x.\nSay x.\nSay x.\nSay x.\nSay x.\nSay nobody.\n"
        self.assertEqual([p.line for p in errors(source)], [3, 9])

    def test_advice_is_still_given_inside_the_block_of_a_refused_sentence(self):
        problems = errors("else:\n    return x\n")
        self.assertEqual([p.line for p in problems], [1, 2])
        self.assertIn('"return"', problems[1].message)
        self.assertIn("also needs a period", problems[1].hint)
        problems = errors("Loop:\n  Say 1.\n  If x == 1:\n    Print 1.\n  Say nobody.\n")
        self.assertEqual([p.line for p in problems], [1, 3, 4])
        # ...but no other kind of error: nothing there is compiled.
        self.assertEqual([p.line for p in errors("else:\n  Say nobody.\n  Say $1 + 1.\n")], [1])
        self.assertEqual([p.kind for p in lint("else:\n  say 1.\n")], ["error"])

    def test_the_compiler_still_stops_at_the_first(self):
        with self.assertRaises(EnglishError) as caught:
            compile_source("Say 1.\nSay nobody.\nSay $5 + 5.\n")
        self.assertEqual(caught.exception.line.number, 2)

    def test_one_error_per_line_and_the_more_useful_one(self):
        problems = errors('print("Hello")\n')
        self.assertEqual(len(problems), 1)
        self.assertIn('"Say"', problems[0].message)
        self.assertIn("also needs a period", problems[0].hint)


class NoFloods(unittest.TestCase):
    CASES = {
        "a kind": ("A dragon has an age (number).", "A dragon has an age (numbr)."),
        "a thing": ("There is a dragon called Smaug whose age is 771.", "There is a dragon called Smaug whose ag is 771."),
        "an adjective": ("A dragon is ancient when its age is at least 500.",
                         "A dragon is ancient when its ag is at least 500."),
        "a worked-out property": ("The hoard of a dragon is the total worth of its treasures.",
                                  "The hoard of a dragon is the total wrth of its treasures."),
        "a verb": ("To send a knight against a dragon:", "To send a knight againt a dragon:"),
    }

    def test_one_mistake_in_a_definition_gives_one_error(self):
        for title, (right, wrong) in self.CASES.items():
            with self.subTest(title):
                self.assertIn(right, DRAGONS)
                self.assertEqual(len(errors(DRAGONS.replace(right, wrong, 1))), 1)

    def test_a_refused_assignment_hides_its_name(self):
        problems = errors("x = 5\nif x == 5:\n    Say 1.\n")
        self.assertEqual([p.line for p in problems], [1, 2])
        self.assertIn('"=="', problems[1].message)
        for first in ("Let x = 5.", "Var x = 5.", "Int x = 5.", "x is 5.", "The x is 5."):
            with self.subTest(first):
                self.assertEqual([p.line for p in errors(first + "\nSay x.\n")], [1])

    def test_one_mistake_in_a_kind_gives_one_error_not_ten(self):
        source = DRAGONS.replace("A dragon has an age (number).", "A dragon has an age (numbr).")
        try:
            compile_source(source)
        except EnglishError:
            pass
        # Without the flood rule every dragon, treasure and verb would be refused too.
        self.assertGreater(DRAGONS.count("dragon"), 10)
        self.assertEqual([p.message for p in errors(source)], ['I don\'t know the word "numbr". Did you mean "number"?'])

    def test_variables_worked_out_values_and_libraries(self):
        todo = (ROOT / "examples" / "todo.english").read_text(encoding="utf-8")
        for right, wrong in (
            ("Let the next position be 1.", "Let the next position be 1 +."),
            ("To work out the rest (text) of", "To work out the rest (txt) of"),
            ("A task can be done.", "A task can be done done."),
        ):
            with self.subTest(wrong):
                self.assertEqual(len(errors(todo.replace(right, wrong, 1))), 1)
        self.assertEqual(len(errors("Use the nonesuch library.\nDraw a triangle.\nSay the pixel of Easel.\n")), 1)

    def test_an_unrelated_mistake_is_still_reported(self):
        source = DRAGONS.replace("A dragon has an age (number).", "A dragon has an age (numbr).") + "Say $5 + 5.\n"
        self.assertEqual(len(errors(source)), 2)

    def test_a_name_defined_twice_still_lets_later_mistakes_about_it_through(self):
        source = "A cat has an age (number).\nA cat has an age (number).\nThere is a cat called Tom whose age is $1.\n"
        self.assertEqual([p.line for p in errors(source)], [2, 3])


class Warnings(unittest.TestCase):
    def assertWarns(self, source, fragment, line):
        found = warnings(source)
        self.assertTrue(any(fragment in p.message and p.line == line for p in found), found)
        self.assertEqual(errors(source), [])

    def assertQuiet(self, source):
        self.assertEqual(lint(source), [])

    def test_a_variable_that_is_never_read(self):
        self.assertWarns("Let the total be 0.\n", '"total" is never used', 1)
        self.assertWarns("Let the total be 0.\nSet the total to 5.\n", '"total" is never used', 1)
        self.assertWarns('Ask "?" and let the age (number) be the reply.\n', '"age" is never used', 1)
        self.assertQuiet("Let the total be 0.\nAdd 1 to the total.\n")
        self.assertQuiet("Let the total be 0.\nSay the total.\n")
        self.assertQuiet("Let the total be 0.\nRepeat 2 times:\n  Let n be the total.\n  Say n.\n")

    def test_a_verb_value_adjective_or_role_that_is_never_used(self):
        self.assertWarns("To cheer:\n  Say 1.\n", 'The verb "cheer" is never used', 1)
        self.assertWarns("To spin:\n  Spin.\n", 'The verb "spin" is never used', 1)  # only by itself
        self.assertWarns("To work out the x (number):\n  The answer is 1.\n", '"The x" is never worked out', 1)
        self.assertWarns("A cat has an age (number).\nA cat is old when its age is more than 9.\n",
                         'The adjective "old" is never used', 2)
        self.assertWarns("A cat has an age (number).\nA cat can be asleep.\n", 'The adjective "asleep"', 2)
        self.assertWarns("To pet an amount (number):\n  Say 1.\nPet 2.\n", 'The role "amount"', 1)
        self.assertQuiet("To cheer:\n  Say 1.\nCheer.\n")
        self.assertQuiet("To work out the x (number):\n  The answer is 1.\nSay the x.\n")
        self.assertQuiet(
            "A cat has an age (number).\nA cat is old when its age is more than 9.\n"
            "There is a cat called Tom whose age is 10.\nIf Tom is old:\n  Say 1.\n"
        )
        self.assertQuiet("A cat has an age (number).\nA cat can be asleep.\nThere is an asleep cat called Tom whose age is 1.\n")
        self.assertQuiet("A cat has an age (number).\nTo pet a cat:\n  Say its age.\nThere is a cat called Tom whose age is 1.\nPet Tom.\n")

    def test_nothing_from_a_library_is_warned_about(self):
        module = types.ModuleType("englishscript.libraries.linttest")
        module.SOURCE = (
            "A canvas has a width (number).\nA canvas is wide when its width is more than 1.\n"
            "To paint a canvas with a colour (text) is done by the library.\n"
            "To scrub:\n  Let unread be 1.\n"
        )
        module.verb_paint = lambda world, **roles: None
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        self.assertQuiet("Use the linttest library.\n")

    def test_a_sentence_that_is_never_reached(self):
        self.assertWarns("To go:\n  Stop.\n  Say 1.\n  Say 2.\nGo.\n", "never reached", 3)
        self.assertEqual(len([p for p in warnings("To go:\n  Stop.\n  Say 1.\n  Say 2.\nGo.\n")
                              if "never reached" in p.message]), 1)
        self.assertWarns("Repeat 2 times:\n  Stop repeating.\n  Say 1.\n", "never reached", 3)
        self.assertWarns("Say 1.\nEnd the program.\nSay 2.\n", "never reached", 3)
        self.assertWarns('Fail because "no".\nSay 2.\n', "never reached", 2)
        self.assertWarns("To go:\n  If 1 is 1:\n    Stop.\n  Otherwise:\n    Stop.\n  Say 1.\nGo.\n", "never reached", 6)
        # An If with no Otherwise doesn't always leave.
        self.assertQuiet("To go:\n  If 1 is 1:\n    Stop.\n  Say 1.\nGo.\n")
        self.assertQuiet("To work out the x (number):\n  If 1 is 1:\n    The answer is 1.\n  The answer is 2.\nSay the x.\n")

    def test_a_sentence_that_starts_with_a_small_letter(self):
        self.assertWarns("say 1.\n", "capital", 1)
        self.assertWarns("If 1 is 1:\n  Say 1.\notherwise:\n  Say 2.\n", "capital", 3)
        self.assertQuiet("Say 1.\n")

    def test_never_a_warning_for_something_refused(self):
        self.assertEqual(lint("say nobody.\n")[0].kind, "error")
        self.assertEqual(len(lint("say nobody.\n")), 1)
        # A variable whose only use is in a refused sentence is not called unused.
        self.assertEqual([p.kind for p in lint("Let the total be 1.\nSay the total + $1.\n")], ["error"])
        # Nothing inside a refused verb is warned about.
        self.assertEqual([p.kind for p in lint("To go a bad (money:\n  say 1.\n  Let x be 1.\n")], ["error"])


class Advice(unittest.TestCase):
    TABLE = {
        'print("Hello").': ('"Say"', 'Say "Hello".'),
        "Show the total.": ('"Say"', "Write: Say ..."),
        'Display "Hi".': ('"Say"', 'Write: Say "Hi".'),
        "else:\n  Say 1.": ('"Otherwise"', "Otherwise:"),
        "Else if 1 is 2:\n  Say 1.": ('"Otherwise if"', "Otherwise if ...:"),
        "Elif 1 is 2:\n  Say 1.": ('"Otherwise if"', "Otherwise if ...:"),
        "Return 5.": ("Return", "The answer is 5."),
        "Return the total.": ("Return", "The answer is ..."),
        "Give back 5.": ("Give back", "The answer is 5."),
        "Delete Smaug.": ("Delete", "Remove ..."),
        "Create a dragon.": ("Create", 'There is a new ... called "..." whose ...'),
        "Create a dragon named Smaug.": ("Create", 'There is a new ... called "..." whose ...'),
        "Def greet:\n  Say 1.": ("Def", "To greet a dragon:"),
        "Function greet:\n  Say 1.": ("Function", "To greet a dragon:"),
        "Var x = 5.": ('"Let"', "Let x be 5."),
        "Const rate = 5.": ('"Let"', "Let rate always be 5."),
        "x = 5.": ('"Let"', "Let x be 5."),
        "x is 5.": ("a fact", "Let the age be 771."),
        "Smaug is 771 years old.": ("a fact", "Set Smaug's age to 771."),
        "x = the total.": ('"Let"', "Write: Let x be ..."),
        "The total = 5.": ('"Let"', "Write: Let the total be 5."),
        "Let x be 1.\nx = 5.": ('"Set"', "Set x to 5."),
        "Let the total be 1.\nThe total is 5.": ('"Set"', "Set the total to 5."),
        "Let total = 5.": ('"Let ... be"', "Let total be 5."),
        "Let x be 1.\nIncrement x.": ("Increment", "Add 1 to x."),
        "Increment the score.": ("Increment", "Write: Add ... to ..."),
        'Let x be "a".\nIncrement x.': ("Increment", "Write: Add ... to ..."),
        "Let x be 1.\nDecrease x by 2.": ("Decrease", "Subtract 2 from x."),
        'Input "Name?".': ("Input", 'Ask "Name?" and let'),
        "Import graphics.": ("Import", "Use the ... library."),
        "Loop:\n  Say 1.": ("Loop", "Repeat 3 times:"),
        "For x in dragons:\n  Say x.": ('"For each"', "For each x in ...:"),
        "A cat has an age (number).\nFor x in cats:\n  Say x.": ('"For each"', "For each x in cats:"),
        "For i in range(10):\n  Say i.": ('"For each"', "Write: For each i in ...:"),
        "For i = 1 to 10:\n  Say 1.": ("counting loop", "Repeat 10 times:"),
        "End if.": ("isn't needed", "indentation ends"),
        "Endif.": ("isn't needed", "indentation ends"),
        "}": ('"}"', "indentation ends"),
        "If 1 is 1 then:\n  Say 1.": ('"then"', "If ...:"),
        "Repeat 2 times:\n  Break.": ("Break", "Stop repeating."),
        "Repeat 2 times:\n  Continue.": ("Continue", "Skip this round."),
        "Exit.": ("Exit", "End the program."),
        "If 1 == 1:\n  Say 1.": ('"=="', '"is"'),
        "If 1 != 1:\n  Say 1.": ('"!="', '"is not"'),
        "If 1 is 1 && 2 is 2:\n  Say 1.": ('"&"', '"and"'),
        "If 1 is 1 || 2 is 2:\n  Say 1.": ('"|"', '"or"'),
        "If !(1 is 1):\n  Say 1.": ('"!"', '"not"'),
        "Say 1; Say 2.": ('";"', "one sentence per line"),
        "Say 'hello'.": ("double quotes", '"hello"'),
        "Say 'a{b}'.": ("double quotes", '"..."'),
        "Say greet(1).": ("function calls", "the bounty for Smaug"),
        "Let x be true.": ('"true"', '"yes"'),
        "Let x be false.": ('"false"', '"no"'),
        "Let x (number, if any) be null.": ('"null"', '"nothing"'),
        "Write 5.": ('"to the file', "Say 5."),
        'Write "hi".': ('"to the file', 'Write "hi" to the file'),
    }

    def test_borrowed_sentences_get_advice_from_the_compiler_too(self):
        for source, (in_message, in_hint) in self.TABLE.items():
            with self.subTest(source):
                with self.assertRaises(EnglishError) as caught:
                    compile_source(source + "\n")
                error = caught.exception
                self.assertIn(in_message, error.message)
                self.assertIn(in_hint, error.hint or "")
                problems = errors(source + "\n")
                self.assertTrue(any(in_hint in (p.hint or "") for p in problems), problems)

    def test_then_without_a_colon(self):
        # The compiler stops at the missing colon; the linter gives the advice as well.
        problems = errors("If 1 is 1 then\n  Say 1.\n")
        self.assertEqual(len(problems), 1)
        self.assertIn('"then"', problems[0].message)
        self.assertIn("If ...:", problems[0].hint)

    HINT_WORLD = "A dragon has an age (number).\nThere is a dragon called Smaug whose age is 771.\n"
    SUGGESTION = re.compile(r"(?:[Ww]rite(?:, [^:]*)?|given with): (.+)$")

    def test_every_suggested_sentence_compiles_or_leaves_a_gap(self):
        """A hint never shows a sentence the compiler would refuse: what it suggests
        either has "..." left to fill in, or really compiles."""
        world_lines = self.HINT_WORLD.count("\n")
        checked = 0
        for source in self.TABLE:
            program = self.HINT_WORLD + source + "\n"
            for problem in errors(program):
                for hint_line in (problem.hint or "").splitlines():
                    found = self.SUGGESTION.search(hint_line)
                    if not found or "..." in found.group(1):
                        continue
                    suggestion = found.group(1).strip()
                    before = program.splitlines()[:problem.line - 1]
                    with self.subTest(source=source, suggestion=suggestion):
                        self.assertTrue(self.compiles(before, suggestion), suggestion)
                        checked += 1
        self.assertGreater(checked, 10)
        self.assertGreater(world_lines, 0)

    def test_a_suggestion_never_carries_over_words_englishscript_does_not_use(self):
        """Even with "..." in it, a suggestion repeats a word of the writer's only as the
        name being made or changed: never "named", "range", "years old" and the like."""
        vocabulary = set(KEYWORDS) | set(re.findall(r"[a-z]+", self.HINT_WORLD.lower()))
        name_slots = re.compile(r"\b(?:let|set|each|to|from)(?: the)? ([a-z]\w*)")
        for source in self.TABLE:
            program = self.HINT_WORLD + source + "\n"
            for problem in errors(program):
                written = set(re.findall(r"[a-z]\w*", re.sub(r'"[^"]*"', "", problem.sentence.lower())))
                for hint_line in (problem.hint or "").splitlines():
                    found = self.SUGGESTION.search(hint_line)
                    if not found:
                        continue
                    suggestion = re.sub(r'"[^"]*"', "", found.group(1).lower())
                    context = set(re.findall(r"[a-z]+", " ".join(program.splitlines()[:problem.line - 1]).lower()))
                    context |= {pluralize(word) for word in context | vocabulary}  # "dragon" makes "dragons"
                    allowed = vocabulary | context | set(name_slots.findall(suggestion))
                    carried = (set(re.findall(r"[a-z]\w*", suggestion)) & written) - allowed
                    with self.subTest(source=source, suggestion=found.group(1)):
                        self.assertEqual(carried, set())

    def test_the_reviewers_examples(self):
        for source, banned in (("Create a dragon named Smaug.", "named"), ("for i in range(10):\n  Say i.", "range"),
                               ("Smaug is 771 years old.", "years")):
            with self.subTest(source):
                hint = errors(self.HINT_WORLD + source + "\n")[0].hint
                self.assertNotIn(banned, hint)

    @staticmethod
    def compiles(before, suggestion):
        attempts = []
        if suggestion.startswith("The answer is"):
            for type_ in ("number", "money", "percent", "text"):
                attempts.append(before + [f"To work out the x ({type_}):", "  " + suggestion])
        elif suggestion.endswith(":"):
            attempts.append(before + [suggestion, "  Say 1."])
        else:
            attempts.append(before + [suggestion])
        for lines in attempts:
            try:
                compile_source("\n".join(lines) + "\n")
                return True
            except EnglishError:
                pass
        return False

    def test_a_word_the_program_defined_is_not_given_advice(self):
        with self.assertRaises(EnglishError) as caught:
            compile_source("To show a number (number):\n  Say the number.\nShow 3.\nShow.\n")
        self.assertNotIn('"Say"', caught.exception.message)
        self.assertEqual(run_said("To show an amount (number):\n  Say the amount.\nShow 3.\n"), ["3"])
        self.assertEqual(run_said("Let then be 1.\nIf then is 1:\n  Say 2.\n"), ["2"])

    def test_ordinary_messages_are_unchanged(self):
        for source, fragment in (("Sya 1.", 'Did you mean "Say"'), ("Frobnicate 1.", "Teach it to me"),
                                 ("End the show.", "End the program")):
            with self.subTest(source):
                with self.assertRaises(EnglishError) as caught:
                    compile_source(source)
                self.assertIn(fragment, caught.exception.message + " " + (caught.exception.hint or ""))


def run_said(source):
    out = []
    compile_source(source).run(out.append)
    return out


class CommandLine(unittest.TestCase):
    def run_main(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            status = main(list(args))
        return status, out.getvalue()

    def write(self, text):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "program.english"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_lint_lists_every_problem_and_a_summary(self):
        path = self.write("say 1.\nSay nobody.\nSay $5 + 5.\n")
        status, out = self.run_main(path, "--lint")
        self.assertEqual(status, 1)
        self.assertIn("Vocabulary (", out)
        self.assertIn("Capital letters, a suggestion (", out)
        self.assertIn("The rule: a name is introduced by an earlier sentence before it is used. (See section 3.)", out)
        self.assertTrue(out.rstrip().endswith(
            "2 things to mend: 1 of vocabulary, 1 of kinds of value. 1 suggestion."), out)

    def test_warnings_alone_leave_the_status_at_0(self):
        status, out = self.run_main(self.write("say 1.\n"), "--lint")
        self.assertEqual(status, 0)
        self.assertTrue(out.rstrip().endswith("Nothing to mend: every sentence reads one way. 1 suggestion."), out)
        status, out = self.run_main(str(ROOT / "examples" / "dragons.english"), "--lint")
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "Nothing to mend: every sentence reads one way.")

    def test_json_is_the_problems_and_nothing_else(self):
        status, out = self.run_main(self.write("say 1.\nSay nobody.\n"), "--lint", "--json")
        self.assertEqual(status, 1)
        problems = json.loads(out)
        self.assertEqual([p["kind"] for p in problems], ["warning", "error"])
        self.assertEqual(set(problems[0]), {"line", "col", "width", "kind", "message", "hint", "sentence", "file",
                                            "category", "rule", "see", "fix"})
        self.assertEqual(problems[0]["fix"], {"line": 1, "text": "Say 1."})
        status, out = self.run_main(str(ROOT / "examples" / "hello.english"), "--lint", "--json")
        self.assertEqual((status, json.loads(out)), (0, []))


class Reactions(unittest.TestCase):
    WORLD = "A cat has an age (number).\nA cat can be asleep.\nThere is a cat called Tom whose age is 1.\n"

    def test_a_reaction_is_reachable_and_what_it_uses_counts_as_used(self):
        source = self.WORLD + (
            "A cat is old when its age is more than 9.\n"
            'Let the greeting be "Hi".\n'
            "To purr:\n  Say 1.\n"
            "Whenever a cat becomes old:\n  Say the greeting.\n  Purr.\n"
            "Whenever Tom becomes not asleep:\n  Say it.\n"
        )
        self.assertEqual(lint(source), [])

    def test_inside_a_reaction_the_usual_warnings_apply(self):
        source = self.WORLD + "Whenever Tom becomes asleep:\n  Let unread be 1.\n  Stop.\n  Say 2.\n"
        found = [(p.line, p.message) for p in warnings(source)]
        self.assertTrue(any(line == 5 and '"unread" is never used' in message for line, message in found), found)
        self.assertTrue(any(line == 7 and "never reached" in message for line, message in found), found)
        self.assertEqual(errors(source), [])

    def test_a_refused_opener_takes_its_block_with_it_like_any_other(self):
        for opener in ("Whenever a cat becomes ancient:", "Whenever Puff becomes asleep:",
                       "Whenever a dog becomes asleep:", "If nobody is 1:"):
            with self.subTest(opener):
                source = self.WORLD + opener + "\n  Say nobody.\n  say 1.\nSay nobody.\n"
                problems = [(p.line, p.kind) for p in lint(source) if p.line > 3]
                self.assertEqual(problems, [(4, "error"), (7, "error")])

    def test_a_reaction_not_at_the_top_level_is_one_error(self):
        source = self.WORLD + "If Tom is asleep:\n  Whenever Tom becomes asleep:\n    Say 1.\nSay nobody.\n"
        self.assertEqual([(p.line, p.kind) for p in lint(source)], [(5, "error"), (7, "error")])


class Chapters(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def write(self, name, text):
        (self.folder / name).write_text(text, encoding="utf-8")

    def test_the_problems_of_a_chapter_are_one_error_at_its_use(self):
        self.write("tales.english", "Let x be 1.\nSay y.\nSay $5 + 5.\nlet unused be 2.\n")
        problems = lint("Say 0.\nUse the tales chapter.\nSay x.\nSay nobody.\n", self.folder)
        self.assertEqual([(p.line, p.kind) for p in problems], [(2, "error"), (4, "error")])
        first = problems[0]
        self.assertEqual(first.message, "The tales chapter has 2 problems.")
        self.assertIn("tales.english, line 2", first.hint)
        self.assertIn("Say y.", first.hint)
        self.assertEqual((first.col, first.width), (8, len("tales chapter")))
        self.assertIsNone(first.file)
        self.assertIsNone(first.as_dict()["file"])

    def test_a_chapter_without_problems_and_its_unused_words_are_not_the_programs_business(self):
        self.write("tales.english", "Let x be 1.\nTo spin:\n  Say 1.\n")
        self.assertEqual(lint("Use the tales chapter.\nSay x.\n", self.folder), [])

    def test_a_shared_name_counts_as_used_in_its_chapter(self):
        source = ("This chapter shares only spin, x and old.\nLet x be 1.\nTo spin:\n  Say 1.\n"
                  "A cat has an age (number).\nA cat is old when its age is more than 9.\nTo hide:\n  Say 2.\n")
        found = [p.message for p in lint(source, self.folder)]
        self.assertEqual(found, ['The verb "hide" is never used.'])

    def test_a_missing_chapter_is_one_error_and_does_not_flood(self):
        problems = lint("Use the ghosts chapter.\nSay boo.\nSay $5 + 5.\n", self.folder)
        self.assertEqual([p.line for p in problems], [1, 3])

    def test_an_unshared_name_is_reported_with_the_reason(self):
        self.write("a.english", "This chapter shares nothing.\nLet x be 1.\n")
        problems = lint("Use the a chapter.\nSay x.\n", self.folder)
        self.assertEqual([p.line for p in problems], [2])
        self.assertIn("does not share it", problems[0].message)


class TheTeachersMarks(unittest.TestCase):
    """Each problem is marked as a teacher marks a paper: category, message, correction, rule, section."""

    WORLD = (
        "A dragon has an age (number) and a lair (text).\n"
        "A treasure has a worth (money) and an owner (dragon).\n"
        "A knight has a purse (money) and a mount (dragon, if any).\n"
        "A dragon is ancient when its age is at least 500.\n"
        "The hoard of a dragon is the total worth of its treasures.\n"
        'There is a dragon called Smaug whose age is 771 and whose lair is "Erebor".\n'
        'There is a dragon called Glaurung whose age is 300 and whose lair is "Nargothrond".\n'
        "There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.\n"
        "There is a knight called Gawain whose purse is $300.\n"
        "To tax a dragon:\n"
        "  For each treasure of the dragon:\n"
        "    Subtract 10% of the treasure's worth from the treasure's worth.\n"
    )

    # (written, category, words the message must contain, the corrected first line or None,
    #  does the line then read without any error?)
    CORPUS = [
        ('Say "{the number of dragns}".', "spelling", '"dragns". Did you mean "dragons"',
         'Say "{the number of dragons}".', True),
        ("Say Smuag's age.", "spelling", 'Did you mean "Smaug"', "Say Smaug's age.", True),
        ("Say Smaug's agee.", "spelling", 'Did you mean "age"', "Say Smaug's age.", True),
        ("Txa Smaug.", "spelling", 'Did you mean "Tax"', "Tax Smaug.", True),
        ('Sya "hello".', "spelling", 'Did you mean "Say"', 'Say "hello".', True),
        ('For each anceint dragon:\n  Say "{the dragon}".', "spelling", 'Did you mean "ancient"',
         "For each ancient dragon:", True),
        ("Say 1 + 2", "punctuation", "no period", "Say 1 + 2.", True),
        ('say "hello".', "capitals", "capital letter", 'Say "hello".', True),
        ("Is Smaug ancient?", "punctuation", "no questions", None, None),
        ("Tax Smaug!", "punctuation", "not with an exclamation mark", "Tax Smaug.", True),
        ("Tax Smaug. Tax Glaurung.", "layout", "two sentences", None, None),
        ('There is dragon called Fafnir whose age is 5 and whose lair is "x".', "grammar", "article",
         'There is a dragon called Fafnir whose age is 5 and whose lair is "x".', True),
        ("Say the number of dragon.", "grammar", 'write "dragons"', "Say the number of dragons.", True),
        ('For each dragons:\n  Say "{the dragon}".', "grammar", 'write "dragon"', "For each dragon:", True),
        ("Say its age.", "meaning", "doesn't refer to anything", None, None),
        ('To duel a dragon against a knight:\n  Say "{its name}".\nDuel Smaug against Gawain.', "meaning",
         "can be read two ways", None, None),
        ("Say the dragon's age.", "meaning", "Which dragon?", None, None),
        ('If Smaug is ancient and Glaurung is ancient or Gawain\'s purse is $0:\n  Say "x".', "meaning",
         "can be read two ways", None, None),
        ("Add 5 to Gawain's purse.", "kinds", "plain number to money", None, None),
        ("Set Smaug's lair to 7.", "kinds", "text", None, None),
        ("Tax.", "grammar", "Tax what?", None, None),
        ("Subtract $5 to Gawain's purse.", "grammar", '"Subtract" goes with "from"',
         "Subtract $5 from Gawain's purse.", True),
        ("Smaug tax.", "grammar", '"Smaug" is a dragon, not a verb', "Tax Smaug.", True),
        ("Smaug should be taxed twice.", "grammar", "not a verb", None, None),
        ("Please tax Smaug.", "grammar", 'no need for "Please"', "Tax Smaug.", True),
        ("Burn Smaug.", "vocabulary", 'the verb "Burn"', None, None),
        ("A dragon has a wingspan (number).", "vocabulary", "described only once", None, None),
        ("Add 1 to the count.", "vocabulary", '"the count"', None, None),
        ("Let the number be 5.", "vocabulary", "name of a kind of value", None, None),
        ('If Smaug is ancient:\nSay "old".', "layout", "nothing is indented", None, None),
        ('If Smaug is ancient.\n  Say "old".', "punctuation", "ends with a colon",
         "If Smaug is ancient:", True),
        ('Say "hello.', "punctuation", "no closing quote", 'Say "hello."', True),
        ("Say 'hello'.", "punctuation", "double quotes", 'Say "hello".', True),
        ('If Smaug\'s age is bigger than 5:\n  Say "x".', "grammar", '"more than"',
         "If Smaug's age is more than 5:", True),
        ('If Smaug\'s age is equal to 5:\n  Say "x".', "grammar", 'just "is"', "If Smaug's age is 5:", True),
        ('If Smaug\'s age is at lest 5:\n  Say "x".', "spelling", '"at least"', "If Smaug's age is at least 5:", True),
        ('Otherwise:\n  Say "x".', "layout", "straight after", None, None),
        ("The answer is 5.", "meaning", "To work out", None, None),
        ("There is a dragon called Fafnir whose age is 5.", "grammar", "also needs a lair", None, None),
        ("Say Smaug's age if it isn't 5.", "grammar", "contractions", None, None),
        ("x = 5", "borrowed", '"Let"', "Let x be 5.", True),
        ("Var y = 5.", "borrowed", '"Let"', "Let y be 5.", True),
        ('print("Hello")', "borrowed", '"Say"', 'Say "Hello".', True),
        ("else:\n  Say 1.", "borrowed", '"Otherwise"', "Otherwise:", None),
        ("If 1 == 1:\n  Say 1.", "borrowed", '"=="', "If 1 is 1:", True),
        ("Let total = 5.", "grammar", '"Let ... be"', "Let total be 5.", True),
        ("Let x be true.", "borrowed", '"true"', "Let x be yes.", True),
        ("Use the a.b chapter.", "vocabulary", "plain words", None, None),
        ("Use the ../secret chapter.", "vocabulary", "a path to it can't be given", None, None),
        ("Use the paint.x library.", "vocabulary", "one word of letters", None, None),
        ("For each ancient rival in dragons:\n  Say 1.", "vocabulary", "begins with the adjective",
         "For each ancient dragon:", True),
        ("Repeat 3 time:\n  Say 1.", "spelling", 'Did you mean "times"', "Repeat 3 times:", True),
    ]

    def lint_case(self, text):
        return lint(self.WORLD + text + "\n")

    def first_line(self):
        return self.WORLD.count("\n") + 1

    def test_the_corpus_reads_like_a_teacher(self):
        for written, category, words, fixed, clean in self.CORPUS:
            with self.subTest(written):
                problems = [p for p in self.lint_case(written) if p.kind == "error" or p.category in ("capitals",)]
                self.assertTrue(problems, "nothing was said")
                first = problems[0]
                self.assertEqual(first.category, category, first.message)
                self.assertIn(words, first.message + " " + (first.hint or ""))
                self.assertTrue(first.rule and first.see)
                if fixed is not None:
                    self.assertIsNotNone(first.fix, first.message)
                    self.assertEqual(first.fix["text"], fixed)

    def test_every_fix_mends_its_problem(self):
        """Apply each fix and lint again: the problem is gone from that line; for the
        cases marked clean, every error is gone from it. And mending again and again ends."""
        checked = 0
        for written, _, _, _, clean in self.CORPUS:
            source = self.WORLD + written + "\n"
            for problem in lint(source):
                if problem.fix is None:
                    continue
                lines = source.splitlines()
                lines[problem.fix["line"] - 1] = problem.fix["text"]
                after = lint("\n".join(lines) + "\n")
                with self.subTest(written=written, message=problem.message):
                    same = [p for p in after if p.line == problem.line and p.message == problem.message]
                    self.assertEqual(same, [])
                    if clean and problem.line == self.first_line():
                        self.assertEqual([p.message for p in after if p.line == problem.line and p.kind == "error"],
                                         [])
                    checked += 1
            # Mending everything, again and again, comes to an end.
            for _ in range(20):
                fixes = [p.fix for p in lint(source) if p.fix is not None]
                if not fixes:
                    break
                lines = source.splitlines()
                lines[fixes[0]["line"] - 1] = fixes[0]["text"]
                source = "\n".join(lines) + "\n"
            else:
                self.fail(f"mending {written!r} never ends")
        self.assertGreater(checked, 25)

    def test_a_fix_never_doubles_the_period(self):
        problems = errors("x = 5\n")
        self.assertEqual(problems[0].fix["text"], "Let x be 5.")
        self.assertEqual(lint(problems[0].fix["text"] + "\n"), [warnings("Let x be 5.\n")[0]])

    BANNED = ("token", "syntax", "parse", "invalid", "illegal", "unexpected", "identifier", "expression",
              "statement", "operator", "string", "boolean", "null", "exception", "eof")

    def test_no_compiler_words_in_any_message(self):
        import ast
        pattern = re.compile(r"\b(" + "|".join(self.BANNED) + r")s?\b", re.I)
        allowed = {'EnglishScript has no "{tok.text}".', "null"}  # "null" is quoted back to the writer
        for name in ("compiler", "lexer", "runtime", "linter"):
            tree = ast.parse((ROOT / "englishscript" / f"{name}.py").read_text(encoding="utf-8"))
            docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                          if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
                          and node.body and isinstance(node.body[0], ast.Expr)
                          and isinstance(node.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str) and " " in node.value
                        and "(?" not in node.value
                        and id(node) not in docstrings and node.value not in allowed):
                    with self.subTest(module=name, text=node.value[:60]):
                        self.assertIsNone(pattern.search(node.value))
        for written, *_ in self.CORPUS:
            for problem in self.lint_case(written):
                for text in (problem.message, problem.hint or "", problem.rule or ""):
                    without_quotes = re.sub(r'"[^"]*"', "", text)
                    with self.subTest(written=written, text=text[:60]):
                        self.assertIsNone(pattern.search(without_quotes))

    def test_every_rule_names_a_real_section(self):
        from englishscript.lexer import CATEGORIES, RULES
        text = (ROOT / "docs" / "SYNTAX.md").read_text(encoding="utf-8")
        sections = set(re.findall(r"^#{2,4} (\d+(?:\.\d+)*)\.? ", text, re.M))
        for key, (category, rule, see) in RULES.items():
            with self.subTest(key):
                self.assertIn(see, sections)
                self.assertIn(category, CATEGORIES)
                self.assertTrue(rule.endswith((".", '."', ":\"")), rule)
        for written, *_ in self.CORPUS:
            for problem in self.lint_case(written):
                self.assertIn(problem.see, sections)

    def test_a_mark_has_a_heading_a_correction_and_a_rule(self):
        problem = errors(self.WORLD + 'Say "{the number of dragns}".\n')[0]
        self.assertEqual(problem.render(), "\n".join([
            f"Spelling (line {self.first_line()}):",
            "",
            '    Say "{the number of dragns}".',
            "                        ^^^^^^",
            "                        dragons",
            "",
            '  I don\'t know the word "dragns". Did you mean "dragons"?',
            '  The rule: a kind is described with "A ... has ..." before it is used. (See section 4.1.)',
        ]))
        warning = warnings("say 1.\n")[0]
        self.assertTrue(warning.render().startswith("Capital letters, a suggestion (line 1):"))
        # A correction that is more than the underlined words is written out.
        problem = errors("Please say 1.\n")[0]
        self.assertIn("  Write: Say 1.", problem.render())

    def test_a_problem_while_running_has_the_same_shape(self):
        with self.assertRaises(EnglishError) as caught:
            compile_source("Let x be 0.\nSay 1 / x.\n").run(lambda text: None)
        error = caught.exception
        self.assertEqual((error.category, error.see), ("running", "5.3"))
        self.assertEqual(error.rule, "Nothing can be divided by zero.")
        rendered = error.render("demo.english")
        self.assertTrue(rendered.startswith("While running (demo.english, line 2):"))
        self.assertIn("x was 0. Check it first: If x is not 0:", rendered)
        self.assertTrue(rendered.endswith("The rule: nothing can be divided by zero. (See section 5.3.)"))


class TheSpellingHelper(unittest.TestCase):
    def test_one_close_word_is_suggested(self):
        from englishscript.compiler import close_words, distance
        self.assertEqual(distance("anceint", "ancient"), 1)  # two neighbours swapped count as one
        self.assertEqual(close_words("dragns", ["dragons", "knights"]), ["dragons"])
        self.assertEqual(close_words("agee", ["age", "name"]), ["age"])
        self.assertEqual(close_words("sat", ["say", "set"]), ["say", "set"])  # a tie: no single guess
        self.assertEqual(close_words("ag", ["age"]), [])  # one or two letters: no guess
        self.assertEqual(close_words("abcd", ["abxy"]), [])  # four letters: one change at most
        self.assertEqual(close_words("SMUAG", ["Smaug"]), ["Smaug"])  # capitals don't count

    def test_a_tie_lists_the_words_that_would_fit(self):
        problem = errors("Sat 1.\n")[0]
        self.assertNotIn("Did you mean", problem.message)
        self.assertIn("Say", problem.hint)
        self.assertIn("Set", problem.hint)
        self.assertIsNone(problem.fix)

    def test_only_words_of_the_right_sort_are_offered(self):
        world = "A dragon has an age (number).\nThere is a dragon called Smaug whose age is 1.\n"
        problem = errors(world + "Say the number of drakes.\n")[0]
        self.assertNotIn("Smaug", problem.hint)  # a kind was wanted, not a thing
        self.assertIn("dragons", problem.hint)
        problem = errors(world + "Say Smaug's wing.\n")[0]
        self.assertIn("A dragon has: name, age.", problem.hint)


class ForTools(unittest.TestCase):
    """The API an editor or a language server uses (SYNTAX.md section 10, "For tools")."""

    def test_notes_survive_an_error_elsewhere(self):
        problems, notes = lint("Let the x be 1.\nSay nonsense.\nLet the y be the x.\n", notes=True)
        self.assertEqual([p.line for p in problems if p.kind == "error"], [2])
        self.assertEqual([line for line, _ in notes], [1, 3])
        self.assertIsInstance(lint("Say 1.\n"), list)

    def test_the_table_of_names(self):
        import englishscript
        table = englishscript.names("A dragon (plural dragonz) has an age (number).\n"
                                    "A dragon is old when its age is more than 5.\n"
                                    "There is a dragon called Smaug whose age is 9.\n"
                                    "To roar at a victim (dragon):\n  Say 1.\nLet the x be 2.\nSay nonsense.\n"
                                    "To work out the double (number) of a value (number):\n  The answer is 2.\n"
                                    "Whenever a dragon becomes old:\n  Say 1.\n")
        found = {(n["what"], n["name"], n["of"], n["line"], n["col"], n["width"]) for n in table["names"]}
        for entry in [("kind", "dragon", None, 1, 2, 6), ("plural of a kind", "dragonz", "dragon", 1, 17, 7),
                      ("property", "age", "dragon", 1, 33, 3), ("adjective", "old", "dragon", 2, 12, 3),
                      ("thing", "Smaug", "dragon", 3, 25, 5), ("verb", "roar", None, 4, 3, 4),
                      ("role", "victim", None, 4, 13, 6), ("variable", "x", None, 6, 8, 1),
                      ("worked-out value", "double", None, 8, 16, 6)]:
            self.assertIn(entry, found)
        self.assertIn("reaction", {n["what"] for n in table["names"]})
        self.assertEqual(table["chapters"], [])

    def test_a_chapter_open_in_an_editor(self):
        import englishscript
        texts = {"near.english": "This chapter shares only greeting.\nLet the greeting be \"hi\".\n"}

        def read(path):
            return texts.get(path.name)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual([p for p in lint("Use the near chapter.\nSay the greeting.\n", folder, read=read)
                              if p.kind == "error"], [])
            out = []
            englishscript.compile_source("Use the near chapter.\nSay the greeting.\n", folder,
                                         read=read).run(out.append)
            self.assertEqual(out, ["hi"])
            table = englishscript.names("Use the near chapter.\n", folder, read=read)
            self.assertEqual(table["chapters"], [{"file": "near.english", "name": "near", "shares": ["greeting"]}])

    def test_a_fix_keeps_the_line_as_written(self):
        problem = lint("say “hi”   # greeting\n")[0]
        self.assertEqual(problem.fix["text"], "Say “hi”   # greeting")

    def test_the_exports(self):
        import englishscript
        self.assertIn("whenever", englishscript.KEYWORDS)
        self.assertEqual(englishscript.CATEGORY_HEADINGS["spelling"], "Spelling")
        self.assertRegex(englishscript.__version__, r"^\d+\.\d+\.\d+$")


class TheNewWarnings(unittest.TestCase):
    def test_a_kind_that_could_never_be_made(self):
        found = [p for p in warnings("A node has a label (text) and a next (node).\n") if p.rule == RULES["endless_kind"][1]]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].fix["text"], "A node has a label (text) and a next (node, if any).")
        self.assertFalse([p for p in warnings("A node has a next (node, if any).\n") if p.rule == RULES["endless_kind"][1]])

    def test_a_or_an(self):
        found = warnings("A egg has an weight (number).\nA egg is big when its weight is more than 1.\n"
                         "There is a big egg called Ova whose weight is 2.\n")
        texts = [(p.line, p.message, p.fix["text"]) for p in found if p.category == "grammar"]
        self.assertIn((1, 'Write "An egg": "egg" starts with a vowel sound.',
                       "An egg has an weight (number)."), texts)
        self.assertIn((1, 'Write "a weight": "weight" starts with the sound of a consonant.',
                       "A egg has a weight (number)."), texts)
        self.assertEqual(lint("A egg has an weight (number).\n")[0].kind, "warning")
        compile_source("A egg has an weight (number).\n")  # a warning never stops a program

    def test_a_or_an_is_silent_when_unsure(self):
        for source in ("A unit has a size (number).\n", "An hour has a length (number).\n",
                       "An umbrella has a size (number).\n", "A user has an age (number).\n",
                       "A unicorn has a horn (number).\n", "An unifier has a horn (number).\n",
                       "A one has a size (number).\n", "A FBI has a size (number).\n"):
            with self.subTest(source):
                self.assertEqual([p for p in warnings(source) if p.category == "grammar"], [])

    def test_are_after_one_thing(self):
        world = "A knight has a purse (money).\nThere is a knight called Gawain whose purse is $300.\n"
        found = [p for p in warnings(world + "If Gawain's purse are $300:\n  Say 1.\n") if p.category == "grammar"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].fix["text"], "If Gawain's purse is $300:")
        self.assertEqual(run_said(world + "If Gawain's purse are $300:\n  Say 1.\n"), ["1"])
        # Silent when the last word looks plural: "the totals" may be one thing's name.
        self.assertEqual([p for p in warnings("Let the totals be 1.\nIf the totals are 1:\n  Say 1.\n")
                          if p.category == "grammar"], [])


class TheSyntaxDocument(unittest.TestCase):
    def test_its_examples_have_no_errors(self):
        text = (ROOT / "docs" / "SYNTAX.md").read_text(encoding="utf-8")
        blocks = [body for kind, body in re.findall(r"^```(\w+)\n(.*?)^```", text, re.M | re.S)
                  if kind == "englishscript"]
        world, examples = blocks[0], blocks[1:]
        for body in examples:
            with self.subTest(body.strip().splitlines()[0]):
                # The examples of chapters use the book in examples/.
                self.assertEqual([p for p in lint(world + body, ROOT / "examples") if p.kind == "error"], [])


if __name__ == "__main__":
    unittest.main()
