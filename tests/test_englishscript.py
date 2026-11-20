"""Run with:  python -m unittest discover tests"""
import re
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
