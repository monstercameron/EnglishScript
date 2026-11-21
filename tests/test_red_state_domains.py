import unittest
from pathlib import Path

from englishscript import compile_source
from englishscript.lexer import EnglishError


RED = Path(__file__).resolve().parents[1] / "docs" / "red"
MODES = (
    "opening", "title", "main menu", "intro", "naming", "custom naming", "rival naming",
    "custom rival naming", "walk", "dialogue", "starter", "battle", "battle party",
    "battle bag", "field menu", "party", "bag", "trainer card", "town map", "shop",
)
FLAGS = ("parcel", "dex", "badge", "tm34", "town map", "blue house entered",
         "daisy walking", "route rival beaten")


def compile_with_foundation(source):
    return compile_source("Use the foundation chapter.\n" + source, folder=RED)


def run(source):
    output = []
    compile_with_foundation(source).run(out=output.append)
    return output


class JourneyStateDomains(unittest.TestCase):
    def test_every_mode_is_a_choice_that_can_be_set_and_said(self):
        lines = []
        for mode in MODES:
            lines.extend((f"Set Journey's mode to {mode}.", "Say Journey's mode."))
        self.assertEqual(run("\n".join(lines))[:len(MODES)], list(MODES))

    def test_a_misspelled_mode_is_refused_when_compiled(self):
        for sentence in ("Set Journey's mode to wolk.", "If Journey's mode is batle:\n  Say 1."):
            with self.subTest(sentence=sentence):
                with self.assertRaises(EnglishError) as caught:
                    compile_with_foundation(sentence)
                self.assertEqual(caught.exception.stage, "compile")

    def test_a_mode_written_as_text_is_refused_when_compiled(self):
        with self.assertRaisesRegex(EnglishError, "a mode, but that would make it text"):
            compile_with_foundation('Set Journey\'s mode to "walk".')

    def test_binary_values_remain_writable(self):
        lines = []
        for flag in FLAGS:
            for value in (1, 0):
                lines.extend((f"Set Journey's {flag} to {value}.", f"Say Journey's {flag}."))
        self.assertEqual(run("\n".join(lines))[:2 * len(FLAGS)], ["1", "0"] * len(FLAGS))

    def test_binary_domain_cannot_be_extended(self):
        with self.assertRaisesRegex(EnglishError, 'made with "always"'):
            run("Add 2 to the progress values.")

    def test_every_binary_fact_rejects_out_of_range_and_fractional_values(self):
        for flag in FLAGS:
            for value in ("-1", "2", "1 / 2"):
                with self.subTest(flag=flag, value=value):
                    with self.assertRaisesRegex(EnglishError, "break a rule"):
                        run(f"Set Journey's {flag} to {value}.")


if __name__ == "__main__":
    unittest.main()
