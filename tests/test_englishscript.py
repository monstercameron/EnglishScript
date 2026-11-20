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
