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
from englishscript.lexer import RULES, _strip_comment  # noqa: E402
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
        self.refuses('Say "oops {1 + ".', 'has no "}" to close it')
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
        self.refuses("Say the y.", 'I don\'t know "the y": no sentence before this one has made it.')
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
        self.refuses("Say 1", "has no period at the end")
        self.refuses("Say 1.\n  Say 2.", "does not open a block")
        self.refuses("If 1 is 1:\nSay 2.", "nothing is indented")
        self.refuses("If 1 is 1.\nSay 2.", "ends with a colon, not a period")
        self.refuses("Say 1:\n  Say 2.", "so it ends with a period, not a colon")
        self.refuses("If 1 is 1:\n    Say 1.\n  Say 2.", "does not line up")
        self.refuses("Otherwise:\n  Say 1.", "straight after")
        self.refuses('Say "unclosed.', "has no closing quote")
        self.refuses("If 1 is 1:\n  A cat has an age (number).", "top level")

    def test_unknown_verbs(self):
        self.refuses("Sya 1.", 'Did you mean "Say"')
        self.refuses("Frobnicate 1.", "Teach it to me")
        self.refuses("Say 1 2.", 'The sentence is complete before "2"')


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
        self.refuses("A cat has a tail (fluffy).", '"fluffy" is not a type')
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
        self.refuses(self.PAY + "Move $1 from Gawain onto Robin.", '"Move" was taught with "from" and "to", not "onto".')
        self.refuses(self.PAY + "Move from Gawain to Robin.", "Move what?")

    def test_a_rule_stops_a_bad_change_and_says_where(self):
        error = self.refuses(self.PAY + "Move $500 from Robin to Gawain.", "break a rule", stage="run")
        self.assertIn("Subtract the amount", error.line.text)
        self.assertEqual(len(error.trace), 1)
        self.assertIn("would become -$480", error.hint)

    def test_two_of_a_kind_make_pronouns_ambiguous(self):
        self.refuses(self.PAY + "To rob a giver (knight) for a taker (knight):\n  Say its purse.", "can be read two ways")
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
        self.refuses("To hug an amount (money) an other (money):\n  Say 1.", "linking word")
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
        self.refuses("To go:\n  Stop now.", 'The sentence is complete before "now"')

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
            "Let the gate open be whether (Gawain is sworn or Lancelot is sworn).\n"
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
    def test_list_properties_can_be_reached_through_the_current_thing(self):
        source = ("A shelf has a tags (list of text).\n"
                  'There is a shelf called Desk whose tags is a list of "red" and "blue".\n'
                  "For each shelf:\n"
                  "  Let the original be shelf.\n"
                  "  For each tag in its tags:\n    Say the tag.\n"
                  "  For each tag in their tags:\n    Say the tag.\n"
                  "  For each tag in shelf's tags:\n    Say the tag.\n"
                  "  Say the original.\n")
        self.assertEqual(run(source), ["red", "blue"] * 3 + ["Desk"])

    def test_a_possessive_group_skips_things_removed_before_their_turn(self):
        source = WORLD + ("A shelf has a keeper (dragon).\n"
                          "There is a shelf called Desk whose keeper is Smaug.\n"
                          "For each shelf:\n  For each prize in its keeper's treasures:\n"
                          "    Say the prize.\n    Remove Cup.\n")
        self.assertEqual(run(source), ["Goblet"])

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

    def test_lists_are_not_said_or_compared(self):
        self.refuses('Say the words of "a b".', "can't be said")
        self.refuses('Say "{the words of "a b"}".', "")
        self.refuses('If the words of "a" is the words of "a":\n  Say 1.', "can't be compared")
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
        self.refuses(STABLE + "Set Tom's mount to Bill.\nA squire's mount is never nothing.\nRemove Shadowfax.",
                     "would break a rule", stage="run")

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
        self.refuses('Ask "?" and let x (dragon) be the reply.', '"dragon" is not a type')
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
        self.refuses("Try.", "ends with a colon, not a period")
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
        self.refuses('Say "oops {1 + ".', 'has no "}" to close it')

    def test_a_group_where_a_list_is_wanted_is_made_a_list(self):
        head = (
            "A horse has a speed (number).\nA horse can be tired.\n"
            "To count a batch (list of horses):\n  Say the number of items in the batch.\n"
            "To work out the size (number) of a batch (list of horses):\n  The answer is 1.\n"
        )
        head += ("There is a horse called Bill whose speed is 5.\nNow Bill is tired.\n"
                 "There is a horse called Ned whose speed is 1.\n")
        said = run(head + "Count all horses.\nCount tired horses.\nCount horses.\nSay the size of horses.\n"
                          "Let b (list of horses) be all horses.\nSay the number of items in b.\n")
        self.assertEqual(said, ["2", "1", "2", "1", "2"])

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

    def test_a_library_preserves_known_problem_kinds(self):
        source = (
            "Use the paint library.\nTry:\n  Break Easel.\nIf that fails:\n"
            "  If the problem is a missing item:\n    Say \"missing item\".\n"
            "  If the problem is a bad number:\n    Say \"bad number\".\n"
            "  If the problem is a bad reply:\n    Say \"bad reply\".\n"
            "  If the problem is no model:\n    Say \"no model\".\n"
            "  If the problem is a library problem:\n    Say \"library problem\".\n"
        )
        cases = (("missing_item", "missing item"), ("rounding", "bad number"),
                 ("bad_reply", "bad reply"), ("no_model", "no model"), ("fail", "library problem"))
        for key, expected in cases:
            with self.subTest(key=key):
                self.failure = lambda: EnglishError("x", stage="run", recoverable=True, teach=key)
                self.assertEqual(run(source), [expected])
        self.failure = lambda: EnglishError("x", stage="run", recoverable=True, teach="rounding",
                                            problem="missing item")
        self.assertEqual(run(source), ["missing item"])

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

    def test_a_change_made_by_a_librarys_verb_sets_off_reactions(self):
        source = (
            "Use the paint library.\n"
            "A canvas can be framed.\n"
            "Whenever a canvas becomes wide:\n  Say \"{the canvas} is wide at {its width}.\"\n"
            "To decorate a canvas:\n  Splash \"red\" on the canvas with no.\n  Say \"decorated\"\n"
            "Decorate Easel.\n"
        )
        self.assertEqual(run(source), ["Easel is wide at 13.", "decorated"])

    def test_a_librarys_source_may_say_whenever(self):
        self.module.SOURCE += "Whenever a canvas becomes wide:\n  Say \"wide {the canvas}\"\n"
        source ="Use the paint library.\nTo stretch:\n  Set Easel's width to 50.\n  Say \"stretched\"\nStretch.\n"
        program = compile_source(source)
        self.assertTrue(program.compiler.reactive)
        out = []
        program.run(out.append)
        self.assertEqual(out, ["wide Easel", "stretched"])

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


