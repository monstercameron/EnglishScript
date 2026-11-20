"""Run with:  python -m unittest discover tests"""
import os
import re
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from englishscript import EnglishError, compile_source, explain  # noqa: E402
from englishscript.compiler import KEYWORDS  # noqa: E402
from englishscript.lexer import _strip_comment  # noqa: E402
from englishscript.tour import REFUSALS, STORY_MARKER  # noqa: E402

WORLD = """
A dragon has an age (number).
A treasure has a worth (money) and an owner (dragon).
A knight has a purse (money) and a courage (number).
The hoard of a dragon is the total worth of its treasures.
A dragon is ancient when its age is at least 500.
A knight is brave when its courage is more than 5.
A knight's purse is never less than $0.
There is a dragon called Smaug whose age is 771.
There is a dragon called Norbert whose age is 1.
There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.
There is a treasure called Cup whose worth is $500 and whose owner is Smaug.
There is a knight called Gawain whose purse is $300 and whose courage is 8.
There is a knight called Robin whose purse is $20 and whose courage is 2.
"""


def run(source):
    out = []
    compile_source(source).run(out.append)
    return out


def run_asking(source, replies):
    """Run with scripted replies. When they run out, input has ended."""
    out, waiting = [], list(replies)

    def ask(question):
        out.append(question)
        return waiting.pop(0) if waiting else None
    compile_source(source).run(out.append, ask)
    return out


