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