class Reactions(Base):
    """Whenever a thing becomes an adjective (or stops being one)."""

    KNIGHTS = WORLD + (
        "A knight is broke when its purse is $0.\n"
        "A knight can be sworn.\n"
    )

    def test_a_kind_becomes_a_defined_adjective_and_stops_being_it(self):
        source = self.KNIGHTS + (
            "Whenever a knight becomes broke:\n  Say \"{the knight} is broke.\"\n"
            "Whenever a knight becomes not broke:\n  Say \"{it} has money.\"\n"
            "Set Robin's purse to $0.\n"
            "Set Robin's purse to $0.\n"  # already broke: nothing becomes
            "Say \"between\".\n"
            "Add $1 to Robin's purse.\n"
        )
        self.assertEqual(run(source), ["Robin is broke.", "between", "Robin has money."])

    def test_a_named_thing_becomes_a_stored_adjective(self):
        source = self.KNIGHTS + (
            "Whenever Gawain becomes sworn:\n"
            "  Say \"{Gawain} {the knight} {it} {its purse}\"\n"
            "Whenever Gawain becomes not sworn:\n  Say \"unsworn\"\n"
            "Now Robin is sworn.\n"
            "Now Gawain is sworn.\n"
            "Now Gawain is sworn.\n"
            "Now Gawain is not sworn.\n"
        )
        self.assertEqual(run(source), ["Gawain Gawain Gawain $300", "unsworn"])

    def test_a_reaction_applies_from_its_sentence_on(self):
        source = self.KNIGHTS + (
            "Now Robin is sworn.\n"
            "Whenever a knight becomes sworn:\n  Say \"{the knight} swears.\"\n"
            "Now Gawain is sworn.\n"
        )
        self.assertEqual(run(source), ["Gawain swears."])

    def test_several_things_go_in_the_order_made_and_reactions_in_the_order_written(self):
        source = WORLD + (
            "Let the line be $10.\n"
            "A knight is poor when its purse is less than the line.\n"
            "There is a knight called Kay whose purse is $5 and whose courage is 1.\n"
            "Whenever a knight becomes poor:\n  Say \"first {the knight}\"\n"
            "Whenever Robin becomes poor:\n  Say \"second Robin\"\n"
            "Whenever a knight becomes poor:\n  Say \"third {the knight}\"\n"
            "Set the line to $1,000.\n"
        )
        self.assertEqual(run(source), [
            "first Gawain", "third Gawain", "first Robin", "second Robin", "third Robin",
        ])

    def test_the_order_made_holds_across_kinds(self):
        source = WORLD + (
            "There is a new dragon whose age is 3.\n"
            "Let the mark be 0.\n"
            "A dragon is marked when the mark is 1.\n"
            "A knight is marked when the mark is 1.\n"
            "Whenever a knight becomes marked:\n  Say the knight.\n"
            "Whenever a dragon becomes marked:\n  Say the dragon.\n"
            "Set the mark to 1.\n"
        )
        self.assertEqual(run(source), ["Smaug", "Norbert", "Gawain", "Robin", "dragon 3"])

    def test_reactions_set_off_reactions_at_once(self):
        source = self.KNIGHTS + (
            "Whenever a knight becomes broke:\n"
            "  Say \"{the knight} is broke.\"\n"
            "  Now the knight is sworn.\n"
            "  Say \"after swearing\"\n"
            "Whenever a knight becomes sworn:\n  Say \"{the knight} swears.\"\n"
            "Set Robin's purse to $0.\n"
            "Say \"done\"\n"
        )
        self.assertEqual(run(source), ["Robin is broke.", "Robin swears.", "after swearing", "done"])

    def test_reactions_that_never_settle_stop_at_200_levels(self):
        source = self.KNIGHTS + (
            "Whenever Robin becomes sworn:\n  Now Robin is not sworn.\n"
            "Whenever Robin becomes not sworn:\n  Now Robin is sworn.\n"
            "Try:\n  Now Robin is sworn.\nIf that fails:\n  Say \"caught\"\n"
        )
        error = self.refuses(source, "200 levels", stage="run")
        self.assertFalse(error.recoverable)
        self.assertIn('in this circle: "Whenever Robin becomes sworn" (Robin), then '
                      '"Whenever Robin becomes not sworn" (Robin), and round again.', error.message)
        # 197 levels are fine.
        source = self.KNIGHTS + (
            "Let the left be 99.\n"
            "Whenever Robin becomes sworn:\n  Subtract 1 from the left.\n  If the left is more than 0:\n"
            "    Now Robin is not sworn.\n"
            "Whenever Robin becomes not sworn:\n  Now Robin is sworn.\n"
            "Now Robin is sworn.\nSay the left.\n"
        )
        self.assertEqual(run(source), ["0"])

    def test_reactions_happen_inside_verbs_and_loops_straight_after_the_sentence(self):
        source = self.KNIGHTS + (
            "Whenever a knight becomes broke:\n  Say \"{the knight} is broke.\"\n"
            "To spend for a knight:\n  Set the knight's purse to $0.\n  Say \"spent\"\n"
            "Spend for Gawain.\n"
            "For each knight:\n  Add $1 to its purse.\n  Set its purse to $0.\n  Say \"next\"\n"
        )
        self.assertEqual(run(source), [
            "Gawain is broke.", "spent", "Gawain is broke.", "next", "Robin is broke.", "next",
        ])

    def test_a_problem_in_a_reaction_belongs_to_the_sentence_and_try_undoes_it_all(self):
        source = self.KNIGHTS + (
            "Let the count be 0.\n"
            "Whenever a knight becomes broke:\n"
            "  Add 1 to the count.\n"
            "  Now the knight is sworn.\n"
            "  If the knight is brave:\n    Fail because \"{the knight} refuses\"\n"
            "Try:\n  Set Robin's purse to $0.\n  Set Gawain's purse to $0.\nIf that fails:\n"
            "  Say \"{the problem}: {the count} {Robin's purse} {Gawain's purse}\"\n"
            "Say the number of sworn knights.\n"
        )
        self.assertEqual(run(source), ["Gawain refuses: 0 $20 $300", "0"])
        error = self.refuses(self.KNIGHTS + (
            "Whenever a knight becomes broke:\n  Say \"ok\"\n  Fail because \"no\"\n"
            "Set Robin's purse to $0.\n"
        ), "no", stage="run")
        self.assertEqual(error.line.text.strip(), 'Fail because "no"')
        self.assertIn("(while doing line 20: Set Robin's purse to $0.)", error.render())

    def test_rules_hold_inside_reactions(self):
        source = self.KNIGHTS + (
            "Whenever Robin becomes sworn:\n  Subtract $100 from Robin's purse.\n"
            "Try:\n  Now Robin is sworn.\nIf that fails:\n  Say \"{the problem} {the number of sworn knights}\"\n"
        )
        self.assertEqual(run(source), ['That would break a rule: "A knight\'s purse is never less than $0." 0'])

    def test_stop_leaves_a_reaction(self):
        source = self.KNIGHTS + (
            "Whenever a knight becomes sworn:\n  If the knight is not brave:\n    Stop.\n  Say \"{the knight} rides.\"\n"
            "Now Robin is sworn.\nNow Gawain is sworn.\nSay \"end\"\n"
        )
        self.assertEqual(run(source), ["Gawain rides.", "end"])

    def test_end_the_program_in_a_reaction_ends_it(self):
        source = self.KNIGHTS + "Whenever Robin becomes sworn:\n  End the program.\nNow Robin is sworn.\nSay 1.\n"
        self.assertEqual(run(source), [])

    def test_a_thing_made_fitting_does_not_become_and_a_removed_one_becomes_nothing(self):
        source = self.KNIGHTS + (
            "A knight is rich when its purse is more than $100.\n"
            "Whenever a knight becomes broke:\n  Say \"broke {the knight}\"\n"
            "Whenever a knight becomes sworn:\n  Say \"sworn {the knight}\"\n"
            "Whenever a knight becomes not rich:\n  Say \"not rich {the knight}\"\n"
            "There is a new knight called \"Pauper\" whose purse is $0 and whose courage is 1.\n"
            "There is a new sworn knight called \"Squire\" whose purse is $1 and whose courage is 1.\n"
            "Let the third be a new knight called \"Third\" whose purse is $0 and whose courage is 1.\n"
            "Remove Gawain.\n"
            "Say \"quiet\"\n"
        )
        self.assertEqual(run(source), ["quiet"])

    def test_a_thing_removed_by_an_earlier_reaction_is_skipped(self):
        source = WORLD + (
            "Let the line be $10.\n"
            "A knight is poor when its purse is less than the line.\n"
            "Whenever a knight becomes poor:\n  Say \"poor {the knight}\"\n  If the knight is Gawain:\n    Remove Robin.\n"
            "Set the line to $1,000.\n"
        )
        self.assertEqual(run(source), ["poor Gawain"])

    def test_working_out_sets_nothing_off(self):
        source = self.KNIGHTS + (
            "To work out the double (number) of a value (number):\n"
            "  Let the result be 0.\n  Set the result to the value * 2.\n  The answer is the result.\n"
            "A knight is bold when the double of its courage is more than 10.\n"
            "Whenever a knight becomes bold:\n  Say \"bold {the knight}\"\n"
            "Set Robin's courage to 6.\nSay the double of 2.\n"
        )
        self.assertEqual(run(source), ["bold Robin", "4"])

    def test_what_is_refused(self):
        cases = {
            "Whenever a wizard becomes broke:\n  Say 1.\n": "what a wizard is",
            "Whenever a knight becomes ancient:\n  Say 1.\n": 'what "ancient" means for a knight',
            "Whenever Puff becomes broke:\n  Say 1.\n": 'what "Puff" refers to',
            "Whenever knight becomes broke:\n  Say 1.\n": 'Write "a knight"',
            "Whenever Robin is broke:\n  Say 1.\n": '"becomes"',
            "Whenever Robin becomes broke.\n": "ends with a colon, not a period",
            "If 1 is 1:\n  Whenever Robin becomes broke:\n    Say 1.\n": "top level",
            "To work out the x (number):\n  Whenever Robin becomes broke:\n    Say 1.\n  The answer is 1.\n": "top level",
            "To go:\n  Whenever Robin becomes broke:\n    Say 1.\nGo.\n": "top level",
            "Whenever Robin becomes broke:\n  Stop repeating.\n": "needs a loop",
            "For each knight:\n  Whenever it becomes broke:\n    Say 1.\n": "top level",
            "Whenever Robin becomes broke:\n  Say the dragon.\n": "the dragon",
            "Say 1.\nWhenever Kay becomes broke:\n  Say 1.\nThere is a knight called Kay whose purse is $1 and whose courage is 1.\n":
                'what "Kay" refers to',
            "Let whenever be 1.\n": "already has a meaning",
            "Let becomes be 1.\n": "already has a meaning",
        }
        for body, fragment in cases.items():
            with self.subTest(body.splitlines()[0]):
                self.refuses(self.KNIGHTS + body, fragment)

    def test_checks_for_nothing_do_not_survive_a_change_when_there_are_reactions(self):
        body = (
            "A horse has a speed (number).\nA squire has a wage (money) and a mount (horse, if any).\n"
            "A squire can be paid.\n"
            "There is a horse called Shadowfax whose speed is 40.\n"
            "There is a squire called Wat whose wage is $3 and whose mount is Shadowfax.\n"
            "If Wat has a mount:\n  Set Wat's wage to $5.\n  Say Wat's mount's speed + 1.\n"
        )
        self.assertEqual(run(body), ["41"])
        reaction = "Whenever Wat becomes paid:\n  Set Wat's mount to nothing.\n"
        self.refuses(body + reaction, "may be nothing")
        # A check of a variable of a block survives, since no reaction can reach it.
        source = body.split("If Wat", 1)[0] + reaction + (
            "To go:\n  Let n be \"1\" as a number.\n  If n is not nothing:\n    Now Wat is paid.\n    Say n + 1.\nGo.\n"
            "Say Wat's mount.\n"
        )
        self.assertEqual(run(source), ["2", "nothing"])

    def test_the_trace_and_line_of_a_problem_in_a_reaction(self):
        source = self.KNIGHTS + "Whenever Robin becomes sworn:\n  Say 1 / 0.\nNow Robin is sworn.\n"
        error = self.refuses(source, "divide by zero", stage="run")
        self.assertEqual(error.line.number, 18)
        self.assertEqual([line.number for line in error.trace], [19])

    def test_a_program_without_whenever_watches_nothing(self):
        program = compile_source(self.KNIGHTS + "Set Robin's purse to $0.\n")
        self.assertFalse(program.compiler.reactive)
        self.assertTrue(compile_source(self.KNIGHTS + "Whenever Robin becomes broke:\n  Say 1.\n").compiler.reactive)

    def test_serials_count_things_of_every_kind_in_the_order_made(self):
        source = WORLD + (
            "There is a new dragon whose age is 2.\n"
            "Try:\n  There is a new knight whose purse is $1 and whose courage is 1.\n  Fail because \"no\".\n"
            "If that fails:\n  Say 1.\n"
            "There is a new treasure whose worth is $1 and whose owner is Smaug.\n"
            "A dragon's age is never more than 1,000.\n"
        )
        world = compile_source(source + "Try:\n  There is a new dragon whose age is 5,000.\nIf that fails:\n  Say 2.\n"
                               "There is a new dragon whose age is 3.\n").run(lambda text: None)
        things = sorted((t for items in world.things.values() for t in items), key=lambda t: t.serial)
        self.assertEqual([t.name for t in things],
                         ["Smaug", "Norbert", "Goblet", "Cup", "Gawain", "Robin", "dragon 3", "treasure 3", "dragon 4"])
        serials = [t.serial for t in things]
        self.assertEqual(serials[:7], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(len(set(serials)), len(serials))
        self.assertEqual(serials, sorted(serials))
        self.assertGreater(serials[7], 8)  # the knight made in the failed Try kept number 8


class LiveLibraries(Base):
    """A library that goes on working after the sentences: live(world) and world.event."""

    SOURCE = (
        "A switch has a label (text) and a count (number).\n"
        "A switch can be lit.\n"
        "A switch can be done.\n"
        "A switch's count is never more than 3.\n"
        "A switch is busy when its count is at least 2.\n"
        "To flick a switch is done by the library.\n"
    )
    PROGRAM = (
        "Use the clicker library.\n"
        "There is a switch called Lamp whose label is \"lamp\" and whose count is 0.\n"
        "There is a switch called Fan whose label is \"fan\" and whose count is 0.\n"
        "Whenever a switch becomes lit:\n  Say \"{the switch} on\"\n  Add 1 to the switch's count.\n"
        "Whenever Lamp becomes not lit:\n  Say \"Lamp off\"\n"
        "Whenever a switch becomes busy:\n  Say \"{the switch} busy\"\n  If the switch is Fan:\n"
        "    Fail because \"the fan is too busy\"\n"
        "Whenever a switch becomes done:\n  Say \"bye\"\n  End the program.\n"
    )

    def setUp(self):
        import types
        self.log = []
        module = types.ModuleType("englishscript.libraries.clicker")
        module.SOURCE = self.SOURCE
        module.live = lambda world: self.log.append(("live", world.busy, world.ended))
        module.finish = lambda world: self.log.append(("finish",))

        def flick(world, switch):
            world.event(lambda: switch.marks.add("lit"))
        module.verb_flick = flick
        self.module = module
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)

    def start(self, extra=""):
        out = []
        world = compile_source(self.PROGRAM + extra).run(out.append)
        return world, out

    def test_live_is_called_once_before_finish_when_the_sentences_end(self):
        world, _ = self.start()
        self.assertEqual(self.log, [("live", False, False), ("finish",)])
        self.assertFalse(world.ended)

    def test_live_is_not_called_after_end_the_program_or_a_problem(self):
        world, _ = self.start("End the program.\n")
        self.assertEqual(self.log, [("finish",)])
        self.assertTrue(world.ended)
        self.log.clear()
        with self.assertRaises(EnglishError):
            self.start('Fail because "no".\n')
        self.assertEqual(self.log, [("finish",)])

    def test_a_failure_in_live_is_reported_like_one_in_finish(self):
        def broken(world):
            raise ValueError("no screen")
        self.module.live = broken
        with self.assertRaises(EnglishError) as caught:
            self.start()
        self.assertIn("no screen", caught.exception.message)
        self.assertIn("clicker library", caught.exception.message)
        self.assertEqual(self.log, [("finish",)])

    def test_an_event_after_the_run_sets_off_reactions(self):
        world, out = self.start()
        lamp, fan = world.named["lamp"], world.named["fan"]
        self.assertTrue(world.event(lambda: lamp.marks.add("lit")))
        self.assertEqual(out, ["Lamp on"])
        self.assertEqual(lamp.fields["count"], 1)
        self.assertTrue(world.event(lambda: lamp.marks.discard("lit")))
        self.assertEqual(out, ["Lamp on", "Lamp off"])
        # A property changed from outside sets off a defined adjective.
        world.event(lambda: lamp.fields.__setitem__("count", 2))
        self.assertEqual(out[-1], "Lamp busy")
        # Things changed by one event go in the order they were made, not the order changed.
        out.clear()

        def both():
            fan.marks.add("lit")
            lamp.marks.add("lit")
        self.assertTrue(world.event(both))
        self.assertEqual(out, ["Lamp on", "Fan on"])
        self.assertEqual((lamp.fields["count"], fan.fields["count"]), (3, 1))

    def test_an_event_with_a_problem_puts_everything_back(self):
        world, out = self.start()
        lamp, fan = world.named["lamp"], world.named["fan"]
        # A broken rule.
        with self.assertRaises(EnglishError) as caught:
            world.event(lambda: lamp.fields.__setitem__("count", 5))
        self.assertIn("break a rule", caught.exception.message)
        self.assertTrue(caught.exception.recoverable)
        self.assertEqual(lamp.fields["count"], 0)
        # A reaction that fails: its changes, and the event's, are undone.
        fan.fields["count"] = 1
        with self.assertRaises(EnglishError) as caught:
            world.event(lambda: fan.marks.add("lit"))
        self.assertEqual(caught.exception.message, "the fan is too busy")
        self.assertEqual(out, ["Fan on", "Fan busy"])  # what was said stays said
        self.assertEqual((fan.fields["count"], fan.marks), (1, set()))
        # Any other exception also puts the world back, and passes through.

        def careless():
            lamp.marks.add("lit")
            raise KeyError("oops")
        with self.assertRaises(KeyError):
            world.event(careless)
        self.assertEqual(lamp.marks, set())
        # The world still works.
        self.assertTrue(world.event(lambda: lamp.marks.add("lit")))
        self.assertEqual(lamp.fields["count"], 1)

    def test_end_the_program_in_a_reaction_ends_the_events(self):
        world, out = self.start()
        lamp = world.named["lamp"]
        self.assertTrue(world.event(lambda: lamp.marks.add("done")))
        self.assertEqual(out, ["bye"])
        self.assertTrue(world.ended)
        self.assertIn("done", lamp.marks)  # what the event changed stays
        called = []
        self.assertFalse(world.event(lambda: called.append(1)))
        self.assertEqual(called, [])
        # After the program's own "End the program.", events do nothing either.
        world, _ = self.start("End the program.\n")
        self.assertFalse(world.event(lambda: called.append(1)))
        self.assertEqual(called, [])

    def test_an_event_cannot_come_in_while_a_sentence_or_an_event_is_carried_out(self):
        # From a verb of the library, while the program's sentences run: a fault in the library.
        with self.assertRaises(EnglishError) as caught:
            self.start("Flick Lamp.\n")
        self.assertIn("RuntimeError", caught.exception.message)
        self.assertIn("world.event", caught.exception.message)
        # From inside an event.
        world, _ = self.start()
        lamp = world.named["lamp"]
        with self.assertRaises(RuntimeError):
            world.event(lambda: world.event(lambda: None))
        # From world.out during a reaction.
        world.out = lambda text: world.event(lambda: None)
        with self.assertRaises(RuntimeError):
            world.event(lambda: lamp.marks.add("lit"))
        self.assertEqual((lamp.marks, lamp.fields["count"]), (set(), 0))
        self.assertFalse(world.busy)

    def test_an_event_works_without_reactions_and_checks_rules(self):
        module_source = "Use the clicker library.\nThere is a switch called Lamp whose label is \"l\" and whose count is 0.\n"
        world = compile_source(module_source).run(lambda text: None)
        lamp = world.named["lamp"]
        self.assertTrue(world.event(lambda: lamp.fields.__setitem__("count", 3)))
        with self.assertRaises(EnglishError):
            world.event(lambda: lamp.fields.__setitem__("count", 4))
        self.assertEqual(lamp.fields["count"], 3)

    def test_an_event_lifts_the_limits_a_run_lifts(self):
        world, out = self.start(
            "A switch is cold when its count is less than 0.\n"
            "Whenever a switch becomes cold:\n  Say the switch's count.\n"
        )
        lamp = world.named["lamp"]
        big = 10 ** 5000  # more digits than Python turns into text by default
        world.event(lambda: lamp.fields.__setitem__("count", Fraction(-big)))  # the rule allows it
        self.assertTrue(out[-1].startswith("-100,000,"))
        self.assertGreater(len(out[-1]), 5000)
        limit = sys.getrecursionlimit()
        seen = []
        world.event(lambda: seen.append(sys.getrecursionlimit()))
        self.assertGreaterEqual(seen[0], 20_000)
        self.assertEqual(sys.getrecursionlimit(), limit)