class InTemporaryFolder(unittest.TestCase):
    """Runs each test in an empty folder, so files a program writes are thrown away."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(folder.name)
        self.folder = Path(folder.name)


class Base(unittest.TestCase):
    def refuses(self, source, fragment, stage="compile"):
        with self.assertRaises(EnglishError) as caught:
            run(source)
        error = caught.exception
        self.assertIn(fragment, error.message + " " + (error.hint or ""))
        self.assertEqual(error.stage, stage)
        self.assertIsNotNone(error.line)
        return error


class Values(Base):
    def test_arithmetic_follows_the_usual_order(self):
        self.assertEqual(run("Say 2 + 3 * 4."), ["14"])
        self.assertEqual(run("Say (2 + 3) * 4."), ["20"])
        self.assertEqual(run("Say 2 plus 3 times 4."), ["14"])
        self.assertEqual(run("Say 10 divided by 4."), ["2.5"])
        self.assertEqual(run("Say -3 + 5."), ["2"])
        self.assertEqual(run("Say 1,000 * 1,000."), ["1,000,000"])

    def test_money_and_percentages(self):
        self.assertEqual(run("Say $1,000 + $0.50."), ["$1,000.50"])
        self.assertEqual(run("Say 10% of $250."), ["$25"])
        self.assertEqual(run("Say 10% of $250 + $5."), ["$30"])
        self.assertEqual(run("Say $10 * 3."), ["$30"])
        self.assertEqual(run("Say $10 / $4."), ["2.5"])
        self.assertEqual(run("Say $1 - $3."), ["-$2"])
        self.assertEqual(run("Say 50%."), ["50%"])

    def test_units_do_not_mix(self):
        self.refuses("Say $5 + 5.", "add a plain number to money")
        self.refuses("Say $5 * $5.", "multiply money by money")
        self.refuses("Say 5 / $5.", "divide a plain number by money")
        self.refuses('Say 5 + "five".', "add text to a plain number")
        self.refuses("If $5 is 5:\n  Say 1.", "compare money with a plain number")
        self.refuses('If "a" is less than "b":\n  Say 1.', "more or less")

    def test_division_by_zero_is_a_running_error(self):
        self.refuses("Let n be 0.\nSay 1 / n.", "divide by zero", stage="run")

    def test_text_is_filled_in(self):
        self.assertEqual(run('Let n be 3.\nSay "n is {n} and twice n is {n * 2}."'), ["n is 3 and twice n is 6."])
        self.refuses('Say "oops {1 + ".', "never closed")
        self.refuses('Say "oops {}".', "nothing between")
        self.refuses('Say "oops {nobody}".', "don't know what")


class Variables(Base):
    def test_let_set_and_the_four_verbs(self):
        source = "Let the total be 10.\nAdd 5 to the total.\nSubtract 1 from total.\nMultiply the total by 2.\nDivide the total by 4.\nSay the total.\nSet the total to 0.\nSay total."
        self.assertEqual(run(source), ["7", "0"])

    def test_names_can_be_several_words(self):
        self.assertEqual(run("Let the late fee be $5.\nAdd $1 to the late fee.\nSay the late fee."), ["$6"])

    def test_a_name_means_one_thing(self):
        self.refuses("Let x be 1.\nLet x be 2.", "already means something")
        self.refuses("Let x be 1.\nIf x is 1:\n  Let x be 2.", "already means something")
        self.refuses("Let a be 1.", "already has a meaning")

    def test_a_variable_keeps_its_type(self):
        self.refuses("Let x be 1.\nSet x to $5.", "is a plain number, but")
        self.refuses("Let x be $1.\nMultiply x by $2.", "multiply money by money")

    def test_unknown_names(self):
        self.refuses("Say y.", 'don\'t know what "y"')
        self.refuses("Say the y.", 'don\'t know what "the y"')
        self.refuses("Set 5 to 6.", "isn't something that can be changed")


class Control(Base):
    def test_if_otherwise(self):
        source = "Let n be {}.\nIf n is less than 0:\n  Say \"negative\"\nOtherwise if n is 0:\n  Say \"zero\"\nOtherwise:\n  Say \"positive\""
        self.assertEqual(run(source.format("0 - 1")), ["negative"])
        self.assertEqual(run(source.format(0)), ["zero"])
        self.assertEqual(run(source.format(7)), ["positive"])

    def test_brackets_settle_and_or(self):
        self.assertEqual(run('If (1 is 1 and 2 is 3) or 4 is 4:\n  Say "yes"'), ["yes"])
        self.assertEqual(run('If 1 is 2 and (2 is 3 or 4 is 4):\n  Say "yes"\nOtherwise:\n  Say "no"'), ["no"])
        self.assertEqual(run('If (1 + 1) is 2 and not 1 is 2:\n  Say "yes"'), ["yes"])
        self.assertEqual(run('If 1 < 2 and 2 >= 2:\n  Say "yes"'), ["yes"])
        self.refuses("If 1 is 1 and 2 is 2 or 3 is 3:\n  Say 1.", 'mixes "and" with "or"')

    def test_divisible_by(self):
        source = 'If {} is divisible by {}:\n  Say "yes"\nOtherwise:\n  Say "no"'
        self.assertEqual(run(source.format(15, 5)), ["yes"])
        self.assertEqual(run(source.format(15, 4)), ["no"])
        self.assertEqual(run(source.format(0, 7)), ["yes"])
        self.assertEqual(run(source.format("(2 + 4)", "1 + 2")), ["yes"])
        self.assertEqual(run(source.format(1, 0.5)), ["yes"])
        self.assertEqual(run('If 7 is not divisible by 2 and 8 is divisible by 2:\n  Say "yes"'), ["yes"])
        self.refuses(source.format("$15", 5), "about plain numbers")
        self.refuses(source.format(15, "$5"), "about plain numbers")
        self.refuses(source.format(15, 0), "divisible by zero", stage="run")
        self.refuses("Let divisible be 1.", "already has a meaning")

    def test_fizzbuzz_matches_the_usual_definition(self):
        source = (ROOT / "examples" / "fizzbuzz.english").read_text(encoding="utf-8")
        expected = [
            "FizzBuzz" if n % 15 == 0 else "Fizz" if n % 3 == 0 else "Buzz" if n % 5 == 0 else str(n)
            for n in range(1, 101)
        ]
        self.assertEqual(run(source), expected)

    def test_loops(self):
        self.assertEqual(run("Let n be 3.\nWhile n is more than 0:\n  Say n.\n  Subtract 1 from n."), ["3", "2", "1"])
        self.assertEqual(run('Repeat 2 + 1 times:\n  Say "hi"'), ["hi"] * 3)
        self.refuses("While 1 is 1:\n  Let y be 1.", "gone round", stage="run")
        self.refuses("Repeat 2.5 times:\n  Say 1.", "2.5 times", stage="run")

    def test_layout(self):
        self.refuses("Say 1", "ends with a period")
        self.refuses("Say 1.\n  Say 2.", "doesn't open a block")
        self.refuses("If 1 is 1:\nSay 2.", "nothing is indented")
        self.refuses("If 1 is 1.\nSay 2.", "needs a block")
        self.refuses("Say 1:\n  Say 2.", "should end with a period")
        self.refuses("If 1 is 1:\n    Say 1.\n  Say 2.", "doesn't line up")
        self.refuses("Otherwise:\n  Say 1.", "straight after")
        self.refuses('Say "unclosed.', "never closed")
        self.refuses("If 1 is 1:\n  A cat has an age (number).", "top level")

    def test_unknown_verbs(self):
        self.refuses("Sya 1.", 'Did you mean "Say"')
        self.refuses("Frobnicate 1.", "Teach it to me")
        self.refuses("Say 1 2.", "not this part")


class Things(Base):
    def test_properties_can_be_reached_three_ways(self):
        self.assertEqual(run(WORLD + "Say Smaug's age.\nSay the age of Smaug.\nSay smaug's name."), ["771", "771", "Smaug"])
        self.assertEqual(run(WORLD + "Say Goblet's owner's age.\nSay the age of the owner of Goblet."), ["771", "771"])

    def test_defined_properties_and_adjectives(self):
        self.assertEqual(run(WORLD + "Say the hoard of Smaug.\nSay Norbert's hoard."), ["$3,500", "$0"])
        self.assertEqual(run(WORLD + 'If Smaug is ancient and Norbert is not ancient:\n  Say "ok"'), ["ok"])
        self.assertEqual(run(WORLD + 'If Goblet\'s owner is Smaug:\n  Say "ok"'), ["ok"])

    def test_groups(self):
        source = WORLD + (
            "Say the number of dragons.\n"
            "Say the number of ancient dragons.\n"
            "Say the number of treasures of Smaug.\n"
            "Say the number of Norbert's treasures.\n"
            "Say the number of treasures whose worth is at least $1,000.\n"
            "Say the total worth of all treasures.\n"
            "Say the total age of dragons.\n"
        )
        self.assertEqual(run(source), ["2", "1", "2", "0", "1", "$3,500", "772"])

    def test_for_each_binds_the_noun_and_the_pronoun(self):
        source = WORLD + 'For each dragon:\n  Say "{its name} {the dragon\'s age}"\nFor each brave knight:\n  Say it.'
        self.assertEqual(run(source), ["Smaug 771", "Norbert 1", "Gawain"])
        self.assertEqual(run(WORLD + "For each treasure of Smaug:\n  Say the treasure's name."), ["Goblet", "Cup"])

    def test_creating_things(self):
        self.refuses(WORLD + "There is a dragon called Puff.", "also needs an age")
        self.refuses(WORLD + "There is a dragon called Puff whose age is $5.", "is a plain number, but $5 is money")
        self.refuses(WORLD + "There is a dragon called Smaug whose age is 5.", "already means something")
        self.refuses(WORLD + "There is a wizard called Merlin.", "don't know what a wizard is")
        self.refuses(WORLD + "There is a knight called Poor whose purse is $0 - $1 and whose courage is 1.", "break a rule", stage="run")

    def test_describing_kinds(self):
        self.refuses("A cat has a tail.", "What sort of value")
        self.refuses("A cat has a tail (fluffy).", "isn't a type I know")
        self.refuses("A cat has a name (text).", "already has a meaning")
        self.refuses("A cat has an age (number).\nA cat has an age (number).", "already described")
        self.refuses("A cat has an age (number).\nA cat is old when its tail is 1.", 'no "tail"')
        self.refuses("A cat has an age (number).\nA cat's age is sometimes 1.", '"never" or "always"')

    def test_singular_and_plural_are_checked(self):
        self.refuses(WORLD + "For each dragons:\n  Say 1.", "one at a time")
        self.refuses(WORLD + "Say the number of dragon.", 'write "dragons"')

    def test_plurals(self):
        source = "A pony has an age (number).\nA fox has an age (number).\nSay the number of ponies.\nSay the number of foxes."
        self.assertEqual(run(source), ["0", "0"])


class Verbs(Base):
    PAY = WORLD + (
        "To move an amount (money) from a giver (knight) to a taker (knight):\n"
        "  Subtract the amount from the giver's purse.\n"
        "  Add the amount to the taker's purse.\n"
    )

    def test_roles_are_named_by_prepositions_in_any_order(self):
        self.assertEqual(run(self.PAY + "Move $100 from Gawain to Robin.\nSay Robin's purse."), ["$120"])
        self.assertEqual(run(self.PAY + "Move $100 to Robin from Gawain.\nSay Gawain's purse."), ["$200"])

    def test_roles_are_checked(self):
        self.refuses(self.PAY + "Move 100 from Gawain to Robin.", "wants an amount here")
        self.refuses(self.PAY + "Move $1 from Gawain.", "to a taker")
        self.refuses(self.PAY + "Move $1 from Gawain to Robin to Robin.", "appears twice")
        self.refuses(self.PAY + "Move $1 from Gawain onto Robin.", 'how "onto" fits')
        self.refuses(self.PAY + "Move from Gawain to Robin.", "Move what?")

    def test_a_rule_stops_a_bad_change_and_says_where(self):
        error = self.refuses(self.PAY + "Move $500 from Robin to Gawain.", "break a rule", stage="run")
        self.assertIn("Subtract the amount", error.line.text)
        self.assertEqual(len(error.trace), 1)
        self.assertIn("would become -$480", error.hint)

    def test_two_of_a_kind_make_pronouns_ambiguous(self):
        self.refuses(self.PAY + "To rob a giver (knight) for a taker (knight):\n  Say its purse.", "ambiguous")
        self.refuses(WORLD + "To duel a knight against a knight:\n  Say 1.", "two things called")

    def test_verbs_can_call_themselves(self):
        source = (
            "To count from a start (number):\n"
            "  If the start is more than 0:\n"
            "    Say the start.\n"
            "    Count from the start - 1.\n"
            "Count from 3.\n"
        )
        self.assertEqual(run(source), ["3", "2", "1"])
        self.refuses("To spin:\n  Spin.\nSpin.", "keeps calling itself", stage="run")

    def test_defining_verbs(self):
        self.refuses("To say a number:\n  Say 1.", "already has a meaning")
        self.refuses("To hug a bear:\n  Say 1.", "What is a bear?")
        self.refuses("To hug an amount (money) an other (money):\n  Say 1.", "preposition")
        self.refuses("To hug:\n  Say 1.\nTo hug:\n  Say 2.", "already know how")

    def test_a_loop_cannot_reuse_a_noun_already_in_view(self):
        self.refuses(WORLD + "To greet a dragon:\n  For each dragon:\n    Say 1.", "would mean two things")


class Examples(Base):
    def test_examples_pass_or_explain(self):
        world = compile_source("Let x be 2.\nFor example, x + x is 4.").run(lambda text: None)
        self.assertEqual(world.examples, 1)
        error = self.refuses("Let x be 2.\nFor example, x + x is 5.", "doesn't hold", stage="run")
        self.assertIn("x + x is 4", error.hint)

    def test_the_example_programs_run(self):
        expected = {
            "hello.english": "The score is 216.",
            "dragons.english": "All the treasure in the world: $10,840.",
            "invoices.english": "To ada@example.com: you now owe $85 in late fees.",
            "tournament.english": "Gawain wins, riding Shadowfax.",
        }
        for name, last_line in expected.items():
            with self.subTest(name):
                source = (ROOT / "examples" / name).read_text(encoding="utf-8")
                self.assertEqual(run(source)[-1], last_line)
                self.assertIn(source.splitlines()[0], explain(source))

    def test_the_sha256_example_agrees_with_hashlib(self):
        import hashlib

        source = (ROOT / "examples" / "sha256.english").read_text(encoding="utf-8")
        messages = [
            "The quick brown fox jumps over the lazy dog",
            'He said "hi" to {Sam} & paid $5 (50% off)! ' + "x" * 30,  # two blocks, awkward characters
            "café",  # not a keyboard character
        ]
        replies = messages + [""]
        said = []
        world = compile_source(source).run(said.append, lambda prompt: replies.pop(0))
        self.assertEqual(world.examples, 11)  # the constants, the bit operations and two published digests
        self.assertEqual(said[1], hashlib.sha256(messages[0].encode()).hexdigest())
        self.assertEqual(said[2], hashlib.sha256(messages[1].encode()).hexdigest())
        self.assertTrue(said[3].startswith("Sorry. I can only hash plain keyboard characters"))
        self.assertEqual(len(said), 4)

    def test_the_triangle_example_draws_a_shaded_triangle(self):
        source = (ROOT / "examples" / "triangle.english").read_text(encoding="utf-8")
        said = run(source)
        self.assertEqual(said[0], "Hello Triangle, drawn on Card:")
        rows = said[1:]
        self.assertEqual(len(rows), 30)
        self.assertTrue(all(len(row) == 60 for row in rows))
        self.assertEqual(rows[8].strip(), "--")  # just under the apex
        self.assertEqual(rows[22].strip(), "..:::----===++++****####%%%@@@")  # dark blue to bright green
        self.assertTrue(all(not row.strip() for row in rows[:8] + rows[23:]))

    def test_every_refusal_in_the_tour_is_refused(self):
        prelude = (ROOT / "examples" / "dragons.english").read_text(encoding="utf-8").split(STORY_MARKER)[0]
        for title, snippet in REFUSALS:
            with self.subTest(title):
                with self.assertRaises(EnglishError) as caught:
                    run(prelude + "\n" + snippet + "\n")
                self.assertEqual(caught.exception.stage, "run" if "while running" in title else "compile")

    def test_errors_render_with_a_pointer(self):
        with self.assertRaises(EnglishError) as caught:
            compile_source("Let x be 1.\n  Say x.")
        self.assertIn("line 2", caught.exception.render("demo.english"))
        with self.assertRaises(EnglishError) as caught:
            compile_source("Say $5 + 5.")
        text = caught.exception.render()
        self.assertIn("Say $5 + 5.", text)
        self.assertIn("^^^^^^", text)


STABLE = """
A horse has a speed (number).
A squire has a wage (money) and a mount (horse, if any).
A dragon has an age (number) and a parent (dragon, if any).
A treasure has a worth (money) and an owner (dragon).
The hoard of a dragon is the total worth of its treasures.
A dragon is ancient when its age is at least 500.
There is a horse called Shadowfax whose speed is 40.
There is a horse called Bill whose speed is 5.
There is a squire called Wat whose wage is $3 and whose mount is Shadowfax.
There is a squire called Tom whose wage is $2.
There is a dragon called Smaug whose age is 771.
There is a dragon called Norbert whose age is 1 and whose parent is Smaug.
There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.
There is a treasure called Cup whose worth is $500 and whose owner is Smaug.
"""


class Nothing(Base):
    def test_a_property_left_out_is_nothing(self):
        source = STABLE + "Say Tom's mount.\nSay Wat's mount.\nSay Tom's mount's speed or else 0.\nSay Wat's mount's speed or else 0."
        self.assertEqual(run(source), ["nothing", "Shadowfax", "0", "40"])

    def test_a_kind_can_point_at_its_own_kind(self):
        source = STABLE + "Say Norbert's parent.\nSay Smaug's parent's parent's age or else 0.\nSay the number of dragons of Smaug."
        self.assertEqual(run(source), ["Smaug", "0", "1"])

    def test_using_what_may_be_nothing_is_refused(self):
        for sentence in (
            "Say Tom's mount's speed + 1.",
            "If Tom's mount is Bill:\n  Say 1.",
            "If Tom's mount's speed is more than 3:\n  Say 1.",
            "Set Tom's mount's speed to 3.",
            "Say the number of squires of Tom's mount.",
            "Repeat Tom's mount's speed times:\n  Say 1.",
        ):
            with self.subTest(sentence):
                error = self.refuses(STABLE + sentence, "may be nothing")
                self.assertIn("If Tom has a mount:", error.hint)

    def test_a_check_makes_the_value_usable(self):
        cases = {
            "If Wat has a mount:\n  Say Wat's mount's speed + 1.": ["41"],
            "If Wat has no mount:\n  Say 0.\nOtherwise:\n  Say Wat's mount's speed + 1.": ["41"],
            "If Wat's mount is not nothing:\n  Say Wat's mount's speed + 1.": ["41"],
            "If Tom's mount is nothing:\n  Say 0.\nOtherwise:\n  Say Tom's mount's speed + 1.": ["0"],
            "If Wat has a mount and Wat's mount's speed is more than 30:\n  Say 1.": ["1"],
            "If Tom has no mount or Tom's mount's speed is less than 10:\n  Say 1.": ["1"],
            "If not Wat has no mount:\n  Say Wat's mount's speed + 1.": ["41"],
            "If Tom has a mount:\n  Say 1.\nOtherwise if Wat has a mount:\n  Say Wat's mount's speed + 1.": ["41"],
            "Set Tom's mount to Bill.\nSay Tom's mount's speed + 1.": ["6"],
        }
        for source, said in cases.items():
            with self.subTest(source):
                self.assertEqual(run(STABLE + source), said)

    def test_a_guard_that_leaves_counts_as_a_check(self):
        source = STABLE + (
            "To greet a squire:\n"
            "  If the squire has no mount:\n"
            "    Say \"{the squire} walks.\"\n"
            "    Stop.\n"
            "  Say the squire's mount's speed + 1.\n"
            "Greet Wat.\nGreet Tom.\n"
        )
        self.assertEqual(run(source), ["41", "Tom walks."])
        # A branch that does not leave is not a guard.
        self.refuses(
            STABLE + "To greet a squire:\n  If the squire has no mount:\n    Say 0.\n  Say the squire's mount's speed + 1.",
            "may be nothing",
        )

    def test_a_check_stops_counting_once_things_may_have_changed(self):
        unseat = "To unseat a squire:\n  Set the squire's mount to nothing.\n"
        for source in (
            "If Wat has a mount:\n  Set Wat's mount to nothing.\n  Say Wat's mount's speed + 1.",
            unseat + "If Wat has a mount:\n  Unseat Wat.\n  Say Wat's mount's speed + 1.",
            "If Wat has a mount:\n  Repeat 2 times:\n    Say Wat's mount's speed + 1.\n    Set Wat's mount to nothing.",
            "If Wat has a mount or Wat's wage is $3:\n  Say Wat's mount's speed + 1.",
            "If Wat has a mount:\n  Say 1.\nSay Wat's mount's speed + 1.",
        ):
            with self.subTest(source):
                self.refuses(STABLE + source, "may be nothing")
        # A loop that changes nothing relied on keeps the check.
        self.assertEqual(run(STABLE + "If Wat has a mount:\n  Repeat 2 times:\n    Say Wat's mount's speed + 1."), ["41", "41"])

    def test_checks_that_cannot_matter_are_refused(self):
        self.refuses(STABLE + "If Wat has a wage:\n  Say 1.", "always has a wage")
        self.refuses(STABLE + "If Wat's wage is nothing:\n  Say 1.", "can't be nothing here")
        self.refuses(STABLE + "Say Wat's wage or else $0.", "isn't needed")
        self.refuses(STABLE + "Say Tom's mount or else 5.", "stand-in")
        self.refuses(STABLE + "If Wat has a mount:\n  If Wat's mount is nothing:\n    Say 1.", "can't be nothing here")
        self.refuses(STABLE + "Say nothing + 1.", "can't be used as a value")

    def test_definitions_can_check_too(self):
        source = STABLE + (
            "A squire is mounted when it has a mount.\n"
            "A squire is quick when it has a mount and its mount's speed is at least 30.\n"
            "Say the number of mounted squires.\nSay the number of quick squires.\n"
            "Say the total speed of horses.\n"
        )
        self.assertEqual(run(source), ["1", "1", "45"])

    def test_variables_may_be_nothing(self):
        source = (
            "Let the winner (horse, if any) be nothing.\nSay the winner.\n"
            "If the winner is nothing:\n  Say \"nobody\"\n"
            "Set the winner to Bill.\nSay the winner's speed + 0.\n"
            "Set the winner to nothing.\nSay the winner.\n"
            "Let the pick be Tom's mount.\nSay the pick.\n"
        )
        self.assertEqual(run(STABLE + source), ["nothing", "nobody", "5", "nothing", "nothing"])
        self.refuses("Let x be nothing.", "Nothing of what sort")
        self.refuses("Let n (number) be $5.", "is to hold a plain number")
        self.refuses(STABLE + "Let the pick (horse) be Tom's mount.", "may be nothing")
        self.refuses(STABLE + "Set Wat's wage to nothing.", "is money, but that would make it nothing")
        self.refuses("A cat has an age (number, maybe).", '"if any"')


class FixedVariables(Base):
    def test_always_makes_a_variable_that_cannot_change(self):
        self.assertEqual(run("Let the rate always be 10%.\nSay the rate of $50."), ["$5"])
        self.assertEqual(run("Let the cap (number) always be 3.\nSay the cap + 1."), ["4"])
        for change in ("Set the rate to 5%.", "Multiply the rate by 2."):
            self.refuses("Let the rate always be 10%.\n" + change, 'made with "always"')


class Leaving(Base):
    def test_stop_ends_the_verb(self):
        source = "To count:\n  Say 1.\n  Stop.\n  Say 2.\nCount.\nSay 3."
        self.assertEqual(run(source), ["1", "3"])
        source = WORLD + "To find:\n  For each dragon:\n    Say the dragon.\n    Stop.\nFind.\nSay \"after\""
        self.assertEqual(run(source), ["Smaug", "after"])
        self.refuses("Stop.", "isn't inside one")
        self.refuses("To go:\n  Stop now.", "not this part")

    def test_stop_repeating_ends_the_loop(self):
        self.assertEqual(run("Let n be 0.\nRepeat 10 times:\n  Add 1 to n.\n  If n is 3:\n    Stop repeating.\nSay n."), ["3"])
        self.assertEqual(run("Let n be 0.\nWhile n is at least 0:\n  Add 1 to n.\n  If n is 5:\n    Stop repeating.\nSay n."), ["5"])
        self.assertEqual(run(WORLD + "For each dragon:\n  Say the dragon.\n  Stop repeating."), ["Smaug"])
        self.refuses("Stop repeating.", "needs a loop")
        self.refuses(WORLD + "For each dragon:\n  For each treasure of the dragon:\n    Stop repeating.", "either of the loops")
        # A loop outside a verb is not around the sentences inside the verb.
        source = "To scan:\n  Repeat 3 times:\n    Stop repeating.\n  Say \"scanned\"\nRepeat 2 times:\n  Scan."
        self.assertEqual(run(source), ["scanned", "scanned"])

    def test_skip_goes_on_to_the_next(self):
        source = WORLD + "For each treasure:\n  If the treasure's worth is less than $1,000:\n    Skip this treasure.\n  Say the treasure."
        self.assertEqual(run(source), ["Goblet"])
        source = "Let n be 0.\nRepeat 6 times:\n  Add 1 to n.\n  If n is divisible by 2:\n    Skip this round.\n  Say n."
        self.assertEqual(run(source), ["1", "3", "5"])
        source = WORLD + (
            "For each dragon:\n  For each treasure of the dragon:\n"
            "    If the treasure's worth is less than $1,000:\n      Skip this dragon.\n"
            "    Say the treasure.\n  Say \"end {the dragon}\""
        )
        self.assertEqual(run(source), ["Goblet", "end Norbert"])
        self.refuses(WORLD + "For each dragon:\n  Skip this round.", "has no rounds")
        self.refuses(WORLD + "For each dragon:\n  Skip this treasure.", 'no "For each treasure"')
        self.refuses("Skip this round.", "needs a loop")
        self.refuses("Repeat 2 times:\n  Repeat 2 times:\n    Skip this round.", "either of the loops")

    def test_end_the_program(self):
        self.assertEqual(run('Say "a"\nEnd the program.\nSay "b"'), ["a"])
        self.assertEqual(run("To halt:\n  End the program.\nSay 1.\nHalt.\nSay 2."), ["1"])
        self.refuses("End the show.", "End the program")

    def test_the_new_words_are_reserved(self):
        for word in ("stop", "skip", "end", "nothing", "answer"):
            with self.subTest(word):
                self.refuses(f"Let {word} be 1.", "already has a meaning")


class WorkingOut(Base):
    BOUNTY = STABLE + (
        "To work out the bounty (money) for a dragon:\n"
        "  If the dragon is ancient:\n"
        "    The answer is $1,000.\n"
        "  The answer is 10% of the dragon's hoard.\n"
    )
    CHANGE = "To work out the change (money) from an amount (money) for a price (money):\n  The answer is the amount - the price.\n"

    def test_a_value_is_worked_out_and_used(self):
        self.assertEqual(run(self.BOUNTY + "Say the bounty for Smaug.\nSay the bounty for Norbert + $1."), ["$1,000", "$1"])

    def test_roles_come_in_any_order_and_take_one_value_each(self):
        source = self.CHANGE + "Say the change from $20 for $12.50.\nSay the change for $1 from $5.\nSay the change from ($10 + $10) for $12.50 + $1."
        self.assertEqual(run(source), ["$7.50", "$4", "$8.50"])

    def test_it_may_use_itself_and_its_own_variables(self):
        source = (
            "To work out the factorial (number) of a count (number):\n"
            "  If the count is at most 1:\n    The answer is 1.\n"
            "  The answer is the count * the factorial of (the count - 1).\n"
            "To work out the sum (number) to a limit (number):\n"
            "  Let the total be 0.\n  Let n be 0.\n"
            "  While n is less than the limit:\n    Add 1 to n.\n    Add n to the total.\n"
            "  The answer is the total.\n"
            "Say the factorial of 10.\nSay the sum to 100.\n"
        )
        self.assertEqual(run(source), ["3,628,800", "5,050"])

    def test_the_answer_may_be_nothing(self):
        source = STABLE + (
            "To work out the eldest (dragon, if any):\n"
            "  Let the best (dragon, if any) be nothing.\n  Let the top be 0.\n"
            "  For each dragon:\n    If the dragon's age is more than the top:\n"
            "      Set the best to the dragon.\n      Set the top to the dragon's age.\n"
            "  The answer is the best.\n"
            "Say the eldest.\nSay the eldest's age or else 0.\n"
        )
        self.assertEqual(run(source), ["Smaug", "771"])
        self.refuses(source + "Say the eldest's age + 1.", "may be nothing")

    def test_it_can_be_used_in_definitions(self):
        source = self.BOUNTY + "A dragon is costly when the bounty for the dragon is at least $500.\nSay the number of costly dragons."
        self.assertEqual(run(source), ["1"])

    def test_every_path_must_answer(self):
        grade = "To work out the grade (text) for a score (number):\n  If the score is at least 50:\n    The answer is \"pass\".\n"
        self.refuses(grade, "Not every path")
        self.assertEqual(run(grade + "  Otherwise:\n    The answer is \"fail\".\nSay the grade for 60.\nSay the grade for 10."), ["pass", "fail"])
        self.refuses("To work out the x (number):\n  Repeat 2 times:\n    The answer is 1.", "Not every path")

    def test_working_out_changes_nothing(self):
        head = "To work out the x (number):\n"
        self.refuses(head + "  Say 1.\n  The answer is 1.", "can't say anything")
        self.refuses(STABLE + head + "  Set Smaug's age to 1.\n  The answer is 1.", "can't change anything")
        self.refuses("Let g be 1.\n" + head + "  Set g to 2.\n  The answer is g.", "can't change anything")
        self.refuses("To cheer:\n  Say 1.\n" + head + "  Cheer.\n  The answer is 1.", "is a verb")
        self.refuses(head + "  Stop.", 'finish with "The answer is')
        self.refuses(head + "  End the program.", 'finish with "The answer is')

    def test_types_and_roles_are_checked(self):
        self.refuses("To work out the x (number):\n  The answer is $5.", "is a plain number, but $5 is money")
        self.refuses("To work out the x:\n  The answer is 5.", "What sort of value")
        self.refuses(self.BOUNTY + "Say the bounty.", "missing something: for a dragon")
        self.refuses(self.BOUNTY + "Say the bounty for Goblet.", "wants a dragon here")
        self.refuses(self.BOUNTY + "Say the bounty for Norbert's parent.", "may be nothing")
        self.refuses("The answer is 5.", 'belongs inside a "To work out')

    def test_names_cannot_collide(self):
        self.refuses(STABLE + "To work out the hoard (money) of a dragon:\n  The answer is $1.", "already a property")
        self.refuses("To work out the x (number):\n  The answer is 1.\nLet x be 2.", "already means something")
        self.refuses("To work out the x (number):\n  The answer is 1.\nA cat has an x (number).", "worked out")
        self.refuses("To work out the x (number):\n  The answer is 1.\nTo work out the x (number):\n  The answer is 2.", "already know how to work out")

    def test_endless_working_out_is_stopped(self):
        self.refuses("To work out the loop (number):\n  The answer is the loop.\nSay the loop.", "keeps using itself", stage="run")


class StoredAdjectives(Base):
    SWORN = WORLD + (
        "A knight can be sworn.\n"
        "There is a sworn knight called Lancelot whose purse is $5 and whose courage is 9.\n"
    )

    def test_a_stored_adjective_starts_as_no_and_is_changed_with_now(self):
        source = self.SWORN + (
            "Say the number of sworn knights.\n"
            "Now Robin is sworn.\nNow Lancelot is not sworn.\n"
            "For each sworn knight:\n  Say it.\n"
            "If Gawain is not sworn and Robin is sworn:\n  Say \"ok\"\n"
        )
        self.assertEqual(run(source), ["1", "Robin", "ok"])

    def test_adjectives_can_be_given_when_a_thing_is_made(self):
        source = self.SWORN + "Let the page be a new sworn knight whose purse is $1 and whose courage is 1.\nSay the number of sworn knights."
        self.assertEqual(run(source), ["2"])
        self.refuses(self.SWORN + "There is an ancient dragon called Puff whose age is 3.", "can't be given")
        self.refuses(self.SWORN + "There is a sleepy dragon called Puff whose age is 3.", 'A dragon can be sleepy')

    def test_now_is_refused_where_it_could_not_work(self):
        self.refuses(self.SWORN + "Now Smaug is ancient.", '"Now" can\'t change it')
        self.refuses(self.SWORN + "Now Smaug is sworn.", 'A dragon can be sworn')
        self.refuses(STABLE + "A horse can be tired.\nNow Tom's mount is tired.", "may be nothing")
        self.refuses(self.SWORN + "To work out the x (number):\n  Now Robin is sworn.\n  The answer is 1.", "can't change anything")
        self.refuses(self.SWORN + "A knight can be sworn.", "already defined")

    def test_yes_or_no_values(self):
        source = self.SWORN + (
            "Let the gate open be whether Gawain is sworn or Lancelot is sworn.\n"
            "Say the gate open.\n"
            "Let shut (yes or no) be no.\nSay shut.\n"
            "If the gate open is yes and shut is no:\n  Say \"Enter.\"\n"
            "Set shut to yes.\nIf shut is not no:\n  Say \"Shut.\"\n"
            "To work out the open (yes or no) for a knight:\n  The answer is whether the knight is sworn.\n"
            "Say the open for Robin.\n"
        )
        self.assertEqual(run(source), ["yes", "no", "Enter.", "Shut.", "no"])

    def test_a_yes_or_no_property_points_at_can_be(self):
        self.refuses("A cat has a happy (yes or no).", 'A cat can be happy')
        self.refuses("Let x be yes.\nSay x + 1.", "can't add")
        self.refuses("Let x be yes.\nIf x is more than no:\n  Say 1.", "more or less")
        self.refuses("Let yes be 1.", "already has a meaning")


class NamedLoops(Base):
    def test_a_loop_can_name_its_thing(self):
        source = WORLD + (
            "To greet a dragon:\n"
            "  For each rival in dragons whose age is more than 0:\n"
            "    If the rival is the dragon:\n      Skip this rival.\n"
            "    Say \"{the dragon} glares at {the rival}, aged {the rival's age}.\"\n"
            "Greet Smaug.\n"
            "For each prize in Smaug's treasures:\n  Say the prize.\n"
            "For each prize in all treasures of Smaug whose worth is more than $600:\n  Say the prize.\n"
        )
        self.assertEqual(run(source), ["Smaug glares at Norbert, aged 1.", "Goblet", "Cup", "Goblet"])

    def test_the_name_must_be_new(self):
        self.refuses(WORLD + "To greet a dragon:\n  For each dragon in dragons:\n    Say 1.", "mean two things")
        self.refuses(WORLD + "For each Smaug in dragons:\n  Say 1.", "mean two things")
        self.refuses(WORLD + "For each x in 5:\n  Say 1.", "not a group of things or a list")
        self.refuses(WORLD + "For each x in dragon:\n  Say 1.", 'write "dragons"')

    def test_a_loop_can_go_through_a_list(self):
        source = (
            "Let the words (list of text) be the words of \"a bb ccc\".\n"
            "Say the number of items in the words.\n"
            "For each word in the words:\n  If the word is \"bb\":\n    Skip this word.\n  Say the length of the word.\n"
            "To shout a batch (list of text):\n  For each word in the batch:\n    Say the word in upper case.\n"
            "Shout the lines of \"x{new line}y\".\n"
        )
        self.assertEqual(run(source), ["3", "1", "3", "X", "Y"])

    def test_lists_are_not_said_or_compared_or_stored_in_properties(self):
        self.refuses('Say the words of "a b".', "can't be said")
        self.refuses('Say "{the words of "a b"}".', "")
        self.refuses('If the words of "a" is the words of "a":\n  Say 1.', "can't be compared")
        self.refuses("A cat has a toy box (list of text).", "can't hold a list")
        self.refuses("Let x (list of dogs) be nothing.", 'a list of "dogs"')
        self.refuses("Say the number of items in 5.", "not a list")


class CreatingAndRemoving(Base):
    def test_things_can_be_made_anywhere(self):
        source = STABLE + (
            "To hatch for a dragon:\n"
            "  Let the chick be a new dragon called \"{the dragon}'s chick\" whose age is 0 and whose parent is the dragon.\n"
            "  Say \"{the chick} hatches, child of {the chick's parent}.\"\n"
            "Hatch for Smaug.\n"
            "Repeat 2 times:\n  There is a new horse whose speed is 1.\n"
            "For each horse:\n  Say it.\n"
        )
        self.assertEqual(run(source), ["Smaug's chick hatches, child of Smaug.", "Shadowfax", "Bill", "horse 3", "horse 4"])

    def test_a_thing_can_be_found_by_name(self):
        source = STABLE + (
            'Let the found be the dragon called "NORBERT".\nSay the found.\n'
            'Say the dragon called "Nobody".\n'
            'If the found is not nothing:\n  Say the found\'s age.\n'
        )
        self.assertEqual(run(source), ["Norbert", "nothing", "1"])
        self.refuses(STABLE + 'Say the dragon called "Smaug"\'s age + 1.', "")
        self.refuses(STABLE + 'Let x be the dragon called "Smaug".\nSay x\'s age + 1.', "may be nothing")

    def test_making_things_is_refused_where_it_cannot_work(self):
        self.refuses(STABLE + "Say a new horse whose speed is 1.", "whole value")
        self.refuses(STABLE + "There is a new horse.", "also needs a speed")
        self.refuses(STABLE + 'There is a new horse called 5 whose speed is 1.', "A name is text")
        self.refuses(STABLE + "To work out the x (number):\n  There is a new horse whose speed is 1.\n  The answer is 1.", "can't make new things")
        self.refuses(STABLE + "A horse's speed is never more than 50.\nThere is a new horse whose speed is 99.", "break a rule", stage="run")

    def test_remove_takes_a_thing_out_of_the_world(self):
        source = STABLE + (
            "Remove Shadowfax.\n"
            "Say Wat's mount.\n"
            "Say the number of horses.\n"
            "Say the horse called \"shadowfax\".\n"
        )
        self.assertEqual(run(source), ["nothing", "1", "nothing"])
        error = self.refuses(STABLE + "Remove Smaug.", "Goblet's owner and Cup's owner", stage="run")
        self.assertTrue(error.recoverable)
        error = self.refuses(STABLE + "Remove Bill.\nSay Bill's speed.", "has been removed", stage="run")
        self.assertTrue(error.recoverable)
        self.refuses(STABLE + "A horse can be tired.\nLet b be Bill.\nRemove Bill.\nNow b is tired.", "has been removed", stage="run")
        self.refuses(STABLE + "Let b be Bill.\nRemove Bill.\nSet Tom's mount to b.", "has been removed", stage="run")
        self.refuses(STABLE + "Remove 5.", "Only a thing")
        self.refuses(STABLE + "Remove Tom's mount.", "may be nothing")
        self.refuses(STABLE + "To work out the x (number):\n  Remove Bill.\n  The answer is 1.", "can't remove anything")
        self.refuses(STABLE + "A squire's mount is never nothing.\nRemove Shadowfax.", "would break a rule", stage="run")

    def test_remove_cancels_checks_for_nothing(self):
        self.refuses(STABLE + "If Wat has a mount:\n  Remove Bill.\n  Say Wat's mount's speed + 1.", "may be nothing")


class TextOperations(Base):
    def test_text_forms(self):
        source = (
            'Let the title be "The ""Lonely"" Mountain".\n'
            "Say the title.\nSay the length of the title.\n"
            "Say the title in upper case.\nSay the title in lower case.\n"
            "Say the first 3 letters of the title.\nSay the last 8 letters of the title.\n"
            'Say the last 100 letters of "abc".\nLet the none be the last 0 letters of "abc".\nSay "[{the none}]".\n'
            "Say the number of items in the words of the title.\n"
            'Say ("12" as a number or else 0) + 1.\nSay "1,234.5" as a number or else 0.\nSay "x" as a number.\n'
            'Say "{{braces}} and{new line}a line break".\n'
        )
        self.assertEqual(run(source), [
            'The "Lonely" Mountain', "21", 'THE "LONELY" MOUNTAIN', 'the "lonely" mountain', "The", "Mountain",
            "abc", "[]", "3", "13", "1,234.5", "nothing", "{braces} and\na line break",
        ])

    def test_text_conditions(self):
        source = (
            'If "apple" comes before "Banana" and "Cherry" comes after "banana":\n  Say "order"\n'
            'If "haystack" contains "st" and "haystack" starts with "hay" and "haystack" ends with "ack":\n  Say "parts"\n'
            'If not "Hay" starts with "hay":\n  Say "capitals count"\n'
        )
        self.assertEqual(run(source), ["order", "parts", "capitals count"])
        self.refuses('If 5 contains "a":\n  Say 1.', "about text")

    def test_text_forms_are_checked(self):
        self.refuses('Say the first -1 letters of "abc".', "-1 letters", stage="run")
        self.refuses('Say the first 1.5 letters of "abc".', "1.5 letters", stage="run")
        self.refuses('Say the first $1 letters of "abc".', "plain number of letters")
        self.refuses("Say the length of 5.", "needs text")
        self.refuses("Say 5 in upper case.", "only change the case of text")
        self.refuses('Say "5" as a number + 1.', "may be nothing")
        self.refuses('Say the length of the title in upper case.', "")

    def test_length_may_still_be_a_property(self):
        source = "A bridge has a length (number).\nThere is a bridge called Tower whose length is 244.\nSay the length of Tower.\nSay the length of \"Tower\"."
        self.assertEqual(run(source), ["244", "5"])


class InputAndFiles(InTemporaryFolder, Base):
    def test_ask_reads_each_type_and_asks_again(self):
        source = (
            'Ask "Age?" and let the age (number) be the reply.\n'
            'Ask "Pay?" and let the pay (money) be the reply.\n'
            'Ask "Rate?" and let the rate (percent) be the reply.\n'
            'Ask "Ready?" and let ready (yes or no) be the reply.\n'
            'Ask "Name?" and let the caller (text) be the reply.\n'
            'Say "{the age + 1} {the pay} {the rate} {ready} [{the caller}]".\n'
        )
        said = run_asking(source, ["old", "1,000", "-", "$2.50", "10", "12.5%", "maybe", "N", " Ada "])
        self.assertEqual(said, [
            "Age?", "Please answer with a number, such as 7 or 2.5.", "Age?",
            "Pay?", "Please answer with an amount of money, such as $5 or $2.50.", "Pay?",
            "Rate?", "Please answer with a percentage, such as 10%.", "Rate?",
            "Ready?", "Please answer yes or no.", "Ready?", "Name?",
            "1,001 $2.50 12.5% no [ Ada ]",
        ])
        self.assertEqual(run_asking('Ask "Pay?" and let p (money) be the reply.\nSay p.', ["7"]), ["Pay?", "$7"])

    def test_the_end_of_input_ends_the_program_quietly(self):
        source = 'Say "a"\nAsk "?" and let x (text) be the reply.\nSay "b"'
        self.assertEqual(run_asking(source, []), ["a", "?"])

    def test_ask_is_checked(self):
        self.refuses('Let x be 1.\nAsk "?" and let x (number) be the reply.', "already means something")
        self.refuses('Ask "?" and let x (dragon) be the reply.', "isn't a type I know")
        self.refuses('Ask "?" and let x (text, if any) be the reply.', "can't ask for")
        self.refuses('Ask "?" and let x be the reply.', "What sort of reply")
        self.refuses('Ask 5 and let x (text) be the reply.', "The question is text")
        self.refuses('To work out the x (number):\n  Ask "?" and let y (number) be the reply.\n  The answer is y.', "can't ask")

    def test_files_are_written_added_to_and_read(self):
        source = (
            'Write "one{new line}" to the file "notes.txt".\n'
            'Add "two{new line}" to the file "notes.txt".\n'
            'Add "three" to the file "notes.txt".\n'
            'Say the length of the text of the file "notes.txt".\n'
            'For each line in the lines of the file "notes.txt":\n  Say the line.\n'
            'Let n be 1.\nAdd 2 to n.\nSay n.\n'
        )
        self.assertEqual(run(source), ["13", "one", "two", "three", "3"])
        self.assertEqual((self.folder / "notes.txt").read_bytes(), b"one\ntwo\nthree")

    def test_file_problems_and_where_files_may_be_touched(self):
        error = self.refuses('Say the text of the file "missing.txt".', "couldn't read the file missing.txt", stage="run")
        self.assertTrue(error.recoverable)
        self.refuses('Write 5 to the file "a.txt".', "Only text")
        self.refuses('Write "a" to the file 5.', "name of a file is text")
        self.refuses('Add 5 to the file "a.txt".', "")
        self.refuses('To work out the x (number):\n  Write "a" to the file "a.txt".\n  The answer is 1.', "can't write to a file")
        self.refuses('To work out the x (number):\n  Add "a" to the file "a.txt".\n  The answer is 1.', "can't write to a file")
        (self.folder / "a.txt").write_text("x y z", encoding="utf-8")
        source = 'To work out the size (number):\n  The answer is the number of items in the words of the text of the file "a.txt".\nSay the size.'
        self.assertEqual(run(source), ["3"])


class Recovering(InTemporaryFolder, Base):
    PAY = WORLD + (
        "A knight can be sworn.\n"
        "To move an amount (money) from a giver (knight) to a taker (knight):\n"
        "  If the giver is the taker:\n"
        "    Fail because \"a knight cannot pay himself\".\n"
        "  Add the amount to the taker's purse.\n"
        "  Subtract the amount from the giver's purse.\n"
    )

    def test_a_failed_try_leaves_the_world_as_it_was(self):
        source = self.PAY + (
            "Let the tally be 0.\n"
            "Try:\n"
            "  Add 1 to the tally.\n"
            "  Now Robin is sworn.\n"
            "  There is a new dragon whose age is 3.\n"
            "  Remove Norbert.\n"
            "  Say \"said\"\n"
            "  Write \"kept\" to the file \"log.txt\".\n"
            "  Move $500 from Robin to Gawain.\n"
            "  Say \"not reached\"\n"
            "If that fails:\n"
            "  Say \"No payment: {the problem}\"\n"
            "Say \"{Gawain's purse} {the tally} {the number of sworn knights} {the number of dragons} {Norbert's age}\"\n"
            "Try:\n  Move $5 from Robin to Robin.\nIf that fails:\n  Say the problem.\n"
        )
        self.assertEqual(run(source), [
            "said", 'No payment: That would break a rule: "A knight\'s purse is never less than $0."',
            "$300 0 0 2 1", "a knight cannot pay himself",
        ])
        self.assertEqual((self.folder / "log.txt").read_text(encoding="utf-8"), "kept")

    def test_a_try_that_succeeds_keeps_its_changes(self):
        source = self.PAY + "Try:\n  Move $5 from Gawain to Robin.\nIf that fails:\n  Say the problem.\nSay Robin's purse."
        self.assertEqual(run(source), ["$25"])

    def test_what_can_be_recovered_from(self):
        cases = {
            "Say 1 / 0.": "divide by zero",
            "If 1 is divisible by 0:\n    Say 1.": "divisible by zero",
            "Repeat -1 times:\n    Say 1.": "-1 times",
            'Say the first -1 letters of "a".': "-1 letters",
            'Say the text of the file "nope.txt".': "couldn't read",
            "Remove Smaug.": "can't remove Smaug",
            'Fail because "my own reason".': "my own reason",
        }
        for sentence, problem in cases.items():
            with self.subTest(sentence):
                said = run(STABLE + f"Try:\n  {sentence}\nIf that fails:\n  Say the problem.")
                self.assertEqual(len(said), 1)
                self.assertIn(problem, said[0])

    def test_faults_in_the_program_are_not_recovered_from(self):
        self.refuses("Try:\n  For example, 1 is 2.\nIf that fails:\n  Say 1.", "doesn't hold", stage="run")
        self.refuses("Try:\n  While 1 is 1:\n    Say 1.\nIf that fails:\n  Say 2.", "gone round", stage="run")
        self.refuses("To spin:\n  Spin.\nTry:\n  Spin.\nIf that fails:\n  Say 1.", "keeps calling", stage="run")

    def test_leaving_a_try_early_is_not_a_failure(self):
        source = (
            "Let n be 0.\n"
            "Repeat 3 times:\n  Try:\n    Add 1 to n.\n    Stop repeating.\n  If that fails:\n    Say 0.\n"
            "Say n.\n"
            "To work out the x (number):\n  Try:\n    The answer is 7.\n  If that fails:\n    The answer is 0.\n"
            "Say the x.\n"
            "Try:\n  End the program.\nIf that fails:\n  Say 0.\nSay \"not reached\"\n"
        )
        self.assertEqual(run(source), ["1", "7"])

    def test_try_is_written_correctly(self):
        self.refuses("Try:\n  Say 1.\nSay 2.", '"If that fails:" block straight after')
        self.refuses("If that fails:\n  Say 1.", 'straight after a "Try:"')
        self.refuses("Say the problem.", "only means something inside")
        self.refuses("Try.", "needs a block")
        self.refuses('Fail because 5.', "The reason is text")

    def test_checks_for_nothing_after_a_try(self):
        for source in (
            "If Wat has a mount:\n  Try:\n    Set Wat's mount to nothing.\n  If that fails:\n    Say 1.\n  Say Wat's mount's speed + 1.",
            "If Wat has a mount:\n  Try:\n    Say 1.\n  If that fails:\n    Set Wat's mount to nothing.\n  Say Wat's mount's speed + 1.",
        ):
            with self.subTest(source):
                self.refuses(STABLE + source, "may be nothing")
        source = "If Wat has a mount:\n  Try:\n    Say 1.\n  If that fails:\n    Say 2.\n  Say Wat's mount's speed + 1."
        self.assertEqual(run(STABLE + source), ["1", "41"])


class LeavingALoopPartWay(Base):
    """A round can end at a Skip, and a loop at a Stop repeating, before the end of the block."""

    def test_checks_that_a_skipped_or_stopped_round_lost_are_not_relied_on(self):
        for source in (
            "If Wat has a mount:\n  Repeat 2 times:\n    Say Wat's mount's speed + 1.\n    Set Wat's mount to nothing.\n"
            "    If 1 is 1:\n      Skip this round.\n    Set Wat's mount to Bill.",
            "If Wat has a mount:\n  Repeat 2 times:\n    Set Wat's mount to nothing.\n"
            "    If 1 is 1:\n      Stop repeating.\n    Set Wat's mount to Bill.\n  Say Wat's mount's speed + 1.",
        ):
            with self.subTest(source):
                self.refuses(STABLE + source, "may be nothing")


class ReviewFixes(InTemporaryFolder, Base):
    def test_very_long_numbers_are_said_in_full(self):
        source = "Let n be 10.\nRepeat 13 times:\n  Multiply n by n.\nSay n.\nSay \"{n}\".\nSay $1 * n.\nSay n / 3.\n"
        said = run(source)
        digits = "1" + "0" * 8192
        self.assertEqual(said[0].replace(",", ""), digits)
        self.assertEqual(said[1], said[0])
        self.assertEqual(said[2], "$" + said[0])
        self.assertTrue(said[3].replace(",", "").startswith("3333") and said[3].endswith(".3333"))
        self.assertEqual(run("Say 1" + "0" * 5000 + ".")[0].replace(",", ""), "1" + "0" * 5000)
        # A rule's hint quotes the values, and must manage long ones too.
        error = self.refuses(
            "A cat has an age (number).\nA cat's age is never more than 5.\n"
            "There is a cat called Tom whose age is 1.\nLet n be 10.\nRepeat 13 times:\n  Multiply n by n.\n"
            "Set Tom's age to n.", "break a rule", stage="run")
        self.assertIn("would become 100,000,000,", error.hint)
        # The usual limit is back once the program has finished.
        if hasattr(sys, "get_int_max_str_digits"):
            self.assertNotEqual(sys.get_int_max_str_digits(), 0)
        said = run_asking('Ask "?" and let n (number) be the reply.\nSay n + 1.', ["9" * 5000])
        self.assertEqual(said[1].replace(",", ""), "1" + "0" * 5000)

    def test_for_each_does_not_visit_things_removed_after_it_began(self):
        horses = "A horse has a speed (number).\nThere is a horse called Shadowfax whose speed is 40.\nThere is a horse called Bill whose speed is 5.\n"
        for loop in ("For each horse:\n", "For each steed in horses:\n"):
            noun = "horse" if "horse:" in loop else "steed"
            source = horses + loop + f"  If the {noun} is Shadowfax:\n    Remove Bill.\n  Say \"{{the {noun}}} {{the {noun}'s speed}}\""
            with self.subTest(loop):
                self.assertEqual(run(source), ["Shadowfax 40"])

    def test_adding_a_number_to_a_file_is_explained(self):
        self.refuses('Add 5 to the file "f.txt".', "Only text can be written to a file")
        self.assertEqual(run("Let file count be 1.\nAdd 5 to the file count.\nSay the file count."), ["6"])

    def test_a_fill_in_with_quotes_is_explained(self):
        error = self.refuses('Say "{the length of "abc"}"', "can't contain quotes")
        self.assertIn("variable first", error.hint)
        self.refuses('Say "oops {1 + ".', "never closed")

    def test_a_group_where_a_list_is_wanted_is_explained(self):
        head = (
            "A horse has a speed (number).\nA horse can be tired.\n"
            "To count a batch (list of horses):\n  Say the number of items in the batch.\n"
            "To work out the size (number) of a batch (list of horses):\n  The answer is 1.\n"
        )
        for sentence in ("Count all horses.", "Count tired horses.", "Count horses.",
                         "Say the size of horses.", "Let b (list of horses) be all horses."):
            with self.subTest(sentence):
                self.refuses(head + sentence, "a group of things can't be given where a list is expected yet")

    def test_a_removed_thing_cannot_own_a_group(self):
        source = (
            "A horse has a speed (number).\nA saddle has a wearer (horse, if any).\n"
            "There is a horse called Bill whose speed is 5.\nThere is a saddle called Old whose wearer is Bill.\n"
            "Let h be Bill.\nRemove Bill.\nSay the number of saddles of h."
        )
        error = self.refuses(source, "has been removed", stage="run")
        self.assertTrue(error.recoverable)


class Libraries(Base):
    """A fake library, registered in sys.modules for each test and removed afterwards."""

    SOURCE = (
        "A canvas has a width (number) and a frame (canvas, if any).\n"
        "There is a canvas called Easel whose width is 3.\n"
        "A canvas is wide when its width is more than 10.\n"
        "To splash a colour (text) on a canvas with a big brush (yes or no) is done by the library.\n"
        "To price a cost (money) at a rate (percent) for a count (number) by a few (list of text) "
        "from a backup (canvas, if any) is done by the library.\n"
        "To work out the pixel count (number) of a canvas at a scale (number) is done by the library.\n"
        "To break a canvas is done by the library.\n"
        "To widen a canvas:\n"
        "  Add 1 to the canvas's width.\n"
        "  Break the canvas.\n"
    )
    RETURNS = {  # worked-out value -> declared type, all answered from self.result
        "label back": "text", "count back": "number", "cost back": "money", "share back": "percent",
        "flag back": "yes or no", "pick back": "canvas", "maybe back": "canvas, if any",
        "words back": "list of text",
    }

    def setUp(self):
        import types
        self.calls, self.finished, self.result = [], [], None
        module = types.ModuleType("englishscript.libraries.paint")
        module.SOURCE = self.SOURCE + "".join(
            f"To work out the {name} ({type_}) is done by the library.\n" for name, type_ in self.RETURNS.items()
        )

        def record(name):
            def fn(world, **roles):
                self.calls.append((name, roles))
                world.libraries["paint"].setdefault("calls", 0)
                world.libraries["paint"]["calls"] += 1
            return fn

        def splash(world, **roles):
            record("splash")(world, **roles)
            roles["canvas"].fields["width"] += 10

        def pixel_count(world, canvas, scale):
            self.calls.append(("pixel count", {"canvas": canvas, "scale": scale}))
            return canvas.fields["width"] * scale

        def break_(world, canvas):
            raise self.failure()

        module.verb_splash = splash
        module.verb_price = record("price")
        module.verb_break = break_
        module.value_pixel_count = pixel_count
        for name in self.RETURNS:
            setattr(module, "value_" + name.replace(" ", "_"), lambda world: self.result)
        module.finish = lambda world: self.finished.append(dict(world.libraries["paint"]))
        self.module = module
        self.failure = lambda: EnglishError("The canvas tore.", stage="run", recoverable=True)
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)

    def test_the_vocabulary_of_a_library_joins_the_program(self):
        source = (
            "Use the paint library.\n"
            "Say Easel's width.\n"
            "There is a canvas called Board whose width is 20.\n"
            "Say the number of wide canvases.\n"
        )
        self.assertEqual(run(source), ["3", "1"])
        self.refuses("Say Easel.\nUse the paint library.", 'don\'t know what "Easel"')

    def test_outside_verbs_and_values_get_their_roles_by_keyword(self):
        source = (
            "Use the paint library.\n"
            'Splash "red" on Easel with yes.\n'
            "Say Easel's width.\n"
            'Price $2.50 at 10% for 3 by the words of "a b" from Easel\'s frame.\n'
            "Say the pixel count of Easel at 2.\n"
        )
        self.assertEqual(run(source), ["13", "26"])
        splash, price, pixels = self.calls
        self.assertEqual(splash[0], "splash")
        self.assertEqual(set(splash[1]), {"colour", "canvas", "big_brush"})
        self.assertEqual(splash[1]["colour"], "red")
        self.assertIs(splash[1]["big_brush"], True)
        self.assertEqual(splash[1]["canvas"].name, "Easel")
        roles = price[1]
        self.assertEqual(roles, {"cost": Fraction(5, 2), "rate": Fraction(1, 10), "count": Fraction(3),
                                 "few": ("a", "b"), "backup": None})
        self.assertIsInstance(roles["cost"], Fraction)
        self.assertEqual(pixels[1]["scale"], Fraction(2))

    def test_what_a_worked_out_value_gives_back_is_checked_and_converted(self):
        say = {name: f"Use the paint library.\nSay the {name}." for name in self.RETURNS}
        say["words back"] = "Use the paint library.\nFor each w in the words back:\n  Say the w."
        good = [
            ("label back", "hi", "hi"), ("count back", 7, "7"), ("count back", 0.1, "0.1"),
            ("count back", Fraction(1, 4), "0.25"), ("cost back", 2.5, "$2.50"), ("share back", Fraction(1, 5), "20%"),
            ("flag back", True, "yes"), ("maybe back", None, "nothing"), ("words back", ["a", "b"], "a"),
        ]
        for name, value, said in good:
            with self.subTest(name=name, value=value):
                self.result = value
                self.assertEqual(run(say[name])[:1], [said])
        self.result = ("x", "y")
        self.assertEqual(run(say["words back"]), ["x", "y"])
        # 0.1 arrives exactly, not as a float's approximation.
        self.result = 0.1
        self.assertEqual(run("Use the paint library.\nIf the count back * 3 is 0.3:\n  Say \"exact\""), ["exact"])
        bad = [
            ("label back", 5), ("count back", "5"), ("count back", True), ("count back", float("nan")),
            ("flag back", 1), ("pick back", None), ("pick back", "Easel"), ("words back", "a b"),
            ("words back", ["a", 1]), ("cost back", None),
        ]
        for name, value in bad:
            with self.subTest(name=name, value=value):
                self.result = value
                error = self.refuses(say[name], "gave back", stage="run")
                self.assertFalse(error.recoverable)

    def test_a_thing_given_back_must_be_alive_and_of_the_kind(self):
        self.module.value_pick_back = lambda world: world.named["easel"]
        self.assertEqual(run("Use the paint library.\nSay the pick back."), ["Easel"])
        self.refuses("Use the paint library.\nRemove Easel.\nSay the pick back.", "gave back", stage="run")
        self.module.value_pick_back = lambda world: world.named["mug"]
        self.refuses(
            "Use the paint library.\nA cup has a size (number).\nThere is a cup called Mug whose size is 1.\n"
            "Say the pick back.", "should be a canvas", stage="run",
        )

    def test_a_problem_in_a_library_can_be_recovered_from_and_the_world_is_put_back(self):
        source = (
            "Use the paint library.\n"
            "Try:\n  Widen Easel.\nIf that fails:\n  Say \"{the problem} {Easel's width}\"\n"
            "Try:\n  Splash \"red\" on Easel with no.\n  Break Easel.\nIf that fails:\n  Say Easel's width.\n"
        )
        self.assertEqual(run(source), ["The canvas tore. 3", "3"])
        error = self.refuses("Use the paint library.\nBreak Easel.", "The canvas tore.", stage="run")
        self.assertEqual(error.line.number, 2)

    def test_an_unexpected_python_exception_is_reported_in_english(self):
        self.failure = lambda: ZeroDivisionError("division by zero")
        error = self.refuses("Use the paint library.\nBreak Easel.", "The paint library failed", stage="run")
        self.assertIn("division by zero", error.message)
        self.assertFalse(error.recoverable)
        # It is a fault, so Try does not recover from it.
        self.refuses("Use the paint library.\nTry:\n  Break Easel.\nIf that fails:\n  Say 1.", "failed", stage="run")
        self.failure = KeyboardInterrupt
        self.finished.clear()
        with self.assertRaises(KeyboardInterrupt):
            run("Use the paint library.\nBreak Easel.")
        self.assertEqual(len(self.finished), 1)

    def test_finish_is_called_once_however_the_run_ends(self):
        endings = {
            "normal end": ('Splash "red" on Easel with no.', None),
            "End the program": ('Splash "red" on Easel with no.\nEnd the program.\nSay 1.', None),
            "a problem": ('Splash "red" on Easel with no.\nBreak Easel.', EnglishError),
        }
        for title, (body, raised) in endings.items():
            with self.subTest(title):
                self.finished.clear()
                program = compile_source("Use the paint library.\n" + body)
                if raised:
                    with self.assertRaises(raised):
                        program.run(lambda text: None)
                else:
                    program.run(lambda text: None)
                self.assertEqual(self.finished, [{"calls": 1}])
        self.finished.clear()
        run_asking('Use the paint library.\nAsk "?" and let x (text) be the reply.', [])
        self.assertEqual(self.finished, [{}])

    def test_a_failure_to_finish_never_hides_the_outcome_of_the_run(self):
        def bad_finish(world):
            raise RuntimeError("could not let go")
        self.module.finish = bad_finish
        self.refuses("Use the paint library.\nBreak Easel.", "The canvas tore.", stage="run")
        with self.assertRaises(EnglishError) as caught:
            run("Use the paint library.\nSay 1.")
        self.assertIn("could not let go", caught.exception.message)

    def test_library_state_starts_empty_for_each_run(self):
        program = compile_source('Use the paint library.\nSplash "red" on Easel with no.')
        for _ in range(2):
            self.assertEqual(program.run(lambda text: None).libraries, {"paint": {"calls": 1}})

    def test_outside_verbs_are_verbs(self):
        self.refuses(
            "Use the paint library.\nTo work out the x (number):\n  Splash \"red\" on Easel with no.\n  The answer is 1.",
            "is a verb",
        )
        self.refuses(
            "Use the paint library.\n"
            "If Easel has a frame:\n  Splash \"red\" on Easel with no.\n  Say Easel's frame's width + 1.",
            "may be nothing",
        )
        self.assertEqual(
            run("Use the paint library.\nIf Easel has a frame:\n  Say Easel's frame's width + 1.\nOtherwise:\n  Say 0."),
            ["0"],
        )
        notes = explain('Use the paint library.\nSplash "red" on Easel with no.')
        self.assertIn('"splash" → colour = "red"', notes)
        self.assertNotIn("is done by the library", notes)
        # A worked-out value from a library may be used where working out is, in a definition.
        self.assertEqual(
            run("Use the paint library.\nA canvas is busy when the pixel count of it at 1 is more than 2.\n"
                "Say the number of busy canvases."),
            ["1"],
        )

    def test_using_a_library_is_checked(self):
        self.refuses("Use the paint library.\nUse the paint library.", "already in use (line 1)")
        self.refuses("If 1 is 1:\n  Use the paint library.", "top level")
        error = self.refuses("Use the nonesuch library.", 'no library called "nonesuch"')
        self.assertIn("paint", error.hint)
        self.refuses("Use the paint brush library.", "one word")
        self.refuses("Let use be 1.", "already has a meaning")
        self.refuses("To splash a colour (text) is done by the library.", "Only a library")
        self.refuses("To work out the x (number) is done by the library.", "Only a library")

    def test_a_library_without_source_is_refused(self):
        del self.module.SOURCE
        self.refuses("Use the paint library.", "has no SOURCE text")

    def test_a_library_may_not_use_another(self):
        self.module.SOURCE = "Use the paint library.\n"
        error = self.refuses("Say 1.\nUse the paint library.", "can't use another library")
        self.assertEqual(error.line.number, 2)

    def test_a_missing_function_is_the_librarys_fault(self):
        del self.module.verb_break
        error = self.refuses("Use the paint library.", "verb_break")
        self.assertIn("fault in the paint library", error.hint)
        self.module.SOURCE = "To work out the colour depth (number) is done by the library.\n"
        self.refuses("Use the paint library.", "value_colour_depth")

    def test_a_mistake_in_a_librarys_source_is_reported_as_the_librarys(self):
        self.module.SOURCE = "A canvas has a width (number).\nSay the height of a canvas.\n"
        error = self.refuses("Say 1.\n\nUse the paint library.", "The paint library has a sentence I can't read")
        self.assertEqual(error.line.number, 3)
        self.assertEqual(error.line.text, "Use the paint library.")
        self.assertIn("In the paint library, line 2:", error.hint)
        self.assertIn("Say the height of a canvas.", error.hint)
        self.assertIn("fault in the paint library", error.hint)
        # A clash with the program's own names is refused in the usual way.
        self.module.SOURCE = "A canvas has a width (number).\n"
        error = self.refuses("A canvas has a size (number).\nUse the paint library.", "already described on line 1")

    def test_a_problem_inside_a_librarys_own_verb_names_the_library(self):
        self.module.SOURCE = (
            "A canvas has a width (number).\nA canvas's width is never less than 0.\n"
            "There is a canvas called Easel whose width is 3.\n"
            "To shrink a canvas:\n  Subtract 5 from the canvas's width.\n"
        )
        error = self.refuses("Say 1.\nUse the paint library.\nShrink Easel.", "break a rule", stage="run")
        self.assertEqual(error.line.library, "paint")
        rendered = error.render("drawing.english")
        self.assertIn("line 5 of the paint library", rendered)
        self.assertIn("(while doing line 3: Shrink Easel.)", rendered)


class TodoExample(InTemporaryFolder, Base):
    SOURCE = (ROOT / "examples" / "todo.english").read_text(encoding="utf-8")

    def test_tasks_are_added_marked_listed_and_kept_in_a_file(self):
        said = run_asking(self.SOURCE, ["add Buy milk", "add Walk dog", "done 1", "list", "quit"])
        self.assertEqual(said, [
            "No saved list yet. Starting a new one.",
            "To-do list. Commands: list, add <title>, done <number>, undo <number>, remove <number>, clear, quit.",
            "Nothing to do.",
            ">", "Added: Buy milk",
            ">", "Added: Walk dog",
            ">", "Done: Buy milk",
            ">", "  1. [x] Buy milk", "  2. [ ] Walk dog", "1 of 2 done.",
            ">", "Goodbye.",
        ])
        self.assertEqual((self.folder / "todo.txt").read_text(encoding="utf-8"), "x Buy milk\n- Walk dog\n")

        # A second run finds the list in the file.
        said = run_asking(self.SOURCE, ["undo 1", "add ", "remove 2", "done 9", "clear", "quit"])
        self.assertEqual(said, [
            "To-do list. Commands: list, add <title>, done <number>, undo <number>, remove <number>, clear, quit.",
            "  1. [x] Buy milk", "  2. [ ] Walk dog", "1 of 2 done.",
            ">", "Not done: Buy milk",
            ">", "Add what?",
            ">", "Removed: Walk dog",
            ">", "There is no task with that number.",
            ">", "  1. [ ] Buy milk", "0 of 1 done.",
            ">", "Goodbye.",
        ])
        self.assertEqual((self.folder / "todo.txt").read_text(encoding="utf-8"), "- Buy milk\n")

    def test_the_program_ends_quietly_when_input_runs_out(self):
        said = run_asking(self.SOURCE, ["add Feed cat"])
        self.assertEqual(said[-2:], ["Added: Feed cat", ">"])
        self.assertNotIn("Goodbye.", said)
        self.assertEqual((self.folder / "todo.txt").read_text(encoding="utf-8"), "- Feed cat\n")


class SyntaxDocument(Base):
    """docs/SYNTAX.md is executable: its examples must behave as written."""

    FENCE = re.compile(r"^```(\w+)\n(.*?)^```", re.M | re.S)

    def blocks(self, kind):
        text = (ROOT / "docs" / "SYNTAX.md").read_text(encoding="utf-8")
        return [body for marker, body in self.FENCE.findall(text) if marker == kind]

    @staticmethod
    def stated_output(body):
        said = []
        for line in body.splitlines():
            comment = line[len(_strip_comment(line)):]
            if comment.startswith("#>"):
                said.append(comment[2:].strip())
        return said

    def test_examples_run_and_say_what_the_document_claims(self):
        world, *examples = self.blocks("englishscript")
        self.assertGreater(len(examples), 15)
        for body in examples:
            with self.subTest(body.strip().splitlines()[0]):
                try:
                    said = run(world + body)
                except EnglishError as error:
                    self.fail(error.render())
                self.assertEqual(said, self.stated_output(body))

    def test_refused_examples_are_refused(self):
        world = self.blocks("englishscript")[0]
        refused = self.blocks("refused")
        self.assertGreater(len(refused), 8)
        for body in refused:
            with self.subTest(body.strip().splitlines()[-1]):
                with self.assertRaises(EnglishError):
                    run(world + body)

    def test_reserved_words_match_the_compiler(self):
        text = (ROOT / "docs" / "SYNTAX.md").read_text(encoding="utf-8")
        table = text.split("| Group | Reserved words |")[1].split("\n\n")[0]
        listed = set()
        for row in table.splitlines()[2:]:
            listed.update(re.findall(r"`(\w+)`", row.split("|")[2]))
        self.assertEqual(listed, set(KEYWORDS))


class FailingInsteadOfAnswering(Base):
    HALF = (
        "To work out the half (number) of a count (number):\n"
        "  If the count is divisible by 2:\n"
        "    The answer is the count / 2.\n"
        '  Fail because "{the count} is odd".\n'
    )

    def test_a_path_that_fails_needs_no_answer(self):
        self.assertEqual(run(self.HALF + "Say the half of 10."), ["5"])
        self.refuses(self.HALF + "Say the half of 7.", "7 is odd", stage="run")
        said = run(self.HALF + "Try:\n  Say the half of 7.\nIf that fails:\n  Say the problem.")
        self.assertEqual(said, ["7 is odd"])

    def test_a_path_that_just_ends_still_needs_one(self):
        self.refuses("To work out the half (number) of a count (number):\n  If the count is 2:\n    Fail because \"two\".", "Not every path")


class ShadersAndPictures(unittest.TestCase):
    """The parts of the vulkan library that need no graphics card."""

    def test_each_shader_is_well_formed_spirv(self):
        from englishscript.libraries import _spirv

        for build in (_spirv.vertex_shader, _spirv.fragment_shader):
            with self.subTest(build.__name__):
                words = build()
                self.assertEqual(words[0], 0x07230203)  # the SPIR-V magic number
                bound, position, ids = words[3], 5, set()
                while position < len(words):
                    length, opcode = words[position] >> 16, words[position] & 0xFFFF
                    self.assertGreater(length, 0)
                    if opcode in (19, 21, 22, 23, 30, 32, 33, 248):  # types and labels define their first word
                        ids.add(words[position + 1])
                    position += length
                self.assertEqual(position, len(words))  # every instruction's length adds up exactly
                self.assertTrue(all(0 < found < bound for found in ids))
                self.assertEqual(words[-1], (1 << 16) | 56)  # ends with OpFunctionEnd

    def test_a_picture_is_saved_as_a_real_png(self):
        import struct
        import zlib

        from englishscript.libraries import _vk

        pixels = bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 9, 8, 7, 255])  # 2 by 2
        data = _vk.png(2, 2, pixels)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (2, 2))
        start = data.index(b"IDAT") + 4
        length = struct.unpack(">I", data[start - 8:start - 4])[0]
        raw = zlib.decompress(data[start:start + length])
        self.assertEqual(raw, b"\0" + pixels[:8] + b"\0" + pixels[8:])


def vulkan_works():
    """Is there a graphics card here that Vulkan can draw on?"""
    try:
        from englishscript.libraries import _vk

        _vk.Card("test").close()
        return True
    except Exception:  # noqa: BLE001 - any failure means "skip the tests that need a card"
        return False


@unittest.skipUnless(vulkan_works(), "no graphics card with a Vulkan driver on this computer")
class VulkanLibrary(InTemporaryFolder, Base):
    SCENE = (
        "Use the vulkan library.\n"
        "There is a vertex called Apex whose x is 0, whose y is -0.5, and whose colour is Red.\n"
        "There is a vertex called East whose x is 0.5, whose y is 0.5, and whose colour is Green.\n"
        "There is a vertex called West whose x is -0.5, whose y is 0.5, and whose colour is Blue.\n"
        "There is a triangle called Hello whose top corner is Apex, whose right corner is East, and whose left corner is West.\n"
        "There is a picture called Canvas whose width is 80, whose height is 60, and whose background is Black.\n"
    )

    @staticmethod
    def parts(pixel):
        return [int(part) for part in pixel.split(", ")]

    def test_a_triangle_is_drawn_shaded_and_read_back(self):
        said = run(self.SCENE + (
            "Start Vulkan.\nPrepare Canvas.\n"
            "Say the pixel of Canvas at 40 by 35.\n"        # before any drawing: just the background
            "Draw Hello on Canvas.\n"
            "Say the pixel of Canvas at 0 by 0.\n"          # outside the triangle
            "Say the pixel of Canvas at 40 by 35.\n"        # the middle: an even mix of the corners
            "Say the pixel of Canvas at 40 by 17.\n"        # near the top corner: mostly red
            "Say Vulkan's card.\n"
            "Close Vulkan.\nSay Vulkan's card.\n"
        ))
        self.assertEqual(said[0], "0, 0, 0")
        self.assertEqual(said[1], "0, 0, 0")
        for part in self.parts(said[2]):
            self.assertAlmostEqual(part, 85, delta=6)
        red, green, blue = self.parts(said[3])
        self.assertGreater(red, 200)
        self.assertLess(green + blue, 60)
        self.assertNotEqual(said[4], "not started")
        self.assertEqual(said[5], "not started")

    def test_a_second_triangle_is_added_to_the_first(self):
        said = run(self.SCENE + (
            "There is a vertex called North whose x is -1, whose y is -1, and whose colour is White.\n"
            "There is a vertex called Side whose x is -0.5, whose y is -1, and whose colour is White.\n"
            "There is a vertex called Low whose x is -1, whose y is -0.5, and whose colour is White.\n"
            "There is a triangle called Patch whose top corner is North, whose right corner is Side, and whose left corner is Low.\n"
            "Start Vulkan.\nPrepare Canvas.\nDraw Hello on Canvas.\nDraw Patch on Canvas.\n"
            "Say the pixel of Canvas at 2 by 2.\nSay the pixel of Canvas at 40 by 35.\n"
        ))
        self.assertEqual(said[0], "255, 255, 255")  # the new patch
        self.assertNotEqual(said[1], "0, 0, 0")     # the first triangle is still there

    def test_a_picture_is_saved_and_the_card_is_given_back(self):
        program = compile_source(self.SCENE + 'Start Vulkan.\nPrepare Canvas.\nDraw Hello on Canvas.\nSave Canvas as "out.png".\n')
        world = program.run(lambda text: None)  # the program never says "Close Vulkan."
        self.assertEqual((self.folder / "out.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertNotIn("card", world.libraries["vulkan"])  # finish() closed it all the same

    def test_mistakes_are_problems_a_program_can_recover_from(self):
        cases = {
            "Prepare Canvas.": "has not been started",
            "Start Vulkan.\nStart Vulkan.": "already started",
            "Start Vulkan.\nDraw Hello on Canvas.": "has not been prepared",
            "Start Vulkan.\nPrepare Canvas.\nPrepare Canvas.": "already prepared",
            "Start Vulkan.\nPrepare Canvas.\nSay the pixel of Canvas at 80 by 0.": "whole number from 0 to 79",
            "Start Vulkan.\nPrepare Canvas.\nSay the pixel of Canvas at 1.5 by 0.": "whole number",
            'Start Vulkan.\nPrepare Canvas.\nSave Canvas as ".".': "couldn't write",
            "There is a picture called Vast whose width is 0, whose height is 5, and whose background is Black.\nStart Vulkan.\nPrepare Vast.": "width of Vast",
        }
        for sentences, fragment in cases.items():
            with self.subTest(sentences):
                self.refuses(self.SCENE + sentences, fragment, stage="run")
                body = "\n".join("  " + line for line in sentences.split("\n") if not line.startswith("There is"))
                setup = "\n".join(line for line in sentences.split("\n") if line.startswith("There is"))
                said = run(self.SCENE + setup + "\nTry:\n" + body + '\nIf that fails:\n  Say "recovered"\n')
                self.assertEqual(said[-1], "recovered")

    def test_the_example_program_runs(self):
        source = (ROOT / "examples" / "gpu_triangle.english").read_text(encoding="utf-8")
        said = run(source)
        self.assertTrue(said[0].startswith("Drawing on "))
        self.assertEqual(said[1], "Saved gpu_triangle.png.")
        self.assertTrue((self.folder / "gpu_triangle.png").stat().st_size > 1000)
        self.assertFalse((ROOT / "gpu_triangle.png").exists())


if __name__ == "__main__":
    unittest.main()