class Chapters(InTemporaryFolder, Base):
    """A program split over files: chapters, and books of them."""

    def write(self, name, text):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_main(self, source, name="main.english"):
        out = []
        world = compile_source(source, self.folder, name).run(out.append)
        return out, world

    def refuses_main(self, source, fragment, stage="compile"):
        with self.assertRaises(EnglishError) as caught:
            self.run_main(source)
        error = caught.exception
        self.assertIn(fragment, error.message + " " + (error.hint or ""))
        self.assertEqual(error.stage, stage)
        return error

    def test_both_forms_and_names_of_several_words(self):
        self.write("roman_numerals.english", 'To work out the shout (text):\n  The answer is "hey".\n')
        self.write("old_shelf/fairy_tales.english", 'Let the moral be "be kind".\n')
        said, _ = self.run_main(
            "Use the roman numerals chapter.\nUse the fairy tales chapter of the old shelf book.\n"
            "Say the shout.\nSay the moral.\n"
        )
        self.assertEqual(said, ["hey", "be kind"])
        self.refuses_main("Use the roman_numerals chapter.\n", "plain words")
        self.refuses_main("Use the roman numerals chapter of the shelf.\n", '"book"')

    def test_a_chapter_is_read_once_where_it_is_first_used(self):
        self.write("a.english", 'Say "a is read".\nLet the count be 1.\n')
        self.write("b.english", 'Use the a chapter.\nSay "b is read".\nAdd 1 to the count.\n')
        said, world = self.run_main(
            'Say "start".\nUse the b chapter.\nUse the a chapter.\nSay "main {the count}".\n'
        )
        self.assertEqual(said, ["start", "a is read", "b is read", "main 2"])
        self.refuses_main("Use the a chapter.\nUse the a chapter.\n", "already uses the a chapter (line 1)")

    def test_chapters_in_a_circle_are_refused(self):
        self.write("a.english", "Use the b chapter.\n")
        self.write("b.english", "Use the c chapter.\n")
        self.write("c.english", "Use the a chapter.\n")
        error = self.refuses_main("Use the a chapter.\n", "a -> b -> c -> a")
        self.assertEqual(error.line.number, 1)
        self.assertIn("c.english, line 1", error.render("main.english"))
        # A chapter that uses the program itself is a circle too.
        self.write("d.english", "Use the main chapter.\n")
        self.refuses_main("Use the d chapter.\n", "main -> d -> main")

    def test_a_missing_chapter_is_refused_saying_where_it_was_looked_for(self):
        self.write("calendar.english", "Let x be 1.\n")
        error = self.refuses_main("Use the moons chapter.\n", "moons.english")
        self.assertIn(str(self.folder / "moons.english"), error.message)
        self.assertIn("Chapters there: calendar.", error.hint)
        error = self.refuses_main("Use the moons chapter of the almanac book.\n", "almanac")
        self.assertIn("There is no folder", error.hint)

    def test_what_a_chapter_shares(self):
        self.write("all.english", "A gem has a size (number).\nThere is a gem called Ruby whose size is 3.\n"
                                  "A gem is big when its size is more than 2.\n")
        self.write("none.english", "This chapter shares nothing.\nLet the secret be 7.\n")
        self.write("some.english", "# A comment may come first.\n\nThis chapter shares only hat and Crown.\n"
                                   "A hat has a size (number).\nThere is a hat called Crown whose size is 5.\n"
                                   "There is a hat called Cap whose size is 1.\nA hat is tall when its size is more than 2.\n"
                                   "The width of a hat is its size * 2.\n")
        said, _ = self.run_main(
            "Use the all chapter.\nUse the none chapter.\nUse the some chapter.\n"
            "Say the number of big gems.\nSay Ruby's size.\nSay Crown's size.\nSay the number of hats.\n"
        )
        self.assertEqual(said, ["1", "3", "5", "2"])
        uses = "Use the all chapter.\nUse the none chapter.\nUse the some chapter.\n"
        self.refuses_main(uses + "Say the secret.\n", '"secret" belongs to the none chapter, which does not share it.')
        self.refuses_main(uses + "Say Cap.\n", '"Cap" belongs to the some chapter, which does not share it.')
        self.refuses_main(uses + "Say the number of tall hats.\n", '"tall" for a hat belongs to the some chapter')
        error = self.refuses_main(uses + "Say Crown's width.\n", '"width" belongs to the some chapter')
        self.assertIn("shares only hat and Crown", error.hint)

    def test_the_shares_sentence_is_checked(self):
        cases = {
            "Let x be 1.\nThis chapter shares nothing.\n": "first sentence",
            "This chapter shares only ghost.\n": 'defines no "ghost"',
            "This chapter shares only the x.\nLet x be 1.\n": "without an article",
            "This chapter shares only x and x.\nLet x be 1.\n": "listed twice",
            "This chapter shares only tally.\nA tally has a count (number).\nTo tally:\n  Say 1.\n": "could mean the kind and verb",
            "This chapter shares only count.\nA tally has a count (number).\n": "shared with its kind",
            "This chapter shares only tallies.\nA tally has a count (number).\n": 'singular: "tally"',
            "This chapter shares x.\nLet x be 1.\n": '"only"',
            "If 1 is 1:\n  This chapter shares nothing.\n": "top level",
        }
        for text, fragment in cases.items():
            with self.subTest(text.splitlines()[0]):
                self.write("c.english", text)
                error = self.refuses_main("Use the c chapter.\n", fragment)
                self.assertEqual(error.line.unit.name, "c")
        # The program itself may say it.
        said, _ = self.run_main("This chapter shares only x.\nLet x be 1.\nSay x.\n")
        self.assertEqual(said, ["1"])
        self.refuses_main("This chapter shares only y.\nLet x be 1.\n", 'defines no "y"')

    def test_a_name_from_a_chapter_this_file_does_not_use(self):
        self.write("a.english", "Let the depth be 3.\nTo dig:\n  Say 1.\n")
        self.write("b.english", "Use the a chapter.\nLet the width be 2.\n")
        self.write("shelf/c.english", "Let the height be 1.\n")
        self.write("shelf/d.english", "Use the c chapter.\n")
        self.refuses_main("Use the b chapter.\nSay the depth.\n", 'Write "Use the a chapter." first.')
        self.refuses_main("Use the b chapter.\nDig.\n", 'Write "Use the a chapter." first.')
        self.refuses_main("Use the d chapter of the shelf book.\nSay the height.\n",
                          'Write "Use the c chapter of the shelf book." first.')
        # Once used, it is fine.
        said, _ = self.run_main("Use the b chapter.\nUse the a chapter.\nSay the depth + the width.\nDig.\n")
        self.assertEqual(said, ["5", "1"])

    def test_a_name_a_chapter_does_not_share_is_its_own(self):
        self.write("a.english", "This chapter shares nothing.\nLet the count be 1.\nA gem has a size (number).\n"
                                "There is a gem called Ruby whose size is 1.\nTo shine:\n  Say 1.\n"
                                "To work out the glow (number):\n  The answer is 1.\n"
                                'Say "a: {the count} {the glow} {the number of gems} {Ruby\'s size}"\n')
        uses = "Use the a chapter.\n"
        said, _ = self.run_main(
            uses + "Let the count be 2.\nA gem has a weight (number).\nThere is a gem called Ruby whose weight is 7.\n"
            'To shine:\n  Say "main shines".\nTo work out the glow (number):\n  The answer is 2.\n'
            "Shine.\nSay \"main: {the count} {the glow} {the number of gems} {Ruby's weight}\"\n")
        self.assertEqual(said, ["a: 1 1 1 1", "main shines", "main: 2 2 1 7"])
        # A variable of a block, or a role, is its block's own.
        said, _ = self.run_main(uses + "To go with a count (number):\n  Let the size be the count.\n  Say the size.\nGo with 4.\n")
        self.assertEqual(said, ["a: 1 1 1 1", "4"])

    def private_chapter(self, name, shares):
        """A chapter with a private variable, verb, worked-out value, adjective on a
        shared kind, kind and thing, which another chapter may have too."""
        self.write("knights.english", "A knight has a courage (number).\n"
                                      "There is a knight called Champion whose courage is 9.\n")
        self.write(f"{name}.english", (
            f"{shares}\n"
            "Use the knights chapter.\n"
            "Let the count be 0.\n"
            f"A cell has a {name} mark (text).\n"
            f'There is a cell called Marker whose {name} mark is "{name}".\n'
            "A knight can be ready.\n"
            "To tidy:\n  Add 1 to the count.\n"
            "To work out the size (number):\n  The answer is the number of cells.\n"
            f"To sweep:\n  Tidy.\n  Now Champion is ready.\n"
            f'  Say "{name}: count {{the count}}, size {{the size}}, Marker {{Marker\'s {name} mark}}, '
            f'ready {{the number of ready knights}}"\n'))

    def test_two_chapters_with_the_same_private_names_work_apart(self):
        self.private_chapter("east", "This chapter shares only sweep.")
        self.write("west.english", (
            "This chapter shares only mop.\n"
            "Use the knights chapter.\n"
            "A cell has a west mark (text) and a level (number).\n"
            'There is a cell called Marker whose west mark is "west" and whose level is 1.\n'
            'There is a new cell whose west mark is "spare" and whose level is 2.\n'
            "Let the count be 100.\n"
            "A knight is ready when its courage is more than 100.\n"
            "To tidy:\n  Subtract 1 from the count.\n"
            "To work out the size (number):\n  The answer is the number of cells.\n"
            "To mop:\n  Tidy.\n"
            '  Say "west: count {the count}, size {the size}, Marker {Marker\'s west mark}, '
            'ready {the number of ready knights}"\n'))
        said, world = self.run_main("Use the east chapter.\nUse the west chapter.\n"
                                    "Sweep.\nMop.\nSweep.\nMop.\n")
        self.assertEqual(said, ["east: count 1, size 1, Marker east, ready 1",
                                "west: count 99, size 2, Marker west, ready 0",
                                "east: count 2, size 1, Marker east, ready 1",
                                "west: count 98, size 2, Marker west, ready 0"])
        # Two kinds, each with its own things; and two things called Marker.
        cells = [kind for kind in world.things if kind.startswith("cell")]
        self.assertEqual(sorted(len(world.things[kind]) for kind in cells), [1, 2])

    def test_a_shared_name_has_one_meaning_in_the_whole_program(self):
        self.write("a.english", "This chapter shares only count.\nLet the count be 1.\n")
        self.write("b.english", "This chapter shares nothing.\nLet the count be 2.\n")
        said, _ = self.run_main("Use the a chapter.\nUse the b chapter.\nSay the count.\n")
        self.assertEqual(said, ["1"])
        self.write("b.english", "This chapter shares only count.\nLet the count be 2.\n")
        error = self.refuses_main("Use the a chapter.\nUse the b chapter.\n", "also shared by the a chapter")
        self.assertEqual(error.line.number, 2)
        # Even when no one file uses both.
        self.write("c.english", "Use the b chapter.\n")
        self.refuses_main("Use the a chapter.\nUse the c chapter.\n", "also shared by the a chapter")

    def test_a_private_name_may_not_clash_with_a_name_a_used_chapter_shares(self):
        self.write("a.english", "This chapter shares only count and shine.\nLet the count be 1.\n"
                                "To shine:\n  Say 1.\n")
        # The file's own name first: refused at the "Use".
        error = self.refuses_main("This chapter shares nothing.\nLet the count be 2.\nUse the a chapter.\n",
                                  'shares "count"')
        self.assertEqual(error.line.number, 3)
        self.assertIn("this file", error.message)
        self.refuses_main("This chapter shares nothing.\nTo shine:\n  Say 2.\nUse the a chapter.\n", 'shares "shine"')
        # The chapter first: refused at the definition.
        error = self.refuses_main("This chapter shares nothing.\nUse the a chapter.\nLet the count be 2.\n",
                                  "already means something (in the a chapter)")
        self.assertEqual(error.line.number, 3)
        self.refuses_main("Use the a chapter.\nTo shine:\n  Say 2.\n", 'already know how to "shine"')
        # A private name of a chapter the file uses is never in view, so it never clashes.
        self.write("b.english", "This chapter shares only polish.\nTo shine:\n  Say 2.\n"
                                "To polish:\n  Shine.\n  Shine.\n")
        said, _ = self.run_main("Use the a chapter.\nUse the b chapter.\nPolish.\nShine.\n")
        self.assertEqual(said, ["2", "2", "1"])

    def test_a_private_kind_is_seen_only_by_its_own_chapter(self):
        self.private_chapter("east", "This chapter shares only sweep.")
        self.write("west.english", (
            "This chapter shares only age and census.\n"
            "A cell has a level (number).\nA cell can be old.\n"
            "There is a cell called Marker whose level is 1.\n"
            'Whenever a cell becomes old:\n  Say "west: {the cell} is old"\n'
            "A cell's level is never more than 5.\n"
            "To age:\n  For each cell:\n    Now the cell is old.\n"
            "  Try:\n    For each cell:\n      Set the cell's level to 9.\n  If that fails:\n"
            '    Say "west: {the problem}"\n'
            "  Try:\n    There is a new cell whose level is 2.\n    Fail because \"no\".\n  If that fails:\n"
            '    Say "west: still {the number of cells}"\n'
            "To census:\n  Say \"west: {the number of cells} cells\"\n"))
        said, _ = self.run_main("Use the east chapter.\nUse the west chapter.\n"
                                "Sweep.\nAge.\nCensus.\nSweep.\n")
        self.assertEqual(said, ["east: count 1, size 1, Marker east, ready 1", "west: Marker is old",
                                'west: That would break a rule: "A cell\'s level is never more than 5."',
                                "west: still 1", "west: 1 cells", "east: count 2, size 1, Marker east, ready 1"])
        # The program can't name either kind of cell.
        self.refuses_main("Use the east chapter.\nUse the west chapter.\nSay the number of cells.\n", "cell")

    def test_a_thing_of_a_kind_a_file_cannot_name_cannot_be_removed_there(self):
        self.write("gems.english", "This chapter shares only biggest.\nA gem has a size (number).\n"
                                   "There is a gem called Ruby whose size is 3.\n"
                                   "To work out the biggest (gem):\n  The answer is Ruby.\n")
        error = self.refuses_main("Use the gems chapter.\nRemove the biggest.\n", "can't name")
        self.assertEqual(error.rule, RULES["shared"][1])

    def test_a_shared_value_may_give_back_a_thing_of_a_kind_that_is_not_shared(self):
        self.write("gems.english", "This chapter shares only biggest.\nA gem has a size (number).\n"
                                   "There is a gem called Ruby whose size is 3.\n"
                                   "To work out the biggest (gem):\n  The answer is Ruby.\n")
        said, _ = self.run_main("Use the gems chapter.\nSay the biggest.\nIf the biggest is the biggest:\n  Say 1.\n")
        self.assertEqual(said, ["Ruby", "1"])
        self.refuses_main("Use the gems chapter.\nSay the biggest's size.\n", "come with the kind")
        self.refuses_main("Use the gems chapter.\nLet g (gem, if any) be nothing.\n", '"gem" belongs to the gems chapter')

    def test_a_library_used_by_two_files_is_loaded_once(self):
        import types
        finished = []
        module = types.ModuleType("englishscript.libraries.gadgets")
        module.SOURCE = "A gadget has a size (number).\nThere is a gadget called Box whose size is 1.\n"
        module.finish = lambda world: finished.append(1)
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        self.write("a.english", "Use the gadgets library.\nAdd 1 to Box's size.\n")
        said, _ = self.run_main("Use the a chapter.\nUse the gadgets library.\nSay Box's size.\n")
        self.assertEqual((said, finished), (["2"], [1]))
        self.refuses_main("Use the a chapter.\nSay Box's size.\n", 'Write "Use the gadgets library." first.')
        self.refuses_main("Use the gadgets library.\nUse the gadgets library.\n", "already in use (line 1)")

    def test_a_whenever_in_a_chapter_makes_the_program_reactive(self):
        self.write("lamps.english", "A lamp has a power (number).\nA lamp can be lit.\n"
                                    "There is a lamp called Glow whose power is 1.\n"
                                    "Whenever a lamp becomes lit:\n  Say \"{the lamp} is lit\"\n")
        self.write("room.english", "Use the lamps chapter.\n")
        program = compile_source("Use the lamps chapter.\nNow Glow is lit.\n", self.folder)
        self.assertTrue(program.compiler.reactive)
        out = []
        program.run(out.append)
        self.assertEqual(out, ["Glow is lit"])
        # Found through a chapter that uses it, too; the reaction applies to the whole world.
        self.write("switch.english", "Use the lamps chapter.\nTo switch:\n  Now Glow is lit.\n")
        program = compile_source("Use the switch chapter.\nSwitch.\n", self.folder)
        self.assertTrue(program.compiler.reactive)
        out = []
        program.run(out.append)
        self.assertEqual(out, ["Glow is lit"])

    def test_a_problem_in_a_chapter_names_its_file_and_line(self):
        self.write("shelf/tales.english", "Let x be 1.\nSay y.\n")
        error = self.refuses_main("Say 0.\nUse the tales chapter of the shelf book.\n", 'what "y" refers to')
        rendered = error.render("main.english")
        self.assertIn("(shelf/tales.english, line 2)", rendered)
        self.assertIn("(The tales chapter is used at main.english, line 2: Use the tales chapter of the shelf book.)",
                      rendered)
        self.write("shelf/tales.english", 'To break:\n  Fail because "it broke".\n')
        error = self.refuses_main("Use the tales chapter of the shelf book.\nBreak.\n", "it broke", stage="run")
        rendered = error.render("main.english")
        self.assertIn("(shelf/tales.english, line 2)", rendered)
        self.assertIn("(while doing main.english, line 2: Break.)", rendered)

    def test_explain_notes_what_a_chapter_brought_in(self):
        self.write("a.english", "This chapter shares only x.\nLet x be 1.\n")
        self.write("b.english", "Use the a chapter.\n")
        notes = explain("Use the b chapter.\nUse the a chapter.\nSay x.\n", self.folder)
        self.assertIn('"b" → b.english, which shares everything', notes)
        self.assertIn('"a" → a.english, read already', notes)

    def test_compile_file_and_the_command_line(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from englishscript import compile_file
        from englishscript.__main__ import main
        self.write("shelf/greeting.english", 'To work out the hello (text):\n  The answer is "Hello".\n')
        path = self.write("prog/../hi.english", "Use the greeting chapter of the shelf book.\nSay the hello.\n")
        out = []
        compile_file(path).run(out.append)
        self.assertEqual(out, ["Hello"])
        os.chdir(self.folder.parent)  # the file's own folder counts, not where it is run from
        name = str(Path(self.folder.name) / "hi.english")
        for flags, expected in (((), "Hello"), (("--check",), "Nothing was run"),
                                (("--explain",), "shelf/greeting.english"), (("--lint",), "Nothing to mend")):
            with self.subTest(flags):
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    status = main([name, *flags])
                self.assertEqual(status, 0, stderr.getvalue())
                self.assertIn(expected, stdout.getvalue())


class AlmanacExample(Base):
    """examples/almanac.english and the chapters of examples/almanac, end to end."""

    PATH = ROOT / "examples" / "almanac.english"

    def test_it_says_the_almanac_and_checks_nine_examples(self):
        from englishscript import compile_file
        out = []
        world = compile_file(self.PATH).run(out.append)
        self.assertEqual(out[0], "An Almanack for the Year MMXXVII,")
        self.assertIn("Candlemas falls on a Tuesday, 2 February.", out)
        self.assertIn("Christmas falls on a Saturday, 25 December.", out)
        self.assertIn("3 of the 7 fall in the cold months.", out)
        self.assertEqual(world.examples, 9)

    def test_each_file_lints_clean(self):
        from englishscript import lint
        for path in [self.PATH, *sorted((ROOT / "examples" / "almanac").glob("*.english"))]:
            with self.subTest(path.name):
                self.assertEqual([p.render() for p in lint(path.read_text(encoding="utf-8"), path.parent)], [])

    def test_only_what_is_shared_can_be_said(self):
        source = self.PATH.read_text(encoding="utf-8")
        folder = self.PATH.parent
        refused = {
            "For each numeral:\n  Say 1.\n": "numeral", 'Say the weight of "X".\n': "weight",
            "Say the month row.\n": "month row", "Say Candlemas.\n": "Candlemas",
            "Say the leftover of 10.\n": "leftover",
        }
        for extra, name in refused.items():
            with self.subTest(name):
                with self.assertRaises(EnglishError) as caught:
                    compile_source(source + extra, folder)
                self.assertIn(f'"{name}" belongs to', caught.exception.message)
                self.assertIn("which does not share it", caught.exception.message)
        out = []
        compile_source(source + "Say Michaelmas.\nSay the number of wintry feasts.\nFor each feast:\n  Skip this feast.\n"
                       "Say the roman of 4.\n", folder).run(out.append)
        self.assertEqual(out[-3:], ["Michaelmas", "3", "IV"])


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

    @staticmethod
    def run_here(source):
        """Run with the chapters looked for in examples/, as the document's examples of chapters expect."""
        out = []
        compile_source(source, ROOT / "examples").run(out.append)
        return out

    def test_examples_run_and_say_what_the_document_claims(self):
        world, *examples = self.blocks("englishscript")
        self.assertGreater(len(examples), 15)
        for body in examples:
            with self.subTest(body.strip().splitlines()[0]):
                try:
                    said = self.run_here(world + body)
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
                    self.run_here(world + body)

    def test_reserved_words_match_the_compiler(self):
        text = (ROOT / "docs" / "SYNTAX.md").read_text(encoding="utf-8")
        table = text.split("| Group | Reserved words |")[1].split("\n\n")[0]
        listed = set()
        for row in table.splitlines()[2:]:
            listed.update(re.findall(r"`(\w+)`", row.split("|")[2]))
        self.assertEqual(listed, set(KEYWORDS))


class ProjectPage(unittest.TestCase):
    """docs/ is served by GitHub Pages. What it serves must match the source."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import build_site

        cls.build = build_site
        cls.docs = ROOT / "docs"
        cls.page = (cls.docs / "index.html").read_text(encoding="utf-8")

    def test_the_bundled_compiler_is_the_current_compiler(self):
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO((self.docs / "play" / "englishscript.zip").read_bytes())) as archive:
            bundled = {name: archive.read(name) for name in archive.namelist()}
        self.assertEqual(bundled, dict(self.build.package_files()), "run: python tools/build_site.py")
        self.assertIn("englishscript/__init__.py", bundled)

    def test_the_bundled_examples_are_the_current_examples(self):
        text = (self.docs / "play" / "examples.json").read_text(encoding="utf-8")
        self.assertEqual(text, self.build.examples_text(), "run: python tools/build_site.py")

    def test_every_program_printed_on_the_page_shows_what_the_compiler_says(self):
        programs = self.build.SNIPPET.findall(self.page)
        self.assertGreaterEqual(len(programs), 10)
        self.assertTrue(any(expect == "refused" for _, expect, *_ in programs))
        # render_page runs each one, and fails if one marked "ok" is refused or the reverse.
        self.assertEqual(self.build.render_page(self.page), self.page, "run: python tools/build_site.py")

    PAGES = ("index.html", "playground.html", "reference.html", "how.html", "vulkan.html")

    def test_the_pages_printed_from_markdown_are_current(self):
        for name, make in (("reference.html", self.build.reference_page), ("vulkan.html", self.build.vulkan_page)):
            with self.subTest(name):
                self.assertEqual((self.docs / name).read_text(encoding="utf-8"), make(), "run: python tools/build_site.py")

    def test_the_grammar_page_carries_every_example_of_the_reference(self):
        page = (self.docs / "reference.html").read_text(encoding="utf-8")
        source = (self.docs / "SYNTAX.md").read_text(encoding="utf-8")
        blocks = re.findall(r"^```(\w+)\n(.*?)^```", source, re.M | re.S)
        runnable = [body for kind, body in blocks if kind == "englishscript"]
        refused = [body for kind, body in blocks if kind == "refused"]
        self.assertEqual(page.count('data-expect="ok"'), len(runnable))
        self.assertEqual(page.count('data-expect="refused"'), len(refused))
        self.assertEqual(page.count("data-world>"), 1)  # the small world every other example builds on
        import html as html_module

        printed = [html_module.unescape(text) for text in re.findall(r'<pre class="program" data-expect="\w+">(.*?)</pre>', page, re.S)]
        self.assertEqual(sorted(text.strip("\n") for text in printed), sorted(body.strip("\n") for body in runnable + refused))
        self.assertNotRegex(re.sub(r"<pre.*?</pre>|<code>.*?</code>", "", page, flags=re.S), r"\*\*|\]\(")  # no stray Markdown

    def test_how_to_say_it_is_current_and_is_a_working_program(self):
        text = (self.docs / "play" / "phrases.json").read_text(encoding="utf-8")
        self.assertEqual(text, self.build.phrases_text(), "run: python tools/build_site.py")
        said = []
        world = compile_source(self.build.phrases_program()).run(said.append, lambda question: "Ada")
        self.assertIn("Hello, Ada.", said)
        self.assertEqual(world.examples, 1)
        from englishscript import lint

        self.assertEqual([p for p in lint(self.build.phrases_program()) if p.kind == "error"], [])

    def test_every_page_links_only_to_what_exists(self):
        for name in self.PAGES:
            with self.subTest(name):
                page = (self.docs / name).read_text(encoding="utf-8")
                self.assertIn('class="sitenav"', page)
                self.assertIn("assets/english.css", page)
                for target in re.findall(r'(?:href|src)="([^"#]+)(?:#[^"]*)?"', page):
                    if target.startswith(("http://", "https://")):
                        continue
                    local = self.docs / ("index.html" if target == "./" else target)
                    self.assertTrue(local.is_file(), f"{name} links to {target}, which is not there")
                for anchor in re.findall(r'href="#([^"]+)"', page):
                    self.assertIn(f'id="{anchor}"', page, f"{name} links to #{anchor}, which is not on the page")

    def test_the_engine_can_find_what_it_loads(self):
        engine = (self.docs / "play" / "engine.js").read_text(encoding="utf-8")
        self.assertIn("englishscript.zip", engine)
        self.assertRegex(engine, r"cdn\.jsdelivr\.net/pyodide/v\d+\.\d+\.\d+/full/")  # a pinned version
        for path in ("play/englishscript.zip", "play/examples.json", "play/snippets.js", "assets/triangle-gpu.png"):
            with self.subTest(path):
                self.assertTrue((self.docs / path).is_file())
        self.assertTrue((self.docs / ".nojekyll").is_file())  # so GitHub Pages serves the files as they are
        for name in ("index.html", "reference.html"):
            self.assertIn("./play/snippets.js", (self.docs / name).read_text(encoding="utf-8"))
        self.assertIn("./play/engine.js", (self.docs / "playground.html").read_text(encoding="utf-8"))


class ThePromise(Base):
    """The four blockers of the adversarial review (docs/CONCERNS.md)."""

    def test_a_rule_holds_from_its_sentence_on(self):
        said = []
        with self.assertRaises(EnglishError) as caught:
            compile_source(WORLD + 'Say "before".\nA dragon\'s age is always at least 100.\nSay "after".').run(said.append)
        self.assertEqual(said, ["before"])
        self.assertEqual(caught.exception.stage, "run")
        self.assertIn("Norbert already breaks this rule", caught.exception.message)
        self.assertEqual(caught.exception.line.text, "A dragon's age is always at least 100.")
        # Before its sentence, the rule does not hold.
        self.assertEqual(run(WORLD + "Set Norbert's age to 0.\nSay Norbert's age.\nSet Norbert's age to 5.\n"
                                     "A dragon's age is always at least 1.\nSay 1."), ["0", "1"])

    def test_a_rule_reads_only_what_cannot_change_behind_its_back(self):
        for source, fragment in (
            ("Let the cap be $10.\nA knight's purse is never more than the cap.", 'the variable "cap"'),
            ("A treasure's owner is always ancient.", 'the adjective "ancient"'),
            ("A treasure's worth is never more than the hoard of Smaug.", "another thing, Smaug"),
            ("A treasure's worth is never more than Gawain's purse.", "another thing, Gawain"),
            ("A treasure's worth is never more than its owner's hoard.", "a property of another thing"),
            ("A knight's purse is never more than the number of dragons * $1.", '"the number'),
        ):
            with self.subTest(source):
                error = self.refuses(WORLD + source, fragment)
                self.assertEqual(error.key, "rule_reads")
        self.assertEqual(run(WORLD + "Let the cap always be $1,000.\nA knight's purse is never more than the cap.\n"
                                     "Say 1."), ["1"])

    def test_a_rule_on_two_of_the_things_own_properties_is_checked_when_either_changes(self):
        source = ("A knight has a purse (money) and a debt (money).\n"
                  "There is a knight called Gawain whose purse is $10 and whose debt is $5.\n"
                  "A knight's debt is never more than its purse.\n")
        self.refuses(source + "Add $10 to Gawain's debt.", "break a rule", stage="run")
        self.refuses(source + "Set Gawain's purse to $1.", "break a rule", stage="run")
        self.assertEqual(run(source + "Add $1 to Gawain's debt.\nSay Gawain's debt."), ["$6"])

    def test_a_rule_on_an_if_any_property_holds_while_it_is_nothing(self):
        source = ("A squire has a wage (money, if any).\nThere is a squire called Wat.\n"
                  "A squire's wage is never more than $9.\n")
        self.assertEqual(run(source + "Set Wat's wage to $5.\nSay Wat's wage."), ["$5"])
        self.refuses(source + "Set Wat's wage to $50.", "break a rule", stage="run")

    def test_numbers_are_said_exactly(self):
        self.assertEqual(run("Say 123,456,789,012,345,678,901 + 0.5.\nSay 1,000,000,000,000,000.1234.\n"
                             "Say 0.00005.\nSay 0.00015.\nSay -0.00005.\nSay -0.00001.\nSay $0.125.\nSay $0.005.\n"
                             "Say -$0.001.\nSay 0.000005%.\nSay 12.34565%."),
                         ["123,456,789,012,345,678,901.5", "1,000,000,000,000,000.1234", "0.0001", "0.0002",
                          "-0.0001", "0", "$0.13", "$0.01", "$0", "0%", "12.3457%"])
        error = self.refuses("For example, 1 / 3 is 0.", "doesn't hold", stage="run")
        self.assertIn("1 / 3 is 0.3333", error.hint)

    CHAIN = ("A node has a label (text) and a next (node, if any).\n"
             'There is a node called Tail whose label is "tail".\n'
             'There is a node called Head whose label is "head" and whose next is Tail.\n'
             "Let the spot (node, if any) be Head.\n")

    def test_a_check_before_a_loop_does_not_count_for_what_the_loop_changes(self):
        self.assertEqual(run(self.CHAIN + "While the spot is not nothing:\n  Say the spot's label.\n"
                                          "  Set the spot to the spot's next."), ["head", "tail"])
        self.assertEqual(run(self.CHAIN + "Repeat 3 times:\n  If the spot is not nothing:\n"
                                          "    Say the spot's label.\n    Set the spot to the spot's next."),
                         ["head", "tail"])
        # What the loop does not change still counts, and a needless check is still refused.
        self.refuses(self.CHAIN + "Repeat 2 times:\n  If the spot is not nothing:\n    Say 1.", "nothing to check")
        self.refuses(self.CHAIN + "Repeat 2 times:\n  Say the length of the spot's next's label.", "may be nothing")

    def test_a_name_is_never_also_an_adjective(self):
        world = WORLD + "A dragon can be sleepy.\n"
        for source, fragment in (
            ("There is a dragon called Ancient whose age is 3.", "already an adjective of a dragon"),
            ("Let ancient be 1.", "already an adjective"),
            ("For each ancient in dragons:\n  Say 1.", "already an adjective"),
            ("To pet a sleepy (number):\n  Say 1.", "already an adjective"),
            ("Let rich be 1.\nA dragon is rich when its age is 1.", '"rich" is already a variable (line'),
            ("A cat has an age (number).\nA dragon is cat when its age is 1.", '"cat" is already a kind'),
            ("A sleepy has an age (number).", "already an adjective"),
            ("Let sleepy count be 1.", "begins with the adjective"),
        ):
            with self.subTest(source):
                self.assertEqual(self.refuses(world + source, fragment).key, "namespaces")
        error = self.refuses(world + "For each ancient rival in dragons:\n  Say 1.", "begins with the adjective")
        self.assertEqual(error.fix["text"], "For each ancient dragon:")
        # A property and a verb may share a word with anything.
        self.assertEqual(run(world + "A gem has a sleepy (number).\nTo ancient:\n  Say 2.\nAncient."), ["2"])

    def test_a_kind_name_in_a_block_holds_that_kind(self):
        self.assertEqual(run(WORLD + "To hatch:\n  Let the dragon be a new dragon whose age is 0.\n"
                                     "  Say the dragon's age.\nHatch."), ["0"])
        self.refuses(WORLD + "To hatch:\n  Let the dragon be 5.\nHatch.", '"the dragon" would read as a dragon')
        self.refuses(WORLD + "To hatch:\n  Let the dragon be Gawain.\nHatch.", "holds a knight")
        self.refuses(WORLD + "To hatch a dragon (number):\n  Say 1.", "this role holds a plain number")

    def test_only_what_a_file_may_say_counts_for_these_checks(self):
        import types
        module = types.ModuleType("englishscript.libraries.rowtest")
        module.SOURCE = "A row has a size (number).\nA row can be ripe.\n"
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "table.english").write_text(
                "To show a row (text):\n  Say the row.\nShow \"a\".\nLet ripe be 1.\nSay ripe.\n", encoding="utf-8")
            out = []
            compile_source("Use the rowtest library.\nUse the table chapter.\n", folder).run(out.append)
            self.assertEqual(out, ["a", "1"])

    def test_two_kinds_never_share_a_name_or_a_plural(self):
        for source, word in (("A bus has a size (number).\nA buse has a size (number).", '"buses"'),
                             ("A ax has a size (number).\nA axe has a size (number).", '"axes"'),
                             ("A dragons has a size (number).", '"dragons"')):
            with self.subTest(source):
                self.assertEqual(self.refuses(WORLD + source, word).key, "kind_names")


class TwoReadings(Base):
    """Phase A: a sentence a careful reader could take two ways is refused, with both readings."""

    SQUIRES = ("A horse has a speed (number).\nA squire has a wage (money) and a mount (horse, if any).\n"
               "There is a horse called Shadowfax whose speed is 40.\n"
               "There is a squire called Wat whose wage is $3 and whose mount is Shadowfax.\n")

    def readings(self, source, first, second):
        error = self.refuses(source, "can be read two ways")
        self.assertIn(f"(1) {first}", error.hint)
        self.assertIn(f"(2) {second}", error.hint)
        return error

    def test_a_whose_filter_followed_by_arithmetic(self):
        self.readings(WORLD + "Say the number of knights whose courage is more than 5 + 1.",
                      "(the number of knights whose courage is more than 5) + 1",
                      "the number of knights whose courage is more than (5 + 1)")
        self.assertEqual(run(WORLD + "Say (the number of knights whose courage is more than 5) + 1.\n"
                                     "Say the number of knights whose courage is more than (5 + 1)."), ["2", "1"])

    def test_a_second_whose_where_a_thing_is_made(self):
        error = self.refuses(self.SQUIRES + "There is a squire called Sum whose wage is the total wage of squires "
                                            "whose wage is more than $2 and whose mount is Shadowfax.",
                             "can belong to the group before it or to the new squire")
        self.assertIn("whose wage is (the total wage of squires whose wage is more than $2) and whose mount",
                      error.fix["text"])
        self.assertEqual(run(self.SQUIRES + error.fix["text"] + "\nSay Sum's wage."), ["$3"])
        self.assertEqual(run(self.SQUIRES + "For each squire whose wage is more than $2 and whose wage is less than $4:\n"
                                            "  Say the squire."), ["Wat"])

    def test_whether_with_and_or_or(self):
        self.readings(WORLD + "If yes is whether Smaug is ancient and Robin is brave:\n  Say 1.",
                      "whether (Smaug is ancient and Robin is brave)", "(whether Smaug is ancient) and Robin is brave")
        self.assertEqual(run(WORLD + "Say whether (Smaug is ancient and Robin is brave)."), ["no"])

    def test_a_bracketed_whether_can_be_followed_by_a_comparison_or_role(self):
        source = ('To check a flag (yes or no) with a label (text):\n  If the flag is yes:\n    Say the label.\n'
                  'Check whether (1 is 1 and 2 is 2) with "both".\n'
                  'If whether (1 is 1 and 2 is 2) is yes:\n  Say "yes".\n'
                  'If no is whether (1 is 2) and 2 is 2:\n  Say "separate".\n'
                  'Say whether (2 + 3) is 5.')
        self.assertEqual(run(source), ["both", "yes", "separate", "yes"])
        self.refuses('If yes is whether (1) is (2) and 2 is 2:\n  Say 1.', "two ways")

    def test_or_else_beside_arithmetic(self):
        self.readings('Say "12" as a number or else 0 + 1.', '("12" as a number or else 0) + 1',
                      '"12" as a number or else (0 + 1)')
        self.assertEqual(run('Say ("12" as a number or else 0) + 1.\nSay "x" as a number or else (0 + 1).'),
                         ["13", "1"])

    def test_not_before_and_or_or(self):
        self.readings(WORLD + "If not Robin is brave and Gawain is brave:\n  Say 1.",
                      "(not Robin is brave) and Gawain is brave", "not (Robin is brave and Gawain is brave)")
        self.assertEqual(run(WORLD + "If Gawain is brave and not Robin is brave:\n  Say 1.\n"
                                     "If (not Robin is brave) and Gawain is brave:\n  Say 2."), ["1", "2"])

    def test_the_x_of_y_is_decided_by_y(self):
        source = WORLD + "To review a courage (number):\n  Say the courage of Gawain.\nReview 1."
        error = self.readings(source, "Gawain's courage", "(the courage) of Gawain")
        self.assertEqual(error.key, "ambiguous_name")
        # Y has no such property: it is the value in view.
        self.assertEqual(run(WORLD + "To work out the pick (number) at a spot (number) of a row (text):\n"
                                     "  The answer is the spot.\n"
                                     "To show a courage (number):\n  Say the pick at the courage of \"x\".\n"
                                     "Show 7."), ["7"])


class Settling(InTemporaryFolder, Base):
    """Whenever everything has settled: once at the end of each turn that changed something."""

    KNIGHTS = "A knight has a purse (money).\nA knight can be sworn.\nThere is a knight called Gawain whose purse is $5.\n"

    def test_once_a_turn_in_the_order_written_from_its_sentence_on(self):
        source = self.KNIGHTS + (
            "Add $1 to Gawain's purse.\n"
            'Whenever everything has settled:\n  Say "first {Gawain\'s purse}"\n'
            'Say "nothing changed".\n'
            "Whenever everything has settled:\n  Say \"second\"\n"
            "To pay:\n  Add $1 to Gawain's purse.\n  Add $1 to Gawain's purse.\n"
            "Pay.\nRepeat 2 times:\n  Add $1 to Gawain's purse.\nNow Gawain is sworn.\n"
        )
        self.assertEqual(run(source), ["nothing changed", "first $8", "second", "first $10", "second",
                                       "first $10", "second"])

    def test_its_changes_set_off_reactions_but_never_another_settling(self):
        source = self.KNIGHTS + (
            "Whenever Gawain becomes sworn:\n  Say \"sworn\"\n"
            "Whenever everything has settled:\n  Say \"settled\"\n  Now Gawain is sworn.\n  Stop.\n  Say \"never\"\n"
            "Add $1 to Gawain's purse.\nAdd $1 to Gawain's purse.\n"
        )
        self.assertEqual(run(source), ["settled", "sworn", "settled"])

    def test_a_problem_in_it_belongs_to_the_turn_and_a_try_does_not_catch_it(self):
        source = self.KNIGHTS + (
            "Whenever everything has settled:\n  If Gawain's purse is more than $9:\n    Fail because \"too rich\"\n"
            "Try:\n  Add $10 to Gawain's purse.\nIf that fails:\n  Say \"caught\"\n"
        )
        said = []
        with self.assertRaises(EnglishError) as caught:
            compile_source(source).run(said.append)
        self.assertEqual(said, [])
        rendered = caught.exception.render()
        self.assertIn("(while doing line 4: Whenever everything has settled:)", rendered)
        self.assertIn("(while doing line 7: Try:)", rendered)

    def test_each_sentence_of_a_chapter_being_read_is_a_turn(self):
        (self.folder / "gems.english").write_text(
            'A gem has a size (number).\nThere is a gem called Ruby whose size is 1.\nSay "read".\n'
            "Add 1 to Ruby's size.\n", encoding="utf-8")
        source = 'Whenever everything has settled:\n  Say "settled"\nUse the gems chapter.\n'
        out = []
        compile_source(source, self.folder).run(out.append)
        self.assertEqual(out, ["settled", "read", "settled"])

    def test_an_event_is_a_turn(self):
        source = self.KNIGHTS + "Whenever everything has settled:\n  Say \"settled {Gawain's purse}\"\n"
        out = []
        world = compile_source(source).run(out.append)
        gawain = world.named["gawain"]

        def change():
            gawain.fields["purse"] = 7
        world.event(change)
        self.assertEqual(out, ["settled $7"])
        # A problem in the settled block undoes the event.
        source = self.KNIGHTS + "Whenever everything has settled:\n  Fail because \"no\"\n"
        world = compile_source(source).run(lambda text: None)
        gawain = world.named["gawain"]
        with self.assertRaises(EnglishError):
            world.event(change)
        self.assertEqual(gawain.fields["purse"], 5)

    def test_it_is_a_definition(self):
        self.refuses(self.KNIGHTS + "If 1 is 1:\n  Whenever everything has settled:\n    Say 1.", "top level")


class Lists(Base):
    """Lists written out, changed and read; lists as properties; groups as lists."""

    WORLD = ("A treasure has a worth (money).\n"
             "A knight has a purse (money) and a shelf (list of treasures).\n"
             "There is a treasure called Goblet whose worth is $3,000.\n"
             "There is a treasure called Cup whose worth is $500.\n"
             "There is a knight called Gawain whose purse is $300.\n"
             "There is a knight called Robin whose purse is $5 and whose shelf is a list of Cup and Goblet.\n")

    def test_writing_reading_and_changing(self):
        said = run("Let the scores be a list of 3, 8, and 5.\nAdd 10 to the scores.\n"
                   "Say the scores joined with \", \".\nSay item 4 of the scores.\nSay item 0 of the scores.\n"
                   "Say item 1.5 of the scores.\nSet item 1 of the scores to 4.\nRemove 8 from the scores.\n"
                   "Remove 99 from the scores.\nSay the scores joined with \"+\".\nSay the total of the scores.\n"
                   "Say the first of the scores.\nSay the last of the scores.\n"
                   "Let the none be an empty list of money.\nSay the total of the none.\nSay the last of the none.\n"
                   "Let the one be a list of 50%.\nSay the one joined with \"\".\n")
        self.assertEqual(said, ["3, 8, 5, 10", "10", "nothing", "nothing", "4+5+10", "19", "4", "10", "$0",
                                "nothing", "50%"])

    def test_lists_as_properties(self):
        said = run(self.WORLD + "Add Goblet to Gawain's shelf.\nSay the number of items in Gawain's shelf.\n"
                   "Say the number of items in Robin's shelf.\nIf Cup is in Robin's shelf and Cup is not in "
                   "Gawain's shelf:\n  Say \"yes\"\nRemove Goblet.\nSay the number of items in Robin's shelf.\n"
                   "Say the number of items in Gawain's shelf.\nThere is a new knight whose purse is $1.\n")
        self.assertEqual(said, ["1", "2", "yes", "1", "0"])

    def test_each_whose_separator_can_follow_a_written_list(self):
        for separator in (" and ", ", ", ", and "):
            with self.subTest(separator=separator):
                source = self.WORLD + ("Let the guest be a new knight whose shelf is a list of Goblet and Cup"
                                       + separator + "whose purse is $17.\nSay the guest's purse.\n"
                                       "Say the number of items in the guest's shelf.\n")
                self.assertEqual(run(source), ["$17", "2"])

    def test_written_lists_accept_only_supported_item_types(self):
        self.refuses("Let the flags be a list of yes and no.", "A list can hold")
        self.refuses("A team is one of sales or support.\nLet the teams be a list of sales and support.",
                     "A list can hold")

    def test_owned_groups_and_long_adjective_chains_in_list_positions(self):
        source = WORLD + (
            "A treasure can be bright.\nA treasure can be small.\n"
            "A treasure can be shiny.\nA treasure can be dusty.\n"
            "There is a bright small shiny dusty treasure called Gem whose owner is Smaug and whose worth is $9.\n"
            "To show a pile (list of treasures):\n  Say the number of items in the pile.\n"
            "To work out the size (number) of a pile (list of treasures):\n  The answer is the number of items in the pile.\n"
            "To work out the prizes (list of treasures) of a dragon:\n  The answer is its bright treasures.\n"
            "For each bright small shiny dusty treasure:\n  Say the treasure.\n"
            "Let the found be bright small shiny dusty treasures.\nShow the found.\n"
            "Show Smaug's bright small shiny dusty treasures.\n"
            "Say the size of (Smaug)'s bright treasures.\n"
            "For each dragon:\n  Let the pile be their bright treasures.\n"
            "  Say the number of items in the pile.\n  Say the number of dragon's bright treasures.\n"
            "  Show the prizes of the dragon.\n"
            "Show Cup's owner's bright treasures.\n")
        self.assertEqual(run(source), ["Gem", "1", "1", "1", "1", "1", "1", "0", "0", "0", "1"])

    def test_brackets_separate_group_filters_from_the_next_property(self):
        start = WORLD + "A shelf has a display (list of treasures) and a size (number).\n"
        source = ("There is a shelf called Desk whose display is treasures whose owner is Smaug"
                  ", and whose size is 2.")
        error = self.refuses(start + source, "can belong to the group")
        self.assertEqual(run(start + error.fix["text"] + "\nSay the number of items in Desk's display."), ["2"])
        source = ("There is a shelf called Desk whose display is (treasures whose owner is Smaug and whose worth is $500)"
                  " and whose size is (the number of treasures whose owner is Smaug and whose worth is $3,000).\n"
                  "Say the first of Desk's display.\nSay Desk's size.")
        self.assertEqual(run(start + source), ["Cup", "1"])

    def test_a_group_where_a_list_is_wanted_is_the_things_in_it_then(self):
        said = run(self.WORLD + "Let the rich be all treasures whose worth is more than $100.\n"
                   "There is a new treasure whose worth is $900.\nSay the number of items in the rich.\n"
                   "Set Gawain's shelf to treasures whose worth is $500.\n"
                   "Say the number of items in Gawain's shelf.\n"
                   "To show a pile (list of treasures):\n  Say the number of items in the pile.\n"
                   "Show all treasures.\nShow treasures whose worth is $500.\n")
        self.assertEqual(said, ["2", "1", "3", "1"])

    def test_a_failed_try_and_reactions_and_loops(self):
        said = run(self.WORLD + "A knight is laden when the number of items in its shelf is at least 2.\n"
                   "Whenever a knight becomes laden:\n  Say \"{the knight} is laden.\"\n"
                   "Add Cup to Gawain's shelf.\nAdd Goblet to Gawain's shelf.\n"
                   "Try:\n  Remove Cup from Gawain's shelf.\n  Fail because \"no\".\nIf that fails:\n"
                   "  Say the number of items in Gawain's shelf.\n"
                   "Let the scores be a list of 1, 2 and 3.\nFor each score in the scores:\n"
                   "  Add the score * 10 to the scores.\nSay the number of items in the scores.\n")
        self.assertEqual(said, ["Gawain is laden.", "2", "6"])

    def test_working_out_may_change_only_its_own_list(self):
        said = run("To work out the evens (list of numbers) to a top (number):\n"
                   "  Let the found be an empty list of numbers.\n  Let the n be 2.\n"
                   "  While the n is at most the top:\n    Add the n to the found.\n    Add 2 to the n.\n"
                   "  The answer is the found.\nSay the evens to 7 joined with \" \".\n")
        self.assertEqual(said, ["2 4 6"])
        self.refuses("Let the kept be an empty list of numbers.\nTo work out the size (number):\n"
                     "  Add 1 to the kept.\n  The answer is 1.\n", "can't change anything")

    def test_set_item_of_no_item_is_a_problem_a_try_can_recover_from(self):
        said = run("Let the scores be a list of 1.\nTry:\n  Set item 2 of the scores to 5.\nIf that fails:\n"
                   "  Say the problem.\n")
        self.assertEqual(said, ["There is no item 2 of the scores: it has 1 item."])
        self.refuses("Let the scores be a list of 1.\nSet item 2 of the scores to 5.\n", "no item 2", stage="run")

    def test_refusals(self):
        self.refuses("Say the number of items in a list of 1 and 2.\n", "whole value")
        self.refuses('Let the scores be a list of 1, "two" and 3.\n', "all of one kind")
        self.refuses("Let the scores be a list of 1.\nAdd $5 to the scores.\n", "holds numbers")
        self.refuses("Let the scores be a list of 1.\nSubtract 1 from the scores.\n", "Remove 1 from the scores")
        self.refuses("Let the scores be a list of 1.\nRemove the scores.\n", "Only a thing can be removed")
        self.refuses("Let the words be a list of \"a\".\nSay the words joined with 5.\n", "takes text")
        self.refuses(self.WORLD + "Say Gawain's shelf joined with \", \".\n", "only a list of text")
        self.refuses("Let the scores be a list of 1.\nIf \"a\" is in the scores:\n  Say 1.\n", "can't be one")
        error = self.refuses("To work out the total (number) of a pile (list of numbers):\n  The answer is 1.\n"
                             "Let the scores be a list of 1.\nSay the total of the scores.\n", "two ways")
        self.assertEqual(error.teach, "ambiguous_name") if isinstance(error.teach, str) else None

    def test_item_and_first_and_total_are_free_for_names(self):
        said = run("Let the item be 5.\nSay the item.\nSay item.\nFor each word in the words of \"x\":\n"
                   "  Say the word.\nA box has a total (number) and a first (text).\n"
                   "There is a box called Crate whose total is 7 and whose first is \"a\".\n"
                   "Say Crate's total.\nSay the first of Crate.\nSay the first 2 letters of \"abc\".\n")
        self.assertEqual(said, ["5", "5", "x", "7", "a", "ab"])


class MoreArithmetic(Base):
    """Remainders, rounding, powers, roots, larger and smaller, absolute values, percentages."""

    def test_the_forms(self):
        said = run("Say the remainder of 17 divided by 5.\nSay the remainder of -7 divided by 2.\n"
                   "Say the remainder of 7 divided by -2.\nSay the remainder of -7 divided by -2.\n"
                   "Say the remainder of 7.5 divided by 2.\n"
                   "Say 12.5 rounded to the nearest 5.\nSay -12.5 rounded to the nearest 5.\n"
                   "Say -17 rounded up to the nearest 5.\nSay -17 rounded down to the nearest 5.\n"
                   "Say 2 + 17 rounded to the nearest 5.\nSay 5% rounded to the nearest 2%.\n"
                   "Say 2 raised to the power of -2.\nSay 8 raised to the power of (2 / 3).\n"
                   "Say the square root of 0.25.\nSay the larger of 2% and 3%.\nSay the smaller of -$1 and $1.\n"
                   "Say the absolute value of -$2.50.\n")
        self.assertEqual(said, ["2", "1", "-1", "-1", "1.5", "15", "-15", "-20", "-15", "17", "6%", "0.25", "4",
                                "0.5", "3%", "-$1", "$2.50"])

    def test_inexact_answers_have_twelve_places_from_the_exact_fraction(self):
        program = compile_source("Let the r be the square root of 2.\nLet the p be 2 raised to the power of 0.5.\n")
        world = program.run(lambda line: None)
        self.assertEqual(world.globals.vars["r"], Fraction(1414213562373, 10 ** 12))
        self.assertEqual(world.globals.vars["p"], world.globals.vars["r"])

    def test_problems_a_try_can_recover_from(self):
        for value, message in (("the square root of -4", "no square root"),
                               ("the remainder of 3 divided by 0", "divide by zero"),
                               ("(-8) raised to the power of 0.5", "not whole"),
                               ("0 raised to the power of -1", "divide by zero"),
                               ("5 rounded to the nearest 0", "more than nothing")):
            with self.subTest(value):
                said = run(f"Try:\n  Say {value}.\nIf that fails:\n  Say the problem.\n")
                self.assertIn(message, said[0])

    def test_percentages_and_minus_signs(self):
        said = run("Say 10% - 15%.\nSay 3 * 10%.\nSay 10% / 4.\nSay 10% / 5%.\nLet the rate be 5%.\n"
                   "Add 1% to the rate.\nSay the rate.\n"
                   "To work out the double (number) of a value (number):\n  The answer is the value * 2.\n"
                   "Say the double of -3.\nSay 2 * -3.\nSay 2 - -3.\n")
        self.assertEqual(said, ["-5%", "30%", "2.5%", "2", "6%", "-6", "-6", "5"])

    def test_refusals(self):
        self.refuses("Say the remainder of $5 divided by 2.\n", "plain numbers")
        self.refuses("Say $5 rounded to the nearest 1.\n", "same sort")
        self.refuses("Say the larger of 1 and $1.\n", "two numbers")
        self.refuses("Say 10% + 5.\n", "can't add")
        self.refuses("To work out the remainder (number) of a value (number):\n  The answer is 1.\n"
                     "Say the remainder of 5 divided by 2.\n", "two ways")

    def test_the_words_stay_free_for_names(self):
        said = run("Let the remainder be 4.\nSay the remainder.\nA box has a larger (number).\n"
                   "There is a box called Crate whose larger is 9.\nSay the larger of Crate.\n")
        self.assertEqual(said, ["4", "9"])


class Choices(Base):
    def test_a_set_of_choices(self):
        said = run("A mood is one of sleepy, grumpy, or very cross.\nA dragon has a mood (mood).\n"
                   "A dragon is grumpy when its mood is grumpy.\n"
                   "There is a dragon called Puff whose mood is sleepy.\nSay Puff's mood.\n"
                   "Set Puff's mood to grumpy.\nIf Puff is grumpy and Puff's mood is not sleepy:\n  Say \"yes\"\n"
                   "Let the feeling (mood) be very cross.\nSay \"{the feeling}\"\n"
                   "Say the number of dragons whose mood is grumpy.\n")
        self.assertEqual(said, ["sleepy", "yes", "very cross", "1"])

    def test_refusals(self):
        error = self.refuses("A mood is one of sleepy, grumpy or content.\nA dragon has a mood (mood).\n"
                             "There is a dragon called Puff whose mood is furious.\n", "not one of the moods")
        self.assertIn("sleepy, grumpy or content", error.message)
        self.refuses("A mood is one of sleepy or grumpy.\nLet the m (mood) be grumy.\n", 'Did you mean "grumpy"')
        self.refuses("A mood is one of sleepy.\n", "at least two")
        self.refuses("A mood is one of sleepy, grumpy.\n", '"or"')
        self.refuses("A mood is one of sleepy or grumpy.\nA temper is one of grumpy or calm.\n", "already means")
        self.refuses("A dragon has an age (number).\nA mood is one of dragon or calm.\n", "already means")
        self.refuses("A mood is one of sleepy or grumpy.\nLet the m be sleepy.\nIf the m is happy:\n  Say 1.\n",
                     "not one of the moods")
        self.refuses("A mood is one of sleepy or grumpy.\nLet the m be sleepy.\nIf the m is \"sleepy\":\n  Say 1.\n",
                     "can't compare")
        self.refuses("A mood is one of sleepy or grumpy.\nLet the m be sleepy.\nIf the m is more than grumpy:\n"
                     "  Say 1.\n", "Only numbers")


class Text(Base):
    def test_letters_and_negative_text_tests(self):
        said = run("Say letter 2 of \"abc\".\nSay letter 4 of \"abc\".\nSay letter 0 of \"abc\".\n"
                   "Let the letter be \"z\".\nSay the letter.\n"
                   "If \"abc\" does not contain \"x\" and \"abc\" does not start with \"b\" and \"abc\" "
                   "does not end with \"b\":\n  Say \"none\"\nSay the number of items in the words of \"a  b\tc\".\n")
        self.assertEqual(said, ["b", "nothing", "nothing", "z", "none", "3"])
        self.refuses("Say letter 1 of 5.\n", "takes a letter from text")


class KindsOfProblem(InTemporaryFolder, Base):
    """The problem's kind, Fail again, Either way."""

    def test_each_kind(self):
        cases = {
            "a broken rule": "A box has a size (number).\nA box's size is never more than 1.\n"
                             "There is a box called B whose size is 1.\nTry:\n  Set B's size to 2.\n",
            "a division by zero": "Try:\n  Say 1 / 0.\n",
            "a missing file": "Try:\n  Say the text of the file \"no such file.txt\".\n",
            "a refused removal": "A box has a size (number).\nA tag has a box (box).\n"
                                 "There is a box called B whose size is 1.\nThere is a tag called T whose box is B.\n"
                                 "Try:\n  Remove B.\n",
            "a removed thing": "A box has a size (number).\nThere is a box called B whose size is 1.\n"
                               "Let the gone be B.\nRemove B.\nTry:\n  Say the gone's size.\n",
            "a bad count": "Try:\n  Repeat -1 times:\n    Say 1.\n",
            "a missing item": "Let the l be a list of 1.\nTry:\n  Set item 3 of the l to 1.\n",
            "a bad number": "Try:\n  Say the square root of -1.\n",
            "a failure": "Try:\n  Fail because \"no\".\n",
        }
        for kind, source in cases.items():
            with self.subTest(kind):
                checks = "".join(f"  If the problem is {other}:\n    Say \"{other}\"\n" for other in cases)
                said = run(source + "If that fails:\n" + checks)
                self.assertEqual(said, [kind])

    def test_fail_again_passes_the_same_problem_on(self):
        said = run("Try:\n  Try:\n    Say 1 / 0.\n  If that fails:\n    Say \"inner\"\n    Fail again.\n"
                   "If that fails:\n  Say \"{the problem} {whether (the problem is a division by zero)}\"\n")
        self.assertEqual(said, ["inner", "I can't divide by zero. yes"])
        self.refuses("Fail again.\n", "inside one")

    def test_either_way(self):
        said = run("To go:\n  Try:\n    Say \"try\"\n    Stop.\n  If that fails:\n    Say \"fail\"\n"
                   "  Either way:\n    Say \"either\"\n  Say \"never\"\nGo.\n"
                   "Try:\n  Fail because \"x\".\nIf that fails:\n  Say \"fail\"\nEither way:\n  Say \"either\"\n"
                   "Try:\n  Try:\n    Fail because \"y\".\n  If that fails:\n    Fail again.\n"
                   "  Either way:\n    Say \"inner either\"\nIf that fails:\n  Say the problem.\n")
        self.assertEqual(said, ["try", "either", "fail", "either", "inner either", "y"])
        self.refuses("Either way:\n  Say 1.\n", "straight after")
        self.refuses("If the problem is a broken rule:\n  Say 1.\n", "only means something")
        self.refuses("Try:\n  Say 1.\nIf that fails:\n  If the problem is a broken rul:\n    Say 1.\n",
                     "not a kind of problem")


class Testing(InTemporaryFolder, Base):
    def test_test_reports_every_example_and_goes_on(self):
        source = ('Let the x be 2.\nSay "hello"\nFor example, the x is 2.\nFor example, the x is 3.\n'
                  'Write "a" to the file "written.txt".\nFor example, the x + 1 is 3.\n'
                  'Ask "?" and let the y (number) be the reply.\nFor example, the x is 9.\n')
        results = compile_source(source).test()
        self.assertEqual([(r.line, r.held) for r in results], [(3, True), (4, False), (6, True)])
        self.assertEqual(results[1].fact, "In fact, the x is 2.")
        self.assertFalse(os.path.exists("written.txt"))

    def test_the_command_line(self):
        from englishscript.__main__ import main
        Path("p.english").write_text("For example, 1 is 1.\nFor example, 1 is 2.\n", encoding="utf-8")
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            status = main(["p.english", "--test"])
        self.assertEqual(status, 1)
        self.assertIn("2 examples: 1 held, 1 did not.", out.getvalue())


class Tracing(Base):
    def test_the_trace_as_data(self):
        source = ("A knight has a purse (money).\nA knight is broke when its purse is $0.\n"
                  "There is a knight called Robin whose purse is $5.\n"
                  "Whenever a knight becomes broke:\n  Say \"broke\"\n"
                  "To spend from a knight:\n  Set the knight's purse to $0.\nSpend from Robin.\n")
        seen = []
        compile_source(source).run(lambda text: None, trace=lambda *entry: seen.append(entry))
        lines = [(depth, line, cause) for depth, _, line, _, cause in seen]
        self.assertEqual(lines, [(0, 3, None), (0, 4, None), (0, 8, None), (2, 7, None),
                                 (1, 4, "Robin became broke"), (3, 5, None)])
        self.assertTrue(all(file is None for _, file, _, _, _ in seen))


class Keeping(Base):
    WORLD = ("A card has a wording (text), a line (text) and a done (number).\nA card can be open.\n"
             "There is a card called Milk whose wording is \"milk\", whose line is \"\", and whose done is 0.\n")

    def test_kept_properties_and_adjectives(self):
        said = run(self.WORLD + "Keep each card's line as \"- {its wording}\".\n"
                   "Keep each card open when its done is 0.\n"
                   "Whenever a card becomes not open:\n  Say \"{the card} closed\"\n"
                   "Whenever everything has settled:\n  Say \"settled: {Milk's line}\"\n"
                   "Say Milk's line.\nSet Milk's wording to \"eggs\".\nSet Milk's done to 1.\n"
                   "A tally has a count (number).\nThere is a tally called Total whose count is 0.\n"
                   "Keep Total's count as the number of open cards.\n"
                   "There is a new card whose wording is \"x\" and whose line is \"\" and whose done is 0.\n"
                   "Say Total's count.\n")
        self.assertEqual(said, ["- milk", "settled: - eggs", "Milk closed", "settled: - eggs", "settled: - eggs",
                                "settled: - eggs", "settled: - eggs", "1"])

    def test_refusals(self):
        self.refuses(self.WORLD + "Keep each card's line as \"x\".\nSet Milk's line to \"y\".\n",
                     "kept in step by its own sentence")
        self.refuses(self.WORLD + "Keep each card open when its done is 0.\nNow Milk is not open.\n",
                     "kept in step")
        self.refuses(self.WORLD + "Keep Milk's line as \"x\".\nSet Milk's line to \"y\".\n", "kept in step")
        self.refuses(self.WORLD + "Keep each card's line as 5.\n", "is text")
        self.refuses(self.WORLD + "Keep each card's line as \"x\".\nKeep Milk's line as \"y\".\n", "already kept")

    def test_values_that_never_settle_are_a_problem(self):
        self.refuses("A box has a size (number).\nThere is a box called B whose size is 1.\n"
                     "Keep each box's size as its size + 1.\n", "would not settle", stage="run")

    def test_a_rule_still_holds(self):
        self.refuses("A box has a size (number).\nA box's size is never more than 5.\n"
                     "There is a box called B whose size is 1.\nKeep each box's size as 9.\n", "break a rule",
                     stage="run")

    def test_a_verb_called_keep_still_works(self):
        self.assertEqual(run("To keep:\n  Say \"kept\"\nKeep.\n"), ["kept"])
        self.refuses(self.WORLD + "To keep a card:\n  Say 1.\nKeep each card's line as \"x\".\n", "verb \"keep\"")


class VerbShapes(Base):
    def test_shapes_told_apart_by_their_linking_words(self):
        source = ("A knight has a purse (money).\nA dragon has an age (number).\n"
                  "There is a knight called Gawain whose purse is $5.\nThere is a dragon called Smaug whose age is 1.\n"
                  "To send a knight against a dragon:\n  Say \"{the knight} against {the dragon}\"\n"
                  "To send a dragon to a knight:\n  Say \"{the dragon} to {the knight}\"\n"
                  "To send:\n  Say \"nothing\"\n"
                  "Send Gawain against Smaug.\nSend Smaug to Gawain.\nSend.\n")
        self.assertEqual(run(source), ["Gawain against Smaug", "Smaug to Gawain", "nothing"])
        error = self.refuses("A knight has a purse (money).\nA dragon has an age (number).\n"
                             "To greet a knight:\n  Say 1.\nTo greet a dragon:\n  Say 2.\n", "same linking words")
        self.assertEqual(error.key, "verb_shapes")
        self.refuses(source + "Send Gawain with Smaug.\n", "")


class BooksBesideTheProgram(InTemporaryFolder, Base):
    def write(self, name, text):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_a_chapter_may_use_a_book_beside_the_program(self):
        self.write("tales/start.english", "Use the end chapter of the lore book.\nSay the moral.\n")
        self.write("lore/end.english", 'Let the moral be "be kind".\n')
        out = []
        compile_source("Use the start chapter of the tales book.\n", self.folder, "main.english").run(out.append)
        self.assertEqual(out, ["be kind"])
        self.write("tales/lore/end.english", 'Let the moral be "be brave".\n')
        with self.assertRaises(EnglishError) as caught:
            compile_source("Use the start chapter of the tales book.\n", self.folder, "main.english")
        self.assertIn("two books", caught.exception.message + (caught.exception.hint or ""))


class ReferenceFixes(Base):
    """Phase G: what the reference now states, where it changed behaviour."""

    def test_names_in_any_alphabet(self):
        said = run("A dragon has an age (number).\nThere is a dragon called Fáfnir whose age is 3.\n"
                   "Let the größe be 2.\nSay \"{fáfnir} {the größe}\"\n")
        self.assertEqual(said, ["Fáfnir 2"])

    def test_numbers(self):
        error = self.refuses("Say 0,123.\n", "comma in the wrong place")
        self.assertEqual(error.fix["text"], "Say 123.")
        said = run('Say "-5" as a number.\nSay " 5" as a number.\nSay "007" as a number.\n'
                   'Say "+5" as a number.\nSay "0,123" as a number.\nSay "1,000" as a number.\n')
        self.assertEqual(said, ["-5", "5", "7", "nothing", "nothing", "1,000"])

    def test_braces_and_quotes_in_text(self):
        self.refuses('Say "a } b"\n', "closes no fill-in")
        self.refuses('A dragon has an age (number).\nSay "{the dragon called ""x""}"\n', "can't contain quotes")
        self.assertEqual(run('Say "a }} b {{c}}"\n'), ["a } b {c}"])


class Indexes(Base):
    """'whose <property> is <value>' finds things through an index; it must agree with a search."""

    def test_the_index_follows_every_change(self):
        said = run("A slot has a place (number).\n"
                   "There is a slot called Ann whose place is 1.\nThere is a slot called Bob whose place is 2.\n"
                   "There is a slot called Cid whose place is 1.\n"
                   "To show a spot (number):\n  Let the found be \"\".\n"
                   "  For each slot whose place is the spot:\n    Set the found to \"{the found}{the slot}\".\n"
                   "  Say \"{the spot}: {the found}\"\n"
                   "Show 1.\nSet Bob's place to 1.\nShow 1.\nSet Ann's place to 3.\nShow 1.\nShow 3.\n"
                   "There is a new slot called \"Dot\" whose place is 1.\nShow 1.\nRemove Cid.\nShow 1.\n"
                   "Try:\n  Set Ann's place to 1.\n  Remove Bob.\n  Fail because \"no\".\nIf that fails:\n  Show 1.\n"
                   "Set Ann's place to 1.\nShow 1.\nSay the number of slots whose place is 1 and whose name is \"Ann\".\n")
        self.assertEqual(said, ["1: AnnCid", "1: AnnBobCid", "1: BobCid", "3: Ann", "1: BobCidDot", "1: BobDot",
                                "1: BobDot", "1: AnnBobDot", "1"])

    def test_things_found_and_text_and_things_as_values(self):
        said = run("A knight has a lord (knight, if any) and a motto (text).\n"
                   "There is a knight called Arthur whose motto is \"x\".\n"
                   "There is a knight called Kay whose lord is Arthur and whose motto is \"x\".\n"
                   "There is a knight called Bors whose lord is Kay and whose motto is \"y\".\n"
                   "Say the number of knights whose motto is \"x\".\n"
                   "For each knight whose motto is \"y\":\n  Say the knight.\n")
        self.assertEqual(said, ["2", "Bors"])


class StatedPlurals(Base):
    CHILD = "A child has an age (number).\nThere is a child called Ann whose age is 3.\n"
    CHILDREN = "A child (plural children) has an age (number).\nThere is a child called Ann whose age is 3.\n"

    def test_a_stated_plural_replaces_the_one_by_rule(self):
        self.assertEqual(run(self.CHILDREN + "Say the number of children.\n"
                                             "For each kid in children:\n  Say the kid."), ["1", "Ann"])
        error = self.refuses(self.CHILDREN + "Say the number of childs.", "childs")
        self.assertIn('stated as "children"', error.hint)

    def test_the_helper_shows_how_to_state_a_plural(self):
        error = self.refuses(self.CHILD + "Say the number of children.", '"children"')
        self.assertIn("A child (plural children) has ...", error.hint)

    def test_what_is_refused(self):
        for source, fragment in (
            ("A sheep (plural sheep) has an age (number).", "has to differ"),
            ("A kid has an age (number).\nA child (plural kids) has an age (number).", '"kids"'),
            ("A kid has an age (number).\nA child (plural kid) has an age (number).", '"kid"'),
            ("A dragon has an age (number).\nThere is a dragon called Ann whose age is 1.\nA child (plural ann) has an age (number).",
             "already means something"),
            ("A dragon has an age (number).\nA dragon is ancient when its age is 1.\nA child (plural ancient) has an age (number).", "already an adjective"),
            ("A child (plural) has an age (number).", "plural"),
        ):
            with self.subTest(source):
                self.refuses(source, fragment)


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


class AskingAModel(Base):
    """Section 7.8: "Ask the model", with plain functions as the listener."""

    LETTER = ('A team is one of sales, support or very cross.\n'
              'A letter has a wording (text), a worth (money), a rate (percent), a mood (team, if any), '
              'a sender (dragon) and a tags (list of text).\n'
              'There is a letter called Note whose wording is "Help" and whose worth is $1,000.5 and whose rate '
              'is 12.5% and whose sender is Smaug.\n')

    def ask(self, source, replies, judge=None):
        """Run with a model that gives `replies` in turn; returns (said, what the model was asked)."""
        out, asked, waiting = [], [], list(replies)

        def model(question, state, shape, complaint):
            asked.append((question, state, shape, complaint))
            return waiting.pop(0)
        compile_source(WORLD + source).run(out.append, model=model, judge=judge)
        return out, asked

    def test_every_type_of_reply(self):
        cases = [("text", "  two words ", "  two words "), ("number", "1,250.5", "1,250.5"), ("money", "$5", "$5"),
                 ("money", "2.50", "$2.50"), ("percent", "12.5%", "12.5%"), ("yes or no", "Y", "yes"),
                 ("team", "Very  Cross", "very cross"), ("number, if any", "nothing", "nothing"),
                 ("text, if any", "Nothing", "nothing")]
        for type_, reply, said in cases:
            with self.subTest(type_):
                out, asked = self.ask(self.LETTER + f'Ask the model "Q?" and let the p (' + type_ + ') be the reply.\n'
                                      "Say the p.\n", [reply])
                self.assertEqual(out, [said])
                self.assertIsNone(asked[0][1])
        for type_, reply, said in [("list of numbers", "1\n\n2,000\n", "1, 2,000"), ("list of text", "a b\nc", "a b, c"),
                                   ("list of money", "$1\n2", "$1, $2"), ("list of percentages", "", "")]:
            with self.subTest(type_):
                out, _ = self.ask(f'Ask the model "Q?" and let the p ({type_}) be the reply.\n'
                                  'Say the p joined with ", "\n', [reply])
                self.assertEqual(out, [said])

    def test_the_shape_handed_to_the_model(self):
        _, asked = self.ask(self.LETTER + 'Ask the model "Q?" and let the p (team, if any) be the reply.\n'
                            'Ask the model "Q?" and let the q (list of percentages) be the reply.\n'
                            'Ask the model "Q?" and let the c (yes or no) be the reply.\n', ["sales", "1%", "no"])
        self.assertEqual([shape for _, _, shape, _ in asked], [
            {"type": "choice", "choices": ["sales", "support", "very cross"], "items": None, "optional": True},
            {"type": "list", "choices": None, "items": "percent", "optional": False},
            {"type": "yes or no", "choices": None, "items": None, "optional": False}])

    def test_a_thing_as_the_state_and_its_exact_layout(self):
        _, asked = self.ask(self.LETTER + 'Ask the model "Sum up {Note}." about Note and let the gist (text) be the '
                            "reply.\n", ["ok"])
        self.assertEqual(asked[0][0], "Sum up Note.")
        self.assertEqual(asked[0][1], "letter called Note\nwording: Help\nworth: $1,000.50\nrate: 12.5%\n"
                                      "mood: nothing\nsender: Smaug\ntags: an empty list")
        _, asked = self.ask(self.LETTER + 'Set Note\'s tags to a list of "x", "y" and "z".\nSet Note\'s mood to sales.\n'
                            'Ask the model "Q" about "plain" and let the p (text) be the reply.\n'
                            'Ask the model "Q" about Note and let the q (text) be the reply.\n', ["1", "2"])
        self.assertEqual(asked[0][1], "plain")
        self.assertIn("mood: sales\nsender: Smaug\ntags: a list of x, y and z", asked[1][1])

    def test_a_misread_reply_is_asked_again_and_then_read(self):
        out, asked = self.ask('Ask the model "How many?" and let the n (number) be the reply.\nSay the n + 1.\n',
                              ["about seven", "7"])
        self.assertEqual(out, ["8"])
        self.assertEqual([complaint for *_, complaint in asked],
                         [None, 'I could not read "about seven": the reply has to be a number, such as 7 or 2.5, and '
                                "nothing else."])

    def test_three_misreads_are_a_bad_reply(self):
        source = ('Try:\n  Ask the model "Which?" and let the t (team) be the reply.\nIf that fails:\n'
                  '  Say whether (the problem is a bad reply).\n  Say the problem.\n')
        out, asked = self.ask(self.LETTER + source, ["blue", "green", "x" * 100])
        self.assertEqual(len(asked), 3)
        self.assertEqual(out, ["yes", 'The model\'s reply could not be read as one of sales, support or very cross: "'
                                      + "x" * 60 + '..."'])
        with self.assertRaises(EnglishError) as caught:
            self.ask('Ask the model "N" and let the n (number) be the reply.\n', ["a", "b", "c"])
        self.assertEqual((caught.exception.kind, caught.exception.stage), ("bad reply", "run"))

    def test_no_reply_is_a_bad_reply_at_once(self):
        source = ('Try:\n  Ask the model "Q" and let the t (text) be the reply.\nIf that fails:\n'
                  '  If the problem is a bad reply:\n    Say the problem.\n')
        out, asked = self.ask(source, [None])
        self.assertEqual(len(asked), 1)
        self.assertEqual(out, ["The model gave no reply: it refused to answer, or its answer was cut short."])

    def test_no_model(self):
        source = ('Try:\n  Ask the model "Q" and let the t (text) be the reply.\nIf that fails:\n'
                  '  If the problem is no model:\n    Say the problem.\n'
                  'Try:\n  Judge "Q" about "x" and let the c (percent) be the chance.\nIf that fails:\n'
                  '  Say whether (the problem is not no model).\n')
        self.assertEqual(run(source), ["No model is listening.", "no"])
        error = self.refuses('Ask the model "Q" and let the t (text) be the reply.\n', "No model is listening.",
                             stage="run")
        self.assertEqual((error.kind, error.recoverable, error.see), ("no model", True, "7.8"))

    def test_a_problem_the_listener_reports(self):
        def model(*_):
            raise EnglishError("The network is down.", stage="run", recoverable=True)
        out = []
        compile_source('Try:\n  Ask the model "Q" and let the t (text) be the reply.\nIf that fails:\n'
                       '  Say "{the problem}: {whether (the problem is a bad reply)}"\n').run(out.append, model=model)
        self.assertEqual(out, ["The network is down.: yes"])

    def test_a_fault_in_the_listener_ends_the_program(self):
        def model(*_):
            raise ValueError("oops")
        with self.assertRaises(EnglishError) as caught:
            compile_source('Try:\n  Ask the model "Q" and let the t (text) be the reply.\nIf that fails:\n'
                           '  Say 1.\n').run(lambda text: None, model=model)
        self.assertEqual(caught.exception.message, "The model failed: ValueError: oops")
        self.assertFalse(caught.exception.recoverable)
        with self.assertRaises(EnglishError) as caught:
            compile_source('Ask the model "Q" and let the t (text) be the reply.\n').run(
                lambda text: None, model=lambda *_: 5)
        self.assertIn("not text", caught.exception.message)

    def test_refusals(self):
        self.refuses(WORLD + 'Ask the model "Q" and let the d (dragon) be the reply.\n', "I can't ask a model for a dragon")
        self.refuses('Ask the model 5 and let the d (text) be the reply.\n', "The question is text")
        self.refuses(WORLD + 'Ask the model "Q" about 5 and let the d (text) be the reply.\n',
                     "A question is about text or a thing")
        self.refuses('To work out the x (text):\n  Ask the model "Q" and let the d (text) be the reply.\n'
                     "  The answer is the d.\n", "can't ask anything")
        for clash in ('Let the model be "Q?"\n', 'Let the model words be "Q?"\n', "A model has an age (number).\n",
                      'To work out the model (text):\n  The answer is "Q".\n'):
            with self.subTest(clash):
                self.refuses(clash + 'Ask the model "Q" and let the d (text) be the reply.\n', '"Ask the model" could')
        # A plain "Ask" of a variable called model is still read as before.
        self.assertEqual(run_asking('Let the modelling be "Q?"\nAsk the modelling and let the d (text) be the reply.\n'
                                    "Say the d.\n", ["hi"]), ["Q?", "hi"])

    def test_a_reaction_may_ask_a_model_during_an_event(self):
        import types
        module = types.ModuleType("englishscript.libraries.clicks")
        module.SOURCE = "A button has a label (text).\nA button can be pressed.\n"
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        out = []
        source = ('Use the clicks library.\nThere is a button called Go whose label is "go".\n'
                  'Whenever a button becomes pressed:\n'
                  '  Ask the model "Say hi." about the button and let the hello (text) be the reply.\n'
                  '  Judge "Is it urgent?" about the button and let the urgency (percent) be the chance.\n'
                  '  Set the button\'s label to "{the hello} {the urgency}"\n')
        world = compile_source(source).run(out.append, model=lambda q, s, shape, c: f"hi from {s.splitlines()[0]}",
                                           judge=lambda q, s, choices, meanings: 0.5)
        button = world.named["go"]
        self.assertTrue(world.event(lambda: button.marks.add("pressed")))
        self.assertEqual(button.fields["label"], "hi from button called Go 50%")

    def test_the_trace_shows_the_sentence_and_not_the_reply(self):
        seen = []
        compile_source('Ask the model "Q" and let the t (text) be the reply.\n').run(
            lambda text: None, trace=lambda *entry: seen.append(entry), model=lambda *_: "SECRET")
        self.assertEqual(len(seen), 1)
        self.assertNotIn("SECRET", repr(seen))

    def test_test_connects_no_model(self):
        source = ('Try:\n  Ask the model "Q" and let the t (text) be the reply.\nIf that fails:\n'
                  "  For example, the problem is no model.\n")
        self.assertEqual([r.held for r in compile_source(source).test()], [True])


class Judging(Base):
    """Section 7.8: "Judge", with plain functions as the judge."""

    TEAMS = ('A team is one of sales, support or returns.\n'
             'For a team, returns means "the customer wants to send something back".\n'
             'For a team, sales means "a new order".\n')

    def judge(self, source, answer):
        out, asked = [], []

        def judge(question, state, choices, meanings):
            asked.append((question, state, choices, meanings))
            return answer
        compile_source(WORLD + self.TEAMS + source).run(out.append, judge=judge)
        return out, asked

    def test_a_chance(self):
        out, asked = self.judge('Judge "Smaug is angry." about Smaug and let the anger (percent) be the chance.\n'
                                "If the anger is at least 90%:\n  Say \"run\"\nSay the anger.\n", 0.95)
        self.assertEqual(out, ["run", "95%"])
        self.assertEqual(asked, [("Smaug is angry.", "dragon called Smaug\nage: 771", None, None)])
        for answer, said in ((0, "0%"), (1, "100%"), (Fraction(1, 8), "12.5%"), (0.1, "10%")):
            self.assertEqual(self.judge('Judge "Q" about "x" and let the c (percent) be the chance.\nSay the c.\n',
                                        answer)[0], [said])

    def test_a_verdict_with_and_without_a_likelihood(self):
        source = ('Judge "Which team?" about "my cup broke" and let the team (team) be the verdict.\nSay the team.\n'
                  'Judge "Which team?" about "my cup broke" and let the other (team) be the verdict and the sure '
                  "(percent) be the likelihood.\nSay \"{the other} {the sure}\"\n")
        out, asked = self.judge(source, {"sales": 0.1, "support": 0.2, "returns": 0.6})
        self.assertEqual(out, ["returns", "returns 60%"])
        self.assertEqual(asked[0], ("Which team?", "my cup broke", ["sales", "support", "returns"],
                                    {"sales": "a new order", "returns": "the customer wants to send something back"}))

    def test_a_tie_goes_to_the_choice_written_first(self):
        out, _ = self.judge('Judge "Q" about "x" and let the t (team) be the verdict.\nSay the t.\n',
                            {"returns": 0.4, "support": 0.4, "sales": 0.2})
        self.assertEqual(out, ["support"])

    def test_malformed_answers_are_a_bad_reply(self):
        chance = ('Try:\n  Judge "Q" about "x" and let the c (percent) be the chance.\nIf that fails:\n'
                  "  Say whether (the problem is a bad reply).\n")
        for answer in (1.5, -0.1, True, "0.5", None, float("nan"), {"sales": 1}):
            with self.subTest(answer):
                self.assertEqual(self.judge(chance, answer)[0], ["yes"])
        verdict = ('Try:\n  Judge "Q" about "x" and let the t (team) be the verdict.\nIf that fails:\n'
                   "  Say the problem.\n")
        for answer in ({"sales": 0.5, "support": 0.5}, {"sales": 0.5, "support": 0.5, "returns": 0.5, "other": 0},
                       {"sales": 2, "support": 0, "returns": 0}, 0.5, {"sales": 1, "Sales": 0, "support": 0}):
            with self.subTest(answer):
                out, _ = self.judge(verdict, answer)
                self.assertTrue(out[0].startswith("The model's judgement could not be used: a verdict gives a chance "
                                                  "from 0 to 1 to each of sales, support and returns"), out[0])
        out, _ = self.judge(chance, None)
        self.assertEqual(out, ["yes"])

    def test_meanings_and_their_refusals(self):
        self.refuses(self.TEAMS + 'For a team, sales means "again".\n', '"sales" already has a meaning')
        self.refuses(self.TEAMS + 'For a team, calm means "x".\n', "is not one of the teams")
        self.refuses('For a dragon, old means "x".\n', "is not a set of choices")
        self.refuses(self.TEAMS + 'For a team, support means "{1}".\n', "without braces")
        self.refuses(self.TEAMS + 'If 1 is 1:\n  For a team, support means "x".\n', "top level")

    def test_refusals(self):
        self.refuses(self.TEAMS + 'Judge "Q" and let the c (percent) be the chance.\n', "always about something")
        self.refuses(self.TEAMS + 'Judge "Q" about "x" and let the c (number) be the chance.\n',
                     "A chance is a percentage")
        self.refuses(self.TEAMS + 'Judge "Q" about "x" and let the c (percent) be the verdict.\n',
                     "A verdict is one of a set of choices")
        self.refuses(self.TEAMS + 'Judge "Q" about "x" and let the c (percent) be the chance and the l (percent) be '
                     "the likelihood.\n", "A likelihood goes with a verdict")
        self.refuses(self.TEAMS + 'Judge "Q" about "x" and let the t (team) be the verdict and the l (number) be '
                     "the likelihood.\n", "A likelihood is a percentage")
        self.refuses(self.TEAMS + 'Judge "Q" about "x" and let the t (team) be the verdict and the t (percent) be '
                     "the likelihood.\n", '"t" already means something')
        self.refuses(self.TEAMS + 'Judge "Q" about "x" and let the t (team) be the answer.\n',
                     'comes "chance", "verdict" or "grade"')
        self.refuses('To work out the x (percent):\n  Judge "Q" about "x" and let the c (percent) be the chance.\n'
                     "  The answer is the c.\n", "can't ask for a judgement")

    def test_a_verb_called_judge(self):
        verb = "To judge a dragon:\n  Say \"judged {the dragon}\"\n"
        self.assertEqual(run(WORLD + verb + "Judge Smaug.\n"), ["judged Smaug"])
        self.refuses(WORLD + verb + 'Judge "Q" about Smaug and let the c (percent) be the chance.\n',
                     'This could be the verb "judge"')


class ValuesWorkedOutByAModel(Base):
    """Section 9.3: a worked-out value that is one question to a model."""

    SOURCE = ('A team is one of sales, support or returns.\nA ticket has a wording (text).\n'
              'There is a ticket called Jug whose wording is "broken jug".\n'
              'To work out the gist (text) of a letter (text), ask the model "Say what {the letter} wants.".\n'
              'To work out the team (team) for a ticket, judge "Which team should handle this?".\n'
              'To work out the urgency (percent) of a ticket for a sender (text), judge "Is it urgent?".\n'
              'To work out the count (number), ask the model "How many?".\n')

    def test_the_roles_are_the_state(self):
        asked = []

        def model(question, state, shape, complaint):
            asked.append((question, state, shape["type"]))
            return "3" if shape["type"] == "number" else "a refund"

        def judge(question, state, choices, meanings):
            asked.append((question, state, choices))
            return 0.25 if choices is None else {"sales": 0.1, "support": 0.6, "returns": 0.3}
        out = []
        compile_source(self.SOURCE + 'Say the gist of "hi".\nSay the team for Jug.\nSay the urgency of Jug for "Ann".\n'
                       "Say the count + 1.\n").run(out.append, model=model, judge=judge)
        self.assertEqual(out, ["a refund", "support", "25%", "4"])
        self.assertEqual(asked, [("Say what hi wants.", "hi", "text"),
                                 ("Which team should handle this?", "ticket called Jug\nwording: broken jug",
                                  ["sales", "support", "returns"]),
                                 ("Is it urgent?", "ticket: Jug\nsender: Ann", None),
                                 ("How many?", None, "number")])

    def test_the_problems_arise_where_it_is_used(self):
        self.assertEqual(run(self.SOURCE + 'Try:\n  Say the team for Jug.\nIf that fails:\n  Say the problem.\n'),
                         ["No model is listening."])
        out = []
        compile_source(self.SOURCE + 'Try:\n  Say the count.\nIf that fails:\n  Say whether (the problem is a bad '
                       'reply).\n').run(out.append, model=lambda *_: "many")
        self.assertEqual(out, ["yes"])

    def test_refusals(self):
        self.refuses(self.SOURCE + "A ticket is hot when the urgency of it for \"x\" is more than 50%.\n",
                     "asks a model")
        self.refuses(self.SOURCE + "To work out the double (number):\n  The answer is the count * 2.\n", "asks a model")
        self.refuses('To work out the gist (number), judge "Q".\n', "always about something")
        self.refuses('To work out the gist (number) of a letter (text), judge "Q".\n',
                     "A judgement is a chance (percent) or a verdict")
        self.refuses(WORLD + 'To work out the eldest (dragon), ask the model "Q".\n', "can't ask a model for a dragon")
        self.refuses('To work out the gist (text), ask the model "Q":\n  Say 1.\n', "does not open a block")
        # The usual heading, with a block, is unchanged.
        self.assertEqual(run('To work out the gist (text) of a letter (text):\n  The answer is the letter.\n'
                             'Say the gist of "hi".\n'), ["hi"])


class GradesGroupsAndOneAnswer(Base):
    """Section 7.8: grades, judgements put together, and one answer per question in a run."""

    LEVELS = "A level is one of low, middle or high.\n"

    def judged(self, source, answer=None, judges=None, judge=True, model=None):
        """Run with a judge giving `answer` (a function of the request, or a value); returns (said, calls)."""
        out, calls = [], []

        def give(request):
            return answer(request) if callable(answer) else answer

        def one(question, state, choices, meanings):
            calls.append(("judge", question))
            return give({"question": question, "state": state, "choices": choices, "meanings": meanings})

        def many(requests):
            calls.append(("judges", [r["question"] for r in requests]))
            return judges(requests) if callable(judges) else [give(r) for r in requests]
        compile_source(WORLD + self.LEVELS + source).run(out.append, judge=one if judge else None,
                                                         judges=many if judges is not None else None, model=model)
        return out, calls

    def test_a_grade_against_a_verdict(self):
        source = ('Judge "How hot?" about Smaug and let the verdict (level) be the verdict.\n'
                  'Judge "How hot?" about Smaug and let the grade (level) be the grade and the sure (percent) be the '
                  'likelihood.\nSay "{the verdict} {the grade} {the sure}"\n')
        split = {"low": 0.45, "middle": 0.10, "high": 0.45}
        self.assertEqual(self.judged(source, split)[0], ["low middle 10%"])
        clear = {"low": 0.05, "middle": 0.15, "high": 0.8}
        self.assertEqual(self.judged(source, clear)[0], ["high high 80%"])
        # Halfway between two choices goes to the higher one; the chances need not add up to 1.
        self.assertEqual(self.judged(source, {"low": 0.5, "middle": 0.5, "high": 0})[0], ["low middle 50%"])
        self.assertEqual(self.judged(source, {"low": 0.2, "middle": 0, "high": 0.2})[0], ["low middle 0%"])
        out = self.judged('Try:\n  Judge "Q" about Smaug and let the g (level) be the grade.\nIf that fails:\n'
                          "  Say the problem.\n", {"low": 0, "middle": 0, "high": 0})[0]
        self.assertIn("a grade needs a chance of more than 0", out[0])
        self.refuses(self.LEVELS + 'Judge "Q" about "x" and let the g (percent) be the grade.\n',
                     "A grade is one of a set of choices")

    def test_a_grade_as_a_worked_out_value(self):
        source = ('To work out the heat (level) of a dragon, grade "How hot is this dragon?".\n'
                  'To work out the mood (level) of a dragon, judge "How hot is this dragon?".\n'
                  "Say the heat of Smaug.\nSay the mood of Smaug.\n")
        self.assertEqual(self.judged(source, {"low": 0.45, "middle": 0.1, "high": 0.45})[0], ["middle", "low"])
        self.refuses('To work out the heat (number) of a word (text), grade "Q".\n', "A grade is one of a set")

    def test_the_scale_is_told_to_judges(self):
        seen = []

        def many(requests):
            seen.extend(requests)
            return [{"low": 1, "middle": 0, "high": 0}, 0.5]
        out, _ = self.judged('Judge "Q1" about Smaug and let the g (level) be the grade.\n'
                             'Judge "Q2" about Smaug and let the c (percent) be the chance.\nSay "{the g} {the c}"\n',
                             judges=many, judge=False)
        self.assertEqual(out, ["low 50%"])
        self.assertEqual(seen, [
            {"question": "Q1", "state": "dragon called Smaug\nage: 771", "choices": ["low", "middle", "high"],
             "meanings": {}, "scale": True},
            {"question": "Q2", "state": "dragon called Smaug\nage: 771", "choices": None, "meanings": None,
             "scale": False}])

    GROUP = ('Judge "Angry?" about Smaug and let the anger (percent) be the chance.\n'
             'Judge "Hungry?" about Smaug and let the hunger (percent) be the chance.\n'
             'Judge "Which?" about Smaug and let the lvl (level) be the verdict.\n'
             'Say "{the anger} {the hunger} {the lvl}"\n')

    @staticmethod
    def answer(request):
        return {"Angry?": 0.25, "Hungry?": 0.5, "Which?": {"low": 0, "middle": 1, "high": 0}}.get(
            request["question"], 0.1)

    def test_a_group_is_answered_in_one_call_or_one_by_one(self):
        out, calls = self.judged(self.GROUP, self.answer, judges=True)
        self.assertEqual(out, ["25% 50% middle"])
        self.assertEqual(calls, [("judges", ["Angry?", "Hungry?", "Which?"])])
        out, calls = self.judged(self.GROUP, self.answer)
        self.assertEqual(out, ["25% 50% middle"])
        self.assertEqual(calls, [("judge", "Angry?"), ("judge", "Hungry?"), ("judge", "Which?")])
        program = compile_source(WORLD + self.LEVELS + self.GROUP)
        self.assertEqual([len(getattr(step, "group", [step])) for step in program.steps][-2:], [3, 1])

    def test_what_breaks_a_group(self):
        for source, expected in [
            ('Judge "A" about Smaug and let the x (percent) be the chance.\nSay 1.\n'
             'Judge "B" about Smaug and let the y (percent) be the chance.\n', [["A"], ["B"]]),
            ('Judge "A" about Smaug and let the x (percent) be the chance.\n'
             'Judge "B" about Norbert and let the y (percent) be the chance.\n', [["A"], ["B"]]),
            ('Judge "A" about Smaug and let the x (percent) be the chance.\n'
             'Judge "B {the x}" about Smaug and let the y (percent) be the chance.\n', [["A"], ["B 10%"]]),
            ('Judge "A" about Smaug and let the x (percent) be the chance.\n'
             'Judge "B" about  smaug and let the y (percent) be the chance.\n', [["A", "B"]]),
        ]:
            with self.subTest(source):
                _, calls = self.judged(source, 0.1, judges=True, judge=False)
                self.assertEqual([questions for _, questions in calls], expected)

    def test_a_bad_answer_in_a_group_is_a_problem_at_its_own_sentence(self):
        source = ('To check a dragon:\n'
                  '  Judge "Angry?" about the dragon and let the p (percent) be the chance.\n'
                  '  Judge "Bad?" about the dragon and let the q (percent) be the chance.\n'
                  '  Judge "Hungry?" about the dragon and let the r (percent) be the chance.\n'
                  '  Say "never"\n')
        answers = {"Angry?": 0.25, "Bad?": 7, "Hungry?": 0.5}
        caught = []
        for judges in (True, None):
            with self.subTest(judges=judges):
                with self.assertRaises(EnglishError) as error:
                    self.judged(source + "Check Smaug.\n", lambda request: answers[request["question"]],
                                judges=judges)
                caught.append((error.exception.line.number, error.exception.message, error.exception.kind))
                out, calls = self.judged(source + 'Try:\n  Check Smaug.\nIf that fails:\n  Say the problem.\n',
                                         lambda request: answers[request["question"]], judges=judges)
                self.assertEqual(len(calls), 1 if judges else 2)
                self.assertTrue(out[0].startswith("The model's judgement could not be used: a chance"), out)
        self.assertEqual(caught[0], caught[1])
        self.assertEqual(caught[0][0], WORLD.count("\n") + self.LEVELS.count("\n") + 3)
        self.assertEqual(caught[0][2], "bad reply")

    def test_the_names_before_a_bad_answer_keep_their_answers(self):
        from englishscript.compiler import judgement_group
        set_names = []
        program = compile_source('Judge "A" about "x" and let the p (percent) be the chance.\n'
                                 'Judge "B" about "x" and let the q (percent) be the chance.\n')
        group = program.steps[0]
        self.assertEqual(len(group.group), 2)
        from englishscript.runtime import World
        world = World(lambda text: None, judges=lambda requests: [0.25, 7])
        with self.assertRaises(EnglishError) as caught:
            group(world.globals)
        self.assertEqual(caught.exception.line.number, 2)
        self.assertEqual(world.globals.vars.get("p"), Fraction(1, 4))
        self.assertNotIn("q", world.globals.vars)
        self.assertTrue(callable(judgement_group))
        del set_names

    def test_a_wrong_number_of_answers_is_a_fault(self):
        with self.assertRaises(EnglishError) as caught:
            self.judged("Try:\n" + "".join("  " + line + "\n" for line in self.GROUP.splitlines()) +
                        "If that fails:\n  Say 1.\n", judges=lambda requests: [0.5], judge=False)
        self.assertIn("asked 3 questions at once and gave back 1 answers", caught.exception.message)
        self.assertFalse(caught.exception.recoverable)

    def test_no_model_at_the_first_sentence_of_a_group(self):
        with self.assertRaises(EnglishError) as caught:
            compile_source(WORLD + self.LEVELS + self.GROUP).run(lambda text: None)
        self.assertEqual((caught.exception.kind, caught.exception.line.number),
                         ("no model", WORLD.count("\n") + 2))

    def test_the_trace_shows_each_sentence_of_a_group(self):
        seen = []
        compile_source(WORLD + self.LEVELS + self.GROUP).run(
            lambda text: None, trace=lambda *entry: seen.append(entry[2]),
            judges=lambda requests: [self.answer(r) for r in requests])
        first = WORLD.count("\n") + 2
        self.assertEqual(seen[-4:], [first, first + 1, first + 2, first + 3])

    def test_one_answer_per_question_in_a_run(self):
        asked = []

        def model(question, state, shape, complaint):
            asked.append((question, state, complaint))
            return "seven" if len(asked) == 1 else "7"
        source = ('To query a dragon:\n'
                  '  Ask the model "How many?" about the dragon and let the n (number) be the reply.\n'
                  '  Say the n.\n'
                  'Query Smaug.\nQuery Smaug.\nQuery Norbert.\n'
                  'Try:\n  Query Smaug.\n  Fail because "no"\nIf that fails:\n  Query Smaug.\n')
        out = []
        world = compile_source(WORLD + source).run(out.append, model=model)
        self.assertEqual(out, ["7"] * 5)
        self.assertEqual([state.splitlines()[0] for _, state, _ in asked],
                         ["dragon called Smaug", "dragon called Smaug", "dragon called Norbert"])
        self.assertEqual(len(world.answers), 2)  # the misread was not kept
        # A different question, or a different kind of judgement, is asked again.
        _, calls = self.judged('Judge "Q" about Smaug and let the w (level) be the verdict.\n'
                               'Judge "Q" about Smaug and let the x (level) be the grade.\n'
                               'Judge "Q" about Smaug and let the y (level) be the verdict.\n'
                               'Judge "R" about Smaug and let the z (level) be the verdict.\n',
                               {"low": 1, "middle": 0, "high": 0})
        self.assertEqual(calls, [("judge", "Q"), ("judge", "Q"), ("judge", "R")])

    def test_the_answers_are_shared_with_an_event(self):
        import types
        module = types.ModuleType("englishscript.libraries.taps")
        module.SOURCE = "A button has a label (text).\nA button can be pressed.\n"
        sys.modules[module.__name__] = module
        self.addCleanup(sys.modules.pop, module.__name__, None)
        calls = []
        source = ('Use the taps library.\nThere is a button called Go whose label is "go".\n'
                  'Judge "Urgent?" about Go and let the u (percent) be the chance.\n'
                  'Whenever a button becomes pressed:\n'
                  '  Judge "Urgent?" about the button and let the v (percent) be the chance.\n'
                  '  Set the button\'s label to "{the v}"\n')
        world = compile_source(source).run(lambda text: None, judge=lambda *a: calls.append(a) or 0.5)
        button = world.named["go"]
        world.event(lambda: button.marks.add("pressed"))
        self.assertEqual((button.fields["label"], len(calls)), ("50%", 1))


class ConnectingAModel(InTemporaryFolder, Base):
    def test_the_command_line_connects_what_it_is_given(self):
        import io
        import types
        from contextlib import redirect_stdout

        from englishscript.__main__ import main
        fake = types.ModuleType("englishscript.models")
        given = []

        def connect(spec):
            given.append(spec)
            return (lambda question, state, shape, complaint: "Ada"), (lambda *_: 0.75)
        fake.connect = connect
        saved = sys.modules.get("englishscript.models")
        sys.modules["englishscript.models"] = fake
        import englishscript
        saved_attr = getattr(englishscript, "models", None)
        englishscript.models = fake

        def restore():
            if saved is None:
                sys.modules.pop("englishscript.models", None)
            else:
                sys.modules["englishscript.models"] = saved
            if saved_attr is None:
                delattr(englishscript, "models")
            else:
                englishscript.models = saved_attr
        self.addCleanup(restore)
        Path("p.english").write_text('Ask the model "Name?" and let the n (text) be the reply.\n'
                                     'Judge "Q" about the n and let the c (percent) be the chance.\n'
                                     'Say "{the n} {the c}"\n', encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            status = main(["p.english", "--model", "fake:1"])
        self.assertEqual((status, out.getvalue(), given), (0, "Ada 75%\n", ["fake:1"]))
        # Without --model nothing is connected, and --test never connects one.
        import contextlib
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(main(["p.english"]), 1)
        self.assertIn("No model is listening.", err.getvalue())
        self.assertEqual(given, ["fake:1"])


if __name__ == "__main__":
    unittest.main()
